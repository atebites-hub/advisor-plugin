# Advisor

Advisor gives a coding agent an independent review at planning, recovery, and completion checkpoints. This repository is a marketplace containing exactly one plugin: **advisor**.

Users enable the advisors the working agent may choose, with one model and effort setting per CLI. The defaults are:

| Provider | Requested model | Effort | Runtime | Default |
| --- | --- | --- | --- | --- |
| `claude` | Claude Opus 5.5 (`claude-opus-5-5`) | Max | Claude Code CLI | enabled |
| `codex` | GPT 6.1 Sol (`gpt-6.1-sol`) | Max | Codex CLI | enabled |
| `cursor` | Claude Opus 5.5 High (`claude-opus-5-5-high`) | High | Cursor Agent CLI (`cursor-agent`) | disabled |

The working agent checks `advisor_status` and chooses one enabled advisor per consultation. User-supplied workflow preferences favor `claude` for frontend, design, UX, planning, delegation, and orchestration, and `codex` for engineering, backend, architecture, mathematics, implementation, testing, and optimization. Choose `cursor` when that profile is enabled and the question depends on Cursor's agent or CLI. These are soft selection preferences, not benchmarked rankings, and never override disabled settings.

Claude and Codex defaults follow the [Claude CLI reference](https://code.claude.com/docs/en/cli-reference), [Opus 5.5 documentation](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide), and [Codex model documentation](https://learn.chatgpt.com/docs/models). The Cursor id is the catalog entry reported by `agent models` on CLI 2026.10.22; Cursor encodes effort in that id and has no separate effort flag, so `effort` must match the suffix. Each consultation starts with one explicitly selected provider. Optional verified-usage handoff can try the other enabled profile once, and only between Claude and Codex. Cursor is never that alternate. Responses identify the requested model and effort; they do not prove model access or independently verify the served identity. An omitted `cursor` profile stays disabled, so installing this version does not start Cursor Agent consultations by itself.

## How it works

1. After brief orientation, the working agent loads the Advisor skill and consults before substantive implementation or committing to an approach.
2. For longer, multistep tasks, it consults again after saving the deliverable and running tests, before declaring completion. Recurring errors, approach changes, and consequential uncertainty also call for review. Trivial reactive tasks need no repeated reviews.
3. The local MCP tool starts a background job using the selected advising CLI's separate session. In ZCode, the worker immediately starts its returned native background waiter and continues independent work.
4. ZCode alerts the agent at a model boundary or wakes it when idle. The worker promptly retrieves completed advice with `read_advice` before making dependent decisions; a Markdown copy stays in private local state.
5. The working agent evaluates the advice, verifies its decisions, and continues its own task.

**ZCode, Claude Code, Cursor, and local Codex packages include session-start hooks** that put review checkpoints into the worker's context. The native Muse and Antigravity exports also declare startup instruction hooks. These hooks only supply instructions; they never call an advisor. The working agent must invoke the tool and complete the reviews. Grok Build ignores stdout on passive lifecycle events. Ordinary Claude Desktop chat, ordinary ChatGPT cloud chat, a portable Muse install, and Cursor cloud agents have no instruction hook. Those hosts can use the [startup instruction snippet](docs/agent-instructions.md) in their project or user instructions. Installing an MCP tool or a skill alone does not guarantee the full rule is loaded.

Version 0.2.9 requires native ZCode requests to declare `dependent_paths`: concrete workspace files or directories awaiting advice; use `[]` only for read-only advice. Named-edit hooks hold those paths across turns until the exact job's completed advice is retrieved through native `read_advice`. Failed, unavailable, and completed-but-unread results do not release them. Independent named edits remain allowed; shell commands, delegation, and semantic decisions remain policy-only boundaries. Early/final review and waiter rules still apply. See [checkpoint details](docs/agent-instructions.md).

## Set up

Install [uv](https://docs.astral.sh/uv/) and the advising CLIs you want to use, then sign in through their normal login flows. For Cursor Agent, use the `cursor-agent` executable (`agent` can name a different tool). Advisor does not copy credentials or call model APIs directly. It removes `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CODEX_API_KEY`, and `CURSOR_API_KEY` from child environments to favor existing CLI authentication; confirm each CLI's active account and billing mode yourself.

Clone the [Advisor plugin marketplace](https://github.com/atebites-hub/advisor-plugin) and check the local prerequisites:

```sh
git clone https://github.com/atebites-hub/advisor-plugin.git
cd advisor-plugin
uv run --script plugins/advisor/advisor.py doctor
```

In Claude Code or the local Claude Desktop Code tab, add this GitHub marketplace and install its only plugin:

```text
/plugin marketplace add atebites-hub/advisor-plugin
/plugin install advisor@advisor
```

The GitHub repository is `advisor-plugin`; the marketplace and plugin IDs remain `advisor`. This follows the [documented GitHub marketplace route](https://code.claude.com/docs/en/plugins/host-marketplace#host-your-marketplace). For the tested ZCode route, clone the repository and add that checkout in Plugin Marketplace. See the [native acceptance report](docs/harness-acceptance.md) for versioned installation and agent-test results.

The first run resolves the locked MCP dependency and Python runtime. `doctor` checks executable availability; it does not verify authentication or model access. Native plugin support and manual MCP setup for **all 11 requested environments** are listed in [Host compatibility](docs/compatibility.md). Some hosts require manual MCP configuration rather than a native plugin import. Nothing is installed into those hosts automatically.

Muse Code needs a separate native bundle to activate MCP and its startup hook. Generate it from this checkout with `uv run --python 3.11 python scripts/export_muse.py /absolute/new/output`, then follow [Muse installation and verification](docs/muse-integration.md). The exporter copies only public runtime files and skills; it does not install anything or change user settings.

Antigravity Desktop and CLI use `uv run --python 3.11 python scripts/export_antigravity.py /absolute/new/output`. Follow [Antigravity installation](docs/antigravity-integration.md), including the CLI readiness check before submitting a task. Both exporters require a new destination outside this repository.

Before every new native ZCode consultation, call MCP `advisor_status` and require `native_context.recording_mode: "full_retention"`. From 0.2.10, consultation rechecks its own bound record. If the current history is complete but recording is `bounded` or `unknown`, a readiness error creates no snapshot, job, or dependency hold. Enable full recording with user approval unless already authorized, then make a new full request. Status and retrieval of existing advice remain available. `doctor` still checks executables only.

Desktop **Settings → General → Keep complete model I/O** requires the user's privacy consent: it creates app-wide unbounded logs across open and future sessions, including native reasoning. Leave approved recording enabled; Advisor checks the prerequisite but never writes global host settings. Standalone ZCode CLI **0.16.9 does not inherit the Desktop toggle** and has no supported full-retention override in the tested build, so 0.2.10 cannot start native consultations there. Native logs' observed `0644`/`0755` permissions differ from Advisor's sanitized `0600`/`0700` copies. See the [retention contract](docs/context-transfer.md).

The 0.2.9 Desktop acceptance test enabled full recording with permission, completed a **75-message** final consultation, and verified `full_retention` / `long_session_ready: true` at **87 messages**. The setting was then restored **OFF** and verified. A later, separately authorized check verified full retention at **91 messages** with recording enabled. These are historical test observations; every installation needs its own consent and readiness check, and every consultation verifies its own record.

## Configure advisors

The packaged `advisor-setup` skill guides configuration through the existing interactive wizard. Supported OpenAI local plugin surfaces also receive an onboarding entry point to that skill. It preserves known choices and reports setup pending when the host cannot expose interactive input. This is a setup workflow; a native ChatGPT settings panel is not supplied.

In ZCode, open **Settings → Plugins → Advisor → Advanced details → Configuration**. Keep `use_app_settings` enabled to use the plugin's controls: `claude_enabled`, `claude_model`, `claude_effort`, and the matching `codex_*` fields. Save configuration, then start a fresh session if the existing MCP process still reports the old values. `advisor_status` shows the effective enabled profiles without making a model call.

Claude Code exposes the same controls in `/config` through its [plugin `userConfig` support](https://code.claude.com/docs/en/plugins-reference). Cursor declares them as [plugin variables](https://cursor.com/docs/reference/plugins), configurable by team administrators from dashboard **Plugins → Configure**. Cursor uses the uppercase `ADVISOR_*` field names and string choices `true`/`false`. Individual Cursor and Cursor CLI configuration UIs remain unverified.

Cursor CLI requires an explicit mode because it does not apply the manifest's variable defaults. For the default shared configuration file, start a fresh session with `ADVISOR_USE_APP_SETTINGS=false cursor-agent --plugin-dir "/absolute/path/advisor-plugin/plugins/advisor"`. Its native plugin does not forward custom `ADVISOR_CONFIG` or `ADVISOR_STATE_DIR`; use manual MCP configuration for custom paths. Verify the CLI executable: another installed tool may also be named `agent`.

The new Claude and Cursor adapters default app overrides **off**, preserving shared settings on installation. Enable `use_app_settings` (Cursor: `ADVISOR_USE_APP_SETTINGS`) to replace every advisor profile with that app's complete set of controls, including enabled flags. ZCode retains its existing default of app overrides on. Review every profile before enabling overrides: Claude and Codex default on, and Cursor Agent defaults off.

Turn app overrides off to use the shared file and defaults instead. Timeouts, budgets, and `usage_fallback` always remain shared-file settings, and that file must still be valid. Restart the MCP connection or start a fresh session after saving environment-backed settings. `advisor_status` confirms the effective values without consulting a model. See [configuration verification and limits](docs/host-settings.md) and the [ZCode test report](docs/zcode-smoke-test.md).

For manual MCP integrations or shared setup, run the guided configuration command:

```sh
uv run --script plugins/advisor/advisor.py configure
# Or select a different file:
uv run --script plugins/advisor/advisor.py configure --config /absolute/path/advisor.json
```

The wizard previews every profile and asks before saving. It preserves unrelated settings. Run one wizard at a time; saves replace the file atomically but are not transactions between simultaneous writers. The default file is `~/.config/advisor/config.json`; `ADVISOR_CONFIG` selects another file for the MCP process or CLI. An explicitly selected missing file is an error when loading settings. For example, enable only GPT 6 Astra Max:

```json
{
  "advisors": {
    "claude": {"enabled": false},
    "codex": {"enabled": true, "model": "gpt-6-astra", "effort": "max"}
  }
}
```

Omitted fields retain the defaults above. Use explicit model identifiers rather than aliases; Claude identifiers must start with `claude-`. Effort accepts `low`, `medium`, `high`, `xhigh`, or `max`, subject to the installed provider and account. Configuring a value does not establish access or guarantee the provider will serve it. Agent requests select only `provider`; they cannot override the user's model or effort.

Disabling an advisor prevents new consultations with it and excludes it from usage handoff. If every advisor is disabled, no new advice can be requested; report required reviews incomplete. Cursor joins that list only after you set `"cursor": {"enabled": true}` with a catalog id whose suffix matches `effort`, for example `"model": "claude-opus-5-5-high", "effort": "high"`. Existing jobs keep their submitted profiles, and their results remain readable after settings change. Model or effort changes start separate consultation memory.

ChatGPT's structured settings protocol needs its own adapter; Advisor currently uses the shared file there. Other hosts can also use this shared setup. See [configuration by host](docs/compatibility.md#advisor-configuration).

## Request advice

The MCP tool is `consult_advisor`, with one `request` object. Choose one provider and state the review question. An accepted consultation returns a job ID promptly. In ZCode, immediately launch exactly one `completion_watcher.input` through its named `Bash` tool with `run_in_background: true`. Its completion notification prompts `read_advice(job_id)`; the waiter returns readiness only, never advice or a retrieval receipt. Continue independent work while waiting and hold dependent work until advice is retrieved and evaluated. Without a supported native waiter, poll after `poll_after_seconds`. Other hosts require polling unless their native background notifications are verified. Read the existing job after a host timeout rather than resubmitting it.

Native requests include the dependency declaration, for example:

```json
{"provider":"claude","dependent_paths":["app/[slug]/page.tsx","tests/renderer"],"stage":"before_task","question":"Review the proposed rendering change; README work is independent."}
```

Paths are literal: bracketed frontend routes are accepted, without wildcard expansion. Symlink loops in named-edit targets return a structured JSON denial. If job attachment fails after submission, read that existing job: its persisted native snapshot/attempt association, bound to the selected verified native call, repairs only the exact attachment without another provider call. Unrelated failed or no-job attempts remain held.

A genuinely incomplete native history, such as a tail/delta without a complete baseline, returns `status: "unavailable"`, `provider_started: false`, and `review_complete: false`, with **no job ID**. This differs from a repairable bounded/unknown recording-readiness error, which creates no snapshot, job, or path hold. Report the review incomplete; do not poll, retry, invoke a CLI manually, substitute older context or invented IDs, or switch providers. It provides no advice or permission for dependent work, and declared paths remain held. A truthful incomplete-review report is not a completed receipt or a dependency release.

In ZCode, Advisor 0.2.0 uses native request metadata to capture the current session's semantic model input: system instructions, retained messages, tool definitions, calls and results, and visible text already produced in the current response. It binds the snapshot to the native workspace, session, turn, and exact consultation arguments. Missing or ambiguous current input fails explicitly; it never substitutes an older turn. A hashed snapshot and coverage receipt stay in private state. No ZCode source changes are required. See the [context-transfer contract](docs/context-transfer.md).

Other hosts and direct CLI calls require an explicit context packet. Use `context` for the objective, history, approach, and constraints. In 0.3.5, use `context_files` to attach actual saved source, tests, contracts, and test output: Advisor reads and freezes those selected files before starting the consultation. Advising agents cannot open paths themselves or run checks. A summary or test-pass claim alone remains insufficient. ZCode retains its separate native snapshot contract and does not accept this option. See [selected-file transfer and limits](docs/context-transfer.md#selected-files-outside-zcode).

For manual consultations and nonnative integrations, the CLI accepts the same packet and waits for the completed result. It is not a fallback after native ZCode capture fails:

```sh
uv run --script plugins/advisor/advisor.py consult <<'JSON'
{
  "provider": "claude",
  "workspace": "/absolute/path/to/project",
  "host": "cursor",
  "session_id": "current-working-session",
  "task_id": "retry-design",
  "stage": "after_plan",
  "question": "Could this retry strategy duplicate an operation?",
  "context": "Review the retry design against the saved implementation, contract, tests and captured output. Include relevant history and approaches tried here.",
  "context_files": ["src/retry.py", "tests/test_retry.py", "README.md", "test-output.txt"]
}
JSON
```

Replace the example workspace and selected files with existing paths. `context_files` accepts 1–32 explicit workspace-relative regular UTF-8 files; it never expands globs or follows symlinks. Omit secrets. Secure attachment capture needs directory-descriptor/no-follow support; context-only requests remain available elsewhere. Use `provider: "codex"` for the user's enabled Codex profile. Preserve session and task IDs for follow-ups. ZCode defaults its task ID to the native session plus user turn; an explicit stable task ID remains supported. The [skill](plugins/advisor/skills/advisor/SKILL.md) defines every field.

The advising processes run in temporary directories with project configuration excluded. Claude has tools disabled and its child-only `CLAUDE_CODE_TMPDIR` points to that private directory, avoiding its shared `/tmp/claude-<uid>` startup path under host sandbox denials. Codex uses a read-only sandbox with shell, plugins, apps, hooks, subagents, global memories, browser, and computer-use features disabled. Cursor Agent is `cursor-agent --print --output-format stream-json --stream-partial-output --mode ask --sandbox enabled --trust`, with `--workspace` set to that private directory and no `--force`. `CURSOR_CONFIG_DIR` points at a private allowlist whose deny rules cover shell, read, write, web fetch, and MCP; a `tool_call` event rejects the advice. `CURSOR_API_KEY` is removed so the signed-in CLI login is used. This is Cursor's documented ask mode, headless behavior without `--force`, and permission denies. It is not Claude's empty tool list, and rules outside that private workspace can still load. Resume passes `--resume` with the result `session_id` and a new private directory. They advise from the supplied packet and, in ZCode, the bound native snapshot. No unrelated session is imported.

The 0.2.2 Codex transport uses `model_instructions_file`: adviser instructions and the complete quoted JSON packet are loaded as native base instructions from a private temporary file, while stdin carries the actual question. This avoids putting the full packet in one user message without summarizing it or enabling adviser tools. Controlled live checks verified complete Codex and Claude input, evidence-based advice, and Codex resume with refreshed context. Max effort and configuration isolation remain. See the [transport contract](docs/context-transfer.md) for verification and remaining history limits.

## Memory and limits

Native advising sessions retain their conversation history. Advisor stores response text, request fingerprints, and native session IDs in private per-task SQLite directories under `~/.local/state/advisor`. Workspace, host session, task, provider, model, and effort determine isolation. Identical packets with the same effective settings reuse cached advice. Native CLI history follows each provider's own retention rules.

Background requests and results are stored under the same private state root, including an `advice.md` file at the returned `advice_path`. This keeps long calls independent of a host's tool deadline. Do not commit this data or place it under version-controlled `docs/advice`; the repository's `docs/` contains contributor documentation.

If `CLAUDE_CODE_SKIP_PROMPT_HISTORY` disables Claude history, Advisor reports an error instead of overriding that privacy setting or pretending follow-ups can resume.

The defaults are **five successful consultations per task per advisor** and a **1,200-second observable-progress idle timeout**, with no implicit total deadline. Expected provider progress renews the idle timer; stderr, empty events, and unchanged snapshots do not. A silent model may still be working, especially with Codex's less frequent events. Manual input is limited to **1 MiB**, assembled context to **8 MiB**, without silent truncation. Provider CLIs can impose smaller limits; the 0.2.1 live trial exposed one.

Provider streams are drained with a **32 MiB stdout limit** and a **4 KiB stderr tail**. Pending results expose activity counts, elapsed time, and last activity; protected reasoning content is not persisted in progress or returned as advice. Activity does not extend the absolute deadline. Failed jobs retain their error and are never automatically relaunched; they may still consume provider quota. Process and pipe cleanup is bounded. An underlying CLI may retry internally. Optional usage handoff is described below; Advisor never restarts a failed job. Background calls survive host disconnects within their deadline. Common credential formats are redacted, but redaction is not exhaustive: callers must omit secrets.

Optional `~/.config/advisor/config.json`:

```json
{"idle_timeout_seconds": 1200, "max_consults_per_task": 5, "usage_fallback": false}
```

To impose a total deadline, add `"timeout_seconds": 1200`; progress never extends an explicit limit. Both timeout settings accept integers from 1 to 3600 seconds. Background jobs freeze settings at submission; changing configuration does not alter an existing job. Legacy jobs retain their numeric deadlines and previous implicit limit. Watchers observe the original job until terminal status; worker startup, lost progress heartbeats, and post-result process cleanup remain bounded.

Set `"usage_fallback": true` to authorize one switch to the other enabled, configured advisor after **verified account usage exhaustion**. This can send the frozen packet to both services sequentially and consume both accounts' allowances. The default is false; `advisor_status.usage_fallback.enabled` reports the setting. The same background job, snapshot, watcher, dependency hold, and explicit total deadline continue. `provider_attempts` preserves each requested model/effort, the original quota cause, and answering `provider`. Timeouts, authentication, generic 429s, ambiguous quota, local budgets, and context failures never switch. A disabled alternate is never launched; both exhausted means an incomplete review. See [detection and privacy limits](docs/usage-fallback.md).

`ADVISOR_CONFIG` and `ADVISOR_STATE_DIR` override the local paths. To discard plugin-side memory, remove the relevant state directory after active consultations finish; native CLI history must be removed separately. No vector database or shared memory across unrelated tasks is used.

## Develop and verify

```sh
uv run --python 3.11 --with 'mcp>=1.20,<2' python -m unittest discover -s tests -v
uv lock --check --script plugins/advisor/advisor.py
```

Tests cover consultation isolation, resume, deduplication, limits, validation, credential redaction, provider protocol handling, startup context, and an actual MCP stdio connection with background-job recovery after disconnect. Automated provider calls are simulated.

Version **0.2.10** passed installation and a fresh native Claude advice-lifecycle check: all twelve packaged files matched source, **148 plugin tests** and the lock check passed, and the 7,970-byte skill fit the host budget. From a neutral read-only UX prompt, GLM-5.3-Flash independently chose Claude for two reviews, launched the exact waiters, woke from idle, retrieved both original results, and applied concrete critique before finishing. The specification was 490 words, but an unnecessary preamble made the full response 511 words, missing the 500-word output limit. This verifies the advice lifecycle for that read-only task; the earlier engineering evidence remains versioned. See the [test report](docs/zcode-smoke-test.md).

Version **0.2.14** recognizes Claude's advancing hidden-thinking progress, with message/block watermarks that reject replayed totals. The **1,200-second idle limit** and optional absolute deadline remain unchanged. All **220 tests** passed on Python 3.11 and 3.12 with strict resource warnings; the lock check passed. A fresh directed ZCode session completed two uncached Claude reviews in the same advising session, waited for native alerts, retrieved both originals from `src/`, and used their advice before finishing naturally. The normal ZCode installation matches all **thirteen tested source files**. See the [versioned report](docs/zcode-smoke-test.md) for evidence and limits.

A subsequent isolated Roadster comparison finished naturally with and without Advisor. The user preferred the assisted demo before the condition mapping was revealed. Its three Claude reviews completed, were retrieved, and informed changes. It took **221.32 minutes**, versus **78.30 minutes** without Advisor. This single pair does not establish a general improvement rate; see the [benchmark summary](docs/roadster-benchmark.md).

Version **0.2.13** repairs native ownership checks after a foreground directory change. Status, context capture, and retrieval resolve the workspace root from ZCode's exact session index, while preserving session/job ownership and rejecting paths outside that root. All **212 tests** passed on Python 3.11 and 3.12. A fresh directed ZCode session retrieved both original Claude reviews from `src/`, applied the advice, passed unchanged fixture tests, and finished naturally with no outstanding hold. See [context transfer](docs/context-transfer.md) and the [versioned live report](docs/zcode-smoke-test.md). This was a retrieval repair check; the new benchmark was still pending at that release.

Version **0.2.12** adds opt-in verified-usage handoff and the progress-aware timeout repair prepared as 0.2.11. All **204 tests** passed on Python 3.11 and 3.12 with strict resource warnings; all **thirteen installed files matched source**. A controlled injected Claude quota refusal handed off once to real Codex advice, whose findings were fixed and reviewed. Separately, a neutral native ZCode engineering task demonstrated autonomous Codex consultation, background wake, exact-result retrieval, and concrete advice use. Its initial answer exceeded the word limit and retained two reasoning errors, so the advice lifecycle passed but the deliverable did not. No actual account exhaustion was verified. See the [versioned acceptance report](docs/zcode-smoke-test.md). Earlier benchmark copies remained pinned to 0.2.10 at that release.

Version **0.2.9 passed installation and fresh native ZCode Desktop acceptance**, with all twelve packaged files matching source and **145 plugin tests** passing under strict resource-warning handling. A plain coding prompt to GLM-5.3-Flash (Max requested) contained no consultation, provider, or uncertainty cues. The worker independently completed three Codex reviews, launched each exact native waiter once, woke from idle, and retrieved each original result. Independent notes editing proceeded while advice was pending; source/test changes followed completed retrieval. The worker applied substantive plan critique and later test/documentation critique, retrieved a fresh final approval after the latest workspace edit, and finished normally. All **seven fixture tests** passed with original assertions and README preserved; an independent gate mutation failed within its ten-second bound. This verifies the tested fixture, not every task or host. See the [versioned report](docs/zcode-smoke-test.md).

## Earlier verification

Earlier releases passed ZCode installation, startup injection, live Codex consultation/resume, and live Claude retrieval. A controlled Opus Max replay completed in **603.235 seconds**, supporting the longer deadline. Version 0.2.0 missed its instruction-only early checkpoint; its attempted write was denied and its fixture remained pristine.

The 0.2.1 trial demonstrated independent early initiation and native capture, but Codex rejected its oversized user input. The new transport resolves that measured input route; it does not change the earlier trial's outcome.

Version 0.2.2 passed installation, 85 automated tests, and the lock check. In a fresh plain-task ZCode trial, the agent independently requested and retrieved two Codex reviews, applied concrete lifecycle fixes, and passed independent original/expanded tests and race probes. Its initial **1,234,717-byte** advising input matched native base instructions exactly.

The required 0.2.2 post-fix review then failed when the host log exposed only 64 of 80 current messages. The session was stopped before its proposed manual fallback ran. That trial verified retrieval and use but did not finish; the later 0.2.9 acceptance result does not change its outcome. See the [smoke-test report](docs/zcode-smoke-test.md) and [host compatibility](docs/compatibility.md).

Version 0.2.3 passed installation and 96 automated tests with strict resource-warning and lock checks. It introduced explicit unavailable-review reporting. At that release, live unavailable-response handling and full-context recovery were unverified and full recording remained off pending consent.

Version 0.2.4 passed installation and 96 tests after adding rejection of Codex output after terminal `turn.completed`. Its table-driven cases cover trailing advice and a new turn.

Version **0.2.5 passed installation**, with all twelve packaged files matching source and its 7,975-byte skill within the 8,000-byte host budget. It preserves Unicode separators inside JSON strings by splitting provider JSONL only on LF and ignoring blank lines. All **97 tests** and strict resource-warning/lock checks passed. Real Codex CLI fresh/resume checks also passed the terminal guard with retained question history and refreshed context. At that release, full recording remained off and final acceptance was unverified.

Version **0.2.6 passed installation** and added native background completion alerts and unread-result reminders while removing the blanket initial edit gate. All **113 automated tests** and the strict resource-warning/lock checks passed. All twelve packaged files matched source, and the 7,857-byte skill fit the host budget. A fresh session exposed the updated live tool definition. A directed ZCode trial passed active completion delivery, same-job retrieval, evaluated advice use, and a correct reactive finish; independent grading passed **18,908 prefix-budget cases**. A fresh replay also proved independent editing while advice was pending and deferral of the dependent fix until completed retrieval. A third read-only trial proved clean idle wake and original-job retrieval from a new turn, with the review receipt retained only in the original turn. A separate Codex implementation review found no must-fix blockers. Full long-session acceptance was not established by that release.

A separate directed **0.2.7 Claude** trial completed fresh and resumed calls beyond 300 seconds, with exact initial/follow-up input verified. Native idle wake, completed retrieval, guarded edits, and an advised five-test repair passed. Registry 0.2.8 matched all twelve packaged files, but that existing task retained its original 0.2.7 MCP process. These Claude checks are distinct from the fresh 0.2.9 Codex acceptance above. Version 0.2.9 also repairs private Claude temp handling, declared-path holds, Stop precedence, literal bracketed paths, and exact-job attachment recovery; earlier benchmark evidence is unchanged.
