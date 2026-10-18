# Changelog

## Unreleased

- Long-poll, opt-in ([gateway #182](https://github.com/adidshaft/grok-gadgets-gateway/issues/182), hub ADR 014). `grok-linux-agent --wait-ms N` or `Agent(wait_ms=N)` (100..10000) adds `wait_ms` to each poll; the relay answers when a command is ready or the wait ends, and the agent polls again at once. An older relay refuses the field once: the agent keeps its session and polls without it until restart. Protocol re-pinned at gateway `70fbd43`.

## 0.1.0-alpha.9 — 18 October 2026

- On 17 October 2026 two Linux gadgets from a batch (`enroll --count 2`) connected to a fresh relay over TLS with `--gateway`, `--ca`, `--device-id` and their token files, and showed Online in the relay's `builder report` ([hub record](https://github.com/adidshaft/grok-gadgets/blob/dev/docs/verification/builder-kit-2026-10-17.md)). Simulated devices; a Linux gadget has no claim code, so the operator assigns it to an account.
- The `gateway` extra pins `grok-gadgets-gateway==0.1.0a17` from PyPI. The protocol is unchanged.

- Connect to a relay ([#76](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/76), hub ADR 013). `grok-linux-agent --gateway NAME[:PORT] --ca FILE` connects over TLS with the relay's CA as the only trust anchor and the name checked; port 8444 by default; polls every 500 ms. A certificate from another CA or for another name stops the agent with `tls_rejected` (exit 2). `Agent(host=..., ca=..., server_name=...)` in code. Loopback stays the default and unchanged.
- `grok-linux-agent --device-id ID` sets the enrolled ID, so one factory serves a whole batch made with `enroll --count` ([#76](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/76), clean-room run). The agent shows its device ID when it starts.
- Background producers and a climate sensor example ([#13](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/13)). `device.background(async def produce(stop))` starts once per agent run, survives reconnects and stops before the shutdown callbacks. `grok_gadgets_linux.examples:climate_sensor` publishes `climate` every 2 s, emits `threshold.crossed`, takes `threshold.set`, and counts events dropped by a full queue.

## 0.1.0-alpha.8 — 17 October 2026

- Protocol 0.1.0 is re-pinned from gateway 0.1.0-alpha.16, with its optional signed-update frames and `fixtures/update-transcript.json` ([#89](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/89)). The Linux agent does not take updates and sends no update fields; its wire behaviour is unchanged.
- The `gateway` extra pins `grok-gadgets-gateway==0.1.0a16` from PyPI ([#87](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/87)).

## 0.1.0-alpha.7 — 17 October 2026

- Protocol files re-pinned to gateway `dev` with the optional claim fields of hub ADR 011 ([#82](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/82)). The agent does not send `claim`, so its frames and replies are unchanged.

## 0.1.0-alpha.6 — 13 October 2026

- The `gateway` extra and lockfile pin gateway v0.1.0-alpha.10, which is on PyPI, so `pip install "grok-gadgets-linux-sdk[gateway]"` resolves from PyPI ([#70](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/70)).
- The release workflow publishes an already-released tag after checking its files match (#67).
- README: install from PyPI with `pip install --pre`.

## 0.1.0-alpha.5 — 12 October 2026

- `grok-linux-agent --version` prints the SDK version and exits without connecting ([#16](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/16)).
- The `gateway` extra and lockfile pin gateway v0.1.0-alpha.7, so the extra names a version that the gateway's own release workflow can publish to PyPI.
- A hand-started **release packages** workflow builds a tag, writes `SHA256SUMS` with plain file names, checks it in a fresh folder and attaches the files to the release. PyPI upload is a separate opt-in through trusted publishing; no token is stored ([#61](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues/61), hub [#151](https://github.com/adidshaft/grok-gadgets/issues/151)). The package is not on PyPI yet.
- README adds pip install from the release wheel. Homepage is https://grokgadgets.org/. Docs match the 12 October evidence.

## 0.1.0-alpha.4 — 8 October 2026

- Pin the gateway extra and lockfile to gateway v0.1.0-alpha.4, which uses `mcp` 2.3.0. The README quick-start check uses the `mcp` 2.x HTTP client.
- Development tools: `ruff` 0.16.10 and `hatchling` 1.32.4. Code follows the new `ruff` default rules without behavior changes. CI checks packages with `twine` 7.0.0, which reads the Metadata-Version 2.5 that `hatchling` 1.32 writes.

## 0.1.0-alpha.3 — 8 October 2026

- Security: pin the gateway extra and lockfile to gateway v0.1.0-alpha.3. This moves `mcp` from 1.26.0 to 1.28.1 and closes its high-severity Dependabot alerts.
- Dependabot opens weekly grouped update PRs into `dev`.
- CONTRIBUTING starts fork branches from `upstream/dev`. CI also runs the plain-language check on CONTRIBUTING and SUPPORT.

## 0.1.0-alpha.2 — 7 October 2026

- Pin the gateway extra and lockfile to gateway v0.1.0-alpha.2.
- Add a runnable Grok Bot rehearsal step to the README quick start.

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
