# Develop a gadget

Python 3.11+; install this repository with `uv sync --frozen`, or its built wheel with pip into your own venv. This SDK has no model/backend dependency. The gateway hosts Grok tools; the SDK implements your device.

A trusted module exposes a factory returning `Device`. For example `my_gadget.py`:

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

With an authenticated local gateway already running and the corresponding device authorized in its credential file, set `GROK_DEVICE_TOKEN` privately and run `uv run grok-linux-agent --factory my_gadget:create`. Module imports execute local code; use trusted code only. Set `simulated=False` only for a real peripheral implementation and still record visible physical effects separately.

Handlers are async and return a complete state object. SDK validates arguments against a declared inline Draft 2020-12 schema; `rgb.set` always uses canonical strict RGB channels/on schema. References are prohibited. Missing custom schema allows arbitrary JSON-object arguments, so provide one or explicitly validate in the handler. Returning invalid state reports failure. Exceptions become fixed errors with no raw exception text. Concurrent calls serialize, preventing duplicate handlers in the retained window.

Use `device.publish_state({...})` for background observations. `device.emit("button", {"pressed": True})` queues an event; release is a second event. Event IDs are monotonic within the random boot ID. Queue cap defaults to 64 and raises `event_queue_full` instead of silently losing history; applications decide backpressure. Snapshot/queued values are copied to prevent mutations after validation. Do not invoke the example's injection controls as physical evidence.

Command dedup retains 128 results per process/boot. Same ID/arguments returns original acknowledgement; changed parameters conflict. Results can be evicted or lost on restart: not durable exactly-once delivery. Never create a new command ID to retry an uncertain physical action. Gateway separately prevents replay across disconnected sessions.

Copied protocol files are validated at import against [source manifest](../src/grok_gadgets_linux/protocol/source.json), pinned to gateway commit `17d31686ad06d608f20b117e6f4070bacbff7a35`. Update them only by copying a reviewed canonical version and recording new hashes/source; do not hand-edit the SDK's schema copies. Canonical transcript is a contract fixture, not a hardware capture.
