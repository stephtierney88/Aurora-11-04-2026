# AI operator and setup guide

Read README.md, README_FOR_HUMANS.md, AGENTS.md, UPGRADING.md and RELEASE_NOTES.md first. This Windows preview intentionally retains a broad command/settings arsenal. Preserve aliases, legacy modes, saved configurations and Advanced access. Introduce behavior through explicit profiles/toggles rather than silently replacing it.

## Setup with the human

Create an isolated Python 3.11/3.12 environment, install requirements-preview.txt, run `aurora_preflight.py --surface panel --display --json`, and select that interpreter through `AURORA_PYTHON`. Launch `launch_aurora2_ui.cmd`; start runtime paused. Reuse securely configured credentials without printing or copying them. The human completes OAuth consent. Verify the intended auth route and actual provider-reported model where available; do not equate a display alias with routing or silently switch to paid API access.

Demonstrate chat delivery stages, Pause, Cancel work, Stop runtime and Reset to preview defaults before live actions. Inspect monitor/crop/DPI/target coordinates with explicit human scope. The author's native testing pause is not permission to operate a new user's desktop; obtain their task scope and use bounded tests. Never run `live_*` scripts merely as installation checks.

## Find code and commands

| Reference | Purpose |
| --- | --- |
| `aurora_reference_maps/runtime/overview.md` | Lightweight runtime map. |
| `aurora_reference_maps/runtime/runtime-function-skeleton.jsonl` | Implemented runtime functions. |
| `aurora_reference_maps/runtime/control-plane-function-skeleton.jsonl` | Shared service functions. |
| `aurora_reference_maps/ui/ui-lite.md` | Control Panel map. |
| `aurora_reference_maps/commands/commands.json` | Searchable command catalog and exact syntax. |
| `aurora_command_contracts.py` | Reviewed admission/receipt contracts; these cover a subset of bindings. |
| `aurora2_init.txt` | Current startup instruction text. Inspect effective prompt diagnostics to confirm delivery. |

Current inventory: **410 command bindings, 180 reviewed contracts, 54 settings, 24 views**. Discover exact command signatures instead of guessing punctuation. Multiple independent commands can be batched within configured bounds; stop at uncertainty or a new visual decision. A fresh screenshot requires a subsequent inference call, even when presented as continuation of the same visible task. Check receipts, effective settings and observation freshness before further input. Waiting needs a condition and deadline; blocked commands need explicit recovery, not blind repetition.

Immediate/Next/horizon goals are planning context, not automatic executable queues. Old and fuller profiles remain selectable. Priority and importance describe separate concepts. Retained operator objectives preserve task intent; editable assistant plans do not become operator instructions. Respect source roles and cancellation.

## Recovery and inspection

Legacy session-only delivery remains available. Optional durable input recovery holds uncertain/interrupted work and requires explicit retry; identity hashes guard duplicates across restarts. Compaction removes eligible terminal text while retaining identity protection. `SHOW_INPUT_RECOVERY_STATUS()` is read-only. `PREVIEW_INPUT_RECOVERY_ARCHIVE(1000)` returns selected hashes/counts, candidate size/digest and hypothetical savings in durable mode; it writes no archive and frees zero actual slots. Never infer that a preview migrated storage.

Execution snapshots/recordings preserve bounded inspection evidence and report gaps. Historical running/queued status is not the present outcome. Loaded inspector state never replays actions. Reconciliation, retention and task-context steering have versioned/exact-ID boundaries; stale or uncertain results require fresh inspection. Do not automatically resend after an unconfirmed outcome.

## Development checks and housekeeping

Run appropriate pure unit tests, then guarded `offline_*` fixtures. Hidden panel checks use synthetic data, disabled input/capture/providers and owned temporary resources; they do not establish native visual or long-session success. Regenerate maps/skeletons with `regenerate_aurora_skill_refs.ps1 -Force`, then `-Check`. Generated references describe implemented code only.

Track child PIDs/start times, ports and exact scratch paths; clean only owned resources. Keep credentials, captures, logs, recovery/recording stores and game files out of Git. Keep unknowns explicit and preserve the user's other applications. Release identity and lineage are documented in [VERSIONING.md](VERSIONING.md).
