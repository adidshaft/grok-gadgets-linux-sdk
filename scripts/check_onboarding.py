"""Run with fresh wheel-installed Python; no source imports or editable installations.

Usage: /fresh/venv/bin/python -I scripts/check_onboarding.py docs/development.md [--dataclass]
Both SDK and gateway wheels must be installed in that environment.
"""

import asyncio
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

import grok_gadgets_linux
from grok_gadgets_gateway.domain import Gateway
from grok_gadgets_gateway.transport import Credentials, DeviceServer


async def eventually(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.01)


async def check(document, *, dataclass=False):
    assert "site-packages" in grok_gadgets_linux.__file__
    example = document.read_text().split("```python\n", 1)[1].split("```", 1)[0]
    if dataclass:
        example = (
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class Settings:\n"
            '    label: str = "Software display"\n\n'
            + example.replace('"Software display"', "Settings().label")
        )
    with tempfile.TemporaryDirectory(prefix="grok-custom-") as directory:
        cwd = Path(directory)
        (cwd / "my_gadget.py").write_text(example)
        credentials = cwd / "credentials.json"
        token = "fixture-custom-onboarding-only"
        credentials.write_text(json.dumps({"devices": {"display-1": {"token": token}}}))
        credentials.chmod(0o600)
        gateway = Gateway()
        server = await DeviceServer(gateway, Credentials(credentials), port=0).start()
        environment = dict(os.environ, GROK_DEVICE_TOKEN=token)
        environment.pop("PYTHONPATH", None)
        executable = Path(sys.executable).parent / "grok-linux-agent"
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "--factory-file",
            "./my_gadget.py:create",
            "--port",
            str(server.port),
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await eventually(lambda: "display-1" in gateway.devices)
            gateway.command(
                "display-1", "display.set", {"text": "installed custom works"}, "custom-c1"
            )
            await eventually(lambda: gateway.command_status("custom-c1")["status"] == "executed")
            state = gateway.state("display-1")
            assert state["state"] == {"text": "installed custom works"}
            assert state["simulated"]
            assert not gateway.command_status("custom-c1")["physical_verified"]
            print(
                json.dumps(
                    {
                        "platform": platform.platform(),
                        "machine": platform.machine(),
                        "python": platform.python_version(),
                        "installed_package": grok_gadgets_linux.__file__,
                        "sdk_version": importlib.metadata.version("grok-gadgets-linux-sdk"),
                        "factory_variant": "annotated dataclass" if dataclass else "documented",
                        "custom_capability": "display.set",
                        "ack": "executed",
                        "state": state["state"],
                        "simulated": True,
                        "physical_verified": False,
                        "PYTHONPATH": "removed",
                        "cwd": "fresh temporary directory",
                    },
                    indent=2,
                ),
                flush=True,
            )
        finally:
            if process.returncode is None:
                process.terminate()
            _, errors = await asyncio.wait_for(process.communicate(), 2)
            await server.close()
            assert token.encode() not in errors
        help_process = await asyncio.create_subprocess_exec(
            str(executable),
            "--help",
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
        )
        help_text, _ = await help_process.communicate()
        assert help_process.returncode == 0 and b"--factory-file" in help_text


asyncio.run(check(Path(sys.argv[1]).resolve(), dataclass="--dataclass" in sys.argv[2:]))
