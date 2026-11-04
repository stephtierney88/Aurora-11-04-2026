# Aurora 2 Control Panel Lite Map

## November 4 — display onboarding / Implementation 25

`aurora_preflight.inspect_display_environment` reads caller geometry without runtime import/capture/input; its result does not establish runtime coordinate calibration. `aurora_panel_layout.fit_popout_window` clamps selected popouts and handles negative monitor origins through absolute WinAPI placement. Main paused GUI startup uses a 2-second capture interval; other profiles and all capabilities remain. See the human/AI setup checklist for startup scale, resized screenshot versus desktop coordinates and incomplete mixed-DPI support. Runtime import-time capture and per-frame transform provenance remain roadmap work.

November 4 final acceptance: the friend-preview guides now distinguish working in-memory goal/history commands from broken goal persistence and unsupported range deletion/full horizons. The bounded FireRed run verified one mapped input and Sol/Astra restoration but stopped on a scene-classifier error; the Switchboard's displayed scene is a heuristic state, not verified visual truth. See Implementation 24; no new UI control or binding is claimed.

## November 4 — The Switchboard / Implementation 23

The 24th view lives in `aurora_switchboard.py`: default Overview flow, observed model/mode/cadence summary, hover/click context contents, expandable typed switches and command desk. Settings use the existing versioned transaction service; raw commands use correlated shared inbox receipts. Yellow prepares; green runs complete commands; placeholders cannot execute. Overview/Groups/Functions are topology views, not live traces. Loaded Init/current conversation/latest capture differ from bounded last-prepared system/memory/retrieval/current-prompt evidence. Missing evidence remains unknown. One top Conversation/Popout pair stays visible; clockwise Portal animation is cached and optional. All old Advanced/raw routes remain. Human/AI guides explain setup and limitations.

## November 4 — Conversation-first friend preview / Implementation 22

`aurora_conversation.py` builds detached bounded current/retained views from HistoryContextService state; effective drop filters apply to current rows. The panel starts on Conversation, has a composer and optional system details, and retains Chat historical logs plus all 23 views. `Reopen last view` preserves the prior startup option. New routine models default to gpt-6.1-sol low; review role defaults to gpt-6-astra medium, with older models/configurations retained. The native bounded test sequence and limits are recorded in docs/reviews/2026-11-04/implementation-22.md. General gameplay/native testing remains deferred. Core R2b2b is still next after this user-directed preview.

## November 4 — shared query preflight / Implementation 21

Search filters exposes argument_policy=legacy|strict (legacy default). `_episodic_retrieval_segments` validates the final serialized command with `aurora_retrieval_commands.build_retrieval_request`, so invalid strict numeric controls and filter/grammar errors remain visible before send. Runtime admission/execution uses that same parser; existing controls and saved/default behavior remain. Query/snapshot results flow through existing Chat/receipt surfaces. Headless controller tests only; native GUI/scaling acceptance stays paused.

## November 4 — retained result selection / Implementation 20

Episodic Search filters adds optional result_mode=legacy|retained. A separate editable handle defaults blank for legacy preview promotion. Use displayed handle binds deliberately; refresh records the displayed handle but does not overwrite the selected one. Inspect retained (Chat) sends SHOW_RETRIEVAL_RESULT(handle,0,24); Promote Selected sends the optional fourth handle argument through shared validation. Returned versus preview count and retention metadata are visible. Full source text is available beyond the eight preview items; all old controls remain. Runtime handles expire/evict/restart and fail explicitly. Native visual/scaling acceptance remains paused; AST/controller tests cover forwarding and errors. See the [retrieval reference](../../docs/reference-packs/memory-retrieval-reference.md).

## Date convenience controls — Implementation 19

Episodic Search filters now includes After, Before, Relative period and Fixed period anchor. None retains existing start/end controls; helper text explains strict boundaries, Monday-based weeks and frozen relative paging/feedback. `_episodic_retrieval_segments` uses the shared normalizer and JSON forwarding for Preview and Recall; no global profile defaults change. Resolved windows appear in retrieval summaries/evidence. Offline parser/controller wiring verified; native layout/scaling remains paused.

## Optional local web console — Implementation 18

The native Tk panel remains unchanged. `launch_aurora_validation.cmd` opens a separate opt-in service; use its printed localhost URL. `aurora_validation_web/index.html`, `style.css` and `app.js` implement Command browser and Offline validation views: full catalog filters/details, source provenance, editable/saved profiles, dry preview, guarded fake run/cancel, per-turn evidence, recent runs and JSON export. Controls use the shared headless validation service, not a second runtime-settings authority. Live provider/native input are unavailable. HTTP and DOM/API wiring are tested; rendered layout/scaling remains unverified under the pause. See [usage](../../docs/notes/aurora_validation_console_plan.md).

## Repeat-search controls — Implementation 17

Advanced repeat-search feedback exposes Off/Skip/Penalize, coefficient, operator session, action and token. Two buttons mark the last batch unhelpful and search next, or reset and search. The panel receives tokens from runtime state; per-panel sessions separate feedback. All existing weights/distribution controls remain.

## Episodic search filters — Implementation 16

Episodic now includes an expandable Search filters section: required text, match mode, field, start/end, timezone, sort, offset and string encoding. Preview/Recall use the same validated options. The visual scorer and Advanced retrieval controls remain. Result text includes effective filters, counts and matching reasons; the eight-item preview limit is explicit. Native visual/scaling QA remains paused.

## Episodic Advanced retrieval — Implementation 15

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

The Episodic view adds a collapsed Advanced retrieval section for this query only: ordinal/age time mode, half-life hours, minimum query relevance, semantic tag mix, ordinal anchor/scale and lexical/partial fallback. Preview and Recall share _episodic_retrieval_segments. Results show relevance, age and time source; the runtime summary shows effective modes and coverage. Existing weights/filters/models/shapes/promotion controls remain. This is per-query configuration, not a new persistent settings service. AST/controller and guarded state tests cover wiring; visible GUI/scaling proof remains paused.

## Pending selection correctness — Implementation 13

Pending selected-item Approve/Clear now sends stable item IDs plus the version of the displayed queue. A changed queue is rejected with a receipt instead of targeting a different index. Selection survives refresh when the same ID remains visible. Existing index/risk/category/family/raw selectors and normal/insert/replace modes remain available; old snapshots retain index fallback. Reserved/uncertain state appears beside the mode, and full entries/routes/recovery evidence are available in pending_queue and SHOW_PENDING(). Model/parent authority and sub-agent manual gates remain unchanged. AST/guarded-state verification passes; visible GUI/scaling acceptance is still open under the native-testing pause. See docs/reviews/2026-09-07/implementation-13.md.

## September 6 model controls

Modes & Models includes a Transport combobox (`chat_completions` default, opt-in `responses`) in the existing registered-settings transaction form. Model presets restore their intended transport. Current Model Status shows Responses session state, effective/request-level/API-reported effort, context usage and block reason. Queued effort remains in the next-turn plan. Astra and max effort are discoverable; supported efforts remain model-specific. Raw commands/catalog expose session reset. Legacy stateful preset profiles remain metadata. Native visual verification is still open; this slice used AST/controller tests and guarded fake-provider runtime proof.

## Current layout — September 5, 2026

- Persistent header: runtime status, inference mode, model-I/O state and freshness; activate, pause, cancel, stop and capture controls stay outside scrolling.
- `Ctrl+K` focuses the full-name view selector. All 22 views listed below remain available, including raw state, command catalog/help and both image viewers. Dashboard, Recovery and Screenshots have direct shortcuts.
- `Ctrl+,` toggles settings. Hide, dock or expand the settings pane; its divider is remembered and clamped. Search section/control labels, expand/collapse all, or reload observed values into the form.
- Each work page and settings pane scroll independently in both axes. Dashboard cards adapt to width, and receipt/detail widgets have their own scrollbars.
- F11 toggles maximize; normal/maximized geometry and active view are restored within current monitor work areas. Preferences live in `aurora_control_panel_layout.json` and never apply runtime settings.
- Settings retain all former quick actions and the full banner. Banner animation is optional and initially off. Runtime details also open from the persistent header.
- `aurora_panel_layout.py` owns presentation helpers; its symbols are in the common control-plane/helper skeleton.
- Command references preserve all 335 runtime + 19 desktop bindings; 53 have reviewed contracts. Desktop receipts now include action_route (admitted namespace/origin/mode/backend/requested/effective key); settings, locks and transactions retain their typed results. Known same-batch mode changes guide implicit actions, and explicit prefixes retain their meaning. Implementation 08 changes runtime routing and references; panel source/layout remain unchanged. Receipt presentation and final manual keyboard/wheel/scaling QA remain open.

## Quick Controls (inside settings)

Live/execution/action modes, runtime/health/risk/monitor/checkpoint/capture, auth/locks/OAuth helpers, Chat Head, Help and Commands are retained in the Quick Controls section.

These mostly call `self.send_raw(...)`, which uses the shared `aurora_control_plane.append_bridge_request()` sender and writes correlated request envelopes into `aurora_external_inbox.jsonl`.

Window 23 Slices 4-5 make the Control Panel a nonblocking client of the shared 22-setting transaction service and expose the runtime's mutation-admission posture. The left settings card exposes Preview Atomic, Apply Atomic, Rollback, Refresh, Settings Details, and Apply Additional. Registered changes carry one expected version and exact receipt; additional controls remain explicitly independent. Overview and Commands show reserved/terminal/uncertain admission counts and that automatic replay is off.

Window 23 Slice 6 is intentionally CLI-only: its shell/discovery/completion/history layer does not add a second Control Panel execution path. Slice 7 adds one shared `aurora_operator_dashboard_v1` observation model, a Dashboard tab, and a toggleable popout; the panel calls the structured builder directly rather than scraping terminal output.

## Settings Pane

Main cards:

- settings/model/security/defaults card
- runtime feedback card

## Work Views (Notebook-backed selector)

- `Overview`
- `Dashboard`
- `Memory`
- `Episodic`
- `Pending`
- `Command Drip`
- `Chat`
- `Commands`
- `Prompt Ledger`
- `Agents`
- `History Context`
- `Portal Intake`
- `Visual Context`
- `Image Index`
- `Live Harness`
- `Responses Shadow`
- `Context Files`
- `Recovery`
- `Screenshots`
- `Images In Memory`
- `Help`
- `Raw State`

## Core UI Behaviors

- refresh loop every ~1200 ms; its next callback survives failures, the last accepted file revision is retried, and a visible error qualifies potentially stale data
- sixty editable variables preserve local drafts across refresh; unedited values follow runtime; Reload observed resets only the form
- reads `aurora_control_panel_state.json`
- writes `aurora_bridge_request_v1` raw commands to `aurora_external_inbox.jsonl` and shows the queued request id in Operator Activity
- reads `mutation_admission` from exported state and surfaces reserved/terminal/uncertain counts plus the no-automatic-replay posture in Overview, Commands, and raw details
- builds the read-only Dashboard tab/popout from shared process/state, operation, settings, mutation-admission, and sanitized recent-receipt snapshots
- screenshot viewer and image-memory viewer both support prev/next/latest/popout flows

## Verification

November 4 preview follow-up: main status links to scoped Primary/Vision/Review selectors. Conversation defaults to Times/Models/Edits enabled with persistent display preferences. Reset to preview defaults opens the same 22-setting review/apply/rollback view from main controls, Switchboard title/command desk and Commands. It preserves auth, game profile, other Advanced settings, saved profiles and history. This bounded reset is not a factory wipe.

Implementation 03 passed 146 unit tests and hidden Tk/offline runtime transaction and refresh checks. Final manual visual/keyboard/scaling QA is open after the user stopped Computer Use because of severe desktop lag; do not infer a cause or resume native capture from this note. See `docs/reviews/2026-09-05/implementation-03.md`.

November 4 prompt/novice follow-up: current/legacy init profiles and command-discovery context delivery are selectable at startup; see README_FOR_AI.md. Primary runtime start is paused/safe, enable preserves settings, legacy orb activation remains, Advanced opens expanded with Dock retained, and Conversation has Quick start. See README_FOR_HUMANS.md.
