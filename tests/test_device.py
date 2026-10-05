import asyncio
import json
import threading
import time
import unittest
from importlib.resources import files

from grok_gadgets_linux import Device, SDKError
from grok_gadgets_linux.contracts import (
    REQUEST_VALIDATOR,
    SOURCE,
    validate_request,
    worst_case_ack,
)


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    def device(self, **kwargs):
        return Device("linux-test", "software fixture", simulated=True, **kwargs)

    async def test_custom_capability_and_dedup(self):
        calls = []

        async def handler(arguments):
            calls.append(arguments)
            return {"custom": arguments["value"]}

        device = self.device()
        device.capability(
            "display.set",
            handler,
            schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        hello = device.hello("fixture-token-only")
        self.assertIn("display.set", hello["device"]["capability_schemas"])
        command = {"command_id": "c1", "capability": "display.set", "arguments": {"value": "hi"}}
        ack = await device.execute(command)
        self.assertEqual(ack["status"], "executed")
        self.assertEqual(device.state, {"custom": "hi"})
        self.assertEqual(await device.execute(command), ack)
        self.assertEqual(len(calls), 1)
        conflict = await device.execute({**command, "arguments": {"value": "changed"}})
        self.assertEqual(conflict["status"], "failed")
        self.assertEqual(
            conflict["error"],
            {
                "code": "duplicate_conflict",
                "message": "Command ID reused with changed arguments; not executed",
            },
        )
        self.assertEqual(len(calls), 1)
        # The conflict is not cached: the original outcome is still replayed.
        self.assertEqual(await device.execute(command), ack)
        bad = await device.execute({**command, "command_id": "c2", "arguments": {"value": 1}})
        self.assertEqual(bad["status"], "failed")
        self.assertEqual(len(calls), 1)

    async def test_replay_reports_cached_status_with_current_state(self):
        async def handler(arguments):
            return {"value": arguments["value"]}

        device = self.device().capability("x", handler)
        command = {"command_id": "c1", "capability": "x", "arguments": {"value": "red"}}
        self.assertEqual((await device.execute(command))["state"], {"value": "red"})
        device.publish_state({"value": "blue"})
        replay = await device.execute(command)
        self.assertEqual(replay["status"], "executed")
        self.assertEqual(replay["state"], {"value": "blue"})
        failed = {"command_id": "c2", "capability": "absent", "arguments": {}}
        await device.execute(failed)
        device.publish_state({"value": "green"})
        replay = await device.execute(failed)
        self.assertEqual(replay["error"]["code"], "unsupported_capability")
        self.assertEqual(replay["state"], {"value": "green"})

    async def test_largest_state_still_fits_every_failed_ack(self):
        device = self.device()
        size = 0
        for step in (1024, 256, 64, 16, 4, 1):
            while True:
                try:
                    device.publish_state({"blob": "x" * (size + step)})
                except SDKError as error:
                    self.assertEqual(error.code, "frame_too_large")
                    break
                size += step
        self.assertGreater(size, 1700)
        self.assertEqual(device.state["blob"], "x" * size)
        command = {"command_id": "c" * 64, "capability": "absent", "arguments": {}}
        self.assertEqual((await device.execute(command))["status"], "failed")
        conflict = await device.execute({**command, "arguments": {"changed": 1}})
        self.assertEqual(conflict["error"]["code"], "duplicate_conflict")
        self.assertLessEqual(len(validate_request(conflict)), 2048)

    async def test_oversized_handler_state_is_executed_and_deduplicated(self):
        calls = []

        async def handler(arguments):
            calls.append(1)
            return {"blob": "x" * 1990}

        device = self.device(state={"ok": 1}).capability("big", handler)
        command = {"command_id": "c1", "capability": "big", "arguments": {}}
        ack = await device.execute(command)
        self.assertEqual(ack["status"], "executed")
        self.assertNotIn("error", ack)
        self.assertEqual(ack["state"], {"ok": 1})
        self.assertEqual(device.results["c1"][1], None)
        self.assertLessEqual(len(validate_request(ack)), 2048)
        self.assertGreater(
            len(validate_request({"type": "state", "state": {"blob": "x" * 1990}})),
            2000,
        )
        with self.assertRaises(SDKError) as oversized_failure:
            validate_request(worst_case_ack({"blob": "x" * 1990}, "c1"))
        self.assertEqual(oversized_failure.exception.code, "frame_too_large")
        device.publish_state({"ok": 2})
        replay = await device.execute(command)
        self.assertEqual(replay["status"], "executed")
        self.assertEqual(replay["state"], {"ok": 2})
        self.assertEqual(len(calls), 1)

    def test_custom_events_are_annotated_and_reserved_names_guarded(self):
        async def handler(arguments):
            return {}

        device = self.device().event_capability("button").event_capability("motion")
        device.capability("relay.set", handler)
        schemas = device.hello("fixture-token-only")["device"]["capability_schemas"]
        self.assertEqual(schemas, {"motion": {"type": "object", "x-grok-gadgets-kind": "event"}})
        for name in ("button", "history_lost"):
            with self.assertRaises(SDKError):
                self.device().capability(name, handler)
        with self.assertRaises(SDKError):
            self.device().event_capability("history_lost")
        # Sixteen names (15 events + state) still fit the hello frame.
        many = self.device()
        for number in range(15):
            many.event_capability(f"sensor.event-{number:02d}")
        self.assertLessEqual(len(validate_request(many.hello("t" * 256))), 2048)

    async def test_sync_handler_runs_in_thread_without_blocking_loop(self):
        ticks = []
        threads = []

        def blocking(arguments):
            threads.append(threading.current_thread() is threading.main_thread())
            time.sleep(0.2)
            return {"pin": arguments["pin"]}

        async def ticker():
            while True:
                ticks.append(1)
                await asyncio.sleep(0.01)

        device = self.device().capability("gpio.set", blocking)
        task = asyncio.create_task(ticker())
        try:
            ack = await device.execute(
                {"command_id": "g1", "capability": "gpio.set", "arguments": {"pin": 1}}
            )
        finally:
            task.cancel()
        self.assertEqual(ack["state"], {"pin": 1})
        self.assertEqual(threads, [False])
        self.assertGreater(len(ticks), 5)

    async def test_timed_out_sync_handler_never_overlaps_next_call(self):
        running = []
        overlaps = []

        def blocking(arguments):
            overlaps.append(bool(running))
            running.append(1)
            time.sleep(0.15)
            running.pop()
            return {}

        device = self.device().capability("slow", blocking)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(
                device.execute({"command_id": "s1", "capability": "slow", "arguments": {}}), 0.02
            )
        await device.execute({"command_id": "s2", "capability": "slow", "arguments": {}})
        self.assertEqual(overlaps, [False, False])

    async def test_shutdown_callbacks_reverse_order_and_contained(self):
        order = []
        device = self.device()

        def first():
            order.append("first")

        async def second():
            raise RuntimeError("PRIVATE_TOKEN")

        async def third():
            order.append("third")

        device.on_shutdown(first)
        device.on_shutdown(second)
        device.on_shutdown(third)
        await device.shutdown(1)
        self.assertEqual(order, ["third", "first"])
        with self.assertRaises(TypeError):
            device.on_shutdown(None)

    async def test_rgb_bounds_bool_and_handler_failure(self):
        async def handler(arguments):
            raise RuntimeError("TOKEN secret must never leak")

        device = self.device().capability("rgb.set", handler)
        for arguments in [
            {"r": True, "g": 0, "b": 0, "on": True},
            {"r": 256, "g": 0, "b": 0, "on": True},
        ]:
            ack = await device.execute(
                {
                    "command_id": str(len(device.results)),
                    "capability": "rgb.set",
                    "arguments": arguments,
                }
            )
            self.assertEqual(ack["error"]["code"], "invalid_arguments")
        ack = await device.execute(
            {
                "command_id": "valid",
                "capability": "rgb.set",
                "arguments": {"r": 1, "g": 0, "b": 0, "on": True},
            }
        )
        self.assertEqual(ack["error"]["code"], "handler_failed")
        self.assertNotIn("TOKEN", json.dumps(ack))

    def test_pinned_fixtures_validate_and_match_hashes(self):
        self.assertEqual(SOURCE["source_commit"], "5ea23b7ff083b1f493540a4f2747a210e8dae27b")
        fixture = files("grok_gadgets_linux").joinpath(
            "protocol", "0.1.0", "fixtures", "device-transcript.json"
        )
        data = json.loads(fixture.read_text())
        self.assertTrue(data)
        for request in data:
            self.assertTrue(REQUEST_VALIDATOR.is_valid(request))

    def test_event_queue_does_not_drop_silently(self):
        device = self.device(event_limit=2).event_capability("button")
        self.assertEqual(device.emit("button", {"pressed": True}), "e1")
        self.assertEqual(device.emit("button", {"pressed": False}), "e2")
        with self.assertRaises(SDKError):
            device.emit("button", {"pressed": True})
        self.assertEqual([x["data"]["pressed"] for x in device.events], [True, False])

    def test_copy_and_validation_boundaries(self):
        device = self.device(state={"value": 1}).event_capability("button")
        state = device.state
        state["value"] = 2
        self.assertEqual(device.state["value"], 1)
        with self.assertRaises(SDKError):
            device.emit("button", {"pressed": 1})
        with self.assertRaises(SDKError):
            validate_request({"type": "state", "state": {"too_big": "x" * 2048}})
        self.assertFalse(REQUEST_VALIDATOR.is_valid({"type": "hello", "protocol_version": "9"}))

    def test_external_schema_references_rejected(self):
        async def handler(arguments):
            return arguments

        with self.assertRaises(SDKError):
            self.device().capability("x", handler, schema={"$ref": "https://example.com"})
        with self.assertRaises(TypeError):
            self.device().capability("x", None)
        self.device().capability("x", lambda arguments: arguments)

    async def test_dedup_window_is_bounded_and_not_durable(self):
        calls = []

        async def handler(arguments):
            calls.append(1)
            return {}

        device = self.device(command_limit=1).capability("x", handler)
        first = {"command_id": "first", "capability": "x", "arguments": {}}
        await device.execute(first)
        await device.execute({**first, "command_id": "second"})
        await device.execute(first)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(device.results), 1)

    async def test_concurrent_duplicate_does_not_execute_twice(self):
        calls = []

        async def handler(arguments):
            await asyncio.sleep(0.001)
            calls.append(1)
            return {}

        device = self.device().capability("x", handler)
        command = {"command_id": "same", "capability": "x", "arguments": {}}
        results = await asyncio.gather(device.execute(command), device.execute(command))
        self.assertEqual(len(calls), 1)
        self.assertEqual(results[0], results[1])
        with self.assertRaises(SDKError):
            await device.execute({**command, "command_id": "bad id"})
        self.assertEqual(len(calls), 1)
