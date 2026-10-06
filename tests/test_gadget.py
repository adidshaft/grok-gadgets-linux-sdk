import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Annotated, Literal

from fake_gateway import bounded
from grok_gadgets_linux import Agent, Gadget, SDKError
from grok_gadgets_linux.gadget import Range, schema_from_signature

GATEWAY_SOURCE = os.environ.get("GROK_GATEWAY_SOURCE")
TOKEN = "fixture-agent-token-only"


class SchemaTests(unittest.TestCase):
    def test_type_hints_become_a_strict_schema(self):
        def tune(
            on: bool,
            level: Annotated[int, "Brightness", Range(0, 100)],
            mode: Literal["warm", "cool"] = "warm",
            label: str | None = None,
            ratio: float = 1.0,
            tags: list[str] | None = None,
        ) -> dict:
            return {}

        self.assertEqual(
            schema_from_signature(tune),
            {
                "type": "object",
                "properties": {
                    "on": {"type": "boolean"},
                    "level": {
                        "type": "integer",
                        "description": "Brightness",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "mode": {"enum": ["warm", "cool"]},
                    "label": {"type": "string"},
                    "ratio": {"type": "number"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
                "required": ["on", "level"],
            },
        )

    def test_unsupported_or_missing_hints_fail_at_registration(self):
        lamp = Gadget("lamp-1", "Lamp")
        with self.assertRaisesRegex(TypeError, "needs a type hint"):

            @lamp.command("No hint")
            def bad(on):
                return {}

        with self.assertRaisesRegex(TypeError, "Unsupported"):

            @lamp.command("Bad type")
            def worse(on: dict):
                return {}

        with self.assertRaisesRegex(TypeError, "Describe the command"):
            lamp.command(lambda: None)

    def test_hello_carries_descriptions_and_derived_names(self):
        lamp = Gadget("lamp-1", "Desk lamp", state={"on": False})

        @lamp.command("Turn the desk lamp on or off")
        def set_light(on: bool) -> dict:
            return {"on": on}

        lamp.event("motion", "Someone moved in front of the lamp")
        device = lamp.hello(TOKEN)["device"]
        self.assertIn("set.light", device["capabilities"])
        schema = device["capability_schemas"]["set.light"]
        self.assertEqual(schema["description"], "Turn the desk lamp on or off")
        self.assertEqual(schema["required"], ["on"])
        self.assertEqual(
            device["capability_schemas"]["motion"]["description"],
            "Someone moved in front of the lamp",
        )
        self.assertTrue(device["simulated"])
        with self.assertRaises(SDKError):
            lamp.capability("x.set", lambda a: {}, description="x" * 301)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyword_arguments_and_state_merge(self):
        lamp = Gadget("lamp-1", "Lamp", state={"on": False, "level": 5})
        calls = []

        @lamp.command("Turn it on or off")
        def set_light(on: bool) -> dict:
            calls.append(on)
            return {"on": on}

        @lamp.command("Set brightness", name="level.set")
        async def level(level: int) -> None:
            calls.append(level)

        ack = await lamp.execute(
            {"command_id": "c1", "capability": "set.light", "arguments": {"on": True}}
        )
        self.assertEqual((ack["status"], ack["state"]), ("executed", {"on": True, "level": 5}))
        ack = await lamp.execute(
            {"command_id": "c2", "capability": "level.set", "arguments": {"level": 9}}
        )
        self.assertEqual(ack["state"], {"on": True, "level": 5})
        bad = await lamp.execute(
            {"command_id": "c3", "capability": "set.light", "arguments": {"on": "yes"}}
        )
        self.assertEqual(bad["error"]["code"], "invalid_arguments")
        self.assertEqual(calls, [True, 9])


@unittest.skipUnless(GATEWAY_SOURCE, "Set GROK_GATEWAY_SOURCE for real gateway integration")
class GatewayDescriptionTests(unittest.IsolatedAsyncioTestCase):
    @bounded()
    async def test_descriptions_reach_the_gateway(self):
        sys.path.insert(0, GATEWAY_SOURCE)
        from grok_gadgets_gateway.domain import Gateway
        from grok_gadgets_gateway.transport import Credentials, DeviceServer

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text('{"devices": {"lamp-1": {"token": "%s"}}}' % TOKEN)
            path.chmod(0o600)
            gateway = Gateway()
            server = await DeviceServer(gateway, Credentials(path), port=0).start()
            lamp = Gadget("lamp-1", "Desk lamp", state={"on": False})

            @lamp.command("Turn the desk lamp on or off")
            def set_light(on: bool) -> dict:
                return {"on": on}

            stop = asyncio.Event()
            agent = Agent(lamp, TOKEN, port=server.port, poll_interval=0.01)
            task = asyncio.create_task(agent.run(stop))
            try:
                await asyncio.wait_for(agent.connected.wait(), 2)
                listed = gateway.list_devices()[0]
                self.assertEqual(
                    listed["capability_descriptions"]["set.light"],
                    "Turn the desk lamp on or off",
                )
                gateway.command("lamp-1", "set.light", {"on": True}, "g1")
                async with asyncio.timeout(2):
                    while gateway.command_status("g1")["status"] != "executed":
                        await asyncio.sleep(0.01)
                self.assertEqual(gateway.state("lamp-1")["state"], {"on": True})
            finally:
                stop.set()
                await asyncio.wait_for(task, 2)
                await server.close()
