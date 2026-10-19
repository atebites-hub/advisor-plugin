# Roadster benchmark

An October 2026 local comparison used two isolated ZCode Desktop sessions, both requesting GLM-5.3-Flash at Max effort. The task was to build a detailed interactive Three.js Roadster from the same frozen reference packet and pinned dependencies. Advisor was version **0.2.14**.

| Candidate | Condition | Native task time | Visual preference |
| --- | --- | --- | --- |
| K | Without Advisor | 78.30 minutes | |
| L | With Advisor | 221.32 minutes | Preferred |

The user selected L before the condition mapping was revealed. The assisted run took approximately **2.83 times** as long. Times include model, tool, and consultation waits; later operator observation and cleanup delays are excluded.

## Advice lifecycle

All three consultations completed through the requested Claude Opus 5.5 Max profile, without fallback or provider failure. The worker retrieved each original result and evaluated the advice. Completion left no outstanding jobs, unread results, or dependency holds.

The early review preceded the first source edit and changed the geometry and lighting approach. A completion review identified mirrored-door hierarchy, interior-camera targeting, and rear-deck material problems; subsequent edits repaired them. A fresh final review prompted additional verification and narrower console claims.

## Isolation and validation

The runs used fresh isolated histories and independent copies of equal prompts, references, and dependencies. OS containment checks denied access to the other run, prior candidate work, and controller data. Neither run received operator coaching or source repairs after submission.

Both finished naturally. Nonstopping 60-minute snapshots were preserved, and both outputs were frozen before source or visual evaluation. Independent unchanged production builds passed. Both WebGL canvases rendered in Safari; selected camera, door, wing, light, and interior controls were exercised.

## Limits

This is one pair with unequal runtimes and a subjective visual preference, not a general improvement percentage. The operator knew the condition mapping. Requested model identities were not independently attested. Advisers reported they could not see reference images or screenshots.

Exhaustive geometry, pointer interaction, accessibility, cross-browser behavior, and frame performance were not independently tested. K recorded a shadow-map deprecation fallback warning. No candidate uncaught error appeared in the inspected console buffer; this does not establish an error-free console. L's final description claimed 29 loft stations, while its saved source contained 23.

Raw sessions, advice, snapshots, and benchmark artifacts remain private outside this repository.
