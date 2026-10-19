# Host compatibility

**0.3.4 adds native Antigravity packaging and Claude SessionStart instructions.** Native Grok, Antigravity CLI, Claude Code, Codex CLI, and Cursor CLI trials requested advice without an Advisor-specific task prompt, retrieved the original completed results before dependent edits, used critique, and ran tests. Claude and Antigravity reviews had incomplete supplied context, so these establish consultation mechanics rather than unconditional source-review approval. Muse connected all three tools, but its working model was blocked by account billing. A fresh Antigravity Desktop warm-session trial passed original reads, advice use, and final-review freshness after a shared-instruction clarification. Its earlier failure and cold-start/invalidation limits remain recorded. Desktop results are tracked separately. See [native acceptance and limits](harness-acceptance.md) and the [Antigravity guide](antigravity-integration.md).

The 0.3.4 source suite passes **304 tests on Python 3.11 and 3.12**, with resource warnings treated as errors. Live trials used the exact package/source revisions listed in the acceptance report; the version label alone does not establish a fresh installation.

## Historical integration evidence

**0.3.3 adds a native Muse export and OpenAI setup onboarding.** Muse 1.4.9 passed isolated install, approval, startup-hook, cached-process launch, and package-integrity checks; a separate SDK client verified the installed MCP server. Codex CLI 0.162.1 discovered both skills, MCP, and onboarding metadata. Host-routed Muse tool use and GUI setup remain unverified. All 293 tests pass on Python 3.11 and 3.12. See [versioned verification](host-settings.md#033-openai-onboarding).

**0.3.1 native configuration is installed and package-verified in ZCode 3.16.1.** A directed 0.3.0 session discovered GUI-selected Astra Max, completed and retrieved two reviews, used their critique, and finished with six unchanged tests passing. A neutral small-task attempt skipped consultation, so unprompted triggering is not established. All 269 plugin tests pass on Python 3.11 and 3.12. See the [versioned test report](zcode-smoke-test.md#031-configurable-advisors-october-19-2026).

**0.2.10 installation and the native Claude advice lifecycle passed.** All twelve packaged files matched source; 148 plugin tests and the lock check passed. A neutral read-only UX task independently requested two Claude reviews, waited, retrieved both original results, and applied critique before finishing. Its 490-word specification plus preamble exceeded the full-response limit at 511 words. This is a lifecycle check, with that output-format miss; see the [test report](zcode-smoke-test.md). Every new native ZCode consultation requires full recording. A separately authorized historical check verified full retention at 91 messages with Desktop recording enabled; each installation needs its own consent and readiness check. Advisor checks each consultation's bound record but never writes global host settings.

**0.2.9 installation and fresh native ZCode Desktop acceptance passed.** All twelve packaged files matched source; 145 plugin tests and the lock check passed. From a plain coding prompt, GLM-5.3-Flash (Max requested) independently completed three Codex reviews with exact waiters, idle wakes, original-job reads, dependent-edit ordering, and actual critique use. A fresh final approval followed the last workspace edit, and the worker finished with seven passing fixture tests. A complete 75-message consultation and an 87-message full-retention status check passed during an approved test; full recording was restored OFF. This verifies the tested fixture on Desktop, not every task or host. See the [test report](zcode-smoke-test.md).

Native requests require concrete `dependent_paths` (`[]` only for read-only advice) and hold overlapping named edits until the exact completed native read. Literal bracketed paths are accepted; symlink loops fail with JSON denials. Native reads can repair persisted snapshot/attempt attachments for the exact selected call without another provider call or clearing unrelated holds. Shell/delegation remains policy-only. Earlier directed Claude fresh/resume evidence came from an existing 0.2.7 process retained across a 0.2.8 package update; it is distinct from the fresh 0.2.9 Codex acceptance.

Historical verification through 0.2.6: host documentation checked on October 15, 2026; ZCode behavior retested on October 16. **Advisor 0.2.6 installation is verified, with 113 automated tests and the lock check passing.** All twelve packaged files match source, and a fresh session exposes the updated tool definition. A directed trial passed active completion alert, retrieval, evaluated use, and a correct reactive finish; a replay also proved independent editing while pending and dependent-work deferral. A third read-only trial passed clean idle wake and later-turn retrieval without cloning review credit. The earlier 0.2.2 **ZCode 3.15.3.8237 / GLM-5.3 Max** task independently requested and retrieved two Codex reviews and applied their findings; independent tests passed. A required third review failed on retained host-log context, so the task was stopped before final acceptance. Live handling of the unavailable result introduced in 0.2.3 and other host installations remain untested. See the [versioned smoke-test report](zcode-smoke-test.md); a documented contract does not establish a passing installation.

## Consultation behavior

Advisor asks the working agent to consult after brief orientation and before substantive implementation or committing to an approach. Longer, multistep tasks require an early review and a final review after saving the deliverable and running tests, before claiming completion. Recurring errors, approach changes, and consequential uncertainty also call for review; trivial reactive tasks need no repeated reviews. ZCode, Claude Code, and the native Antigravity/Muse exports supply startup instructions without consulting a model. Other routes can use the [instruction snippet](agent-instructions.md). The model invokes the tool; no failure counter or confidence score schedules calls.

Version 0.2.6 removes the blanket initial edit gate and adds unread-result reminders after tool success/failure. The worker starts early reviews, then launches the returned `completion_watcher.input` once through native `Bash` with `run_in_background: true`; completion alerts the active agent at a model boundary or wakes it when idle. Independent work can continue, but dependent work awaits completed retrieval and evaluation. A verified running waiter permits explicit pending/incomplete yield, never a completion claim. Fresh final review remains worker policy after edits, including across idle wakes; receipts credit only their original turn. Claude Code native background-task notifications were also observed in the later [0.3.4 acceptance work](harness-acceptance.md#claude-code); other hosts' push delivery remains unverified. Tests, installation, and a directed active-alert/advice-use finish pass; a replay also proved independent editing while pending and dependent-work deferral. A third read-only trial passed clean idle wake and later-turn retrieval without cloning review credit. See the [hook contract](agent-instructions.md).

The host and advisor provider are separate choices. Every host connects to the same local MCP service. Users configure enabled/model/effort settings for `claude` (Claude Code CLI) and `codex` (Codex CLI). Defaults remain Claude Opus 5.5 Max (`claude-opus-5-5`) and GPT 6.1 Sol Max (`gpt-6.1-sol`). The working agent queries `advisor_status` and explicitly chooses **one enabled** provider; it cannot override the user's model or effort. Opt-in verified-usage handoff permits the other enabled, configured profile once within the same job. The host need not offer that model itself. Requested settings do not establish CLI/account access or independently verify the served identity.

## All requested hosts

| Host | Documented route and supplied integration | Current limit |
| --- | --- | --- |
| Cursor desktop | Native Cursor package and automatic Claude-plugin import. [Plugin reference](https://cursor.com/docs/reference/plugins) | Desktop 3.24.18 completed early/final original reads, advice use, and 17 fixture tests. Local skill loaded; MCP reused a byte-identical imported Claude cache. Local-only MCP launch and GUI variables remain unverified. |
| ZCode | `.zcode-plugin/plugin.json` with shared skill, stdio MCP, native context adapter, and startup/edit/post-tool/Stop hooks. [Plugins](https://zcode.z.ai/en/docs/plugin) | 0.3.1 GUI controls installed; directed Astra Max lifecycle verified on 0.3.0. Earlier natural trials remain separate. Every new native consultation requires verified full retention; standalone CLI 0.16.9 lacked a supported override. Git-source installation and dependable unprompted triggering remain unverified. |
| ChatGPT/Codex desktop app | Portable plugin manifest, `mcp.json`, `.agents/plugins/marketplace.json`, and onboarding to `advisor-setup`. [OpenAI plugins](https://developers.openai.com/plugins/build/plugins) | Actual native status, consultation, and completed retrieval work in the tested local Codex thread. Neutral task acceptance and GUI setup remain separate; ordinary cloud chat cannot be assumed to start local CLIs. |
| Claude desktop app | Its **Code tab**, when using the local Claude Code environment, supports Claude plugins. Ordinary desktop chat uses local MCP configuration or MCPB extensions. [Code tab](https://code.claude.com/docs/en/desktop), [desktop MCP](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) | Public marketplace discovery is verified; local MCP trust approval and a desktop task are separate acceptance gates. CLI evidence does not cover the bundled desktop version. No MCPB supplied. |
| Antigravity Desktop | Native workspace bundle from `scripts/export_antigravity.py`. [Guide](antigravity-integration.md) | Desktop 2.23.1 fresh warm-session task completed original early/final reads and advice use with 11 tests passing and no post-submission edits. Cold startup and post-review-edit invalidation remain unproven; an earlier freshness failure is preserved. |
| Muse Code | Export a native bundle with `scripts/export_muse.py`; it declares both skills, one SessionStart hook, and the shared stdio MCP server. [Muse guide](muse-integration.md), [format compatibility](https://meta-models.github.io/muse-code-sdk/next/guides/plugins/concepts/compatibility/) | Muse 1.4.9 TUI connected all three tools. The working-model request failed with HTTP 402 billing verification before output, so host-routed advice use remains unverified. Portable source alone loads only skills. |
| Antigravity CLI | Native workspace package from `scripts/export_antigravity.py`; wait for `/mcp` readiness before submitting the task. [Guide](antigravity-integration.md) | CLI 1.4.2 completed early/final consultation and original reads, used advice, and passed nine fixture tests. Startup race and supplied-context limits remain. |
| Grok Build CLI | Reuses the Claude plugin and marketplace. [Skills, plugins, marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces) | CLI 1.0.52 completed natural early/final reviews, original reads, advice use, and 16 fixture tests. Restrictive host sandboxing can prevent the advising CLI from initializing. |
| Cursor CLI | Load the package with explicit shared-file mode; see [settings](host-settings.md#cursor). [CLI parameters](https://cursor.com/docs/cli/reference/parameters) | Build 2026.10.18-ea085cb completed natural early/final reviews, original reads, advice use, and 13 fixture tests. This build requires explicit shared-file mode; GUI variables remain unverified. |
| Codex CLI | Portable plugin, OpenAI marketplace descriptor, and `advisor-setup` onboarding. [OpenAI plugins](https://developers.openai.com/plugins/build/plugins) | CLI 0.162.1 completed natural early/final reviews, original reads, advice use, and six fixture tests. Headless approval policy must permit the three tools. GUI onboarding is separate. |
| Claude Code | Native `.claude-plugin/plugin.json`, inline MCP settings, SessionStart instructions, shared skills, and marketplace. [Plugin reference](https://code.claude.com/docs/en/plugins-reference), [marketplaces](https://code.claude.com/docs/en/plugin-marketplaces) | CLI 2.1.301 completed natural early/final reviews, native notifications, original reads, advice use, and ten fixture tests. Completion packets contained summaries, limiting source-review approval. |

## Advisor configuration

Plugin configuration UIs exist, but their schemas and execution surfaces differ:

| Host | Documented native configuration route | Advisor support in this change |
| --- | --- | --- |
| ZCode | Plugin `userConfig` fields in Settings → Plugins → Advisor → Advanced details → Configuration. [Configuration](https://zcode.z.ai/en/docs/plugin#configure-plugins) | Enabled/model/effort controls for both providers, plus `use_app_settings`. |
| ChatGPT | A Plugin settings extension exposes product-specific settings inside ChatGPT. [Extensions](https://developers.openai.com/plugins/build/extensions) | Advisor supplies onboarding to the shared wizard; a structured settings panel is deferred. UI-only tool visibility is not treated as authorization to write local configuration. |
| Claude Code | Plugin `userConfig` exposes fields in `/config`, including boolean switches and effort option pickers. [Reference](https://code.claude.com/docs/en/plugins-reference) | Seven controls and a complete inline MCP definition; overrides default off. The option-picker feature is documented from 2.1.271. Ordinary Claude Desktop chat is a separate surface. |
| Cursor | Plugin `variables` schema; team administrators configure values from the Plugins dashboard. [Reference](https://cursor.com/docs/reference/plugins) | Seven uppercase `ADVISOR_*` controls forwarded through Cursor's MCP file. Boolean choices are strings. The tested CLI requires explicit `ADVISOR_USE_APP_SETTINGS=false` for shared-file mode; GUI controls remain unverified. |

In ZCode, `use_app_settings` defaults to true: `claude_enabled`, `claude_model`, `claude_effort`, and matching `codex_*` values override the shared file's advisor profiles. Turn it off to use shared profiles and defaults. Save, then start a fresh session if the existing MCP process retains old values. Verify effective settings with `advisor_status`; package installation alone does not verify a configured consultation.

Claude Code and Cursor manifests declare app overrides off, preserving shared disabled providers when the host resolves that setting. The tested Cursor CLI requires the explicit launch value below. Enabling their master switch replaces both complete profiles; inspect both enabled flags first. Claude uses lower-case `userConfig` names; Cursor uses uppercase environment names and `true`/`false` string choices. Their host-specific placeholders never enter the neutral portable MCP files. Existing jobs retain their frozen configuration. See [settings verification](host-settings.md).

For the tested Cursor CLI, launch `ADVISOR_USE_APP_SETTINGS=false cursor-agent --plugin-dir /absolute/path/to/advisor/plugins/advisor`. This uses the default shared file; its native plugin launcher did not forward custom `ADVISOR_CONFIG` or `ADVISOR_STATE_DIR`. See [Cursor details](host-settings.md#cursor).

The shared setup works through the existing MCP service: run `uv run --script plugins/advisor/advisor.py configure`, or edit `~/.config/advisor/config.json`. `configure --config /absolute/path/advisor.json` writes another file; set `ADVISOR_CONFIG` on the MCP process to load it. Timeouts, budgets, and handoff permission stay in the shared file even when an app controls the profiles. See [examples and precedence](../README.md#configure-advisors). ChatGPT's native settings adapter remains deferred; tested local tool use is listed separately above.

Muse native plugin processes remove custom `ADVISOR_*` environment variables. Use the default shared configuration file for that route; custom environment-based configuration requires its manual MCP settings route. Its setup skill does not add a native settings GUI. Always compare the effective `advisor_status` source with the intended file.

Only enabled profiles may receive new calls or quota handoffs. With both disabled, report required reviews incomplete rather than claiming approval. Existing jobs retain their frozen settings and remain readable after configuration changes. Efforts are validated against `low`, `medium`, `high`, `xhigh`, and `max`; provider/account support still needs verification.

## Installation routes

The public marketplace source is [atebites-hub/advisor-plugin](https://github.com/atebites-hub/advisor-plugin). Clone it with `git clone https://github.com/atebites-hub/advisor-plugin.git`. The repository name is `advisor-plugin`; the catalog and plugin IDs remain `advisor`.

Claude Code also supports the [documented GitHub marketplace route](https://code.claude.com/docs/en/plugins/host-marketplace#host-your-marketplace):

```text
/plugin marketplace add atebites-hub/advisor-plugin
/plugin install advisor@advisor
```

Claude Desktop discovered the public GitHub marketplace and Advisor 0.3.3; discovery does not complete its local MCP trust prompt or task acceptance. The previously tested ZCode route uses a local checkout.

Start with a checkout of this repository and `uv` on the host's executable search path. Keep that checkout available when using manual MCP configuration. Merge settings with existing configuration instead of replacing it.

Claude Code, including the local Claude Desktop Code tab:

```text
/plugin marketplace add /absolute/path/to/advisor
/plugin install advisor@advisor
```

Codex CLI's tested local marketplace route is:

```sh
codex plugin marketplace add /absolute/path/to/advisor --json
codex plugin add advisor@advisor --json
```

For Cursor's plugin-capable surfaces, use the marketplace interface to add this repository/local marketplace, then install its only plugin, `advisor`. Cursor CLI requires the explicit shared-file launch above; use the absolute Cursor executable if another host also installs a command named `agent`. For OpenAI surfaces, add the local repository through the plugin marketplace interface supported by the installed build. For Grok, use `/plugins` and its Marketplace tab to register the repository; inspect the discovered package before enabling it. These are host installation steps, not commands Advisor executes.

In ZCode 3.15.3.8237, use **Plugin Marketplace → Add → Add plugin marketplace**, enter this checkout's directory, then install **Advisor** under **Personal**. Local catalog discovery, the skill, and the MCP server were verified in that build. Refresh the marketplace before checking for updates; use a fresh native session to load changed hooks and MCP definitions. Existing tasks may retain the previous MCP process after package replacement. Labels may differ in other builds. The manual MCP route below is separate from marketplace discovery.

For every new native ZCode consultation in 0.2.10, enable Desktop **Settings → General → Keep complete model I/O**. Obtain user approval unless already authorized and leave approved recording enabled. This bypasses normal tail retention and size/rotation limits, retaining app-wide unbounded logs including native reasoning across open/future sessions and workspaces. Advisor never changes the setting. Standalone CLI **0.16.9 does not inherit the Desktop toggle** and has no supported full-retention override, so it cannot start new native consultations. Check MCP `advisor_status.native_context`: only observed `full_retention` yields `long_session_ready: true`, and consultation rechecks its own record. Bounded/unknown readiness errors create no snapshot, job, or path hold; status and existing advice retrieval still work. CLI `doctor` remains an executable check. The 0.2.9 test's OFF restoration was verified at that time; a later authorized test verified full retention at 91 messages with recording enabled. These observations do not establish the setting in another installation.

On the tested installation, native model-I/O files use `0644` permissions and directories `0755`. Header/media sanitization still runs, but native reasoning remains. Advisor's sanitized copies use `0600` files and `0700` directories; those protections do not change native logs. See the [context-transfer contract](context-transfer.md).

Muse needs the native export to activate the MCP server and startup hook:

```sh
uv run --python 3.11 python scripts/export_muse.py /absolute/new/advisor-muse
muse plugins validate /absolute/new/advisor-muse --json
muse plugins install /absolute/new/advisor-muse --scope user
```

Use an existing real parent directory and a new destination outside this repository. Only use the bundle after the exporter exits successfully; failed writes leave partial output for inspection. Inspect and approve capabilities through Muse before starting a fresh session. See [the Muse guide](muse-integration.md) for configuration and verification limits. Installing the original portable source directly still loads only skills.

Antigravity also needs its [native export](antigravity-integration.md) for packaged startup instructions and MCP.

If you install the original portable source in Muse instead, configure MCP separately using the manual route below. Its native overlay cannot override the authoritative portable root manifest. [Import rules](https://meta-models.github.io/muse-code-sdk/next/guides/plugins/concepts/compatibility/)

## Manual MCP setup

Use the following server definition, replacing the script path and, if necessary, `uv` with absolute executable paths:

```json
{
  "mcpServers": {
    "advisor": {
      "command": "uv",
      "args": [
        "run",
        "--script",
        "/absolute/path/to/advisor/plugins/advisor/advisor.py",
        "serve"
      ]
    }
  }
}
```

- **Antigravity app/CLI:** merge into `~/.gemini/config/mcp_config.json` or the project's `.agents/mcp_config.json`; inspect the server in the app's Customizations settings or CLI `/mcp`. [Configuration reference](https://antigravity.google/docs/mcp/)
- **Muse Code:** merge into the project's `.mcp.json` in a trusted workspace, or the `mcpServers` section of `~/.config/muse/settings.json`. A newly created user settings file must also contain `"schema_version": 1`; project `.mcp.json` does not use that field. Restart the process after changes. [Muse MCP settings](https://meta-models.github.io/muse-code-sdk/next/guides/extend/mcp-servers/)
- **ZCode:** its native project `.zcode/config.json` uses `mcp.servers` rather than `mcpServers`; put the same `advisor` server object there. Alternatively use `.agents/mcp.json` with the JSON above when no native MCP servers override it. [ZCode MCP](https://zcode.z.ai/en/docs/mcp-services)
- **Ordinary Claude Desktop chat:** merge into the application's local MCP configuration using its documented developer settings; this is separate from installing a Code-tab plugin. [Desktop instructions](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)

On manual integrations, install the skill using the host's supported skills directory and add the [startup rule](agent-instructions.md) to the working agent's instructions. An MCP connection alone does not enforce skill execution. Hosts without the native ZCode metadata contract still require the working agent to supply context explicitly.

## Hook and context boundaries

MCP `advisor_status` uses `readOnlyHint=False` to finalize the generating native record before checking its exact bound invocation; it makes no model call or context copy. This scheduling barrier is also used by consultation and native retrieval. It is not an OS write sandbox.

Claude advising now receives a private child `CLAUDE_CODE_TMPDIR`. A network-denied native probe isolated the shared-temp failure; a directed 0.2.7 fresh/resume trial then completed real Claude advice, native idle wake, retrieval and evaluated use. Both calls exceeded 300 seconds. This is separate from the fresh 0.2.9 Codex coding trial and its long-context final review; it does not establish equivalent Claude coverage for every task.

Hook schemas differ by host. ZCode accepts structured context output; Antigravity uses `injectSteps`; Grok ignores stdout on passive lifecycle events. Claude Code uses its native `SessionStart` registration. Do not copy a hook configuration between them or treat a reminder as a consultation. [ZCode hooks](https://zcode.z.ai/en/docs/hooks), [Antigravity hooks](https://antigravity.google/docs/hooks/), [Grok hooks](https://docs.x.ai/build/features/hooks)

Advisor 0.2.0 captures ZCode's current semantic model input using native MCP request metadata: system instructions, retained messages, tool definitions, calls/results, and visible current-response text. It checks the native session/workspace index and matches the turn and exact consultation arguments, then saves a hashed private snapshot with coverage information. Missing, partial, or ambiguous current input fails; no older turn is substituted and no host source is edited. See the [context-transfer contract](context-transfer.md).

Discarded history before host compaction cannot be recovered. Protected reasoning, credential headers, and unrelated sessions are excluded. This is a semantic snapshot, not an identical provider wire request. Other hosts retain explicit manual context packets. The [acceptance report](harness-acceptance.md) distinguishes tested consultation mechanics from context quality; no full-session adapter is supplied for those hosts.

The default is a 1,200-second observable-progress idle timeout with no total deadline; explicit `timeout_seconds` remains absolute. Effort uses the user's profile, defaulting to Max. Silent models can still hit the idle limit. Jobs freeze settings, retain legacy numeric deadlines, and bound worker/cleanup failures; watchers follow original terminal status. Manual input is limited to 1 MiB and assembled context to 8 MiB; a CLI can impose a smaller limit. In the 0.2.1 live trial, Codex rejected 1,226,163 input characters against its 1,048,576-character ceiling. Capture retains at most 32 MiB stdout and 4 KiB stderr; progress excludes protected content. Only user-enabled verified account-exhaustion handoff is automatic; timeouts, authentication, generic rate limits, and ambiguous evidence never switch. See [usage handoff](usage-fallback.md). Authentication, model availability, and advice application remain external to this matrix.

The 0.2.2 Codex transport loads the adviser instructions and full quoted JSON packet through the native `model_instructions_file` setting, using a `0600` file in an isolated `0700` temporary directory. Stdin carries the actual question. It preserves Max effort, ignored user configuration, feature isolation, and native history without summarizing context or enabling tools. This provider-side change does not add transcript adapters for other hosts.

A controlled Codex consultation completed; initial native base instructions exactly matched the intended **1,224,533 bytes / 1,223,689 characters**. A same-session follow-up verified retained history and refreshed context; no byte-exact resumed-record comparison is claimed. A controlled Claude consultation also completed with its full **1,224,538-byte** input verified in native history. Both used source, contract, test, and schema evidence absent from their questions.

An installed-0.2.9 two-call canary also verified new context on same-session Codex resume, with the new value present only in the replacement instructions file. Native journal metadata retains the initial instructions rather than updated resume overrides; it cannot establish a byte-exact resumed full-packet match. The fresh coding trial's initial native base instructions matched **1,231,352 bytes**, and later reviews used newly supplied source/test/note evidence.

The autonomous 0.2.2 early-review input independently matched all **1,234,717 bytes** in the native Codex base instructions. Two completed reviews led to tested changes. Later, the adapter rejected a current log record containing only 64 of 80 messages, preventing the required fresh post-fix review. The proposed manual fallback was denied before invocation. No tail stitching, host-source edit, or global recording change was used in that stopped trial. Its outcome is unchanged by the later 0.2.9 acceptance. See the [transport contract](context-transfer.md) and [trial report](zcode-smoke-test.md).

The 0.2.3 source returns a structured `unavailable` result for verified incomplete native history, such as a tail/delta without a complete baseline, with `provider_started: false`, `review_complete: false`, and no job ID. A current-revision final-attempt marker permits truthful incomplete-review reporting, never a completed receipt or permission for advice-dependent work; later admitted edits invalidate it. Invalid or unverified requests remain errors. In 0.2.10, complete bounded/unknown recording records instead produce a readiness error before snapshot, job, or hold creation; enable recording with approval and make a new full request. Genuine unavailable-history holds remain intact. Manual CLI packets, older snapshots, invented IDs, retries, and provider switching must not replace failed native capture. Manual/non-native CLI integration remains supported separately.

All 96 tests and the lock check passed for this handling, with resource warnings treated as errors. Version 0.2.3 was installed through marketplace Refresh and Update; all twelve packaged files matched source, and its 7,975-byte skill fit the 8,000-byte host budget. Live unavailable-response/Stop behavior remains untested. Installation alone did not recover missing context or establish final-review acceptance.

Version 0.2.4 added rejection of Codex output after terminal completion, with two new table-driven cases and the same 96 passing tests plus lock check. Marketplace installation was verified: all twelve packaged files matched source and the skill remained 7,975 bytes. Complete final-review acceptance was unverified at that release.

Version 0.2.5 splits both providers' JSONL on LF, preserving Unicode separators inside JSON strings and accepting blank lines. All 97 tests and strict resource-warning/lock checks pass. Fresh and same-session resume checks with Codex CLI 0.162.1 passed the terminal guard, retained prior question memory, and used refreshed context. Marketplace installation is verified with all twelve packaged files matching source and the skill at 7,975 bytes. This does not establish live native unavailable-response handling or full final acceptance.
