# Repository instructions

Own reusable Linux library, agent and examples here. Consume the pinned canonical protocol from the gateway repository's protocol/0.1.0 and communicate breaking changes before adopting them. Prepared upstream: https://github.com/adidshaft/grok-gadgets-gateway. No conflicting schema definitions. Keep host/runtime evidence explicit; macOS does not verify Linux. Use subagents when useful; never Brave/Safari/Passwords. No push/publication/deployment/spending/live devices without authorization.

Use main and short feature branches with small tested commits referencing planning/issues.json. Maintain issues and respond when remote publication is authorized. Checks: uv sync --frozen; uv run ruff check .; uv run ruff format --check .; uv run python -m unittest discover -s tests -v; uv build. Never commit credentials or imply execution proves physical effects.

Use bounded subagents with explicit file ownership when helpful. Research tasks use the strongest available reasoning and cite primary sources. If unavailable, report it before substituting. Ordinary implementation/review
may use established settings. Do not research on a lower-effort assignment; ask the
coordinator to arrange an authorized research task.

## Ignore rules and publication privacy

Keep `.gitignore` current whenever a new tool produces caches, build output, local device configurations, execution logs or credentials. Preserve reviewed sample configuration files and the hub's verified public simulator download. Check new patterns with `git check-ignore`, then review the staged file list before committing. Ignore rules do not remove tracked files or past history; never merge the private pre-publication history back into a public branch. Use the sanitized public checkout and a public or GitHub noreply commit email.
