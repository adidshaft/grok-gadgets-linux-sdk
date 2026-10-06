import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fake_gateway import bounded
from grok_gadgets_linux import Gadget, SDKError
from grok_gadgets_linux.cli import FactoryError, _token_file, load_device_file

HAS_GATEWAY = importlib.util.find_spec("grok_gadgets_gateway") is not None and (
    importlib.util.find_spec("mcp") is not None
)
GADGET = """from grok_gadgets_linux import Gadget

lamp = Gadget("desk-lamp", "Desk lamp", state={"on": False})


@lamp.command("Turn the desk lamp on or off")
def set_light(on: bool) -> dict:
    return {"on": on}
"""


class LoadingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        return str(path)

    def test_module_gadget_create_and_explicit_function(self):
        self.assertIsInstance(load_device_file(self.write("a.py", GADGET)), Gadget)
        created = self.write("b.py", GADGET + "\ndef create():\n    return lamp\n")
        self.assertEqual(load_device_file(created).device_id, "desk-lamp")
        self.assertEqual(load_device_file(created + ":create").device_id, "desk-lamp")
        two = self.write("c.py", GADGET + '\nother = Gadget("other-1", "Other")\n')
        with self.assertRaisesRegex(FactoryError, "exactly one Gadget"):
            load_device_file(two)

    def test_token_file_is_private_and_reread(self):
        path = self.root / "lamp.token"
        path.write_text("a" * 32 + "\n")
        path.chmod(0o600)
        read = _token_file(path)
        self.assertEqual(read(), "a" * 32)
        path.write_text("b" * 32 + "\n")
        self.assertEqual(read(), "b" * 32)
        path.chmod(0o644)
        with self.assertRaises(SDKError) as caught:
            read()
        self.assertEqual(caught.exception.code, "token_file_insecure")

    def test_missing_gateway_names_the_install_command(self):
        from grok_gadgets_linux import dev

        with mock.patch.dict(sys.modules, {"grok_gadgets_gateway": None}):
            with self.assertRaises(SystemExit) as caught:
                dev._gateway()
        self.assertIn("grok-gadgets-linux-sdk[gateway]", str(caught.exception))


@unittest.skipUnless(HAS_GATEWAY, "Install the [gateway] extra for the dev command test")
class DevStdioTests(unittest.IsolatedAsyncioTestCase):
    @bounded(60)
    async def test_mcp_client_starts_the_gadget_with_no_token(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as folder:
            gadget = Path(folder) / "my_gadget.py"
            gadget.write_text(GADGET)
            environment = {**os.environ, "XDG_CONFIG_HOME": folder}
            environment.pop("GROK_GADGETS_DEVICE_TOKEN", None)
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "grok_gadgets_linux.cli", "dev", "--stdio", str(gadget)],
                env=environment,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    async def call(name, **arguments):
                        result = await session.call_tool(name, arguments)
                        return json.loads(result.content[0].text)

                    for _ in range(100):
                        devices = (await call("gadgets_list_devices"))["devices"]
                        if devices:
                            break
                        await asyncio.sleep(0.05)
                    self.assertEqual(
                        devices[0]["capability_descriptions"]["set.light"],
                        "Turn the desk lamp on or off",
                    )
                    command = (
                        await call(
                            "gadgets_command",
                            device_id="desk-lamp",
                            capability="set.light",
                            arguments={"on": True},
                        )
                    )["command"]
                    self.assertEqual(command["status"], "executed")
                    self.assertEqual(command["reported_state"], {"on": True})
            # Nothing was written to the user's gateway config in stdio mode.
            self.assertFalse((Path(folder) / "grok-gadgets").exists())
