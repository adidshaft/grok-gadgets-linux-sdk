"""FUT-LIN-SENSOR-001 (#13): a background sensor with a clean lifecycle."""

import asyncio
import unittest

from fake_gateway import FakeGateway, bounded

from grok_gadgets_linux import Agent, Device, SDKError
from grok_gadgets_linux.examples import climate_sensor

TOKEN = "fixture-sensor-token-only"


class Background(unittest.IsolatedAsyncioTestCase):
    @bounded()
    async def test_a_producer_starts_once_survives_reconnects_and_stops_first(self):
        device = Device("sensor-test", "test", simulated=True)
        order, starts = [], []

        @device.background
        async def produce(stop):
            starts.append(1)
            try:
                await stop.wait()
            finally:
                order.append("producer stopped")

        device.on_shutdown(lambda: order.append("shutdown hook"))
        with self.assertRaises(TypeError):
            device.background(lambda stop: None)  # Producers are async functions.

        drops = {"left": 2}

        def respond(message, connection):
            if message["type"] == "poll" and drops["left"]:
                drops["left"] -= 1
                return None  # Close: the agent reconnects.
            return (
                {"ok": True, "commands": []}
                if message["type"] == "poll"
                else (
                    {"ok": True, "session_id": "s", "protocol_version": "0.1.0"}
                    if message["type"] == "hello"
                    else {"ok": True}
                )
            )

        gateway = await FakeGateway(respond).start()
        agent = Agent(device, TOKEN, port=gateway.port, backoff_initial=0.01)
        stop = asyncio.Event()
        task = asyncio.create_task(agent.run(stop))
        while gateway.connections < 3:
            await asyncio.sleep(0.01)
        self.assertEqual(starts, [1])
        stop.set()
        await task
        self.assertEqual(order, ["producer stopped", "shutdown hook"])
        gateway.server.close()


class ClimateSensor(unittest.IsolatedAsyncioTestCase):
    @bounded()
    async def test_readings_threshold_events_and_a_full_queue(self):
        readings = iter([20.0, 24.0, 26.5, 27.0, 23.0, 26.0])
        sensor = climate_sensor(read=lambda: (next(readings), 40.0), interval=0.01, event_limit=2)
        self.assertIn("threshold.crossed", sensor.event_names)
        self.assertEqual(sensor.state["climate"]["above_c"], 25.0)
        stop = asyncio.Event()
        producer = asyncio.create_task(sensor._background[0](stop))
        for _ in range(200):
            if sensor.state["climate"].get("temperature_c") == 26.0:
                break
            await asyncio.sleep(0.005)
        stop.set()
        await producer
        events = [event["data"] for event in sensor.events]
        # Crossing up at 26.5 and down at 23.0; the third crossing finds the queue full.
        self.assertEqual(
            events,
            [
                {"reading": "temperature_c", "value": 26.5, "above": True},
                {"reading": "temperature_c", "value": 23.0, "above": False},
            ],
        )
        self.assertEqual(sensor.state["climate"]["dropped_events"], 1)
        self.assertEqual(sensor.state["climate"]["humidity_pct"], 40.0)

    async def test_threshold_command_is_bounded(self):
        sensor = climate_sensor(read=lambda: (20.0, 40.0))
        result = await sensor.execute(
            {"command_id": "c1", "capability": "threshold.set", "arguments": {"above_c": 30}}
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(sensor.state["climate"]["above_c"], 30)
        bad = await sensor.execute(
            {"command_id": "c2", "capability": "threshold.set", "arguments": {"above_c": 500}}
        )
        self.assertEqual(bad["status"], "failed")

    def test_cadence_is_bounded(self):
        with self.assertRaises(ValueError):
            climate_sensor(interval=0.001)
        with self.assertRaises(SDKError):
            Device("x", "x").emit("threshold.crossed", {})
