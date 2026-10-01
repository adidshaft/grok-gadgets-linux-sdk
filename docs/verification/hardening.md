# HARD-LIN-001 — installed custom factory

4 October 2026; H2 owner: bounded Linux agent, GPT-6.1 Sol Medium. Starting source `256a07e23ac4a4393066e0492847276849ac3348`, branch `fix/hard-lin-001`. Coordinator-created issue was the only initial dirty path.

Baseline: built the unmodified wheel with `uv build`, installed it into `/tmp/hard-lin-baseline-venv`, created `my_gadget.py` in a separate temporary working directory, and ran the installed `grok-linux-agent --factory my_gadget:create` with `PYTHONPATH` removed. Exit 1, generic safe diagnostic; an isolated import confirmed `ModuleNotFoundError: my_gadget`. The factory was unreachable.

Correction: explicit `--factory-file ./my_gadget.py:create` executes a trusted file using importlib's file loader without changing `sys.path`. Installed package factories still use `--factory package.module:create`; built-in software lamp remains default. Files execute trusted local code. Dependencies must be installed; file-directory/sibling and relative-package imports are not provided. Fixed diagnostic categories explain bad specification, unavailable file/module/function, load failure, factory failure and wrong return type without exposing original exception data.

Validation before implementation commit: `uv sync --frozen`; `uv run ruff check .`; `uv run ruff format --check .`; `GROK_GATEWAY_SOURCE=/path/to/grok-gadgets-gateway/src uv run python -m unittest discover -s tests -v` (18 passed, zero skipped); `uv build`; hub `python3 scripts/check.py` (passed). Source was a dirty feature branch, not a clean committed snapshot. The protocol README and source provenance were copied from canonical gateway `84b06fb9bef0f01639c215f2b5ada83fe5074218`; schemas/fixture unchanged, README SHA256 `b1ae2a5c8ea0933eb9bcedce01e8c7bbed5215591229a78932637f2a76f07ac1`. One intervening full-suite failure exposed the old fixed source-commit assertion in the fixture test; updated it consistently and reran all 18 successfully.

Fresh installed-wheel acceptance: `scripts/check_onboarding.py` extracts the exact Python example from `docs/development.md`, writes `my_gadget.py` in a fresh temporary directory, runs the installed console script with the documented `--factory-file ./my_gadget.py:create` and test gateway port, authenticates/registers `display-1`, commands `display.set`, checks executed acknowledgment and reported `{"text": "installed custom works"}` state, and checks help. Both SDK and gateway are installed wheels; Python runs with `-I`, subprocess removes `PYTHONPATH`; neither imports source or an editable checkout. Gateway wheel is installed without optional/MCP dependencies because this verifier exclusively uses its domain/TCP transport and shared jsonschema dependency; it does not claim MCP verification.

macOS: 27.0 arm64, CPython 3.11.15, SDK imported from fresh venv site-packages. Actual Linux: kernel 6.10.14-linuxkit aarch64/glibc 2.41, CPython 3.11.17, official pinned image `python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b`, Docker server 28.3.3. Fresh `/tmp/fresh` venv, installed wheel, working directory `/tmp`; `--network none`, read-only input mounts, no ports published. Both passed. Initial raw results under ignored `reports/hardening/`.

Repeat after building both component wheels:

```sh
uv venv /tmp/grok-custom-venv
uv pip install --python /tmp/grok-custom-venv/bin/python dist/grok_gadgets_linux_sdk-0.1.0a1-py3-none-any.whl
uv pip install --no-deps --python /tmp/grok-custom-venv/bin/python ../grok-gadgets-gateway/dist/grok_gadgets_gateway-0.1.0a1-py3-none-any.whl
/tmp/grok-custom-venv/bin/python -I scripts/check_onboarding.py docs/development.md
```

Linux, with SDK_DIR/GATEWAY_DIR absolute checkout paths and the locked wheelhouse prepared as in `docs/verification.md`:

```sh
docker run --rm --network none -v "$SDK_DIR:/sdk:ro" -v "$GATEWAY_DIR/dist:/gateway-dist:ro" -v /tmp/grok-linux-wheelhouse:/wheels:ro python@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b sh -c 'python -m venv /tmp/fresh && /tmp/fresh/bin/python -m pip install --no-index --find-links=/wheels /sdk/dist/grok_gadgets_linux_sdk-0.1.0a1-py3-none-any.whl && /tmp/fresh/bin/python -m pip install --no-deps /gateway-dist/grok_gadgets_gateway-0.1.0a1-py3-none-any.whl && cd /tmp && /tmp/fresh/bin/python -I /sdk/scripts/check_onboarding.py /sdk/docs/development.md'
```

Evidence level: installed software simulation against a real local gateway TCP server. No actual Grok, physical peripheral, systemd, USB permission or independent human verification. No publication, push, account calls or deployment. Clean implementation commit and artifact hashes are recorded in the following checkpoint.
