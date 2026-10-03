# Contributing to the Linux SDK

Improve the library, agent, examples, tests, or documentation without hardware.
Device handlers belong here; canonical protocol and MCP routing belong in the gateway.
Discuss substantial features, interfaces, and protocol changes first. Small typo fixes
need no issue ceremony.

The hub owns [shared contribution policy](https://github.com/adidshaft/grok-gadgets/blob/main/CONTRIBUTING.md),
[governance](https://github.com/adidshaft/grok-gadgets/blob/main/GOVERNANCE.md), and
[roadmap](https://github.com/adidshaft/grok-gadgets/blob/main/ROADMAP.md). These links are
planned destinations until publication. Use the supplied source and [local issues](planning/issues.json)
during preparation.

## Standalone checks

Use Python 3.11+ and uv. After publication, fork/clone this component; a supplied local
source tree works now. From the SDK root:

```sh
git switch -c docs/clearer-device-example
uv sync --frozen --python 3.11
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv build
```

These checks require no sibling checkout. Five optional gateway integration cases skip
without `GROK_GATEWAY_SOURCE`; that is explicit scope, not full integration acceptance.
When coordinating a runtime/protocol change, point to a reviewed gateway source checkout:

```sh
GROK_GATEWAY_SOURCE=/absolute/path/grok-gadgets-gateway/src uv run python -m unittest discover -s tests -v
```

Replace the placeholder with the checkout at the exact agreed commit. Record both SHAs.
The hub separately tests the coordinated component combination; an isolated SDK success
does not promote it automatically.

For example, factory-loading, or installation guidance changes, also run the [README](README.md)
fresh-wheel onboarding from outside the checkout. Run the lint/format/unit/build checks
before committing documentation as well as code. Linux service/peripheral claims need
their own authorized Linux/hardware observations.

## Review and credit

Keep small tested commits and a short branch from main. Link the public issue after
migration or the stable local ID now. Explain before/after behavior and add a focused
functional regression when needed. Provide exact commands, results, runtime, and evidence
level; update user guidance. Respond to review, resolve conflicts on your branch, and rerun
affected checks.

Handlers must validate arguments and report observed state. Preserve retry, reconnect,
bounded retention, and safe-error behavior. Protocol changes start upstream and require
renewed canonical pins/hashes plus hub compatibility evidence; never hand-edit schema copies.

The maintainer credits code, documentation, testing, and review. You remain responsible
for AI-assisted contributions, licenses, and verified test claims. Contributions use
Apache-2.0; no additional CLA or sign-off is required. Never include credentials or private
captures. Do not publish, deploy, or operate live peripherals in an unapproved test.

See [support](SUPPORT.md), [conduct](CODE_OF_CONDUCT.md), [security](SECURITY.md), and [AGENTS](AGENTS.md).
