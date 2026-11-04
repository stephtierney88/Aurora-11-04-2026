# Log and State Field Reference

## Purpose
- Explain the main exported fields Aurora and operators use during smoke and soak testing.

## `aurora_control_panel_state.json`
- `timestamp`: latest export time for freshness checks
- `runtime_summary`: compact live/offline, execution/action, scheduler, model, and auth summary
- `auth_summary`: configured and resolved auth path, including unresolved auth errors when present
- `latest_feedback`: recent runtime/operator feedback lines, including raw-command dispatch and command-result summaries
- `last_screenshot_path`: most recent screenshot Aurora exported
- `last_screenshot_timestamp`: timestamp tied to the current screenshot
- `modes.live`: whether model/live response flow is enabled
- `modes.execution`: `safe`, `assist`, or `auto`
- `modes.action`: active action mode such as `gb` or `pyag`
- `modes.game_profile`: current Pokemon profile
- `scheduler.profile`: active named scheduler profile such as `balanced`, `responsive`, `conservative`, `legacy`, or `custom`
- `scheduler.profile_description`: short operator-facing explanation of the active profile
- `scheduler.mode`: `hybrid`, `event`, or `per_capture`
- `scheduler.description`: short operator-facing explanation of the active scheduler
- `scheduler.heartbeat_seconds`: fixed safety heartbeat for event-driven waking
- `scheduler.min_gap_seconds`: minimum spacing between automatic turns
- `scheduler.capture_wake_enabled`: whether hybrid mode can wake on a settled capture change
- `scheduler.capture_wake_debounce_seconds`: settle delay before hybrid capture-change wakes
- `scheduler.post_action_settle_seconds`: short settle window after a command result before follow-up turns may run
- `scheduler.last_wake_reason`: most recent reason a turn was launched
- `scheduler.last_wake_details`: short diagnostic details for the most recent wake
- `scheduler.pending_reasons`: reasons the scheduler currently believes a turn is due
- `scheduler.capture_counter`: count of processed captures seen by the scheduler
- `scheduler.last_submitted_capture_counter`: capture counter used for the last submitted model turn
- `scheduler.pending_command_result`: whether Aurora is waiting to follow up on a command result
- `queue_bridge.latest_raw_inbox_request_id`: correlation id for the newest raw inbox request; legacy rows fall back to `message_id`
- `queue_bridge.latest_bridge_request_id`: correlation id for the newest raw bridge delivery/rejection event
- `queue_bridge.latest_external_command_result_request_id`: correlation id on the newest external command result
- `queue_bridge.command_result_caught_up`: exact request-id match for new correlated records, with timestamp fallback only for legacy records
- `settings.schema_version`: runtime transaction-status contract, currently `aurora_settings_transaction_runtime_v1`
- `settings.registry`: bounded registry summary for the 22 registered controls and 36 aliases
- `settings.version`: opaque version used by preview/apply/rollback preconditions
- `settings.scope`: currently `runtime_session`; persistent settings transactions are not enabled
- `settings.write_enabled` / `settings.atomic_apply` / `settings.expected_version_required`: transaction capability flags
- `settings.transaction_active`: whether one settings transaction currently holds the runtime transaction boundary
- `settings.rollback_handle_count`: available bounded same-session rollback handles
- `settings.last_receipt`: compact summary of the latest settings transaction receipt
- `planning.gameplay_scene`: Aurora's current scene guess
- `planning.game_profile_save_note`: profile-specific save-state reminder
- `episodic_memory.enabled`: whether compact episodic snapshot writing is active
- `episodic_memory.interval_seconds`: periodic snapshot cadence
- `episodic_memory.snapshot_count`: count of retained JSONL snapshot rows
- `episodic_memory.last_snapshot_timestamp`: newest snapshot timestamp
- `episodic_memory.last_snapshot_reason`: why the newest snapshot was written
- `episodic_memory.embeddings_mode`: whether episodic retrieval is lexical-only, lexical with embedding fallback, or embedding-required
- `episodic_memory.embedding_model`: active embedding model name for episodic retrieval
- `episodic_memory.embedding_cache_entries`: count of locally cached embedding vectors used to avoid repeated recomputation
- `episodic_memory.planning_assist_mode`: whether bounded planning-turn episodic retrieval is off, review-only, critique-only, or both
- `episodic_memory.planning_assist_k`: how many episodic memories a bounded planning turn may inject
- `episodic_memory.planning_assist_cooldown_turns`: minimum turn gap before bounded planning retrieval may run again
- `episodic_memory.last_search_query`: most recent episodic-memory search query Aurora handled
- `episodic_memory.last_retrieval_count`: how many entries the last weighted retrieval pull returned
- `episodic_memory.last_retrieval_summary`: short summary of the last weighted retrieval request
- `episodic_memory.last_retrieval_backend`: whether the last retrieval ran lexical-only, used embeddings, or failed an embedding-required request
- `episodic_memory.last_retrieval_items`: compact cached payload of the last weighted retrieval results, including score breakdowns and summary/tag previews
- `episodic_memory.planning_last_query`: most recent automatically built query used by bounded planning retrieval
- `episodic_memory.planning_last_count`: how many memories bounded planning retrieval last selected
- `episodic_memory.planning_last_summary`: short summary of the last bounded planning retrieval
- `episodic_memory.planning_last_backend`: backend used by the last bounded planning retrieval
- `episodic_memory.planning_last_items`: compact cached payload of the last bounded planning retrieval
- `episodic_memory.planning_last_reason`: whether the last bounded planning retrieval was for a review or critique turn
- `episodic_memory.planning_last_turn`: inference turn number where bounded planning retrieval last ran
- `episodic_memory.planning_last_error`: last bounded planning retrieval error, if any
- `episodic_memory.planning_last_decision`: whether the latest eligible planning turn used retrieval or intentionally skipped it
- `episodic_memory.planning_last_decision_turn`: inference turn number tied to the latest planning-assist decision
- `episodic_memory.planning_cooldown_remaining_turns`: remaining cooldown before bounded planning retrieval may run again
- `episodic_memory.planning_next_eligible_turn`: next inference turn where bounded planning retrieval is eligible after a prior use
- `episodic_memory.planning_turns_since_last`: turn gap since the last bounded planning retrieval actually ran
- `episodic_memory.last_promoted_target`: last live-memory bucket a retrieved item was promoted into
- `episodic_memory.last_promoted_summary`: summary text that was last promoted into live working memory
- `episodic_memory.last_promoted_snapshot_id`: snapshot id of the last promoted retrieval item
- `episodic_memory.last_promoted_timestamp`: source timestamp remembered for the last promoted retrieval item
- `gameplay.visibility`: `visible`, `obstructed`, or `unknown`
- `gameplay.visibility_reason`: why Aurora chose that visibility state
- `gameplay.foreground_window`: latest foreground title seen by the runtime
- `gameplay.last_key`: latest key Aurora believes was sent
- `gameplay.last_command`: latest gameplay command Aurora believes was executed
- `gameplay.last_input_backend`: keyboard/input backend used
- `gameplay.last_input_focus_ok`: whether focus recovery reported success before input
- `gameplay.last_input_focus_reason`: short focus/failure summary
- `gameplay.last_focus_recovery_summary`: summary of the most recent emulator recovery attempt
- `recent_action_intents`: recent command intent summaries surfaced for operator review
- `command_drip`: multi-turn command snapshot with current/future buckets, executed/held/failed lanes, pending queue settings, and short command metadata
- `pending_commands`: compact pending assistant-command rows used by the Pending tab
- `paths`: runtime-exported file locations for screenshots, command log, mutation admission log, chat log, episodic memory, external inbox, state file, and model catalog
- `mutation_admission`: `aurora_mutation_admission_v1` counts/path with reserved, admitted, rejected, terminal, and uncertain totals plus `no_automatic_replay=true`

## `aurora_command_execution_log.jsonl`
- Append-only execution history for runtime commands and desktop actions
- Useful for confirming whether Aurora dispatched a command even if the UI did not visibly change
- Main event types:
  - `command_result`: one processed/rejected command batch with command text, source, status, expanded/executed/failed commands, timings, foreground/input fields, and mouse position
  - `episodic_snapshot`: compact memory snapshot event with trigger/reason, snapshot id, importance, gameplay scene, and summary hash
  - smoke/test events: bounded runtime smoke progress markers when smoke profiles are active
- Command-state-log truth check:
  - raw operator command should appear as `message_ingested` in `aurora_external_bridge_log.jsonl`
  - the corresponding execution should appear as `command_result` in this log
  - the next state export should surface the effect through `latest_feedback`, `modes`, `command_drip`, `recent_action_intents`, or a domain-specific state block
- Correlated external command results added in Window 23 use `receipt_schema_version=aurora_command_receipt_v1` and carry `receipt_id`, `request_id`, `message_id`, `client_id`, `status`, `outcome_status`, `delivery_status`, and `terminal`.
- Slice 5 mutating-command results additionally carry `mutation_admission_schema_version`, `mutation_admission_id`, `command_digest`, `admission_status`, `duplicate_suppressed`, `replay_attempted`, and `replayed`. Duplicate terminal responses preserve useful prior result details but use the current delivery's `message_id` and `delivery_status=duplicate_suppressed`.
- Window 23 Slice 3 settings commands also carry `settings_transaction_receipts`, a list of nested `aurora_settings_transaction_receipt_v1` rows. Each row identifies the operation/status and before/after versions, plus validation errors, effective change readback, or rollback-handle metadata when applicable. The nested receipt is the settings-domain result; the outer `aurora_command_receipt_v1` remains the bridge/command-delivery result.
- Window 23 Slice 7 derives bounded `aurora_operator_dashboard_event_v1` rows from recent receipts for the shared read-only dashboard. These rows retain command name and lifecycle metadata but intentionally omit raw command arguments; they are a view contract, not an additional append-only log.
- Settings rollback handles are bounded, single-use, and runtime-local. They expire on shutdown and must not be inferred to provide durable replay or crash recovery.
- Historical Slice 1 rows used `request_id` for correlation only. From Slice 5 onward, recognized mutating raw commands reserve `client_id + request_id` before dispatch; read-only commands remain repeatable and do not reserve mutation identities.

## `aurora_mutation_admission_log.jsonl`
- Fsynced append-only admission truth for recognized mutating raw commands
- Schema: `aurora_mutation_admission_v1`
- `mutation_admitted` / `mutation_rejected` rows reserve `client_id + request_id` with deterministic `admission_id`, `message_id`, command name/hash, disposition, and `replay_attempted=false`
- `mutation_terminal` rows attach the sanitized terminal command receipt after ordinary command-result logging
- Restart recovery can use a matching nonduplicate terminal command row if the command log reached disk before the terminal journal row
- Same identity and same hash returns either the prior terminal result or explicit `duplicate_uncertain`; same identity and changed hash returns terminal `request_conflict`
- An admission without terminal proof is not replayed automatically. It remains counted as uncertain until a future explicit reconciliation design exists.

## `aurora_cli_history.jsonl`
- Local operator-shell convenience history introduced in Window 23 Slice 6; it is not runtime execution evidence.
- Schema: `aurora_cli_history_v1`.
- Fields: `timestamp`, `created_at_epoch`, `source=aurora_shell`, normalized `command`, and integer `exit_code`.
- Writes are append-only and fsynced. `history clear --yes` replaces the local file explicitly; clear is refused without `--yes`.
- Empty or oversized commands and lines matching passcode, password, API-key, secret, access/refresh-token, bearer, or authorization patterns are not stored or returned.
- `aurora shell --no-history` disables history loading and writes for that session.
- Use `aurora_command_execution_log.jsonl`, exact receipts, and `aurora_mutation_admission_log.jsonl` to decide whether a runtime command executed. Shell history only says what this local shell attempted and its client-side exit code.

## `aurora_chat_history_log.jsonl`
- Append-only conversation history used to inspect what the model was told and how it responded
- Useful for coherence checks during interrogation soaks

## `aurora_external_bridge_log.jsonl`
- External operator bridge activity
- Useful for verifying that the control panel, harness, or outside tools successfully injected commands or tester messages
- For raw-command paths, expect:
  - `event=message_ingested`
  - `ingest_mode=raw`
  - `dispatched_as_command=true`
  - `request_id`, `message_id`, and `client_id` on `aurora_bridge_request_v1` producers
  - `delivery_status=delivered` when admitted for command dispatch
  - `preview` matching the command text
- Rejections appear as `message_rejected` with a reason and a terminal correlated `command_result` receipt; these usually mean passcode/security gating or unauthorized command text, not necessarily a crashed runtime.
- Slice 5 duplicate paths add `mutation_duplicate_suppressed` or `mutation_request_conflict` bridge events before the common `message_ingested` row. The common row carries admission id/status, command hash, duplicate flag, and `replay_attempted=false`.

## `aurora_memory/episodic_snapshots.jsonl`
- Append-only compact episodic memory foundation
- Each row is a bounded continuity snapshot with:
  - timestamp
  - trigger/reason
  - summary text
  - tags
  - importance/confidence/outcome scores

## `aurora_memory/episodic_embedding_cache.json`
- Local embedding cache keyed by normalized text and model name
- Used to avoid repeated OpenAI embedding requests for the same query/snapshot text
- Helpful during debugging because cache growth is a visible signal that semantic retrieval is actually exercising the embedding backend

## Common soak interpretations
- fresh state + stale screenshot usually means screenshot path/capture trouble
- changing chat history + obstructed gameplay often means the model is alive but looking at the wrong window
- correct last key + no scene change often means focus or emulator menu interception
- retrieval backend stays `lexical` with cache count `0` usually means embeddings are off, unavailable, or the retrieval request fell back before vectors were fetched
