---
name: advisor
description: Review plans before substantive work and review saved, tested deliverables before declaring multi-step tasks complete. Also consult when uncertain, stuck on recurring errors, or changing approach.
---

# Advisor

After orientation, gather evidence and start a review before substantive work. Identify dependent decisions/edits and independent work; defer the uncertain approach until advice arrives.

Multistep tasks require early and final reviews. Save and test before the final consultation; retrieve and evaluate advice before declaring done.

Also consult for recurring errors, unexpected results, approach changes, or consequential uncertainty. Short reactive tasks need no repeated reviews. The worker invokes consultations.

## Choose one advisor

Use `consult_advisor` with exactly one `provider`:

- `claude`: Claude Opus 5.5 with Max effort through Claude Code CLI.
- `codex`: GPT 6.1 Sol with Max reasoning through Codex CLI.

Prefer `claude` for frontend, design, UX, planning, delegation, and orchestration; `codex` for engineering, backend, architecture, mathematics, implementation, testing, and optimization. These are preferences, not benchmarks. Choose the primary explicitly. User-enabled `usage_fallback` allows Advisor to try the other fixed Max profile once after verified account exhaustion. Inspect `provider_attempts` and the answering `provider`; keep the same job, waiter, context, and dependency hold. Timeout, auth, unknown quota, or capture failure never switches. Do not submit a replacement or substitute models.

## Supply the context

In **ZCode**, first call `advisor_status`. Every new native consultation requires `native_context.recording_mode: full_retention`; bounded/unknown recording fails before a snapshot or provider starts. Enable General → Keep complete model I/O with user approval unless already authorized, and leave it enabled. This retains app-wide, unbounded local logs including reasoning. Each consultation rechecks its own record.

Send `provider`, `question`, and explicit `dependent_paths`: concrete workspace files/directories awaiting advice; `[]` only for read-only consultations. Native metadata binds workspace, session, turn, and invocation. Advisor freezes instructions, available conversation, tool definitions/calls/results, and visible assistant text. Optional: `stage`, stable `task_id`, extra `context`. Default task: session plus turn; stage: `during_task`.

```json
{"provider": "codex", "stage": "before_plan", "dependent_paths": ["src/cache.py"], "question": "Review this approach against the contract and evidence in this session."}
```

Read necessary source, contracts, and test output into the conversation. Paths alone do not supply contents. Missing, ambiguous, oversized, or incompletely retained native input fails explicitly; Advisor never substitutes an older turn or summary. `context_transfer` identifies the frozen snapshot and coverage.

ZCode named-edit hooks block declared paths across turns until that exact job's completed advice is retrieved. Pending, failed, interrupted, unavailable, and completed-but-unread results never release them. Submission failure also keeps the boundary; another job does not silently replace it. Independent paths remain editable. Declare actual dependencies; never hide them with `[]` or bypass through shell, JavaScript, delegation, or other tools. Hooks cannot judge semantic decisions or mediate arbitrary commands. Send consultation and edits in separate batches; evaluate advice before dependent work.

An early `before_plan`, `after_plan`, or `before_task` review arms final review after edits in its turn. Save and test before that review; further edits require new final review. Continue this policy after an idle wake even though receipts stay in their original turn. Stop checks outstanding jobs and local freshness; old advice cannot review new edits. Reactive `during_task`-only tasks need no repeated reviews. An uncompleted job means incomplete review; never resubmit it to recover.

In **other hosts or the standalone CLI**, pass the explicit packet below. Automatic context capture is currently implemented only for ZCode.

| Field | Value |
| --- | --- |
| `provider` | `claude` or `codex` |
| `workspace` | Absolute path to the current project |
| `host` | Working environment, such as `cursor` or `zcode` |
| `session_id` | Stable identifier for your current working session |
| `task_id` | Stable identifier for this task; reuse it for follow-ups |
| `stage` | `before_plan`, `after_plan`, `before_task`, or `during_task`; use `during_task` for completion reviews |
| `question` | The plan, completed work, uncertainty, or behavior you want reviewed |
| `context` | The context packet described below, as text |

For code reviews, include source/diffs, surrounding code, contracts, and test output. The advisor cannot open files or run checks. Mark missing evidence or compacted history and limit the review accordingly.

Omit secrets and unrelated personal data. Native capture reads only the selected session, excludes protected reasoning and credential headers/values, and declares compaction and omitted image/video bytes. It cannot recover discarded history or unseen media. Manual input is limited to 1 MiB; assembled native packets to 8 MiB, without silent truncation. See `docs/context-transfer.md`.

## Use the advice

`consult_advisor` returns a background `job_id`. In ZCode, immediately launch the returned `completion_watcher.input` with the named `Bash` tool, including `run_in_background: true`, exactly once per job. Do not run it in the foreground or invent a shell detachment. Continue independent work; dependent work remains blocked until you retrieve and evaluate completed advice.

The waiter reports readiness, never advice or retrieval. ZCode sends its native completion notification at the next model boundary, or wakes an idle agent. On notification, promptly call `read_advice(job_id)` and evaluate the result before resuming dependent work. Hooks remind you of unread results. Notifications never count as advice retrieval.

Without a supported native waiter, poll `read_advice` after `poll_after_seconds`, between independent tasks and before dependent work. Other hosts have no verified push delivery. Never resubmit to poll. With a verified running waiter, you may yield with an explicit pending/incomplete report; never claim completion with outstanding advice. Cross-turn reads require the same workspace/session; receipts stay with the original turn and cannot satisfy another turn's review.

Native capture can return `unavailable` without a job or provider call. Report incomplete review; never substitute a manual summary, older snapshot, invented IDs, or another provider. Declared dependencies remain blocked.

Max advice may take many minutes. No total limit is implicit; `idle_timeout_seconds` defaults to 1200. Silent models may still be working. Explicit `timeout_seconds` stays absolute. Jobs freeze settings; watchers follow terminal status. Progress is counts only; private reasoning is never persisted or returned.

Advice is private at `advice_path`; never commit it or copy it into version-controlled `docs/`. Results identify provider, requested model, effort, and budget.

Each workspace/session/task/advisor has a separate resumable conversation. Keep IDs stable for follow-ups; use new task IDs for unrelated work.

Check advice against the repository and user instructions; make your own decision and verify changes. Investigate conflicts with direct evidence or request a focused follow-up. Ask the user about unknown preferences.

Do not retry an identical failed request repeatedly. Timeouts may have consumed provider quota. Nested consultations are blocked; an advising agent must not invoke Advisor.

`advisor_status` makes no model calls. For non-native use, send JSON on stdin to `uv run --script /absolute/path/advisor.py consult`.
