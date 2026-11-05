# Aurora preview — November 5, 2026 · release 54

This refresh brings the public snapshot from release 45 (runtime through Implementation 44) through **Implementation 53**, plus a release-54 GUI settings-readback repair and updated setup/upgrade guidance. The repository retains its original `Aurora-11-04-2026` name. This is still a Windows developer preview for supervised use.

## New since the previous public release

- **Longer Pokémon runs through normal workers.** A completed 25-minute FireRed run won the rival battle, healed, won three wild battles and reached Viridian Pokémon Center. A separate later 20-minute Terra-low continuation delivered Oak's Parcel, received five Poké Balls, verified the Pokédex menu and then completed the goal. Aurora ran its production command, capture and inference scheduler paths; a bounded supervisor owned setup/shutdown and target guards, not per-turn gameplay decisions.
- **Optional bounded subscription transport.** `SET_SUBSCRIPTION_POLICY(bounded)` adds an owned inference process, 90-second read-idle limit, 180-second inference deadline and cancellation during blocked reads. It validates complete output, discards partial output on failure and never automatically replays or switches to API billing. `legacy` remains the default. Auth/catalog preflight has separate parent-process timeouts; local cancellation is not confirmed remote cancellation. The setting is session-only and affects the next request.
- **Optional task outcomes and budgets.** A task can declare done/wait/approval/error and stop automatic continuation. Operator-set command allowances reserve complete batches; reported-token thresholds stop after known usage reaches the limit. Missing usage stays unknown, the last request may overshoot, and a model's completion claim is not independently verified success. These are not hard dollar caps.
- **Correlated progress and task transitions.** Command, receipt, frame and model-request identities plus local latency observations help explain stalls. Independent carry/discard/hold choices manage attributable old-task plans and proposals. Operator/unattributed or already-reserved work is preserved; this does not implement durable queue recovery.
- **Planning controls with compatibility paths.** `SET_HIERARCHY_DISPATCH(advisory)` prevents stored Level 1 hierarchy from dispatching. `SET_HORIZON_SYNC(preserve)` keeps explicit horizons separate. Both retain legacy defaults and supported saved-profile behavior. Goal previews show IDs/labels clearly; Init now explains goal labels and dedicated horizons. A zero CLI heartbeat stays off.
- **Scene and trial repairs.** Generic battle tutorial/result dialogue no longer conflicts with a fresh explicit battle scene in the repaired case. Several prior setup/connection failures are documented separately from completed runs; they are not counted as endurance passes.
- **GUI settings regression caught before publication.** The new subscription policy was absent from the exported models snapshot, which made GUI Preview/Apply reject even unrelated settings as incomplete. The export now includes the effective policy. The guarded panel regression checks all registered values plus subscription Preview/Apply/Undo while inference remains paused.

Inventory is **387 command bindings / 157 reviewed argument contracts / 48 shared settings / 24 views**. A binding is not necessarily a unique action; most commands remain outside the reviewed typed subset. Existing commands, settings, aliases and legacy modes remain available. No broad default/profile promotion is made on the strength of one trial.

## Retained from the earlier refresh

Conversation has queued/awaiting messages and delivery stages, revision-checked edit/pin, readable detachable mini-preview and current/retained/history views. Switchboard has draft/apply receipts, shared Preview/Apply/Undo, context inspection and scoped reset. Header/layout/scroll/repaint fixes improve usability, with broader display qualification still open.

Recursive goal save/load, nested IDs and failure-preserving imports are repaired. Everyday goal/note/history commands have clearer contracts. Optional command-driven capture, reviewed text-result continuation and request-time duplicate-Init removal reduce avoidable waits while retaining compatibility behavior. Capture metadata records acquisition identity/time, target/origin and transforms; optional deadlines fence late publication. Mouse input still uses literal desktop coordinates, so inspect calibration.

Aurora-owned ChatGPT sign-in/inference and a Sol → one Astra medium turn → Sol low restoration were verified on the development account. API keys remain an independent billing route; there is no automatic subscription-to-API fallback.

## What the tests establish

| Evidence | Result and boundary |
| --- | --- |
| Production-worker FireRed, Implementation 50 | **1,500.82 seconds / 198 responses**, uninterrupted timed attempt; rival victory/healing/Route 1/Viridian progress. Three earlier diagnostic attempts are separate. Inputs released and owned processes exited normally. |
| Four-horizon Terra-low comparisons, Implementation 51 | Completed paired 15-minute retries: **92 and 127 responses**. Outcomes differed; detailed memory added about 12.7% memory-envelope characters and still retained stale steps. One temporary review restored low effort afterward. No conclusive best profile. |
| Checkpoint maintenance comparison, Implementation 52 | Two planned 15-minute runs ended at **635.54s / 71 responses** and **868.90s / 113 responses** with subscription read timeouts. One obtained Oak's Parcel. Neither is a completed 15-minute pass. These failures motivated bounded transport. |
| Bounded subscription continuation, Implementation 53 | **1,201.04 seconds / 117 completed responses / 118 requests**, returned model `gpt-6.1-terra`, requested low effort. Parcel/Pokédex visually verified before goal completion. No connection failure or failed assistant batch; timed shutdown cancelled the final request and closed its child. One operator checkpoint save supplied no gameplay decision. |
| Frame/prompt evidence in that continuation | All 117 image requests matched saved production-frame identity/fingerprints/owned target; one intentional text-only readback request. One Init per request. Median completed-request latency 4.375s, p95 33.328s, maximum 76.062s. |
| Memory persistence | Native saves and offline full-document/object round trips preserved completed goal ID/priority/importance and horizon content. Immediate/short plans changed; medium still retained a completed step. Timestamped past-goal history recorded completion even though the manual diary stayed old. |
| Offline subscription boundary | Ten synthetic localhost/process tests cover slow completion, idle/deadline failure, cancellation, partial output, crashes, validation, cleanup and explicit new-request recovery. No real credentials/provider calls in those tests. |
| Release-54 exported build | **778 regression tests passed** after the settings-snapshot repair; 144 guarded runtime receipts, 180 everyday-command checks, 50 readback checks and hidden Tk across 24 views/36 synthetic Dashboard refreshes. Policy Preview/Apply/Undo passed with no callback errors. Python 3.12.8 isolated environment on the development Windows host; no new live-provider/gameplay or displayed-pixel acceptance is implied. |
| Websites and other PCs | Screenshot/mouse/keyboard primitives support supervised experiments. Comparable production-worker website acceptance, a second-PC installation and general mixed-DPI input calibration are **not yet established**. |

The 25-minute and 20-minute results are separate scoped trials, not a 45-minute session. ROMs, copied saves, raw transcripts and screenshots are private test artifacts and are not distributed. This publication performs offline packaging/validation; it does not claim another live run.

## Still unfinished

1. Coherent memory projection across snapshot/pinned context, recent-journal selection, omitted counts, entry ownership/status and stale-plan reconciliation. Near/extra-long horizons, typed notes, enforced per-category caps and fuller Horizons profiles remain planned.
2. Durable queued-message/task recovery, queued cancellation and deliberate retry after restart (CP1c). Same-task resume and broad crash/account-switch recovery remain incomplete.
3. Optional strict parsing/dependent batches, remaining mutation contracts and fuller worker/queue accounting.
4. Production-worker website acceptance, wider display/UI/input checks, optional game-client/aspect-preserving capture, duplicate-capture coalescing and predictable-dialogue batching.
5. Retrieval publication/concurrency, full ordinary-message/person search and immutable versions → supersession → as-of state → replay. Timestamp filters are not historical state reconstruction.

## Package and setup

The public snapshot contains runtime/UI source, launchers, dependencies, offline tests, command/reference tools and five functional UI artwork files. Optional read-only integration adapters remain available without being required for basic chat. Personal notification/email helpers, private history/reports, runtime state, screenshots, auth caches, API keys, emulator/ROMs and game saves are excluded. The export is checked for configured secrets, credential patterns, personal identifiers and unexpected media; public Git history is checked separately. These are scoped disclosure checks, not a formal security audit.

Use [UPGRADING](UPGRADING.md) to stop/rename an older copy and install into a fresh folder, [the human guide](README_FOR_HUMANS.md) for GUI/shell use, and [the AI guide](README_FOR_AI.md) for setup assistance. Keep your own credentials private and start paused. The active [roadmap](docs/notes/aurora_runtime_roadmap.md) distinguishes delivered controls from future work.
