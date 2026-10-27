"""FUT-LIN-SENSOR-001 (#13): a background sensor with a clean lifecycle."""

import asyncio
import unittest

from fake_gateway import FakeGateway, bounded

from grok_gadgets_linux import Agent, Device, SDKError
from grok_gadgets_linux.examples import aht20_reader, climate_sensor

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

    @bounded()
    async def test_a_missing_module_drops_the_reading_and_recovers(self):
        def unplugged():
            raise OSError("no module")

        script = iter([(20.0, 40.0), unplugged, (27.0, 41.0), (28.0, 41.0), (20.0, 41.0)])

        def read():
            step = next(script)
            return step() if callable(step) else step

        sensor = climate_sensor(read=read, interval=0.01)
        seen = []
        sensor.publish_state = lambda state: seen.append(dict(state["climate"]))
        stop = asyncio.Event()
        producer = asyncio.create_task(sensor._background[0](stop))
        while len(seen) < 5:
            await asyncio.sleep(0.005)
        stop.set()
        await producer
        self.assertEqual(seen[1]["sensor"], "missing")
        self.assertNotIn("temperature_c", seen[1])
        self.assertEqual(seen[2]["sensor"], "ok")
        # The first reading after the gap is not a crossing; 28 -> 20 is.
        self.assertEqual([e["data"]["value"] for e in sensor.events], [20.0])

    def test_aht20_frames(self):
        sleeps = []

        class Bus:
            def __init__(self, replies):
                self.replies, self.writes, self.closed = iter(replies), [], False

            def write(self, data):
                self.writes.append(bytes(data))

            def read(self, size):
                reply = next(self.replies)
                if isinstance(reply, Exception):
                    raise reply
                return reply

            def close(self):
                self.closed = True

        # 40 % and 25 °C, then the busy bit, then a bus error, then a fresh bus.
        first = Bus(
            [bytes([0x1C, 0x66, 0x66, 0x66, 0, 0]), bytes([0x9C, 0, 0, 0, 0, 0]), OSError()]
        )
        second = Bus([bytes([0x1C, 0x66, 0x66, 0x66, 0, 0])])
        buses = iter([first, second])
        read = aht20_reader(1, open_bus=lambda: next(buses), sleep=sleeps.append)
        temperature, humidity = read()
        self.assertAlmostEqual(humidity, 40.0, places=1)
        self.assertAlmostEqual(temperature, 25.0, places=1)
        self.assertEqual(first.writes[:2], [bytes([0xBE, 0x08, 0x00]), bytes([0xAC, 0x33, 0x00])])
        self.assertIn(0.08, sleeps)
        with self.assertRaises(OSError):
            read()  # Busy.
        with self.assertRaises(OSError):
            read()  # The module stopped answering: the bus closes and opens again next time.
        self.assertTrue(first.closed)
        self.assertAlmostEqual(read()[0], 25.0, places=1)
        self.assertEqual(second.writes[0], bytes([0xBE, 0x08, 0x00]))

    def test_cadence_is_bounded(self):
        with self.assertRaises(ValueError):
            climate_sensor(interval=0.001)
        with self.assertRaises(SDKError):
            Device("x", "x").emit("threshold.crossed", {})
