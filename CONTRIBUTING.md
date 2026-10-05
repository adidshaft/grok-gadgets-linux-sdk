# Contributing to the Linux SDK

Contribute to the library, agent, examples, tests or documentation without hardware. Device handlers belong here. The gateway owns the canonical protocol and MCP routing.

Discuss large features, interface changes and protocol changes before implementation. Submit small typo fixes directly. Use the [writing guide](https://github.com/adidshaft/grok-gadgets/blob/main/docs/contributing/writing-guide.md) for documentation.

The hub owns [shared contribution policy](https://github.com/adidshaft/grok-gadgets/blob/main/CONTRIBUTING.md),
[governance](https://github.com/adidshaft/grok-gadgets/blob/main/GOVERNANCE.md), and
[roadmap](https://github.com/adidshaft/grok-gadgets/blob/main/ROADMAP.md). Use [GitHub Issues](https://github.com/adidshaft/grok-gadgets-linux-sdk/issues) to track current work. The [local issue ledger](planning/issues.json) records preparation work.

## Standalone checks

Use Python 3.11 or later and uv. Fork the repository and clone your fork. From the SDK root, run:

```sh
git switch -c docs/clearer-device-example
uv sync --frozen --python 3.11
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv build
```

These checks need no sibling checkout. Without `GROK_GATEWAY_SOURCE`, five gateway integration tests skip. This result does not prove full integration.

For runtime or protocol changes, use a reviewed gateway source checkout:

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

Use a short branch from `main`. Make small tested commits and link the public issue. Explain the behavior before and after the change. Add a regression test when necessary.

Record commands, results, runtime and evidence level. Update user guidance. Respond to review and resolve conflicts on your branch. Then repeat affected checks.

Handlers must validate arguments and report observed state. Preserve retry, reconnect,
bounded retention, and safe-error behavior. Protocol changes start upstream and require
renewed canonical pins/hashes plus hub compatibility evidence; never hand-edit schema copies.

The maintainer credits code, documentation, testing, and review. You remain responsible
for AI-assisted contributions, licenses, and verified test claims. Contributions use
Apache-2.0; no additional CLA or sign-off is required. Never include credentials or private
captures. Do not publish, deploy, or operate live peripherals in an unapproved test.

See [support](SUPPORT.md), [conduct](CODE_OF_CONDUCT.md), [security](SECURITY.md), and [AGENTS](AGENTS.md).

## Ignore rules and publication privacy

Update `.gitignore` for new caches, build output, local device configuration, logs and credentials. Keep reviewed sample configuration and the hub’s public simulator download.

Check new patterns with `git check-ignore`. Review staged files before each commit. Ignore rules do not remove tracked files or history. Never merge private pre-publication history into a public branch. Use the sanitized public checkout and a public or GitHub noreply commit email.
