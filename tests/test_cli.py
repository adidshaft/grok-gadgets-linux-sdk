import asyncio
import contextlib
import io
import os
import shlex
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fake_gateway import FakeGateway, bounded, error
from grok_gadgets_linux.cli import FactoryError, _token, load_device_file, load_factory, main


async def eventually(predicate, timeout=10):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class FactoryTests(unittest.TestCase):
    def test_builtin_and_explicit_file_without_path_mutation(self):
        self.assertTrue(load_factory("grok_gadgets_linux.examples:software_lamp").simulated)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "gadget.py"
            file.write_text(
                'from grok_gadgets_linux import Device\ndef create():\n return Device("test", "test", simulated=True)\n'
            )
            before = list(sys.path)
            self.assertEqual(load_factory(f"{file}:create", file=True).device_id, "test")
            self.assertEqual(sys.path, before)

    def test_annotated_dataclasses_repeated_loads_and_same_filename(self):
        source = """from __future__ import annotations
from dataclasses import dataclass
from grok_gadgets_linux import Device

@dataclass
class Settings:
    label: str = "LABEL"

def create():
    return Device("test", Settings().label, simulated=True, state={"module": __name__})
"""
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first" / "gadget.py"
            second = Path(directory) / "second" / "gadget.py"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text(source.replace("LABEL", "first"))
            second.write_text(source.replace("LABEL", "second"))
            before = list(sys.path)
            devices = [load_factory(f"{path}:create", file=True) for path in (first, first, second)]
            names = [device.state["module"] for device in devices]
            self.assertEqual(len(set(names)), 3)
            self.assertEqual(
                [sys.modules[name].Settings().label for name in names], ["first", "first", "second"]
            )
            self.assertEqual(sys.path, before)
            # Existing class metadata still resolves its defining module after subsequent loads.
            from typing import get_type_hints

            for name in names:
                self.assertEqual(get_type_hints(sys.modules[name].Settings), {"label": str})

    def test_failed_file_load_rolls_back_its_module_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "failed.py"
            file.write_text('raise RuntimeError("PRIVATE_TOKEN")\n')
            before = {name for name in sys.modules if name.startswith("_grok_trusted_factory_")}
            with self.assertRaises(FactoryError) as caught:
                load_factory(f"{file}:create", file=True)
            after = {name for name in sys.modules if name.startswith("_grok_trusted_factory_")}
            self.assertEqual(after, before)
            self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    def test_safe_actionable_failure_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "gadget.py"
            cases = [
                ('raise RuntimeError("PRIVATE_TOKEN")', "could not load"),
                ('def create():\n raise RuntimeError("PRIVATE_TOKEN")', "function failed"),
                ("create = 7", "function unavailable"),
                ("def create():\n return 7", "must return"),
                ("syntax ??? PRIVATE_TOKEN", "could not load"),
            ]
            for source, category in cases:
                file.write_text(source)
                with self.assertRaises(FactoryError) as caught:
                    load_factory(f"{file}:create", file=True)
                self.assertIn(category, str(caught.exception))
                self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))
            for factory, is_file, category in [
                ("broken", False, "Use module:function"),
                ("absent_private_module:create", False, "module could not load"),
                (f"{file}:absent", True, "function unavailable"),
                (f"{file}.missing:create", True, "file unavailable"),
                ("x:create()", False, "Use module:function"),
            ]:
                # Replace stale invalid source so the missing function reaches lookup.
                file.write_text("value = 1\n")
                with self.assertRaises(FactoryError) as caught:
                    load_factory(factory, file=is_file)
                self.assertIn(category, str(caught.exception))

    def test_cli_reports_category_without_private_input(self):
        errors = io.StringIO()
        with patch.object(sys, "argv", ["grok-linux-agent", "--factory", "PRIVATE_TOKEN:create"]):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(main(), 2)
        self.assertIn("Agent stopped (factory_error).", errors.getvalue())
        self.assertIn("install it or use --factory-file", errors.getvalue())
        self.assertNotIn("PRIVATE_TOKEN", errors.getvalue())

    def test_token_prefers_new_variable_and_warns_on_legacy(self):
        new, legacy = "fixture-new-token-only", "fixture-legacy-token-only"
        with patch.dict(
            os.environ, {"GROK_GADGETS_DEVICE_TOKEN": new, "GROK_DEVICE_TOKEN": legacy}
        ):
            self.assertEqual(_token(), new)
        errors = io.StringIO()
        with patch.dict(os.environ, {"GROK_DEVICE_TOKEN": legacy}, clear=True):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(_token(), legacy)
        self.assertIn("GROK_DEVICE_TOKEN is deprecated", errors.getvalue())
        self.assertNotIn(legacy, errors.getvalue())


AGENT = str(Path(sys.executable).parent / "grok-linux-agent")
TOKEN = "fixture-cli-token-only"
ROOT = Path(__file__).resolve().parents[1]
DOCUMENTED_GADGET = (
    (ROOT / "docs" / "development.md").read_text().split("```python\n", 1)[1].split("```", 1)[0]
)


def clean_environment(**extra):
    environment = {
        k: v
        for k, v in os.environ.items()
        if k not in {"GROK_GADGETS_DEVICE_TOKEN", "GROK_DEVICE_TOKEN"}
    }
    environment.pop("PYTHONPATH", None)
    return {**environment, **extra}


async def run_agent(*args, environment, cwd=None, timeout=10):
    process = await asyncio.create_subprocess_exec(
        *args, env=environment, cwd=cwd, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, errors = await asyncio.wait_for(process.communicate(), timeout)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return process.returncode, errors.decode()


class ReadmeQuickstartTests(unittest.IsolatedAsyncioTestCase):
    async def test_readme_gadget_loads_and_executes(self):
        source = (ROOT / "README.md").read_text().split("```python\n", 1)[1].split("```", 1)[0]
        # The hello world stays about ten lines.
        self.assertLessEqual(len([line for line in source.splitlines() if line.strip()]), 8)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "my_gadget.py"
            file.write_text(source)
            device = load_device_file(str(file))
        command = {"command_id": "q1", "capability": "set.light", "arguments": {"on": True}}
        ack = await device.execute(command)
        self.assertEqual((ack["status"], ack["state"]), ("executed", {"on": True}))
        bad = await device.execute({**command, "command_id": "q2", "arguments": {"on": 1}})
        self.assertEqual(bad["error"]["code"], "invalid_arguments")
        schema = device.hello(TOKEN)["device"]["capability_schemas"]["set.light"]
        self.assertEqual(schema["description"], "Turn the desk lamp on or off")


class CliExitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.gateway = await FakeGateway(lambda message, connection: error("unauthorized")).start()

    async def asyncTearDown(self):
        await self.gateway.close()
        self.directory.cleanup()

    async def closed_port(self):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        return port

    @bounded(30)
    async def test_distinct_messages_and_exit_codes(self):
        huge = self.folder / "huge.py"
        huge.write_text(
            "from grok_gadgets_linux import Device\n"
            "async def h(arguments):\n    return {}\n"
            "def create():\n"
            '    device = Device("big-1", "big", simulated=True)\n'
            "    for n in range(6):\n"
            "        values = [f'v{i}' + 'x' * 100 for i in range(30)]\n"
            '        schema = {"type": "object", "properties": {"v": {"enum": values}}}\n'
            '        device.capability(f"c{n}", h, schema=schema)\n'
            "    return device\n"
        )
        port = str(self.gateway.port)
        closed = str(await self.closed_port())
        cases = [
            ([], {}, 2, "token_missing"),
            ([], {"GROK_GADGETS_DEVICE_TOKEN": "short"}, 2, "token_invalid"),
            (["--max-attempts", "0"], {"GROK_GADGETS_DEVICE_TOKEN": TOKEN}, 2, "invalid_option"),
            (["--port", port], {"GROK_GADGETS_DEVICE_TOKEN": TOKEN}, 3, "unauthorized"),
            (["--port", port], {"GROK_DEVICE_TOKEN": TOKEN}, 3, "unauthorized"),
            (
                ["--factory-file", f"{huge}:create"],
                {"GROK_GADGETS_DEVICE_TOKEN": TOKEN},
                4,
                "frame_too_large",
            ),
            (
                ["--port", closed, "--max-attempts", "1"],
                {"GROK_GADGETS_DEVICE_TOKEN": TOKEN},
                5,
                "reconnect_exhausted",
            ),
        ]
        for args, extra, status, code in cases:
            with self.subTest(code=code, extra=sorted(extra)):
                result, errors = await run_agent(
                    AGENT, *args, environment=clean_environment(**extra)
                )
                self.assertEqual(result, status, errors)
                self.assertIn(f"Agent stopped ({code}). ", errors)
                self.assertNotIn(TOKEN, errors)
                if "GROK_DEVICE_TOKEN" in extra:
                    self.assertIn("GROK_DEVICE_TOKEN is deprecated", errors)

    @bounded(30)
    async def test_sigterm_cancels_handler_and_runs_shutdown_hook(self):
        markers = self.folder / "markers.txt"
        gadget = self.folder / "relay.py"
        gadget.write_text(
            "import asyncio\n"
            "from grok_gadgets_linux import Device\n"
            f"MARKERS = {str(markers)!r}\n"
            "def mark(text):\n"
            "    with open(MARKERS, 'a') as file:\n"
            "        file.write(text + '\\n')\n"
            "def create():\n"
            '    device = Device("relay-1", "relay", simulated=True)\n'
            "    async def relay(arguments):\n"
            "        mark('on')\n"
            "        try:\n"
            "            await asyncio.sleep(60)\n"
            "        finally:\n"
            "            mark('off')\n"
            "        return {}\n"
            '    device.capability("relay.set", relay)\n'
            "    device.on_shutdown(lambda: mark('safe'))\n"
            "    return device\n"
        )
        gateway = await FakeGateway().start()
        gateway.commands.append({"command_id": "r1", "capability": "relay.set", "arguments": {}})
        process = await asyncio.create_subprocess_exec(
            AGENT,
            "--factory-file",
            f"{gadget}:create",
            "--port",
            str(gateway.port),
            env=clean_environment(GROK_GADGETS_DEVICE_TOKEN=TOKEN),
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await eventually(lambda: markers.exists() and "on" in markers.read_text())
            process.send_signal(signal.SIGTERM)
            _, errors = await asyncio.wait_for(process.communicate(), 10)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            await gateway.close()
        self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(markers.read_text().split(), ["on", "off", "safe"])
        self.assertIn(b"Agent stopped (signal).", errors)


def unit_settings():
    settings = {}
    for line in (ROOT / "examples" / "grok-gadget.service").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            settings.setdefault(key.strip(), []).append(value.strip())
    return settings


class ServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_unit_lifecycle_settings(self):
        settings = unit_settings()
        self.assertNotIn("After", settings)
        self.assertEqual(settings["Restart"], ["on-failure"])
        self.assertEqual(settings["RestartSec"], ["5"])
        self.assertEqual(set(settings["RestartPreventExitStatus"][0].split()), {"2", "3", "4"})
        command = shlex.split(settings["ExecStart"][0])
        self.assertIn("--factory-file", command)
        self.assertNotIn("--factory", command)
        self.assertIn("--retry-forever", command)
        self.assertIn("loginctl enable-linger", (ROOT / "docs" / "operation.md").read_text())

    @bounded(30)
    async def test_shipped_exec_start_runs_from_temporary_home(self):
        """Runs ExecStart as systemd would expand it; this is not a systemd verification."""
        settings = unit_settings()
        with tempfile.TemporaryDirectory() as home:

            def expand(value):
                return value.replace("%h", home)

            command = shlex.split(expand(settings["ExecStart"][0]))
            working = Path(expand(settings["WorkingDirectory"][0]))
            executable = Path(command[0])
            executable.parent.mkdir(parents=True)
            executable.symlink_to(AGENT)
            factory = command[command.index("--factory-file") + 1].rsplit(":", 1)[0]
            Path(factory).write_text(DOCUMENTED_GADGET)
            environment_file = Path(expand(settings["EnvironmentFile"][0]))
            environment_file.parent.mkdir(parents=True)
            environment_file.write_text(f"GROK_GADGETS_DEVICE_TOKEN={TOKEN}\n")
            environment_file.chmod(0o600)
            variables = dict(
                line.split("=", 1) for line in environment_file.read_text().splitlines()
            )
            gateway = await FakeGateway().start()
            gateway.commands.append(
                {"command_id": "s1", "capability": "display.set", "arguments": {"text": "unit"}}
            )
            environment = {"HOME": home, "PATH": "/usr/bin:/bin", **variables}
            process = await asyncio.create_subprocess_exec(
                *command,
                "--port",
                str(gateway.port),
                cwd=working,
                env=environment,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await eventually(
                    lambda: (
                        any(m["type"] == "ack" for m in gateway.received)
                        or process.returncode is not None
                    )
                )
                process.send_signal(signal.SIGTERM)
                _, errors = await asyncio.wait_for(process.communicate(), 10)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                await gateway.close()
        hello = gateway.received[0]
        ack = next(m for m in gateway.received if m["type"] == "ack")
        self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(hello["device"]["device_id"], "display-1")
        self.assertEqual((ack["status"], ack["state"]), ("executed", {"text": "unit"}))
        self.assertNotIn(TOKEN.encode(), errors)
