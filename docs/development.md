# Develop a gadget

Use Python 3.11 or later. Install the source with `uv sync --frozen`, or install a built wheel in a virtual environment.

The SDK implements your device. The gateway provides the tools for Grok. The SDK does not call a model or backend.

## Create a device

Create a trusted file with a factory function that returns a `Device`. Save this example as `my_gadget.py`:

```python
from grok_gadgets_linux import Device


def create():
    device = Device("display-1", "Software display", simulated=True, state={"text": ""})

    async def display(arguments):
        # Replace with authorized peripheral code, then read/report its current state.
        return {"text": arguments["text"]}

    device.capability("display.set", display, schema={
        "type": "object", "properties": {"text": {"type": "string", "maxLength": 100}},
        "required": ["text"], "additionalProperties": False,
    })
    device.event_capability("button")
    return device
```

## Install and start the agent

1. Create a directory outside the checkout.
2. Replace `/absolute/path` with the wheel location.
3. Create an environment and install the wheel:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install /absolute/path/grok_gadgets_linux_sdk-0.1.0a1-py3-none-any.whl
```

4. Save `my_gadget.py` in this directory.
5. Start an authenticated gateway on loopback port 8765.
6. Authorize `display-1` in the gateway credential file.
7. Set `GROK_DEVICE_TOKEN` privately.
8. Start the agent:

```sh
.venv/bin/grok-linux-agent --factory-file ./my_gadget.py:create
```

Use `--port PORT` if the gateway uses a different port.

The agent executes the selected file as trusted local code. Install its dependencies in the same environment. This file route does not provide sibling imports or relative package imports.

For a packaged gadget, install its package. Then use `--factory your_package.module:create`. Neither factory route adds a directory to `sys.path`. An editable install and `PYTHONPATH` are not necessary.

Without a factory option, the CLI starts the software lamp. Use `simulated=False` only for an implementation that controls a real peripheral. Record physical observations separately.

## Write a handler

Handlers are asynchronous. Each handler returns a complete state object.

Declare an inline Draft 2020-12 schema for arguments. The SDK does not allow schema references. Without a schema, it accepts any JSON object. In that case, validate arguments in the handler.

`rgb.set` always uses the canonical schema for strict RGB channels and the `on` value. Invalid returned state produces an error. Exceptions produce fixed error messages without raw exception text.

The SDK serializes concurrent calls. See the retry limits below before you use a handler for physical actions.

## Publish state and events

Use `device.publish_state({...})` to report background observations.

Use `device.emit("button", {"pressed": True})` to queue a press event. Queue a separate event for release. Event IDs increase within each random boot ID.

The default queue limit is 64 events. A full queue raises `event_queue_full`. The application must decide how to handle a full queue. Validated state and event values are copied to prevent later changes to those values.

Example injection controls produce simulated events. They are not physical evidence.

## Handle retries

The command cache retains 128 results per process and boot. Within that cache, the same command ID and arguments return the original acknowledgement. Changed arguments with the same ID produce a conflict.

**Known limitation:** an oversized acknowledgement can fail after the handler runs, before the result enters the cache. See [issue 8](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/8). Do not assume retry protection covers this case.

Eviction or restart removes cached results. This is not durable exactly-once delivery. Never use a new command ID to retry an uncertain physical action. The gateway also prevents replay across disconnected sessions.

## Update the protocol

The SDK checks copied protocol files against the [source manifest](../src/grok_gadgets_linux/protocol/source.json) at import. The pin is gateway commit `aeabcaf46cca830894836ac5cb85f3a6d33cd63d`.

Copy only a reviewed canonical version. Record its source and hashes. Do not edit copied schemas independently. The canonical transcript is a contract fixture, not a hardware recording.
