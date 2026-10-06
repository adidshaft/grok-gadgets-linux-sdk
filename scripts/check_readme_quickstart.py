"""Run the README quick start in fresh clones and call the gadget over MCP.

    python3 scripts/check_readme_quickstart.py [GATEWAY_CHECKOUT]

Clones this checkout's HEAD and the gateway (default ../grok-gadgets-gateway) side by side
in a temporary folder, as the README does; commit your change first. The README `git clone`
and `cd` lines are skipped because those clones exist. Blocks that start a long-running
process (serve, the agent) run in the background. A temporary config directory keeps your
own tokens untouched. Software only: no Grok Bot, hardware or systemd.
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LONG_RUNNING = ("grok-gadgets-gateway serve", "grok-linux-agent")
CLIENT = r"""
import asyncio, json, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main(url, token):
    headers = {"Authorization": "Bearer " + token}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, **arguments):
                result = await session.call_tool(name, arguments)
                return json.loads(result.content[0].text)

            for _ in range(100):
                devices = (await call("gadgets_list_devices"))["devices"]
                if any(d["device_id"] == "my-pi" and d["available"] for d in devices):
                    break
                await asyncio.sleep(0.1)
            command = (await call(
                "gadgets_command", device_id="my-pi", capability="lamp.set",
                arguments={"on": True},
            ))["command"]
            for _ in range(100):
                if command["status"] not in ("accepted", "dispatched"):
                    break
                await asyncio.sleep(0.05)
                command = (await call(
                    "gadgets_command_status", command_id=command["command_id"]
                ))["command"]
            state = (await call("gadgets_get_state", device_id="my-pi"))["device"]
            print(json.dumps({
                "devices": [d["device_id"] for d in devices],
                "status": command["status"],
                "state": state["state"],
                "simulated": state["simulated"],
            }))

asyncio.run(main(sys.argv[1], sys.argv[2]))
"""


def blocks():
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Quickstart", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```(sh|python)\n(.*?)```", section, re.S)


def wait_for_port(port, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"Nothing listened on 127.0.0.1:{port}")


def check(condition, message):
    if not condition:
        raise SystemExit("README quick start failed: " + message)
    print("ok  " + message, flush=True)


def main():
    gateway = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "grok-gadgets-gateway")
    background = []
    with tempfile.TemporaryDirectory(prefix="grok-linux-readme-") as folder:
        workspace = Path(folder)
        sdk = workspace / "grok-gadgets-linux-sdk"
        for source, target in [(ROOT, sdk), (gateway, workspace / "grok-gadgets-gateway")]:
            subprocess.run(["git", "clone", "-q", str(source), str(target)], check=True)
        env = {**os.environ, "XDG_CONFIG_HOME": str(workspace / "config")}
        env.pop("GROK_GADGETS_DEVICE_TOKEN", None)
        try:
            for kind, body in blocks():
                if kind == "python":
                    (sdk / "my_gadget.py").write_text(body)
                    continue
                lines = [
                    line
                    for line in body.splitlines()
                    if line.strip() and not line.startswith(("git clone", "cd "))
                ]
                script = "set -euo pipefail\n" + "\n".join(lines) + "\n"
                if any(marker in body for marker in LONG_RUNNING):
                    process = subprocess.Popen(
                        ["bash", "-c", script], cwd=sdk, env=env, start_new_session=True
                    )
                    background.append(process)
                    if "serve" in body:
                        wait_for_port(8766)
                        wait_for_port(8765)
                else:
                    subprocess.run(["bash", "-c", script], cwd=sdk, env=env, check=True)
            check(len(background) == 2, "README started the gateway and the agent")
            token = (workspace / "config/grok-gadgets/mcp-token").read_text().strip()
            result = subprocess.run(
                [str(sdk / ".venv/bin/python"), "-c", CLIENT, "http://127.0.0.1:8766/mcp", token],
                cwd=sdk,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode:
                raise SystemExit(result.stdout + result.stderr)
            outcome = json.loads(result.stdout.strip().splitlines()[-1])
            check("my-pi" in outcome["devices"], "the MCP client lists my-pi")
            check(outcome["status"] == "executed", "lamp.set reaches executed")
            check(outcome["state"] == {"on": True}, "reported state is {'on': True}")
            check(outcome["simulated"] is True, "the device is labelled simulated")
        finally:
            for process in reversed(background):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(20)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
    print("README quick start passed (software only; no Grok Bot, hardware or systemd).")


if __name__ == "__main__":
    sys.exit(main())
