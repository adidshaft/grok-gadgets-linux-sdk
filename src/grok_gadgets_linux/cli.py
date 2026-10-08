"""Run a developer-selected gadget factory with loopback gateway credentials."""

import argparse
import asyncio
import importlib
import importlib.util
import os
import signal
import sys
from pathlib import Path
from uuid import uuid4

from .agent import Agent
from .contracts import SDKError
from .device import Device


class FactoryError(Exception):
    """Fixed, public diagnostic categories; never include exception data."""


def _load_file(location):
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
    return module


def load_device_file(location):
    """A trusted gadget file: path.py:function, path.py with create(), or one module Device."""
    if ":" in Path(location).name:
        return load_factory(location, file=True)
    module = _load_file(location)
    if callable(getattr(module, "create", None)):
        return load_factory(location + ":create", file=True)
    devices = [value for value in vars(module).values() if isinstance(value, Device)]
    if len(devices) != 1:
        raise FactoryError(
            "Define exactly one Gadget at module level, or a create() function returning it."
        )
    return devices[0]


def load_factory(factory, *, file=False):
    try:
        location, function = factory.rsplit(":", 1)
        if not location or not function.isidentifier():
            raise ValueError
    except ValueError:
        raise FactoryError("Use module:function or --factory-file path.py:function.") from None
    if file:
        module = _load_file(location)
    else:
        try:
            module = importlib.import_module(location)
        except Exception:  # noqa: BLE001 - report a fixed category, never user code errors
            raise FactoryError(
                "Factory module could not load; install it or use --factory-file."
            ) from None
    creator = getattr(module, function, None)
    if not callable(creator):
        raise FactoryError("Factory function unavailable; expose a callable returning Device.")
    try:
        device = creator()
    except Exception:  # noqa: BLE001 - report a fixed category, never user code errors
        raise FactoryError("Factory function failed; inspect trusted code privately.") from None
    if not isinstance(device, Device):
        raise FactoryError("Factory must return a grok_gadgets_linux.Device.")
    return device


TOKEN_ENV = "GROK_GADGETS_DEVICE_TOKEN"
LEGACY_TOKEN_ENV = "GROK_DEVICE_TOKEN"

EXIT_OK, EXIT_INTERNAL, EXIT_CONFIG, EXIT_AUTH, EXIT_CONTRACT, EXIT_RECONNECT = range(6)

# Fixed public hints; codes are fixed SDK strings and never carry secrets or remote text.
_HINTS = {
    "token_missing": (
        EXIT_CONFIG,
        (
            f"Set {TOKEN_ENV} or --token-file; get one with grok-gadgets-gateway enroll <device-id>"
            " (or try: grok-linux-agent dev ./my_gadget.py, which needs no token)."
        ),
    ),
    "token_invalid": (EXIT_CONFIG, "The device token must have 16 to 256 characters."),
    "token_file_insecure": (EXIT_CONFIG, "Make the token file private: chmod 600 <file>."),
    "factory_error": (EXIT_CONFIG, "Factory could not load."),
    "invalid_option": (EXIT_CONFIG, "Check --port and --max-attempts values."),
    "simulation_only": (EXIT_CONFIG, "--simulate-button needs a simulated device."),
    "unauthorized": (
        EXIT_AUTH,
        "Gateway rejected the device ID or token; enroll the device and set its token.",
    ),
    "revoked": (
        EXIT_AUTH,
        "Gateway revoked this device; enroll a new device ID and update the factory and token.",
    ),
    "protocol_mismatch": (EXIT_CONTRACT, "Gateway uses another protocol version; update both."),
    "invalid_request": (
        EXIT_CONTRACT,
        "A message violates protocol 0.1.0; check capability names, schemas and state.",
    ),
    "invalid_response": (
        EXIT_CONTRACT,
        "Malformed gateway reply; check that a Grok Gadgets gateway owns this port.",
    ),
    "frame_too_large": (
        EXIT_CONTRACT,
        "A message is too large (hello 16 KiB, others 2048 bytes); shorten schemas, descriptions or state.",
    ),
    "duplicate_conflict": (
        EXIT_CONTRACT,
        "Gateway reported a changed acknowledgement or event; report this defect.",
    ),
    "reconnect_exhausted": (
        EXIT_RECONNECT,
        "No gateway answered; start grok-gadgets-gateway serve or use --retry-forever.",
    ),
}


def _token_file(path):
    """Read the token on every connection, so `enroll --rotate --token-file` needs no restart."""
    path = Path(path).expanduser()

    def read():
        try:
            if path.stat().st_mode & 0o077:
                raise SDKError("token_file_insecure")
            token = path.read_text().strip()
        except OSError:
            raise SDKError("token_missing") from None
        if not 16 <= len(token) <= 256:
            raise SDKError("token_invalid")
        return token

    read()
    return read


def _token():
    token = os.environ.get(TOKEN_ENV)
    if token is None and LEGACY_TOKEN_ENV in os.environ:
        print(f"{LEGACY_TOKEN_ENV} is deprecated; use {TOKEN_ENV}.", file=sys.stderr)
        token = os.environ[LEGACY_TOKEN_ENV]
    if not token:
        raise SDKError("token_missing")
    if not 16 <= len(token) <= 256:
        raise SDKError("token_invalid")
    return token


def _stopped(code, hint=None):
    status, default = _HINTS.get(code, (EXIT_INTERNAL, "Inspect redacted diagnostics privately."))
    print(f"Agent stopped ({code}). {hint or default}", file=sys.stderr)
    return status


async def _serve(agent):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        try:
            loop.add_signal_handler(number, stop.set)
            installed.append(number)
        except (NotImplementedError, RuntimeError, TypeError, ValueError):
            pass  # Unsupported platform: SIGINT still raises KeyboardInterrupt.
    try:
        await agent.run(stop)
    finally:
        for number in installed:
            loop.remove_signal_handler(number)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["dev"]:
        from .dev import main as dev_main

        return dev_main(argv[1:])
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            f"Token: {TOKEN_ENV} ({LEGACY_TOKEN_ENV} is a deprecated fallback). Exit codes: "
            "0 stopped by signal, 1 internal, 2 configuration, 3 unauthorized or revoked, "
            "4 protocol contract, 5 reconnect attempts exhausted. "
            "For local development with no tokens: grok-linux-agent dev ./my_gadget.py"
        ),
    )
    factories = parser.add_mutually_exclusive_group()
    factories.add_argument(
        "--factory",
        default=None,
        help="Installed trusted module:function returning a Device (default: software lamp)",
    )
    factories.add_argument(
        "--factory-file",
        help="Explicit trusted local path.py (one Gadget or create()) or path.py:function; "
        "executes local code",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--token-file",
        help="private (mode 0600) file holding the device token, re-read on each connection; "
        "write it with grok-gadgets-gateway enroll <id> --token-file <file>",
    )
    parser.add_argument(
        "--simulate-button",
        action="store_true",
        help="Explicitly inject press/release into the simulated example",
    )
    retries = parser.add_mutually_exclusive_group()
    retries.add_argument(
        "--max-attempts",
        type=int,
        default=8,
        help="Consecutive failed connection attempts before exit code 5 (1..32, default 8)",
    )
    retries.add_argument(
        "--retry-forever",
        action="store_true",
        help="Service mode: never give up reconnecting; backoff ceiling 30 seconds",
    )
    args = parser.parse_args(argv)
    try:
        if args.factory_file:
            device = load_device_file(args.factory_file)
        else:
            device = load_factory(args.factory or "grok_gadgets_linux.examples:software_lamp")
        if args.simulate_button:
            if not device.simulated:
                raise SDKError("simulation_only")
            device.emit("button", {"pressed": True})
            device.emit("button", {"pressed": False})
        token = _token_file(args.token_file) if args.token_file else _token()
        try:
            agent = Agent(
                device,
                token,
                port=args.port,
                reconnect_attempts=None if args.retry_forever else args.max_attempts,
                backoff_cap=30.0 if args.retry_forever else 5.0,
            )
        except ValueError:
            raise SDKError("invalid_option") from None
        print(
            "Agent starting; software simulation"
            if device.simulated
            else "Agent starting; physical effects require observation",
            file=sys.stderr,
            flush=True,
        )
        asyncio.run(_serve(agent))
    except FactoryError as error:
        return _stopped("factory_error", str(error))
    except SDKError as error:
        return _stopped(error.code)
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception:  # noqa: BLE001 - report a fixed category, never user code errors
        return _stopped("internal_error")
    print("Agent stopped (signal). Handlers were cancelled; shutdown hooks ran.", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
