# Verified usage handoff

Set `"usage_fallback": true` in `~/.config/advisor/config.json` to authorize one alternate advisor after verified account usage exhaustion. It defaults to false and accepts only a JSON boolean. `advisor_status.usage_fallback.enabled` reports the current setting. Enabling this can send the same frozen context to both services sequentially and consume both accounts' allowances.

The working agent chooses the primary. Claude Opus 5.5 Max can hand off to GPT 6.1 Sol Max, or vice versa. Advisor preserves the original job, snapshot, question, dependency hold, and watcher. It uses each provider's separate native conversation and successful-consult budget. An explicit total deadline covers both attempts, including verification; the alternate gets no fresh total allowance. Idle tracking starts anew for each provider.

`provider_attempts` records the bounded, redacted exhaustion cause before the alternate starts. Pending, failed, interrupted, and completed reads retain it. Completed results identify `requested_provider` and the actual answering `provider`. A journal-write failure prevents further launches. Both exhausted, or any alternate failure, leaves the review incomplete. Only retrieving the original job's completed advice can release its declared paths; the worker must also evaluate and verify it.

Settings freeze at submission. Changing them cannot restart or alter an existing job. Unsnapshotted legacy jobs keep handoff disabled. Failed jobs are never automatically relaunched.

## What counts as exhaustion

Only a normally terminated, fully captured POSIX invocation can qualify. Windows handoff detection is unsupported because its abnormal exits can have positive status codes; ordinary consultations still work without automatic switching:

- **Claude:** a unique final result with `is_error: true`, `api_error: "usage_limit_reached"`, and `api_error_origin: "first_party"`. A generic HTTP 429, warning event, assistant text, or unknown origin is insufficient. The result subtype alone is not proof: Claude can emit subtype `success` for an error result.
- **Codex:** `exec --json` omits the typed error code. Its failed-turn message must match a known consumed-usage template **and** its own fresh terminal rollout metadata must report `usage_limit_exceeded`. The proof binds thread, turn, private invocation directory, fixed model, Max effort, timestamps, and terminal message. Text alone cannot qualify because another error can use arbitrary wording.

Timeouts, process signals, cleanup failures, authentication, capacity/transient rate limits, ambiguous errors, context failures, model entitlement, and Advisor's local consultation budget never switch providers. Missing, changed, torn, conflicting, or oversized evidence means unknown and no switch. An underlying CLI can still perform its own retries.

## Codex metadata privacy and limits

With handoff enabled, Advisor locates only the current Codex thread's uncompressed `sessions/YYYY/MM/DD/rollout-…-<thread>.jsonl`. Lookup is bounded to the UUIDv7 creation date and adjacent dates. A resumed thread is snapshotted before launch; append-only identity and boundary checks reject replacement or truncation. Safe descriptor-relative, no-follow file access is required; unsupported platforms/layouts disable this detection without preventing ordinary advice.

The parser projects only lifecycle/error metadata. It skips message, tool, and protected reasoning spans before semantic JSON decoding; none are persisted or returned. Verification has finite byte, record, depth, directory, and time bounds. It makes no account/model request and reads no credentials or unrelated session contents. This assumes the native CLI is a trusted append-only writer; it does not authenticate a malicious local CLI or defend against a same-user attacker.

Detection is based on Claude Code 2.1.301 and Codex 0.162.1 evidence. Future schema or wording changes can fail closed. The [Claude SDK message contract](https://code.claude.com/docs/en/agent-sdk/python#resultmessage) and pinned [Codex error protocol](https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/protocol/src/codex_error_info.rs) distinguish typed errors from plain text. Synthetic quota fixtures verify switching; they do not establish actual account exhaustion.
