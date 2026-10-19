# Repository Guidelines

## Project Structure & Module Organization

Root OpenAI, Claude, and Cursor marketplace catalogs distribute one plugin, `advisor`. Limit every catalog to it.

- `plugins/advisor/advisor.py`: shared Python CLI, MCP server, provider adapters, and consultation memory.
- `plugins/advisor/{configuration,session_context,review_checkpoints,usage_limits}.py`: user profiles, scoped capture, checkpoints, and quota evidence.
- `plugins/advisor/skills/{advisor,advisor-setup}/SKILL.md`: consultation and user-guided setup instructions.
- `scripts/export_muse.py`: native Muse package export from shared public sources.
- `plugins/advisor/.*-plugin/`, `mcp.json`, and `.mcp.json`: host-specific packaging.
- `tests/`: unit tests and MCP transport tests.
- `docs/compatibility.md`: installation routes and host limitations.

## Build, Test, and Development Commands

Use `uv` with Python 3.11+, inline dependencies, and the committed script lockfile. No build step.

```sh
uv run --script plugins/advisor/advisor.py doctor
uv run --script plugins/advisor/advisor.py serve
uv run --python 3.11 --with 'mcp>=1.20,<2' python -m unittest discover -s tests -v
uv lock --check --script plugins/advisor/advisor.py
```

`doctor` checks advising executables; `serve` starts stdio MCP. Tests simulate model calls. Refresh dependencies with `uv lock --script plugins/advisor/advisor.py`.

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations at boundaries, `snake_case` functions, and descriptive names. Prefer standard-library features; the official MCP SDK owns protocol handling. Format JSON manifests with two-space indentation. No formatter or linter is configured.

## Testing Guidelines

Use `unittest`, files named `test_*.py`, and behavior-focused test names. Cover validation, provider failures, session isolation, and budgets when changing consultation logic. Maintain the stdio smoke test. No coverage threshold is enforced.

Do not make live model calls in automated tests. Distinguish simulated provider checks from application installation and account verification.

## Commit & Pull Request Guidelines

No commit convention exists. Use imperative subjects, such as `Add consultation session isolation`. Describe behavior changes, validation, and host-specific limits in focused pull requests. Link related issues.

## Agent-Specific Constraints

Hooks supply instructions; agents invoke consultations. Users configure enabled models and efforts for the two providers; preserve existing Max defaults. Check `advisor_status` and explicitly choose one enabled advisor; requests cannot override user profiles. User-enabled `usage_fallback` permits the other enabled profile only after verified account exhaustion, within the same job and frozen context. Never switch on ambiguous errors, copy credentials, consult recursively, or commit session data. Distinguish documented compatibility from live-tested support.

## Using Advisor

After brief orientation, load the Advisor skill and consult before substantive implementation or committing to an approach. Longer, multistep tasks require early and final reviews: save the deliverable and run tests before the final review, then claim completion. Also consult for recurring errors, approach changes, or consequential uncertainty. Trivial reactive tasks need no repeated reviews. Supply a focused question, objective, constraints, evidence, attempts, and stable session/task IDs. Retrieve completed advice with `read_advice` before dependent decisions; evaluate and verify it. Ask users about unknown preferences.
