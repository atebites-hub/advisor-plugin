# Host settings verification

For current native task results, see [0.3.4 harness acceptance](harness-acceptance.md). Configuration, tool transport, and a completed consultation are separate checks. All advising calls in that work used Codex `gpt-6.1-sol` at `max`, with the Claude advising profile disabled.

Advisor 0.3.2 adds native settings declarations for Claude Code and Cursor. Both reuse the existing profile validator and default app overrides off. Installing these adapters preserves the shared configuration; enabling overrides replaces both complete profiles. ZCode retains its existing default of overrides on.

## Claude Code

The [plugin reference](https://code.claude.com/docs/en/plugins-reference) documents `userConfig`, `${user_config.KEY}` substitution, and replacement of a root `.mcp.json` server by a same-name inline manifest server. Advisor supplies the complete inline server, including all seven settings. Its neutral root `.mcp.json` is unchanged for other consumers. The effort option-picker feature is documented from Claude Code 2.1.271; the installed version tested was **2.1.301**.

No-inference checks on October 19, 2026:

- Strict package validation passed without warnings or errors.
- `plugin configure advisor@inline --values-stdin --json` accepted all seven settings in an isolated configuration directory. Test values explicitly disabled Claude and enabled `gpt-6.1-sol` at `max`.
- `mcp get plugin:advisor:advisor` connected the actual Advisor stdio server from the production package.
- A private package copy replaced only the launch command with an environment-recording wrapper. The real host resolved all seven strings correctly, including `"false"` for Claude enablement. The wrapper checked effective Advisor status, then connected the same shared stdio implementation. This verifies interpolation separately from the unmodified production command.

These commands inspect an inline package without installing it or requesting a Claude response:

```sh
claude plugin validate plugins/advisor --strict --json
claude --plugin-dir "$PWD/plugins/advisor" plugin configure advisor@inline --json
claude --plugin-dir "$PWD/plugins/advisor" mcp get plugin:advisor:advisor
```

The complete automated suite passes **279 tests on Python 3.11 and 3.12**, with resource warnings treated as errors. Ten new host-configuration tests cover declarations, opt-in precedence, disabled profiles, retained shared policy, and invalid or unresolved values. The script lock check also passes.

Those 0.3.2 checks did not test `/config` GUI use or a consultation lifecycle. The 0.3.4 source adds a native `SessionStart` hook that runs `advisor.py session-start` and supplies the complete checkpoint policy before the first tool. It does not call a model or block arbitrary edits. Run the documented `doctor` prerequisite before the first host session to resolve the runtime and dependencies. The hook has a ten-second timeout; cold-cache startup was not tested.

A fresh neutral CLI 2.1.301 task, using Opus 5.5 at Low as the working model, then completed three Codex Sol Max consultations, retrieved all original results, received native background-task completion notifications, and passed ten independently checked tests. An earlier production 0.3.3 trial completed the task while skipping consultation. The new trial establishes mechanics and observed triggering for that fixture; its completion reviews received summaries rather than literal source, so source-level approval remained limited. See [the acceptance report](harness-acceptance.md#claude-code).

The local Claude Desktop Code tab uses its own bundled version and requires separate acceptance. Ordinary Desktop chat requires a separate MCP configuration or MCPB package.

## Cursor

The [plugin reference](https://cursor.com/docs/reference/plugins) documents a `variables` JSON Schema and `${VAR}` interpolation. Advisor declares uppercase `ADVISOR_*` variables in its Cursor manifest and forwards them only through `.cursor-plugin/mcp.json`. Version 0.3.6 adds `ADVISOR_CURSOR_ENABLED`, `ADVISOR_CURSOR_MODEL`, and `ADVISOR_CURSOR_EFFORT`. Cursor Agent stays off unless that enabled value is `true`. The checks below record the earlier seven-variable package. Boolean controls use string enums `true`/`false` because boolean-to-environment serialization is undocumented.

Team administrators configure variables through dashboard **Plugins → Configure**. Individual GUI configuration remains unverified.

Version 0.3.7 points the Cursor manifest `hooks` field at `hooks/hooks-cursor.json`. `sessionStart` runs `uv run --script ./advisor.py session-start --hook-format cursor` from the plugin directory and prints `additional_context`. It does not call a model. Cursor CLI plugin hooks, including a package loaded with `--plugin-dir`, use that same file. The Desktop 3.24.18 and CLI 2026.10.18 sessions above predate this hook.

Cursor CLI **2026.10.18-ea085cb** loaded the unmodified production plugin and connected its actual MCP server. This build left absent manifest variables as literal placeholders instead of applying their declared defaults. Start shared-file mode explicitly:

```sh
ADVISOR_USE_APP_SETTINGS=false cursor-agent --plugin-dir /absolute/path/to/advisor/plugins/advisor
```

Use the absolute Cursor executable when another installed CLI also owns the name `agent`. Configure `~/.config/advisor/config.json` with the shared wizard first, then start a fresh Cursor session. Verify every profile and the configuration source with `advisor_status`. With the master switch explicitly false, unused profile placeholders are ignored; an unresolved master switch or incomplete opted-in profile still fails validation.

The native plugin launcher did not forward inherited custom `ADVISOR_CONFIG` or `ADVISOR_STATE_DIR`. Use the default shared file with this route; custom locations require a separately configured manual MCP server. Headless tool execution also needs an appropriate native approval policy: the tested `--force` option permitted tool calls for that disposable session, whereas `--approve-mcps` alone approved server startup only.

A neutral CLI task completed original early/final Sol Max reads, applied critique, and passed 13 independent fixture tests. It used an existing byte-identical shared skill from the normal Claude plugin cache, so this was not an empty-user-profile skill-discovery test. See [CLI acceptance](harness-acceptance.md#cursor-cli).

Desktop 3.24.18 separately completed a neutral task with original early/final reads, advice use, and 17 independent tests passing. Its local skill loaded from the new Cursor installation, while the app reused an imported byte-identical Claude-cache MCP server. Local-manifest-only MCP provenance and GUI variable editing remain unverified. See [Desktop acceptance and context limits](harness-acceptance.md#cursor-desktop).

## Other hosts

Use the shared file and guided `advisor.py configure` command until a host adapter is verified. ChatGPT's [structured settings extension](https://developers.openai.com/plugins/build/extensions) uses MCP read/update tools and server-owned persistence; it is not a manifest-to-launch-environment equivalent. Advisor does not expose a configuration-writing model tool.

The original portable Muse package discovers only skills; 0.3.3 adds a [native export](muse-integration.md) for MCP and startup instructions. Version 0.3.4 adds a distinct [Antigravity export](antigravity-integration.md); actual CLI runtime verified its relative MCP/hook paths and plugin working directory. Grok completed native consultations using the Claude-compatible package and shared configuration; its native settings interpolation remains undocumented. None of these routes supplies ZCode's full-session capture or edit holds. See [host compatibility](compatibility.md) and [native acceptance](harness-acceptance.md).

## 0.3.3 OpenAI onboarding

No-inference checks on October 19, 2026 used Codex CLI **0.162.1** with an isolated configuration directory. Its app-server discovered the local marketplace, installed Advisor, and reported both enabled skills, one MCP server, and the resolved `advisor:advisor-setup` onboarding entry. Installed manifests and skills matched the source bytes. No model turn was started and the normal profile was unchanged.

This verifies installation and onboarding metadata. It does not establish a GUI setup conversation, an interactive wizard save, or host-routed tool use. The shared wizard remains the configuration writer; there is no new configuration-writing model tool or structured ChatGPT settings panel.

## 0.3.3 Muse native export

No-inference checks on October 19, 2026 used **Muse Code 1.4.9** with fresh isolated XDG directories. Native validation reported two skills, one SessionStart hook, one MCP server, and no diagnostics. Installation copied all nine exported files unchanged. After approval, the private installation source was moved away.

- Two installed hook fixtures completed with exit code 0 and supplied the startup policy.
- Two sessions using Muse's deterministic echo provider exposed both skills and the enabled hook. Native Muse processes launched `uv` and Python against the installed cached `advisor.py`, independently of the original source path.
- A separate official MCP SDK client initialized the installed server, listed all three tools, and read effective profiles: Claude disabled; Codex `gpt-6.1-sol` at `max` enabled.
- All nine file hashes and the recursive directory inventory remained unchanged after hooks, sessions, SDK requests, and shutdown, without Python bytecode environment overrides. Final inspection remained valid and active with no package or capability diagnostics.

This closes an observed approval-digest failure caused by runtime bytecode writes. The fixed entry point suppresses those writes; existing changed experimental caches require a fresh export and installation. All **293 automated tests pass on Python 3.11 and 3.12**, with resource warnings treated as errors; the script lock check and Claude/ZCode package validators also pass.

No model turn was requested in that initial 0.3.3 check. A later native Muse 1.4.9 TUI `/mcp` check reported `plugin:advisor:advisor` connected with `advisor_status`, `consult_advisor`, and `read_advice`; this closes the native-connection evidence gap despite the separate `mcpServer/list` projection still returning an empty array.

One authorized working-model request to `muse-spark-1.3-contributor` failed before output with HTTP 402 `billing_error`: “Billing verification failed. Please check your payment method.” It produced no tool calls, advice jobs, or edits. That request did not carry the private test installation's capability override; a subsequent no-inference TUI check used the corrected approval arrangement and verified the connection. Neither check establishes a successful host-routed consultation. No payment information, credentials, or normal settings were changed. Automatic advice use, GUI setup, full transcript capture, edit holds, and completion notifications remain unverified.

All live advice requested during this integration work used **Codex CLI, `gpt-6.1-sol`, Max effort**. Configuration checks and automated tests made no model calls. Private test settings, provider sessions, and advice remain outside Git.
