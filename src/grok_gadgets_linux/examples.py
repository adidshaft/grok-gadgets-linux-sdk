"""Software simulation only. Replace handlers with your authorized peripheral code."""

import asyncio
import random
from typing import Annotated

from .contracts import SDKError
from .device import Device
from .gadget import Gadget, Range


def software_lamp():
    device = Device(
        "linux-lamp-1",
        "Linux software lamp",
        simulated=True,
        state={"rgb": {"r": 0, "g": 0, "b": 0, "on": False}, "button": {"pressed": False}},
    )

    async def set_rgb(arguments):
        state = device.state
        state["rgb"] = arguments
        return state

    device.capability("rgb.set", set_rgb).event_capability("button")
    return device


def _simulated_climate():
    """A slow random walk around room conditions. Replace with your sensor's driver."""
    reading = {"temperature_c": 22.0, "humidity_pct": 45.0}

    def read():
        reading["temperature_c"] = min(
            40.0, max(5.0, reading["temperature_c"] + random.uniform(-0.6, 0.6))
        )
        reading["humidity_pct"] = min(
            90.0, max(10.0, reading["humidity_pct"] + random.uniform(-1, 1))
        )
        return reading["temperature_c"], reading["humidity_pct"]

    return read


def climate_sensor(read=None, *, interval=2.0, above_c=25.0, event_limit=16):
    """A simulated climate sensor (hub ADR 013 vocabulary: `climate`, `threshold.crossed`).

    A background producer reads every `interval` seconds, publishes `climate` in the state,
    and emits `threshold.crossed` when the temperature goes above or below `above_c`. Grok Bot
    reads the state with gadgets_get_state and the crossings with gadgets_read_events.
    `read()` returns (temperature °C, relative humidity %); put your authorized driver there.
    """
    if not 0.01 <= interval <= 3600:
        raise ValueError("interval must be 0.01 to 3600 seconds")
    read = read or _simulated_climate()
    sensor = Gadget(
        "climate-1",
        "Simulated climate sensor",
        state={"climate": {"above_c": above_c, "dropped_events": 0}},
        event_limit=event_limit,
    )
    sensor.event(
        "threshold.crossed",
        "The temperature went above or below the threshold: reading, value, above",
    )

    @sensor.command(
        "Set the temperature in °C above which the sensor reports a crossing", name="threshold.set"
    )
    async def threshold_set(above_c: Annotated[float, Range(-40, 85)]) -> dict:
        return {"climate": {**sensor.state["climate"], "above_c": above_c}}

    @sensor.background
    async def sample(stop):
        above = None
        while not stop.is_set():
            temperature, humidity = read()
            climate = sensor.state["climate"]
            now_above = temperature > climate["above_c"]
            climate.update(temperature_c=round(temperature, 1), humidity_pct=round(humidity, 1))
            if above is not None and now_above != above:
                try:
                    sensor.emit(
                        "threshold.crossed",
                        {
                            "reading": "temperature_c",
                            "value": round(temperature, 1),
                            "above": now_above,
                        },
                    )
                except SDKError:
                    climate["dropped_events"] += 1  # The queue is full: count it, never block.
            above = now_above
            sensor.publish_state({**sensor.state, "climate": climate})
            try:
                await asyncio.wait_for(stop.wait(), interval)
            except TimeoutError:
                pass

    return sensor
