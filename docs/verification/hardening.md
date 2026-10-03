# Historical installed-factory correction evidence

This document records the 2026-10-04 software checkpoints and original counts/hashes.
Use [README](../../README.md) and [launch verification](launch-docs.md) for current setup.

# HARD-LIN-001 — installed custom factory

4 October 2026; Starting source `256a07e23ac4a4393066e0492847276849ac3348`, branch `fix/hard-lin-001`. Coordinator-created issue was the only initial dirty path.

Baseline: built the unmodified wheel with `uv build`, installed it into `/tmp/hard-lin-baseline-venv`, created `my_gadget.py` in a separate temporary working directory, and ran the installed `grok-linux-agent --factory my_gadget:create` with `PYTHONPATH` removed. Exit 1, generic safe diagnostic; an isolated import confirmed `ModuleNotFoundError: my_gadget`. The factory was unreachable.

Correction: explicit `--factory-file ./my_gadget.py:create` executes a trusted file using importlib's file loader without changing `sys.path`. Installed package factories still use `--factory package.module:create`; built-in software lamp remains default. Files execute trusted local code. Dependencies must be installed; file-directory/sibling and relative-package imports are not provided. Fixed diagnostic categories explain bad specification, unavailable file/module/function, load failure, factory failure and wrong return type without exposing original exception data.

Validation before implementation commit: `uv sync --frozen`; `uv run ruff check .`; `uv run ruff format --check .`; `GROK_GATEWAY_SOURCE=/absolute/path/grok-gadgets-gateway/src uv run python -m unittest discover -s tests -v` (18 passed, zero skipped); `uv build`; hub `python3 scripts/check.py` (passed). Source was a dirty feature branch, not a clean committed snapshot. The protocol README and source provenance were copied from canonical gateway `84b06fb9bef0f01639c215f2b5ada83fe5074218`; schemas/fixture unchanged, README SHA256 `b1ae2a5c8ea0933eb9bcedce01e8c7bbed5215591229a78932637f2a76f07ac1`. One intervening full-suite failure exposed the old fixed source-commit assertion in the fixture test; updated it consistently and reran all 18 successfully.

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

## Committed checkpoint

2026-10-04 16:28 UTC: clean implementation source `beb69c1ff38236adeb570c213d036fd225f8d41e` rebuilt with `uv build`; gateway source `84b06fb9bef0f01639c215f2b5ada83fe5074218`. New fresh macOS venv `/tmp/hard-lin-committed-venv` and new network-disabled Linux container repeated onboarding successfully against installed wheels. In both, installed-package unit/CLI tests passed: 18 collected, 13 executed, 5 optional source-gateway integrations skipped; the fresh custom verifier separately exercised real installed gateway transport. Full 18-case macOS source-gateway integration already passed before this commit. Built-in factory, missing/invalid factory categories, token redaction and help were verified.

Artifacts from that exact implementation source: wheel SHA256 `afef63923c4bfafe758978ec444a5b52064c965f4443a68bf2107693cdf3711d`, sdist SHA256 `980b2521b053083f90c763561086d7c8b2681cd6a6cf1ab9db7db1013ddf0be4`; tracked metadata in `planning/artifacts.json`, ignored raw logs/manifests in `reports/hardening/`. This checkpoint is a documentation-only follow-up; these package hashes refer to the stated implementation commit. The coordinator's final publication archive must identify its own actual source HEADs when rebuilt.

## Independent review correction — annotated dataclass factories

Independent source review reopened HARD-LIN-001 on the clean `04b5ac3` checkpoint. A valid self-contained file with `from __future__ import annotations` and stdlib `@dataclass class Settings: label: str` failed during import: dataclasses resolves string annotations through the defining module's `sys.modules` entry, which the original explicit loader did not create. New regression reproduced the safe `Factory file could not load` error before the fix (`reports/hardening/dataclass-before.log`, one error among five CLI tests). This was a local correctness gap, not an external gate.

Correction on short branch `fix/hard-lin-module-registration`: generate a fresh private UUID-based module name for each explicit load, register it before `exec_module`, and remove the owned entry on failed execution, including interrupted loads. Successful entries remain so class metadata can resolve their defining module for the running device lifetime. Repeated loads and identical basenames do not replace prior module objects; no `sys.path` additions. Fixed/redacted diagnostic categories remain unchanged. New tests execute annotated dataclasses, repeat the same file and a second same-basename file, resolve class type hints after subsequent loads, assert path preservation, and verify rollback/redaction on failure.

Before correction commit: frozen sync, Ruff lint/format, full macOS gateway-integrated suite (20 passed, zero skipped), wheel/sdist build and hub `python3 scripts/check.py` passed. This run used the dirty correction branch. `scripts/check_onboarding.py docs/development.md --dataclass` extends the installed-wheel verifier with the reviewed stdlib/string-annotation factory while keeping the default exact documented example unchanged. Fresh committed macOS/Linux acceptance and rebuilt artifact provenance follow in the next checkpoint.

### Reviewed correction committed checkpoint

2026-10-04 16:41 UTC: clean correction implementation `89478e51488764dd1d28618d7028973e5546e4a6` rebuilt with `uv build`; gateway wheel still from `84b06fb9bef0f01639c215f2b5ada83fe5074218`. Fresh macOS environment `/tmp/hard-lin-dataclass-venv` and a new offline pinned Linux container both passed the exact documented file example and `--dataclass` verifier variant, each registering/executing `display.set` and reporting state. SDK imports are from site-packages, Python verifier uses `-I`, child removes `PYTHONPATH`, and each factory runs from a fresh temporary working directory. Installed suites collected 20 tests: 15 executed/passed and 5 optional source-gateway tests skipped. Full source-gateway macOS suite passed all 20 before the implementation commit. macOS dependencies: jsonschema4.26.0/rpds-py2026.9.1; offline Linux retained locked jsonschema4.26.0/rpds-py2026.6.3. Platform versions/image and software-only limitations remain those recorded above.

Current corrected wheel SHA256 `79c3bbb464977e088b3461d9359900ec638ee6df601731dcd3ec8191f0835493`, sdist SHA256 `24103c8239de90d4b778ce411ce7f2f3c8af3a29bac63c597c3226e0f1fa260c`. They supersede the earlier package hashes and derive from clean `89478e51488764dd1d28618d7028973e5546e4a6`. `planning/artifacts.json` now identifies these files/source accurately. Raw evidence: ignored `reports/hardening/dataclass-before.log`, `macos-dataclass-docs.json`, `macos-dataclass.json`, `macos-dataclass-installed-tests.log`, `linux-dataclass-committed.log`, `dataclass-artifacts.json`. This documentation-only checkpoint follows the tested implementation; final publication archives must continue to name their actual rebuilt source commit.

Repeat the review variant by adding `--dataclass` to the verifier commands above, including the command inside the pinned container. The default verifier remains the exact documented Python example. HARD-LIN-001 closed again after this local correction; independent review disposition is maintained by the hub coordinator.
