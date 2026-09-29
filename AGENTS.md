# Repository instructions

Own reusable Linux library, agent and examples here. Consume pinned canonical protocol from ../grok-gadgets-gateway/protocol/0.1.0 and communicate breaking changes before adopting them. No conflicting schema definitions. Keep host/runtime evidence explicit; macOS does not verify Linux. Use subagents when useful; never Brave/Safari/Passwords. No push/publication/deployment/spending/live devices without authorization.

Use main and short feature branches with small tested commits referencing planning/issues.json. Maintain issues and respond when remote publication is authorized. Checks: uv sync --frozen; uv run ruff check .; uv run ruff format --check .; uv run python -m unittest discover -s tests -v; uv build. Never commit credentials or imply execution proves physical effects.
