# Run and recover

The agent connects only to loopback TCP: `127.0.0.1` or `::1`. The default port is 8765. Run the agent and gateway on the same host.

This SDK does not provide a remote transport, public gateway, tunnel or cloud service. The authenticated route from Grok remains unresolved.

## Start the agent

1. Install the gateway. Follow its README.
2. Authorize a per-device token in the gateway credential file. Set file permissions to `600`. The default software device ID is `linux-lamp-1`.
3. Start the gateway listener through an initialized MCP client or the local demo. A stdio process alone does not start the listener.
4. Set `GROK_DEVICE_TOKEN` privately to the same token.
5. Run `uv run grok-linux-agent`.
6. Request device capabilities through gateway MCP.

The default agent is a software lamp. Add `--simulate-button` to queue simulated press and release events. Use `--factory module:function` for a trusted application. Use `--port` for a different loopback port.

SDK integration tests start `DeviceServer` directly on temporary loopback ports. They do not use a paid API call or a live Grok account.

Keep both services running while you need the device. Keep ordinary peripheral controls independent of Grok. When the agent stops, the gateway marks it offline. Closing an MCP client does not necessarily stop either service.

A command can be accepted without a confirmed result. A reported result does not prove a physical effect. Record each evidence level separately.

## Connection limits

| Setting | Default |
| --- | --- |
| Poll interval | 100 ms |
| Socket timeout | 2 seconds |
| Handler timeout | 5 seconds |
| Failed connection or session attempts | At most 8 |
| Reconnect delay | Starts at 250 ms; doubles up to 5 seconds |
| Healthy session needed to reset the failure budget | 10 seconds |

Authorization, revocation and contract errors stop the agent immediately. Each request rechecks gateway revocation. Exhausted reconnect attempts produce a fixed diagnostic. Shutdown interrupts a reconnect delay.

A lost event acknowledgement retains the event ID for reconnect. The gateway does not replay a dispatched command into a new session. A handler timeout produces no success acknowledgement. On disconnect, the gateway marks that command unconfirmed.

Handlers must respond to cancellation. Do not detach physical actions from a handler.

## State and restart behavior

Each poll reports stored state. This refreshes gateway receipt time; it does not prove a new measurement. Publish new observations when necessary.

The boot ID stays the same during reconnects within one process. Restart creates a new boot ID. The event queue and command cache exist only in memory. Gateway restart removes its history and changes its cursor epoch.

## Prepare a Linux user service

The template is `examples/grok-gadget.service`. Real user-service operation and physical peripherals remain untested.

1. Copy the template and set the virtual environment and factory paths.
2. Set environment-file permissions to `600`.
3. Run `systemctl --user daemon-reload`.
4. Run `systemctl --user start grok-gadget`.
5. Check manual operation before you enable automatic startup.

Automatic restart is disabled to preserve the retry limit. Diagnose a failure before restart. Replace revoked credentials when necessary.

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

Without this variable, five integration tests skip. Unit tests still run independently. Component CI runs unit checks. Cross-repository checks must supply the pinned gateway source.
