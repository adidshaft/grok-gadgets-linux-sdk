# Security policy

Supported scope: current experimental alpha (`0.1.0a1`, protocol `0.1.0`).
No security SLA or support for older snapshots is promised.

Use [GitHub private vulnerability reporting](https://github.com/adidshaft/grok-gadgets-linux-sdk/security/advisories/new)
once enabled after repository activation. Until then, or if unavailable, email
**adidshaft@kyokasuigetsu.xyz**. Do not post exploit details or credentials in public
issues or Reddit. The hub owns the shared
[disclosure policy](https://github.com/adidshaft/grok-gadgets/blob/main/SECURITY.md).

Include exact versions/commits, impact, and a minimal safe reproduction. Redact tokens,
private paths, account identifiers, household state, event contents, and raw captures.
The maintainer coordinates reproduction, mitigation, and disclosure privately without
an invented response deadline.

## Component limits

- Transport is unencrypted authenticated loopback TCP; no remote endpoint is supported.
  Keep credentials outside Git and supply `GROK_DEVICE_TOKEN` privately.
- A factory file/module is trusted local code with process privileges. Never execute a
  factory supplied by an untrusted conversation, device payload, or support attachment.
- The agent does not log raw frames, arguments, or exception text by default. Application
  code must still keep state/events free of secrets visible through gateway tools.
- Retry/dedup/event retention is bounded and memory-only. Do not blindly repeat an
  uncertain physical action under a new command ID.
- Background physical handlers must honor cancellation; detached actions can outlive
  a timed-out command. An acknowledgement alone never verifies a physical effect.

Read [operation](docs/operation.md) and [development](docs/development.md) before enrollment.
Real peripherals, service activation, and network exposure require separate approval and evidence.
