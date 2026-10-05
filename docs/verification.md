# Verification — 4 October 2026

Historical software verification checkpoints. For current first-run instructions and
launch checks use [README](../README.md) and [launch verification](verification/launch-docs.md).

H2 correction: explicit trusted custom-file onboarding now passes from fresh wheel installations on macOS and in the pinned Linux container. See [hardening evidence](verification/hardening.md) for source commit, current canonical pin, failures, commands and artifacts. The earlier 15-case snapshot below is historical.

15 tests passed on macOS (CPython 3.11.15 arm64) and in a Linux container (Docker on macOS): clean built-wheel install, generic async custom capability, schema/argument checks, bounded command dedup (including concurrency and eviction), event ordering/backpressure, capped backoff/exhaustion/stop, real authenticated gateway TCP, revocation with no retries, gateway restart reconnect, handler timeout remaining unconfirmed, and installed software-lamp CLI subprocess with explicit simulated button edges. Tests used gateway commit `d2b1008c2f2a7474288bf3ae9aa83cd49c1e5554` with protocol copies from `9f65e48de6eb4b74d0b3ab18a34a19e29cb44f8b`. The shipped pin is now `aeabcaf46cca830894836ac5cb85f3a6d33cd63d` in the public gateway repository; an external review (5 October 2026) reported identical schema files between these commits, with only `protocol/0.1.0/README.md` changed.

Linux: official image `python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b`; kernel `6.10.14-linuxkit`, CPython `3.11.17`, aarch64, glibc2.41. Package imported from `/usr/local/lib/python3.11/site-packages/grok_gadgets_linux/__init__.py`, not the mounted source. Container used `--network none`, read-only SDK/gateway/wheelhouse mounts, no published ports. This is Linux container software acceptance (partial) on one container configuration. It is not a Linux host, systemd, Raspberry Pi or physical-hardware verification.

Checks passed: frozen uv installation, Ruff lint/format, wheel/sdist, macOS integration and clean Linux-wheel acceptance in the container. A standalone clone's default suite intentionally skips the gateway integration cases; set GROK_GATEWAY_SOURCE or use the container procedure to execute them. At the time of this record GitHub CI had not run; an external review later reported the `Checks` workflow succeeding on `main` on 5 October 2026 (Python 3.11 only, before the 3.11–3.14 matrix). User service template has not been enabled/tested under systemd.

Repeat Linux acceptance after building the wheel:

```sh
mkdir -p /tmp/grok-linux-wheelhouse
# Network is needed only to download the locked dependency wheels; no ports published.
docker run --rm -v /tmp/grok-linux-wheelhouse:/wheels python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b python -m pip download --only-binary=:all: --dest /wheels jsonschema==4.26.0 attrs==26.1.0 jsonschema-specifications==2025.9.1 referencing==0.37.0 rpds-py==2026.6.3 typing-extensions==4.16.0
# Set SDK_DIR and GATEWAY_DIR to absolute checkout paths before this command.
docker run --rm --network none -v "$SDK_DIR:/sdk:ro" -v "$GATEWAY_DIR:/gateway:ro" -v /tmp/grok-linux-wheelhouse:/wheels:ro python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b python /sdk/scripts/linux_acceptance.py
```

Original code licensed Apache-2.0. Dependencies locked in uv.lock. No secrets, account calls, external endpoints, deployment or publication used. Evidence level: Linux container software acceptance (partial) + software simulation + package build verified. Open gates: real Grok/tool route/mobile, physical peripherals, systemd behavior, a non-container Linux host, independent reproduction and publication approval.
