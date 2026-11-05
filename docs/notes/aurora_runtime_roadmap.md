# Public preview roadmap — November 5, 2026

This is the current public queue, not the private chronological development ledger. Read RELEASE_NOTES.md for evidence and limitations. Preserve all commands, legacy options and Advanced settings.

| Order | Status and completion target |
| --- | --- |
| CF1a capture identity | Implemented and guarded-tested: acquisition timestamps/frame IDs, request generations and stale publication/cancellation boundaries. Native qualification remains. |
| CF1b geometry/lifecycle | Implemented and guarded-tested: source rectangle, target identity, resize/DPI metadata, optional deadlines/attempt limits and active acquisition diagnostics. Native mixed-DPI input calibration and hard interruption of stuck OS calls remain. |
| CF2c — next engineering work | Reviewed receipt delivery/correlation and initial accounting are implemented as optional first slices. Finish explicit done/wait/approval/error outcomes, broader latency/progress and optional operation/usage limits. |
| CP1c | Durable queued input, restart reconciliation, queued cancellation and explicit retry without duplicate effects. |
| CF2d / 4B4 | Optional strict parsing, dependent batches and remaining goal/note/history mutation contracts. |
| Acceptance | With deliberate operator scope: normal production-worker local website task, five-minute gameplay, then ten-minute endurance after repairs. Include interruption, restoration, auth recovery and display checks. Prior gameplay used a test controller. |
| R2b2b / G1 | Retrieval concurrency/publication and preservation of manual versus hierarchy-derived horizons; can proceed offline while native testing is paused. |
| Later options | Retrieval quality, ordinary-message/person search, fuller horizons/notes, immutable versions → supersession → as-of views, then replay and richer validation comparisons. |

Cross-cutting: keyboard/mixed-DPI/repaint polish, short mini-preview layout, long-session OAuth/account switching, optional idle/pre-inference decay and measured prompt/receipt cost. Existing time/turn limits are not spend caps. Current context is not a complete inference replay. Timestamp filtering is not as-of reconstruction.

Fixed: recursive goal persistence/nested IDs, snapshot-ID collision, multiple scene false positives, subscription inference/restoration within the tested account, and the duplicate-Init optimization as an optional path. Not implemented: date-range message deletion, full person/conversation search, near/extra-long horizons or durable versioned memory.
