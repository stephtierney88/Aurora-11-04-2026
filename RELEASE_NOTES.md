# November 5, 2026 preview refresh

Compared with the previous public snapshot, commit `1ba4d49` from November 4. This refresh includes the private runtime/Control Panel work through Implementation 44, with release packaging and documentation cleanup. Old commands, aliases, valid legacy settings and advanced controls remain.

## Visible changes

- **Chat feedback:** submitted/queued messages remain visible; Outbox and Awaiting reply distinguish ingestion, preparation, request start, response, failure and cancellation. Session-local state is not advertised as durable delivery.
- **Readable conversation preview:** text excerpts, click-to-jump, docking/collapse/popout, current-context highlights and model-window estimates. The old compact colored map remains selectable.
- **Message editing:** revision-checked Edit / pin, sender/editor attribution and explicit stale-target failures. Existing PIN/edit/exact-timestamp-delete commands remain.
- **Switchboard and layout:** compact header, clearer unapplied drafts, hover contrast, measured flow cards, receipt inspection and refresh/scroll stability fixes. Full capabilities remain behind Advanced/raw commands.
- **Agent controls and sign-in:** prominent OpenAI sign-in, model/effort controls and explicit subscription routing. Regular speed stays the default.

## Runtime repairs and additions

- Evidence-aware scene classification handles token boundaries, negation, quoted/closed dialogue and location overlays more accurately; legacy behavior remains an option.
- Recursive goal save/load, nested IDs and failure-preserving imports are repaired. Everyday goal/note/horizon/toggle contracts now reject malformed arguments and preserve fuller text in task-flow mode. Duplicate/completed goals and unsupported TASKS behavior report truthfully.
- Multiple-command batches and command-driven screenshots reduce unnecessary pacing breaks. Post-action capture ordering is repaired; reading the result still needs another model call.
- Optional bounded task turns/time, command lookup wake and request-time Init deduplication coexist with compatibility defaults.
- New optional reviewed readbacks carry structured settings/retrieval/goal and other supported receipts into the same task's next eligible request. Task/request/batch correlation and initial usage/operation accounting distinguish reported values from unknowns; no spend cap or complete task lifecycle is claimed.
- Capture workers now preserve acquisition identity, timestamps, request generations, crop/target geometry and resize transforms. Optional deadlines/attempt limits fence late publication. Import-time capture and a cursor GDI resource leak were repaired. Guarded tests cover these paths; native multi-monitor/input qualification is still outstanding.
- Fresh-install checks found and fixed missing `tzdata` (Windows named timezones) and `websockets` (included optional OBS adapter/tests) dependencies. The old runtime smoke was updated to require truthful failure from the unimplemented TASKS command and to distinguish legacy handler failure from reviewed Boolean admission rejection.

## What the tests actually showed

| Evidence | Result and boundary |
| --- | --- |
| Ten-minute FireRed continuation | 606 seconds, 92 Sol 6.1 low requests; won the rival battle, healed, won a Route 1 wild battle and continued north. No held/uncertain inputs remained. Used the real parser/admission/subscription route with a bounded test controller and owned screenshots, not normal background capture/inference workers. |
| Subscription/model switching | Live Aurora-owned ChatGPT sign-in/inference and Sol → one Astra medium turn → Sol low restoration were verified on the development account. Account/plan availability and long-session recovery can differ. |
| Goals/history/commands | Recursive goals/horizons round-tripped during gameplay; later guarded tests cover edits/pins/deletes, both goal formats, labels, failures and cancellation. Does not establish all memory concurrency or full message search. |
| Latest private regression baseline | 700 tests passed; 50 guarded readback/continuation checks; hidden Tk checks across 24 views and 36 synthetic Dashboard refreshes. Public export validation is recorded with the snapshot publication. |
| This public snapshot | Fresh Python 3.12 Windows venv: 700 regressions passed in 216.809s, 144 guarded runtime receipts, 50 readback checks and 24-view synthetic Tk checks with no callback errors. Both preflights and dependency consistency passed. This is a fresh environment on the development host, not a second PC or a new live gameplay run. |
| Website/desktop use | Isolated test-window clicking and screenshot recognition were verified earlier. The primitives support small supervised browser tasks, but broad website-task reliability and production-loop endurance are not yet established. |

The Pokémon result is a substantial improvement over the old 83-second scene-classifier failure; it is not a blanket claim that all Pokémon situations or unattended play work well. Native gameplay testing was not rerun just to publish this snapshot.

## Still unfinished

1. Full task done/wait/approval/error semantics, broader progress/latency and optional operation/usage budgets.
2. Durable queued-message recovery, queued cancellation and deliberate retry after restart.
3. Optional strict parsing/dependent batches and remaining everyday mutation contracts.
4. Native production-loop website/gameplay acceptance, interruption/recovery, mixed-DPI input calibration and wider GUI coverage.
5. Retrieval publication/concurrency, preservation of manual versus derived horizons, ordinary-message/person search, richer horizons/notes and versioned/as-of memory.

OAuth is now tested within the scope above. “Goal persistence is broken” and “subscription inference is unverified” in older notes are superseded. Long-session recovery and production-loop acceptance are still open. See [the active roadmap](docs/notes/aurora_runtime_roadmap.md).

## Package contents

The public snapshot contains relevant runtime/UI code, launchers, dependencies, offline tests, reference tools/maps and five UI artwork files. Personal notification/email helpers, private reports/history, runtime state, screenshots, auth caches, API keys and game assets are excluded. Public Git history is checked separately for credential patterns and non-artwork media. The private repository retains its existing test evidence; none is merged into public history.

Use [UPGRADING](UPGRADING.md) for a fresh-folder replacement and [README_FOR_HUMANS](README_FOR_HUMANS.md) for GUI or shell setup.
