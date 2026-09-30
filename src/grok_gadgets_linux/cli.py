"""Run a developer-selected gadget factory with loopback gateway credentials."""

import argparse
import asyncio
import importlib
import os
import sys

from .agent import Agent
from .contracts import SDKError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--factory",
        default="grok_gadgets_linux.examples:software_lamp",
        help="Trusted local module:function returning a Device",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--simulate-button",
        action="store_true",
        help="Explicitly inject press/release into the simulated example",
    )
    args = parser.parse_args()
    try:
        module, function = args.factory.split(":", 1)
        device = getattr(importlib.import_module(module), function)()
        if args.simulate_button:
            if not device.simulated:
                raise SDKError("simulation_only")
            device.emit("button", {"pressed": True})
            device.emit("button", {"pressed": False})
        agent = Agent(device, os.environ.get("GROK_DEVICE_TOKEN", ""), port=args.port)
        print(
            "Agent starting; software simulation"
            if device.simulated
            else "Agent starting; physical effects require observation",
            file=sys.stderr,
        )
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(
            "Agent stopped. Check credentials, factory, endpoint and redacted diagnostics privately.",
            file=sys.stderr,
        )
        return 1
    return 0
