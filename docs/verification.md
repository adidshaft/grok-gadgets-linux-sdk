# Verification — 4 October 2026

Historical software verification checkpoints. For current first-run instructions and
launch checks use [README](../README.md) and [launch verification](verification/launch-docs.md).

H2 correction: explicit trusted custom-file onboarding now passes from fresh wheel installations on macOS and actual pinned Linux. See [hardening evidence](verification/hardening.md) for source commit, current canonical pin, failures, commands and artifacts. The earlier 15-case snapshot below is historical.

15 tests passed on macOS (CPython 3.11.15 arm64) and on actual Linux in Docker: clean built-wheel install, generic async custom capability, schema/argument checks, bounded command dedup (including concurrency and eviction), event ordering/backpressure, capped backoff/exhaustion/stop, real authenticated gateway TCP, revocation with no retries, gateway restart reconnect, handler timeout remaining unconfirmed, and installed software-lamp CLI subprocess with explicit simulated button edges. Tests use gateway commit `46060230e52ea5dd3834a269ef44cebaf186490a`; canonical protocol copies remain pinned to `9cf5a25e795bce878485d160c01e5d7bea04267d`.

Linux: official image `python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b`; kernel `6.10.14-linuxkit`, CPython `3.11.17`, aarch64, glibc2.41. Package imported from `/usr/local/lib/python3.11/site-packages/grok_gadgets_linux/__init__.py`, not the mounted source. Container used `--network none`, read-only SDK/gateway/wheelhouse mounts, no published ports. This verifies software runtime on this Linux configuration, not all distributions, architectures or physical hardware.

Checks passed: frozen uv installation, Ruff lint/format, wheel/sdist, macOS integration and clean Linux-wheel acceptance. A standalone clone's default suite intentionally skips five gateway integration cases; set GROK_GATEWAY_SOURCE or use the container procedure to execute them. GitHub CI is only a prepared template and has not run remotely. User service template has not been enabled/tested.

Repeat Linux acceptance after building the wheel:

```sh
mkdir -p /tmp/grok-linux-wheelhouse
# Network is needed only to download the locked dependency wheels; no ports published.
docker run --rm -v /tmp/grok-linux-wheelhouse:/wheels python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b python -m pip download --only-binary=:all: --dest /wheels jsonschema==4.26.0 attrs==26.1.0 jsonschema-specifications==2025.9.1 referencing==0.37.0 rpds-py==2026.6.3 typing-extensions==4.16.0
# Set SDK_DIR and GATEWAY_DIR to absolute checkout paths before this command.
docker run --rm --network none -v "$SDK_DIR:/sdk:ro" -v "$GATEWAY_DIR:/gateway:ro" -v /tmp/grok-linux-wheelhouse:/wheels:ro python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b python /sdk/scripts/linux_acceptance.py
```

Original code licensed Apache-2.0. Dependencies locked in uv.lock. No secrets, account calls, external endpoints, deployment or publication used. Evidence level: Linux runtime verified + software simulation + package build verified. Open gates: real Grok/tool route/mobile, physical peripherals, systemd behavior, independent reproduction and publication approval.
