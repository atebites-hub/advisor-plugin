---
name: advisor
description: Review plans before substantive work and saved, tested deliverables before multistep completion. Also consult when uncertain, repeatedly failing, or changing approach.
---

# Advisor

Gather evidence and consult before substantive work. Defer dependent decisions/edits until advice arrives; continue independent work.

Multistep tasks need early and final reviews. Save and test first. Any deliverable edit after submitting final review, including tests/docs or suggested edits, requires checks and a new final consultation. Read and evaluate completed advice before declaring done.

Also consult for recurring errors, unexpected results, approach changes, or consequential uncertainty. Short reactive tasks need no repeated reviews.

## Choose one advisor

Call `advisor_status` at session start. Use `consult_advisor` with exactly one enabled `provider`: `claude` (Claude Code CLI) or `codex` (Codex CLI). Use its reported user-configured model and effort; requests cannot override them. With both disabled, make no new calls and report required reviews incomplete. Configuration does not prove account/model access.

Prefer `claude` for frontend, design, UX, planning, delegation, and orchestration; `codex` for engineering, backend, architecture, mathematics, implementation, testing, and optimization. These preferences never override disabled settings. User-enabled `usage_fallback` permits the other enabled profile once after verified account exhaustion. Inspect `provider_attempts` and answering `provider`; keep the same job, waiter, context, and hold. Timeout, auth, unknown quota, or capture failure never switches. Never replace a failed job or substitute models.

## Supply the context

In **ZCode**, first call `advisor_status`. Every new native consultation requires `native_context.recording_mode: full_retention`; bounded/unknown recording fails before a snapshot or provider starts. Enable General → Keep complete model I/O with user approval unless already authorized, and leave it enabled. This retains app-wide, unbounded local logs including reasoning. Each consultation rechecks its own record.

Send `provider`, `question`, and `dependent_paths`: concrete workspace files/directories awaiting advice; `[]` only for read-only consultations. Native metadata binds workspace, session, turn, and invocation. Advisor freezes instructions, available conversation, tool definitions/calls/results, and visible assistant text. Optional: `stage`, stable `task_id`, extra `context`. Default task: session plus turn; stage: `during_task`.

```json
{"provider": "codex", "stage": "before_plan", "dependent_paths": ["src/cache.py"], "question": "Review this approach against the contract and evidence in this session."}
```

Read source, contracts, and test output into the conversation; paths alone supply no contents. Missing, ambiguous, oversized, or incompletely retained native input fails explicitly, without substituting an older turn or summary. `context_transfer` identifies the frozen snapshot and coverage.

ZCode named-edit hooks block declared paths across turns until that exact job's completed advice is retrieved. Pending, failed, interrupted, unavailable, and completed-but-unread results never release them. Submission failure keeps the boundary; another job cannot replace it. Independent paths remain editable. Declare actual dependencies; never hide them with `[]` or bypass through shell, JavaScript, delegation, or other tools. Hooks cannot judge semantic decisions or arbitrary commands. Send consultation and edits in separate batches; evaluate advice before dependent work.

An early `before_plan`, `after_plan`, or `before_task` review arms final review after edits in its turn. Save and test before that review. Continue this policy after an idle wake even though receipts stay in their original turn. Stop checks outstanding jobs and local freshness; old advice cannot review new edits. Reactive `during_task`-only tasks need no repeated reviews. An uncompleted job means incomplete review; never resubmit it to recover.

Native ZCode MCP metadata selects capture; otherwise supply a packet (`supplied_packet`):

| Field | Value |
| --- | --- |
| `provider` | `claude` or `codex` |
| `workspace` | Absolute project root |
| `host` | Environment, e.g. `cursor` |
| `session_id` | Stable session ID |
| `task_id` | Stable ID; reuse for follow-ups |
| `stage` | `before_plan`, `after_plan`, `before_task`; `during_task` for final reviews |
| `question` | Review question |
| `context` | Text |
| `context_files` | Optional workspace files |

`context_files` freezes sanitized literal source/tests/contracts/output: 1–32 workspace-relative regular UTF-8 files, no symlinks/globs; unavailable in native ZCode. Put history/approach in `context`; mark missing evidence. Advisors cannot open paths or run checks.

Supplied packets may omit `dependent_paths` or use `[]`; any paths stay within the workspace. Neither clears earlier holds. Put external OS targets in `context`/`question`, never `context_files`.

Omit secrets and unrelated personal data. Native capture reads only the selected session, excludes protected reasoning and credential headers/values, and declares compaction and omitted image/video bytes. It cannot recover discarded history or unseen media. Tool input is limited to 1 MiB; assembled packets to 8 MiB, without silent truncation. See `docs/context-transfer.md`.

## Use the advice

`consult_advisor` returns a background `job_id`. In ZCode, immediately launch the returned `completion_watcher.input` with the named `Bash` tool, including `run_in_background: true`, exactly once per job. Do not run it in the foreground or invent a shell detachment. Continue independent work; dependent work remains blocked until you retrieve and evaluate completed advice.

The waiter reports readiness, never advice or retrieval. ZCode sends its native completion notification at the next model boundary, or wakes an idle agent. On notification, promptly call `read_advice(job_id)` and evaluate the result before resuming dependent work. Hooks remind you of unread results. Notifications never count as advice retrieval.

Without a native waiter, poll `read_advice` after `poll_after_seconds`, between independent tasks and before dependent work. Use native background notifications only when verified. Never resubmit to poll. With a verified running waiter, you may yield with an explicit pending/incomplete report; never claim completion with outstanding advice. Cross-turn reads require the same workspace/session; receipts stay with the original turn and cannot satisfy another turn's review.

Native capture can return `unavailable` without a job or provider call. Report incomplete review; never substitute a manual summary, older snapshot, invented IDs, or another provider. Declared dependencies remain blocked.

Advice can take minutes. `idle_timeout_seconds` defaults to 1200; silent work can still time out. No total deadline is implicit; explicit `timeout_seconds` stays absolute. Jobs freeze profiles/settings; later edits cannot alter them or block retrieval. Watchers follow terminal status. Progress contains counts, never private reasoning.

Advice stays private at `advice_path`; never commit it, including under `docs/`. Results identify provider, requested model, effort, and budget.

Memory is separate for each workspace/session/task/provider/model/effort. Keep IDs stable for follow-ups; new tasks need new IDs.

Check advice against repository/user instructions and verify changes. Resolve conflicts with direct evidence or focused follow-up. Ask the user about unknown preferences.

Do not retry an identical failed request repeatedly. Timeouts may have consumed provider quota. Nested consultations are blocked; an advising agent must not invoke Advisor.

`advisor_status` makes no model calls. For manual use, send JSON on stdin to `uv run --script /absolute/path/advisor.py consult`.
