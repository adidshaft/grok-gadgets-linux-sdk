# Run and recover

The agent connects only to `127.0.0.1`/`::1` TCP (default 8765). No remote transport, public gateway, tunnel or cloud hosting is activated. It shares the host with the gateway; the Grok cloud route is a separately unresolved authenticated connection.

1. Install gateway separately following its README; authorize a per-device token in its mode-600 credential file. Default software example device ID is `linux-lamp-1`.
2. Activate gateway device listener through its MCP lifespan/client, or use its local demo. Starting a stdio process without MCP initialization does not start a listener. For integration verification here, tests start real `DeviceServer` directly on ephemeral loopback TCP.
3. Supply the same token through `GROK_DEVICE_TOKEN`, then `uv run grok-linux-agent`. This default is explicitly a software lamp. Optional `--simulate-button` queues simulated press/release; absent by default. `--factory module:function` selects your trusted application; `--port` selects a loopback listener.
4. Request custom device capabilities through gateway MCP. Distinguish accepted, reported execution and observed physical effect. No API conversation, paid call or live Grok account is used by SDK tests.

Run both services continuously for device availability. Ordinary local peripheral controls should remain independent of a Grok conversation. Closing this agent makes gateway state offline; closing a client alone does not necessarily stop either service.

Default agent: poll 100ms; 2s socket timeout; 5s handler timeout; at most 8 failed session/connect attempts, starting 250ms exponential backoff capped 5s. A healthy session of 10s resets the failure budget. Unauthorized/revoked/contract errors stop immediately. Capped reconnect exhaustion exits with a fixed diagnostic. Shutdown interrupts backoff. Every request rechecks gateway revocation. Lost event acknowledgement retains the same event ID for reconnect; no dispatched command is replayed into a new gateway session. A timed-out handler receives no success ACK, causing gateway unconfirmed status on disconnect. Handlers must honor cancellation and avoid detached physical actions.

Agent reports its stored state during polls: this updates gateway receipt freshness, not proof of a new physical measurement. Applications must publish new observations as appropriate. Boot ID survives reconnect in one process and changes at restart. Event queue and command cache are memory-only. Gateway restart loses its history and changes cursor epoch.

Optional Linux user service template in `examples/grok-gadget.service`: copy/edit paths to your venv/factory, keep environment file mode600, then use `systemctl --user daemon-reload` and `systemctl --user start grok-gadget`. Enable autostart only after manual validation. Restart is disabled to preserve bounded retry behavior; recover deliberately after diagnosing/replacing revoked credentials. User service lifecycle and physical peripherals remain untested; the template is preparation.

Remove experiment by stopping the service/agent and revoking its gateway device token; uninstall the venv if desired. Preserve unrelated gateway devices. Never include credentials, args, private state or event bodies in issue logs.

Real gateway integration from sibling checkout:

```sh
GROK_GATEWAY_SOURCE=../grok-gadgets-gateway/src uv run python -m unittest discover -s tests -v
```

Without this environment variable, five integration cases are explicitly skipped and unit tests remain independently runnable. The CI template runs unit checks; cross-repository orchestration must provide the pinned gateway source for integration checks.
