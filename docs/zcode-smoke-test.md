# ZCode smoke test

## 0.3.1 configurable advisors (October 19, 2026)

ZCode Desktop **3.16.1** (bundled CLI **0.17.0**) displayed all seven native Advisor configuration controls. Saving Claude disabled and Codex `gpt-6-astra` / `max` reached the real MCP `advisor_status` in a fresh session without restarting the app. Status also verified `full_retention`. The shared JSON configuration and guided CLI setup were checked separately.

A fresh **directed configuration test** used GLM-5.3-Flash with Max requested to repair a small Python function. The prompt required the installed review workflow but did not name a provider or model. The worker discovered the enabled profiles, selected Codex, loaded the skill, and completed two uncached Astra Max reviews in the same advising session. The calls took **97.4 and 133.5 seconds**; native Codex `turn_context` metadata recorded `gpt-6-astra` and `max`.

The worker launched each returned background watcher, retrieved both original results with native `read_advice`, and evaluated them. It waited for early advice before the dependent write, incorporated an implementation correction, saved the result, passed all **six unchanged fixture tests**, and submitted the final review after the last edit. The final critique led to stronger assertion-based verification before the worker finished. Independent grading passed the original tests plus structural-input and iterator-exception identity probes. Both native receipts completed, the final submission was newer than the last edit, and no jobs remained unread.

A preceding **neutral** prompt for the same small task skipped Advisor; that attempt was stopped before its proposed edit. This trial therefore establishes directed configuration and advice use, not dependable unprompted triggering or benchmark improvement.

All **269 automated tests passed on Python 3.11 and 3.12** with ResourceWarnings treated as errors; model calls in those tests are simulated. Lock, whitespace, and official manifest checks passed. Regressions cover configured alternate handoff, disabled providers, GUI precedence, frozen jobs, model/effort isolation, and legacy missing-versus-invalid configuration. The final code review found no blocking defect; the CLI wizard's single-writer assumption is documented.

The full lifecycle above ran installed **0.3.0**. The final **0.3.1** adds the legacy migration repair and shares the effort constant; its profile-selection and schema-2 behavior are unchanged. The official updater installed 0.3.1, all **fourteen packaged files matched source**, and the native UI showed 0.3.1 with restored default profiles. The exact prior Advisor option entry was restored; approved complete model-I/O recording stayed enabled. Existing sessions may retain older MCP processes, so start a fresh session after an update. Other hosts' native settings adapters and every model/account combination remain untested. Requested identity is not an independent served-model attestation. Private sessions and original advice remain outside the repository.

## Earlier checks

Tested locally on October 15–18, 2026, using ZCode **3.15.3.8237**, working models **GLM-5.3 / GLM-5.3-Flash (Max requested)**, Advisor **0.1.1–0.2.14**, Claude Code **2.1.301**, and Codex CLI **0.162.1**. Version 0.2.12 separately verified controlled quota handoff and a fresh natural Codex advice lifecycle. Earlier versioned failures and directed checks remain recorded below. Both advising CLIs were already signed in. No credentials were copied.

## 0.2.14 Claude hidden-thinking progress

A later benchmark consultation reached Advisor's idle limit with no recognized progress. That run was frozen as a technical failure; both runs and their 60-minute snapshots remain preserved, unseen and unscored. The historical stdout stream was not retained, so its exact activity cannot be reconstructed.

Static inspection of Claude Code 2.1.301 and separate live probes established a missed signal: `system/thinking_tokens` events can report activity while thinking text is hidden. Advisor now accepts finite, positive advances against watermarks for each message/content-block pair. New blocks can start from zero; repeated starts and historical message replays cannot erase earlier watermarks. Block-start noise and post-terminal activity cannot extend the idle or cleanup timers. The **1,200-second idle limit**, optional absolute deadline, fixed Max profiles, and reasoning-content exclusion remain unchanged.

All **220 automated tests passed on Python 3.11 and 3.12** with strict resource warnings; provider calls are simulated. The lock check passed. Regressions cover hidden progress beyond a virtual 1,200 seconds, invalid/replayed estimates, fresh/resumed input preservation, absolute limits, and terminal cleanup. The alternating-message replay regression failed against the earlier source and passed after correction. Separate real Claude CLI fresh/resume probes passed with 1,024-byte inputs and with 139,130/656,314-byte inputs. The larger sizes approximate earlier snapshot geometry, not its unmeasured provider-input bytes or review complexity.

A fresh **directed** GLM-5.3-Flash session, with Max requested, ran the final hardened build. It loaded the Advisor skill and completed two distinct uncached Claude Opus Max reviews in the **same advising session**, without fallback. Native captures contained **15 and 35 complete messages**, each with **37 tool definitions** and no reported source omissions. For both jobs, metadata confirmed a genuine pending yield with an active source hold. Native alerts woke the worker; it retrieved each original result from `src/` before dependent work or completion.

The first advice produced the one-expression repair `return sum(values)`. The worker displayed the saved source before final review, passed both unchanged original tests, and checked single-pass iterator behavior. The final critique corrected its preservation and identity claims; the worker adopted those corrections and finished naturally. Independent hashes and Python 3.11 checks confirmed unchanged README/tests, both passing tests, and single-pass iteration. Both review receipts completed, all holds and watchers cleared, and the test app was retired after two idle checks.

The official updater installed **0.2.14** into normal ZCode; all **thirteen packaged files matched the tested source**, with other plugins and enablement unchanged. Existing tasks may retain older MCP processes; start a fresh task to load the update. This verifies a small directed workflow, not autonomous triggering, a large native review, the historical twenty-minute failure, or benchmark improvement. Served-model identity was not independently attested (`identity_verified: false`). Private session data remains outside the repository. At this directed check, the new benchmark was still pending; the subsequent completed K/L comparison is reported separately in the [benchmark summary](roadster-benchmark.md).

## 0.2.13 native subdirectory ownership repair

A benchmark attempt produced Claude advice, but three native retrieval calls were rejected by workspace/session verification. The user stopped that run as a technical failure; its artifacts remain preserved and unscored. A separate unchanged-0.2.12 diagnostic reproduced a cwd-dependent defect: the same original job was rejected twice in `src/`, then became readable at the root while the indexed session directory stayed unchanged. The benchmark's exact rejected metadata was unavailable, so this does not establish its historical cause conclusively.

Version 0.2.13 resolves ownership from the exact native session's read-only index. The current working directory may be the indexed root or its descendant; explicit workspace arguments and stored job roots must match that root exactly. Status, capture, and retrieval share this resolver. Foreign sessions, outside paths, escaping symlinks, and missing or changed index bindings remain rejected. Retrieval requires no model-I/O recapture.

All **212 automated tests passed on Python 3.11 and 3.12** with strict resource warnings; model calls are simulated. Lock and official package validation passed. The normal installation and fresh private test package each matched all **thirteen source files**. Targeted repair-diff reviews found no blockers.

In a fresh **directed** GLM-5.3-Flash test (Max requested), an early Claude consultation started at the root. The worker launched its exact background waiter, changed into `src/`, and yielded. Direct metadata confirmed the original job remained pending more than 70 seconds after the stop. Its native notification woke the worker, which retrieved completed advice from `src/`; the original-turn receipt completed and its hold cleared.

The worker adopted `return sum(values)`, passed both unchanged original tests, and checked iterators/generators (`3 3 0`). A new final consultation from `src/` reported **34 complete messages and 37 tool definitions**, with no omissions in that snapshot's coverage. Its own pending yield, notification, original-job retrieval, and hold release passed. The final advice requested a saved-source display after the host deduplicated a redundant Read; a read-only `cat` supplied it. The worker finished naturally without further edits. Independent verification confirmed the exact source, unchanged README/tests, and both passing tests.

Both advising calls answered through the requested Claude Opus Max profile without handoff; served-model identity was not independently attested. This proves the directed repair lifecycle, not autonomous triggering or a completed benchmark comparison. Session data and original advice remain private outside the repository.

## 0.2.12 usage handoff and native advice lifecycle

Opt-in `usage_fallback` authorizes one switch between the two fixed Max profiles after verified account exhaustion. The original job, frozen context, watcher, dependency hold, and explicit total deadline continue. Other errors never trigger a switch. Missing typed evidence fails closed; Windows handoff detection is unsupported. The timeout repair removes the implicit total limit while retaining a 1,200-second observable-progress idle timeout and bounded cleanup. Existing jobs retain their frozen settings. See the [usage handoff contract](usage-fallback.md).

All **204 automated tests passed on Python 3.11 and 3.12** with strict resource-warning handling. Provider calls in these tests are simulated. Coverage includes both handoff directions, identical supplied context, attempt journaling, shared deadlines, failure classification, native MCP retrieval, dependency holds, and host disconnection. Regressions rejected two defects found during source review: nullable duplicate terminal fields and abnormal positive process exits. Both failed against the archived earlier source and passed after correction. The lock check and official ZCode manifest validation passed.

### Controlled handoff with real alternate advice

A private fake Claude executable returned the expected typed first-party quota refusal without making an account request. Advisor recorded that cause, switched exactly once, and obtained real **Codex GPT 6.1 Sol Max** source-review advice. The review found the two defects above; they were fixed with regressions, and a separate corrected-source review returned scoped approval. This verifies the injected refusal-to-real-advice route, not genuine account exhaustion. A metadata-only probe against this review's own Codex session confirmed the installed CLI's lifecycle fields and resume boundary without exposing protected content or modifying native records.

### Installed native ZCode check

The existing marketplace was refreshed and its only plugin updated from 0.2.10 to **0.2.12** through the official bundled CLI. All **thirteen packaged files matched source**, the plugin was enabled with no diagnostics, and the **7,974-byte** skill fit the host budget. The user's private configuration enabled usage handoff; native `advisor_status` confirmed it. Complete model-I/O recording remained **ON** under the user's existing authorization. Fresh MCP and waiter processes used the 0.2.12 installation; an update does not replace older active session processes.

A fresh read-only engineering workspace contained only a README describing export retries, leases, object creation, and non-idempotent email. The neutral prompt requested its recommendation without mentioning Advisor, providers, or uncertainty. GLM-5.3-Flash (Max requested) independently checked readiness, loaded the skill, chose Codex, and submitted one consultation with `dependent_paths: []`. Its bound snapshot contained **12 complete messages and 410 tool definitions**. The job froze handoff enabled, the 1,200-second idle timeout, and no implicit total deadline.

The worker launched the exact returned background waiter once and yielded with the task explicitly incomplete. Real Codex advice completed; the native notification woke the worker, which requested the original job's advice about **9.7 seconds** later. Retrieved text matched the saved advice exactly. Public evaluation and the final answer adopted two concrete corrections: fresh owner tokens can still fence database writes after row recreation, and duplicate-versus-loss email semantics remain an unknown product preference. The worker finished naturally, with no outstanding receipt or background execution, and the sole README remained unchanged. This run used Codex directly and did not encounter quota exhaustion.

The initial full response was **305 whitespace words**, exceeding the 250-word limit; its recommendation body alone was **256 words**. It also incorrectly called finitely capped retries at-least-once delivery and asserted an unspecified continuation after failed object creation. The advice lifecycle passed; the initial deliverable failed. Its original output and audit were preserved before a separate directed correction turn. That turn's model request was cancelled after about eight seconds, producing no assistant text or tool calls; no corrected completion is claimed.

This read-only run did not exercise a live file dependency hold or the twenty-minute boundary; those paths have simulated regression coverage, while earlier versioned native coding checks remain separate. Requested model selectors and Max effort were observed, without independent served-model attestation. No account was deliberately depleted, Windows or other-host support was not established, and the frozen 0.2.10 Roadster benchmark was not rerun. Private session identifiers, transcripts, and advice remain outside the repository.

## 0.2.10 recording prerequisite and Claude advice lifecycle

Every new native ZCode consultation now requires positively verified `full_retention`, checked against that consultation's exact bound native record. A complete bounded/unknown record returns a readiness tool error before any snapshot, job, provider launch, or path hold. After user-approved enablement, a new full request can proceed. Status and existing advice retrieval remain usable. Genuine missing-history tail/delta failures still return `unavailable` with scoped dependency holds; no manual-packet or provider fallback is permitted.

In a separately authorized historical check, **Keep complete model I/O** was enabled, verified in the UI and by native status reporting full retention at **91 messages**. The earlier 0.2.9 OFF-restoration evidence below remains valid. Each installation needs its own consent and readiness check. Recording is app-wide and unbounded, includes native reasoning, and has no automatic deletion. Advisor enforces the prerequisite without writing global settings. Standalone CLI 0.16.9 lacks a supported full-retention override and cannot start new native consultations in this release.

Installation through marketplace Refresh and Update passed: all **twelve packaged files matched source**, and a fresh session exposed the new tool definition and 0.2.10 waiter path. The skill is **7,970 bytes**, within the 8,000-byte host budget. All **148 plugin tests** passed with strict resource-warning handling, and the lock check resolved the same 30 packages. Automated provider calls remain simulated; the live trial below is separate.

### Fresh natural read-only UX task

A fresh GLM-5.3-Flash session (Max requested) received a neutral checkout UX brief, with no consultation, provider, or uncertainty cues. Its workspace contained only the brief's README. The worker independently chose Claude for an early review and later requested a final critique. The exact bound native snapshots contained **12 and 29 complete messages**, respectively, each with **410 tool definitions** and no source omissions. These are verified local semantic captures, not byte-exact provider-input comparisons or a claim that both calls shared an advising conversation.

Both original jobs completed. Each returned one exact 0.2.10 background waiter, launched once; native completion woke the idle worker, which retrieved that job's completed advice. Public evaluation and subsequent output showed concrete advice use. After the second critique, the worker corrected the pending-button condition, failure recovery and focus behavior, and numeric-keypad scope. It checked the revised specification's word count and ran targeted text checks before finishing normally. No provider fallback occurred.

The specification was **490 words**, but an unnecessary **21-word preamble made the full response 511 words**, exceeding the 500-word limit despite advice to send the specification alone. The advice lifecycle passed; flawless brief conformance did not. The task remained read-only, with the sole README unchanged. It does not replace the separate 0.2.9 engineering edit/dependency checks or establish other-host support, independently attested model identity, or UX certification. The Roadster benchmark was not rerun; earlier results retain their versions and scope. Raw identifiers, transcripts, and advice remain outside this repository.

## 0.2.9 native Desktop acceptance

The source requires native `dependent_paths` and guards overlapping named edits across turns until the exact job's completed advice is read natively. Failed, unavailable, and completed-but-unread results retain their holds; unrelated named edits remain allowed. Literal bracketed frontend paths are accepted, symlink loops return JSON denials, and a native read can repair an attachment using its exact persisted snapshot/attempt association without another provider call. Unrelated failed/no-job attempts remain held. Shell writes, delegation, and semantic decisions remain policy-only boundaries.

MCP `advisor_status.native_context` checks the exact bound record for `full_retention`, `bounded`, or `unknown`, with `long_session_ready` true only for positively verified full retention. Its `readOnlyHint=False` annotation supplies the native record-finalization barrier; `doctor` still checks executables only. Desktop full Model I/O requires user consent for app-wide unbounded logs including native reasoning. Standalone CLI 0.16.9 cannot inherit that toggle and has no supported full-retention override in the tested build.

A fresh, isolated native Claude startup probe used the fixed Max/tools-disabled adapter flags with all network access denied and no copied credentials. The default temp root reproduced the exact shared `/tmp/claude-<uid>` mkdir error. Setting child-only `CLAUDE_CODE_TMPDIR` to the private consultation directory removed that error and reached the expected unsigned-in result. Benchmark workspaces, credentials, snapshots, and logs were preserved; no successful advice inference is claimed by this probe.

Registry **0.2.8 matched all twelve packaged files**, but the existing task retained its original **0.2.7 MCP process**: the Phase 2 watcher command still referenced 0.2.7. Package verification therefore does not establish 0.2.8 runtime execution. Source 0.2.8 includes unresolved-path Stop precedence; 0.2.9 adds literal paths and attachment recovery bound to the selected verified native call. Its snapshot provenance/hash distinguishes separate calls in one batch and stays stable for repeat capture of the same call.

### Fresh natural coding task, installed 0.2.9

All **twelve installed files matched source**. A fresh native session received a plain coding prompt with no consultation, provider, or uncertainty cues. GLM-5.3-Flash (Max requested) independently requested three Codex reviews. Each returned one exact **0.2.9** background waiter, launched once; native completion woke the idle worker, which retrieved the original completed job. There was no replacement consultation or provider fallback.

An independent `NOTES.md` edit proceeded while early advice was pending. Source and tests stayed unchanged through the completed-but-unread state, with dependency satisfaction still `0`; dependent edits followed completed retrieval. The early advice identified two substantive cancellation/generation defects in the proposed approach, and the worker adopted the corrected lifecycle. It independently caught and fixed an accidental original-test setup typo after its own failed test run.

The first final critique accepted the production repair but required bounded test cleanup, accurate generation coverage, abandoned-cleanup-failure coverage, and corrected verification notes. The worker retrieved and applied those changes. The last review followed the latest workspace edit, approved completion, and was retrieved and evaluated before the worker's normal final response. No deliverable file changed afterward. Independent inspection found the **README byte-identical and all three original test methods AST-identical**.

The final fixture passed **seven tests** on native Python 3.9 and in an independent Python 3.11 development-mode run with strict resource warnings. Complete native debug output was inspected without fault diagnostics. An independent gate-release mutation finished all seven tests with failure in **4.147 seconds**, below a ten-second timeout, confirming a bounded failure for that regression. One cross-generation overtaking schedule remains explicitly untested; single-loop and undrained-shutdown limitations are documented.

### Complete context, resume, and recording restoration

The initial Codex native base instructions matched all **1,231,352 bytes**. A separate installed-0.2.9 two-call canary confirmed fresh context on same-session resume, with the new value supplied only through the replacement instructions file. The immutable native journal retains initial metadata rather than updated resume overrides, so no byte-exact resumed full-packet journal match is claimed. Later actual reviews also used newly supplied source, tests, and notes.

With the user's permission to test and restore, Desktop full recording was temporarily enabled. The final consultation captured **75 complete messages and 410 tool definitions**, with no source omissions, and completed retrieval and task finish. A separate native `advisor_status` call at **87 messages** reported `recording_mode: "full_retention"` and `long_session_ready: true`. **Keep complete model I/O was then restored OFF and verified.** This does not grant permanent recording consent or establish standalone CLI readiness.

The plugin suite passed **145 tests** with strict resource-warning handling; the lock check resolved the same **30 packages**. Separate source reviews completed without remaining must-fix findings. This acceptance covers one fresh Desktop coding fixture, not every task, host, or scheduler interleaving. No private identifiers, session dumps, or advice are copied into the repository.

### Live Phases 1–2, original installed 0.2.7 process

The real Claude consultation completed in approximately **527.7 seconds**. Its native user input matched all **1,228,539 bytes**, including **410 tool definitions and 21 messages**. Native idle wake delivered the completion; the worker retrieved the exact completed job and evaluated its recommendations. Both the fresh and resumed calls exceeded 300 seconds; this was a directed Claude check, separate from the natural 0.2.9 Codex task above.

An independent `NOTES.md` edit proceeded while advice was pending. A dependent `Write` was denied and the original source hash remained unchanged. The dependency receipt remained unsatisfied (`0`) before completed native retrieval and became satisfied (`1`) afterward. This demonstrates actual advice delivery, waiting, retrieval, evaluated use, and path-hold release for that phase; no private identifiers, transcripts or advice are copied here.

Phase 2's `after_plan` follow-up completed through the same original 0.2.7 native MCP process and Claude session. Its complete bound input matched all **1,262,942 bytes**, including **410 tool definitions and 40 messages**. These are two completed real Claude consultations, fresh and resumed; the package update did not replace the existing MCP process.

Completed native retrieval preceded the source `Write` and additive test `Edit`. The repair implements the advice's retirement lifecycle and both requested regression scenarios. Independent inspection found the README byte-identical and all **three original test methods AST-identical**. The native development-mode test command passed **five tests**; an independent Python 3.11 development-mode run also passed all five without warnings. This verifies saved implementation and specific advice use, not final-review completion.

These directed 0.2.7 results establish Claude startup recovery, fresh/resumed context transfer, and advice use at those phases; the final long-context acceptance above used Codex in a fresh 0.2.9 process. Earlier benchmark evidence below is unchanged.

## Earlier verified behavior

- Added this repository as a local marketplace through ZCode's Plugin Marketplace, installed its only plugin, and updated it to 0.1.1 after refreshing the source.
- Confirmed the installed runtime, skill, and ZCode manifest match the repository files.
- Observed Advisor's skill and MCP server in ZCode, and its read-only `SessionStart` entry in Settings → Hooks.
- In a new session in an empty workspace outside this repository, the working agent quoted the hook's exact source heading and first two policy sentences without reading files, loading skills, or calling tools. This rules out the repository's `AGENTS.md` as the source of the reminder.
- Completed a live Codex consultation and a follow-up using the same native advising session. The follow-up recalled a synthetic marker absent from its new request, demonstrating conversation memory.
- Completed a live Claude consultation. ZCode's original synchronous tool timed out at 30 seconds, but Advisor saved the completed result. Reissuing the identical packet recovered cached advice without decrementing that provider's budget.
- In the fresh session, loaded the skill and started one new Claude consultation through 0.1.1. The initial tool returned `pending` promptly; later `read_advice` calls returned `pending` and then `completed` with advice and its Markdown path. The call ran beyond 30 seconds without blocking the MCP service, requested Opus 5.5 Max, and spent exactly one successful consultation.
- Verified the job directory uses `0700` permissions and result/advice files use `0600`. The transient request file was removed after the worker loaded it.

An existing ZCode session retained its original two-tool MCP interface after the plugin update. Start a **fresh session** to obtain the new `read_advice` tool and startup hook.

## Behavioral trials

These tests used disposable workspaces outside this repository, with no `AGENTS.md` or Advisor instructions in their files. The ordinary coding prompts did not name Advisor, providers, or consultation tools.

| Trial | Observed result |
| --- | --- |
| Simple normalization fix, 0.1.1 | Minimal correct change; one test passed; no unnecessary consultation. The session's hook diagnostics showed Advisor's startup hook ran. |
| SQLite lease recovery, 0.1.1 | Completed without consulting; 12 tests passed. An independent six-process probe confirmed exclusive claiming. The agent's added concurrency regressions used threads, leaving the requested process regression incomplete. |
| Knowledge check after lease recovery | Without tools, files, or skill loading, accurately recalled the uncertainty trigger, one-provider selection, context packet, stable IDs, background job, `read_advice`, and verification requirements from current session context. |
| Process cleanup assessment, 0.1.1 | Prompt explicitly asked for unresolved correctness questions, without naming Advisor. Agent declared its questions settled and requested no advice. Test stopped at the first write approval; implementation was not evaluated. |
| Ordinary process cleanup task, 0.1.2 | Fresh session with no uncertainty-check instruction in the task prompt. Reproduced baseline failures, implemented a process-group fix, and passed four tests without consulting. An independent Python 3.11 run also passed; no fixture processes remained. |
| Current-context check after process cleanup, 0.1.2 | With no tools or file reads, quoted the revised hook heading and first two sentences exactly, and identified the live submission/retrieval tool names and background job contract. The hook log showed `SessionStart Plugin 47ms`. |

The lease task included a hung test command. Only that command was stopped; the agent diagnosed and repaired its test harness without consultation. These observations verify instruction awareness, but do not establish a self-initiated consultation: the agent reported resolving its questions from local evidence.

Version 0.1.2 makes the uncertainty check explicit at planning, implementation, and recovery decisions, while keeping calls conditional. It was installed through the marketplace update flow, and its installed runtime, skill, and ZCode manifest matched the source. The fresh process-cleanup retest still did not demonstrate a self-initiated consultation. None of these coding trials started a new Advisor job. A reminder exposes the rule; the working model still decides whether uncertainty remains.

### Harder asynchronous-cache trial, 0.1.2

A further trial used a fresh external asynchronous-cache workspace and unchanged Advisor 0.1.2. The contract combined request coalescing, per-waiter cancellation, overlapping invalidation generations, a global producer limit that includes cancellation cleanup, and shutdown of retired producers. Event barriers and bounded waits made the races reproducible.

The baseline passed 8 of 18 tests and failed 10 in 1.306 seconds. A separate evaluator implementation passed all 18 unchanged tests before launch. The fixture's three files and the installed plugin were checked against their recorded hashes.

The ordinary coding prompt contained no uncertainty, Advisor, provider, or consultation-tool cues:

> Fix the asynchronous catalog cache to satisfy the cancellation, invalidation, concurrency, and shutdown guarantees in README.md. Preserve the public API, documented guarantees, and existing test assertions. Keep the change minimal and standard-library-only, add any missing regression, and run the full suite with the supported Python version.

There was one run, bounded in advance to 30 minutes of active agent time plus any consultation already in progress. Only routine one-time approvals were supplied; no evaluator hints or policy changes occurred. Success required independent consultation about an unresolved technical question, visible retrieval of completed advice, evaluated use of a concrete recommendation, and independently verified completion without weakened tests.

The agent finished in **10 minutes 38 seconds**. Its first implementation passed all 18 tests, it added two regressions, and it reported 20 passing tests across ten runs. The hook log showed `SessionStart Plugin 47ms`. The complete visible action trace contained no consultation or retrieval calls, and private state contained **zero new Advisor jobs**. The installed runtime, skill, and hook manifest remained identical to the frozen source.

Independent verification passed the original 18 tests, the expanded 20-test suite, and a separate combined-race probe. All original helper/test methods were AST-identical, and the README was unchanged. A further diagnostic exposed an ordinary loader failure also emitting `Task exception was never retrieved`; fixture teardown had masked that warning by gathering producer tasks. The initial completion therefore had a residual defect.

**Initial outcome:** no autonomous consultation was demonstrated. The agent did not identify an unresolved technical question; advice retrieval and use were not exercised.

A separate recovery phase supplied only the unexpected error and a standalone reproduction command, then requested a fix and regression. It did not mention Advisor, uncertainty, providers, or consultation tools. The agent finished in **8 minutes 11 seconds**, diagnosed the failure locally, fixed it, and added a third regression. Independent final verification passed the original 18 unchanged tests, the expanded 21-test suite, the combined-race probe, and the exception-cleanup diagnostic with no unhandled exceptions or pending tasks. All original test methods and the README remained unchanged. Neither phase contained a consultation or retrieval call, and both phases together created zero new Advisor jobs.

| Acceptance gate | Final result |
| --- | --- |
| Independent consultation | Not demonstrated; no call occurred. |
| Completed advice retrieved | Not exercised in this trial. |
| Advice evaluated and used | Not exercised in this trial. |
| Coding task completed | Independently verified after factual QA feedback. |

The harder task and its unexpected failure did not produce an identified unresolved technical question. This result cannot establish whether the model will consult when it recognizes such uncertainty. The startup rule was available, but this trial did not demonstrate an autonomous end-to-end consultation. These synthetic checks do not cover production load or every event-loop interleaving.

### Review-checkpoint trial, 0.1.3

On October 16, Advisor 0.1.3 was installed through the existing marketplace's refresh and Update controls. The installed runtime, skill, and manifests matched the repository. A fresh session ran the 0.1.3 MCP process; its hook log showed `SessionStart Plugin 54ms`. No ZCode source or account settings were changed.

The trial reused the exact ordinary cache prompt above in a fresh workspace with the three pristine files and no Advisor instructions. The baseline again passed 8 of 18 tests and failed 10. The task, plugin, and prompt stayed fixed throughout; only routine one-time approvals were supplied. ZCode reported **20 minutes 8 seconds**, including approval waits.

The agent began implementation without consulting, missing the early checkpoint. After saving its implementation, adding one regression, and running its checks, it independently requested a completion review. It explicitly selected **Claude Opus 5.5 Max**, used `during_task`, and supplied the objective, constraints, implementation design, evidence, and stable task/session IDs. The prompt had not named Advisor or asked for a review.

The call returned `pending`. The agent used `read_advice` on the same job, performed independent stress checks while waiting, waited between polls, and eventually retrieved `failed`: the advising CLI exceeded its **300-second** deadline. The native CLI record contained the supplied request and outbound API-request events, but no assistant reply. Exactly one new Advisor job was created. The agent disclosed the timeout, did not retry or switch providers, and reported its coding work complete. No completed advice was available to evaluate or use.

Independent grading passed the original **18 unchanged tests**, the expanded **19-test suite**, the combined-race probe, and the exception-cleanup probe with **zero unhandled exceptions or pending tasks**. All original tests/helpers were AST-identical and the README was unchanged.

| Acceptance gate | Result |
| --- | --- |
| Early review before implementation | Failed; no consultation preceded the first edit. |
| Self-initiated final-review request | Passed; the agent selected one advisor after implementation and checks. |
| Pending-job handling | Passed; same-job retrieval, no duplicate call or fallback. |
| Completed advice retrieved and used | Not achieved; the provider timed out without advice. |
| Coding task completed | Independently verified. |

This run demonstrates autonomous final-review initiation under the checkpoint policy. It does **not** establish reliable early-checkpoint adherence or a completed Advisor-assisted finish. Earlier directed tests establish that completed retrieval can work; they do not repair this autonomous trial's missing advice.

### Timeout diagnosis and packet review, 0.1.5

The 300-second stop was Advisor's configured subprocess deadline, not a timeout response from Claude or ZCode. Its error path discarded captured subprocess output, leaving the original wait unexplained. Version 0.1.5 identifies the provider and deadline, preserves a bounded redacted stderr tail, reports whether stdout was captured without exposing it, and bounds output cleanup. Binary capture preserves diagnostics even if termination splits a UTF-8 character; successful responses still require valid UTF-8. A real fake-CLI regression reproduced that decoding failure before the correction. At 0.1.5 the default remained 300 seconds; Advisor did not automatically retry jobs or switch providers. The underlying CLI's internal retries are a separate behavior.

A separate minimal diagnostic through the same isolated Claude adapter completed in **3.319 seconds**. A single controlled replay of the previous review packet, with private native debug logging, received the first response chunk **1.260 seconds** after dispatch but produced no completed advice before the same deadline (**300.014 seconds** overall). The captured trace showed no connection error or retry. This reproduces the missing completed response, but does not distinguish long generation from a stalled stream or establish the original request's internal state. These manual diagnostics are separate from the autonomous ZCode trial.

Inspection also found that the original review packet contained a design summary and claimed test results, without actual source, diffs, README guarantees, or test output. Since the advisor had no tools, the repository path did not provide source access. Version 0.1.5 strengthens the instructions to include those materials and disclose missing context. It adds the user's soft provider-selection preferences without claiming measured model rankings or changing explicit one-provider selection.

The live diagnostic logs, advice, and native session records remain outside the repository. At that stage, the provider's reason for not completing the review remained unresolved; the confirmed diagnostic-loss defect had regression coverage.

After final checks, 0.1.5 was installed through marketplace refresh and Update. Its installed runtime, skill, and native manifests matched the tested source; the installed startup command emitted the strengthened packet instructions and provider preferences. This verifies the update, not a new autonomous coding trial. Start a fresh ZCode session to load the changed instructions.

### Native context and extended deadline, 0.2.0

A later controlled replay completed the review in **603.235 seconds** using the same **Claude Opus 5.5 Max** profile. Its first stream byte arrived at **2.093 seconds**. The trace showed no errors, retries, or tool calls. This establishes that the review can complete beyond the old five-minute cutoff and supports long active inference as an explanation; it does not prove the original run's internal state or autonomous advice use.

Version 0.2.0 uses a **1,200-second (20-minute) absolute deadline**, preserving the fixed Max profiles. Bounded stream capture retains at most **32 MiB stdout** and a **4 KiB stderr tail**. Pending results report activity counts and timing without protected reasoning content. Progress does not extend the deadline, and no automatic retry or provider fallback is added.

With the user's authorization, the ZCode adapter captures the current semantic model input: system instructions, retained messages, tool definitions, calls/results, and visible current-response text. Native workspace/session metadata, the turn, and exact consultation arguments identify the source. The frozen snapshot is hashed, kept in private state, and accompanied by coverage information. Missing or ambiguous current input fails rather than falling back to an older turn. No host source is edited. See the [context-transfer contract](context-transfer.md).

The snapshot cannot recover history discarded before compaction. Protected reasoning, credential headers, and unrelated sessions are excluded. A source file absent from the working session remains absent from the review. Manual tool input is bounded to **1 MiB**; the separately assembled context is bounded to **8 MiB**, with no silent truncation. Other hosts retain manual context packets and remain untested.

Version 0.2.0 was installed through the local marketplace's Refresh and Update controls. Its runtime, context adapter, lockfile, skill, all native manifests, and both MCP configurations matched the tested source byte for byte. The installed startup command advertises automatic native context and the 20-minute deadline. A separate live consultation through the revised Claude streaming adapter completed successfully, and the parser accepted the full successful ten-minute replay stream.

The fresh 0.2.0 trial reused the unchanged ordinary cache prompt in a pristine three-file workspace. Its actual model input contained the current startup checkpoint instructions, automatic native-context workflow, and 20-minute deadline; its tool definition also advertised the new native context contract. A stale installation or cached manual-only schema did not explain the behavior.

The agent read the project, publicly committed to a detailed implementation plan, and attempted `Write(cache.py)` before any consultation. That write was still awaiting native permission. The evaluator denied it without feedback and stopped the session at **9 minutes 23 seconds**. No edit was executed: all three files retained their original hashes. The trace contained zero consultation/retrieval calls and no Advisor jobs were created.

**Outcome:** the instruction-only early checkpoint failed. Native context transfer, completed retrieval, advice use, and final review were not exercised by this trial. Stopping at the first attempted write preserves that result without claiming an implementation was changed or graded.

### File-edit checkpoints and autonomous trial, 0.2.1

Version 0.2.1 adds a ZCode `PreToolUse` gate for `Write`, `Edit`, `ApplyPatch`, `MultiEdit`, and `NotebookEdit`. A named file edit requires completed-advice retrieval in the current native workspace/session/user turn. Initial `before_plan`, `after_plan`, or `before_task` review arms a bounded final `Stop` checkpoint after admitted edits; final advice must come from a job submitted after the latest edit. Rereading an older job is insufficient. A `during_task`-only short reactive consultation does not force repeated reviews.

The native MCP wrapper checks scope before exporting advice and records retrieval receipts atomically in private SQLite state. Core polling is side-effect free. A failed early review cannot admit edits. A fresh final review retrieved as failed or interrupted permits reporting the review incomplete without automatic retry or fallback. Consultation and file edits must not be batched concurrently.

This gate does not intercept Bash, JavaScript, or delegated writes. ZCode limits `Stop` continuations to three. It is a behavioral guardrail, not a security sandbox or proof of understanding and evaluated use. See the [hook instructions](agent-instructions.md) and [context-transfer contract](context-transfer.md).

Version 0.2.1 was installed through marketplace Refresh and Update; all eleven runtime, adapter, checkpoint, lockfile, skill, manifest, and MCP files matched the source byte for byte.

A fresh GLM-5.3 Max session used the same ordinary coding prompt and three pristine fixture files. After orientation and a baseline showing ten failures among eighteen tests, it independently announced a plan review and selected **Codex GPT 6.1 Sol Max**. This happened before any write attempt or hook denial; no evaluator reminder requested consultation. The request contained only `provider`, `question`, and `stage: before_plan`. The question presented a proposed approach for review; this demonstrates review before implementation, not consultation before the agent formed a proposal.

Native capture produced a hash-verified **1,157,772-byte** frozen snapshot with **16 messages and 410 tool definitions**, the actual source, README contract, baseline test results, system instructions, and current visible response. Native workspace/session/turn binding matched. An exact original source statement and a baseline test name were present in the snapshot and absent from the consultation question, demonstrating transfer beyond the agent's summary.

The background job returned `pending`, but Codex's CLI then rejected its **1,226,163-character** assembled input against a **1,048,576-character** limit. No advice was produced. The agent called `read_advice` on that same job; the native wrapper recorded a correctly scoped **failed** retrieval receipt. No retry or fallback occurred. The evaluator stopped the session at **about 11 minutes 6 seconds**, before further work. There were no admitted writes, and all three original file hashes remained unchanged.

| Acceptance gate | Result |
| --- | --- |
| Independent early consultation | Passed before any write attempt or hook denial. |
| Native source and session-context capture | Passed; frozen hash, scope, categories, and earlier evidence verified. |
| Same-job status retrieval | Passed with a scoped failed receipt; no duplicate or fallback. |
| Adviser model received full context | Not established; the CLI rejected oversized input. |
| Completed advice retrieved and evaluated | Not achieved; no advice was available. |
| Live file-edit admission and fresh final review | Not exercised. |
| Coding task completed | Not exercised; stopped fixture remained pristine. |

**Outcome:** autonomous early initiation, native capture, and failure retrieval were verified in this session. The 0.2.1 CLI transport blocked completed advice; no Advisor-assisted finish is claimed. The failed 0.2.0 trial remains a separate recorded result. Raw snapshots, receipts, and session identifiers stay outside this repository.

### Controlled Codex full-input diagnostics, 0.2.2

The revised Codex adapter supplies adviser instructions and the complete quoted JSON packet through the native `model_instructions_file` setting. A private file in the isolated temporary directory becomes Codex's base instructions; stdin carries the actual question. Fixed Max effort, ignored user configuration, and disabled tools remain unchanged. See the [transport contract](context-transfer.md).

A controlled consultation using the selected 0.2.1 snapshot completed successfully. An exact byte comparison against the resulting native session metadata verified the entire **1,224,533-byte / 1,223,689-character** base-instruction input. The returned advice cited actual source, README guarantees, test evidence, and tool-schema details absent from the question. This establishes receipt beyond local snapshot capture, without truncating or summarizing the context.

A follow-up completed in the same native advising session after the first temporary input file was removed. It recalled a prior-question token absent from the new packet and identified a fresh context marker absent from the new question. This verifies retained history and refreshed file context. The resumed record does not persist the updated base-instruction field; the exact byte comparison applies to the initial consultation only.

These were explicitly selected provider diagnostics, not automatic retries by the stopped ZCode agent. They do not repair the 0.2.1 autonomous trial. A controlled Claude full-snapshot consultation also completed: native user content matched all **1,224,538 bytes**, and its answer used actual source, README guarantees, baseline failures, and tool-schema evidence absent from the question. Native records, input comparisons, and returned advice remain private.

### Autonomous reviews and retained-tail failure, 0.2.2

Version 0.2.2 was installed through marketplace Refresh and Update. All **twelve packaged files** matched the tested source byte for byte, including the expanded skill. A fresh GLM-5.3 Max session received the same plain coding prompt in the pristine three-file fixture. No provider, tool, consultation, or uncertainty cue was added to the prompt, and no evaluator hint was supplied during the run. Only routine one-time approvals were given until the stopping intervention below; the plugin and task stayed fixed.

After reading the source, contract, and tests, the agent loaded the skill and independently chose **Codex GPT 6.1 Sol Max** for a plan review before any file-edit attempt or hook denial. It supplied only `provider`, `question`, and `stage: before_plan`. The frozen initial context contained **17 messages and 410 tool definitions**, actual source and tests, environment output, system instructions, and current visible text. Its **1,234,717-byte / 1,233,865-character** adviser input matched the native Codex base instructions exactly. Source and tool-result evidence absent from the question was present in that input.

The agent waited between same-job checks, retrieved completed advice, and publicly evaluated two concrete lifecycle gaps: shutdown between producer completion and waiter resumption, and cancellation before a producer coroutine starts. It implemented both fixes and regressions, then passed 22 tests. A new completion review was submitted **218.189 seconds after the latest admitted edit**, with changed source and test output in its 45-message snapshot. The same native advising session returned a further cancellation-cleanup concern. The agent retrieved that advice, fixed independently initiated cancellation handling, strengthened regressions, and verified scratch mutations and orphaned-exception behavior. Both completed native receipts were independently checked, and both advice results appeared in subsequent executor model input.

After the last edits and 23 passing tests, the agent independently requested a fresh post-fix review. This third submission failed before creating a provider job: **“Current model input is incomplete; a full baseline was not retained.”** The current host record reported **80 messages**, retained **64**, and declared **offset 16**. The adapter rejected this tail rather than substituting old context. The agent then proposed a manual CLI packet with invented session/task aliases and summarized evidence. That pending command included an actual CLI invocation; it was denied without feedback and the session was stopped before another provider call. Such a manual packet would not establish full native-context transfer or a fresh scoped final receipt.

The original 30-minute target was extended to observe the natural advice-driven repair and re-review loop. Recorded model requests spanned **43 minutes 14 seconds** before the stop; this run is not claimed to have stayed within the original bound or reached autonomous completion.

Independent grading of the stopped candidate passed the **18 original tests**, **23 expanded tests**, and **five combined-race/exception-cleanup probes**, with no unhandled exceptions or pending tasks. All original test and helper definitions were AST-identical. The README's only change was its test count, **18 → 23**; its guarantees and API contract were unchanged. The literal README-hash check therefore differed without a correctness regression.

| Acceptance gate | Result |
| --- | --- |
| Independent early consultation | Passed before edits or hook denial. |
| Full initial native input received | Passed by byte-exact comparison and evidence absent from the question. |
| Completed retrieval and evaluated use | Passed for two reviews, with concrete resulting fixes and tests. |
| Post-implementation review | Passed, then correctly led to further changes requiring renewed review. |
| Fresh review after the last edits | Not achieved; retained-tail capture failed before provider invocation. |
| Stopped implementation correctness | Original/expanded suites and independent probes passed. |
| Autonomous finish | Not achieved; evaluator stopped the proposed manual fallback. |

This run verifies that the working agent can independently consult, receive advice, and use it. It does not establish reliable long-session context capture or a completed workflow with the required fresh final review. The retained-tail failure remains unresolved in 0.2.2.

### Native retention setup after the stopped 0.2.2 trial

Subsequent host inspection found **Settings → General → Keep complete model I/O** off. Native full retention bypasses the normal 64-message recording baseline, successful-request body/SDK pruning, and all writer rotation/size caps. Its UI describes no compression, size limits, or automatic deletion. This is an app-global setting affecting existing open and future sessions across workspaces; no supported session/workspace-only, CLI, environment, or complete-input export alternative was found.

Native header/media sanitization still runs, but native reasoning remains in the host logs. Observed native permissions are **`0644` files / `0755` directories**. Advisor's sanitized snapshots remain **`0600` / `0700`**; their exclusions and permissions do not apply retroactively to the host's originals.

At that stage, the user had been asked whether to enable the global setting; it remained off and no host source or recording configuration was edited. The adapter's own selected-log read remains bounded to **64 MiB**. The later 0.2.9 test verified a complete >64-message review with permission, then restored recording OFF. No unsafe tail stitching substitutes for full context. Historical stage results and the stopped 0.2.2 trial remain unchanged.

### Explicit unavailable-review handling, 0.2.3

The new source handles verified retained-history failure with `status: unavailable`, `provider_started: false`, `review_complete: false`, and an explanation, without a job ID. It does not start a provider, invent a job, record completed advice, or silently substitute a manual packet. Policy, skill, and tool instructions explicitly prohibit manual CLI invocation, older context, invented IDs, retry, or provider fallback after failed native capture. Standalone CLI support remains for manual/non-native consultations.

Native workspace/session/turn identity, uniquely matching call arguments, separate review/edit batches, and the full request must be validated first. The attempt starts before scanning. Only a `during_task` unavailable attempt begun after the latest admitted edit can record a separate marker for the current edit revision. `Stop` then permits a truthful incomplete-review report. Early unavailability cannot admit writes; later admitted edits invalidate the marker. Malformed, ambiguous, or unverified requests remain errors without such a marker.

Version 0.2.3 was installed through marketplace Refresh and Update. All **twelve packaged files** matched the source byte for byte; its **7,975-byte skill** fits the host's **8,000-byte budget**. At that release, **Keep complete model I/O** was off and recording consent was pending.

**Still unverified:** live agent handling of the unavailable response and its failure-path `Stop` exception. Successful final-review completion is verified separately in 0.2.9. Installation does not repair the stopped 0.2.2 trial or supply its missing final advice.

### Codex terminal-output hardening, 0.2.4

The parser now rejects output after a Codex `turn.completed` event instead of accepting trailing advice or another turn. Two cases were added to its existing table-driven regression; the full suite still has 96 tests. Strict resource-warning and lock checks pass. This parser change does not recover missing context or establish live unavailable-response/final-review acceptance.

Version 0.2.4 was installed through marketplace Refresh and Update. All twelve packaged files matched the source byte for byte; the skill remains 7,975 bytes. At that release, full recording remained off pending consent.

### Unicode JSONL framing and real resume, 0.2.5

Both provider parsers now split JSONL only on LF and ignore blank lines, preserving U+0085, U+2028, and U+2029 inside JSON string values. One new test method covers both providers and all three separators; existing cases strengthen failure-branch and trailing-LF checks. The full suite is **97 tests**, with strict resource-warning and lock checks passing.

Real Codex CLI 0.162.1 fresh and same-session resume calls passed the terminal-completion guard. The follow-up retained earlier question memory and used a new context marker, confirming that resumed stdout did not replay a previous `turn.completed`. No native IDs, tokens, or records are copied here.

A closing Claude consultation through the current adapter completed and was retrieved. It found no blockers in the parser changes. Its suggested JSONL-framing check found no remaining `splitlines()` calls in the shared adapter; the completed consultation also exercised the current Claude parsing branch live.

Version 0.2.5 was installed through marketplace Refresh and Update. All twelve packaged files matched source byte for byte; the skill remains 7,975 bytes. At that release, full recording remained off pending consent and final acceptance was unverified.

### Independent work and completion alerts, 0.2.6

The source removes the blanket initial edit gate. Named-edit hooks now track changes and remind the worker to defer advice-dependent work while allowing independent work. Early-review intent still arms final freshness within its originating turn. The worker must continue the same review policy after a native idle wake; receipt state is not cloned across turns.

Native job submissions return one exact `completion_watcher` launch for the supported `Bash` tool with `run_in_background: true`. The agent must launch it immediately. The bounded waiter checks the existing job and returns readiness only, without advice, provider calls, or a retrieval receipt. ZCode's background-task completion enters an active agent's next model request or wakes an idle agent. Post-tool success/failure hooks additionally remind the agent about terminal unread results until actual `read_advice` retrieval. A verified running waiter permits truthful pending/incomplete yield, never a completion claim.

Source inspection at ZCode commit `9e30b014d3141af7d6e97e472657fd68deedf4c8` distinguishes native task notification from MCP logging, resource updates, and tool-list changes, which do not wake the agent. Model-boundary delivery is not a mid-token interruption.

Version 0.2.6 was installed through marketplace Refresh and Update. All **twelve packaged files** match source byte for byte; the skill is **7,857 bytes**, within the host budget. A fresh GLM-5.3 Max session's actual MCP tool definition includes `completion_watcher` and dependent-work instructions, verifying that the live process loaded the update. All **113 automated tests** pass in **11.269 seconds** with resource warnings treated as errors. The lock check resolves the same 30 packages successfully.

A directed short reactive trial completed. Its prompt explicitly chose one Codex `during_task` consultation and separated an independent README edit from a UTF-8 fix that had to await completed advice, with no extra plan or final consultation. The native system task notification entered the active agent's model input; the background Bash task completed with exit code zero and an actionable summary naming the exact job and `read_advice`.

The real Codex consultation completed in approximately **44.9 seconds**. The worker retrieved that same job and publicly evaluated the recommendation to encode, slice, and decode rather than follow its planned character loop. Only then did it edit the README and apply the dependent fix. The frozen five-test suite and ten advice-derived edge checks passed. Independent grading passed **1,885 strings / 18,908 prefix-budget cases**; the frozen test hash was unchanged, the README contract was exact with only a Development append, and the API/docstring were preserved with only the implementation's return line changed.

This first trial proves active completion delivery, retrieval, evaluated use, and a correct directed reactive finish. It does **not** prove an independent edit while consultation was pending or an idle wake: the review finished before the README edit, and exact watcher-dispatch versus provider-completion timing was not established.

A fresh pristine replay completed with the independent README edit first and background waiter second in one tool batch. The README edit's observed modification time was **22:36:39.631 UTC**, before the Advisor result at **22:36:51.817 UTC**. Source and frozen tests remained unmodified until completed retrieval and public evaluation. The single Codex consultation took approximately **42.2 seconds**. The worker then changed the return line, passed all five frozen tests, and finished. Independent grading again passed **1,885 strings / 18,908 prefix-budget cases**; test hash, API, docstring, and README contract were preserved.

This replay proves independent editing while advice is pending and deferral of the dependent fix. Its native completion notification and a ready-result Stop reminder were delivered in the original turn. It does **not** prove clean idle wake: the waiting response ran from **22:36:43.570 to 22:36:53.964 UTC**, so provider completion occurred during that response. No coaching, fake provider, or artificial delay was added after either coding run began. These are directed behavior tests, not autonomous-trigger tests or replacements for historical long-session final-review acceptance.

A third, read-only engineering-review test passed clean idle wake using four exact current source copies. The worker's first request omitted its provider and was rejected before any job or model call; it corrected the request without coaching. Exactly **one** real Codex consultation ran, completing in approximately **150.4 seconds**. After launching one native background waiter, the agent's exact `Waiting.` final response completed at **22:43:03.125 UTC**. An independent UI observation at **22:43:20.817 UTC** showed the waiting response and no working, stop, or permission control while the job still had no result, more than **74 seconds after submission**.

The provider result appeared at **22:44:37.005 UTC**, after **93.880 seconds of clean idle**. Native completion automatically started a **new turn at 22:44:38.575 UTC**, approximately **1.570 seconds after the result**. Following a routine one-time tool approval, the agent retrieved the original completed job and publicly evaluated its static-review conclusions and limits before finishing. Private checkpoint inspection found the completed receipt and zero outstanding jobs in the original turn; the wake turn's reviews, outstanding jobs, and work state were empty. This proves later-turn retrieval without cloning fresh-review credit. Independent verification found all **four source-file hashes unchanged**, with no edit, TaskOutput, extra Bash, or test execution. The final report accurately bounded its static review, and the UI was inactive afterward.

A separate closing Codex review of the current implementation completed and was retrieved with no must-fix blockers. It noted that verifying watcher launch does not prove future process liveness: a failed watcher must lead to polling the same job. The reviewer received supplied validation results; it did not independently execute the tests.

| 0.2.6 acceptance gate | Status |
| --- | --- |
| Automated tests and lock check | Passed: 113 tests with strict resource warnings; lock check passed. |
| Marketplace update and packaged-byte comparison | Passed: all twelve files match; skill 7,857 bytes. |
| Updated live MCP tool definition | Passed in a fresh native GLM-5.3 Max session. |
| Independent edits while consultation is pending | Passed in the fresh replay by edit/result timing. |
| Native active completion alert and prompt retrieval | Passed in the first directed trial. |
| Native idle completion wake | Passed in the third read-only trial: independently observed idle period, then automatic new turn. |
| Later-turn retrieval preserves original receipt scope | Passed: original receipt completed; wake turn received no cloned review credit. |
| Read-only idle trial preserves reviewed files | Passed: all four hashes unchanged; no mutation or test execution. |
| Advice-dependent work waits for retrieval/evaluation | Passed in both directed coding trials. |
| Directed short reactive task finishes after advice use | Passed twice; frozen tests and independent prefix-budget grading passed. |
| Planned long-session fresh final review | Unverified; historical retained-context limitation remains. |

At 0.2.6, full recording remained off pending consent. That source change did not repair the historical retained-tail failure, prove long-session full context, or establish another host's push support.

## Local checks

At 0.2.0, all **70 automated tests** pass with simulated providers, and the script lock check passes. Tests include native metadata over real stdio MCP transport, a canary present only in an earlier tool result, frozen snapshot forwarding after the host log changes, full tool schemas, scope/hash checks, secret/reasoning exclusion, media-omission reporting, streaming progress, fixed deadlines, bounded output, and process/pipe cleanup. These checks are separate from live autonomous acceptance.

All **82 tests** pass for 0.2.1, including native scope-before-export, retrieval receipts over stdio MCP, malformed hook CLI input, concurrent checkpoint processes, stale-advice rereads, partial-write tracking, and failure reporting. Resource warnings were treated as errors. The lock check passes.

Version 0.2.2 passes **85 automated tests** and the lock check, including the Codex context-file transport. Installation, controlled provider diagnostics, and autonomous stage results are reported separately above. These tests do not cover the newly observed retained-tail failure.

Version 0.2.3 passes **96 automated tests**, treating resource warnings as errors, and the lock check. Coverage includes verified-unavailable scope, full-request validation before marker creation, attempt timing/edit-revision binding, separate unavailable state, invalidation by later edits, no early unlock, and truthful final Stop behavior. Installation was checked separately; these simulated tests do not establish live agent behavior or complete retained input.

Version 0.2.4 also passes **96 tests** and the lock check after the terminal-output correction; its two added cases are within an existing test method. Installation was verified separately.

Version 0.2.5 passes **97 tests** and the lock check after LF-only framing and stronger parser cases. Fresh/resume CLI checks and marketplace installation passed separately.

Version 0.2.6 passes **113 tests** in **11.269 seconds** with strict resource-warning handling, plus the lock check. Marketplace installation and the fresh session's actual tool definition passed separately. Two directed coding trials passed active alerts, retrieval, evaluated use, correct finishes, and independent grading; the replay proved independent editing while pending. A third read-only trial passed clean idle wake and later-turn retrieval with original-turn receipt scope preserved.

## Limits

Version 0.2.9 passed installation, 145 plugin tests, the lock check, and fresh natural Desktop acceptance: three completed reviews with exact waiters/reads, actual advice use, a fresh 75-message final review, and normal task completion. The fixture's seven tests and independent bounded mutation passed their respective expectations. Full-retention readiness was observed at 87 messages during an approved test; recording was restored OFF afterward. The user later authorized leaving recording ON, with full retention verified at 91 messages. Version 0.2.10 requires full retention for every new native consultation; installation, 148 plugin tests, the lock check, and the read-only native Claude advice lifecycle passed. Its 511-word full response missed the 500-word limit despite a 490-word specification. This does not change the stopped 0.2.2 trial or establish every task's behavior. Live unavailable-review handling, other hosts, Git-source installation, and other operating systems remain untested. Shell/delegated mutations remain policy-only, and watcher launch does not guarantee ongoing liveness. Reported model and effort are requested settings, not independent verification of the served model. Raw transcripts, native session identifiers, and advice stay outside this repository.

See the subsequent [native Claude Advisor analysis](claude-advisor-analysis.md) for the trigger-policy comparison.
