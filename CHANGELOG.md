# Changelog

## Unreleased

## 0.1.0a1 — 6 October 2026

- Pin the gateway dependency to its `v0.1.0-alpha.1` release tag.
- `grok-linux-agent dev ./my_gadget.py` runs your gadget with an in-process gateway and loopback auto-trust: no tokens to copy. It prints pasteable MCP settings (stdio needs no token at all). Needs the new `[gateway]` extra (`uv sync --extra gateway`; the gateway comes from its GitHub repository until it is on PyPI).
- `--token-file <path>` reads a private device token and re-reads it on every connection, so `grok-gadgets-gateway enroll <id> --rotate --token-file <path>` needs no agent restart. `--factory-file` accepts a plain gadget file.
- README: the quick start is one install, one ten-line file and one command.
- New decorator API: `Gadget(...)` with `@gadget.command("What it does")`. The JSON schema comes from type hints (`bool`, `int`, `float`, `str`, `Literal`, `list`, optional, `Annotated` with `Range`). `Device.capability` keeps working and gains `description=`; `event_capability` too.
- Capability descriptions reach the assistant (gateway `capability_descriptions`). A TCP hello may be up to 16 KiB; other frames stay 2048 bytes. Protocol README re-pinned from gateway `3e41aec`.
- Re-pin the protocol 0.1.0 README from gateway `c568c3e` (sections and `late_ack`; wire format unchanged). With `GROK_GATEWAY_SOURCE`, a test checks the copied protocol files match that gateway.
- A handler that overruns `handler_timeout` now gets a `failed` ACK (`handler_timeout`) and the session stays open; a replay of that command ID reports the same failure.
- `late_ack` and `unknown_command` replies to an ACK are non-fatal: the agent drops that ACK and keeps polling instead of reconnecting.
- CI runs the seven gateway integration tests against gateway `main` and fails if they skip. A new job runs the README quick start in fresh clones and calls the gadget over MCP. Both run on push, pull request and nightly.

## 0.1.0a1 — unpublished

Generic capability SDK and loopback agent with strict pinned contracts, bounded retries,
safe errors, and explicit trusted-file factories (including annotated dataclasses).
Installed software acceptance is recorded on macOS arm64 and Linux aarch64 in a pinned
container. Physical peripherals, real systemd behavior, native Grok/mobile evidence,
and independent human reproduction remain pending.

### Review fixes, 2026-10-05 — unpublished

- A reused command ID with changed arguments returns a failed `duplicate_conflict`
  acknowledgement and keeps the session; replays report current state.
- State is limited so every acknowledgement fits one 2048-byte frame (closes the
  AUDIT-LIN-001 edge); deeply nested replies are `invalid_response`.
- Custom event names carry `x-grok-gadgets-kind: event`; `history_lost` is reserved.
- Plain-function handlers run in a worker thread; new `Device.on_shutdown(callback)`.
- SIGTERM/SIGINT cancel the running handler and run shutdown hooks; one transient
  `unauthorized` after a successful hello is retried; jittered backoff;
  `--max-attempts` and `--retry-forever`; distinct exit codes 2/3/4/5.
- `GROK_GADGETS_DEVICE_TOKEN` replaces `GROK_DEVICE_TOKEN` (deprecated fallback).
- Usable systemd user-unit template; CI matrix for Python 3.11–3.14.
- Plain-language README; corrected evidence labels and security limits.

### Launch preparation, 2026-10-05 — unpublished

- Add a standalone fresh-wheel custom-device journey, architecture diagram, and runtime/evidence table.
- Expand contribution/support/conduct/security guidance and prepare `adidshaft` ownership.
- Preserve SDK runtime, canonical protocol pins, Apache-2.0 license, and notices.
