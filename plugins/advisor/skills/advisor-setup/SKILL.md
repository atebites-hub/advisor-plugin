---
name: advisor-setup
description: Set up or change Advisor's enabled providers, models, and effort when the user requests plugin configuration. Does not apply to routine coding or consultations.
---

# Set up Advisor

Use this workflow for the user's Advisor setup or configuration request. Keep existing choices and session authorization; ask only about preferences that remain unknown.

## Choose profiles

If available, call `advisor_status` to inspect effective profiles and their configuration source. It makes no model calls. Each provider has `enabled`, `model`, and `effort` settings:

- `claude` uses the installed, signed-in Claude Code CLI; its default is `claude-opus-5-5` with `max` effort.
- `codex` uses the installed, signed-in Codex CLI; its default is `gpt-6.1-sol` with `max` effort.

Both providers are enabled by default. Users may disable either or both. Use explicit model IDs; Claude IDs must start with `claude-`. Valid effort values are `low`, `medium`, `high`, `xhigh`, and `max`; actual support depends on the account and model. Preserve unrelated settings, including fallback permission and budgets.

## Save through the existing wizard

Resolve the installed plugin root, two directories above this skill's directory, and locate `advisor.py`. The shared file is `~/.config/advisor/config.json`, unless a nonempty `ADVISOR_CONFIG` selects another path. Show the resolved absolute file path and proposed profile changes without exposing unrelated private values.

`ADVISOR_CONFIG` must reach the MCP process to select its file; a terminal can have a different environment. Native Muse plugins remove custom `ADVISOR_*` variables and use the default file. Compare the reported configuration source before choosing a target. A custom path in Muse requires its manual MCP route; writing another file alone will not change its native server.

Cursor CLI does not apply the plugin's variable defaults. To use the shared file, launch a fresh CLI session with `ADVISOR_USE_APP_SETTINGS=false cursor-agent --plugin-dir "/absolute/plugin/root"`. The native plugin does not forward custom `ADVISOR_CONFIG` or `ADVISOR_STATE_DIR`; use its default shared file or the manual MCP route for custom paths. Cursor dashboard variables are a separate configuration route.

Run the existing command with resolved absolute paths, quoted for the shell:

```sh
uv run --script "/absolute/plugin/root/advisor.py" configure --config "/absolute/config.json"
```

The wizard owns validation and private, atomic saving. Have the user provide its responses and save confirmation through an interactive terminal. Do not invent preferences or pipe confirmation on behalf of an uninformed user. Already authorized choices need no separate approval request. If the host cannot expose interactive input, provide the exact command with the resolved paths for the user to run; report setup pending until the save is confirmed. Cancellation or a write error does not establish a saved configuration.

## Verify effective settings

After an actual save, call `advisor_status` again and compare enabled flags, model IDs, and effort with the user's choices. If the tool is unavailable, report effective-settings verification pending. Host GUI overrides can supersede the shared file: ZCode enables them by default; Advisor's Claude Code and Cursor packages default them off. If effective profiles differ, explain the source and let the user choose to edit that host's GUI or turn its overrides off. Do not silently rewrite host configuration.

Installed executables and configured models do not prove authentication or model access. Direct missing CLI installation or sign-in through each provider's official flow. Do not copy credentials or make live consultations as part of setup.
