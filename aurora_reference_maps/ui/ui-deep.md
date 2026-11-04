# Aurora 2 Control Panel Deep Map

## November 4 — The Switchboard / Implementation 23

`AuroraControlPanel._build_switchboard_tab` hosts a fit-width scroll page. `Switchboard` preserves dirty setting drafts across exports, reads effective source/scope/lock values and submits preview/apply/rollback through `_submit_settings_transaction(inline_results=True)`; Advanced retains its existing dialog behavior. `load_switchboard_catalog` validates generated source hashes, falling back to AST discovery. `command_draft` uses visible argument placeholders; local framing/name validation complements runtime admission. `wait_receipt` is a bounded worker returning through a queue; Tk owns rendering and no timeout replays work.

`switchboard_flow` supplies 3/4/8 abstract/group/function nodes and separate capture/turn loops with stale gates. `draw_flow` redraws only on topology/size changes. Context chips use `context_contents`, `show_tip`, `show_contents` and a scrollable viewer; loaded Init/current conversation/latest screenshot are distinct from last-prepared text. Inspection does no capture, retrieval or provider I/O. `PortalShortcuts` caches 24 clockwise frames and shares one panel timer; hidden widgets stop frame advancement, motion is optional and close cancels the timer. Main chat shortcuts are not duplicated inside visible pages. The legacy Advanced chat shortcut remains reachable.

## November 4 — Conversation-first friend preview / Implementation 22

`aurora_conversation.py` builds detached bounded current/retained views from HistoryContextService state; effective drop filters apply to current rows. The panel starts on Conversation, has a composer and optional system details, and retains Chat historical logs plus all 23 views. `Reopen last view` preserves the prior startup option. New routine models default to gpt-6.1-sol low; review role defaults to gpt-6-astra medium, with older models/configurations retained. The native bounded test sequence and limits are recorded in docs/reviews/2026-11-04/implementation-22.md. General gameplay/native testing remains deferred. Core R2b2b is still next after this user-directed preview.

## November 4 — shared query preflight / Implementation 21

Search filters exposes argument_policy=legacy|strict (legacy default). `_episodic_retrieval_segments` validates the final serialized command with `aurora_retrieval_commands.build_retrieval_request`, so invalid strict numeric controls and filter/grammar errors remain visible before send. Runtime admission/execution uses that same parser; existing controls and saved/default behavior remain. Query/snapshot results flow through existing Chat/receipt surfaces. Headless controller tests only; native GUI/scaling acceptance stays paused.

## November 4 — retained result selection / Implementation 20

Episodic Search filters adds optional result_mode=legacy|retained. A separate editable handle defaults blank for legacy preview promotion. Use displayed handle binds deliberately; refresh records the displayed handle but does not overwrite the selected one. Inspect retained (Chat) sends SHOW_RETRIEVAL_RESULT(handle,0,24); Promote Selected sends the optional fourth handle argument through shared validation. Returned versus preview count and retention metadata are visible. Full source text is available beyond the eight preview items; all old controls remain. Runtime handles expire/evict/restart and fail explicitly. Native visual/scaling acceptance remains paused; AST/controller tests cover forwarding and errors. See the [retrieval reference](../../docs/reference-packs/memory-retrieval-reference.md).

## Search date wiring — Implementation 19

SEARCH_DEFAULTS adds after/before/date_period/date_anchor, automatically creating episodic_search_vars. `_build_episodic_search_filters` supplies explicit labels and period choices, retaining the existing collapsible surface. `_episodic_retrieval_segments` normalizes all options, rejects conflicting dates and moving-window paging/feedback, and forwards unchanged anchor/period strings with JSON encoding to Preview/Recall. The runtime, not panel clock, resolves an omitted anchor. Existing preview/feedback token behavior is unchanged. AST/controller tests cover new option forwarding/errors; native GUI verification remains paused.

## Local validation web wiring — Implementation 18

`aurora_validation_web/app.js` consumes `/api/catalog`, `/api/profiles`, `/api/preview`, `/api/run`, `/api/cancel` and `/api/runs` from the same-origin loopback service. A launch fragment bootstraps bearer authentication, is removed from the address bar and retained only in tab session storage. All dynamic values use textContent; no catalog/profile HTML execution. Recipe/profile drafts remain client-side until Save/Preview/Run; changing recipes deliberately loads that recipe's defaults. Saved versions are content-addressed.

`renderCommands` filters names/aliases/descriptions/handlers, subsystem tags and contract maturity while retaining full detail. `displayRun` distinguishes sent/controller effort and fake timing; full JSON includes configuration updates, synthetic usage, restoration and cleanup. Polling is once per second only while an observed run is active and the page is visible; visibility changes refresh status. `tests/test_validation_web.cjs` checks shipped script behavior with a DOM/API fixture without browser/native capture. This is not rendered-layout proof. Python HTTP/service checks and isolated runtime evidence are in Implementation 18; native panel wiring is unchanged.

## Repeat-search wiring — Implementation 17

send_episodic_feedback selects a one-request action and uses the existing Preview builder/send_raw path. normalize_search_options validates all feedback options. The action resets to none after submission; render_episodic updates the token only for the panel session. SearchFeedbackLedger owns feedback mutation; the panel never judges result usefulness automatically.

## Conventional search controls — Implementation 16

_build_episodic_search_filters creates request-scoped fields from SEARCH_DEFAULTS/SEARCH_CHOICES. _episodic_retrieval_segments calls normalize_search_options, permits intentional filter-only input and forwards all fields through existing send_raw ingress. render_episodic reads last_retrieval_search and per-row search_matches. It does not own a second scorer, index or settings service.

## Episodic retrieval hardening — Implementation 15

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

Preview and Recall now send the same query-scoped options from _episodic_retrieval_segments. The collapsed Advanced retrieval section retains ordinal/age selection, semantic tag mix, minimum relevance, half-life hours, anchor/scale and fallback. Defaults preserve ordinal/permissive ranking. Per-result evidence includes time mode/source/age and query relevance. No settings registry/default-profile fields change; manual visual acceptance remains paused.

## Pending selection correctness — Implementation 13

Pending selected-item Approve/Clear now sends stable item IDs plus the version of the displayed queue. A changed queue is rejected with a receipt instead of targeting a different index. Selection survives refresh when the same ID remains visible. Existing index/risk/category/family/raw selectors and normal/insert/replace modes remain available; old snapshots retain index fallback. Reserved/uncertain state appears beside the mode, and full entries/routes/recovery evidence are available in pending_queue and SHOW_PENDING(). Model/parent authority and sub-agent manual gates remain unchanged. AST/guarded-state verification passes; visible GUI/scaling acceptance is still open under the native-testing pause. See docs/reviews/2026-09-07/implementation-13.md.

## Adaptive reasoning UI ownership

`model_transport_var`, `_collect_registered_settings_form_values`, observed-state `_sync_setting_var` and `apply_model_preset` use the shared `model.transport` setting. The Models status view reads `model_status.responses_reasoning`; its compact lines do not render the full JSON snapshot. See `docs/reference-packs/adaptive-reasoning-reference.md` for reset, effort and provider-history behavior. No new background UI process or automatic Live switch is created.

## Freshness Note - 2026-09-05

- Implementation 03 adds recoverable refresh, draft-preserving settings, persistent runtime controls, a full-name view selector, independent page/settings scrolling, disclosure/search and remembered geometry. Read `ui-lite.md` for the current layout. Hidden Tk/runtime checks passed; final native visual/keyboard/scaling QA remains open after a user-reported desktop slowdown.
- `aurora_panel_layout.py` owns presentation-only geometry, preferences, ScrollablePane, FlowBar and CollapsibleSection. Its symbols are in the common helper skeleton.

- Current Control Panel truth includes the Window 22 Portal Intake tab/surfaces through Slice 14, with closure parked locally and all live Portal read/write/mutation gates still off.
- Window 23 Slices 1-7 provide the current UI-facing control-plane work: correlated request receipts, a typed 22-setting registry, atomic runtime-session settings transactions, a nonblocking Control Panel transaction client with details/conflict refresh/rollback, visible durable mutation-admission/no-replay posture, and a shared structured Dashboard tab/popout. Slice 6's shell/discovery/completion/history remains CLI-only.
- OAuth controls are helper/opt-in surfaces; `api_key` remains the conservative default auth mode.
- Use this file for UI orientation, then verify against `aurora2_control_panel.py`, exported state, and the current handoff before implementation. Regenerate generated UI refs after source edits.

## Event Model

- startup:
  `refresh_loop()` (initial refresh plus recurring scheduling)
- recurring poll:
  `refresh_loop()`
- state source:
  `STATE_PATH = aurora_control_panel_state.json`
- command sink:
  `INBOX_PATH = aurora_external_inbox.jsonl`

## Persistent Header and Workspace

`_build_ui()` creates a fixed header/status/actions strip and wrapping navigation above a paned workspace. `_build_runtime_status_strip()` retains activate/pause/cancel/stop/capture actions. `_new_work_page()` wraps each of the 22 original view builders in an independent scroll pane. `show_tab()` selects and reveals a page.

The settings pane can be hidden, docked or expanded. `_apply_settings_mode()` and `_clamp_settings_sash()` own the layout only. `_build_quick_controls()` and `_build_sidebar_runtime_details()` retain the former quick action groups and full banner. `_filter_settings_sections()` searches static labels, excluding field contents.

`_sync_setting_var()` tracks last-observed values separately from edited form values. `reload_observed_settings()` refreshes the form without submitting a command. `refresh_now()` accepts a file revision only after successful rendering and logs refresh health; `refresh_loop()` schedules the next callback in `finally`.

## Left Settings Card

Built in `_build_settings_card()`.

Major areas:

- model selections and runtime settings
- security/passcode controls
- command-drip settings
- overlay/profile/defaults buttons
- continuity actions:
  save handoff, retrieve, load yesterday, recall previous summary
- scoped clear actions
- raw command entry and note entry

Current settings boundary:

- `aurora_settings_registry.py` is canonical metadata/readback/versioning for 22 high-value settings, and `aurora_settings_transactions.py` is the atomic runtime-session mutation contract.
- `_build_settings_card()` exposes `Preview Atomic`, `Apply Atomic`, `Rollback`, `Refresh`, `Settings Details`, and `Apply Additional`.
- `apply_settings()` submits one version-preconditioned transaction and waits off the Tk thread; exact receipt handling returns to the UI through `_drain_settings_transaction_results()`.
- named scheduler profiles submit one bundle key; leaf edits select `custom` and submit all six scheduler leaves.
- broader nonregistered controls remain independent commands. Operator/model/advanced profile follow-ups wait for a successful registered apply and the UI discloses their count.
- Keep the broader `SETTING_SAFETY_INVENTORY` as operator guidance for settings plus operations such as approvals and clears.

Mutation admission visibility:

- `format_mutation_admission_summary()` reads the shared `mutation_admission` state snapshot;
- the Overview Queue card and Commands workflow strip show reserved, terminal, and uncertain counts plus automatic replay off;
- the Overview raw-detail block exposes the same summary and journal path;
- these are read-only status views. Duplicate/conflict/no-replay decisions remain runtime/control-plane behavior rather than a second UI-owned policy.

High-value buttons here:

- `Preview Atomic`
- `Apply Atomic`
- `Rollback`
- `Settings Details`
- `Apply Additional`
- `Refresh`
- `Add Model`
- `Remove Model`
- `Reload`
- `Queue Next`
- `Clear`
- `Apply System`
- `Apply Personal`
- `Save Personal`
- `Show Defaults`

## Notebook Tabs

### Overview

Read-only formatted status summary, including mutation-admission reserved/terminal/uncertain counts and no-replay posture.

### Dashboard

Read-only structured operator snapshot built by shared `build_operator_dashboard()` rather than terminal scraping:

- compact Runtime, Operation, Control Plane, and Settings summary cards;
- bounded sanitized recent-receipt Treeview with both scrollbars, stable selection and full selected-receipt detail;
- shared formatted detail text, wrap toggle and popout freshness summary;
- Refresh and Open/Close Popout controls; and
- refresh while the tab is active or its popout is open, with event-row signature caching to reduce flicker.

### Memory

Tree view of serialized runtime memory slices.

### Episodic

Retrieval, planning, and promotion surface for episodic-memory context.

### Pending

Queue review surface with filters and action buttons:

- approve selected
- approve all
- clear selected
- clear all
- risk-scoped approve/clear

### Command Drip

Refreshable text view of near-term command tree.

### Chat

Tail/full views of chat log.

### Commands

Tail/full views of command log plus the mutation-admission workflow summary.

### Prompt Ledger

Prompt-context inclusion/omission ledger with links to visual context and agent surfaces.

### Agents

Metadata-first agent registry, suggestion, task, ACL, and pending-insert review surface.

### History Context

History-service and rehydration visibility for what can be pulled back into context.

### Portal Intake

Window 22 companion-intake registry/viewer surface; live Portal read/write/mutation gates remain off.

### Visual Context

Visual-context readiness, screenshot/image context, and prompt-surface comparison view.

### Image Index

Screenshot sidecar/index inspection, search, and bounded backfill controls.

### Live Harness

Live visual harness readiness/rehearsal/probe status.

### Responses Shadow

Responses transport comparison surface kept as an opt-in/shadow lane.

### Context Files

Local context-file inventory and prompt-surface hints.

### Recovery

Settings safety, diagnostics, recovery home, and baseline/defaults review surface.

### Screenshots

Preview area, thumbnail strip, prev/latest/next/popout.

### Images In Memory

Parallel viewer for retained image-memory entries.

### Help

Embedded operator help and command list.

### Raw State

Direct JSON snapshot view for debugging.

## Viewer and Popout Surfaces

The Dashboard has a toggleable text-detail popout over the same shared snapshot. Screenshot and image-memory viewers both support:

- preview navigation
- thumbnail strip
- popout window
- fit mode
- 1:1 mode
- keyboard navigation

## Search Priorities

If you need to trace a control, start here:

- `_build_ui`
- `_build_settings_card`
- `_build_dashboard_tab`
- `refresh_dashboard`
- `toggle_dashboard_popout`
- `_build_pending_tab`
- `_build_command_drip_tab`
- `_build_prompt_ledger_tab`
- `_build_agents_tab`
- `_build_portal_intake_tab`
- `_build_visual_context_tab`
- `_build_image_context_index_tab`
- `_build_settings_safety_tab`
- `_build_screenshots_tab`
- `_build_image_memory_tab`
- `send_raw`
- `refresh_now`
- `refresh_loop`

November 4 prompt/novice follow-up: current/legacy init profiles and command-discovery context delivery are selectable at startup; see README_FOR_AI.md. Primary runtime start is paused/safe, enable preserves settings, legacy orb activation remains, Advanced opens expanded with Dock retained, and Conversation has Quick start. See README_FOR_HUMANS.md.
