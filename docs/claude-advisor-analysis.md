# Claude Code Advisor trigger analysis

The client inspection on October 16, 2026 used REA and focused static reads of installed Claude Code **2.1.301**. That inspection made no model requests or configuration changes. Later plugin changes and controlled provider diagnostics are identified separately below.

## Main finding

Claude Code supplies explicit review checkpoints. Its packaged Advisor instructions request a consultation after orientation and before substantive work, before declaring completion, when stuck, and when changing approach. Longer tasks receive both an early and a final consultation checkpoint. The instructions also ask the executor to evaluate advice against evidence and reconcile conflicting evidence with another consultation.

This differs from Advisor 0.1.2's rule, which asked the working agent to consult only when consequential uncertainty remained. A model that believed it had settled its questions could finish under that rule without consulting. The native policy does not require that admission before its early and final reviews.

## Observed client flow

The inspected executable is `~/.local/share/claude/versions/2.1.301`, SHA-256 `1f04c69e1c24e4d0a716a863af0aad8fc64d49a499334c29701f073700276b99`.

| Step | Static location: function, absolute file byte offset | Behavior |
| --- | --- | --- |
| Configure | `Drt`, 217269098 | `/advisor` validates and saves the consulting model; the command does not itself perform a consultation. |
| Resolve | `NZo`, 212552954 | Resolves the setting and model compatibility, then tracks the conversation's advisor availability. |
| Announce | Module-local `x`, 212555104; caller at 212702017 | Creates an `advisor_tool` availability attachment and appends it to conversation history. |
| Inject guidance | Attachment renderer at 208662987; `nvs`, 202273112 | Selects the full `Qh` Advisor instructions for an enabled, non-abbreviated announcement. Later announcements can use a short reminder. |
| Expose tool | Request builder at 207167029 | Adds the `advisor_20260301` server-tool definition with its configured model. |

Eligibility includes feature state, provider support, model compatibility, and capability ranking. The full instructions are not simply reinserted every turn. Conversation declarations can remain pinned until clearing or compaction; supported tool-change paths can update availability.

These paths establish context injection and tool exposure. They do not directly schedule a consultation when a local uncertainty detector fires.

## Documented server behavior

The model emits an empty-input advisor call. Anthropic supplies its transcript and returns advice to the executor, without requiring the executor to assemble a context packet. This is a server capability, not access an ordinary MCP plugin automatically receives. [API mechanism](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#how-it-works)

That quoted context includes the executor's system prompt, tool definitions, earlier turns and tool results, and text produced so far in the current turn. The advisor receives its own system prompt and runs without tools. These details come from the documented server contract; static client inspection cannot establish the server implementation.

Anthropic acknowledges under-calling on coding tasks and recommends stronger timing instructions. It also warns that reminder nudges can create poorly timed calls and conflict with uncertainty-only restraint. The installed checkpoint text closely follows that published guidance. [Coding guidance](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#prompting-for-coding-and-agent-tasks), [nudge tradeoffs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#mid-conversation-nudge-for-under-calling-executors)

## Implications for this plugin

| Aspect | Native Claude Advisor | Advisor 0.1.2 | Advisor 0.2.0 in ZCode |
| --- | --- | --- | --- |
| Timing | Early/final reviews, difficulty and approach changes | Consequential uncertainty | Early/final reviews, difficulty and approach changes |
| Invocation | Empty-input server tool | Explicit provider, context and identifiers | Explicit provider/question; native metadata supplies session context |
| Result handling | Server returns guidance | Background job and `read_advice` | Background job, bounded activity reporting and `read_advice` |
| Context | Server supplies transcript | Working agent supplies packet | Frozen current semantic model-input snapshot |

The user subsequently approved checkpoint-based review guidance, implemented in Advisor 0.1.3 while preserving uncertainty-driven escalation. It adds early and final reviews without a new scheduler or hook. Claude advising subprocesses explicitly disable their own native advisor tool, preserving the recursion boundary. Explicit selection of one fixed advisor and private consultation state remain. See the [ZCode report](zcode-smoke-test.md) for versioned live results.

The subsequent packet inspection found a practical difference: the worker sent a detailed design summary and claimed checks, without implementation, contract text, diff, or test output. A no-tools advisor could review that design but could not verify actual code. Advisor 0.1.5 therefore required those materials in the explicit packet and disclosure of missing evidence; it did not receive the host transcript automatically.

## Authorized ZCode context transfer, 0.2.0

The user then authorized transfer of the current ZCode session. Advisor 0.2.0 uses native request metadata to bind the workspace, session, turn, and exact consultation arguments. It captures the retained system instructions, messages, tool definitions, calls/results, and visible current-response text from that model input. The frozen snapshot is hashed, privately stored, and accompanied by a coverage receipt. Missing or ambiguous current input fails explicitly; an older turn is never substituted. No host source changes are required. See the [context-transfer contract](context-transfer.md).

This transfers current semantic input, not an identical native wire request or discarded pre-compaction history. Protected reasoning, credential headers, and unrelated sessions are excluded. Files never read into the working session are not implicitly available to the advisor. Other hosts continue to require explicit context packets and remain untested.

## Deadline evidence

A controlled replay of the earlier review completed in **603.235 seconds**, with its first stream byte at **2.093 seconds**, using the same Claude Opus 5.5 Max profile. The trace showed no errors, retries, or tool calls. This supports active, lengthy inference as an explanation for the earlier missing completion and shows that a 300-second cutoff can terminate a successful review. It does not establish the original run's internal state.

Advisor 0.2.0 raises the default absolute deadline to **1,200 seconds (20 minutes)** without reducing Max effort. It drains bounded provider streams and reports activity counts without exposing protected content; activity does not extend the deadline. Capture limits are 32 MiB stdout and a 4 KiB stderr tail. Manual tool input retains a 1 MiB bound, separately from the 8 MiB assembled-context bound. No automatic retry or fallback is introduced.

Installation and fresh autonomous ZCode validation of 0.2.0 remain pending. A successful controlled provider replay does not demonstrate the working agent independently retrieves and uses advice.

Policy strength and invocation effort are plausible explanations for our zero-call ZCode trials. This investigation does not establish their causal effect on GLM or guarantee that copying the instructions will produce reliable calls.

## Evidence and limits

- REA Mach-O evidence: `ev_3e736cb393d32364848add33df43e30f1446cb02f3deb40c4b0ab8e7bb150c94`. It identifies the executable and its `__BUN` section.
- REA selected-source analysis: `ev_5a7bc3cd3685736627835022929092a0bfe8f7c44a45bcf39e80098fce9c54e8`. The derived source candidates retain original byte ranges and hashes. Semantic graph coverage is partial because of node limits and unselected modules; focused byte reads support the locations above.
- Recovered source and the exported evidence bundle remain outside the repository in a temporary analysis directory. No packaged application source or consultation memory is committed here.

The original client analysis was static and corroborated by official documentation. It did not measure model compliance, server internals, or consultation frequency in the user's live Claude sessions. The later policy changes, context adapter, and controlled replay are separate work and do not guarantee reliable autonomous invocation.

## Hidden-thinking progress in Claude Code 2.1.301

The shipped CLI emits `system/thinking_tokens` with approximate running and incremental estimates while thinking text is hidden. Advisor 0.2.14 recognizes finite, positive advances as activity without retaining reasoning or publishing token estimates. Repeated or invalid counters and retry notices do not extend the idle deadline. The estimate restarts for each content block; the CLI forwards that block's start before its generated progress events when partial messages are enabled.

Static inspection of the pinned 2.1.301 binary and content-free live probes verified these event shapes. Fresh and resumed neutral calls completed with both 1,024-byte inputs and 139,130/656,314-byte inputs; the larger sizes approximate earlier snapshot geometry, not its unknown provider-input sizes or review complexity. These probes establish a missed progress signal, not the exact activity of a historical timed-out process. The default idle limit remains 1,200 seconds; explicit absolute deadlines still apply.
