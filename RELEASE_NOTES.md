# Aurora 2 · Preview 84 · November 6, 2026

Annotated tag: `preview-2026.11.06-r84`. This cumulative preview includes implementations 55–84 after public Preview 54. [Upgrade instructions](UPGRADING.md) and [version identity](VERSIONING.md).

## Changes since the previous public snapshot

- Dynamic task flow: retained operator objectives, exact-task cancellation/context steering, clearer progress/outcomes, optional batch-end capture, capture-only handling and bounded observation waits. Legacy modes remain available.
- Memory: selectable recent-journal ordering, stale-goal/completion reconciliation and explicit horizon-to-goal identity. Planning entries remain plans rather than automatically executed commands.
- Recovery: optional durable queued input, restart holding, explicit cancellation/retry, terminal-text compaction preserving identity hashes, exact-receipt reconciliation, readiness/diagnostic acknowledgement and capacity reporting.
- Execution inspector: frozen correlated task/request/frame/action/receipt evidence, exact artifact checks, explicit saved snapshots, opt-in bounded recording, historical browsing and explicit previewed retention. Historical inspection never replays desktop actions.
- New archive command: `PREVIEW_INPUT_RECOVERY_ARCHIVE([limit=1000])` reports deterministic selected identity records, bytes/digest and hypothetical capacity savings. No archive is written or activated; no duplicate hashes are removed and no migration occurs.
- Saved-defaults repair: capture-command policy now round-trips through the shared profile contract; omitted fields in old partial profiles retain their effective values.
- Consistent release title/build metadata, annotated-tag conventions and a file-hashed sanitized public snapshot. Shorter public setup guides explain paused startup, cancellation, defaults and separate-folder upgrades.

Inventory: **410 bindings / 180 reviewed contracts / 54 settings / 24 views**. These counts describe breadth; reviewed contracts are a subset of command bindings. Existing commands, aliases, legacy states and optional settings remain.

## Evidence and limits

Earlier production-loop subscription tests used provider-reported `gpt-6.1-sol` at low effort. A scoped 20-minute comparison completed parcel delivery and used 173 game commands, including 25 two-game-command batches, with no failed assistant batches or reviewed memory commands. One Init, retained operator projection and image were present in each of 161 requests. Batch-end capture retained 162 frames versus 303 for the matched legacy-policy run; selected frames remained fresh. This is one stochastic comparison, not proof of general speed or full game completion. Pewter was not reached; ledges/dialogue still exposed hesitant behavior.

Prior subscription inference and one-turn Sol → Astra → Sol restoration were verified in scoped tests. Long-session OAuth refresh, account/model availability and broad desktop/browser acceptance remain open. No automatic API-billing fallback is promised.

Preview 84 is checked with unit tests, guarded fake-provider/synthetic-capture runtime fixtures, hidden-Tk regressions and sanitized-export checks. Native input/capture/gameplay is currently paused after reported lag. Offline success does not qualify visible layout, display calibration or extended gameplay. No new live run is claimed for this release.

Next recovery stage: verified archive activation/lookup with migration and interruption tests. Then granular memory/projection and outstanding retrieval/command contracts. Exact historical inference replay, complete message/person search and fully editable flow graphs remain later work. See [roadmap](docs/notes/aurora_runtime_roadmap.md).

## Distribution

Windows-first technical preview. Python 3.11/3.12 recommended. Public history is separate from private development. Personal notes/reviews, credentials, runtime state, screenshots, recordings, ROMs and saves are excluded; only named UI artwork ships. Automated pattern/configured-secret scans reduce risk but are not a formal security audit.
