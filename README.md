# Grok Gadgets Linux SDK

An independently installable Python library and loopback device agent for Linux gadget applications targeting Grok through the Grok Gadgets gateway. Original code Apache-2.0; independent of xAI. No alternative model backend.

Status: local alpha. Python library, installed CLI example and gateway TCP integration passed on macOS and Linux aarch64 in Docker. Physical peripherals and Linux service lifecycle pending. Examples use explicit software simulation. Gateway protocol artifacts are pinned and hash-checked, not rewritten here.

```sh
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run grok-linux-agent --help
```

See [API/example](docs/development.md), [operation](docs/operation.md), [verification](docs/verification.md), and [issues](planning/issues.json). The gateway is a separately installed service; this SDK declares capabilities and reports device execution/state/events.
