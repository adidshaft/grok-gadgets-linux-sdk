"""Run a developer-selected gadget factory with loopback gateway credentials."""

import argparse
import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from uuid import uuid4

from .device import Device

from .agent import Agent
from .contracts import SDKError


class FactoryError(Exception):
    """Fixed, public diagnostic categories; never include exception data."""


def load_factory(factory, *, file=False):
    try:
        location, function = factory.rsplit(":", 1)
        if not location or not function.isidentifier():
            raise ValueError
    except ValueError:
        raise FactoryError("Use module:function or --factory-file path.py:function.") from None
    if file:
        path = Path(location).expanduser()
        if path.suffix != ".py" or not path.is_file():
            raise FactoryError("Factory file unavailable; select an existing trusted .py file.")
        # Each explicit execution owns a distinct module; preserve existing class metadata
        # when the same file (or another file with the same basename) is loaded again.
        module_name = f"_grok_trusted_factory_{uuid4().hex}"
        while module_name in sys.modules:
            module_name = f"_grok_trusted_factory_{uuid4().hex}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path.resolve())
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except BaseException as error:
            sys.modules.pop(module_name, None)
            if not isinstance(error, Exception):
                raise
            raise FactoryError(
                "Factory file could not load; check syntax and installed dependencies."
            ) from None
    else:
        try:
            module = importlib.import_module(location)
        except Exception:
            raise FactoryError(
                "Factory module could not load; install it or use --factory-file."
            ) from None
    creator = getattr(module, function, None)
    if not callable(creator):
        raise FactoryError("Factory function unavailable; expose a callable returning Device.")
    try:
        device = creator()
    except Exception:
        raise FactoryError("Factory function failed; inspect trusted code privately.") from None
    if not isinstance(device, Device):
        raise FactoryError("Factory must return a grok_gadgets_linux.Device.")
    return device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    factories = parser.add_mutually_exclusive_group()
    factories.add_argument(
        "--factory",
        default=None,
        help="Installed trusted module:function returning a Device (default: software lamp)",
    )
    factories.add_argument(
        "--factory-file", help="Explicit trusted local path.py:function; executes local code"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--simulate-button",
        action="store_true",
        help="Explicitly inject press/release into the simulated example",
    )
    args = parser.parse_args()
    try:
        device = load_factory(
            args.factory_file or args.factory or "grok_gadgets_linux.examples:software_lamp",
            file=args.factory_file is not None,
        )
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
    except FactoryError as error:
        print(f"Agent stopped. {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(
            "Agent stopped. Check credentials, factory, endpoint and redacted diagnostics privately.",
            file=sys.stderr,
        )
        return 1
    return 0
