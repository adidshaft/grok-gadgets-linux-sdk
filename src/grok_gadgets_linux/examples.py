"""Examples. All are simulated except `aht20_climate_sensor`, which reads a real AHT20."""

import asyncio
import fcntl
import os
import random
import time
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


I2C_SLAVE = 0x0703  # linux/i2c-dev.h: address the next reads and writes to one device.
AHT20_ADDRESS = 0x38


def aht20_reader(bus=1, *, open_bus=None, sleep=time.sleep):
    """Return read() for an AHT20 on /dev/i2c-`bus`: (temperature °C, relative humidity %).

    Uses only the kernel's i2c-dev interface (enable I2C, for example with raspi-config).
    A missing or busy module raises OSError; the climate sensor then reports `missing`.
    """
    path = f"/dev/i2c-{int(bus)}"

    def default_open():
        device = open(path, "r+b", buffering=0)  # noqa: SIM115 - kept open between reads
        fcntl.ioctl(device.fileno(), I2C_SLAVE, AHT20_ADDRESS)
        return device

    open_bus = open_bus or default_open
    state = {"bus": None}

    def transfer(write, size=0):
        if state["bus"] is None:
            state["bus"] = open_bus()
            state["bus"].write(bytes([0xBE, 0x08, 0x00]))  # Calibrate (datasheet).
            sleep(0.01)
        try:
            if write:
                state["bus"].write(bytes(write))
            return state["bus"].read(size) if size else b""
        except OSError:
            state["bus"].close()  # Open again on the next read: the module may be back.
            state["bus"] = None
            raise

    def read():
        transfer([0xAC, 0x33, 0x00])  # Trigger a measurement.
        sleep(0.08)
        raw = transfer(None, 6)
        if len(raw) != 6 or raw[0] & 0x80:
            raise OSError("AHT20 is busy or answered short")
        humidity = ((raw[1] << 12) | (raw[2] << 4) | (raw[3] >> 4)) * 100 / 1048576
        temperature = (((raw[3] & 0x0F) << 16) | (raw[4] << 8) | raw[5]) * 200 / 1048576 - 50
        return temperature, humidity

    return read


def aht20_climate_sensor():
    """The climate sensor with a real AHT20 on I2C bus GROK_AHT20_BUS (default 1).

    Run it with `grok-linux-agent --factory grok_gadgets_linux.examples:aht20_climate_sensor`.
    """
    return climate_sensor(
        aht20_reader(os.environ.get("GROK_AHT20_BUS", "1")),
        device_id="climate-aht20-1",
        name="Climate sensor",
        simulated=False,
    )


def climate_sensor(
    read=None,
    *,
    interval=2.0,
    above_c=25.0,
    event_limit=16,
    device_id="climate-1",
    name="Simulated climate sensor",
    simulated=True,
):
    """A climate sensor (hub ADR 013 vocabulary: `climate`, `threshold.crossed`).

    A background producer reads every `interval` seconds, publishes `climate` in the state,
    and emits `threshold.crossed` when the temperature goes above or below `above_c`. Grok Bot
    reads the state with gadgets_get_state and the crossings with gadgets_read_events.
    `read()` returns (temperature °C, relative humidity %); put your authorized driver there.
    Without one, readings are simulated. A read that raises OSError reports `sensor: missing`.
    """
    if not 0.01 <= interval <= 3600:
        raise ValueError("interval must be 0.01 to 3600 seconds")
    read = read or _simulated_climate()
    sensor = Gadget(
        device_id,
        name,
        simulated=simulated,
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
            climate = sensor.state["climate"]
            try:
                temperature, humidity = read()
            except OSError:
                # No stale reading and no crossing: the next good reading starts afresh.
                climate["sensor"] = "missing"
                climate.pop("temperature_c", None)
                climate.pop("humidity_pct", None)
                above = None
            else:
                climate["sensor"] = "ok"
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
                        climate["dropped_events"] += 1  # The queue is full: count it.
                above = now_above
            sensor.publish_state({**sensor.state, "climate": climate})
            try:
                await asyncio.wait_for(stop.wait(), interval)
            except TimeoutError:
                pass

    return sensor
