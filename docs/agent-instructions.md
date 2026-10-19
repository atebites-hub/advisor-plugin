# Loading the consultation rule

Advisor needs both an available tool and a rule the working agent sees before making decisions. The full skill is loaded on demand; its presence alone does not ensure the whole policy enters the initial context.

## ZCode

The native `.zcode-plugin/plugin.json` declares a `SessionStart` hook. It runs `advisor.py session-start` and returns structured `additionalContext` containing the review checkpoints and tool workflow. It does not read conversation history, change permissions, or call a model. Refresh the marketplace and update Advisor to get this hook. Start a fresh native session afterward: ZCode snapshots hooks at startup, and an existing task can retain its old MCP process despite a registry/package update. A new turn alone does not prove the new runtime loaded.

Verify Advisor's entries under **Settings → Hooks**, then ask a fresh agent to describe the consultation rule already in its context. See [ZCode's hook contract](https://zcode.z.ai/en/docs/hooks).

Call `advisor_status` at session start and choose only an enabled provider with its reported user-configured model and effort. Requests cannot override those values. Configure them in **Settings → Plugins → Advisor → More details → Configuration**. `use_app_settings` defaults to true and overrides shared-file profiles; turning it off uses `~/.config/advisor/config.json` and defaults. The shared CLI wizard is `uv run --script plugins/advisor/advisor.py configure`; `ADVISOR_CONFIG` selects another file. Save and use a fresh session if the running MCP process retains old app values. See [configuration details](../README.md#configure-advisors).

Native consultation captures the current session using MCP metadata. From 0.2.10, every new consultation requires `advisor_status.native_context.recording_mode: "full_retention"`, rechecked against the consultation's own record. Enable **General → Keep complete model I/O** with user approval unless already authorized, and leave approved recording enabled. This creates app-wide unbounded logs including native reasoning; Advisor does not write global settings. Then choose one enabled provider, declare `dependent_paths`, and ask the question. See the [context-transfer contract](context-transfer.md).

A bounded/unknown readiness error creates no snapshot, job, or dependency hold: enable recording and make a new full request. Status and existing `read_advice` remain usable. Genuinely missing native history still returns `unavailable` with scoped dependency holds; never substitute a manual packet or provider fallback. Standalone CLI 0.16.9 lacks a supported full-retention setting and cannot start new native consultations in this release.

## Consultation timeouts

New jobs freeze their provider profiles, handoff permission, and timeout settings. Changing or disabling profiles does not alter existing jobs or prevent their retrieval. By default there is no total deadline; `idle_timeout_seconds` limits silence in observable progress to 1200 seconds. A silent model may still be working. Explicit `timeout_seconds` stays absolute, and existing numeric job deadlines remain binding. Watchers follow original terminal status without a separate duration limit.

## ZCode asynchronous checkpoints, 0.2.10

Every native request must include `dependent_paths`, concrete workspace files or directories awaiting advice, such as `["app/[slug]/page.tsx", "tests/renderer"]`. Use `[]` only when no file mutation depends on this read-only consultation; it does not clear earlier holds. Relative and in-workspace absolute paths are supported. Brackets are literal; wildcard expansion and escaping symlinks are unsupported. Symlink loops in named-edit targets return a structured JSON denial.

`PreToolUse` guards overlapping `Write`, `Edit`, `ApplyPatch`, `MultiEdit`, and `NotebookEdit` targets. Declared holds survive failures, unavailable capture, completed-but-unread jobs, restart, and later turns until the matching job's completed advice is retrieved through native `read_advice`. Independent named edits remain allowed. Arbitrary shell writes, delegation, and semantic decisions remain policy-only: do not use them to bypass a hold. Keep consultation and dependent actions in separate tool batches.

Immediately start exactly one returned `completion_watcher.input` with its named `Bash` tool, including `run_in_background: true`. The waiter is bounded by the existing job deadline, returns only readiness, and never starts a provider or records retrieval. ZCode's native notification enters the next model request while active or starts a model-only turn when idle. On notification, promptly call `read_advice(job_id)`; reading waiter output is insufficient. `PostToolUse` and `PostToolUseFailure` additionally remind the worker about terminal unread jobs until actual retrieval. Native notification is not a mid-token interruption.

An initial `before_plan`, `after_plan`, or `before_task` review arms a final `Stop` checkpoint once edits have been admitted in that native turn. Save the deliverable, run relevant checks, then submit and retrieve a fresh review after the latest edit. Reading an older job again does not satisfy freshness. A task with only a `during_task` consultation for a short reactive action does not automatically acquire repeated review checkpoints. After an idle wake, path holds persist and the worker continues final-review policy; review credit is not cloned into the new turn.

The native MCP retrieval wrapper verifies the same workspace/session before exporting advice. A completed native read releases only the exact job's holds, atomically with its receipt. Later-turn retrieval is supported, but the review receipt stays on the job's original turn and cannot satisfy another turn's freshness requirement. Failed or interrupted reads permit truthful incomplete-review reporting, without releasing paths or authorizing a replacement job. Notifications, waiter output, status checks, and core polling are not completed retrieval.

If submission created a job but attaching its hold failed, retrieve that existing job. Native retrieval repairs attachment using its exact persisted snapshot/attempt association for the selected verified native call, without calling the provider again. It never clears an unrelated failed or no-job attempt.

Outstanding advice blocks a completion claim. Once native post-tool evidence verifies the exact background waiter launch, the worker may yield with an explicit pending/incomplete report and let ZCode wake it; this is not a completed review or successful final receipt. Without a supported native waiter, use spaced `read_advice` polls rather than silently abandoning the question.

ZCode caps `Stop` continuations at three. These hooks cannot prove that advice was evaluated or intercept arbitrary shell/delegated mutations. A verified watcher launch is not a liveness guarantee; if it fails, poll the same job. Other hosts have no verified native push delivery.

A fresh 0.2.9 Desktop task with a plain coding prompt passed natural consultation, one exact waiter per review, idle wake, completed original-job retrieval, independent editing, and dependent-edit ordering. The worker applied early and final critique, retrieved a fresh approval after its last workspace edit, and finished with seven passing fixture tests. A complete 75-message final consultation and 87-message full-retention status check passed during a consented test; full recording was restored OFF afterward. A later, separately authorized historical check verified full retention at 91 messages with recording enabled. Each installation needs its own consent and readiness check.

Installation and the native Claude advice lifecycle passed in a fresh 0.2.10 read-only UX task. Without consultation cues, the worker independently requested two Claude reviews, launched each exact waiter once, woke from idle, retrieved the original completed advice, and applied it before finishing. Its 490-word specification had a preamble that pushed the full response to 511 words, exceeding the 500-word limit. This does not replace the 0.2.9 engineering edit checks or separate directed 0.2.7 Claude fresh/resume evidence. See the [versioned test report](zcode-smoke-test.md) for scope and limits.

## Project or user instructions

For a host without a supplied startup hook, merge this section into the project's `AGENTS.md` or the host's equivalent instructions. User-level instructions apply more broadly when the host supports them. Preserve existing content; do not replace the whole file.

```markdown
## Advisor

After brief orientation, load the Advisor skill and consult before substantive
implementation or committing to an approach. For longer, multistep tasks,
require an early review and a final review after saving the deliverable and
running tests, before claiming completion. Also consult for recurring errors,
approach changes, or consequential technical uncertainty. Trivial reactive
tasks do not need repeated reviews.
Call `advisor_status` at session start. Choose exactly one enabled `claude` or
`codex` using its reported model and effort; do not override user settings.
If both are disabled, make no new calls and report required reviews incomplete.
User-supplied workflow preferences favor Claude for
frontend, design, UX, planning, delegation, and orchestration; Codex for
engineering, backend, architecture, mathematics, implementation, testing,
and optimization. These are soft preferences, not benchmarked rankings.
Call `consult_advisor` with a focused question, objective, constraints,
relevant evidence, attempts, and stable session/task IDs. For code and
completion reviews, include actual relevant source/diffs, the applicable
contract, and concrete test commands and output. Summaries, file paths,
and test-pass claims alone are insufficient; the advisor cannot read project
files or run checks. Explicitly mark missing material or compacted history.
Identify and defer the work that needs the answer; continue independent work.
In native ZCode, require `recording_mode: full_retention` from
`advisor_status.native_context` before every new consultation. Enable General → Keep complete
model I/O with user approval unless already authorized; leave it enabled.
This stores app-wide unbounded logs including native reasoning. Supply concrete
`dependent_paths`; use `[]` only for read-only advice. Declared paths stay held
across turns until the exact job's completed native `read_advice` retrieval.
Failures and unavailable capture do not release them. Shell/delegation is no bypass.
In ZCode, immediately launch exactly one returned `completion_watcher.input`
through its named Bash tool with `run_in_background: true`. On its native
completion notification, promptly retrieve the job with `read_advice`.
Otherwise poll after `poll_after_seconds`. Retrieve and evaluate completed
advice before dependent work; notifications and waiter output are not advice.
Verify the resulting decision; never claim completion with outstanding advice.
User-enabled verified usage handoff keeps the same job; inspect provider_attempts
and the answering provider. Do not send secrets, retry failed jobs, substitute
models, or consult recursively. Ask the user about unknown preferences.
```

A file inside an installed plugin is not automatically a project's instruction file. Host instruction discovery differs, so check a fresh session rather than assuming a plugin-root `AGENTS.md` is inherited. The startup hook supplies instructions; the model remains responsible for invoking Advisor, evaluating advice, and completing the reviews.

## Verified usage handoff

With user-enabled `usage_fallback`, verified account exhaustion permits the other enabled, configured advisor once inside the original job. A disabled alternate is never launched. Keep the same watcher and dependency hold; retrieve and evaluate that job's completed advice. `provider_attempts` records requested models/efforts, the exhausted primary, and actual answer provider. The frozen context and explicit total deadline are shared. Timeouts, sign-in failures, unknown quota, local budgets, and native capture failures never switch. Both exhausted means incomplete review. See [evidence and privacy limits](usage-fallback.md).
