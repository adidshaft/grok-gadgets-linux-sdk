# HUB-HW-001 — Raspberry Pi 5 host report

Issue: [adidshaft/grok-gadgets#15](https://github.com/adidshaft/grok-gadgets/issues/15)

This report covers **one** host: a Raspberry Pi 5 running the tagged Linux SDK
against a loopback gateway. It does **not** prove other boards or GPIO.

## Hardware and software

- Board: Raspberry Pi 5 Model B Rev 1.1
- OS: Debian (Raspberry Pi OS), aarch64, kernel `6.18.50+rpt-rpi-2712`
- Peripherals: none attached (no user LED/button on documented gadget pins)
- Gateway: `grok-gadgets-gateway` `v0.1.0-alpha.2` (`3ac72a3`)
- Linux SDK: `grok-gadgets-linux-sdk` `v0.1.0-alpha.2` (`83d55b6`)
- Interpreter for SDK/gateway venv: CPython 3.11.15 via `uv`
- Connection: gateway `serve --simulator --allowed-host <owner HTTPS hostname>`
  on `127.0.0.1:8766` (MCP) and `127.0.0.1:8765` (devices). Device port remains
  loopback-only. MCP later received an **owner-approved** HTTPS front (TLS
  terminator to `127.0.0.1:8766/mcp` only). No Tailscale Serve/Funnel. Device
  port was not published.
- Tester: local operator on this host. Tokens and credential files were not
  recorded. The public hostname is omitted from this report.

## Commands (repeatable, no secrets)

Gateway (already initialized; token file mode `0600`, not shown):

```sh
# from grok-gadgets-gateway v0.1.0-alpha.2
uv sync --locked
uv run grok-gadgets-gateway serve --simulator
```

Linux SDK software lamp (documented README example, `simulated` default):

```sh
# from grok-gadgets-linux-sdk v0.1.0-alpha.2
uv sync --extra gateway
# enroll writes a device token file (mode 0600); do not print it
grok-gadgets-gateway enroll desk-lamp --token-file "$HOME/.config/grok-gadgets/desk-lamp.token"
grok-linux-agent --factory-file ./my_gadget.py --token-file "$HOME/.config/grok-gadgets/desk-lamp.token"
grok-gadgets-gateway rehearse --device desk-lamp --command set.light --args '{"on": true}'
```

`ss -ltn` showed only `127.0.0.1:8765` and `127.0.0.1:8766`. Unauthenticated
`GET http://127.0.0.1:8766/mcp` returned `401`.

## Results

| Check | Result | Notes |
| --- | --- | --- |
| Gateway simulator `sim-c124` / `rgb.set` | **Pass** | `rehearse` executed; software simulation only |
| Linux SDK software lamp `desk-lamp` / `set.light` | **Pass** | `executed`, state `{"on": true}`; `simulated: true` |
| Agent stop | **Pass** | `gadgets_command` → `unavailable: Device is disconnected` |
| Agent reconnect | **Pass** | `set.light {"on": true}` executed again |
| Physical LED / button | **Not tested** | No documented peripheral. On-board `PWR`/`ACT` sysfs LEDs exist; they are not a Grok Gadgets gadget, pins were not guessed, and the LED was not visually observed. |
| Grok Bot | **Pass (operator-confirmed Remote HTTPS)** | Grok Bot desktop connector (Remote HTTPS + bearer) reached this host’s MCP. Device port `:8765` unpublished. This is **not** a pass of [HARD-GROK-REMOTE-001](https://github.com/adidshaft/grok-gadgets/issues/4) (OAuth, named/revocable tokens, rate limits still unimplemented). |

## Evidence levels (kept separate)

- **Build / install:** tagged checkouts synced with `uv`; user systemd unit ran
  `serve --simulator`.
- **Simulator / SDK TCP:** `rehearse` on loopback MCP with bearer token file.
- **Physical observation:** none. A successful `rehearse` is not a hardware pass.
- **Grok Bot:** operator-confirmed Remote HTTPS session against owner-fronted
  MCP. No tokens, request bodies, or hostnames recorded here.

## Blockers

1. Packaged product remote MCP (HARD-GROK-REMOTE-001) is still unimplemented.
2. No authorized, documented gadget peripheral on this Pi.

This report applies only to this Raspberry Pi 5 + tagged `v0.1.0-alpha.2` pair.
