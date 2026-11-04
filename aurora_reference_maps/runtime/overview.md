# Aurora 2 Runtime Overview

## November 4 — assistant game routing / Implementation 24

`infer_pending_queue_directive` preserves authored namespaces until `prepare_command_batch` freezes the action route. The actual assistant/pending-wrapper path now retains GB mapping independently of current mode; internal canonical PYAG dispatch spelling must not become a new explicit desktop route. 360 bindings are unchanged. Guarded scenario evidence confirms goal/history operations and remaining G1 persistence gaps. The bounded FireRed test verified one native movement and Sol/Astra/restoration, then stopped on scene-classifier false positives (`upper`/`pp`, negated battle text). Evidence-aware classification and G1 precede more gameplay qualification; full details are in Implementation 24.

## November 4 — Switchboard runtime / Implementation 23

`capture.mode` is the 24th shared setting: heartbeat preserves periodic capture, request_only waits for due demand requests. Environment, CLI, raw SET_CAPTURE_MODE, profiles and versioned transactions converge on the same setter; the interruptible worker reevaluates deadlines. Turn scheduling remains separate. All 359 prior bindings remain (360 now, 98 reviewed). `aurora_conversation.build_init_context` exports loaded Init/source/clipping; `build_prompt_materials` retains four bounded last-prepared text components without image bytes. The panel reads these exports; inspection never invokes prompt builders or provider/native operations. Preparation is not delivery or exact provider-session replay. See Implementation 23 and the human/AI guides.

## November 4 — Conversation-first friend preview / Implementation 22

`aurora_conversation.py` builds detached bounded current/retained views from HistoryContextService state; effective drop filters apply to current rows. The panel starts on Conversation, has a composer and optional system details, and retains Chat historical logs plus all 23 views. `Reopen last view` preserves the prior startup option. New routine models default to gpt-6.1-sol low; review role defaults to gpt-6-astra medium, with older models/configurations retained. The native bounded test sequence and limits are recorded in docs/reviews/2026-11-04/implementation-22.md. General gameplay/native testing remains deferred. Core R2b2b is still next after this user-directed preview.

## November 4 — R2b2a admission/receipts / Implementation 21

`aurora_retrieval_commands.py` now owns query defaults, shared parsing, optional argument_policy=legacy|strict, snapshot argument contracts and typed receipt construction. `aurora_command_contracts` calls it before batch execution and advertises named defaults/choices. Runtime `_build_retrieval_request` / shorthand remain thin compatibility adapters; `retrieval_pull_command` / `_execute_retrieval_pull_command` preserve display and attach effective evidence/correlation IDs. `execute_episodic_snapshot_command` serves the three existing snapshot handlers with count/identity/score receipts and truthful uncertainty. All 359 bindings remain; 97 reviewed contracts. Native testing stays paused. Next R2b2b is coherent publication and append/memory concurrency; see [reference](../../docs/reference-packs/memory-retrieval-reference.md).

## November 4 — R2b1 retained K-sets / Implementation 20

`aurora_retrieval_results.py` owns bounded canonical JSON retention, exact handle reads, item/content identities and shared inspection/promotion contracts. `run_episodic_retrieval` prepares optional retained evidence before feedback/publication; `result_mode=legacy` remains default. `show_retrieval_result_command` inspects full records, and `promote_episodic_retrieval_item(..., result_handle=...)` selects full source text independently of the current preview. Legacy no-handle promotion stays available. New snapshots use session-prefixed UUIDs; old IDs remain untouched.

`retrieval_results` follows existing action/log/control-plane receipt and mutation deduplication paths. Handles are runtime-memory only: 32 sets / 8 MiB / 1 MiB per set / 30 minutes. No provider calls on inspection, no implicit fallback/replay. See [retrieval reference](../../docs/reference-packs/memory-retrieval-reference.md). Next R2b2 covers broader retrieval/snapshot admission, coherent exported publication and mutation concurrency; V1/V3/G1 history remains planned. Native testing stays paused.

## November 4 — R2a2 date conveniences / Implementation 19

`aurora_search_query.resolve_search_dates` resolves strict before/after and optional calendar/elapsed periods with explicit anchor/timezone. `normalize_search_options` validates without freezing the clock; `compile_search_filter` resolves one window at execution. `run_episodic_retrieval` records date_window and evaluation_epoch and applies hard bounds before embedding/scoring. Relative paging/feedback requires a fixed anchor; feedback identity includes all new date controls. Existing date_start/date_end/default none behavior is unchanged. Panel/raw Preview/Recall share these controls. See [reference](../../docs/reference-packs/memory-retrieval-reference.md) and [proof](../../docs/reviews/2026-11-04/implementation-19.md). Next is R2b; native visual testing stays paused.

## November 4 — VC0/initial VC1 implemented

`aurora_validation_console.py` exposes static catalog discovery, strict profile validation, source fingerprint checks, atomic local artifacts, a single owned offline runner and loopback bearer-authenticated HTTP/CLI adapters. `aurora_validation_worker.py` executes three turns through the actual runtime in a disposable source copy with fake transport, synthetic tokenizer, native/network guards and restoration readback. It does not start runtime.main or attach to a current runtime. `launch_aurora_validation.cmd` starts the opt-in web frontend. Existing control paths/defaults stay intact; live execution is unavailable.

Python entries appear in the generated shared-layer skeleton. See [operating details](../../docs/notes/aurora_validation_console_plan.md) and [offline evidence](../../docs/reviews/2026-11-04/implementation-18.md). Native/browser visual QA remains paused; synthetic usage and local timings do not establish live model performance. Historical planning paragraphs below are superseded for this delivered scope only.

## November 4 — local validation console (planned VC0–VC3)

Reuse `aurora_command_catalog.build_command_catalog` (static AST discovery), shared settings registry/transactions, command admission/receipts and existing guarded smoke fixtures for an optional localhost web view. `tests/offline_responses_smoke.py` already exercises the actual model-turn path with a fake provider; its values are synthetic, not live acceptance. The native Tk panel remains available; share core data/services rather than copying UI handlers or creating a second settings authority. Plan source-aware catalog browsing and dry/fake runs first, then budgeted live text tests and comparison history. See [readiness and boundaries](../../docs/notes/aurora_validation_console_plan.md). No new console APIs/functions are implemented by this note.

## October 31 — optional historical memory (planned)

`build_episodic_snapshot_record` records timestamped selected-state summaries, not a complete immutable state history. Date-filtered retrieval does not reconstruct knowledge as-of a cutoff. Existing settings versions/receipts, pending-command superseded/contradicted fields and route-field freshness provide partial building blocks. Accepted V1–V8 adds optional version points, supersession and as-of views first, then freshness/conflict policies, diffs, lineage and recorded decision-context inspection. See [coverage/acceptance](../../docs/notes/aurora_versioned_memory_plan.md) and roadmap; none of these planned APIs belongs in generated skeletons yet.

## October 31 — hierarchy preservation and optional expansion (planned)

Current `Goal` retains priority/significance/status and nested subgoals; hierarchical tasks retain rationale, notes and associated goals. `sync_action_horizons_from_hierarchical_tasks` replaces immediate/short/mid/long lists from levels 1/2/3/4+, while apriority, overarching and unknown-priority stores remain separate. Notes/journal remain text stores. Pending-command numerical scores and episodic ratings are separate from goal labels.

Accepted G1–G3 work repairs persistence/IDs and characterizes overwrite semantics before offering optional fuller horizons and attributed structured notes. Current defaults remain; extra automation and prompt structure must be independently avoidable. This is planned, not implemented. See [findings and acceptance](../../docs/notes/aurora_goals_notes_hardening.md) and [roadmap](../../docs/notes/aurora_runtime_roadmap.md). Generated skeletons must continue to reflect source only.

## October 17 — repeat-search feedback / Implementation 17

Implementation 17 (2026-10-17) adds optional repeat-search feedback before the next date-convenience slice. feedback_mode=off|skip|penalize preserves ordinary searches by default; feedback_factor (0–1, default .25) is a score multiplier per explicit rejection. feedback_action=reject_last marks the previously returned K results using an exact feedback_token; reset clears marks for that query/session. Feedback is bounded in runtime memory (32 query/session entries, 2048 rejected content identities each), not persistent training or probability sampling. Plain repetition never labels results unhelpful. Skip removes marked records before embeddings; penalty modifies ranking contributions, and zero excludes. Query/text/date/tag/source/session define the scope; changing weights, shape or K preserves marks, while changed record content is new evidence. Tokens prevent stale/concurrent batch feedback; failed/cancelled searches do not commit marks. Separate feedback_session values isolate AI operators; panel sessions use their PID.

The panel exposes these controls under Advanced repeat-search feedback, with Batch unhelpful → search next and Reset feedback & search. Existing four-axis scoring, legacy weights, shape/center/spread/jitter, date/text filters and raw commands remain. Penalty requires relevance/legacy ordering; feedback uses offset=0 because exclusions change the pool. Distributions are rank reshaping/jitter, not a calibrated sampling distribution; K is a result count, not implemented semantic clustering. Native GUI/input/capture acceptance remains paused.

Verification: 436 full regression tests passed in 124.084 seconds; after a final panel guard clearing tokens for foreign/missing displayed results, all 26 focused search/panel tests passed in 1.426 seconds. Guarded runtime: 126 receipts, 15 retrieval checks, 33.04 seconds; native input/capture/provider guards passed. Owned fixture removed. GitHub checkpoint branch: codex/aurora-retrieval-feedback-2026-10-17. Native GUI acceptance stays paused.

Standing reminder: [capability breadth is intentional](../../docs/notes/aurora_capability_compatibility.md). Preserve commands, aliases, valid old/new modes and saved state; offer explicit toggles/configuration/profiles and searchable Advanced access. The accepted harness adoption track remains staged around the core quality roadmap.

## October 16 Implementation 16 — current continuation

Implementation 16 adds R2a1 conventional episodic search: composable hard text/tag/source/date filters before embeddings and scoring; literal, whole-word, exact-phrase, escaped wildcard and bounded Boolean modes; UTC/offset/IANA date boundaries; filter-only requests; explicit relevance/newest/oldest ordering, offsets/counts and matching evidence. The Control Panel exposes these in Search filters beside the retained visual scorer. Legacy query scoring, distributions, aliases and saved settings remain; raw value_encoding=legacy preserves existing backslashes, and explicit json encoding decodes quoted values (the panel default). Unknown/duplicate named options now fail visibly.

Remaining search work: R2a2 before/after and relative-period conveniences, then R2b reviewed whole-batch contracts, immutable full-result handles/promotion beyond eight previews and concurrency-safe publication. Offset paging is deterministic for unchanged records and scoring inputs, not a retained snapshot cursor; R2b must make concurrent changes explicit. Person/conversation filters remain R4 and are rejected today. Native GUI/input/capture testing remains paused; this slice uses offline fixtures only.

Implementation 16 verification: 430 regression tests passed in 122.477 seconds. After final command-serialization and out-of-range epoch repairs, all 37 retrieval tests and 20 search/panel tests passed again (2.588 / 1.417 seconds). Guarded runtime: 122 correlated receipts, 11 retrieval checks, 31.22 seconds; cancellation 116.21 ms, shutdown 118.75 ms; zero captures/provider effects. All 358 bindings/aliases remain, with 89 reviewed contracts. Skeletons: 1344 runtime / 488 shared / 338 UI functions. See docs/reviews/2026-10-16/implementation-16.md. Owned runtime/test processes and the disposable checkout were cleaned up; native GUI/scaling proof remains paused.

Implementation 15 adds the user-requested R1 semantic lookup/scorer hardening before 4B4e. Zero weights and RECALL/MEM forwarding are repaired. Existing ordinal recency, permissive ranking (`min_relevance=0`), lexical search, rating bonuses, distributions, planning assist and promotion remain. Optional `time_mode=age`, `age_half_life_hours`, `min_relevance` and `embedding_fallback=lexical|partial` are per-query controls; the Episodic view exposes them under Advanced retrieval, and Preview/Recall share the same options. No global/default-profile fields were added or changed.

Embedding responses now validate indices, finite/nonzero vectors and dimensions. Content keys prevent duplicate snapshot IDs from sharing wrong vectors. Required tags/source buckets filter before embedding; repeated text is deduplicated, provider batches contain at most 64 texts, and one locked atomic cache merge replaces per-vector rewrites. `force` requires complete eligible coverage; `auto` falls back to lexical, with explicit partial mode available. Cancellation propagates and cache-save failures are visible. Empty/excluded collections do not call the provider. These repairs preserve intended valid behavior; corrupt vectors and false force-success are not retained as successful modes.


The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

Implementation 15 verification (historical): all 411 regression tests passed in 123.261 seconds. After a final rating-contribution reporting correction and GUI wording change, all 37 focused retrieval tests passed again in 2.561 seconds. Guarded real runtime: 117 correlated receipts in 30.98 seconds, including six retrieval checks; cancellation 116.04 ms and shutdown 121.67 ms. No native input/capture/provider calls. Skeletons contain 1344 runtime / 471 shared / 337 UI entries; all 358 bindings/handlers/aliases and 89 reviewed contracts remain. Evidence: docs/reviews/2026-10-16/implementation-15.md.

After R2a2 date conveniences, R2b covers reviewed admission/receipts, full result identity/promotion beyond eight preview items, unique snapshot IDs and clearer coverage/failure evidence. R3 covers measured quality/scale, rating provenance, indexing/budgets and optional calibration. Resume 4B4e retention/prompt state afterward or integrate R2 with that mutation work. Native testing remains paused; OBS and sibling ownership are unchanged. Work remains local and uncommitted.

## October 1 Implementation 14 — prior evidence

Implementation 14 completes 4B4d local history controls. Thirteen existing bindings share validation, positional selection, serialized mutation and typed history_command_results. Percentage command names now reach dispatch; protected/duplicate history and zero/rounding boundaries are repaired. INIT/PIN honor retention gates, whole edits validate before publication, and SAVECH returns a verified collision-safe actual path.

All 358 bindings/handlers/aliases remain; 89 now have reviewed parameter contracts and 269 retain legacy coverage. Random partial clearing stays the default, with optional oldest/newest selection. First-match timestamp edits, all-match deletes, total-budget CLEAR% behavior, text/image-preview exports, all 60 defaults fields and the 23-setting / 24-raw-name registry remain. Changed history cancels stale model work and invalidates active Responses continuation; no-op clears/read/export do not. Reset is explicit, and there is no provider replay or remote deletion.

Verification: 374 tests passed in 131.256 seconds, including 29 focused history tests. Guarded real runtime: 111 correlated receipts in 36.44 seconds, 10 history checks, cancellation 126.58 ms and shutdown 115.55 ms; zero capture/native/provider effects. Skeletons: 1343 runtime / 456 shared / 331 UI; 43 reference artifacts / 21 packs.

Next is 4B4e retention and prompt-state controls, then remaining memory/task/overlay mutation services, 4C measured performance and 4D GUI/clean-install acceptance. Plan roughly 4–7 further focused core-quality slices through 4D, then a bounded useful-workflow proof; H0–H5 remain additional staged work. This slice does not complete advanced context marks, Prompt Inclusion or private sub-agent history controls. Keep capability breadth, OBS/sibling boundaries, native-testing pause and automation state. Evidence: docs/reviews/2026-10-01/implementation-14.md. Work remains local and uncommitted.

## Comparative harness research — September 6

The [public-agent survey](../../docs/reviews/2026-09-06/agent-harness-survey.md) maps 14 public repositories to Aurora. The user accepted H0 measurement, H1 discovery/evidence handles, H2 optional isolated analysis, then bounded RLM/specialists and memory/workflow/hooks as a staged roadmap direction. These capabilities remain unimplemented and disabled. Query the existing skeletons and current status before assuming a registry or readiness surface executes work. 4B4c is implemented; prompt/history controls are next; old capabilities and provider-specific reasoning/history behavior stay available.

## Earlier dated evidence


## September 6 adaptive reasoning

Final regression: all 250 tests passed in 111.761 seconds. All 18 changed source/test files compiled; all original bindings were preserved. The final guarded fake-provider runtime proof passed in 10.843 seconds. There are 42 verified reference artifacts / 20 reference packs; skeletons contain 1,318 runtime, 391 shared-layer and 330 UI entries.

Implementation 09 adds opt-in Astra Responses adaptive reasoning. SET_MODEL_TRANSPORT(responses) selects the session transport without enabling Live; RESET_RESPONSES_SESSION() explicitly starts a new provider chain. Existing one-turn effort requests drive configuration_update while the original request baseline stays fixed; the next normal turn explicitly restores its selected policy. Model Status distinguishes selected/effective/API-reported effort and exposes continuation, limits and uncertainty.

`aurora_responses_reasoning.py` owns the provider conversation and strict output acceptance; `post_openai_turn_request` keeps I/O in the existing cancellable worker. `evaluate_assistant_command_policy` permits valid unlocked one-turn effort in assist/auto; safe mode holds it. Use `SHOW_REFERENCE_PACK(adaptive_reasoning)` for operating details. Astra/API-key only; text/image input and completed text output; no automatic replay, fallback, truncation or compaction. Active prompt omission/inclusion is blocked pending parity. Live provider acceptance/cache measurement, native GUI/gameplay and full clean installation remain unproved. Keep native capture off unless separately resumed.

## Command and map ownership — September 5

Roadmap items 4A, 4B1 and 4B2a–c are implemented. All original bindings remain; with transport/reset there are 337 runtime + 19 desktop bindings, 56 reviewed contracts. Prepared actions carry immutable namespace/backend/key context, so explicit PYAG stays literal and GB keeps translation/focus/backend. Known preceding mode setters guide later implicit actions; queued actions keep their admitted meaning. Typed desktop/setting/lock/transaction receipts retain evidence and stop the tail after reviewed failures. Raw batches have no CAS/automatic rollback. Next: input ownership, critical command families, measured performance, then GUI/clean-install acceptance. See compact status and roadmap for proof and scope.

`tools/generate_aurora_references.py` owns portable generation/checks; the AST mapper and configuration live in `tools/aurora_maps`. Author curated lite/deep maps in this repository, and packs in `docs/reference-packs`. Use the root PowerShell wrapper with `-Force` to generate, `-Check` to verify without publishing, and `-SyncSkills` for explicit installed-skill exports. Skeleton file paths are checkout-relative. Generation uses normalized source/output hashes, not personal skill paths or timestamps. The moved-checkout isolated-Python proof covers generation, not a full clean runtime installation.

## Freshness Note - 2026-09-05

- September 6 coordination: Browser bridge repairs R1/R2 are planned in its task before timeline/workflow and B8-S3 integration. Aurora retains settings/admission/receipt authority; the cross-process contract must preserve timeout uncertainty, reserved context fields and immutable content-version/hash evidence. See `docs/reviews/2026-09-05/browser-integration-review.md`. No runtime change in this intake; 4B3 remains next.

- Historical September 5: Implementation 08 completed action routing. The full suite passed 226 tests in 97.777 seconds. Guarded runtime proof: 57 receipt checks in 18.83 seconds, exit 0; WAIT cancellation receipt 117.44 ms and shutdown receipt 163.72 ms. Offline/live-lock startup state was verified. Input/capture/model guards stayed unused and zero captures were recorded. Manual GUI/gameplay and clean-install proof remain open; no automatic capture restart. The compact status summarizes earlier slices and routes to dated evidence.

- Start with `C:/Users/YourName for current next steps and validation. The detailed handoff is a historical ledger. MCP `aurora://handoff/current` serves the compact status.
- September review: CLI/UI receipt waits match `client_id + request_id`; FL adapter `0.2.1` validates capture time as well as file age and isolates temporary cache writes. The installed FL script remains `0.2.0`. August live activation proof is historical; the September cache-only check was stale/inactive, not a failed activation.

- Current parent-repo truth: Window 22 Portal companion-intake remains parked at Slice 14; Window 23 operator control plane / CLI Slices 1-7 are checkpointed at `0d30c0b`; Window 24 Slice 1 adds `aurora-readonly`, Slice 2 adds validated `blender-readonly` scene inventory, and Slice 3 adds a separate `fl-studio-readonly` adapter/device heartbeat. All three surfaces are observation-only. FL installation, linked-port assignment, live heartbeat capture, correlated observation, and real stdio proof are complete; OBS authenticated proof is deferred behind the September runtime/command/GUI quality work. CX-4 remains an independent explicitly opened lane.
- Auth remains conservative: `api_key` is the default, with `codex_oauth` / `auto` and `LOGIN_CODEX_OAUTH()` opt-in.
- Agent helpers remain metadata-first: no hidden worker spawn, parent-history write, model-visible promotion, model call, or Pending execution.
- If source or roadmap docs changed, regenerate generated maps with `C:/Users/YourName -Force` before treating generated refs as fresh.

- September implementation: advanced AI is the primary operator; preserve capabilities. Launch preflight/shortcuts and R1/R2 batch admission/inbox recovery are repaired. Model-I/O cancellation, immutable captures and recoverable GUI layout are implemented. Next: command contracts and measured performance; finish interrupted manual GUI QA when appropriate. See the compact current status for verification.

- September implementation 03: persistent stop/status controls, independent scrolling, all 22 views, draft-preserving settings, geometry/disclosure preferences and automatic refresh recovery. Hidden Tk/runtime proof passed. Native visual testing was stopped by the user because of severe lag; see the dated implementation report for limits.

## Core Files

- `C:/Users/YourName strict side-effect-free batch framing shared by admission/execution; runtime preparation freezes resolved actions for the command queue.
- `C:/Users/YourName cooperative cancellation generations and a single bounded model-I/O slot; local cancellation keeps remote work visibly draining until it returns.
- `C:/Users/YourName exclusive temporary writes and atomic no-overwrite capture publication; runtime persistence shares the saved identity with sidecars and scheduler/history.
- `C:/Users/YourName presentation-only window geometry, preferences, scrolling, wrapping controls and disclosure.
- `C:/Users/YourName launcher import-resolution diagnostics; no runtime/hardware initialization.
- `C:/Users/YourName main runtime, command system, model loop, gameplay integration, external bridge, state export.
- `C:/Users/YourName separate Tk control panel process.
- `C:/Users/YourName shared request envelope, receipt reader, mutation-admission journal, status/process helpers, and read-only dashboard snapshot/formatter used by the runtime and operator clients.
- `C:/Users/YourName shared definitions, type constraints, defaults paths, lock metadata, effective/last-observed readback, and opaque settings versions.
- `C:/Users/YourName bounded strict JSON/base64 request codec, shared side-effect-free admission/planner validation, runtime plan construction, command invocation metadata and receipt extraction.
- `C:/Users/YourName one-shot and interactive `aurora` / `auroractl` client with status/control, dashboard text/JSON/watch output, typed settings, generated discovery/completion, and safe local history over the existing bridge and exported state.
- `C:/Users/YourName dependency-free local stdio MCP facade with five semantic read tools, eight allowlisted resources, two orientation prompts, and no command/settings/desktop authority.
- `C:/Users/YourName separate local stdio MCP/CLI adapter with two read-only tools, two resources, one prompt, strict `.blend` path allowlisting, and fixed headless Blender invocation.
- `C:/Users/YourName bounded `bpy.data` scene/object inventory script invoked only by the adapter; it contains no save, render, import, export, or mutation operation.
- `C:/Users/YourName separate stdio MCP/CLI adapter with installation, heartbeat-status, and correlated observation tools; it captures Aurora-prefixed SysEx, sanitizes one bounded fixed readback file, and exposes no FL mutation authority.
- `C:/Users/YourName Aurora-specific FL MIDI device script that emits read-only version/project-dirty/transport heartbeat state and has no MIDI-input or mutation callbacks.
- `C:/Users/YourName safe launcher entrypoint.

## Main Shape

Aurora 2 is one large runtime file that does seven jobs at once:

1. Startup and config resolution:
   CLI args, env vars, auth mode, execution mode, model settings, screenshot cadence, smoke-test options.
2. State and memory management:
   Agent memory stores, route state, recent context, pending commands, recent actions, model status.
3. Command interpretation and execution:
   Structured commands go through `is_known_command`, `handle_commands`, and `command_dispatch`.
4. Runtime loop and workers:
   `main()` starts the runtime, spins worker threads/processes, polls bridges, exports state, and monitors restarts.
5. External operator/control-plane bridge:
   `aurora_external_inbox.jsonl` is the append-only operator command path; `aurora_control_panel_state.json` is the snapshot export for the UI; CLI/Control Panel waits match normalized `client_id + request_id` through both bridge events and terminal command receipts. Mutations reserve that same pair in an fsynced journal before dispatch, so exact duplicates can be suppressed and unresolved work is reported without automatic replay.
6. Typed settings and transaction plane:
   twenty-two high-value settings are discoverable through `aurora settings list|get|describe|version`; an active runtime accepts atomic `preview|apply|rollback` transactions with version preconditions, effective readback, and same-session rollback handles. The Control Panel uses the same contract for Preview Atomic, Apply Atomic, details, conflict refresh, and rollback; nonregistered controls remain explicitly independent.
7. Gameplay and screenshot flow:
   The runtime captures screenshots, infers game state, routes commands, and logs action outcomes.

The Slice 6 operator shell is a client layer around jobs 5-6, not an eighth runtime job. It loads the generated command index, completes setting metadata, sends known runtime commands through the ordinary correlated bridge, and records only non-sensitive local shell attempts. It has no operating-system command escape or automatic mutation replay.

The Slice 7 dashboard is another read-only client view over jobs 5-6. `build_operator_dashboard()` produces `aurora_operator_dashboard_v1` with sanitized recent `aurora_operator_dashboard_event_v1` rows; terminal and Control Panel surfaces consume that structure directly rather than parsing rendered text.

The Window 24 Slice 1 MCP server is an external adapter over those read helpers, not a new runtime job. It lets a local Codex host inspect Aurora through MCP while keeping command submission, settings mutation, replay, model calls, desktop control, and external-app control absent from the tool list.

Window 24 Slice 2 keeps Blender in a second server. Codex may inspect Aurora context and an explicit allowlisted `.blend` file in one workflow, while Aurora has no Blender command path and Blender has no Aurora command path.

Window 24 Slice 3 keeps FL Studio in a third sibling server. The FL device script emits bounded ASCII-JSON observation state over the linked MIDI output; the outer adapter captures only the Aurora-prefixed SysEx packet, sanitizes it, and atomically writes `%LOCALAPPDATA%\Aurora\aurora_readback.json`. Linked-port assignment, live heartbeat capture, correlated observation, and stdio proof are complete. No transport action is authorized.

## Pokemon Profile Notes

- The current live-test default game profile is `firered`; `blue` remains supported.
- The runtime exposes `SET_GAME_PROFILE(firered|blue)` and `SHOW_GAME_PROFILE()` so prompts, smoke guidance, and state export can stay aligned with the active game.
- FireRed on this machine still uses `Start = h`.
- FireRed caveat: in-game `SAVE` is not treated as trusted emulator persistence.
- VBA-RR save-state handling is documented for operators only, not as Aurora runtime commands: slot `#1` save-state is `F1`, and slot `#1` load/restart is `Shift+F1`.

## Highest-Value Runtime Anchors

- `build_cli_parser()` / `apply_cli_args()`: startup control surface.
- `main()`: boot, worker startup, polling loop, shutdown.
- `write_control_panel_state_snapshot()`: JSON export used by the UI.
- `poll_external_reply_bridges()` / `poll_external_inbox_messages()`: operator input path.
- `MutationAdmissionJournal` / `get_mutation_admission_journal()`: durable mutation reservation, duplicate/conflict decisions, terminal reconciliation, and restart recovery.
- `handle_commands()` / `command_dispatch`: structured runtime command system.
- `monitor_and_restart_processes()`: worker liveness and restart logic.

## Data Boundaries

- Runtime to UI:
  `aurora_control_panel_state.json`
- UI to runtime:
  `aurora_external_inbox.jsonl`
- CLI/Control Panel client contract:
  `aurora_bridge_request_v1` -> `aurora_command_receipt_v1`
- Mutation admission contract:
  `aurora_mutation_admission_v1`, keyed by normalized `client_id + request_id`; exact terminal duplicates re-expose prior results, unresolved duplicates return uncertain/no-replay, and changed-payload reuse returns `request_conflict`
- Typed settings contracts:
  `aurora_settings_registry_v1` -> `aurora_setting_readback_v1` + `aurora_settings_version_v1`
- Atomic transaction contracts:
  `aurora_settings_transaction_request_v1` -> `aurora_settings_transaction_plan_v1` -> `aurora_settings_transaction_receipt_v1`; successful applies may issue `aurora_settings_rollback_handle_v1`
- Local CLI discovery/history:
  `aurora_reference_maps\commands\commands-index.tsv` plus ignored local `aurora_cli_history.jsonl` (`aurora_cli_history_v1`); history is convenience rather than execution truth
- Shared dashboard contracts:
  `aurora_operator_dashboard_v1` -> bounded `aurora_operator_dashboard_event_v1`; recent rows include command name/lifecycle metadata but exclude raw command arguments
- Read-only MCP contract:
  `aurora-readonly` stdio -> five read-only tools, eight fixed `aurora://` resources, and two prompts; command search is descriptive, settings responses explicitly deny MCP mutation authority, and no MCP request enters the command bridge
- Blender read-only MCP contract:
  `blender-readonly` stdio -> installation discovery plus explicit allowlisted `.blend` inventory, two fixed `blender://` resources, and one prompt; Blender runs background/factory-startup with autoexec and dependency-graph-on-load disabled and exposes no caller-supplied script, operator, save, render, import, export, GUI, or Aurora-control tool. This is an application-level boundary, not an OS sandbox; trusted scenes may resolve linked dependencies transitively.
- FL Studio read-only MCP contract:
  `fl-studio-readonly` stdio -> installation/device-script posture, bounded SysEx heartbeat status, and a correlated terminal observation receipt, plus three fixed `fl-studio://` resources and one prompt; the device script has no MIDI-input callback, filesystem I/O, or transport/project/plugin mutation call, and stale or missing telemetry is reported as unavailable rather than inferred active.
- Runtime logs:
  `aurora_mutation_admission_log.jsonl`
  `aurora_command_execution_log.jsonl`
  `aurora_chat_history_log.jsonl`
  `aurora_external_bridge_log.jsonl`
- Screenshot/image storage:
  `screenshots\`

## When to Switch to Deeper References

- Trace a behavior end to end:
  use `aurora2-program-map-deep`
- Enumerate or explain commands:
  use `aurora2-command-catalog`
- Map tabs, viewers, or panel buttons:
  use `aurora2-control-panel-map`

November 4 prompt/novice follow-up: current/legacy init profiles and command-discovery context delivery are selectable at startup; see README_FOR_AI.md. Primary runtime start is paused/safe, enable preserves settings, legacy orb activation remains, Advanced opens expanded with Dock retained, and Conversation has Quick start. See README_FOR_HUMANS.md.

Switchboard provenance/reset follow-up: `aurora_conversation` exports timestamp/model/source/editor metadata; `aurora_history_controls.history_actor_scope` carries model identity through queued edits; `BoundedModelIO.snapshot` exposes only the active requested model. `aurora_switchboard.preview_default_changes` defines the bounded 22-setting paused preview reset, through the existing settings authority. Direct role selectors and context previews retain all legacy controls.
