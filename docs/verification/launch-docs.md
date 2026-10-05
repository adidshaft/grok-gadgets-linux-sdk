# Public-alpha documentation verification

LAUNCH-DOCS-LIN-001 covers L2/L3/L6 preparation from `768957f6`. Checks on
2026-10-05 used macOS 27 arm64, CPython 3.11.15. This is documentation/policy
preparation; source, tests, scripts, examples, canonical copies/pins, metadata and lock
files are unchanged. Earlier Linux-container evidence remains historical and linked.

## Source and fresh installation checks

- `uv sync --frozen --python 3.11`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv build`: passed.
- `uv run python -m unittest discover -s tests -v`: 20 collected, 15 passed;
  five optional gateway-source cases explicitly skipped in this standalone checkout.
- Hub `python3 scripts/check.py`: passed; 35 labeled records and Python syntax verified.
- 36 relative links in changed Markdown resolved locally; the Mermaid diagram was
  inspected against the local SDK/agent/gateway interfaces. External destinations
  remain pending activation.

The exact [README](../../README.md) block ran from an otherwise empty temporary folder
with the SDK wheel/sdist and separately built gateway wheel. `uv venv --python 3.11
--seed .venv` selected native arm64 Python 3.11.15. Pip installed both packages and
declared dependencies normally. The verifier and exact development example came from
the extracted SDK sdist. SDK imports came from temporary `site-packages`; there was no
editable install, source gateway path or inherited `PYTHONPATH`.

Both the documented factory and the additional annotated-dataclass variant passed:
`display.set` acknowledged `executed`, readback was `{"text":"installed custom works"}`,
`simulated: true`, `physical_verified: false`. The verifier started a bounded ephemeral
authenticated loopback listener and closed it afterward. This establishes software
SDK-to-gateway TCP behavior, not a native Grok invocation or MCP-client session.

Tested SDK wheel SHA256: `79c3bbb464977e088b3461d9359900ec638ee6df601731dcd3ec8191f0835493`.
Tested SDK sdist SHA256: `3c80ec1af9dea180a2359729f1b8fe14ad8f31761a1f5b13e4a46153758fcf4f`.
Gateway wheel SHA256: `dd0b71b0a9e124962184085c469c6a1bc0292a593d888cf219e4ce703598ac39`.
These name working-source test artifacts. Final clean-commit hashes belong in the
coordinated candidate manifest.

An exploratory generic `python3` install selected x86_64 CPython 3.13.5 and failed
compiling a transitive cryptography dependency with the older Rust toolchain.
The README now explicitly selects the tested environment. Intel and other interpreter
combinations remain unverified.

## License, privacy and remaining gates

Apache-2.0 LICENSE/NOTICE are unchanged and present in the wheel; canonical protocol
copies and hash pins are unchanged. Original Mermaid text adds no third-party assets.
Current historical guidance replaces the personal absolute checkout path with a
clearly marked placeholder. The bounded read-only scan covered all eight pre-change
reachable commits: four retained historical personal machine paths; author metadata
retains `224602646+adidshaft@users.noreply.github.com`. No limited token-signature match was found. This is not
comprehensive credential clearance. No history was rewritten; publication needs the
owner's disposition of historical path/identity exposure.

Public repositories/downloads, hosted CI/private reporting and owner protection remain
pending activation. No service is activated. Native Grok/mobile, real systemd/peripherals,
other platforms/architectures and independent human reproduction remain open. Current
Mac checks do not extend historical Linux aarch64 container evidence to real peripherals.
