# Run and recover

The agent connects only to loopback TCP: `127.0.0.1` or `::1`. The default port is 8765. Run the agent and gateway on the same host.

Local simulation needs no public hosting. You operate the gateway and agent on this host.
Grok/xAI hosts Grok Bot; it does not host these processes for you.

The gateway has local stdio MCP and authenticated HTTP MCP through
`grok-gadgets-gateway serve`. `serve` keeps running on its own. Both modes
can run the loopback device listener. Never tunnel the device port.
A tunnel adds reachability. It does not add authentication.
`HARD-GROK-REMOTE-001` tracks the remote route.
See the [hosting FAQ](https://github.com/adidshaft/grok-gadgets/blob/main/docs/getting-started/hosting.md)
for the future cloud route and product hosting choices.

## Start the agent

For development, `grok-linux-agent dev ./my_gadget.py` is all you need: it starts a gateway in
the same process, trusts your gadget on loopback and prints connector settings. Add `--stdio`
when the connector should start it; that path needs no token at all.

To run beside a long-running gateway service instead:

1. Install the gateway and run `grok-gadgets-gateway init` once.
2. Issue a device token into a private file:
   `grok-gadgets-gateway enroll desk-lamp --token-file desk-lamp.token`.
   The device ID must match your `Gadget(...)`.
3. Start the gateway: `grok-gadgets-gateway serve`.
4. Run `grok-linux-agent --factory-file ./my_gadget.py --token-file desk-lamp.token`.
   `GROK_GADGETS_DEVICE_TOKEN` also works; `GROK_DEVICE_TOKEN` is deprecated.
5. Check it: `grok-gadgets-gateway rehearse --device desk-lamp --command <name> --args '<json>'`.

The default agent is a software lamp. Add `--simulate-button` to queue simulated press and release events. Use `--factory-file ./my_gadget.py` (one module-level `Gadget`, or `path.py:function`) or `--factory module:function` for a trusted application. Use `--port` for a different loopback port.

### Connector settings

Grok Bot's custom MCP connector uses Streamable HTTP with an `Authorization` header. For the
running `serve` process in the quickstart, the settings are:

```json
{
  "mcpServers": {
    "grok-gadgets": {
      "url": "http://127.0.0.1:8766/mcp",
      "headers": {"Authorization": "Bearer <mcp-token>"}
    }
  }
}
```

Replace `<mcp-token>` privately with the single line from
`~/.config/grok-gadgets/mcp-token`. If you set `XDG_CONFIG_HOME`, use that directory
instead of `~/.config`. This is the MCP token, not the device token. Keep the settings
private. Grok Bot cannot open this loopback URL yet; check it locally with `grok-gadgets-gateway rehearse`.

Alternatively, stop `serve` and let the connector start the gateway over stdio.
Do not start both modes on the same device port. Use absolute paths. The listener on
`--device-port` runs while the connector keeps the gateway running:

```json
{
  "mcpServers": {
    "grok-gadgets": {
      "command": "/home/pi/grok-gadget/.venv/bin/grok-gadgets-gateway",
      "args": [
        "--credentials", "/home/pi/.config/grok-gadgets/credentials.json",
        "--device-port", "8765"
      ]
    }
  }
}
```

The credential file must have mode `600`. A cloud Grok Bot cannot start this command on
your computer. This snippet is not verified with Grok Bot.

SDK integration tests start `DeviceServer` directly on temporary loopback ports. They do not use a paid API call or a live Grok account.

Keep both services running while you need the device. Keep ordinary peripheral controls
independent of Grok Bot. When the agent stops, the gateway marks it offline. Closing an
HTTP client leaves `serve` running. A stdio gateway ends when its client closes stdin.

A command can be accepted without a confirmed result. A reported result does not prove a physical effect. Record each evidence level separately.

## Connection limits

| Setting | Default |
| --- | --- |
| Poll interval | 100 ms |
| Socket timeout | 2 seconds |
| Handler timeout | 5 seconds |
| Failed connection or session attempts | 8 (`--max-attempts N`, 1–32); unlimited with `--retry-forever` |
| Reconnect delay | Ceiling starts at 250 ms and doubles to 5 seconds (30 seconds with `--retry-forever`); each delay is random between half the ceiling and the ceiling |
| Healthy session needed to reset the failure budget | 10 seconds |

Revocation and contract errors stop the agent immediately. `unauthorized` before the
first successful hello stops it immediately. After a successful hello in the same run,
one `unauthorized` is retried with backoff, because a gateway can report a transient
credential-file read failure that way; a second consecutive `unauthorized` stops the
agent. `unavailable`, `busy` and connection failures are retried. Each request rechecks
gateway revocation. Shutdown interrupts a reconnect delay.

A lost event acknowledgement retains the event ID for reconnect. The gateway does not replay a dispatched command into a new session. A handler timeout sends a `failed` acknowledgement (`handler_timeout`) and keeps the session. If an acknowledgement reaches the gateway after the command closed, the gateway answers `late_ack`; the agent drops that acknowledgement and keeps polling on the same session. On disconnect, the gateway marks a dispatched command unconfirmed.

Async handlers must respond to cancellation. A plain-function handler runs in a worker
thread: the timeout stops the wait, not the thread. Do not detach physical actions from a handler.

## Stop and exit codes

SIGTERM (`systemctl stop`) and Ctrl-C stop the agent the same way: it cancels the running
handler, so its `finally` blocks run, then it calls `Device.on_shutdown` callbacks, then
it exits with code 0. A plain-function handler that is still running delays exit until it
returns.

Every other stop prints `Agent stopped (<code>). <hint>`. The code is a fixed string; it
never contains tokens, arguments or gateway text.

| Exit | Codes | Meaning |
| --- | --- | --- |
| 0 | `signal` | Stopped by SIGTERM or SIGINT |
| 1 | `internal_error` | Unexpected failure; inspect it privately |
| 2 | `factory_error`, `token_missing`, `token_invalid`, `invalid_option`, `simulation_only` | Configuration; argparse usage errors also exit 2 |
| 3 | `unauthorized`, `revoked` | Check the device ID and token; see token recovery below |
| 4 | `protocol_mismatch`, `invalid_request`, `invalid_response`, `frame_too_large`, `duplicate_conflict` | Protocol contract; for example, a hello larger than 2048 bytes |
| 5 | `reconnect_exhausted` | No gateway answered within the attempt budget |

## State and restart behavior

Each poll reports stored state. This refreshes gateway receipt time; it does not prove a new measurement. Publish new observations when necessary.

The boot ID stays the same during reconnects within one process. Restart creates a new boot ID. The event queue and command cache exist only in memory. Gateway restart removes its history and changes its cursor epoch.

After a gateway restart, the gateway can send a command ID that the device already
executed. The same arguments return the cached status with current state. Changed
arguments return a failed acknowledgement with `duplicate_conflict`; the agent stays
connected.

## Recover a device token

Issue a new token for the same device ID with
`grok-gadgets-gateway enroll <device-id> --rotate --token-file <file>`. The old token stops
working at once. An agent started with `--token-file <file>` reads the file again on its next
connection, so it reconnects without a restart. Rotating also reactivates a revoked ID.
`XDG_CONFIG_HOME` changes where the gateway keeps its registry.

## Prepare a Linux user service

The template is `examples/grok-gadget.service`. It is not yet verified under real systemd.
A test runs its `ExecStart` line from a temporary home folder without systemd.

The template expects:

- `~/grok-gadget/.venv` with this SDK installed;
- `~/grok-gadget/my_gadget.py` with a `create()` function;
- `~/.config/grok-gadgets/linux-agent.env` with `GROK_GADGETS_DEVICE_TOKEN=...`, mode `600`.

Steps:

1. Copy the template to `~/.config/systemd/user/grok-gadget.service`. Change paths if necessary.
2. Run `chmod 600 ~/.config/grok-gadgets/linux-agent.env`.
3. Run `systemctl --user daemon-reload`.
4. Run `systemctl --user start grok-gadget`, then check `journalctl --user -u grok-gadget`.
5. To start at boot without a login session, run `loginctl enable-linger "$USER"`.
6. Run `systemctl --user enable grok-gadget` after manual operation works.

The template uses `--retry-forever`, so the agent waits for a gateway that starts later.
`Restart=on-failure` with `RestartSec=5` restarts it after other failures.
`RestartPreventExitStatus=2 3 4` keeps it stopped after configuration, authorization
and contract errors; fix the cause, then start it again. A user unit cannot order itself
after a system network target, so the template has no `After=network.target`.

## Remove the test setup

1. Stop the service or agent.
2. Revoke its gateway device token.
3. If no longer needed, remove the virtual environment.

Keep unrelated gateway devices intact. Do not put credentials, arguments, private state or event contents in issue logs.

## Run gateway integration tests

Use the reviewed gateway source checkout:

```sh
GROK_GATEWAY_SOURCE=../grok-gadgets-gateway/src uv run python -m unittest discover -s tests -v
```

Without this variable, seven integration tests skip. Unit tests still run independently. Each integration test has a time limit, so a hang is reported as a failure. Component CI runs unit checks. Cross-repository checks must supply the pinned gateway source.
