# Aurora 2 Control Panel Search Guide

## Episodic query controls

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

Search _episodic_retrieval_segments, send_episodic_retrieval, send_episodic_recall_shorthand, episodic_time_mode_var, episodic_min_relevance_var and Advanced retrieval. Runtime source owns normalization and effective policy. See docs/reference-packs/memory-retrieval-reference.md.

## Adaptive reasoning controls

Search for `model_transport_var`, `model.transport`, `responses_reasoning` and `apply_model_preset`. Transport joins the existing settings transaction; the model-status view distinguishes effective effort from the fixed API baseline. Session reset is available through reviewed raw-command/catalog discovery.

Use these `rg` targets in `aurora2_control_panel.py`:

- presentation helpers in `aurora_panel_layout.py`:
  `clamp_window_geometry`, `monitor_work_areas`, `ScrollablePane`, `FlowBar`, `CollapsibleSection`
- layout, navigation and drafts:
  `_new_work_page`, `_apply_settings_mode`, `_clamp_settings_sash`, `_filter_settings_sections`
  `_focus_view_selector`, `show_tab`, `_sync_setting_var`, `reload_observed_settings`
  `_configure_initial_window_geometry`, `_remember_window_geometry`, `on_close`
- top-level window and refresh:
  `_build_ui`
  `refresh_now`
  `refresh_loop`
- left settings column:
  `_build_settings_card`
  `send_raw`
  `apply_settings`
  `_submit_settings_transaction`
  `_drain_settings_transaction_results`
  `_handle_settings_transaction_result`
  `preview_settings`
  `rollback_settings`
  `show_settings_details`
  `apply_additional_settings`
  `apply_advanced_settings`
  `SETTING_SAFETY_INVENTORY`

Shared settings contract:

- `aurora_settings_registry.py` owns typed metadata/readback/versioning for 22 core settings.
- `aurora_settings_transactions.py` owns complete-batch planning plus preview/apply/rollback contracts for active runtime-session settings.
- Control Panel registered settings use that transaction service. Inspect `build_control_panel_registered_changes`, `filter_changed_control_panel_settings`, `_get_control_panel_settings_snapshot`, and the submit/drain/handle methods for client behavior.
- `Apply Additional` and profile post-commands remain independent; inspect `_build_additional_settings_commands`, `_build_advanced_context_commands`, and `_build_episodic_memory_commands` when moving another control into the registry.
- dashboard tab/popout:
  `_build_dashboard_tab`
  `refresh_dashboard`
  `_is_dashboard_popout_open`
  `toggle_dashboard_popout`
  `open_dashboard_popout`
  `close_dashboard_popout`
- pending tab:
  `_build_pending_tab`
  `approve_selected_pending`
  `clear_selected_pending`
- screenshot viewer:
  `_build_screenshots_tab`
  `open_screenshot_popout`
  `refresh_popout_image`
- image memory viewer:
  `_build_image_memory_tab`
  `open_image_memory_popout`
  `refresh_image_memory_popout`
- notebook structure:
  `_build_overview_tab`
  `_build_dashboard_tab`
  `_build_memory_tab`
  `_build_episodic_tab`
  `_build_command_tab`
  `_build_prompt_ledger_tab`
  `_build_agents_tab`
  `_build_history_context_tab`
  `_build_portal_intake_tab`
  `_build_visual_context_tab`
  `_build_image_context_index_tab`
  `_build_live_harness_tab`
  `_build_responses_shadow_tab`
  `_build_context_files_tab`
  `_build_settings_safety_tab`
  `_build_raw_tab`

Generated search surfaces:

- `ui-symbol-index.tsv`:
  symbol index with line numbers, heuristic UI domains, args, return hints, and effect hints
- `ui-function-skeleton.jsonl`:
  one JSON object per UI class/function/method with args, return style, internal-call hints, side-effect hints, and docstring summary

Skeleton caveat:

- generated skeletons are static AST guides for top-level functions/classes and direct class methods; nested local helper closures are intentionally left out, so inspect the parent function when closure-level behavior matters
- `ui-generated-map.md`:
  grouped UI map generated from the current source
- `ui-generated-call-tree.md`:
  static call trees for core build/refresh/action methods

Refresh all generated refs:

- `C:/Users/YourName
- watch and regenerate on source edits:
  `C:/Users/YourName -Watch`
