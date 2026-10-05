import asyncio
import json
import unittest
from importlib.resources import files

from grok_gadgets_linux import Device, SDKError
from grok_gadgets_linux.contracts import REQUEST_VALIDATOR, SOURCE, validate_request


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
        with self.assertRaises(SDKError):
            await device.execute({**command, "arguments": {"value": "changed"}})
        bad = await device.execute({**command, "command_id": "c2", "arguments": {"value": 1}})
        self.assertEqual(bad["status"], "failed")
        self.assertEqual(len(calls), 1)

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
        self.assertEqual(SOURCE["source_commit"], "221f73fddba8eec055d7de312066dbf0234d8f6e")
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
