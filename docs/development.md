# Develop a gadget

Use Python 3.11 or later. Install the source with `uv sync --frozen`, or install a built wheel in a virtual environment.

The SDK implements your device. The gateway provides the tools intended for your existing Grok Bot. The SDK does not call a model or backend.

Develop and simulate on one host without public hosting. The agent connects to the gateway's
authenticated loopback device port. Local MCP clients use stdio. These are different interfaces.
The gateway also has authenticated HTTP MCP on loopback through `serve`. It does not
supply public HTTPS or OAuth. Do not expose the device port through a tunnel.
See the [hosting FAQ](https://github.com/adidshaft/grok-gadgets/blob/main/docs/getting-started/hosting.md)
for gateway ownership, the `HARD-GROK-REMOTE-001` gate, and future product options.

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

Follow the [README quickstart](../README.md#quickstart) to install both packages and
start the gateway. Use the `display-1` example above in place of the README lamp.
In the second terminal, enroll the matching device ID once and start the agent:

```sh
export "$(.venv/bin/grok-gadgets-gateway enroll display-1)"
.venv/bin/grok-linux-agent --factory-file ./my_gadget.py:create
```

Use `--port PORT` if the gateway uses a different port.

The agent executes the selected file as trusted local code. Install its dependencies in the same environment. This file route does not provide sibling imports or relative package imports.

For a packaged gadget, install its package. Then use `--factory your_package.module:create`. Neither factory route adds a directory to `sys.path`. An editable install and `PYTHONPATH` are not necessary.

Without a factory option, the CLI starts the software lamp. Use `simulated=False` only for an implementation that controls a real peripheral. Record physical observations separately.

## Write a handler

A handler receives the arguments and returns a complete state object. It can be an
`async def` function or a plain function.

- **Async handlers** run on the agent's event loop. Use them for non-blocking code.
- **Plain functions** run in a worker thread through the event loop's default executor
  (like `asyncio.to_thread`). Use them for blocking libraries such as RPi.GPIO, gpiozero,
  smbus2 or spidev. Polling continues while the thread works.

The handler timeout (5 seconds) bounds the wait for a result. Python cannot stop a thread,
so a timed-out plain function keeps running until it returns. The SDK does not start the
next plain-function handler until the previous thread has finished. A timed-out command
never gets a success acknowledgement.

GPIO-style example (this code is not tested on hardware):

```python
from gpiozero import LED  # Install gpiozero in the same environment.

from grok_gadgets_linux import Device


def create():
    led = LED(17)
    device = Device("led-1", "GPIO LED", state={"on": False})

    def set_led(arguments):  # Plain function: runs in a worker thread.
        if arguments["on"]:
            led.on()
        else:
            led.off()
        return {"on": led.is_lit}

    device.capability("led.set", set_led, schema={
        "type": "object", "properties": {"on": {"type": "boolean"}},
        "required": ["on"], "additionalProperties": False,
    })
    device.on_shutdown(led.off)  # Make the output safe when the agent stops.
    return device
```

Declare an inline Draft 2020-12 schema for arguments. The SDK does not allow schema references. Without a schema, it accepts any JSON object. In that case, validate arguments in the handler.

`rgb.set` always uses the canonical schema for strict RGB channels and the `on` value. Invalid or oversized returned state produces `handler_failed`. Exceptions produce fixed error messages without raw exception text.

The SDK serializes concurrent calls. See the retry limits below before you use a handler for physical actions.

## Make outputs safe on shutdown

Register cleanup with `device.on_shutdown(callback)`. The callback can be a plain or async
function. When the agent stops (SIGTERM from `systemctl stop`, Ctrl-C, a fatal error or an
exhausted reconnect budget), the agent first cancels the running handler, so its
`finally` blocks run. Then it calls the shutdown callbacks in reverse registration order.
Each callback has the handler timeout. Exceptions in callbacks are suppressed.

## Publish state and events

Use `device.publish_state({...})` to report background observations. State must fit the
largest failed acknowledgement in one 2048-byte frame. In practice, keep the compact JSON
state under about 1800 bytes; a larger state raises `frame_too_large`.

Use `device.emit("button", {"pressed": True})` to queue a press event. Queue a separate event for release. Event IDs increase within each random boot ID.

Declare each event name with `device.event_capability(name)`. A custom event name (for
example `motion`) is sent with the inline schema
`{"type": "object", "x-grok-gadgets-kind": "event"}`, so a gateway that reads this
annotation does not offer it to Grok Bot as a command. `button` is the built-in event.
`history_lost` is reserved and cannot be declared. Neither name can be a command.
Each custom event uses about 55 bytes plus twice its name length of the 2048-byte hello frame.

The default queue limit is 64 events. A full queue raises `event_queue_full`. The application must decide how to handle a full queue. Validated state and event values are copied to prevent later changes to those values.

Example injection controls produce simulated events. They are not physical evidence.
Events wait for a client to call `gadgets_read_events`; they do not start a Grok Bot task.

## Handle retries

The command cache retains 128 results per process and boot. Within that cache:

- The same command ID and arguments do not run the handler again. The reply has the
  original status (and error code) with the **current** state.
- Changed arguments with the same ID do not run the handler. The device replies with a
  failed acknowledgement, error code `duplicate_conflict`, and keeps the session. This
  happens when the gateway forgot the ID, for example after a gateway restart.

Every acknowledgement fits one frame, because state size is limited (see above).

Eviction or restart removes cached results. This is not durable exactly-once delivery. Never use a new command ID to retry an uncertain physical action. The gateway also prevents replay across disconnected sessions.

## Update the protocol

The SDK checks copied protocol files against the [source manifest](../src/grok_gadgets_linux/protocol/source.json) at import. That manifest records the current gateway commit and file hashes.

Copy only a reviewed canonical version. Record its source and hashes. Do not edit copied schemas independently. The canonical transcript is a contract fixture, not a hardware recording.
