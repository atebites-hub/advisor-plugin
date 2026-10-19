# Antigravity integration

Advisor needs a native Antigravity package for its startup instructions and MCP server. Export it from this checkout into a workspace outside the repository; the marketplace still contains only one plugin, `advisor`.

## Export and load

Create the destination's parent, then export into a new directory:

```sh
mkdir -p /absolute/path/to/workspace/.agents/plugins
uv run --python 3.11 python scripts/export_antigravity.py /absolute/path/to/workspace/.agents/plugins/advisor
```

The destination must be absolute, new, and outside the checkout, with an existing parent. Existing paths and symlinks are never replaced. The bundle contains eight shared runtime/skill files plus `mcp_config.json`, `hooks.json`, and the native `plugin.json`, written last. Credentials, user configuration, consultation state, and other hosts' manifests are excluded.

Use the bundle only after the exporter succeeds. A failed write leaves partial output for inspection; choose a new destination rather than installing it. The exporter does not install a global plugin or delete output.

Open that workspace in Antigravity Desktop, or run `agy --new-project` from its directory. Native runtime verified that both MCP and hook commands run from the plugin directory, so their `./advisor.py` paths remain relocatable. `uv` must be on the host's executable search path.

## Wait for readiness

In the CLI, start without an initial prompt. Open `/mcp`, wait until Advisor is connected and shows `advisor_status`, `consult_advisor`, and `read_advice`, close the panel, then submit the task. An initial `--prompt-interactive` trial dispatched the task before MCP initialization and missed the early review; this package does not fix that host startup race.

The SessionStart hook uses Antigravity's `injectSteps` output to supply review instructions. It makes no model call. The worker must load the shared skill, choose an enabled advisor, and perform the consultation. Inspect native tool approvals before granting access; validation or a plugin-list row alone does not prove a connection.

## Configure and consult

Before starting the working session, run the shared wizard:

```sh
uv run --script /absolute/path/to/workspace/.agents/plugins/advisor/advisor.py configure
```

Check effective profiles and their source with `advisor_status`. Executable discovery does not establish authentication or model access.

Antigravity uses explicit context packets: include stable workspace/session/task IDs, the question, contract, actual source or diff, and test output. File paths alone do not transfer contents. Retrieve the original completed job with `read_advice` before dependent work. Poll using `poll_after_seconds` between independent tasks; automatic full-session capture, ZCode edit holds, and plugin completion push are not supplied.

## Tested boundary

CLI **1.4.2**, using working model `gemini-3.8-flash-low` in a disposable `accept-edits` session, naturally completed early/final Codex Sol Max consultations, retrieved both original results, used critique, and passed nine tests. All eleven bundle files remained unchanged. Its incomplete context packets limited final approval to provisional review.

Desktop **2.23.1** passed a fresh neutral task with the revised shared skill: original early/final reads, evaluated advice use, 11 independent tests, and no edits after final submission. It used an existing warm MCP transport; cold-start readiness remains unverified. An earlier continuation edited a test after final review and failed freshness. The revised rule explicitly covers such edits, but no post-submission edit occurred in the fresh retest, so that edge case remains unexercised. See [native acceptance](harness-acceptance.md#antigravity) for evidence and limits. The [native plugin](https://antigravity.google/docs/plugins), [MCP](https://antigravity.google/docs/mcp/), and [hook](https://antigravity.google/docs/hooks/) references describe the host formats.
