# Aurora commands — details

Help signatures are documentation; only contracts marked pre_dispatch are validated before a batch executes.

### ADD_APRIORITY_GOAL

- Signature: `ADD_APRIORITY_GOAL(text)` (reviewed_contract)
- Summary: Add non-empty text to the named memory list, retaining its existing deduplication/retention policy.
- Handler: `add_apriority_goal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: apriority_tasks

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### ADD_GOAL

- Signature: `ADD_GOAL(goal_text[, priority, significance])` (reviewed_contract)
- Summary: Add a goal with opaque priority/significance labels; duplicates are unchanged, not relabeled. Accepts comma fields or one semicolon-delimited argument.
- Handler: `add_goal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: goals_list

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`
- Parameter: `{"default": "No Priority", "name": "priority", "required": false, "type": "string"}`
- Parameter: `{"default": "No Significance", "name": "significance", "required": false, "type": "string"}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### ADD_JOURNAL

- Signature: `ADD_JOURNAL(text)` (reviewed_contract)
- Summary: Add non-empty text to the named memory list, retaining its existing deduplication/retention policy.
- Handler: `add_journal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: journal_entries

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### ADD_MODEL

- Signature: `ADD_MODEL(name)` (help_text)
- Summary: Validate a model with a short test call and add it to the custom Aurora catalog.
- Handler: `add_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ADD_OVERARCHING_GOAL

- Signature: `ADD_OVERARCHING_GOAL(text)` (reviewed_contract)
- Summary: Add non-empty text to the named memory list, retaining its existing deduplication/retention policy.
- Handler: `add_overarching_goal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: overarching_goals

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### ADD_UNKNOWN_PRIORITY

- Signature: `ADD_UNKNOWN_PRIORITY(text)` (reviewed_contract)
- Summary: Add non-empty text to the named memory list, retaining its existing deduplication/retention policy.
- Handler: `add_unknown_priority_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: unknown_priority_candidates

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### APPEND_AGENT_HISTORY

- Signature: `APPEND_AGENT_HISTORY(agent_id, visibility=private|parent_visible, summary=..., text=..., note=...)` (help_text)
- Summary: Append an explicit operator note to one sub-agent private JSONL log without writing parent chat history, prompts, Pending Commands, or execution queues.
- Handler: `append_agent_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### APPLY_PERSONAL_DEFAULTS

- Signature: `APPLY_PERSONAL_DEFAULTS([mode])` (reviewed_contract)
- Summary: Validate and apply the saved personal profile; reapply retains setter effects, while changed_only skips unchanged values.
- Handler: `apply_personal_defaults_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Validate and apply the saved personal profile; reapply retains setter effects, while changed_only skips unchanged values.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "reapply", "enum": ["reapply", "changed_only"], "name": "mode", "required": false, "type": "string"}`

- Result protocol: `aurora_default_profile_result_v1`
- Receipt field: `default_profile_results`
- Verification: Runtime profile state or saved file bytes; not provider, overlay, native-effect or cross-process CAS proof.
- Failure policy: Stop the batch tail. Prevalidate before writes; attempt and verify restoration after partial apply. Never replay automatically.

### APPLY_SETTINGS_TRANSACTION

- Signature: `APPLY_SETTINGS_TRANSACTION(token)` (reviewed_contract)
- Summary: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.
- Handler: `apply_settings_transaction_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"format": "url_safe_base64_json", "name": "token", "operation": "apply", "request_schema": "aurora_settings_transaction_request_v1", "required": true, "type": "string"}`

- Result protocol: `aurora_settings_transaction_receipt_v1`
- Receipt field: `settings_transaction_receipts`
- Verification: Observed registered runtime settings; failed_uncertain means an unexpected service failure prevents a definitive completion claim.
- Failure policy: Stop the remaining batch on any rejected or failed transaction. No automatic replay. Apply attempts restoration on failure; restoration is separately verified.

### APPLY_SYSTEM_DEFAULTS

- Signature: `APPLY_SYSTEM_DEFAULTS([mode])` (reviewed_contract)
- Summary: Validate and apply the process-start system profile; reapply retains setter effects, while changed_only skips unchanged values.
- Handler: `apply_system_defaults_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Validate and apply the process-start system profile; reapply retains setter effects, while changed_only skips unchanged values.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "reapply", "enum": ["reapply", "changed_only"], "name": "mode", "required": false, "type": "string"}`

- Result protocol: `aurora_default_profile_result_v1`
- Receipt field: `default_profile_results`
- Verification: Runtime profile state or saved file bytes; not provider, overlay, native-effect or cross-process CAS proof.
- Failure policy: Stop the batch tail. Prevalidate before writes; attempt and verify restoration after partial apply. Never replay automatically.

### APPROVE_AGENT_SUGGESTION

- Signature: `APPROVE_AGENT_SUGGESTION(suggestion_id|latest|agent_id, note=...)` (help_text)
- Summary: Mark a policy-allowed suggestion approved for review only.
- Handler: `approve_agent_suggestion_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### APPROVE_PENDING

- Signature: `APPROVE_PENDING([selectors..., version:hash])` (reviewed_contract)
- Summary: Submit the selected held commands once; preserve unstarted or uncertain items for inspection.
- Handler: `approve_pending_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "selectors", "required": false, "type": "string", "variadic": true}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### APPROVE_PROMPT_PIN

- Signature: `APPROVE_PROMPT_PIN(mark_id|target, note=...)` (help_text)
- Summary: Approve a Prompt Pin mark as metadata; model-visible inclusion remains off until a later explicit slice.
- Handler: `approve_prompt_pin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ARM_CHEAP_LIVE_VISUAL_HARNESS

- Signature: `ARM_CHEAP_LIVE_VISUAL_HARNESS(optional_model)` (help_text)
- Summary: Arm a one-turn cheap live visual probe while keeping live mode off; default is gpt-5.4-mini unless nano/mini/model is supplied.
- Handler: `arm_cheap_live_visual_harness_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ARM_CHEAP_RESPONSES_SHADOW_PROBE

- Signature: `ARM_CHEAP_RESPONSES_SHADOW_PROBE(optional_model)` (help_text)
- Summary: Arm a cheap Responses live-probe scaffold while keeping send/API/default migration disabled; default is gpt-5.4-mini unless nano/mini/model is supplied.
- Handler: `arm_cheap_responses_shadow_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ARM_LIVE_VISUAL_HARNESS_PROBE

- Signature: `ARM_LIVE_VISUAL_HARNESS_PROBE(optional_model)` (help_text)
- Summary: Arm a one-turn live visual probe while keeping live mode off; tier is inferred from the selected model.
- Handler: `arm_live_visual_harness_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ARM_RESPONSES_SHADOW_PROBE

- Signature: `ARM_RESPONSES_SHADOW_PROBE(optional_model)` (help_text)
- Summary: Arm a Responses live-probe scaffold for a chosen model, metadata-only and no-send.
- Handler: `arm_responses_shadow_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ARM_STRONG_LIVE_VISUAL_HARNESS

- Signature: `ARM_STRONG_LIVE_VISUAL_HARNESS(optional_model)` (help_text)
- Summary: Arm a one-turn stronger-model visual comparison while keeping live mode off; default is gpt-5.4.
- Handler: `arm_strong_live_visual_harness_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ASSIGN_AGENT_TASK

- Signature: `ASSIGN_AGENT_TASK(agent_id, title=..., objective=..., expected=..., context=..., priority=0-100, visibility=parent_visible|private, tags=...)` (help_text)
- Summary: Record a metadata-only sub-agent work brief without spawning workers, writing parent history, inserting Pending Commands, or changing model context.
- Handler: `assign_agent_task_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### AUTHORIZE_OPERATOR

- Signature: `AUTHORIZE_OPERATOR(passcode)` (help_text)
- Summary: Temporarily unlock privileged external operator commands for the configured TTL.
- Handler: `authorize_operator_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### BACKFILL_IMAGE_CONTEXT_INDEX

- Signature: `BACKFILL_IMAGE_CONTEXT_INDEX(optional_limit)` (help_text)
- Summary: Create missing metadata sidecars for a bounded newest-first set of existing screenshots without renaming files.
- Handler: `backfill_image_context_index_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### BUILD_RESPONSES_SHADOW_OFFLINE_POSTURE

- Signature: `BUILD_RESPONSES_SHADOW_OFFLINE_POSTURE()` (help_text)
- Summary: Build and log the offline token/cost/state posture without calling the Responses API.
- Handler: `build_responses_shadow_offline_posture_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### BUILD_RESPONSES_SHADOW_PAYLOAD_PREVIEW

- Signature: `BUILD_RESPONSES_SHADOW_PAYLOAD_PREVIEW()` (help_text)
- Summary: Build and log the no-send Responses payload preview without calling the Responses API.
- Handler: `build_responses_shadow_payload_preview_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CANCEL_ACTIVE_WORK

- Signature: `CANCEL_ACTIVE_WORK()` (reviewed_contract)
- Summary: Cancel model and command work and release Aurora-owned inputs. Live stays unchanged; remote model work may still drain.
- Handler: `cancel_active_work_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Cancel model and command work and release Aurora-owned inputs. Live stays unchanged; remote model work may still drain.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_input_cleanup_v1`
- Receipt field: `input_cleanup_results`
- Verification: Backend submission only; no proof of application behavior or ownership of physically held human inputs.
- Failure policy: Stop the remaining batch on failure. Failed releases stay tracked for explicit retry; an in-flight native call may defer cleanup to its owner.

### CHECK_PREVIOUS_HANDOFF

- Signature: `CHECK_PREVIOUS_HANDOFF()` (help_text)
- Summary: Load yesterday's handoff file into pinned handoff context if it exists.
- Handler: `check_previous_handoff_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR

- Signature: `CLEAR()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_all_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR%

- Signature: `CLEAR%(percentage)` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_percentage_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"maximum": 100, "minimum": 0, "name": "percentage", "required": true, "type": "number"}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_CONTEXT_MARK

- Signature: `CLEAR_CONTEXT_MARK(mark_id|target|all, optional mark_type=...)` (help_text)
- Summary: Append a clear event for writable context marks without deleting audit history.
- Handler: `clear_context_mark_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR_DO_NOT_INCLUDE

- Signature: `CLEAR_DO_NOT_INCLUDE(mark_id|target|all)` (help_text)
- Summary: Clear active do-not-include/drop metadata without erasing the audit log.
- Handler: `clear_do_not_include_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR_HANDOFF

- Signature: `CLEAR_HANDOFF()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_handoff_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_INIT

- Signature: `CLEAR_INIT()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_init_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_NEXT_INFERENCE

- Signature: `CLEAR_NEXT_INFERENCE()` (reviewed_contract)
- Summary: Clear the queued one-turn override, retaining normal session policy. Works while setting locks are enabled.
- Handler: `clear_next_inference_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Clear the queued one-turn override, retaining normal session policy. Works while setting locks are enabled.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_inference_plan_result_v1`
- Receipt field: `inference_plan_results`
- Verification: Detached before/after queued plans and content fingerprints. A queued plan is not proof of provider acceptance; model compatibility normalization still applies.
- Failure policy: Reject malformed batches before effects. Stop the batch tail on execution failure; do not replay uncertain outcomes.

### CLEAR_NONPIN

- Signature: `CLEAR_NONPIN()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_nonpin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_NOPIN%

- Signature: `CLEAR_NOPIN%(percentage[, random|oldest|newest])` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_nopin_percentage_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"maximum": 100, "minimum": 0, "name": "percentage", "required": true, "type": "number"}`
- Parameter: `{"default": "random", "enum": ["random", "oldest", "newest"], "name": "selection", "required": false, "type": "string"}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_OPERATOR_PASSCODE

- Signature: `CLEAR_OPERATOR_PASSCODE()` (help_text)
- Summary: Clear the configured external-operator passcode.
- Handler: `clear_operator_passcode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR_PENDING

- Signature: `CLEAR_PENDING([selectors..., version:hash])` (reviewed_contract)
- Summary: Drop matching held/uncertain items without execution; an empty match changes nothing.
- Handler: `clear_pending_commands_command`
- Binding: runtime
- Aliases: CLEAR_PENDING_COMMANDS
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "selectors", "required": false, "type": "string", "variadic": true}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### CLEAR_PENDING_COMMANDS

- Signature: `CLEAR_PENDING_COMMANDS([selectors..., version:hash])` (reviewed_contract)
- Summary: Drop matching held/uncertain items without execution; an empty match changes nothing.
- Handler: `clear_pending_commands_command`
- Binding: runtime
- Aliases: CLEAR_PENDING
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "selectors", "required": false, "type": "string", "variadic": true}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### CLEAR_PIN

- Signature: `CLEAR_PIN()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `clear_pin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### CLEAR_RECENT_CONTEXT

- Signature: `CLEAR_RECENT_CONTEXT()` (help_text)
- Summary: Clear recent-context memory.
- Handler: `clear_recent_context_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR_RESPONSES_SHADOW_PROBE

- Signature: `CLEAR_RESPONSES_SHADOW_PROBE()` (help_text)
- Summary: Clear the Responses live-probe scaffold while keeping chat/completions as the fallback.
- Handler: `clear_responses_shadow_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLEAR_ROUTE_STATE

- Signature: `CLEAR_ROUTE_STATE()` (help_text)
- Summary: Clear route state, route intent, local path, blockers, and recent movement results.
- Handler: `clear_route_state_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### CLOSE_CHAT_HEAD

- Signature: `CLOSE_CHAT_HEAD()` (help_text)
- Summary: Ask the control panel to close the floating chat strip and its attached history pane.
- Handler: `close_chat_head_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### COMPLETE_GOAL

- Signature: `COMPLETE_GOAL(goal_id)` (reviewed_contract)
- Summary: Complete the exact recursive goal ID; a missing ID fails, repeated completion is unchanged.
- Handler: `complete_goal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: goals_list

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"minimum": 1, "name": "goal_id", "required": true, "type": "integer"}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### DELETE_MSG

- Signature: `DELETE_MSG(timestamp)` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `delete_msg_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "timestamp", "required": true, "type": "string"}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### DHISTORY

- Signature: `DHISTORY()` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `display_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### DRY_RUN_AGENT_PENDING_INSERT

- Signature: `DRY_RUN_AGENT_PENDING_INSERT(optional_filter)` (help_text)
- Summary: Log and display a no-exec dry-run proving which review links satisfy the future insertion contract while leaving the executable Pending queue unchanged.
- Handler: `run_agent_pending_insert_dry_run_command`
- Binding: runtime
- Aliases: RUN_AGENT_PENDING_INSERT_DRY_RUN
- Parameter validation: legacy_handler
- Effects: not_reviewed

### EDIT_MSGS

- Signature: `EDIT_MSGS(timestamp, text[, timestamp, text...])` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `edit_msgs_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "timestamp_text_pairs", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### FIND_REFERENCE

- Signature: `FIND_REFERENCE(query, optional_pack_name|all)` (help_text)
- Summary: Alias for REF(...) when a more explicit command name reads better.
- Handler: `reference_shorthand_command`
- Binding: runtime
- Aliases: REF
- Parameter validation: legacy_handler
- Effects: not_reviewed

### GB_MODE

- Signature: `GB_MODE()` (reviewed_contract)
- Summary: Set runtime.action to gb. Uses the same runtime setting lock and observed readback.
- Handler: `gb_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Set runtime.action to gb. Uses the same runtime setting lock and observed readback.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Registered setting: `runtime.action`
- Runtime lock: action
- Apply timing: immediate_action_dispatch
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### HELP

- Signature: `HELP` (help_text)
- Summary: Display this help message.
- Handler: `help_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### HIDE_AI_COMMANDS

- Signature: `HIDE_AI_COMMANDS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `hide_ai_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### HIDE_AI_TEXT

- Signature: `HIDE_AI_TEXT(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `hide_ai_text_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### HIDE_USER_COMMANDS

- Signature: `HIDE_USER_COMMANDS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `hide_user_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### HIDE_USER_TEXT

- Signature: `HIDE_USER_TEXT(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `hide_user_text_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### INIT

- Signature: `INIT(text...)` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `init_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### INSERT_AGENT_PENDING_COMMAND

- Signature: `INSERT_AGENT_PENDING_COMMAND(review_link_or_dry_run_id, confirm=dry_run:<id>, note=...)` (help_text)
- Summary: Insert a contract-ready sub-agent suggestion into the held Pending queue only after exact dry-run confirmation; it still requires APPROVE_PENDING before execution.
- Handler: `insert_agent_pending_command_command`
- Binding: runtime
- Aliases: INSERT_AGENT_PENDING_FROM_DRY_RUN
- Parameter validation: legacy_handler
- Effects: not_reviewed

### INSERT_AGENT_PENDING_FROM_DRY_RUN

- Signature: `INSERT_AGENT_PENDING_FROM_DRY_RUN(review_link_or_dry_run_id, confirm=dry_run:<id>, note=...)` (help_text)
- Summary: Insert a contract-ready sub-agent suggestion into the held Pending queue only after exact dry-run confirmation; it still requires APPROVE_PENDING before execution.
- Handler: `insert_agent_pending_command_command`
- Binding: runtime
- Aliases: INSERT_AGENT_PENDING_COMMAND
- Parameter validation: legacy_handler
- Effects: not_reviewed

### INSERT_PENDING

- Signature: `INSERT_PENDING(command)` (reviewed_contract)
- Summary: Hold a validated command/batch using the chosen normal, insert or replace mode.
- Handler: `insert_pending_command_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "command", "required": true, "type": "string"}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### LAUNCH_CONTROL_PANEL

- Signature: `LAUNCH_CONTROL_PANEL()` (help_text)
- Summary: Open the Aurora control panel window.
- Handler: `launch_control_panel_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LINK_AGENT_SUGGESTION_TASK

- Signature: `LINK_AGENT_SUGGESTION_TASK(task_id|latest|agent_id, suggestion=latest|suggestion_id|agent_id, note=...)` (help_text)
- Summary: Link a task packet to a suggestion as review provenance while keeping the Pending gate closed.
- Handler: `link_agent_task_suggestion_command`
- Binding: runtime
- Aliases: LINK_AGENT_TASK_SUGGESTION
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LINK_AGENT_TASK_SUGGESTION

- Signature: `LINK_AGENT_TASK_SUGGESTION(task_id|latest|agent_id, suggestion=latest|suggestion_id|agent_id, note=...)` (help_text)
- Summary: Link a task packet to a suggestion as review provenance while keeping the Pending gate closed.
- Handler: `link_agent_task_suggestion_command`
- Binding: runtime
- Aliases: LINK_AGENT_SUGGESTION_TASK
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LIST_COMMANDS

- Signature: `LIST_COMMANDS(low|medium|high)` (help_text)
- Summary: Display the mirrored Aurora command catalog at the requested verbosity.
- Handler: `list_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LIST_EPISODIC_SNAPSHOTS

- Signature: `LIST_EPISODIC_SNAPSHOTS([limit])` (reviewed_contract)
- Summary: Existing episodic snapshot write/list/lexical-search behavior with complete argument admission and correlated receipts; no inferred persistence or rollback guarantee.
- Handler: `list_episodic_snapshots_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: snapshot_read

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"coercion": "finite values truncate/clamp to 1–24", "default_source": "runtime configured list limit", "name": "limit", "required": false, "type": "number"}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### LOAD_TASKS

- Signature: `LOAD_TASKS([path])` (reviewed_contract)
- Summary: Save a validated recursive task snapshot atomically, or validate and restore a complete snapshot. Does not undo live actions.
- Handler: `load_tasks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Save a validated recursive task snapshot atomically, or validate and restore a complete snapshot. Does not undo live actions.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "pinned_tasks.json", "name": "path", "required": false, "type": "string"}`

- Result protocol: `aurora_goal_file_result_v1`
- Receipt field: `goal_file_results`

### LOCK_OPERATOR_ACCESS

- Signature: `LOCK_OPERATOR_ACCESS()` (help_text)
- Summary: Clear the current external-operator authorization immediately.
- Handler: `lock_operator_access_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LOCK_SETTING

- Signature: `LOCK_SETTING([lock])` (reviewed_contract)
- Summary: Read locks when omitted; otherwise enable or disable the named runtime setting lock. Settings values are unchanged.
- Handler: `lock_setting_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read locks when omitted; otherwise enable or disable the named runtime setting lock. Settings values are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"action": "action", "auth": "auth", "chat-log-echo": "chat_log_echo", "chat_log_echo": "chat_log_echo", "chatlog": "chat_log_echo", "cursor-label": "overlay", "cursor_label": "overlay", "display": "overlay", "echo": "chat_log_echo", "execution": "execution", "init": "live_init", "interval": "screenshot_interval", "keypoint-grid": "overlay", "keypoint_grid": "overlay", "live": "live", "live-init": "live_init", "live_init": "live_init", "model": "models", "models": "models", "overlay": "overlay", "overlays": "overlay", "reasoning": "reasoning", "screenshot-interval": "screenshot_interval", "screenshot_interval": "screenshot_interval", "sound": "sound", "status-overlay": "overlay", "status_overlay": "overlay", "temp": "temperature", "temperature": "temperature", "thinking": "reasoning", "tile-grid": "overlay", "tile_grid": "overlay", "time-logging": "time_logging", "time_logging": "time_logging", "timing": "time_logging", "visuals": "overlay"}, "enum": ["auth", "live", "execution", "action", "models", "reasoning", "temperature", "screenshot_interval", "overlay", "live_init", "sound", "time_logging", "chat_log_echo"], "name": "lock", "omitted": "read_current_locks", "required": false, "type": "string"}`

- Result protocol: `aurora_lock_command_result_v1`
- Receipt field: `lock_results`
- Verification: Runtime lock readback under the settings transaction lock; not an access-control boundary.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback.

### LOGIN_CODEX_OAUTH

- Signature: `LOGIN_CODEX_OAUTH()` (help_text)
- Summary: Open the ChatGPT/Codex OAuth sign-in helper in a new window.
- Handler: `login_codex_oauth_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### LOOKUP_COMMAND

- Signature: `LOOKUP_COMMAND(command_name, low|medium|high)` (help_text)
- Summary: Look up one command from the mirrored Aurora command catalog.
- Handler: `lookup_command_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_AGENT_SUGGESTION

- Signature: `MARK_AGENT_SUGGESTION(suggestion_id|latest|agent_id, mark_type=operator_pin|search_pin|importance_score, note=...)` (help_text)
- Summary: Link a staged suggestion to a Context Mark provenance row without prompt inclusion or execution.
- Handler: `mark_agent_suggestion_provenance_command`
- Binding: runtime
- Aliases: MARK_AGENT_SUGGESTION_PROVENANCE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_AGENT_SUGGESTION_PROVENANCE

- Signature: `MARK_AGENT_SUGGESTION_PROVENANCE(suggestion_id|latest|agent_id, mark_type=operator_pin|search_pin|importance_score, note=...)` (help_text)
- Summary: Link a staged suggestion to a Context Mark provenance row without prompt inclusion or execution.
- Handler: `mark_agent_suggestion_provenance_command`
- Binding: runtime
- Aliases: MARK_AGENT_SUGGESTION
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_CONTEXT

- Signature: `MARK_CONTEXT(target, mark_type=..., value=..., note=..., approval=draft|requested|approved|rejected)` (help_text)
- Summary: Record a metadata-only context mark; it stays visible in Prompt Ledger but does not become model-visible.
- Handler: `mark_context_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_DO_NOT_INCLUDE

- Signature: `MARK_DO_NOT_INCLUDE(target, note=...)` (help_text)
- Summary: Convenience command to record a metadata-only do-not-include/drop mark while preserving local evidence.
- Handler: `mark_do_not_include_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_REPLY

- Signature: `MARK_REPLY(target, mark_type=..., value=..., note=..., approval=...)` (help_text)
- Summary: Record a metadata-only mark for a reply target.
- Handler: `mark_reply_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MARK_TURN

- Signature: `MARK_TURN(target, mark_type=..., value=..., note=..., approval=...)` (help_text)
- Summary: Record a metadata-only mark for a turn target.
- Handler: `mark_turn_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### MEM

- Signature: `MEM(query, [k,] options...)` (reviewed_contract)
- Summary: Validate the complete query before batch execution, then recheck with runtime defaults. argument_policy=legacy preserves old clamps/fallbacks; strict rejects invalid legacy numeric/enum fields. Hard filters, option names, Boolean/date syntax and new options always validate. May call embeddings and update cache/feedback/results; no automatic memory promotion.
- Handler: `memory_retrieval_shorthand_command`
- Binding: runtime
- Aliases: RECALL
- Parameter validation: pre_dispatch
- Effects: query_provider_cache_and_result_state

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "query_or_named_options", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### MOD_AGENT

- Signature: `MOD_AGENT(agent_id, role=..., rank=..., urgency=..., allow=..., deny=..., history=..., status=active|paused|silenced|retired)` (help_text)
- Summary: Modify registry metadata only.
- Handler: `mod_agent_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### NO_ACTION_MODE

- Signature: `NO_ACTION_MODE()` (reviewed_contract)
- Summary: Set runtime.action to none. Uses the same runtime setting lock and observed readback.
- Handler: `no_action_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Set runtime.action to none. Uses the same runtime setting lock and observed readback.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Registered setting: `runtime.action`
- Runtime lock: action
- Apply timing: immediate_action_dispatch
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### OPEN_CHAT_HEAD

- Signature: `OPEN_CHAT_HEAD()` (help_text)
- Summary: Ask the control panel to open the floating always-on-top chat strip.
- Handler: `open_chat_head_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### OVERRIDE_PENDING

- Signature: `OVERRIDE_PENDING(command)` (reviewed_contract)
- Summary: Hold a validated command/batch using the chosen normal, insert or replace mode.
- Handler: `replace_pending_command_command`
- Binding: runtime
- Aliases: REPLACE_PENDING
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "command", "required": true, "type": "string"}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### PIN

- Signature: `PIN(text...)` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `pin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### PREVIEW_SETTINGS_TRANSACTION

- Signature: `PREVIEW_SETTINGS_TRANSACTION(token)` (reviewed_contract)
- Summary: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.
- Handler: `preview_settings_transaction_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"format": "url_safe_base64_json", "name": "token", "operation": "preview", "request_schema": "aurora_settings_transaction_request_v1", "required": true, "type": "string"}`

- Result protocol: `aurora_settings_transaction_receipt_v1`
- Receipt field: `settings_transaction_receipts`
- Verification: Observed registered runtime settings; failed_uncertain means an unexpected service failure prevents a definitive completion claim.
- Failure policy: Stop the remaining batch on any rejected or failed transaction. No automatic replay. Apply attempts restoration on failure; restoration is separately verified.

### PROMOTE_EPISODIC_MEMORY

- Signature: `PROMOTE_EPISODIC_MEMORY(index, target[, prefix, result_handle])` (reviewed_contract)
- Summary: Copy a legacy preview item, or exact full retained summary when a handle is supplied, into live memory; no state rewind.
- Handler: `promote_episodic_memory_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: working_memory_mutation

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"maximum": 24, "minimum": 1, "name": "item_index", "required": true, "type": "integer"}`
- Parameter: `{"choices": ["note", "notes", "journal", "context", "recent_context", "recent", "pinned_immediate", "immediate", "pinned_short_term", "short_term", "short", "goal", "apriority_goal", "open_goal", "overarching_goal", "mission"], "name": "target", "required": true, "type": "string"}`
- Parameter: `{"default": "", "name": "prefix", "type": "string"}`
- Parameter: `{"name": "result_handle", "required": false, "type": "string"}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### pyag:click

- Signature: `pyag:click(x=None, y=None, button='left')` (reviewed_contract)
- Summary: Click at optional coordinates; omitted or null coordinates use the current position.
- Handler: `pyautogui_click`
- Binding: desktop
- Aliases: pyag:leftclick
- Parameter validation: pre_dispatch
- Effects: Sends one mouse click.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": null, "name": "x", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": null, "name": "y", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": "left", "enum": ["left", "middle", "right", "primary", "secondary"], "name": "button", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:doubleclick

- Signature: `pyag:doubleclick(x=None, y=None, button='left')` (reviewed_contract)
- Summary: Double-click at optional coordinates using the selected mouse button.
- Handler: `pyautogui_double_click`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Sends two mouse clicks.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": null, "name": "x", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": null, "name": "y", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": "left", "enum": ["left", "middle", "right", "primary", "secondary"], "name": "button", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:drag

- Signature: `pyag:drag(x, y, duration=0.0, button='left')` (reviewed_contract)
- Summary: Drag to desktop coordinates with the selected mouse button.
- Handler: `pyautogui_drag`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Moves the pointer while holding a mouse button.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"name": "x", "required": true, "type": "integer"}`
- Parameter: `{"name": "y", "required": true, "type": "integer"}`
- Parameter: `{"default": 0.0, "finite": true, "minimum": 0, "name": "duration", "required": false, "type": "number"}`
- Parameter: `{"default": "left", "enum": ["left", "middle", "right", "primary", "secondary"], "name": "button", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:focus_window

- Signature: `pyag:focus_window(title=None)` (reviewed_contract)
- Summary: Focus a matching window, or the configured emulator title when omitted; failure blocks later batch actions.
- Handler: `pyautogui_focus_window`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: May restore/foreground a window; reports whether target focus was confirmed.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": null, "name": "title", "nonempty": true, "nullable": true, "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:hold

- Signature: `pyag:hold(key, duration=None)` (reviewed_contract)
- Summary: Hold a key; omit duration for an indefinite hold requiring an explicit release.
- Handler: `pyautogui_hold`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Holds a key; timed holds release on completion or cancellation. Game input requires confirmed focus.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "keyboard_key", "name": "key", "nonempty": true, "required": true, "type": "string"}`
- Parameter: `{"default": null, "finite": true, "minimum": 0, "name": "duration", "nullable": true, "required": false, "type": "number"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:hold_click

- Signature: `pyag:hold_click(x=None, y=None, duration=0.0, button='left')` (reviewed_contract)
- Summary: Hold a mouse button for a finite duration, releasing on completion or cancellation.
- Handler: `pyautogui_hold_click`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Moves to optional coordinates and holds a mouse button for the requested duration.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": null, "name": "x", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": null, "name": "y", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": 0.0, "finite": true, "minimum": 0, "name": "duration", "required": false, "type": "number"}`
- Parameter: `{"default": "left", "enum": ["left", "middle", "right", "primary", "secondary"], "name": "button", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:hotkey

- Signature: `pyag:hotkey(keys...)` (reviewed_contract)
- Summary: Press a complete chord; every key must be valid before any key is sent.
- Handler: `pyautogui_hotkey`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Presses the chord keys in order and releases them in reverse order.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "desktop_keyboard_key", "name": "keys", "nonempty": true, "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:leftclick

- Signature: `pyag:leftclick(x=None, y=None, button='left')` (reviewed_contract)
- Summary: Click at optional coordinates; omitted or null coordinates use the current position.
- Handler: `pyautogui_click`
- Binding: desktop
- Aliases: pyag:click
- Parameter validation: pre_dispatch
- Effects: Sends one mouse click.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": null, "name": "x", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": null, "name": "y", "nullable": true, "required": false, "type": "integer"}`
- Parameter: `{"default": "left", "enum": ["left", "middle", "right", "primary", "secondary"], "name": "button", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:move

- Signature: `pyag:move(x, y, duration=0.0)` (reviewed_contract)
- Summary: Move the pointer to desktop coordinates; negative coordinates support other monitors.
- Handler: `pyautogui_move`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Moves the pointer.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"name": "x", "required": true, "type": "integer"}`
- Parameter: `{"name": "y", "required": true, "type": "integer"}`
- Parameter: `{"default": 0.0, "finite": true, "minimum": 0, "name": "duration", "required": false, "type": "number"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:move_key

- Signature: `pyag:move_key(key, tiles)` (reviewed_contract)
- Summary: Hold a game direction using the existing tile-duration calibration; game-specific accuracy is not guaranteed.
- Handler: `move_key_command`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Waits 1.35 seconds, then performs a timed key hold; requires confirmed game focus when using that backend.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "keyboard_key", "name": "key", "nonempty": true, "required": true, "type": "string"}`
- Parameter: `{"minimum": 1, "name": "tiles", "required": true, "type": "integer"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:multi_hold

- Signature: `pyag:multi_hold(keys...)` (reviewed_contract)
- Summary: Hold all listed keys until explicitly released.
- Handler: `pyautogui_multi_hold`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Holds desktop keys; an interrupted setup attempts to release keys already held.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "desktop_keyboard_key", "name": "keys", "nonempty": true, "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:multi_press

- Signature: `pyag:multi_press(keys...)` (reviewed_contract)
- Summary: Press every listed key in order; invalid keys reject the whole request.
- Handler: `pyautogui_multi_press`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Sends a sequence of desktop key presses.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "desktop_keyboard_key", "name": "keys", "nonempty": true, "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:multi_release

- Signature: `pyag:multi_release(keys...)` (reviewed_contract)
- Summary: Release every listed desktop key.
- Handler: `pyautogui_multi_release`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Attempts every requested key release even if one release reports an error.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "desktop_keyboard_key", "name": "keys", "nonempty": true, "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:press

- Signature: `pyag:press(key, presses=1, interval=0.0)` (reviewed_contract)
- Summary: Press one key a positive integer number of times, with an optional interval.
- Handler: `pyautogui_press`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: PYAG sends literal desktop keys. GB translates game controls through the admitted game backend and requires confirmed focus.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "keyboard_key", "name": "key", "nonempty": true, "required": true, "type": "string"}`
- Parameter: `{"default": 1, "minimum": 1, "name": "presses", "required": false, "type": "integer"}`
- Parameter: `{"default": 0.0, "finite": true, "minimum": 0, "name": "interval", "required": false, "type": "number"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:release

- Signature: `pyag:release(key, routing='owned')` (reviewed_contract)
- Summary: Release a key using its owned route; optional current explicitly uses the current mapping.
- Handler: `pyautogui_release`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Uses the original hold backend/key, without changing focus. Repeated owned release is a no-op. Untracked keys retain legacy current-route key-up; current explicitly bypasses ownership lookup and does not clear another owned route.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"format": "keyboard_key", "name": "key", "nonempty": true, "required": true, "type": "string"}`
- Parameter: `{"default": "owned", "enum": ["owned", "current"], "name": "routing", "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:screenshot

- Signature: `pyag:screenshot(filename='screenshot.png')` (reviewed_contract)
- Summary: Save a desktop screenshot at the supplied path or screenshot.png.
- Handler: `pyautogui_screenshot`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Captures the desktop and writes an image file, potentially replacing an existing file.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": "screenshot.png", "name": "filename", "nonempty": true, "required": false, "type": "string"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:scroll_down

- Signature: `pyag:scroll_down(amount=1)` (reviewed_contract)
- Summary: Scroll downward by signed units; negative units reverse direction.
- Handler: `pyautogui_scroll_down`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Scrolls the current target.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": 1, "name": "amount", "required": false, "type": "integer"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:scroll_up

- Signature: `pyag:scroll_up(amount=1)` (reviewed_contract)
- Summary: Scroll upward by signed units; negative units reverse direction.
- Handler: `pyautogui_scroll_up`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Scrolls the current target.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"default": 1, "name": "amount", "required": false, "type": "integer"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### pyag:type

- Signature: `pyag:type(text, interval=0.0)` (reviewed_contract)
- Summary: Type text supported by the active PyAutoGUI character set, with an optional interval.
- Handler: `pyautogui_type`
- Binding: desktop
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Types into the focused target. Unsupported characters reject the entire request before typing.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Action routing: Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.

- Parameter: `{"name": "text", "required": true, "type": "string"}`
- Parameter: `{"default": 0.0, "finite": true, "minimum": 0, "name": "interval", "required": false, "type": "number"}`

- Result protocol: `aurora_desktop_result_v1`
- Receipt field: `desktop_results`
- Verification: submitted means API completion, not observed application behavior
- Failure policy: Stop the remaining batch; do not retry uncertain input automatically.

### PYAG_MODE

- Signature: `PYAG_MODE()` (reviewed_contract)
- Summary: Set runtime.action to pyag. Uses the same runtime setting lock and observed readback.
- Handler: `pyag_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Set runtime.action to pyag. Uses the same runtime setting lock and observed readback.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Registered setting: `runtime.action`
- Runtime lock: action
- Apply timing: immediate_action_dispatch
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### QUEUE_LIVE_VISUAL_HARNESS_PROBE_PROMPT

- Signature: `QUEUE_LIVE_VISUAL_HARNESS_PROBE_PROMPT()` (help_text)
- Summary: Queue the bounded probe prompt while live mode is off. Turning live on afterward can spend one visual model turn.
- Handler: `queue_live_visual_harness_probe_prompt_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### QUEUE_PENDING

- Signature: `QUEUE_PENDING(command)` (reviewed_contract)
- Summary: Hold a validated command/batch using the chosen normal, insert or replace mode.
- Handler: `queue_pending_command_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "command", "required": true, "type": "string"}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### RECALL

- Signature: `RECALL(query, [k,] options...)` (reviewed_contract)
- Summary: Validate the complete query before batch execution, then recheck with runtime defaults. argument_policy=legacy preserves old clamps/fallbacks; strict rejects invalid legacy numeric/enum fields. Hard filters, option names, Boolean/date syntax and new options always validate. May call embeddings and update cache/feedback/results; no automatic memory promotion.
- Handler: `memory_retrieval_shorthand_command`
- Binding: runtime
- Aliases: MEM
- Parameter validation: pre_dispatch
- Effects: query_provider_cache_and_result_state

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "query_or_named_options", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### RECALL_PREVIOUS_SUMMARY

- Signature: `RECALL_PREVIOUS_SUMMARY(optional_character_name)` (help_text)
- Summary: Display yesterday's handoff summary and the init profile for review.
- Handler: `recall_previous_summary_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RECORD_LIVE_VISUAL_HARNESS_PROBE_RESULT

- Signature: `RECORD_LIVE_VISUAL_HARNESS_PROBE_RESULT()` (help_text)
- Summary: Record the latest post-arm model-turn diagnostics against the live visual probe contract.
- Handler: `record_live_visual_harness_probe_result_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REF

- Signature: `REF(query_or_pack, optional_pack_name|all)` (help_text)
- Summary: Shorthand reference lookup; exact pack names expand to SHOW_REFERENCE_PACK(...), otherwise SEARCH_REFERENCE_PACK(...).
- Handler: `reference_shorthand_command`
- Binding: runtime
- Aliases: FIND_REFERENCE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REHEARSE_LIVE_VISUAL_HARNESS

- Signature: `REHEARSE_LIVE_VISUAL_HARNESS()` (help_text)
- Summary: Run the Window 11 offline harness rehearsal without model calls or desktop/game actions; records checks for live/action/next-turn/image/count/setup posture.
- Handler: `run_live_visual_harness_rehearsal_command`
- Binding: runtime
- Aliases: RUN_LIVE_VISUAL_HARNESS_REHEARSAL
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REJECT_AGENT_SUGGESTION

- Signature: `REJECT_AGENT_SUGGESTION(suggestion_id|latest|agent_id, note=...)` (help_text)
- Summary: Mark a suggestion rejected for review only.
- Handler: `reject_agent_suggestion_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REJECT_PROMPT_PIN

- Signature: `REJECT_PROMPT_PIN(mark_id|target, note=...)` (help_text)
- Summary: Reject a Prompt Pin mark as metadata.
- Handler: `reject_prompt_pin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RELEASE_HELD_INPUTS

- Signature: `RELEASE_HELD_INPUTS()` (reviewed_contract)
- Summary: Cancel active/queued command batches and release Aurora-owned inputs. Model work and Live stay unchanged.
- Handler: `release_held_inputs_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Cancel active/queued command batches and release Aurora-owned inputs. Model work and Live stay unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_input_cleanup_v1`
- Receipt field: `input_cleanup_results`
- Verification: Backend submission only; no proof of application behavior or ownership of physically held human inputs.
- Failure policy: Stop the remaining batch on failure. Failed releases stay tracked for explicit retry; an in-flight native call may defer cleanup to its owner.

### REMOVE_MODEL

- Signature: `REMOVE_MODEL(name)` (help_text)
- Summary: Remove a custom model from the Aurora catalog.
- Handler: `remove_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REPLACE_PENDING

- Signature: `REPLACE_PENDING(command)` (reviewed_contract)
- Summary: Hold a validated command/batch using the chosen normal, insert or replace mode.
- Handler: `replace_pending_command_command`
- Binding: runtime
- Aliases: OVERRIDE_PENDING
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "command", "required": true, "type": "string"}`

- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### REQUEST_DEMAND_CAPTURE

- Signature: `REQUEST_DEMAND_CAPTURE(optional_reason, optional_settle_seconds)` (help_text)
- Summary: Request a one-off screenshot capture without changing the normal timer heartbeat or reordering pending commands.
- Handler: `request_screenshot_capture_command`
- Binding: runtime
- Aliases: REQUEST_SCREENSHOT_CAPTURE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REQUEST_PROMPT_PIN

- Signature: `REQUEST_PROMPT_PIN(target, note=...)` (help_text)
- Summary: Convenience command to request a metadata-only Prompt Pin.
- Handler: `request_prompt_pin_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### REQUEST_SCREENSHOT_CAPTURE

- Signature: `REQUEST_SCREENSHOT_CAPTURE(optional_reason, optional_settle_seconds)` (help_text)
- Summary: Request a one-off screenshot capture without changing the normal timer heartbeat or reordering pending commands.
- Handler: `request_screenshot_capture_command`
- Binding: runtime
- Aliases: REQUEST_DEMAND_CAPTURE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RESET_RESPONSES_SESSION

- Signature: `RESET_RESPONSES_SESSION()` (help_text)
- Summary: Explicitly start a fresh Responses chain after inspecting status; clears local continuation identity, never replays a failed request.
- Handler: `reset_responses_session_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Clear local provider continuation identity between requests under the reasoning lock; no API request, no remote-history deletion, no automatic replay.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `boolean_handler_result`
- Verification: Inspect model_status.responses_reasoning for generation and reset reason.
- Failure policy: Stop batch tail on failure; reject active/draining model I/O.

### RETRIEVAL_PULL

- Signature: `RETRIEVAL_PULL(query_or_filters, options...)` (reviewed_contract)
- Summary: Validate the complete query before batch execution, then recheck with runtime defaults. argument_policy=legacy preserves old clamps/fallbacks; strict rejects invalid legacy numeric/enum fields. Hard filters, option names, Boolean/date syntax and new options always validate. May call embeddings and update cache/feedback/results; no automatic memory promotion.
- Handler: `retrieval_pull_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: query_provider_cache_and_result_state

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "query_or_named_options", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### RETRIEVE_HANDOFF

- Signature: `RETRIEVE_HANDOFF(optional_filename)` (help_text)
- Summary: Load a handoff file into pinned handoff context. Defaults to yesterday if no file is provided.
- Handler: `retrieve_handoff_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### ROLLBACK_SETTINGS_TRANSACTION

- Signature: `ROLLBACK_SETTINGS_TRANSACTION(token)` (reviewed_contract)
- Summary: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.
- Handler: `rollback_settings_transaction_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"format": "url_safe_base64_json", "name": "token", "operation": "rollback", "request_schema": "aurora_settings_transaction_request_v1", "required": true, "type": "string"}`

- Result protocol: `aurora_settings_transaction_receipt_v1`
- Receipt field: `settings_transaction_receipts`
- Verification: Observed registered runtime settings; failed_uncertain means an unexpected service failure prevents a definitive completion claim.
- Failure policy: Stop the remaining batch on any rejected or failed transaction. No automatic replay. Apply attempts restoration on failure; restoration is separately verified.

### RUN_AGENT_HELPER_CLOSURE_CHECK

- Signature: `RUN_AGENT_HELPER_CLOSURE_CHECK()` (help_text)
- Summary: Build and log the Window 20 metadata-first sub-agent helper closure/readiness checklist.
- Handler: `run_agent_helper_closure_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_AGENT_PENDING_INSERT_DRY_RUN

- Signature: `RUN_AGENT_PENDING_INSERT_DRY_RUN(optional_filter)` (help_text)
- Summary: Log and display a no-exec dry-run proving which review links satisfy the future insertion contract while leaving the executable Pending queue unchanged.
- Handler: `run_agent_pending_insert_dry_run_command`
- Binding: runtime
- Aliases: DRY_RUN_AGENT_PENDING_INSERT
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_COMPANION_CONTRACT_CLOSURE_CHECK

- Signature: `RUN_COMPANION_CONTRACT_CLOSURE_CHECK()` (help_text)
- Summary: Build and log the Window 21 companion contract closure/readiness checklist.
- Handler: `run_companion_contract_closure_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_LIVE_VISUAL_HARNESS_REHEARSAL

- Signature: `RUN_LIVE_VISUAL_HARNESS_REHEARSAL()` (help_text)
- Summary: Run the Window 11 offline harness rehearsal without model calls or desktop/game actions; records checks for live/action/next-turn/image/count/setup posture.
- Handler: `run_live_visual_harness_rehearsal_command`
- Binding: runtime
- Aliases: REHEARSE_LIVE_VISUAL_HARNESS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_PROMPT_INCLUSION_CLOSURE_CHECK

- Signature: `RUN_PROMPT_INCLUSION_CLOSURE_CHECK()` (help_text)
- Summary: Build and log the Window 19 Prompt Inclusion closure/readiness checklist after activation proof.
- Handler: `run_prompt_inclusion_closure_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_PROMPT_INCLUSION_PREVIEW_REHEARSAL

- Signature: `RUN_PROMPT_INCLUSION_PREVIEW_REHEARSAL()` (help_text)
- Summary: Create temporary approved Prompt Pin/drop metadata, build the no-send preview, clear the temporary marks, and report non-empty diff/rollback proof without changing prompt packing.
- Handler: `run_prompt_inclusion_preview_rehearsal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### RUN_RESPONSES_SHADOW_CLOSURE_CHECK

- Signature: `RUN_RESPONSES_SHADOW_CLOSURE_CHECK()` (help_text)
- Summary: Build and log the closure/fallback readiness checklist without calling the Responses API.
- Handler: `run_responses_shadow_closure_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SAVECH

- Signature: `SAVECH([path_prefix])` (reviewed_contract)
- Summary: CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.
- Handler: `save_chat_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "chat_history", "name": "path_prefix", "required": false, "type": "string"}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled.
- Failure policy: Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.

### SAVE_ALL_PINS

- Signature: `SAVE_ALL_PINS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `save_all_pins_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SAVE_HANDOFF

- Signature: `SAVE_HANDOFF(optional_filename)` (help_text)
- Summary: Save a structured handoff snapshot to the logging folder or a provided path.
- Handler: `save_handoff_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SAVE_PERSONAL_DEFAULTS

- Signature: `SAVE_PERSONAL_DEFAULTS()` (reviewed_contract)
- Summary: Atomically save current profile settings, retaining unknown fields in a valid existing file.
- Handler: `save_personal_defaults_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Atomically save current profile settings, retaining unknown fields in a valid existing file.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_default_profile_result_v1`
- Receipt field: `default_profile_results`
- Verification: Runtime profile state or saved file bytes; not provider, overlay, native-effect or cross-process CAS proof.
- Failure policy: Stop the batch tail. Prevalidate before writes; attempt and verify restoration after partial apply. Never replay automatically.

### SAVE_PINS

- Signature: `SAVE_PINS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `save_pins_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SAVE_TASKS

- Signature: `SAVE_TASKS([path])` (reviewed_contract)
- Summary: Save a validated recursive task snapshot atomically, or validate and restore a complete snapshot. Does not undo live actions.
- Handler: `save_tasks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Save a validated recursive task snapshot atomically, or validate and restore a complete snapshot. Does not undo live actions.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "pinned_tasks.json", "name": "path", "required": false, "type": "string"}`

- Result protocol: `aurora_goal_file_result_v1`
- Receipt field: `goal_file_results`

### SEARCH_COMMANDS

- Signature: `SEARCH_COMMANDS(query, low|medium|high)` (help_text)
- Summary: Search the mirrored Aurora command catalog by topic, summary, handler, or signature text.
- Handler: `search_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SEARCH_EPISODIC_SNAPSHOTS

- Signature: `SEARCH_EPISODIC_SNAPSHOTS(query[, limit])` (reviewed_contract)
- Summary: Existing episodic snapshot write/list/lexical-search behavior with complete argument admission and correlated receipts; no inferred persistence or rollback guarantee.
- Handler: `search_episodic_snapshots_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: snapshot_read

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "query", "required": true, "type": "string"}`
- Parameter: `{"coercion": "finite values truncate/clamp to 1–24", "default_source": "runtime configured list limit", "name": "limit", "required": false, "type": "number"}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### SEARCH_IMAGE_CONTEXT_INDEX

- Signature: `SEARCH_IMAGE_CONTEXT_INDEX(query, optional_limit)` (help_text)
- Summary: Search image sidecars by caption, OCR text, tags, capture reason, image id, and path.
- Handler: `search_image_context_index_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SEARCH_PROGRAM_MAP

- Signature: `SEARCH_PROGRAM_MAP(query, runtime|ui)` (help_text)
- Summary: Search the mirrored runtime/control-panel symbol indexes and generated maps.
- Handler: `search_program_map_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SEARCH_REFERENCE_PACK

- Signature: `SEARCH_REFERENCE_PACK(query, optional_pack_name|all)` (help_text)
- Summary: Search the mirrored Aurora reference packs by topic text.
- Handler: `search_reference_pack_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_ACTION_MODE

- Signature: `SET_ACTION_MODE([value])` (reviewed_contract)
- Summary: Set runtime.action, or omit value to read it. Controller family available to Aurora for approved actions.
- Handler: `set_action_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read runtime.action when omitted; otherwise set it in this runtime session. Controller family available to Aurora for approved actions. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"clear": "none", "desktop": "pyag", "disabled": "none", "game": "gb", "game_boy": "gb", "gameboy": "gb", "off": "none", "pyautogui": "pyag"}, "enum": ["none", "gb", "pyag"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `runtime.action`
- Runtime lock: action
- Apply timing: immediate_action_dispatch
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_ADD_IMSGS_TO_HISTORY

- Signature: `SET_ADD_IMSGS_TO_HISTORY([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_add_imsgs_to_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_ADD_UMSGS_TO_HISTORY

- Signature: `SET_ADD_UMSGS_TO_HISTORY([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_add_umsgs_to_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_AGENT_SUGGESTION_APPROVAL

- Signature: `SET_AGENT_SUGGESTION_APPROVAL(suggestion_id|latest|agent_id, approval=approved|rejected|requested|draft, note=...)` (help_text)
- Summary: Append review-state metadata without Pending Command insertion or execution.
- Handler: `set_agent_suggestion_approval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_AGENT_TASK_STATUS

- Signature: `SET_AGENT_TASK_STATUS(task_id|latest|agent_id, status=draft|active|review|blocked|closed, note=...)` (help_text)
- Summary: Append review/status metadata for a sub-agent task packet without execution or prompt inclusion.
- Handler: `set_agent_task_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_ALWAYS

- Signature: `SET_ALWAYS(on|off, true|false)` (help_text)
- Summary: Explicitly set always-mode and hide_input together.
- Handler: `set_always_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_ASSISTANT_POLICY

- Signature: `SET_ASSISTANT_POLICY([value])` (reviewed_contract)
- Summary: Set runtime.assistant_policy, or omit value to read it. Task flow admits discovery, enabled capture requests, one-turn plans, bounded GB overworld movement and battle menu steps in Auto. Legacy keeps previous review decisions.
- Handler: `set_assistant_policy_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read runtime.assistant_policy when omitted; otherwise set it in this runtime session. Task flow admits discovery, enabled capture requests, one-turn plans, bounded GB overworld movement and battle menu steps in Auto. Legacy keeps previous review decisions. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["legacy", "task_flow"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `runtime.assistant_policy`
- Runtime lock: execution
- Apply timing: immediate
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_AUTH_MODE

- Signature: `SET_AUTH_MODE([value])` (reviewed_contract)
- Summary: Set auth.mode, or omit value to read it. Credential route Aurora will resolve before a model request.
- Handler: `set_auth_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read auth.mode when omitted; otherwise set it in this runtime session. Credential route Aurora will resolve before a model request. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["api_key", "openai_chatgpt", "codex_oauth", "auto"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `auth.mode`
- Runtime lock: auth
- Apply timing: next_auth_resolution
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_AUTO_DYNAMIC_INFERENCE

- Signature: `SET_AUTO_DYNAMIC_INFERENCE([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_auto_dynamic_inference_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_AUTO_PROMPT

- Signature: `SET_AUTO_PROMPT([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_auto_prompt_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_BATTLE_REASONING_EFFORT

- Signature: `SET_BATTLE_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)` (help_text)
- Summary: Set battle reasoning effort.
- Handler: `set_battle_reasoning_effort_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_BATTLE_VERBOSITY

- Signature: `SET_BATTLE_VERBOSITY(low|medium|high)` (help_text)
- Summary: Set verbosity for battle turns.
- Handler: `set_battle_verbosity_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CAPTURE_GEOMETRY_POLICY

- Signature: `SET_CAPTURE_GEOMETRY_POLICY([value])` (reviewed_contract)
- Summary: Set capture.geometry_policy, or omit value to read it. Verified captures an explicit physical rectangle; legacy keeps startup scaling and default desktop grabs.
- Handler: `set_capture_geometry_policy_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.geometry_policy when omitted; otherwise set it in this runtime session. Verified captures an explicit physical rectangle; legacy keeps startup scaling and default desktop grabs. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["verified", "legacy"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `capture.geometry_policy`
- Runtime lock: screenshot_interval
- Apply timing: next_acquisition
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CAPTURE_MODE

- Signature: `SET_CAPTURE_MODE([value])` (reviewed_contract)
- Summary: Set capture.mode, or omit value to read it. Heartbeat captures periodically; request_only captures only when the demand service has a due request.
- Handler: `set_capture_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.mode when omitted; otherwise set it in this runtime session. Heartbeat captures periodically; request_only captures only when the demand service has a due request. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["heartbeat", "request_only"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `capture.mode`
- Runtime lock: screenshot_interval
- Apply timing: next_capture_cycle
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CAPTURE_PROVENANCE_POLICY

- Signature: `SET_CAPTURE_PROVENANCE_POLICY([value])` (reviewed_contract)
- Summary: Set capture.provenance_policy, or omit value to read it. Verified requires pixels acquired after the action settle boundary; legacy retains counter/clock freshness checks.
- Handler: `set_capture_provenance_policy_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.provenance_policy when omitted; otherwise set it in this runtime session. Verified requires pixels acquired after the action settle boundary; legacy retains counter/clock freshness checks. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["verified", "legacy"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `capture.provenance_policy`
- Runtime lock: screenshot_interval
- Apply timing: next_scheduler_check
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CAPTURE_REQUEST_ATTEMPTS

- Signature: `SET_CAPTURE_REQUEST_ATTEMPTS([value])` (reviewed_contract)
- Summary: Set capture.request_max_attempts, or omit value to read it. Maximum acquisition attempts for one request; zero preserves unlimited retries. Legacy drawing recapture shares its parent's attempt.
- Handler: `set_capture_request_attempts_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.request_max_attempts when omitted; otherwise set it in this runtime session. Maximum acquisition attempts for one request; zero preserves unlimited retries. Legacy drawing recapture shares its parent's attempt. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"minimum": 0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "integer"}`

- Registered setting: `capture.request_max_attempts`
- Runtime lock: screenshot_interval
- Apply timing: next_capture_request
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CAPTURE_REQUEST_TIMEOUT

- Signature: `SET_CAPTURE_REQUEST_TIMEOUT([value])` (reviewed_contract)
- Summary: Set capture.request_timeout_seconds, or omit value to read it. Total monotonic deadline from request admission through settle, acquisition, drawing and publication. Zero preserves unlimited waiting.
- Handler: `set_capture_request_timeout_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.request_timeout_seconds when omitted; otherwise set it in this runtime session. Total monotonic deadline from request admission through settle, acquisition, drawing and publication. Zero preserves unlimited waiting. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `capture.request_timeout_seconds`
- Runtime lock: screenshot_interval
- Apply timing: next_capture_request
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CAPTURE_TARGET

- Signature: `SET_CAPTURE_TARGET([value])` (reviewed_contract)
- Summary: Set capture.target, or omit value to read it. Choose primary monitor, virtual desktop or foreground window for verified geometry.
- Handler: `set_capture_target_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.target when omitted; otherwise set it in this runtime session. Choose primary monitor, virtual desktop or foreground window for verified geometry. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["legacy_options", "primary", "virtual", "foreground"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `capture.target`
- Runtime lock: screenshot_interval
- Apply timing: next_verified_acquisition
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_CHAT_HEAD_HISTORY_SIZE

- Signature: `SET_CHAT_HEAD_HISTORY_SIZE(width,height)` (help_text)
- Summary: Set the attached history window size.
- Handler: `set_chat_head_history_size_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CHAT_HEAD_OPACITY

- Signature: `SET_CHAT_HEAD_OPACITY(value)` (help_text)
- Summary: Set chat-head window opacity between 0.25 and 1.0.
- Handler: `set_chat_head_opacity_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CHAT_HEAD_SEND_ANIMATION

- Signature: `SET_CHAT_HEAD_SEND_ANIMATION(pulse|none)` (help_text)
- Summary: Control the send animation style used by the floating chat strip input.
- Handler: `set_chat_head_send_animation_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CHAT_HEAD_SEND_ANIMATION_SECONDS

- Signature: `SET_CHAT_HEAD_SEND_ANIMATION_SECONDS(value)` (help_text)
- Summary: Set the floating chat strip send animation duration.
- Handler: `set_chat_head_send_animation_seconds_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CHAT_HEAD_STRIP_SIZE

- Signature: `SET_CHAT_HEAD_STRIP_SIZE(width,height)` (help_text)
- Summary: Set the strip window size.
- Handler: `set_chat_head_strip_size_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CHAT_HEAD_TOPMOST

- Signature: `SET_CHAT_HEAD_TOPMOST([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_chat_head_topmost_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_CHAT_LOG_ECHO

- Signature: `SET_CHAT_LOG_ECHO(on|off)` (help_text)
- Summary: Toggle compact [CHATLOG] console echo output.
- Handler: `set_chat_log_echo_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_COMMAND_DRIP_LOOKAHEAD

- Signature: `SET_COMMAND_DRIP_LOOKAHEAD(turns)` (help_text)
- Summary: Set how many turns ahead Aurora sketches likely command candidates; this does not approve commands.
- Handler: `set_command_drip_lookahead_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_COMMAND_DRIP_RETENTION

- Signature: `SET_COMMAND_DRIP_RETENTION(turns)` (help_text)
- Summary: Set how many recent turns of command drip history remain on hand. Recommended normal range: 3-7.
- Handler: `set_command_drip_retention_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_COMMAND_DRIP_SHOW_LIKELY_DROPPED

- Signature: `SET_COMMAND_DRIP_SHOW_LIKELY_DROPPED([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_command_drip_show_likely_dropped_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_COMMAND_DRIP_SHOW_VARIANTS

- Signature: `SET_COMMAND_DRIP_SHOW_VARIANTS([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_command_drip_show_variants_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_CONTEXT_MARK_APPROVAL

- Signature: `SET_CONTEXT_MARK_APPROVAL(mark_id|target, approval=draft|requested|approved|rejected, optional mark_type=...)` (help_text)
- Summary: Update a context mark approval state.
- Handler: `set_context_mark_approval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CRITIQUE_REASONING_EFFORT

- Signature: `SET_CRITIQUE_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)` (help_text)
- Summary: Set reasoning effort for critique/self-review turns.
- Handler: `set_critique_reasoning_effort_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CRITIQUE_TURN_INTERVAL

- Signature: `SET_CRITIQUE_TURN_INTERVAL(turns)` (help_text)
- Summary: Set how often Aurora performs a deeper critique/self-review turn.
- Handler: `set_critique_turn_interval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CRITIQUE_VERBOSITY

- Signature: `SET_CRITIQUE_VERBOSITY(low|medium|high)` (help_text)
- Summary: Set verbosity for critique/self-review turns.
- Handler: `set_critique_verbosity_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_CURSOR_LABEL

- Signature: `SET_CURSOR_LABEL(on|off)` (help_text)
- Summary: Toggle the near-cursor XY label.
- Handler: `set_cursor_label_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_DEMAND_CAPTURE

- Signature: `SET_DEMAND_CAPTURE([value])` (reviewed_contract)
- Summary: Set capture.demand_enabled, or omit value to read it. Whether commands and explicit requests may ask the capture service for a fresh frame.
- Handler: `set_demand_capture_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.demand_enabled when omitted; otherwise set it in this runtime session. Whether commands and explicit requests may ask the capture service for a fresh frame. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "true", "1", "yes", "off", "false", "0", "no"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Registered setting: `capture.demand_enabled`
- Runtime lock: screenshot_interval
- Apply timing: immediate_capture_service
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_EPISODIC_EMBEDDINGS

- Signature: `SET_EPISODIC_EMBEDDINGS(off|auto|force)` (help_text)
- Summary: Choose lexical-only retrieval, lexical fallback, or embedding-required retrieval.
- Handler: `set_episodic_embeddings_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EPISODIC_EMBEDDING_MODEL

- Signature: `SET_EPISODIC_EMBEDDING_MODEL(name)` (help_text)
- Summary: Set which OpenAI embedding model episodic retrieval should use.
- Handler: `set_episodic_embedding_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EPISODIC_MEMORY

- Signature: `SET_EPISODIC_MEMORY([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_episodic_memory_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_EPISODIC_MEMORY_INTERVAL

- Signature: `SET_EPISODIC_MEMORY_INTERVAL(seconds)` (help_text)
- Summary: Set the periodic episodic snapshot interval. Minimum 60 seconds.
- Handler: `set_episodic_memory_interval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EPISODIC_MEMORY_PERIODIC

- Signature: `SET_EPISODIC_MEMORY_PERIODIC([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_episodic_memory_periodic_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_EPISODIC_MEMORY_SCENE_TRIGGER

- Signature: `SET_EPISODIC_MEMORY_SCENE_TRIGGER([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_episodic_memory_scene_trigger_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_EPISODIC_PLANNING_ASSIST

- Signature: `SET_EPISODIC_PLANNING_ASSIST(off|review|critique|review_critique)` (help_text)
- Summary: Bound automatic episodic retrieval injection to higher-attention planning turns.
- Handler: `set_episodic_planning_assist_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EPISODIC_PLANNING_ASSIST_COOLDOWN

- Signature: `SET_EPISODIC_PLANNING_ASSIST_COOLDOWN(turns)` (help_text)
- Summary: Set the minimum turn gap before bounded planning retrieval may run again. Range 0-12.
- Handler: `set_episodic_planning_assist_cooldown_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EPISODIC_PLANNING_ASSIST_K

- Signature: `SET_EPISODIC_PLANNING_ASSIST_K(k)` (help_text)
- Summary: Set how many episodic memories bounded planning turns may inject. Range 1-4.
- Handler: `set_episodic_planning_assist_k_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_EXECUTION_MODE

- Signature: `SET_EXECUTION_MODE([value])` (reviewed_contract)
- Summary: Set runtime.execution, or omit value to read it. Approval and execution posture for commands proposed by the model.
- Handler: `set_execution_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read runtime.execution when omitted; otherwise set it in this runtime session. Approval and execution posture for commands proposed by the model. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"guided": "assist", "live": "auto", "review": "safe"}, "enum": ["safe", "assist", "auto"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `runtime.execution`
- Runtime lock: execution
- Apply timing: immediate_command_policy
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_GAMEPLAY_SCENE_POLICY

- Signature: `SET_GAMEPLAY_SCENE_POLICY([value])` (reviewed_contract)
- Summary: Set game.scene_policy, or omit value to read it. Evidence uses fresh model observation/scene sections with token boundaries and conflict checks. Legacy retains mixed-context substring inference.
- Handler: `set_gameplay_scene_policy_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read game.scene_policy when omitted; otherwise set it in this runtime session. Evidence uses fresh model observation/scene sections with token boundaries and conflict checks. Legacy retains mixed-context substring inference. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["evidence", "legacy"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `game.scene_policy`
- Runtime lock: action
- Apply timing: next_scene_evaluation
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_GAME_PROFILE

- Signature: `SET_GAME_PROFILE([value])` (reviewed_contract)
- Summary: Set game.profile, or omit value to read it. Gameplay assumptions, prompts, controls, and save-state guidance.
- Handler: `set_game_profile_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read game.profile when omitted; otherwise set it in this runtime session. Gameplay assumptions, prompts, controls, and save-state guidance. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["firered", "blue"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `game.profile`
- Runtime lock: none
- Apply timing: next_gameplay_reasoning
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_GOAL_SAVE_FORMAT

- Signature: `SET_GOAL_SAVE_FORMAT([value])` (reviewed_contract)
- Summary: Set goals.save_format, or omit value to read it. Versioned saves add a schema envelope; legacy preserves the existing task document shape. Both use recursive IDs, validation and atomic replacement.
- Handler: `set_goal_save_format_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read goals.save_format when omitted; otherwise set it in this runtime session. Versioned saves add a schema envelope; legacy preserves the existing task document shape. Both use recursive IDs, validation and atomic replacement. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["versioned", "legacy"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `goals.save_format`
- Runtime lock: execution
- Apply timing: next_explicit_save
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_HIGH_DETAIL

- Signature: `SET_HIGH_DETAIL(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `set_high_detail_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_IMAGE_DETAIL

- Signature: `SET_IMAGE_DETAIL([value])` (reviewed_contract)
- Summary: Set vision.image_detail, or omit value to read it. Default image detail before model-specific compatibility normalization.
- Handler: `set_image_detail_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read vision.image_detail when omitted; otherwise set it in this runtime session. Default image detail before model-specific compatibility normalization. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["low", "high", "auto", "original"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `vision.image_detail`
- Runtime lock: none
- Apply timing: next_image_request
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_IMPORTANT_MESSAGES

- Signature: `SET_IMPORTANT_MESSAGES([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_important_messages_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_IMSGS_DECAY_CHECK

- Signature: `SET_IMSGS_DECAY_CHECK([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_imsgs_decay_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_INIT_DELIVERY

- Signature: `SET_INIT_DELIVERY([value])` (reviewed_contract)
- Summary: Set context.init_delivery, or omit value to read it. System once omits exact Init history copies only when the full text is already in the system prompt. Stored history is preserved.
- Handler: `set_init_delivery_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read context.init_delivery when omitted; otherwise set it in this runtime session. System once omits exact Init history copies only when the full text is already in the system prompt. Stored history is preserved. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["legacy", "system_once"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `context.init_delivery`
- Runtime lock: live_init
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_KEYPOINT_GRID

- Signature: `SET_KEYPOINT_GRID(on|off)` (help_text)
- Summary: Toggle the red key-point grid overlay.
- Handler: `set_keypoint_grid_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_LATEST_IMAGE_DETAIL

- Signature: `SET_LATEST_IMAGE_DETAIL(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `set_latest_image_detail_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_LIVE_INIT

- Signature: `SET_LIVE_INIT([value])` (reviewed_contract)
- Summary: Set runtime.live_init, or omit value to read it. Whether Aurora loads its full live initialization prompt when that path is used.
- Handler: `set_live_init_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read runtime.live_init when omitted; otherwise set it in this runtime session. Whether Aurora loads its full live initialization prompt when that path is used. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "true", "1", "yes", "off", "false", "0", "no"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Registered setting: `runtime.live_init`
- Runtime lock: live_init
- Apply timing: next_live_initialization
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_LIVE_MODE

- Signature: `SET_LIVE_MODE([value])` (reviewed_contract)
- Summary: Set runtime.live, or omit value to read it. Whether Aurora may send model requests and process model responses.
- Handler: `set_live_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read runtime.live when omitted; otherwise set it in this runtime session. Whether Aurora may send model requests and process model responses. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"live": true, "safe": false}, "accepted_text": ["on", "true", "1", "yes", "off", "false", "0", "no"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Registered setting: `runtime.live`
- Runtime lock: live
- Apply timing: immediate_model_loop_gate
- Related effects: Turning live mode off cancels pending model work; completed actions are not undone.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_MAX_IMAGES_IN_HISTORY

- Signature: `SET_MAX_IMAGES_IN_HISTORY(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `set_max_images_in_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_MODEL_TRANSPORT

- Signature: `SET_MODEL_TRANSPORT([value])` (reviewed_contract)
- Summary: Set model.transport, or omit value to read it. Explicit live transport selection. Responses requires Astra/API-key auth and keeps provider history. An intervening Chat Completions turn requires an explicit Responses reset. Does not enable live mode.
- Handler: `set_model_transport_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read model.transport when omitted; otherwise set it in this runtime session. Explicit live transport selection. Responses requires Astra/API-key auth and keeps provider history. An intervening Chat Completions turn requires an explicit Responses reset. Does not enable live mode. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["chat_completions", "responses"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `model.transport`
- Runtime lock: models
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_MODEL_VERBOSITY

- Signature: `SET_MODEL_VERBOSITY([value])` (reviewed_contract)
- Summary: Set inference.verbosity, or omit value to read it. Default response verbosity for model families that support it.
- Handler: `set_model_verbosity_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read inference.verbosity when omitted; otherwise set it in this runtime session. Default response verbosity for model families that support it. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["low", "medium", "high"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `inference.verbosity`
- Runtime lock: reasoning
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_NEXT_INFERENCE

- Signature: `SET_NEXT_INFERENCE([key=value; ...])` (reviewed_contract)
- Summary: Replace the queued one-turn model/effort/verbosity/image/temperature plan; omit arguments to inspect. Session defaults stay unchanged.
- Handler: `set_next_inference_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Replace the queued one-turn model/effort/verbosity/image/temperature plan; omit arguments to inspect. Session defaults stay unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"detail": "image_detail", "latest_detail": "latest_image_detail", "reasoning": "reasoning_effort", "summary": "summary_mode", "verbosity_level": "verbosity"}, "assignment": ["=", ":"], "keys": ["service_tier", "reasoning_effort", "verbosity", "image_detail", "latest_image_detail", "temperature", "model", "text_model", "vision_model", "reasoning_model", "summary_mode", "note", "target_turn"], "name": "options", "omitted": "read_current_plan", "option_schema": {"additionalProperties": false, "properties": {"image_detail": {"enum": ["low", "high", "auto", "original"], "setting_contract": "vision.image_detail", "type": "string"}, "latest_image_detail": {"enum": ["low", "high", "auto", "original"], "setting_contract": "vision.image_detail", "type": "string"}, "model": {"setting_contract": "model.text", "type": "string"}, "note": {"type": "string"}, "reasoning_effort": {"enum": ["minimal", "none", "low", "medium", "high", "xhigh", "max"], "setting_contract": "inference.reasoning_effort", "type": "string"}, "reasoning_model": {"setting_contract": "model.reasoning", "type": "string"}, "service_tier": {"enum": ["regular", "priority", "ultrafast"], "setting_contract": "inference.service_tier", "type": "string"}, "summary_mode": {"enum": ["auto", "none", "brief", "detailed"], "type": "string"}, "target_turn": {"default": 0, "maximum": 9223372036854775807, "minimum": 0, "type": "integer", "zero": "next_turn"}, "temperature": {"finite": true, "maximum": 2.0, "minimum": 0.0, "setting_contract": "inference.temperature", "type": "number"}, "text_model": {"setting_contract": "model.text", "type": "string"}, "verbosity": {"enum": ["low", "medium", "high"], "setting_contract": "inference.verbosity", "type": "string"}, "vision_model": {"setting_contract": "model.vision", "type": "string"}}, "type": "object"}, "required": false, "separators": ["semicolon", "newline", "separate command arguments"], "type": "string", "variadic": true}`

- Result protocol: `aurora_inference_plan_result_v1`
- Receipt field: `inference_plan_results`
- Verification: Detached before/after queued plans and content fingerprints. A queued plan is not proof of provider acceptance; model compatibility normalization still applies.
- Failure policy: Reject malformed batches before effects. Stop the batch tail on execution failure; do not replay uncertain outcomes.

### SET_NEXT_REASONING_EFFORT

- Signature: `SET_NEXT_REASONING_EFFORT([effort[, note]])` (reviewed_contract)
- Summary: Replace the queued plan with one turn's reasoning effort and optional note; omit arguments to inspect. Model compatibility normalization still applies.
- Handler: `set_next_reasoning_effort_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Replace the queued plan with one turn's reasoning effort and optional note; omit arguments to inspect. Model compatibility normalization still applies.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["minimal", "none", "low", "medium", "high", "xhigh", "max"], "name": "effort", "omitted": "read_current_plan", "required": false, "type": "string"}`
- Parameter: `{"name": "note", "required": false, "type": "string"}`

- Result protocol: `aurora_inference_plan_result_v1`
- Receipt field: `inference_plan_results`
- Verification: Detached before/after queued plans and content fingerprints. A queued plan is not proof of provider acceptance; model compatibility normalization still applies.
- Failure policy: Reject malformed batches before effects. Stop the batch tail on execution failure; do not replay uncertain outcomes.

### SET_OPERATOR_PASSCODE

- Signature: `SET_OPERATOR_PASSCODE(passcode)` (help_text)
- Summary: Configure or replace the external-operator passcode used for privileged raw bridge commands.
- Handler: `set_operator_passcode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_OPERATOR_PASSCODE_REQUIRED

- Signature: `SET_OPERATOR_PASSCODE_REQUIRED(on|off)` (help_text)
- Summary: Require or relax passcode authorization for privileged external operator commands.
- Handler: `set_operator_passcode_required_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_PASSCODE_COMMAND_VISIBILITY

- Signature: `SET_PASSCODE_COMMAND_VISIBILITY(on|off)` (help_text)
- Summary: Show raw passcode-bearing commands in logs/history, or mask them as *******.
- Handler: `set_passcode_command_visibility_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_PENDING_QUEUE_MODE

- Signature: `SET_PENDING_QUEUE_MODE(normal|replace|insert)` (help_text)
- Summary: Set how newly queued pending commands behave by default in the pending planning lane.
- Handler: `set_pending_queue_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_PROMPT_INCLUSION_ACTIVATION

- Signature: `SET_PROMPT_INCLUSION_ACTIVATION(on|off, preview_id=latest|fresh|..., checklist_id=latest|fresh|..., confirm=offline_proof|rollback)` (help_text)
- Summary: Enable or disable reversible Prompt Inclusion after fresh review and offline proof.
- Handler: `set_prompt_inclusion_activation_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_READBACK_SCOPE

- Signature: `SET_READBACK_SCOPE([value])` (reviewed_contract)
- Summary: Set scheduler.readback_scope, or omit value to read it. Discovery preserves history-based lookup delivery; reviewed additionally includes bounded task-correlated settings, goals, history and retrieval receipts.
- Handler: `set_readback_scope_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.readback_scope when omitted; otherwise set it in this runtime session. Discovery preserves history-based lookup delivery; reviewed additionally includes bounded task-correlated settings, goals, history and retrieval receipts. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["discovery", "reviewed"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `scheduler.readback_scope`
- Runtime lock: reasoning
- Apply timing: next_receipt_and_request
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_READBACK_WAKE

- Signature: `SET_READBACK_WAKE([value])` (reviewed_contract)
- Summary: Set scheduler.readback_wake_enabled, or omit value to read it. Wake a follow-up for eligible discovery or reviewed receipt data, according to readback scope. Requires bounded task mode.
- Handler: `set_readback_wake_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.readback_wake_enabled when omitted; otherwise set it in this runtime session. Wake a follow-up for eligible discovery or reviewed receipt data, according to readback scope. Requires bounded task mode. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "true", "1", "yes", "off", "false", "0", "no"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Registered setting: `scheduler.readback_wake_enabled`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_REASONING_EFFORT

- Signature: `SET_REASONING_EFFORT([value])` (reviewed_contract)
- Summary: Set inference.reasoning_effort, or omit value to read it. Default reasoning effort before model-specific compatibility normalization.
- Handler: `set_reasoning_effort_command`
- Binding: runtime
- Aliases: SET_SESSION_REASONING_EFFORT
- Parameter validation: pre_dispatch
- Effects: Read inference.reasoning_effort when omitted; otherwise set it in this runtime session. Default reasoning effort before model-specific compatibility normalization. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["minimal", "none", "low", "medium", "high", "xhigh", "max"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `inference.reasoning_effort`
- Runtime lock: reasoning
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_REASONING_MODEL

- Signature: `SET_REASONING_MODEL([value])` (reviewed_contract)
- Summary: Set model.reasoning, or omit value to read it. Model selected when Aurora requests a reasoning-oriented turn.
- Handler: `set_reasoning_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read model.reasoning when omitted; otherwise set it in this runtime session. Model selected when Aurora requests a reasoning-oriented turn. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "value", "nonempty": true, "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `model.reasoning`
- Runtime lock: models
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_REASONING_SUMMARY_MODE

- Signature: `SET_REASONING_SUMMARY_MODE(auto|none|brief|detailed)` (help_text)
- Summary: Track the preferred reasoning summary mode.
- Handler: `set_reasoning_summary_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_REVIEW_REASONING_EFFORT

- Signature: `SET_REVIEW_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)` (help_text)
- Summary: Set reasoning effort for scheduled review turns.
- Handler: `set_review_reasoning_effort_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_REVIEW_TURN_INTERVAL

- Signature: `SET_REVIEW_TURN_INTERVAL(turns)` (help_text)
- Summary: Set how often Aurora performs a deliberate review turn.
- Handler: `set_review_turn_interval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_REVIEW_VERBOSITY

- Signature: `SET_REVIEW_VERBOSITY(low|medium|high)` (help_text)
- Summary: Set verbosity for scheduled higher-attention review turns.
- Handler: `set_review_verbosity_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_SCREENSHOT_INTERVAL

- Signature: `SET_SCREENSHOT_INTERVAL([value])` (reviewed_contract)
- Summary: Set capture.screenshot_interval, or omit value to read it. Requested screenshot polling interval before idle floors and other effective cadence rules.
- Handler: `set_screenshot_interval_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read capture.screenshot_interval when omitted; otherwise set it in this runtime session. Requested screenshot polling interval before idle floors and other effective cadence rules. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.02, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `capture.screenshot_interval`
- Runtime lock: screenshot_interval
- Apply timing: next_capture_cycle
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_SERVICE_TIER

- Signature: `SET_SERVICE_TIER([value])` (reviewed_contract)
- Summary: Set inference.service_tier, or omit value to read it. Requested service priority, independent of reasoning effort. Regular omits acceleration; subscription catalog must advertise other tiers.
- Handler: `set_service_tier_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read inference.service_tier when omitted; otherwise set it in this runtime session. Requested service priority, independent of reasoning effort. Regular omits acceleration; subscription catalog must advertise other tiers. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"fast": "priority"}, "enum": ["regular", "priority", "ultrafast"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `inference.service_tier`
- Runtime lock: reasoning
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_SESSION_REASONING_EFFORT

- Signature: `SET_SESSION_REASONING_EFFORT([value])` (reviewed_contract)
- Summary: Set inference.reasoning_effort, or omit value to read it. Default reasoning effort before model-specific compatibility normalization.
- Handler: `set_session_reasoning_effort_command`
- Binding: runtime
- Aliases: SET_REASONING_EFFORT
- Parameter validation: pre_dispatch
- Effects: Read inference.reasoning_effort when omitted; otherwise set it in this runtime session. Default reasoning effort before model-specific compatibility normalization. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["minimal", "none", "low", "medium", "high", "xhigh", "max"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `inference.reasoning_effort`
- Runtime lock: reasoning
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_SHOW_AI_COMMANDS

- Signature: `SET_SHOW_AI_COMMANDS([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_show_ai_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_SHOW_AI_TEXT

- Signature: `SET_SHOW_AI_TEXT([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_show_ai_text_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_SHOW_USER_COMMANDS

- Signature: `SET_SHOW_USER_COMMANDS([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_show_user_commands_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_SHOW_USER_TEXT

- Signature: `SET_SHOW_USER_TEXT([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_show_user_text_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_SOUND_EFFECTS

- Signature: `SET_SOUND_EFFECTS(on|off)` (help_text)
- Summary: Enable or disable sound effects.
- Handler: `set_sound_effects_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_STATEFUL_MODEL_PRESET

- Signature: `SET_STATEFUL_MODEL_PRESET(stateless-default|responses-link-preview|conversation-preview)` (help_text)
- Summary: Select the visible stateful preset profile metadata; live transport remains unchanged until a later transport slice.
- Handler: `set_stateful_model_preset_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_STATUS_OVERLAY

- Signature: `SET_STATUS_OVERLAY(on|off)` (help_text)
- Summary: Toggle the top status text overlay.
- Handler: `set_status_overlay_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_TASK_CONTINUATION

- Signature: `SET_TASK_CONTINUATION([value])` (reviewed_contract)
- Summary: Set task.continuation_mode, or omit value to read it. Bounded limits all model slots/wake reasons in one task; legacy retains unrestricted scheduler behavior.
- Handler: `set_task_continuation_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read task.continuation_mode when omitted; otherwise set it in this runtime session. Bounded limits all model slots/wake reasons in one task; legacy retains unrestricted scheduler behavior. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"enum": ["legacy", "bounded"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `task.continuation_mode`
- Runtime lock: execution
- Apply timing: immediate
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TASK_MAX_MODEL_TURNS

- Signature: `SET_TASK_MAX_MODEL_TURNS([value])` (reviewed_contract)
- Summary: Set task.max_model_turns, or omit value to read it. Maximum model-turn admissions, across primary/review slots. Latched at the next task start.
- Handler: `set_task_max_model_turns_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read task.max_model_turns when omitted; otherwise set it in this runtime session. Maximum model-turn admissions, across primary/review slots. Latched at the next task start. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"maximum": 10000, "minimum": 1, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "integer"}`

- Registered setting: `task.max_model_turns`
- Runtime lock: execution
- Apply timing: next_task
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TASK_MAX_SECONDS

- Signature: `SET_TASK_MAX_SECONDS([value])` (reviewed_contract)
- Summary: Set task.max_seconds, or omit value to read it. Elapsed-time admission limit; late model responses cannot launch new commands. Latched at next task start.
- Handler: `set_task_max_seconds_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read task.max_seconds when omitted; otherwise set it in this runtime session. Elapsed-time admission limit; late model responses cannot launch new commands. Latched at next task start. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "maximum": 86400, "minimum": 1, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `task.max_seconds`
- Runtime lock: execution
- Apply timing: next_task
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TEMPERATURE

- Signature: `SET_TEMPERATURE([value])` (reviewed_contract)
- Summary: Set inference.temperature, or omit value to read it. Sampling temperature used by Aurora where the selected model accepts it.
- Handler: `set_temperature_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read inference.temperature when omitted; otherwise set it in this runtime session. Sampling temperature used by Aurora where the selected model accepts it. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "maximum": 2.0, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `inference.temperature`
- Runtime lock: temperature
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TEXT_MODEL

- Signature: `SET_TEXT_MODEL([value])` (reviewed_contract)
- Summary: Set model.text, or omit value to read it. Model used for text-oriented Aurora turns.
- Handler: `set_text_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read model.text when omitted; otherwise set it in this runtime session. Model used for text-oriented Aurora turns. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "value", "nonempty": true, "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `model.text`
- Runtime lock: models
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TILE_GRID

- Signature: `SET_TILE_GRID(on|off)` (help_text)
- Summary: Toggle the colored tile grid overlay.
- Handler: `set_tile_grid_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_TIME_LOGGING

- Signature: `SET_TIME_LOGGING(on|off)` (help_text)
- Summary: Toggle detailed timing/debug logging.
- Handler: `set_time_logging_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SET_TURN_CAPTURE_WAKE

- Signature: `SET_TURN_CAPTURE_WAKE([value])` (reviewed_contract)
- Summary: Set scheduler.capture_wake_enabled, or omit value to read it. Whether settled capture changes may wake a model turn in hybrid scheduler mode.
- Handler: `set_turn_capture_wake_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.capture_wake_enabled when omitted; otherwise set it in this runtime session. Whether settled capture changes may wake a model turn in hybrid scheduler mode. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "true", "1", "yes", "off", "false", "0", "no"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Registered setting: `scheduler.capture_wake_enabled`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS

- Signature: `SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS([value])` (reviewed_contract)
- Summary: Set scheduler.capture_wake_debounce_seconds, or omit value to read it. Settle delay before a changed capture may wake a model turn.
- Handler: `set_turn_capture_wake_debounce_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.capture_wake_debounce_seconds when omitted; otherwise set it in this runtime session. Settle delay before a changed capture may wake a model turn. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `scheduler.capture_wake_debounce_seconds`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_HEARTBEAT_SECONDS

- Signature: `SET_TURN_HEARTBEAT_SECONDS([value])` (reviewed_contract)
- Summary: Set scheduler.heartbeat_seconds, or omit value to read it. Maximum quiet interval before a heartbeat can wake a turn; zero explicitly disables periodic model turns.
- Handler: `set_turn_heartbeat_seconds_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.heartbeat_seconds when omitted; otherwise set it in this runtime session. Maximum quiet interval before a heartbeat can wake a turn; zero explicitly disables periodic model turns. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `scheduler.heartbeat_seconds`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_MIN_GAP_SECONDS

- Signature: `SET_TURN_MIN_GAP_SECONDS([value])` (reviewed_contract)
- Summary: Set scheduler.min_gap_seconds, or omit value to read it. Minimum spacing between model-turn submissions.
- Handler: `set_turn_min_gap_seconds_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.min_gap_seconds when omitted; otherwise set it in this runtime session. Minimum spacing between model-turn submissions. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `scheduler.min_gap_seconds`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_POST_ACTION_SETTLE_SECONDS

- Signature: `SET_TURN_POST_ACTION_SETTLE_SECONDS([value])` (reviewed_contract)
- Summary: Set scheduler.post_action_settle_seconds, or omit value to read it. Delay after an action result before scheduler follow-up may proceed.
- Handler: `set_turn_post_action_settle_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.post_action_settle_seconds when omitted; otherwise set it in this runtime session. Delay after an action result before scheduler follow-up may proceed. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0.0, "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "number"}`

- Registered setting: `scheduler.post_action_settle_seconds`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_SCHEDULER_MODE

- Signature: `SET_TURN_SCHEDULER_MODE([value])` (reviewed_contract)
- Summary: Set scheduler.mode, or omit value to read it. Wake strategy for capture-driven, event-driven, or hybrid turns.
- Handler: `set_turn_scheduler_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.mode when omitted; otherwise set it in this runtime session. Wake strategy for capture-driven, event-driven, or hybrid turns. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"capture": "per_capture", "capture-tick": "per_capture", "capture_tick": "per_capture", "codex-like": "hybrid", "codex_like": "hybrid", "event-driven": "event", "event_driven": "event", "hybrid-event": "hybrid", "hybrid_event": "hybrid", "legacy": "per_capture", "per-capture": "per_capture", "tool-loop": "event", "tool_loop": "event"}, "enum": ["per_capture", "event", "hybrid"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `scheduler.mode`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_TURN_SCHEDULER_PROFILE

- Signature: `SET_TURN_SCHEDULER_PROFILE([value])` (reviewed_contract)
- Summary: Set scheduler.profile, or omit value to read it. Named bundle for Aurora turn wake and pacing thresholds.
- Handler: `set_turn_scheduler_profile_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read scheduler.profile when omitted; otherwise set it in this runtime session. Named bundle for Aurora turn wake and pacing thresholds. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"default": "balanced", "fast": "responsive", "per-capture": "legacy", "per_capture": "legacy", "quick": "responsive", "slow": "conservative"}, "enum": ["responsive", "balanced", "conservative", "legacy"], "name": "value", "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `scheduler.profile`
- Runtime lock: reasoning
- Apply timing: immediate_scheduler
- Related effects: A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SET_UMSGS_DECAY_CHECK

- Signature: `SET_UMSGS_DECAY_CHECK([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_umsgs_decay_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_UNIMPORTANT_MESSAGES

- Signature: `SET_UNIMPORTANT_MESSAGES([on|off])` (reviewed_contract)
- Summary: Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no.
- Handler: `set_unimportant_messages_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"], "name": "enabled", "omitted": "read_current_value", "required": false, "type": "boolean"}`

- Result protocol: `boolean_handler_result`
- Verification: Query or inspect runtime state; no versioned setting receipt is implied.
- Failure policy: Validate the whole batch before effects; a handler failure stops its remaining commands.

### SET_VISION_MODEL

- Signature: `SET_VISION_MODEL([value])` (reviewed_contract)
- Summary: Set model.vision, or omit value to read it. Model selected for vision-oriented Aurora turns.
- Handler: `set_vision_model_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read model.vision when omitted; otherwise set it in this runtime session. Model selected for vision-oriented Aurora turns. Saved defaults are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "value", "nonempty": true, "nullable": false, "omitted": "read_current_value", "required": false, "type": "string"}`

- Registered setting: `model.vision`
- Runtime lock: models
- Apply timing: next_model_turn
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### SHOW_AGENTS

- Signature: `SHOW_AGENTS()` (help_text)
- Summary: Display metadata-only Agent Registry / History ACL state.
- Handler: `show_agents_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_HELPER_CLOSURE

- Signature: `SHOW_AGENT_HELPER_CLOSURE()` (help_text)
- Summary: Display Window 20 helper closure readiness, Pending cleanup status, manual-approval boundary, and guardrails.
- Handler: `show_agent_helper_closure_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_HISTORY

- Signature: `SHOW_AGENT_HISTORY(optional_agent_id)` (help_text)
- Summary: Display per-agent private-history JSONL counts and parent-visible summaries.
- Handler: `show_agent_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_HISTORY_ACLS

- Signature: `SHOW_AGENT_HISTORY_ACLS()` (help_text)
- Summary: Display per-agent history ACL preview rows and JSONL audit-log path readiness.
- Handler: `show_agent_history_acls_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_PENDING_GATE

- Signature: `SHOW_AGENT_PENDING_GATE(optional_filter)` (help_text)
- Summary: Display task/suggestion review links and the closed Pending Command gate preview.
- Handler: `show_agent_pending_gate_command`
- Binding: runtime
- Aliases: SHOW_AGENT_REVIEW_LINKS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_PENDING_INSERT_CHECKLIST

- Signature: `SHOW_AGENT_PENDING_INSERT_CHECKLIST(optional_filter)` (help_text)
- Summary: Display the no-exec Pending insertion checklist/dry-run contract for review-linked suggestions.
- Handler: `show_agent_pending_insert_checklist_command`
- Binding: runtime
- Aliases: SHOW_AGENT_PENDING_INSERT_DRY_RUN
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_PENDING_INSERT_DRY_RUN

- Signature: `SHOW_AGENT_PENDING_INSERT_DRY_RUN(optional_filter)` (help_text)
- Summary: Display the no-exec Pending insertion checklist/dry-run contract for review-linked suggestions.
- Handler: `show_agent_pending_insert_checklist_command`
- Binding: runtime
- Aliases: SHOW_AGENT_PENDING_INSERT_CHECKLIST
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_REVIEW_LINKS

- Signature: `SHOW_AGENT_REVIEW_LINKS(optional_filter)` (help_text)
- Summary: Display task/suggestion review links and the closed Pending Command gate preview.
- Handler: `show_agent_pending_gate_command`
- Binding: runtime
- Aliases: SHOW_AGENT_PENDING_GATE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_SUGGESTIONS

- Signature: `SHOW_AGENT_SUGGESTIONS(optional_agent_or_status)` (help_text)
- Summary: Display append-only sub-agent suggestion audit rows and policy outcomes.
- Handler: `show_agent_suggestions_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_SUGGESTION_ROUTES

- Signature: `SHOW_AGENT_SUGGESTION_ROUTES()` (help_text)
- Summary: Display metadata-only sub-agent suggestion route and policy-tag preview rows.
- Handler: `show_agent_suggestion_routes_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AGENT_TASKS

- Signature: `SHOW_AGENT_TASKS(optional_agent_or_status)` (help_text)
- Summary: Display append-only sub-agent task packets and review/status outcomes.
- Handler: `show_agent_tasks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_AUTH

- Signature: `SHOW_AUTH()` (help_text)
- Summary: Display the configured and last-resolved auth path.
- Handler: `show_auth_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_CHAT_HEAD

- Signature: `SHOW_CHAT_HEAD()` (help_text)
- Summary: Display the current floating chat-head settings.
- Handler: `show_chat_head_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_CHECKPOINT_READINESS

- Signature: `SHOW_CHECKPOINT_READINESS()` (help_text)
- Summary: Display the read-only Window 18-21 checkpoint posture rollup; does not stage, commit, call models, spawn helpers, or approve Pending Commands.
- Handler: `show_window_18_21_checkpoint_readiness_command`
- Binding: runtime
- Aliases: SHOW_WINDOW_18_21_CHECKPOINT_READINESS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_COMMAND_DRIP

- Signature: `SHOW_COMMAND_DRIP()` (help_text)
- Summary: Display the recent and near-future command tree. Lookahead lanes are candidate forecasts, not approved actions.
- Handler: `show_command_drip_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_COMPANION_CONTRACT_CLOSURE

- Signature: `SHOW_COMPANION_CONTRACT_CLOSURE()` (help_text)
- Summary: Display Window 21 companion contract closure readiness, parked companion status, and write-boundary guardrails.
- Handler: `show_companion_contract_closure_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_COMPANION_CONTRACT_READINESS

- Signature: `SHOW_COMPANION_CONTRACT_READINESS()` (help_text)
- Summary: Display the Window 21 read-only companion contract readiness surface for Control Panel, Browser, Portal/Chats, and AGB without opening integration writes.
- Handler: `show_companion_contract_readiness_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_COMPANION_PROTOCOL_CONTRACT

- Signature: `SHOW_COMPANION_PROTOCOL_CONTRACT()` (help_text)
- Summary: Display the Window 21 read-only companion request/receipt/route protocol contract without enabling companion writes.
- Handler: `show_companion_protocol_contract_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_COMPANION_RECEIPT_AUDIT

- Signature: `SHOW_COMPANION_RECEIPT_AUDIT()` (help_text)
- Summary: Display the Window 21 read-only companion receipt/audit readiness contract without creating or writing a receipt store.
- Handler: `show_companion_receipt_audit_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_CONTEXT_MARKS

- Signature: `SHOW_CONTEXT_MARKS()` (help_text)
- Summary: Display writable metadata context-mark policy/store status for Prompt Pin, Operator/Local Pin, Search Pin, Retention Class, Importance Score, Retrieval Relevance Boost, and explicit drop/do-not-include semantics.
- Handler: `show_context_marks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_DEFAULT_PROFILES

- Signature: `SHOW_DEFAULT_PROFILES()` (reviewed_contract)
- Summary: Inspect system/personal profiles and distinguish missing, invalid and unreadable saved files.
- Handler: `show_default_profiles_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Inspect system/personal profiles and distinguish missing, invalid and unreadable saved files.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_default_profile_result_v1`
- Receipt field: `default_profile_results`
- Verification: Runtime profile state or saved file bytes; not provider, overlay, native-effect or cross-process CAS proof.
- Failure policy: Stop the batch tail. Prevalidate before writes; attempt and verify restoration after partial apply. Never replay automatically.

### SHOW_DO_NOT_INCLUDE

- Signature: `SHOW_DO_NOT_INCLUDE()` (help_text)
- Summary: Display do-not-include/drop metadata rows and their non-erasing, non-model-visible status.
- Handler: `show_do_not_include_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_EPISODIC_MEMORY_STATUS

- Signature: `SHOW_EPISODIC_MEMORY_STATUS()` (help_text)
- Summary: Display episodic snapshot status, last snapshot, and storage path.
- Handler: `show_episodic_memory_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_GAME_PROFILE

- Signature: `SHOW_GAME_PROFILE()` (help_text)
- Summary: Display the current game profile, profile source, and the active save-state caveat.
- Handler: `show_game_profile_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_HELD_INPUTS

- Signature: `SHOW_HELD_INPUTS()` (reviewed_contract)
- Summary: Inspect Aurora-owned inputs, their request identity, frozen route and release uncertainty.
- Handler: `show_held_inputs_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Inspect Aurora-owned inputs, their request identity, frozen route and release uncertainty.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_held_inputs_v1`
- Receipt field: `held_input_results`
- Verification: Backend submission only; no proof of application behavior or ownership of physically held human inputs.
- Failure policy: Stop the remaining batch on failure. Failed releases stay tracked for explicit retry; an in-flight native call may defer cleanup to its owner.

### SHOW_HISTORY_CONTEXT_SERVICE

- Signature: `SHOW_HISTORY_CONTEXT_SERVICE()` (help_text)
- Summary: Display the Window 16 history/context service inventory, current store ownership, companion read/write contract preview, and cleanup candidates.
- Handler: `show_history_context_service_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_IMAGE_CONTEXT_INDEX

- Signature: `SHOW_IMAGE_CONTEXT_INDEX()` (help_text)
- Summary: Display Window 12 screenshot sidecar/index metadata for capture reason, prompt-context state, hashes, caption/OCR/tags, and embedding placeholders.
- Handler: `show_image_context_index_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_IMAGE_COST_POSTURE

- Signature: `SHOW_IMAGE_COST_POSTURE()` (help_text)
- Summary: Display Window 18 screenshot/image-index cost posture, bounded scan/backfill/search limits, cache posture, and cheap-versus-expensive image-work guardrails without changing files or model context.
- Handler: `show_image_cost_posture_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_LIVE_VISUAL_HARNESS

- Signature: `SHOW_LIVE_VISUAL_HARNESS()` (help_text)
- Summary: Display the Window 11 bounded live visual/reasoning harness contract, readiness warnings, expected image/context counts, escalation stages, and cleanup expectations.
- Handler: `show_live_visual_harness_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_LIVE_VISUAL_HARNESS_PROBE

- Signature: `SHOW_LIVE_VISUAL_HARNESS_PROBE()` (help_text)
- Summary: Display the armed live probe contract and latest recorded result.
- Handler: `show_live_visual_harness_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_LIVE_VISUAL_HARNESS_REHEARSAL

- Signature: `SHOW_LIVE_VISUAL_HARNESS_REHEARSAL()` (help_text)
- Summary: Display the latest recorded offline harness rehearsal result.
- Handler: `show_live_visual_harness_rehearsal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_LOCKS

- Signature: `SHOW_LOCKS()` (help_text)
- Summary: Display which runtime settings are currently locked.
- Handler: `show_locks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_MODELS

- Signature: `SHOW_MODELS()` (help_text)
- Summary: Display built-in and custom models currently available to Aurora.
- Handler: `show_model_catalog_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_MODEL_STATUS

- Signature: `SHOW_MODEL_STATUS()` (help_text)
- Summary: Display the active model trio, effort defaults, interval heuristics, stateful preset metadata, and capability notes.
- Handler: `show_model_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_MONITOR_STATUS

- Signature: `SHOW_MONITOR_STATUS()` (help_text)
- Summary: Display bounded runtime health checks for process state, worker restarts, capture freshness, command wake state, pending queue posture, and gameplay input/foreground readiness.
- Handler: `show_monitor_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_NEXT_INFERENCE

- Signature: `SHOW_NEXT_INFERENCE()` (reviewed_contract)
- Summary: Read the queued one-turn plan and its content fingerprint without changing it.
- Handler: `show_next_inference_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read the queued one-turn plan and its content fingerprint without changing it.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_inference_plan_result_v1`
- Receipt field: `inference_plan_results`
- Verification: Detached before/after queued plans and content fingerprints. A queued plan is not proof of provider acceptance; model compatibility normalization still applies.
- Failure policy: Reject malformed batches before effects. Stop the batch tail on execution failure; do not replay uncertain outcomes.

### SHOW_OPERATOR_RISK_SUMMARY

- Signature: `SHOW_OPERATOR_RISK_SUMMARY()` (help_text)
- Summary: Display the Window 18 read-only risk digest for cost/model spend, desktop/game actions, model-visible context, command insertion/execution, Responses/stateful transport, and operator access/auth without changing settings.
- Handler: `show_operator_risk_summary_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_OVERLAY

- Signature: `SHOW_OVERLAY()` (help_text)
- Summary: Display the current overlay/grid settings.
- Handler: `show_overlay_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PENDING

- Signature: `SHOW_PENDING()` (reviewed_contract)
- Summary: Inspect held command identities, queue version, state and recovery evidence.
- Handler: `show_pending_commands_command`
- Binding: runtime
- Aliases: SHOW_PENDING_COMMANDS
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### SHOW_PENDING_COMMANDS

- Signature: `SHOW_PENDING_COMMANDS()` (reviewed_contract)
- Summary: Inspect held command identities, queue version, state and recovery evidence.
- Handler: `show_pending_commands_command`
- Binding: runtime
- Aliases: SHOW_PENDING
- Parameter validation: pre_dispatch
- Effects: Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_pending_command_result_v1`
- Receipt field: `pending_command_results`
- Verification: Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart.
- Failure policy: Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.

### SHOW_PORTAL_COMPANION_INTAKE

- Signature: `SHOW_PORTAL_COMPANION_INTAKE()` (help_text)
- Summary: Display the Window 22 read-only Portal companion-intake viewer/registry surface without Portal calls, polling, receipt writes, source reads, or automation.
- Handler: `show_portal_companion_intake_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_AUDIT

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_AUDIT()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_AUDIT().
- Handler: `show_portal_intake_audit_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_AUDIT
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_CLOSURE

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_CLOSURE()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_CLOSURE().
- Handler: `show_portal_intake_closure_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_CLOSURE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_DOCKET

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_DOCKET()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_DOCKET().
- Handler: `show_portal_intake_docket_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_DOCKET
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_GATES

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_GATES()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_GATES().
- Handler: `show_portal_intake_gates_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_GATES
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_HANDOFFS

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_HANDOFFS()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_HANDOFFS().
- Handler: `show_portal_intake_handoffs_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_HANDOFFS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_PARKING

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_PARKING()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_PARKING().
- Handler: `show_portal_intake_parking_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_PARKING
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_PROOF

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_PROOF()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_PROOF().
- Handler: `show_portal_intake_proof_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_PROOF
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_REGISTRY

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_REGISTRY()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_REGISTRY().
- Handler: `show_portal_intake_registry_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_REGISTRY
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_REPORT

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_REPORT()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_REPORT().
- Handler: `show_portal_intake_report_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_REPORT
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_REVIEW

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_REVIEW()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_REVIEW().
- Handler: `show_portal_intake_review_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_REVIEW
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_UNBLOCKERS

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_UNBLOCKERS()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_UNBLOCKERS().
- Handler: `show_portal_intake_unblockers_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_UNBLOCKERS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_COMPANION_INTAKE_WAITLIST

- Signature: `SHOW_PORTAL_COMPANION_INTAKE_WAITLIST()` (help_text)
- Summary: Alias for SHOW_PORTAL_INTAKE_WAITLIST().
- Handler: `show_portal_intake_waitlist_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_INTAKE_WAITLIST
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE

- Signature: `SHOW_PORTAL_INTAKE()` (help_text)
- Summary: Alias for SHOW_PORTAL_COMPANION_INTAKE().
- Handler: `show_portal_companion_intake_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_AUDIT

- Signature: `SHOW_PORTAL_INTAKE_AUDIT()` (help_text)
- Summary: Display the Window 22 local acceptance audit matrix: what is proved, waiting, missing, or blocked before live reads/proof/submission/mutation.
- Handler: `show_portal_intake_audit_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_AUDIT
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_CLOSURE

- Signature: `SHOW_PORTAL_INTAKE_CLOSURE()` (help_text)
- Summary: Display the Window 22 parked closure audit proving the local intake window is safely paused pending upstream evidence.
- Handler: `show_portal_intake_closure_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_CLOSURE
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_DOCKET

- Signature: `SHOW_PORTAL_INTAKE_DOCKET()` (help_text)
- Summary: Display the Window 22 promotion evidence docket: who owns each missing proof item before later gates may move.
- Handler: `show_portal_intake_docket_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_DOCKET
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_GATES

- Signature: `SHOW_PORTAL_INTAKE_GATES()` (help_text)
- Summary: Display the Window 22 local intake gate board: what is ready, parked, or blocked before live reads, proof, receipt submission, or mutation.
- Handler: `show_portal_intake_gates_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_GATES
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_HANDOFFS

- Signature: `SHOW_PORTAL_INTAKE_HANDOFFS()` (help_text)
- Summary: Display copy-only external handoff packets for Mac Portal, AGB, Aurora Browser, and the operator without submitting or sending them.
- Handler: `show_portal_intake_handoffs_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_HANDOFFS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_PARKING

- Signature: `SHOW_PORTAL_INTAKE_PARKING()` (help_text)
- Summary: Display the Window 22 parking/resume packet naming why Aurora can pause locally and what evidence would reopen later gates.
- Handler: `show_portal_intake_parking_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_PARKING
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_PROOF

- Signature: `SHOW_PORTAL_INTAKE_PROOF()` (help_text)
- Summary: Display the Window 22 local proof ledger for recorded intake slice validations and the current validation target.
- Handler: `show_portal_intake_proof_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_PROOF
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_REGISTRY

- Signature: `SHOW_PORTAL_INTAKE_REGISTRY()` (help_text)
- Summary: Display the local v0.90 envelope registry/cache contract Aurora needs before any live Portal read path.
- Handler: `show_portal_intake_registry_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_REGISTRY
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_REPORT

- Signature: `SHOW_PORTAL_INTAKE_REPORT()` (help_text)
- Summary: Display the Window 22 copy-only operator report packets for the human operator, Mac Portal, AGB, and Aurora Browser.
- Handler: `show_portal_intake_report_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_REPORT
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_REVIEW

- Signature: `SHOW_PORTAL_INTAKE_REVIEW()` (help_text)
- Summary: Display copy-only readiness review packets for Mac Portal, AGB, Aurora Browser, and the human operator while live reads/proof/submission/mutation remain parked.
- Handler: `show_portal_intake_review_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_REVIEW
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_UNBLOCKERS

- Signature: `SHOW_PORTAL_INTAKE_UNBLOCKERS()` (help_text)
- Summary: Display the Window 22 explicit unblocker checklist for later live-read, peer-card, cross-client proof, receipt, and mutation gates.
- Handler: `show_portal_intake_unblockers_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_UNBLOCKERS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PORTAL_INTAKE_WAITLIST

- Signature: `SHOW_PORTAL_INTAKE_WAITLIST()` (help_text)
- Summary: Display the Window 22 copy-only upstream waitlist for Mac Portal, AGB, Aurora Browser, and future gated work.
- Handler: `show_portal_intake_waitlist_command`
- Binding: runtime
- Aliases: SHOW_PORTAL_COMPANION_INTAKE_WAITLIST
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROGRAM_MAP

- Signature: `SHOW_PROGRAM_MAP(runtime|ui, lite|deep|tree|generated|call_tree|skeleton|control_plane_skeleton|guide|index)` (help_text)
- Summary: Display a mirrored runtime or control-panel map section. control_plane_skeleton is runtime-only.
- Handler: `show_program_map_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_ACTIVATION

- Signature: `SHOW_PROMPT_INCLUSION_ACTIVATION()` (help_text)
- Summary: Display current Prompt Inclusion activation state, offline proof, active Prompt Pin additions, and active do-not-include omissions.
- Handler: `show_prompt_inclusion_activation_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_ACTIVATION_CHECKLIST

- Signature: `SHOW_PROMPT_INCLUSION_ACTIVATION_CHECKLIST()` (help_text)
- Summary: Display the default-off Prompt Inclusion activation review checklist, rollback plan, and future command shape without enabling activation.
- Handler: `show_prompt_inclusion_activation_checklist_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_CLOSURE

- Signature: `SHOW_PROMPT_INCLUSION_CLOSURE()` (help_text)
- Summary: Display Window 19 closure readiness, parked-off posture, proof status, and next roadmap guardrails.
- Handler: `show_prompt_inclusion_closure_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_PREVIEW

- Signature: `SHOW_PROMPT_INCLUSION_PREVIEW()` (help_text)
- Summary: Display the Window 19 no-send activation-plan diff naming which approved Prompt Pins would be added and which approved drop marks would omit content if future activation were enabled.
- Handler: `show_prompt_inclusion_preview_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_READINESS

- Signature: `SHOW_PROMPT_INCLUSION_READINESS()` (help_text)
- Summary: Display the Window 19 preview-only gate for Prompt Pins, do-not-include marks, history writes, sub-agent suggestions, and transport guardrails before any model-visible inclusion is enabled.
- Handler: `show_prompt_inclusion_readiness_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_INCLUSION_REHEARSAL

- Signature: `SHOW_PROMPT_INCLUSION_REHEARSAL()` (help_text)
- Summary: Display the latest Prompt Inclusion preview rehearsal result.
- Handler: `show_prompt_inclusion_rehearsal_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_PROMPT_PINS

- Signature: `SHOW_PROMPT_PINS()` (help_text)
- Summary: Display Prompt Pin preview rows from the Prompt Ledger before any model-visible inclusion is enabled.
- Handler: `show_prompt_pins_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_REFERENCE_PACK

- Signature: `SHOW_REFERENCE_PACK(pack_name)` (help_text)
- Summary: Display a mirrored Aurora reference pack such as pokemon, game_profiles, scheduler, runtime_troubleshooting, ui_troubleshooting, log_fields, memory_retrieval, rehydration, roadmap, codex_cli_windows, prime_agent_harness, codex_chat_continuity_refinement, codex_optionality_turn_controls, aurora_control_plane_cli, aurora_settings_registry, aurora_mcp_readonly, blender_readonly_mcp, or fl_studio_readonly_mcp.
- Handler: `show_reference_pack_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_REFERENCE_TOPICS

- Signature: `SHOW_REFERENCE_TOPICS()` (help_text)
- Summary: Display the mirrored Aurora reference-map topics available to both Codex and Aurora.
- Handler: `show_reference_topics_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_REHYDRATION_STATUS

- Signature: `SHOW_REHYDRATION_STATUS()` (help_text)
- Summary: Display continuity source counts, automatic planning-assist gates, last retrieval/promotion, chat-tail state, and reference-pack readiness.
- Handler: `show_rehydration_status_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RESPONSES_SHADOW_CLOSURE

- Signature: `SHOW_RESPONSES_SHADOW_CLOSURE()` (help_text)
- Summary: Display the Window 17 closure/fallback readiness checklist.
- Handler: `show_responses_shadow_closure_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RESPONSES_SHADOW_OFFLINE_POSTURE

- Signature: `SHOW_RESPONSES_SHADOW_OFFLINE_POSTURE()` (help_text)
- Summary: Display the Window 17 offline token/cost/state posture for the no-send Responses preview.
- Handler: `show_responses_shadow_offline_posture_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RESPONSES_SHADOW_PAYLOAD_PREVIEW

- Signature: `SHOW_RESPONSES_SHADOW_PAYLOAD_PREVIEW()` (help_text)
- Summary: Display the Window 17 no-send Responses payload preview derived from Prompt Ledger rows.
- Handler: `show_responses_shadow_payload_preview_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RESPONSES_SHADOW_PROBE

- Signature: `SHOW_RESPONSES_SHADOW_PROBE()` (help_text)
- Summary: Display the Window 17 operator-armed Responses live-probe scaffold and its no-send guardrails.
- Handler: `show_responses_shadow_probe_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RESPONSES_SHADOW_TRANSPORT

- Signature: `SHOW_RESPONSES_SHADOW_TRANSPORT()` (help_text)
- Summary: Display the Window 17 read-only chat/completions vs Responses comparison contract, readiness blockers, and no-migration guardrails.
- Handler: `show_responses_shadow_transport_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RETRIEVAL_RESULT

- Signature: `SHOW_RETRIEVAL_RESULT(handle[, offset, limit])` (reviewed_contract)
- Summary: Inspect an immutable retained K-set without rescoring or a provider call.
- Handler: `show_retrieval_result_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: read_only

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "handle", "required": true, "type": "string"}`
- Parameter: `{"default": 0, "maximum": 24, "minimum": 0, "name": "offset", "type": "integer"}`
- Parameter: `{"default": 8, "maximum": 24, "minimum": 1, "name": "limit", "type": "integer"}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

### SHOW_RUNTIME

- Signature: `SHOW_RUNTIME()` (help_text)
- Summary: Display the current runtime mode and key toggles.
- Handler: `show_runtime_status_command`
- Binding: runtime
- Aliases: STATUS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_RUNTIME_HEALTH

- Signature: `SHOW_RUNTIME_HEALTH()` (help_text)
- Summary: Display the Window 18 operator health readout that summarizes monitor, state export, queue/bridge, capture, image-index cost, recovery/defaults, auth, and safety guardrail posture without changing settings.
- Handler: `show_runtime_health_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_SECURITY

- Signature: `SHOW_SECURITY()` (help_text)
- Summary: Display the external-operator passcode/authorization state.
- Handler: `show_security_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_STATEFUL_MODEL_PRESETS

- Signature: `SHOW_STATEFUL_MODEL_PRESETS()` (help_text)
- Summary: Display explicit stateful preset profiles and whether they are metadata-only or active.
- Handler: `show_stateful_model_presets_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_TURN_SCHEDULER

- Signature: `SHOW_TURN_SCHEDULER()` (help_text)
- Summary: Display the current turn-scheduler mode, cadence, and last wake reason.
- Handler: `show_turn_scheduler_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_TURN_SCHEDULER_PROFILES

- Signature: `SHOW_TURN_SCHEDULER_PROFILES()` (help_text)
- Summary: Display the named scheduler profiles and their thresholds.
- Handler: `show_turn_scheduler_profiles_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHOW_WINDOW_18_21_CHECKPOINT_READINESS

- Signature: `SHOW_WINDOW_18_21_CHECKPOINT_READINESS()` (help_text)
- Summary: Alias for SHOW_CHECKPOINT_READINESS().
- Handler: `show_window_18_21_checkpoint_readiness_command`
- Binding: runtime
- Aliases: SHOW_CHECKPOINT_READINESS
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SHUTDOWN_RUNTIME

- Signature: `SHUTDOWN_RUNTIME()` (reviewed_contract)
- Summary: Request shutdown, cancel work and release Aurora-owned inputs; report incomplete cleanup.
- Handler: `shutdown_runtime_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Request shutdown, cancel work and release Aurora-owned inputs; report incomplete cleanup.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_input_cleanup_v1`
- Receipt field: `input_cleanup_results`
- Verification: Backend submission only; no proof of application behavior or ownership of physically held human inputs.
- Failure policy: Stop the remaining batch on failure. Failed releases stay tracked for explicit retry; an in-flight native call may defer cleanup to its owner.

### SILENCE_AGENT

- Signature: `SILENCE_AGENT(agent_id, note=...)` (help_text)
- Summary: Silence a sub-agent registry row without deleting history or stopping a worker.
- Handler: `silence_agent_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### STAGE_AGENT_SUGGESTION

- Signature: `STAGE_AGENT_SUGGESTION(suggestion_id|latest|agent_id, note=...)` (help_text)
- Summary: Create a visible Pending Command candidate object while leaving the executable Pending Commands queue untouched.
- Handler: `stage_agent_suggestion_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### STATUS

- Signature: `STATUS()` (help_text)
- Summary: Display the current runtime mode and key toggles.
- Handler: `show_runtime_status_command`
- Binding: runtime
- Aliases: SHOW_RUNTIME
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SUGGEST_AGENT_COMMAND

- Signature: `SUGGEST_AGENT_COMMAND(agent_id, command=..., reason=..., risk=low|medium|high, target=pending_commands)` (help_text)
- Summary: Record a policy-tagged suggestion audit row without Pending Command insertion or execution.
- Handler: `suggest_agent_command_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### SUMMON_AGENT

- Signature: `SUMMON_AGENT(agent_id, role=..., rank=..., urgency=..., allow=..., deny=..., history=private|parent_visible)` (help_text)
- Summary: Add or reactivate a sub-agent registry row without spawning a worker.
- Handler: `summon_agent_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TASKS

- Signature: `TASKS()` (reviewed_contract)
- Summary: Unimplemented legacy placeholder: reports failure and stops the batch tail; does not start inference.
- Handler: `tasks_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: unsupported

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### TOGGLE_ADD_IMSGS_TO_HISTORY

- Signature: `TOGGLE_ADD_IMSGS_TO_HISTORY(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_add_imsgs_to_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_ADD_UMSGS_TO_HISTORY

- Signature: `TOGGLE_ADD_UMSGS_TO_HISTORY(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_add_umsgs_to_history_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_ALWAYS

- Signature: `TOGGLE_ALWAYS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_always_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_AUTO_PROMPT

- Signature: `TOGGLE_AUTO_PROMPT(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_auto_prompt_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_CHAT_HEAD

- Signature: `TOGGLE_CHAT_HEAD()` (help_text)
- Summary: Toggle the floating chat strip open/closed.
- Handler: `toggle_chat_head_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_IMAGE_DETAIL

- Signature: `TOGGLE_IMAGE_DETAIL()` (reviewed_contract)
- Summary: Switch low image detail to high; every other supported detail switches to low. Uses the same runtime setting lock and observed readback.
- Handler: `toggle_image_detail_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Switch low image detail to high; every other supported detail switches to low. Uses the same runtime setting lock and observed readback.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Registered setting: `vision.image_detail`
- Runtime lock: none
- Apply timing: next_image_request
- Related effects: See setting metadata for application timing.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### TOGGLE_IMSGS

- Signature: `TOGGLE_IMSGS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_important_messages_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_IMSGS_DECAY_CHECK

- Signature: `TOGGLE_IMSGS_DECAY_CHECK(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_imsgs_decay_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_LATEST_IMAGE_DETAIL

- Signature: `TOGGLE_LATEST_IMAGE_DETAIL(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_latest_image_detail_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_LIVE_MODE

- Signature: `TOGGLE_LIVE_MODE()` (reviewed_contract)
- Summary: Flip live mode on/off. Uses the same runtime setting lock and observed readback.
- Handler: `toggle_live_mode_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Flip live mode on/off. Uses the same runtime setting lock and observed readback.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.


- Registered setting: `runtime.live`
- Runtime lock: live
- Apply timing: immediate_model_loop_gate
- Related effects: Turning live mode off cancels pending model work; completed actions are not undone.

- Result protocol: `aurora_setting_command_result_v1`
- Receipt field: `setting_results`
- Verification: Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback of raw setters.

### TOGGLE_POWER_WORD

- Signature: `TOGGLE_POWER_WORD(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_power_word`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_UMSGS

- Signature: `TOGGLE_UMSGS(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_unimportant_messages_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### TOGGLE_UMSGS_DECAY_CHECK

- Signature: `TOGGLE_UMSGS_DECAY_CHECK(...)` (placeholder)
- Summary: Inspect the handler; detailed usage has not been reviewed.
- Handler: `toggle_umsgs_decay_check_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UNLOCK_SETTING

- Signature: `UNLOCK_SETTING([lock])` (reviewed_contract)
- Summary: Read locks when omitted; otherwise enable or disable the named runtime setting lock. Settings values are unchanged.
- Handler: `unlock_setting_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Read locks when omitted; otherwise enable or disable the named runtime setting lock. Settings values are unchanged.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"accepted_aliases": {"action": "action", "auth": "auth", "chat-log-echo": "chat_log_echo", "chat_log_echo": "chat_log_echo", "chatlog": "chat_log_echo", "cursor-label": "overlay", "cursor_label": "overlay", "display": "overlay", "echo": "chat_log_echo", "execution": "execution", "init": "live_init", "interval": "screenshot_interval", "keypoint-grid": "overlay", "keypoint_grid": "overlay", "live": "live", "live-init": "live_init", "live_init": "live_init", "model": "models", "models": "models", "overlay": "overlay", "overlays": "overlay", "reasoning": "reasoning", "screenshot-interval": "screenshot_interval", "screenshot_interval": "screenshot_interval", "sound": "sound", "status-overlay": "overlay", "status_overlay": "overlay", "temp": "temperature", "temperature": "temperature", "thinking": "reasoning", "tile-grid": "overlay", "tile_grid": "overlay", "time-logging": "time_logging", "time_logging": "time_logging", "timing": "time_logging", "visuals": "overlay"}, "enum": ["auth", "live", "execution", "action", "models", "reasoning", "temperature", "screenshot_interval", "overlay", "live_init", "sound", "time_logging", "chat_log_echo"], "name": "lock", "omitted": "read_current_locks", "required": false, "type": "string"}`

- Result protocol: `aurora_lock_command_result_v1`
- Receipt field: `lock_results`
- Verification: Runtime lock readback under the settings transaction lock; not an access-control boundary.
- Failure policy: Stop the remaining batch after failure; no automatic replay or rollback.

### UPDATE_ACTIVE_QUESTIONS

- Signature: `UPDATE_ACTIVE_QUESTIONS(items)` (help_text)
- Summary: Set the fresh questions Aurora should keep on hand while uncertainty remains high.
- Handler: `update_active_questions_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_CANDIDATE_ALTERNATIVES

- Signature: `UPDATE_CANDIDATE_ALTERNATIVES(items)` (help_text)
- Summary: Set alternative next actions or route ideas worth trying soon.
- Handler: `update_candidate_alternatives_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_CONTEXT

- Signature: `UPDATE_CONTEXT(recent_events)` (help_text)
- Summary: Update recent context and events; separate events with semicolons.
- Handler: `update_context_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_CURRENT_AREA

- Signature: `UPDATE_CURRENT_AREA(area)` (help_text)
- Summary: Set the current area, room, route, or stable location.
- Handler: `update_current_area_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_IMAGE_CONTEXT_METADATA

- Signature: `UPDATE_IMAGE_CONTEXT_METADATA(image_id_or_path, caption="...", ocr="...", tags="tag1;tag2", embedding_ids="id1;id2")` (help_text)
- Summary: Explicitly fill sidecar semantic metadata without making it model-visible.
- Handler: `update_image_context_metadata_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_INVENTORY

- Signature: `UPDATE_INVENTORY(inventory_items)` (help_text)
- Summary: Update your notable inventory; separate items with semicolons.
- Handler: `update_inventory_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_KNOWN_FAILURES

- Signature: `UPDATE_KNOWN_FAILURES(items)` (help_text)
- Summary: Set actions or plans that are currently known to be failing or blocked.
- Handler: `update_known_failures_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_LAST_LANDMARK

- Signature: `UPDATE_LAST_LANDMARK(landmark)` (help_text)
- Summary: Record the most recent stable landmark.
- Handler: `update_last_landmark_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_LOCAL_PATH_PLAN

- Signature: `UPDATE_LOCAL_PATH_PLAN(steps)` (help_text)
- Summary: Set the short-horizon path steps; separate with semicolons.
- Handler: `update_local_path_plan_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_LONG_TERM_CONTEXT

- Signature: `UPDATE_LONG_TERM_CONTEXT(text...)` (reviewed_contract)
- Summary: Replace this horizon's semicolon-delimited items. task_flow joins comma prose; legacy uses the first argument and discloses ignored arguments. Explicit empty text clears it.
- Handler: `update_long_term_context_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: long_term_context

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### UPDATE_MESSAGE

- Signature: `UPDATE_MESSAGE(message_id, revision, text_json_base64url, on|off|keep)` (reviewed_contract)
- Summary: Use the current conversation ID/revision and base64url-encoded JSON text. Stale/missing/ambiguous IDs fail without mutation. Managed protection cannot be changed. Existing timestamp EDIT_MSGS and PIN(text) remain available.
- Handler: `update_message_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: Atomically edit/pin one retained text message through the shared history authority.

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "message_id", "required": true, "type": "string"}`
- Parameter: `{"name": "revision", "required": true, "type": "string"}`
- Parameter: `{"name": "text_json_base64url", "required": true, "type": "string"}`
- Parameter: `{"enum": ["on", "off", "keep"], "name": "pin", "required": true, "type": "string"}`

- Result protocol: `aurora_history_command_result_v1`
- Receipt field: `history_command_results`
- Verification: Before/after history versions and message readback.
- Failure policy: Validate before effects; stale edits stop the raw batch; cancel stale model work on change.

### UPDATE_MID_TERM_CONTEXT

- Signature: `UPDATE_MID_TERM_CONTEXT(text...)` (reviewed_contract)
- Summary: Replace this horizon's semicolon-delimited items. task_flow joins comma prose; legacy uses the first argument and discloses ignored arguments. Explicit empty text clears it.
- Handler: `update_mid_term_context_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: mid_term_context

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### UPDATE_NOTES

- Signature: `UPDATE_NOTES(text)` (reviewed_contract)
- Summary: Replace the semicolon-delimited notes list; explicit empty text clears it.
- Handler: `update_notes_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: notes

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": false}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### UPDATE_PARTY

- Signature: `UPDATE_PARTY(party_status)` (help_text)
- Summary: Update your current party status; provide details for each Pokémon, separated by semicolons.
- Handler: `update_party_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_PINNED_IMMEDIATE

- Signature: `UPDATE_PINNED_IMMEDIATE(text...)` (reviewed_contract)
- Summary: Replace this horizon's semicolon-delimited items. task_flow joins comma prose; legacy uses the first argument and discloses ignored arguments. Explicit empty text clears it.
- Handler: `update_pinned_immediate_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: pinned_immediate_actions

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### UPDATE_PINNED_SHORT_TERM

- Signature: `UPDATE_PINNED_SHORT_TERM(text...)` (reviewed_contract)
- Summary: Replace this horizon's semicolon-delimited items. task_flow joins comma prose; legacy uses the first argument and discloses ignored arguments. Explicit empty text clears it.
- Handler: `update_pinned_short_term_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: pinned_short_term_actions

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"name": "text", "required": true, "type": "string", "variadic": true}`

- Result protocol: `aurora_memory_command_result_v1`
- Receipt field: `memory_command_results`
- Verification: Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee.
- Failure policy: Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.

### UPDATE_RECENT_MOVEMENT_RESULTS

- Signature: `UPDATE_RECENT_MOVEMENT_RESULTS(items)` (help_text)
- Summary: Set recent movement outcomes; separate with semicolons.
- Handler: `update_recent_movement_results_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_ROUTE_BLOCKERS

- Signature: `UPDATE_ROUTE_BLOCKERS(items)` (help_text)
- Summary: Set route blockers or navigation constraints; separate with semicolons.
- Handler: `update_route_blockers_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_ROUTE_INTENT

- Signature: `UPDATE_ROUTE_INTENT(intents)` (help_text)
- Summary: Set the current high-level route or destination intent; separate with semicolons.
- Handler: `update_route_intent_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_STALE_ASSUMPTIONS

- Signature: `UPDATE_STALE_ASSUMPTIONS(items)` (help_text)
- Summary: Set assumptions that may be wrong, outdated, or worth re-checking.
- Handler: `update_stale_assumptions_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_TARGET_AREA

- Signature: `UPDATE_TARGET_AREA(area)` (help_text)
- Summary: Set the intended destination or target area.
- Handler: `update_target_area_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### UPDATE_TRAVEL_HEADING

- Signature: `UPDATE_TRAVEL_HEADING(direction_or_mode)` (help_text)
- Summary: Set the broader travel direction or movement mode.
- Handler: `update_travel_heading_command`
- Binding: runtime
- Aliases: none
- Parameter validation: legacy_handler
- Effects: not_reviewed

### WAIT

- Signature: `WAIT(seconds)` (reviewed_contract)
- Summary: Wait for a finite, non-negative duration in seconds while servicing cancellation and controls.
- Handler: `wait_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: cooperative_delay; cancellation and control servicing remain active

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"finite": true, "minimum": 0, "name": "seconds", "required": true, "type": "number"}`

- Result protocol: `legacy_handler_return`

### WRITE_EPISODIC_SNAPSHOT

- Signature: `WRITE_EPISODIC_SNAPSHOT([reason, tags])` (reviewed_contract)
- Summary: Existing episodic snapshot write/list/lexical-search behavior with complete argument admission and correlated receipts; no inferred persistence or rollback guarantee.
- Handler: `write_episodic_snapshot_command`
- Binding: runtime
- Aliases: none
- Parameter validation: pre_dispatch
- Effects: snapshot_append

Arguments are positional; parameter metadata defines defaults and omitted-value behavior.

- Parameter: `{"default": "manual snapshot", "name": "reason", "type": "string"}`
- Parameter: `{"default": "", "name": "tags", "type": "string"}`

- Result protocol: `aurora_retrieval_result_v1`
- Receipt field: `retrieval_results`

