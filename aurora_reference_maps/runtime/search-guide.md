# Aurora 2 Deep Search Guide

## Semantic retrieval — Implementation 15

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

Query run_episodic_retrieval, _compute_retrieval_candidate, _build_retrieval_request, memory_retrieval_shorthand_command and _update_episodic_embedding_cache_entries in the runtime skeleton. Shared helpers in aurora_episodic_retrieval.py own normalize_retrieval_options, age_time_score, embedding_record_key, parse_embedding_vectors, build_embedding_context and atomic_write_cache. SHOW_REFERENCE_PACK(memory_retrieval) documents ordinal/age modes, the relevance gate and lexical/partial fallback. tests/test_aurora_episodic_retrieval.py is fully offline; the contracts-only runtime smoke checks ingress and state. R2/R3 remain roadmap work.

## Local history lookup — Implementation 14

Query execute_history_command, make_history_control_entry, history_entry_age_minutes, update_chat_history, invalidate_responses_history and _build_history_context_read_state in the runtime skeleton. Query parse_history_arguments, history_exemption, plan_history_change, history_summary, save_history_export and describe_history_contract in the shared skeleton. SEARCH_COMMANDS(CLEAR,high), SEARCH_COMMANDS(SAVECH,high) and SHOW_REFERENCE_PACK(aurora_control_plane_cli) expose commands, optional selection modes and history_command_results. Tests: tests/test_aurora_history_controls.py and the guarded contracts-only runtime smoke. 4B4d local history is implemented; 4B4e retention/prompt-state is next.

## Pending queue lookup — Implementation 13

Query PendingCommandLedger.select/reserve/finish/mutation, parse_pending_selectors and describe_pending_contract in the shared skeleton. Runtime anchors: queue_pending_model_command, get_pending_command_snapshot, evaluate_pending_command_policy, prepare_pending_entry, execute_pending_approval, submit_pending_entry, clear_pending_commands_command and route_assistant_commands. SEARCH_COMMANDS(PENDING,high) exposes all legacy and reviewed controls; SHOW_REFERENCE_PACK(aurora_control_plane_cli) documents selectors, queue modes and pending_command_results. Panel anchors: pending_selection_arguments, render_pending_current, approve_selected_pending and clear_selected_pending. Native GUI acceptance remains paused.

## Defaults lookup — Implementation 12

Query build_runtime_preferences_snapshot, _apply_default_profile, execute_default_profile_command, get_default_profiles_status and set_unchanged_screenshot_persist_interval. Shared helpers live in aurora_default_profiles.py: normalize_profile_snapshot, project_profile_snapshot, profile_lock_keys, read_profile_document, save_profile_document and describe_default_profile_contract. SEARCH_COMMANDS(DEFAULTS,high) and SHOW_REFERENCE_PACK(aurora_settings_registry) explain retained reapply versus optional changed_only and default_profile_results. Implementation 14 is current; 4B4d local history is implemented; retention/prompt-state controls are next.

## One-turn inference lookup — Implementation 11

Query runtime symbols get_next_inference_plan_snapshot, execute_inference_plan_command, set_next_inference_plan_from_pairs, clear_next_inference_plan, resolve_next_inference_plan_for_turn and infer_turn_model_controls. Query shared symbols parse_inference_plan_arguments, normalize_next_inference_pairs, inference_plan_version and describe_inference_plan_contract. SEARCH_COMMANDS(NEXT_INFERENCE,high) and SHOW_REFERENCE_PACK(adaptive_reasoning) expose the four controls; receipts contain inference_plan_results. Capability reminder: docs/notes/aurora_capability_compatibility.md. 4B4a–d are implemented; retention/prompt-state controls are next.

## Comparative harness research lookup

Read docs/reviews/2026-09-06/agent-harness-survey.md and its source inventory for RLM/REPL, progressive discovery, evidence handles and optionality candidates. SHOW_REFERENCE_PACK(prime_agent_harness), SHOW_REFERENCE_PACK(codex_optionality_turn_controls) and SHOW_REFERENCE_PACK(roadmap) lead to the existing design notes. Query runtime symbols search_commands_command, show_reference_pack_command, build_episodic_planning_context_message, _build_agent_private_history_row and _build_prompt_context_ledger_snapshot; query shared symbols build_command_catalog and HeldInputLedger. Research candidates have no fabricated function-skeleton entries. Implementation 14 is current; 4B4d local history is implemented; retention/prompt-state controls are next.

## Held-input lookup

Query the shared skeleton for HeldInputLedger.acquire/release/release_requested/cancel_through and cooperative_move. Query runtime symbols input_key_callbacks, acquire_key_input, acquire_mouse_input, release_input_leases, release_owned_key, cancel_command_inputs, show_held_inputs_command, release_held_inputs_command and execute_command_entry. SHOW_REFERENCE_PACK(held_inputs) documents commands, retained capabilities, failure recovery and limits.


## Adaptive reasoning lookup

Search `aurora_responses_reasoning.py` for `build_reasoning_configuration_update`, `responses_input_messages`, `completed_response_text`, and `ResponsesReasoningSession`. In the runtime skeleton, locate `post_openai_turn_request`, `infer_turn_model_controls`, `evaluate_assistant_command_policy`, `set_model_transport`, `reset_responses_session_command`, and `invalidate_responses_history`. Query commands `SET_MODEL_TRANSPORT`, `RESET_RESPONSES_SESSION`, `SET_NEXT_REASONING_EFFORT`; open `SHOW_REFERENCE_PACK(adaptive_reasoning)` for the complete operating contract.

For current state, read `C:/Users/YourName historical handoff sections are on-demand context.

Use these `rg` targets before opening large code blocks:

- Startup and config:
  `build_cli_parser`
  `apply_cli_args`
  `build_startup_config_snapshot`
  `main`
- State export and control-panel bridge:
  `build_control_panel_state_snapshot`
  `write_control_panel_state_snapshot`
  `poll_external_inbox_messages`
  `append_external_message_record`
- Command system:
  `prepare_command_batch`
  `execute_command_entry`
  `is_urgent_control_command`
  `handle_commands`
  `command_dispatch`
- Reviewed contracts and source-backed discovery:
  `wait_duration` / `validate_command_arguments` / `command_result_failed` in `aurora_command_contracts.py`
  `DESKTOP_COMMAND_SPECS` / `parse_desktop_arguments` / `validate_desktop_keys` / `desktop_result` / `describe_command_contract` in `aurora_command_contracts.py`
  `desktop_command_arguments` / `execute_desktop_command` / `handle_commands` / `ingest_command_result` in `aurora2.py`
  `release_desktop_keys` / `send_desktop_key_sequence` / `send_scancode_backend_press` / `send_keyboard_backend_press` for cancellation and cleanup without backend replay
  `build_mutation_decision_receipt` in `aurora_control_plane.py` for retained desktop outcomes and blocked tails
  `REGISTERED_SETTING_COMMANDS` / `setting_command_definition` / `parse_setting_command_arguments` / `describe_setting_command_contract` in `aurora_command_contracts.py`
  `SettingDefinition` / `coerce_setting_value` in `aurora_settings_registry.py` for canonical setting, command/value aliases and bounds
  `observe_registered_setting` / `execute_registered_setting_command` in `aurora2.py` for locked before/after observation and raw-setting outcomes
  `setting_results` through `handle_commands` / `ingest_command_result` / `build_mutation_decision_receipt` for original/duplicate evidence
  `parse_dispatch` / `build_command_catalog` / `load_generated_catalog` in `aurora_command_catalog.py`
  `filter_command_catalog` / `commands_command` in `aurora_cli.py`
  `_tool_search_commands` in `aurora_mcp_server.py`
  `SETTING_SHORTCUT_COMMANDS` / `LOCK_COMMANDS` / `command_failure_stops_batch` in `aurora_command_contracts.py`
  `RUNTIME_LOCK_KEYS` / `RUNTIME_LOCK_ALIASES` / `normalize_runtime_lock_key` in `aurora_settings_registry.py`
  `execute_runtime_lock_command` / `lock_results` in `aurora2.py` and duplicate evidence in `aurora_control_plane.py`

  `DesktopActionContext` / `desktop_action_scope` / `current_desktop_action_context` / `projected_action_mode` in `aurora_command_contracts.py`
  `resolve_desktop_action_context` / `get_game_input_backend` / `send_pyautogui_game_press` in `aurora2.py`
  `desktop_results.action_route` for admitted namespace/backend/effective-key evidence; do not infer routing from foreground windows

- Portable map generation:
  `generate` / `reference_inputs` / `write_catalog` in `tools/generate_aurora_references.py`
  `configure` / `generate_maps` in `tools/aurora_maps/generate_maps.py`
  `Invoke-Regeneration` / `Sync-InstalledSkillReferences` in `regenerate_aurora_skill_refs.ps1`
  Curated maps are repository inputs; installed skill references are optional exports. Skeleton paths are checkout-relative; only explicit contract coverage is authoritative, not AST effect hints.
- Settings transactions:
  `build_registered_settings_runtime_state`
  `execute_settings_transaction_request`
  `_execute_settings_preview_or_apply`
  `_execute_settings_rollback`
  `parse_settings_transaction_command` / `inspect_settings_transaction_request` for side-effect-free wire admission
  `_settings_transaction_command` / `execute_settings_transaction_request` for typed completion and unexpected uncertainty

  `plan_settings_transaction`
- Operator CLI and shell:
  `receipt_matches_request`
  `wait_for_command_receipt`
  `collect_command_receipts`
  `build_operator_status`
  `build_operator_dashboard`
  `format_operator_dashboard`
  `dashboard_command`
  `load_command_catalog`
  `complete_shell_line`
  `append_shell_history`
  `_shell_cli_argv`
  `shell_command`
- Read-only MCP facade:
  `AuroraReadOnlyMcpServer`
  `tool_definitions`
  `resource_definitions`
  `_call_tool`
  `_read_resource`
  `handle_message`
  `run_stdio`
- Blender read-only adapter:
  `BlenderReadOnlyMcpServer`
  `discover_blender_executable`
  `_validate_scene_path`
  `inspect_scene_file`
  `build_inventory`
  `run_stdio`
- FL Studio read-only adapter:
  `FlStudioReadOnlyMcpServer`
  `discover_fl_studio_executable`
  `discover_fl_studio_readback_path`
  `install_device_script`
  `decode_fl_studio_sysex_data`
  `_capture_readback_from_midi`
  `_cached_bridge_status`
  `bridge_status`
  `observation_receipt`
  `_emit_readback`
  `OnInit`
  `OnIdle`
- Cancellation and model transport:
  `CancellationDomain`
  `BoundedModelIO`
  `serialized_model_turn`
  `post_openai_model_request`
  `service_runtime_control_during_model_wait`
  `cancel_active_work_command`
  `drain_runtime_command_results`
- Immutable capture persistence:
  `save_capture`
  `persist_runtime_capture`
  `drain_runtime_processed_capture`
  `write_image_context_sidecar`
- Worker lifecycle:
  `start_process`
  `Context`
  `monitor_and_restart_processes`
- Gameplay and screenshot path:
  `screenshot_capture`
  `handle_queued_input`
  `infer_operating_context`
  `evaluate_assistant_command_policy`
- Shutdown:
  `shutdown_runtime_command`
  `terminate_launched_control_panel`
  `finally:`

## Recommended Reading Order

1. `main`
2. `Context`
3. `monitor_and_restart_processes`
4. `handle_commands`
5. `build_control_panel_state_snapshot`
6. `poll_external_inbox_messages`

## Generated Search Surfaces

- `runtime-symbol-index.tsv`:
  full symbol index with line numbers, heuristic domains, args, return hints, command bindings, and effect hints
- `runtime-function-skeleton.jsonl`:
  one JSON object per runtime class/function/method with args, return style, command aliases, internal-call hints, side-effect hints, and docstring summary
- `control-plane-function-skeleton.jsonl`:
  one JSON object per shared control-plane, typed settings registry, transaction planner/codec, operator CLI, Aurora read-only MCP facade, Blender read-only adapter, or FL Studio read-only adapter/device function in `aurora_control_plane.py`, `aurora_settings_registry.py`, `aurora_settings_transactions.py`, `aurora_cli.py`, `aurora_mcp_server.py`, `blender_readonly_mcp_server.py`, `blender_scene_inventory.py`, `fl_studio_readonly_mcp_server.py`, and `fl_studio_device_script.py`

Skeleton caveat:

- generated skeletons are static AST guides for top-level functions/classes and direct class methods; nested local helper closures/classes are intentionally left out, so inspect the parent function when closure-level behavior matters
- `runtime-generated-map.md`:
  generated domain grouping from the current source
- `runtime-generated-call-tree.md`:
  static call trees for major runtime anchors

Refresh all generated refs:

- `C:/Users/YourName
- force the wrapper refresh with `C:/Users/YourName -Force`; the underlying Python generator itself has no `--force` flag
- watch and regenerate on source edits:
  `C:/Users/YourName -Watch`
