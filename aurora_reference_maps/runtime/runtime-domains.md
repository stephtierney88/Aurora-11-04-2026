# Aurora 2 Runtime Domains

Implementation 40 / capture authority: `aurora_capture_provenance` is the pure request/frame state machine; no I/O or model calls. Production runtime `acquire_runtime_frame` → `drawing_worker` → `persist_runtime_capture` carry immutable stamps. The service RLock serializes requests, publication and cancellation; legacy exported demand fields mirror its snapshot. `last_capture_frame` and prompt diagnostics retain exact selection, and observation generations prevent old dispatch acknowledgement. Known stale/cancelled/duplicate frames are rejected; unknown legacy payloads stay unknown. Shared registry `capture.provenance_policy` selects verified acquisition versus legacy counter freshness. Crop/DPI/target ownership and full native lifecycle qualification remain CF1b. Capture/drawing state is threaded under either worker mode; other process options remain. See Implementation 40 and its guarded fixtures.

Implementation 39 / everyday commands: static memory validation and metadata live in `aurora_goal_store`; execution/readback and existing goal/note/horizon mutators remain runtime-owned under the goal lock. Results cover only the selected list, not a transaction across every memory publisher. `aurora_command_contracts` validates legacy boolean setters before batch effects and stops failed tails. Existing registry-backed setters keep their separate shared settings authority. The catalog now fingerprints the goal module. `construct_hierarchical_tasks_text` retains descriptive action labels. Guarded proof: `tests/offline_basic_commands_smoke.py`; no provider/native/UI work or semantic scorer changes.

Implementation 37 (private CF2b): `aurora_task_continuation` is the shared process-local bounded-task/readback authority and pure Init request filter. Runtime setters/registry/transactions own configuration; `serialized_model_turn` reserves slots, `evaluate_turn_scheduler` admits wakes, and `mark_turn_scheduler_dispatch` acknowledges readback generation before inference. `publish_command_discovery` marks only results actually added to context. Request assembly exports dedup counts and task snapshot. Model-origin budget mutations/rollback are rejected before effect. No action/token/spend cap, native capture provenance or durable task store is claimed; legacy paths remain. See review and guarded runtime proof for tested stop boundaries.

Implementation 35 (private CF2a): `handle_queued_input` owns the exact pre-inference acknowledgement callback; `maybe_run_due_inference_turn` supplies it, and `mark_turn_scheduler_dispatch` only consumes an actual command-result wake. `evaluate_turn_scheduler` blocks automatic timers behind queued/active commands, unconsumed receipts and requested capture settling. `command_handler` publishes then acknowledges thread-queue work. `should_request_turn_after_command_result` uses typed batch-local effects rather than stale worker_last_* state. `DEFAULT_SCREENSHOT_REVIEW_PROMPT` follows current/legacy Init selection. New tests exercise real worker/model assembly with simulated inputs and synthetic captures; native capture timestamps, budgets and structured/dependency-aware batches remain roadmap work.

Implementation 34 delivery domain: external inbox → `TrackedInput` → `handle_queued_input` / legacy `chatgpt_process` → `serialized_model_turn` → prepared chat/Responses request → usable response or explicit failure/cancellation. `aurora_delivery_receipts` owns context-local initial-turn correlation; `write_external_bridge_log` remains the shared writer. IDs enter prompt diagnostics/request logs, not provider prompt text. Embedding/validation cannot claim delivery. Cancellation is local; no automatic retry or durable queue mutation is introduced. UI consumes the same evidence, never generic activity or matching text.

Implementation 33: history now includes the additive revision-checked UPDATE_MESSAGE binding, conversation row revisions, atomic text/pin plans and per-message GUI receipts. Computed PinnedInfo summaries stay read-only in this new path; legacy commands remain. Task-flow horizons retain full comma prose, strict command framing accepts word apostrophes, and Executed Commands is an explicit heading. Scheduler follow-up detects mixed capture/action receipts in either order. Scene evidence excludes quoted UI text and understands closed dialogue/location overlays. See the private Implementation 33 report for the ten-minute adapter result and the production-loop caveat.

Implementation 32 follow-up: optional task_flow admits bounded battle menu/confirm steps (single press or <=.25s hold), retaining legacy review and action locks. Goal completion now raises malformed/nonexistent-ID errors into shared receipts, stops batch tails and avoids duplicate completion events. The move_key human message identifies legacy timing as an estimate. These changes do not supply calibrated tile counting or immutable goal history.

Implementation 32: `set_assistant_policy` / `set_assistant_policy_command` expose legacy/task_flow with execution-lock enforcement. `evaluate_task_flow_permission` is a narrow optional branch before the existing assistant policy; it neither changes execution mode nor bypasses handler validation. Snapshot/default-profile adapters preserve the new setting through shared transactions and rollback. `AgentControls.apply_flow` exposes policy and execution drafts; `demand_preset` selects task_flow without changing execution/inference. Import-time dimensions now use already-read display geometry instead of a discarded capture. Production per-frame origin/DPI/freshness remains unfinished. Counts: 364 / 104 / 28 / 24; see current status and Implementation 32.

Implementation 31 (private): `aurora_conversation_delivery.SessionOutbox` tracks bounded panel-session submissions through the shared bridge and correlates ingestion by request/message/client IDs; it never claims provider delivery or retries. `conversation_activity` reads exported observations (including additive `conversation_io`). `OutboxWindow` inspects text/receipts and copies only complete display text into an empty main draft. `ConversationPopout` mirrors the selected view, retains a separate draft on withdraw and updates off-tab. `show_main_conversation` raises the main view. Panel `refresh_conversation_feedback` owns polling/preview; navigator preferences `conversation_send_feedback` and `legacy_chat_popout` retain old presentation paths. All legacy strip commands remain. CP1a is implemented; CP1b lifecycle correlation/durable retry/cancel, the remaining CP2 audit and CF/AT work remain pending.

Implementation 30 (private): `aurora_chatgpt_panel.SignInButtons` supplies the upper-right remembered-provider pill and explicit OpenAI circle. `ChatGPTConnection.request_sign_in` waits for status and coalesces pending clicks; `cancel_sign_in` cancels queued intent as well as an active login. Only OpenAI is implemented; buttons preserve runtime auth/inference settings. Utility header controls wrap; existing advanced entry points remain. CP1/CP2/CF1/CF2/AT1/AT2 are roadmap work, not implemented capabilities.

Implementation 29 (private): `aurora_agent_controls.AgentControls` adds compact drafts/effort/scope/speed/flow/auth controls through existing transaction/command authority. `aurora_chatgpt_panel.ChatGPTConnection` owns bounded connection UI jobs; `aurora_chatgpt_auth` owns per-account verified registration and protected atomic credentials/refresh; `aurora_chatgpt_transport` owns catalog validation and completed-only SSE Responses. `openai_chatgpt` never falls back to API keys. `SET_SERVICE_TIER` and next-plan `service_tier` preserve Regular default; provider tier is distinct from requested tier. Heartbeat zero is explicit off; command-driven capture uses request_only + per_capture. Counts: 363 commands / 103 reviewed / 27 settings / 24 views. Real bounded Sol→Astra→Sol subscription proof and limitations are in Implementation 29; older OAuth-unqualified notes below describe the legacy route and earlier snapshot.

Implementation 28: `ConversationArchive.last_order` tracks bounded observed order for relative-move metadata; original order and retained/current distinctions remain. OAuth review changes documentation only: existing `CodexOAuthManager` still uses the legacy ID-token exchange. New SIWC credential lifecycle and streaming transport are roadmap OA1–OA3, not implemented runtime capabilities. Native synthetic panel QA does not establish gameplay/capture portability.

November 4 / Implementation 27: Conversation observation is presentation infrastructure in `aurora_conversation.py`, with its Tk controller in `aurora_conversation_navigator.py`. Identity/observation hooks run under the existing history lock; the archive has its own bounded-copy lock. Current/retained exports, optional original/latest/event text and model text-budget estimates do not replace history authority, change prompt selection, or establish provider-delivery replay. Read the UI lite map and Implementation 27 for controls and limits.

## November 4 — scene evidence and recursive goals / Implementation 26

`aurora_gameplay_scene.classify_scene` owns bounded text evidence matching and reports freshness/source/conflicts. Runtime records parsed Scene/Observation sections before admission; `infer_gameplay_scene_legacy` retains the former heuristic under `game.scene_policy=legacy`. `aurora_goal_store` owns Goal IDs, recursive codec, validation and atomic task files; runtime adapters preserve list aliases and export typed `goal_file_results`. `goals.save_format=legacy` retains the old document shape; versioned adds an envelope, not immutable memory history. Both controls share settings/transactions/profiles and the Switchboard's advanced list. Native input/capture/gameplay acceptance is not claimed. See current status and Implementation 26.

## November 4 — Conversation-first friend preview / Implementation 22

`aurora_conversation.py` builds detached bounded current/retained views from HistoryContextService state; effective drop filters apply to current rows. The panel starts on Conversation, has a composer and optional system details, and retains Chat historical logs plus all 23 views. `Reopen last view` preserves the prior startup option. New routine models default to gpt-6.1-sol low; review role defaults to gpt-6-astra medium, with older models/configurations retained. The native bounded test sequence and limits are recorded in docs/reviews/2026-11-04/implementation-22.md. General gameplay/native testing remains deferred. Core R2b2b is still next after this user-directed preview.

## November 4 — R2b2a admission/receipts / Implementation 21

`aurora_retrieval_commands.py` now owns query defaults, shared parsing, optional argument_policy=legacy|strict, snapshot argument contracts and typed receipt construction. `aurora_command_contracts` calls it before batch execution and advertises named defaults/choices. Runtime `_build_retrieval_request` / shorthand remain thin compatibility adapters; `retrieval_pull_command` / `_execute_retrieval_pull_command` preserve display and attach effective evidence/correlation IDs. `execute_episodic_snapshot_command` serves the three existing snapshot handlers with count/identity/score receipts and truthful uncertainty. All 359 bindings remain; 97 reviewed contracts. Native testing stays paused. Next R2b2b is coherent publication and append/memory concurrency; see [reference](../../docs/reference-packs/memory-retrieval-reference.md).

## November 4 — R2b1 retained K-sets / Implementation 20

`aurora_retrieval_results.py` owns bounded canonical JSON retention, exact handle reads, item/content identities and shared inspection/promotion contracts. `run_episodic_retrieval` prepares optional retained evidence before feedback/publication; `result_mode=legacy` remains default. `show_retrieval_result_command` inspects full records, and `promote_episodic_retrieval_item(..., result_handle=...)` selects full source text independently of the current preview. Legacy no-handle promotion stays available. New snapshots use session-prefixed UUIDs; old IDs remain untouched.

`retrieval_results` follows existing action/log/control-plane receipt and mutation deduplication paths. Handles are runtime-memory only: 32 sets / 8 MiB / 1 MiB per set / 30 minutes. No provider calls on inspection, no implicit fallback/replay. See [retrieval reference](../../docs/reference-packs/memory-retrieval-reference.md). Next R2b2 covers broader retrieval/snapshot admission, coherent exported publication and mutation concurrency; V1/V3/G1 history remains planned. Native testing stays paused.

## Search dates — Implementation 19

`aurora_search_query.resolve_search_dates(options, evaluation_epoch=...)` owns before/after instant/day semantics, explicit-bound conflict checks, elapsed rolling periods, timezone calendar weeks/months and frozen anchors. It returns UTC/epoch boundaries and inclusion metadata. Normalization validates with a deterministic reference time; actual compilation resolves once using the runtime execution time unless an explicit anchor is supplied. `match_search_filter` enforces strict After equality and missing-date exclusion before provider work. `SearchFeedbackLedger.prepare` includes new controls in query identity. Raw/parser admission comes from SEARCH_DEFAULTS; compiled date evidence is exported/logged by `run_episodic_retrieval`. See memory retrieval reference for limitations: no immutable cursor or historical state reconstruction yet.

## Local offline validation — Implementation 18

- Entry: `launch_aurora_validation.cmd`; `aurora_validation_console.main` supports server, `--preview PROFILE.json` and `--run PROFILE.json`.
- Discovery: `build_command_catalog` plus `command_subsystems`; classification is presentation metadata, while existing contracts remain authoritative. `source_identity` fingerprints copied Python/UI inputs; connected repo/runtime identity stays unknown.
- Profiles/artifacts: `validate_profile`, `digest`, `write_json`, `ValidationService.save_profile/preview/records`. Raw profile schema is shared between UI and headless use.
- Lifecycle: `ValidationService.start/cancel/_run/close`; idempotent UUID requests, source-copy validation, one worker/store owner, bounded waits and exact owned cleanup. Restart marks unfinished evidence uncertain without replay.
- Fixture: `aurora_validation_worker.main` guards external I/O, uses synthetic tokenization and transport, sends three real runtime turns, admits interventions through `handle_commands`, verifies controller/provider-fixture selection and settings restoration. No existing runtime or arbitrary command runner.
- HTTP: `make_server` loopback/host/origin/bearer checks; static asset allowlist, bounded JSON and no-cache/CSP. UI and verification boundaries: Implementation 18 (development reference omitted from this snapshot).

## Repeat-search feedback — Implementation 17

SearchFeedbackLedger in aurora_search_query.py owns bounded query/session feedback with prepare/factor/publish. Runtime RETRIEVAL_FEEDBACK is its sole instance: prepare is non-mutating, zero-factor records are excluded before embeddings, nonzero penalties scale score contributions, and successful publication commits with optimistic result-token validation. This is ephemeral retrieval feedback, not a replacement settings authority.

## Conventional search boundary — Implementation 16

aurora_search_query.py owns strict named search options, bounded text grammar, timezone/date semantics, filter matching evidence and deterministic explicit ordering. run_episodic_retrieval compiles once, checks cancellation while filtering, embeds only eligible records, then ranks/pages and exports counts. No new provider or settings authority is introduced. Legacy lexical/scorer paths remain separate; see memory-retrieval-reference.md.

## Episodic retrieval boundary — Implementation 15

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

aurora2.py retains command adapters, lexical/rating/distribution scoring, state publication, planning and promotion. aurora_episodic_retrieval.py owns additive query policy, elapsed-time scoring, record/vector validation, content identities, deduplicated bounded embedding batches and atomic cache serialization. Providers and cancellation remain injected through the existing runtime owner; this module starts no workers and introduces no settings authority. Defaults retain ordinal recency and permissive ranking.

## Local history authority — Implementation 14 / 4B4d

aurora_history_controls.py owns parse_history_arguments, history_exemption, plan_history_change, history_summary and save_history_export. Runtime execute_history_command owns all 13 local history bindings, retention checks, HISTORY_LOCK, local model cancellation and active Responses invalidation. update_chat_history checks the model generation under the same lock; _build_history_context_read_state makes detached snapshots while preserving selection identity. Existing append/image/derived-pin/legacy helpers serialize writes. These helpers retain their own retention/policy behavior; deeper context-mark/Prompt Inclusion and private-history service review remains 4B4e.

History receipts carry before/after versions/counts, added timestamps, model/provider context effects and exact export paths/hashes. Exports remain text with image previews, not restoration checkpoints. Raw batches have no cross-command rollback or history CAS. Preserve capability alternatives: random default, explicit oldest/newest, first-match edit/all-match delete, protected priority within CLEAR%'s total budget. Evidence: docs/reviews/2026-10-01/implementation-14.md.

## Pending-command ownership — Implementation 13

aurora_pending_commands.py owns PendingCommandLedger, stable identities, optional queue-version selection, reserve/finish and aurora_pending_command_result_v1. Existing runtime planning functions retain scoring, support, insert/replace, conflict and scene policies under the ledger lock; reserved/uncertain items are excluded from automatic planning changes. queue_pending_model_command keeps frozen prepared routes. evaluate_pending_command_policy checks every batch member; execute_pending_approval and submit_pending_entry serve manual/auto paths without holding the queue lock over execution. handle_commands, ingest_command_result and control-plane duplicate receipts preserve pending_command_results and pending_id/pending_attempt_id. The panel consumes pending_queue and uses ID/version selectors. See docs/reviews/2026-09-07/implementation-13.md and SHOW_REFERENCE_PACK(aurora_control_plane_cli).

## Defaults profile service — 4B4b

aurora_default_profiles.py owns the 60-field profile schema, registry-backed coercion, preset expansion, file status, bounded atomic persistence and command contracts. Runtime build_runtime_preferences_snapshot, _apply_default_profile and execute_default_profile_command own synchronized state, existing setter invocation, restoration and typed results. The four original handlers remain. _write_default_profile_field retains paired always/hide controls and game-source handling; drip pruning waits until apply readback succeeds. reapply is the existing default; changed_only is optional. aurora_control_plane retains default_profile_results across duplicate receipts. The panel reads personal_status/personal_error through its existing Defaults and recovery surfaces.

## Queued one-turn inference — 4B4a

Runtime get_next_inference_plan_snapshot, set_next_inference_plan_from_pairs, clear_next_inference_plan and resolve_next_inference_plan_for_turn share SETTINGS_TRANSACTION_LOCK. execute_inference_plan_command serves all four existing plan handlers; handle_commands and aurora_control_plane retain inference_plan_results through correlated and duplicate receipts. aurora_command_contracts owns parse_inference_plan_arguments, normalize_next_inference_pairs, _inference_option_segments, inference_plan_version and describe_inference_plan_contract. infer_turn_model_controls retains the consumed inference_plan_id. Provider-specific normalization and transport behavior are unchanged. 4B4b defaults is implemented; 4B4c is implemented; prompt/history controls are next; see the capability commitment and Implementation 11.

## Public-agent pattern mapping — research boundary

See the September 6 survey (development reference omitted from this snapshot) for pinned sources and H0–H5 candidates. Existing discovery belongs to aurora_command_catalog/build_command_catalog and runtime search_commands_command/show_reference_pack_command; context work maps to the prompt ledger and episodic retrieval; future worker calls must use shared admission/settings/receipts/cancellation and HeldInputLedger. General-purpose analysis workers, recursive execution and durable workflow checkpoints remain proposals, not new runtime symbols. Keep provider-aware Responses history handling separate from generic context projections. 4B4 remains next.

## Held-input ownership (4B3)

`aurora_input_ownership.py` owns HeldInputLedger, InputOwnershipError and cooperative_move. Runtime input_key_callbacks/acquire_key_input/acquire_mouse_input freeze native routes; release_owned_key/release_input_leases perform attributable cleanup. cancel_command_inputs couples generation cancellation to owned releases; set_agent_running(False) invokes it on shutdown. execute_command_entry supplies request identity; handle_commands preserves input_cleanup_results/held_input_results and desktop ownership evidence. aurora_control_plane preserves these on duplicate receipts. No background input watcher. See the held-input reference; 4B4 is next.


## Adaptive reasoning boundary — September 6

- `aurora_responses_reasoning.py`: pure request item conversion, completed-output parsing, `ResponsesReasoningSession` and inspectable limits/identity/generation. No network or native input.
- `aurora2.py`: `post_openai_turn_request` selects transport; `send_prompt_to_chatgpt` supplies bootstrap/current context; existing controls select desired effort. `evaluate_assistant_command_policy` and reviewed command contracts admit only the narrow next-turn request automatically.
- `aurora_settings_registry.py`: model.transport through existing versioned settings service; reset is a reviewed command with reasoning lock. History edits call `invalidate_responses_history`; cancellation rejects stale completions.
- `aurora2_control_panel.py`: Transport form/readback and concise effort/context status. Legacy shadow preview is separately scoped.
- Read `docs/reference-packs/adaptive-reasoning-reference.md`; search the shared skeleton for `ResponsesReasoningSession` and the runtime skeleton for the named functions. Astra/API-key only; text/image input and completed text output; no automatic replay, fallback, truncation or compaction. Active prompt omission/inclusion is blocked pending parity. Live provider acceptance/cache measurement, native GUI/gameplay and full clean installation remain unproved. Keep native capture off unless separately resumed.

## Freshness Note - 2026-09-05

- Current entry point: `docs/notes/aurora_current_status.md`. September implementations cover launch/ingress, cancellation/captures, panel refresh/layout, source-backed command discovery and portable reference generation. Manual GUI QA remains open. August FL activation remains dated proof, not current connection status.

- Current parent-repo truth: Portal intake remains parked; observation adapters and sibling ownership are preserved. September 4B2c routing is implemented. 4B3 ownership and cooperative input cancellation are implemented. Next is 4B4 remaining high-impact mutation families, 4C measured performance and snapshot publication, and 4D GUI/clean-install proof. The 298 legacy runtime bindings are coverage backlog, not 298 known defects. Preserve all capabilities; group related commands by their shared service and prioritize actual operator workflows. OBS remains deferred; Browser stays with its own task. Do not restart native capture automatically. Use the compact status/roadmap for the active queue.
- Auth/app-server posture: `api_key` remains Aurora's default. `codex_oauth`, `auto`, and any Codex app-server probing are opt-in reconnaissance lanes, not default runtime transport changes.
- Agent/subagent posture: Aurora's local agent lane is metadata-first; Codex subagents are an external sibling workflow until an explicit summary-intake window maps them into Aurora tasks/receipts.
- Regenerate with the target checkout's `regenerate_aurora_skill_refs.ps1 -Force`; `-Check` verifies without publication and `-SyncSkills` exports installed references. The repository owns the generator and curated maps. No personal skill installation is required for generation.

## 1. Startup, Config, and Mode Resolution

Owns CLI flags, env vars, auth mode, model defaults, live/offline mode, overlay toggles, smoke-test settings, and runtime locks.

Gameplay profile note:

- `AURORA_GAME_PROFILE` and `SET_GAME_PROFILE` / `SHOW_GAME_PROFILE` keep FireRed-vs-Blue assumptions aligned across prompts, smoke checks, and state export.
- The current live-test default profile is `firered`.
- FireRed keeps `Start = h` on this machine, but emulator save-state handling remains operator-only reference material: slot `#1` save-state is `F1`, and slot `#1` load/restart is `Shift+F1`.
- Do not treat emulator save-state shortcuts as callable Aurora commands.

Primary anchors:

- `build_cli_parser`
- `apply_cli_args`
- `build_startup_config_snapshot`
- `set_auth_mode`
- `set_live_mode`
- `set_execution_mode`
- `set_action_mode`

## 2. State and Memory Surfaces

Owns the live agent state store, route memory, recent context, notes, pending commands, and small snapshots for the UI.

Primary anchors:

- `AgentState`
- `agent_state = AgentState().bind_globals()`
- `runtime_state`
- `build_memory_tier_snapshot`
- `build_command_drip_snapshot`

## 3. Command Intake and Dispatch

Owns structured command recognition, alias resolution, policy checks, pending-queue behavior, and dispatch to runtime/game/desktop handlers.

`aurora_command_contracts.py` owns positional parsing, key/text validation, DesktopActionContext and its context-local scope, and typed desktop receipts. Runtime `resolve_desktop_action_context` freezes explicit/implicit namespace, configured backend and effective key without foreground heuristics; `projected_action_mode` accounts for known preceding setters/transactions. `prepare_command_batch` carries the context through queueing; `handle_commands` installs it per action and records action_route. Explicit PYAG stays literal; GB keeps game translation/focus for scancode, keyboard and PyAutoGUI. Timed release uses the same admitted backend/key. Internal calls without prepared context retain their compatibility routing. Indefinite held-input ownership and native duration limits remain next; submitted input still does not prove app effects.

`aurora_settings_registry.py` owns the 22 setting definitions, command/value aliases and coercion. `parse_setting_command_arguments` derives contracts for 23 command names, retaining no-value reads; the 22 low-level setters share that coercion. `execute_registered_setting_command` and `observe_registered_setting` use `SETTINGS_TRANSACTION_LOCK`, canonical handler arguments and one snapshot per observation. `setting_results` holds before/after values/versions and observed/not-started/uncertain outcomes. Lock checks happen at execution so an explicit preceding unlock can work. Failed reviewed setters block the remaining batch; raw batches do not gain atomic rollback or expected-version checks. Five setting shortcuts also use these observations. The two lock commands share registry spellings and the same transaction lock, emitting lock_results; encoded transactions share static admission/planner validation and stop the tail after failure. Unexpected transaction service errors report failed_uncertain with available versions.

`aurora_command_catalog.py` statically reads both dispatch dictionaries: all 335 runtime + 19 desktop bindings remain. Catalog provenance includes the settings registry and transaction validator. Coverage is 53 reviewed bindings and 301 legacy runtime bindings. Reviewed settings/shortcuts, locks, transactions and desktop failures stop the tail; other runtime continuation semantics remain unchanged. `execute_runtime_lock_command` and `execute_registered_setting_command` share `SETTINGS_TRANSACTION_LOCK`; `parse_settings_transaction_command` shares static validation with the planner. Runtime/helper skeletons map these boundaries.

Primary anchors:

- `is_known_command_prefixes`
- `is_known_command`
- `handle_commands`
- `enqueue_or_execute_command`
- `approve_pending_command`
- `clear_pending_commands_command`
- `command_dispatch`

## 4. External Operator Bridge

Owns file-backed operator input, security/passcode rules, mutation admission, and the raw-command path used by the control panel and remote bridge.

Client-side files:

- `aurora_control_plane.py`: shared envelope writer, receipt reader, fsynced mutation-admission journal, status/process helpers, and read-only dashboard snapshot/formatter
- `aurora_settings_registry.py`: shared 22-setting typed metadata, validation, compatibility-default lookup, lock metadata, runtime-state readback, and opaque settings versions
- `aurora_settings_transactions.py`: transaction schemas/codec, complete-batch planning, scope/lock/version checks, existing-setter invocation metadata, and nested receipt extraction
- `aurora_cli.py`: status/dashboard/command/capture/receipts/doctor/settings plus generated command discovery, structured completion, local history, and interactive shell
- `aurora_mcp_server.py`: stdio JSON-RPC/MCP lifecycle, five read-only tools, eight allowlisted resources, two prompts, and self-check; it reuses read helpers but never writes the bridge
- `blender_readonly_mcp_server.py`: separate stdio MCP/CLI adapter with two read-only tools, two resources, one prompt, strict `.blend` allowlisting, fixed headless arguments, and no arbitrary Python or Blender operator authority
- `blender_scene_inventory.py`: bounded in-Blender data inventory used only by the fixed adapter command; reads `bpy.data` and scene/object metadata without save, render, import, export, or mutation calls
- `fl_studio_readonly_mcp_server.py`: separate stdio MCP/CLI adapter with three read-only tools, three resources, one prompt, Aurora-prefixed SysEx capture, fixed heartbeat allowlisting, correlated observation receipts, and no DAW-control authority
- `fl_studio_device_script.py`: FL MIDI lifecycle/idle heartbeat emitter with bounded version/project-dirty/transport readback and no filesystem, MIDI-input, or mutation callbacks
- `aurora.cmd` / `auroractl.cmd`: Windows launchers
- `aurora-mcp.cmd`, `blender-readonly-mcp.cmd`, and `fl-studio-readonly-mcp.cmd`: Windows read-only adapter launchers

Primary anchors:

- `append_external_message_record`
- `poll_external_inbox_messages`
- `poll_external_reply_bridges`
- `can_dispatch_external_raw_command`
- `authorize_operator`
- `append_bridge_request`
- `wait_for_command_receipt`
- `receipt_matches_request` / `collect_command_receipts`
- `build_operator_status`
- `build_operator_dashboard`
- `format_operator_dashboard`
- `MutationAdmissionJournal`
- `get_mutation_admission_journal`
- `build_mutation_decision_receipt`
- `record_mutation_terminal_result`

Operator shell/discovery anchors:

- `load_command_catalog` / `filter_command_catalog`
- `complete_shell_line` / `complete_command`
- `append_shell_history` / `read_shell_history` / `history_command`
- `_shell_cli_argv` / `execute_shell_line` / `shell_command`
- `_windows_read_shell_line`
- `dashboard_command`

The shell reads the generated command TSV and registry metadata locally. Known direct runtime commands still enter the ordinary bridge path; unknown raw text requires explicit `command`/`send`. Bare CLI builtins take precedence over same-named runtime aliases. Local history excludes plausibly secret-bearing lines and is not execution evidence. There is no OS command escape or automatic replay.

The dashboard reads the same state, settings, receipt, and mutation-admission sources. `aurora_operator_dashboard_v1` includes bounded sanitized `aurora_operator_dashboard_event_v1` rows with command names and lifecycle metadata but no raw command arguments. CLI text/JSON/watch/JSONL and the Control Panel Dashboard tab/popout consume this structure directly. It is an observation surface, not another execution path.

CLI and Control Panel receipt waits match normalized `client_id + request_id` across command and bridge events. Legacy source/message identity fallback remains supported; unfiltered receipt history remains cross-client. This aligns client correlation with mutation admission identity.

The MCP facade is another observation adapter. `AuroraReadOnlyMcpServer` exposes status/dashboard/catalog/settings/map resources and map-first/operator-preflight prompts. `aurora://handoff/current` serves the compact current-status note; the detailed roadmap/history is loaded only when needed. Its tool annotations are read-only and nondestructive; its authority posture explicitly disables command submission, settings mutation, uncertain replay, model calls, desktop control, external-app control, and MCP client hosting.

The Blender adapter is intentionally a sibling server rather than an Aurora runtime feature. `BlenderReadOnlyMcpServer` discovers the pinned local Blender executable, validates explicit `.blend` paths beneath configured roots, launches background/factory-startup Blender with autoexec and dependency-graph-on-load disabled, and parses only the bundled inventory marker. Codex can coordinate `aurora-readonly` and `blender-readonly`, but neither server can call or mutate the other. The boundary is application-level rather than an OS sandbox; Blender may resolve linked dependencies named inside a trusted scene.

The FL Studio adapter is another sibling server. `FlStudioReadOnlyMcpServer` discovers the pinned local FL installation, captures only Aurora-prefixed SysEx from the linked virtual MIDI input, validates/sanitizes one fixed Aurora heartbeat, atomically writes the canonical outer readback, and returns explicit stale/missing/unavailable states plus correlated read-only receipts. `fl_studio_device_script.py` emits the heartbeat from FL lifecycle/idle callbacks but performs no filesystem I/O and defines no MIDI-input callback or transport/project/plugin mutation call. Codex may coordinate this observation with Aurora/Blender context; none of the servers call or mutate another.

MCP anchors:

- `AuroraReadOnlyMcpServer`
- `tool_definitions`
- `resource_definitions`
- `_call_tool`
- `_read_resource`
- `_get_prompt`
- `handle_message`
- `run_stdio`

Blender MCP anchors:

- `BlenderReadOnlyMcpServer`
- `discover_blender_executable`
- `_validate_scene_path`
- `installation_snapshot`
- `inspect_scene_file`
- `build_inventory`

FL Studio MCP/device anchors:

- `FlStudioReadOnlyMcpServer`
- `discover_fl_studio_executable`
- `discover_fl_studio_readback_path`
- `install_device_script`
- `decode_fl_studio_sysex_data`
- `bridge_status`
- `observation_receipt`
- `_capture_readback_from_midi`
- `_cached_bridge_status`
- `_emit_readback`
- `OnInit`
- `OnIdle`

FL cache freshness requires positive/nonfuture source capture time and both source/file ages within the configured limit. The cache reader takes bounded bytes and metadata from the same handle. Concurrent capture writes use unique same-directory temporary files, atomic replacement, and own-file-only cleanup. Valid schema alone is not active-connection evidence.

Typed settings and transaction path:

- `registry_summary`
- `resolve_setting_definition`
- `coerce_setting_value`
- `build_setting_readback`
- `build_settings_snapshot`
- `build_settings_version`
- `plan_settings_transaction`
- `execute_settings_transaction_request`
- CLI `settings list|get|describe|version|preview|apply|rollback`

The source of effective-value evidence is `aurora_control_panel_state.json`. A stopped runtime returns `last_observed`, not `effective`, and transaction submission is refused rather than queued. Apply/rollback are atomic runtime-session operations with version preconditions and same-session rollback handles. The Control Panel is a nonblocking client of that service.

Mutation admission path:

- known external commands outside `READONLY_OPERATOR_COMMANDS` are classified as mutations;
- Aurora fsyncs an admission keyed by normalized `client_id + request_id` before dispatch;
- the reservation stores command name plus SHA-256 digest rather than another raw command copy;
- exact duplicates return the prior terminal result or explicit uncertain/no-replay status without dispatch;
- changed-payload identity reuse returns terminal `request_conflict`;
- terminal command results reconcile the journal, including command-log recovery after a crash between result logging and terminal-journal append;
- read-only commands remain independently repeatable.

This is duplicate-dispatch prevention, not a persistent settings service or an automatic uncertainty resolver.

## 5. Screenshot, Vision, and Gameplay Loop

Owns screenshot capture, game-context inference, route observations, smoke-test behavior, and model turn cadence.

Primary anchors:

- `screenshot_capture`
- `get_latest_runtime_screenshot_path`
- `infer_operating_context`
- `infer_gameplay_scene`
- `maybe_run_smoke_test_step`
- `handle_queued_input`

## 6. UI Export Boundary

Owns the control-panel JSON snapshot and runtime feedback surfaced to the separate Tk UI.

Primary anchors:

- `build_control_panel_state_snapshot`
- `write_control_panel_state_snapshot`
- `launch_control_panel`
- `terminate_launched_control_panel`

## 7. Worker Lifecycle and Shutdown

Owns thread/process startup, restart handling, error queues, and runtime cleanup.

Primary anchors:

- `Context`
- `start_process`
- `monitor_and_restart_processes`
- `main`
- `shutdown_runtime_command`

## Cross-Cutting Files

- `aurora_command_execution_log.jsonl`: executed commands, smoke events, approvals
- `aurora_mutation_admission_log.jsonl`: append-before-dispatch mutation reservations and terminal reconciliation rows
- `aurora_chat_history_log.jsonl`: chat/history tail
- `aurora_external_bridge_log.jsonl`: inbox/drop ingestion
- `aurora_control_panel_state.json`: UI-facing snapshot

November 4 prompt/novice follow-up: current/legacy init profiles and command-discovery context delivery are selectable at startup; see README_FOR_AI.md. Primary runtime start is paused/safe, enable preserves settings, legacy orb activation remains, Advanced opens expanded with Dock retained, and Conversation has Quick start. See README_FOR_HUMANS.md.
