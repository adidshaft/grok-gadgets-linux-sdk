"""`grok-linux-agent dev`: your gadget plus an in-process gateway, with no tokens to copy.

Needs the gateway package: pip install "grok-gadgets-linux-sdk[gateway]"
(from a checkout: uv sync --extra gateway). Loopback only; software evidence only.
"""

import argparse
import asyncio
import json
import os
import secrets
import signal
import sys
import tempfile
from pathlib import Path

from .agent import Agent
from .cli import FactoryError, load_device_file
from .contracts import SDKError

GATEWAY_HINT = (
    "The dev command needs the gateway package. Install it with: "
    'pip install "grok-gadgets-linux-sdk[gateway]"  (from a checkout: uv sync --extra gateway)'
)


def _gateway():
    try:
        from grok_gadgets_gateway import operator, service
        from grok_gadgets_gateway.domain import Gateway
        from grok_gadgets_gateway.mcp_server import make_server
        from grok_gadgets_gateway.transport import Credentials, DeviceServer
    except ImportError:
        raise SystemExit(GATEWAY_HINT) from None
    return operator, service, Gateway, make_server, Credentials, DeviceServer


def _agent_command(path):
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if os.path.basename(script) == "grok-linux-agent" and os.path.isfile(script):
        command, prefix = script, []
    else:  # Never resolve symlinks: a virtualenv python must stay inside its virtualenv.
        command, prefix = os.path.abspath(sys.executable), ["-m", "grok_gadgets_linux.cli"]
    return {"command": command, "args": [*prefix, "dev", "--stdio", str(path)]}


def _settings(path, url, token_file):
    stdio = {"mcpServers": {"grok-gadgets": _agent_command(path)}}
    http = {
        "mcpServers": {
            "grok-gadgets": {
                "url": url,
                "headers": {"Authorization": f"Bearer <contents of {token_file}>"},
            }
        }
    }
    return (
        "# Your MCP client starts this gadget itself (no token at all):\n"
        + json.dumps(stdio, indent=2)
        + "\n# Or connect to this running process over HTTP:\n"
        + json.dumps(http, indent=2)
    )


def _trust(device_id, folder):
    """A throwaway credential that exists only for this process: loopback auto-trust."""
    token = secrets.token_urlsafe(32)
    path = Path(folder) / "credentials.json"
    path.write_text(json.dumps({"devices": {device_id: {"token": token}}}))
    path.chmod(0o600)
    return path, token


def _stop_event():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(number, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    return stop


async def _http(device, path, port, gateway_parts):
    operator, service, *_ = gateway_parts
    operator.init_config()
    token_file = operator.mcp_token_path()
    stop = _stop_event()
    with tempfile.TemporaryDirectory(prefix="grok-linux-dev-") as folder:
        credentials, token = _trust(device.device_id, folder)
        async with service.serve_gateway(
            str(credentials), str(token_file), device_port=0, port=port
        ) as running:
            agent = Agent(device, token, port=running.device_port, poll_interval=0.05)
            task = asyncio.create_task(agent.run(stop))
            await asyncio.wait_for(agent.connected.wait(), 10)
            print(
                f"Gadget {device.device_id} is connected to a local gateway at {running.url}\n"
                + _settings(path, running.url, token_file)
                + "\nTry it without a model: "
                "https://github.com/adidshaft/grok-gadgets-gateway/blob/main/docs/first-success.md"
                "\nPress Ctrl+C to stop.",
                file=sys.stderr,
                flush=True,
            )
            waiter = asyncio.create_task(stop.wait())
            await asyncio.wait({task, waiter, running.task}, return_when=asyncio.FIRST_COMPLETED)
            stop.set()
            waiter.cancel()
            await task


async def _stdio(device, gateway_parts):
    _, _, Gateway, make_server, Credentials, DeviceServer = gateway_parts
    stop = _stop_event()
    with tempfile.TemporaryDirectory(prefix="grok-linux-dev-") as folder:
        credentials, token = _trust(device.device_id, folder)
        gateway = Gateway()
        server = await DeviceServer(gateway, Credentials(str(credentials)), port=0).start()
        try:
            agent = Agent(device, token, port=server.port, poll_interval=0.05)
            task = asyncio.create_task(agent.run(stop))
            await asyncio.wait_for(agent.connected.wait(), 10)
            mcp = make_server(gateway)
            mcp_task = asyncio.create_task(mcp.run_stdio_async())
            waiter = asyncio.create_task(stop.wait())
            await asyncio.wait({mcp_task, waiter, task}, return_when=asyncio.FIRST_COMPLETED)
            stop.set()
            waiter.cancel()
            mcp_task.cancel()
            await task
        finally:
            await server.close()


def main(argv):
    parser = argparse.ArgumentParser(
        prog="grok-linux-agent dev",
        description="Run your gadget with an in-process local gateway. No tokens to copy.",
    )
    parser.add_argument("gadget", help="your trusted gadget file, for example ./my_gadget.py")
    parser.add_argument(
        "--stdio", action="store_true", help="serve MCP on stdin/stdout for a client that starts it"
    )
    parser.add_argument("--port", type=int, default=8766, help="loopback MCP HTTP port")
    args = parser.parse_args(argv)
    gateway_parts = _gateway()
    try:
        path = Path(args.gadget).expanduser().resolve()
        device = load_device_file(str(path))
    except FactoryError as error:
        print(f"Agent stopped (factory_error). {error}", file=sys.stderr)
        return 2
    try:
        if args.stdio:
            asyncio.run(_stdio(device, gateway_parts))
        else:
            asyncio.run(_http(device, path, args.port, gateway_parts))
    except SDKError as error:
        print(f"Agent stopped ({error.code}).", file=sys.stderr)
        return 4
    except OSError as error:
        print(
            f"Could not start: {error.strerror or error}. Is port {args.port} in use?",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        pass
    print("Stopped. The gadget and its local gateway are closed.", file=sys.stderr)
    return 0
