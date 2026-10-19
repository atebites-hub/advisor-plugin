# Context transfer

Advisor 0.2.0 transfers the **current semantic model input** in ZCode. This follows Claude's documented Advisor context categories: executor system instructions, tool definitions, previous conversation and tool results, and visible text so far in the current response. Claude supplies these server-side; Advisor captures them locally through a host adapter. It does not reproduce Anthropic's server implementation. [Claude's context contract](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#how-it-works)

## ZCode capture

The MCP request's `com.zcode/request-context` metadata supplies native `session_id`, `turn_id`, and `workspace_path`. ZCode's `workspace_path` is the current working directory, which can change during a session. From 0.2.13, Advisor resolves the canonical workspace root from the exact session's read-only registry row and requires the working directory to be that root or a descendant. Explicit workspace arguments and stored jobs must match the indexed root exactly. Status, capture, and advice retrieval use this same check; a missing index or foreign session fails closed. Retrieval does not recapture model I/O or require full retention. An MCP transport ID or an agent-invented session label is not sufficient.

From 0.2.1, the default task ID combines the native session and user turn, keeping a new user turn separate from earlier work. An explicit stable task ID is still supported for related follow-ups; it does not override native checkpoint scope.

Native 0.2.9 requests require `dependent_paths`, concrete workspace files/directories awaiting the answer; `[]` declares read-only advice. Paths may be relative or in-workspace absolute. Bracketed frontend paths such as `app/[slug]/page.tsx` are literal and accepted; wildcard expansion and escaping symlinks are unsupported. Named-edit path-resolution failures, including symlink loops, return structured JSON denials. This declaration does not replace source/test evidence in the conversation.

The adapter reads only `model-io-<session_id>.jsonl` for that session. It reconstructs retained full/delta message records and selects the latest main request for the exact turn. Its response must contain one uniquely matching `consult_advisor` invocation with the original arguments. The selected verified native `tool_call_id` is included in snapshot provenance and its hash: distinct consultation calls in one batch have distinct snapshot/attempt associations, while repeated capture of the same call is stable. The consultation tool is not marked read-only, so ZCode finalizes the generating model stream before dispatch. A bounded wait accommodates an incomplete final append; missing or ambiguous data fails instead of selecting a previous request.

The frozen packet contains:

| Category | Source |
| --- | --- |
| System and developer instructions | Native request system field and canonical system messages |
| Conversation and history | Reconstructed canonical request messages, preserving order and roles |
| Tool definitions | Retained request tool schemas, including descriptions and parameter definitions |
| Tool calls and results | Conversation messages plus available current response calls/results |
| Current assistant text | Visible text in the response that requested the consultation |

This is a semantic snapshot, not the byte-exact HTTP request. Only history present in the current input is claimed complete. Host compaction or retention may have discarded earlier history; an unreconstructable tail is rejected. ZCode deliberately replaces image/video bytes with omission markers in its logs. Those markers are retained, `source_omissions` identifies missing binary media, and coverage becomes incomplete for such inputs. Advisor cannot review unseen media. Files not read into the conversation are not automatically opened.

## ZCode recording prerequisite and scope

MCP `advisor_status.native_context` reports the current bound status invocation's recording evidence: `recording_mode` is `full_retention`, `bounded`, or `unknown`; `long_session_ready` is true only for positively verified `full_retention`. From 0.2.10, every new native consultation requires full retention and rechecks its own bound record. Complete bounded/unknown records fail as readiness errors before creating a snapshot, job, or dependency hold. Enable recording with approval unless already authorized, then make a new full request. Status and retrieval of existing advice remain available. Verified results include provenance and counts; unknown results explain the limitation. A bounded `messagesKind: "full"` is not unbounded full retention, and absent retention metadata alone is insufficient. Readiness does not recover discarded history/media or guarantee that a later consultation will pass exact-input and size checks. CLI `doctor` remains an executable check.

The MCP status tool uses `readOnlyHint=False` as ZCode's model-stream finalization barrier, so it can verify its exact native record before answering. It makes no model call and does not copy conversation content. `consult_advisor` and native `read_advice` also use that barrier; background polling is not native retrieval.

Desktop **Settings → General → Keep complete model I/O** bypasses normal 64-message-tail retention, body/SDK pruning, and writer rotation/size caps. Enabling it requires user privacy consent: it affects existing open and future sessions across workspaces, with no compression, size limits, or automatic deletion, including native reasoning. Leave approved recording enabled; Advisor checks the prerequisite but never writes global host settings. Standalone CLI **0.16.9 does not inherit the Desktop toggle** and has no supported full-retention override in the tested build, so it cannot start new native consultations in 0.2.10. Do not equate a Desktop setting with standalone readiness; check the current native status result.

During user-approved 0.2.9 Desktop testing, a final consultation captured **75 complete messages and 410 tool definitions**, with no source omissions, and completed advice was retrieved and evaluated before the task finished. A separate native status call at **87 messages** reported `full_retention` and `long_session_ready: true`. Full recording was then restored **OFF** and verified. A later, separately authorized check verified native full retention at **91 messages** with recording enabled. These are historical observations, not a guarantee about another installation. Every consultation still checks its own record.

A fresh installed-0.2.10 read-only UX task independently chose Claude for two reviews. Their exact bound snapshots contained **12 and 29 complete messages**, each with **410 tool definitions** and no source omissions. Exact waiters, native idle wakes, completed original-job retrieval, and concrete advice use were verified before normal finish. This establishes the tested capture/retrieval lifecycle, not a byte-exact provider-input comparison, same advising conversation, or flawless task conformance: a preamble made the 490-word specification's full response 511 words against a 500-word limit. See the [test report](zcode-smoke-test.md).

The adapter keeps its own bounded read of the latest **64 MiB** of the selected session log. A complete current record within that bound may be usable when native full retention is enabled; oversized or incomplete input must still fail. No heuristic stitching of older message tails substitutes for the exact current input. Changing recording settings does not rewrite old records or recover history the host already discarded.

## Privacy, freezing, and scope

Advisor excludes protected reasoning blocks/fields, provider metadata, and credential headers from its copies. Common credential formats and structured credential values are redacted; static schema properties such as `password` remain defined. Redaction cannot recognize every secret embedded in arbitrary text, so keep secrets out of working sessions.

These guarantees do not describe ZCode's original logs. Native full recording still runs header/media sanitization but retains native reasoning. Observed native file/directory permissions are **`0644` / `0755`**, compared with Advisor's **`0600` / `0700`** copies. Enabling full native recording therefore broadens persistent data across sessions even though Advisor reads only the explicitly bound session. Parent-directory permissions and the host's retention policy remain separate.

Sanitized JSON is atomically saved at `~/.local/state/advisor/contexts/<sha256>.json` with private directory/file permissions. The job references this immutable content hash. Both submission and execution verify its hash, version, workspace, host, and native session binding. Later conversation changes cannot alter the frozen evidence. Snapshots and native CLI histories remain local private session data and must not be committed.

`context_transfer` reports `native_snapshot`, its snapshot ID, category counts, exclusions, and the history boundary. Manual packets report `supplied_packet`. Tool input is limited to **1 MiB** and the assembled packet to **8 MiB**; exceeding either limit fails without silent truncation. A provider may impose a smaller context window and reject the request.

## Codex transport, 0.2.2

The 0.2.1 live trial captured the complete selected context, but `codex exec` rejected the 1,226,163-character user input against its 1,048,576-character limit. Capture success did not establish adviser-model receipt or completed advice.

The 0.2.2 implementation uses Codex's native `model_instructions_file` setting for every Codex consultation. A `0600` file inside the isolated `0700` temporary directory contains the adviser instructions and complete quoted JSON packet. Codex loads it as base instructions; stdin carries the actual consultation question. The packet is neither summarized nor truncated, and reading it requires no adviser tools. The temporary file is removed during cleanup; native CLI history retains its own lifecycle.

Explicit provider selection, fixed Max effort, `--ignore-user-config`, feature isolation, and resumable advising history remain. This changes transport, not captured scope or provider context-window limits.

A controlled Codex consultation using the previously captured full snapshot completed successfully. Its native session metadata contained base instructions exactly matching the intended **1,224,533 bytes / 1,223,689 characters**. The response cited source, README, test, and tool-schema evidence absent from the question. This verifies full-input receipt through the new route, beyond local capture alone.

A follow-up resumed the same advising session after the first temporary file was removed. It correctly recalled a prior-question token omitted from the new packet and identified a new context token absent from its new question. This verifies retained conversation plus refreshed file context. The resumed native record does not repeat the updated base-instruction field, so byte-exact verification is claimed only for the initial input.

A later installed-0.2.9 two-call canary positively verified fresh context on same-session resume: the new value was present only in the replacement instructions file, never the focused stdin question. The immutable native journal preserves initial metadata rather than recording updated resume overrides; its missing replacement text does not establish stale context, and no byte-exact resumed full-packet journal match is claimed. In the fresh 0.2.9 coding trial, initial native base instructions matched all **1,231,352 bytes**; subsequent advice used new source/test/note evidence absent from the earlier packet and short question.

A controlled Claude full-snapshot consultation also completed: native user content matched all **1,224,538 bytes**, and the answer used source, contract, baseline-failure, and schema evidence absent from the question. In a separate autonomous ZCode task, the initial Codex base instructions matched all **1,234,717 bytes** reconstructed from the exact submitted question and frozen snapshot. That agent retrieved and applied two completed reviews. These checks verify receipt and use at those stages, not universal completeness or final task acceptance.

The later 0.2.2 post-fix review exposed a retention boundary: the current ZCode log record reported 80 messages but retained only the final 64, with offset 16. The adapter rejected it as incomplete before starting another provider job. It did not silently reuse older context. The proposed manual packet fallback was denied and that trial stopped, without host-source or recording-setting changes. The later 0.2.9 long-context acceptance does not change that historical outcome. See the [trial report](zcode-smoke-test.md).

## Native retrieval receipts and checkpoints, 0.2.9

The native MCP `read_advice` wrapper verifies the job's workspace/session before exporting advice, including retrieval after an idle wake. Only the exact job's `completed` result with nonblank advice releases its declared holds, atomically with the retrieval receipt. The receipt remains against the job's **original turn**, never credited to an unrelated new turn. Core reads, notifications, status checks, and background waits do not release holds or establish retrieval.

An attachment failure after job creation is recoverable through that existing native read. Persisted job metadata binds its dependency attempt to the exact frozen snapshot; retrieval verifies this association before attaching and releasing the matching completed job. It starts no additional provider call and cannot clear unrelated failed/no-job attempts.

Declared-path holds are armed before provider launch, including genuinely unavailable history without a job. These holds survive failed/interrupted results, completed-but-unread jobs, restart, and later turns in the same native workspace/session. `PreToolUse` denies overlapping `Write`, `Edit`, `ApplyPatch`, `MultiEdit`, and `NotebookEdit` targets; unrelated named edits remain allowed. Directory overlap and resolved aliases count. Shell/delegated mutations and semantic decisions remain policy-only, never a bypass. A 0.2.10 bounded/unknown recording-readiness error creates no hold and does not release an earlier obligation. Early/final review policy and original-turn freshness remain; keep consultation and dependent actions in separate batches.

A failed/interrupted final review permits truthful incomplete-review reporting without restarting that job; it does not release declared paths. A verified running native waiter permits a pending/incomplete yield, without granting a completed receipt. Outstanding unread advice prevents a completion claim. `Stop` cannot exceed ZCode's three continuations, and hooks cannot establish that advice was evaluated. Fresh 0.2.9 Desktop acceptance verified three exact waiter launches and completed reads, actual critique use, and final approval after the latest workspace edit. A completed-but-unread hold remained unsatisfied until retrieval; independent notes editing proceeded and source/test changes followed completed advice.

Each native submission returns `completion_watcher` containing `tool: "Bash"` and the exact `input` for one background `advisor.py wait <job_id>` process. The agent launches it immediately. It waits only on the existing job, returns readiness without advice, and cannot spend model quota or create a review receipt. Native completion enters the active model's next request or wakes an idle agent; it does not interrupt generation. `PostToolUse` and `PostToolUseFailure` also repeat terminal-unread reminders until retrieval. Other hosts retain polling unless their native notification route is verified.

ZCode source inspection at `9e30b014d3141af7d6e97e472657fd68deedf4c8` verified this background delivery contract in `apps/zcode-cli/packages/core/src/runtime/methods/{runtime-command-active-loop,runtime-command-queue}.ts`. Its MCP logging notifications only enter logs, resource updates only drive subscribed UI events, and tool-list changes only refresh tools; they are not agent completion delivery. Version 0.2.6 passes 113 automated tests and the lock check; all twelve installed packaged files match source, and a fresh session exposes its updated tool definition. A directed native trial passed active completion alert, same-job retrieval, evaluated use, and a correct reactive finish. A fresh coding replay also proved independent editing while pending and dependent-work deferral until completed retrieval. Both coding runs received notification in their original turn. A third read-only trial independently established a clean idle period followed by an automatic new turn and completed original-job retrieval. The original turn received its completed receipt; the wake turn received no cloned review credit. Watcher-launch verification establishes launch, not future liveness; a failed watcher requires polling the same job. See [agent instructions](agent-instructions.md) and the [versioned report](zcode-smoke-test.md).

## Verified context unavailability, 0.2.3 source

When the exact native call is verified but retained tail/delta data lacks a complete baseline, `consult_advisor` returns:

```json
{
  "status": "unavailable",
  "provider_started": false,
  "review_complete": false,
  "error": "Explanation of the verified native retention failure"
}
```

There is **no `job_id`**, provider invocation, or completed-review receipt. Do not call `read_advice`, retry, invoke an advising CLI directly, reuse older context, invent session IDs, or choose another provider. Report the review incomplete. Malformed requests, unverified identity, ambiguous calls, concurrent review/file-edit batches, and other capture errors remain tool errors; they do not create an unavailable-review exception.

From 0.2.9, verified incomplete-history capture still arms the declared dependency hold. An unavailable marker or truthful incomplete-review report never unlocks those files. The 0.2.10 full-recording precondition is separate: a complete bounded/unknown record returns a readiness tool error with no snapshot, job, or hold; after user-approved enablement, a new full request can be consulted. Changing the setting cannot repair an already incomplete record or release earlier holds.

Only the adapter can establish the native unavailable scope, after checking the session/workspace registry, exact turn, uniquely matching call arguments, and separate-tool-batch requirement. The MCP wrapper validates the full bound request before recording anything and timestamps the attempt before scanning. A `during_task` attempt begun after the latest admitted edit may create a separate private `unavailable` marker tied to that exact workspace/session/user turn and edit revision. An early attempt creates no final-review exception; a later admitted edit clears the marker. Internal polling does not create it, and it is never represented as a job or completed receipt.

For that unchanged final revision, `Stop` permits a truthful report that the review is incomplete. This prevents repeated blocked completion attempts without claiming advice was received. The existing three-continuation host limit remains. Version 0.2.3 passed 96 automated tests and the lock check, with installation verified separately. Live unavailable-response behavior remains untested; successful 0.2.9 full-retention acceptance does not exercise that failure path.

## Other hosts

Generic MCP does not expose a host's system prompt or conversation. Other hosts and manual standalone CLI consultations still require an explicit `context` packet containing the relevant instructions, history, source/contracts, tool definitions/results, and test evidence. Their native transcript adapters are not implemented or claimed tested. Manual CLI support does not authorize an automatic fallback after native capture fails.

## Runtime and verification

Max effort remains fixed. There is no implicit total deadline. The default **1,200-second idle timeout** measures expected observable progress; it cannot prove a silent model has stalled. Nonempty Claude thinking/text deltas, advancing Claude `system/thinking_tokens` estimates for hidden thinking, and changing Codex reasoning/agent-message items renew it. Hidden-thinking watermarks are scoped to a message and content block; a new block can start from zero without accepting an older block's replayed totals. Empty, repeated, invalid or nonfinite counters, retry notices, and diagnostic noise do not renew it. Codex's JSON event format is documented in [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode). Explicit `timeout_seconds` remains an absolute limit. Jobs freeze their configuration; legacy numeric deadlines remain binding. Pending `read_advice` exposes phase, timings, counts, and output size only. Atomic progress updates also supply a bounded worker lease independently of provider activity. Watchers have no separate total cutoff. Successful terminal output and clean process exit are required, with bounded post-result cleanup. Stdout stays capped at 32 MiB, stderr at 4 KiB; errors show bounded redacted stderr. Private reasoning remains in bounded memory and is never written to Advisor state or returned.

Claude's child-only `CLAUDE_CODE_TMPDIR` now uses the existing private consultation directory. A fresh network-denied native probe reproduced `/tmp/claude-<uid>` startup failure and eliminated it with this override. A directed live trial through the original 0.2.7 MCP process completed fresh and same-session resumed Claude advice, both beyond 300 seconds. Native user input matched all **1,228,539 bytes / 21 messages** initially and **1,262,942 bytes / 40 messages** on follow-up, each with **410 tool definitions**. Native idle wake, completed retrieval, dependent-path release, and implementation of the retrieved advice were observed; the fixture's five tests passed with all original assertions preserved. These checks are distinct from the fresh 0.2.9 Codex final-review acceptance. Credentials, parent environment, tools-disabled configuration, and Max effort are unchanged.

Version 0.2.4 also rejects any Codex output after terminal `turn.completed`; two table-driven regressions cover trailing advice and a new turn after completion. All 96 tests and the lock check passed, and marketplace installation was verified with all twelve packaged files matching source. That release did not establish live unavailable-response handling or full-context recovery.

Version 0.2.5 uses LF-only JSONL framing for both providers, so U+0085, U+2028, and U+2029 inside JSON strings remain intact; blank lines are ignored. Its 97 tests and strict resource-warning/lock checks passed. A real Codex CLI 0.162.1 fresh/resume pair passed the terminal guard, retaining prior question memory and applying refreshed context without replaying old terminal events. Marketplace installation was verified with all twelve packaged files matching source and the skill at 7,975 bytes. Those checks preceded the 0.2.9 final acceptance.

The 0.2.9 plugin suite passed **145 tests** under strict resource-warning handling and the lock check. Its fresh coding fixture passed **seven tests**, retained all three original method ASTs and the README, and completed final review after applying the advisor's test/documentation critique. An independent gate mutation finished all seven tests with failure in **4.147 seconds** under a ten-second timeout. These live and simulated checks have different scopes; see the [versioned report](zcode-smoke-test.md).

Automated tests use fake providers to verify native MCP metadata, earlier tool-result canaries, complete schemas, frozen evidence, scope/hash checks, missing baselines, secret/reasoning exclusion, stream limits, deadlines, and process cleanup. Live installation and autonomous behavior are tracked separately in the [ZCode test report](zcode-smoke-test.md).

## Verified usage handoff

With user-enabled `usage_fallback`, verified account exhaustion permits one alternate fixed Max advisor inside the original job. Keep its watcher and dependency hold; retrieve and evaluate that job's completed advice. `provider_attempts` records the exhausted primary and actual answer provider. The frozen context and explicit total deadline are shared. Timeouts, sign-in failures, unknown quota, local budgets, and native capture failures never switch. Both exhausted means incomplete review. See [evidence and privacy limits](usage-fallback.md).
