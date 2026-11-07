# Aurora 2 Runtime Overview

Current additions: recovery archive preview (`aurora_input_recovery.py`), shared release identity (`aurora_control_plane.release_info`), optional durable recovery/reconciliation/readiness, exact-task steering and execution recording/history. Archive preview writes no files or evictions; actual activation remains future work. Read RELEASE_NOTES.md and the public roadmap for current scope. Inventory: 410/180/54/24. Older subsystem notes below describe their original foundations.

Public snapshot: November 6, 2026, release 84, runtime through Implementation 84. **410 bindings / 180 reviewed argument contracts / 54 shared settings / 24 views.** Start with [AI guide](../../README_FOR_AI.md), [release evidence](../../RELEASE_NOTES.md) and [active roadmap](../../docs/notes/aurora_runtime_roadmap.md). Generated catalogs/skeletons describe implemented code; optional future work is kept in the roadmap.

## Main paths

| Responsibility | Implementation entry points |
| --- | --- |
| Runtime/bootstrap | aurora2.py; launch_aurora2.cmd; aurora_preflight.py |
| Operator control | aurora_control_plane.py, aurora_cli.py, aurora_command_protocol.py |
| Discovery/contracts | aurora_command_catalog.py, aurora_command_contracts.py; commands/commands.json |
| Shared settings | aurora_settings_registry.py, aurora_settings_transactions.py; Preview/Apply/Undo |
| Work and inputs | aurora_runtime_work.py, aurora_input_ownership.py |
| Capture | aurora_capture_provenance.py, aurora_capture_geometry.py, aurora_capture_store.py |
| Bounded tasks/readbacks | aurora_task_continuation.py |
| Conversation/history | aurora_conversation.py, aurora_conversation_delivery.py, aurora_delivery_receipts.py, aurora_history_controls.py |
| Recovery | aurora_input_recovery.py, aurora_recovery_reconciliation.py, aurora_recovery_panel.py |
| Execution history | aurora_execution_inspector.py, aurora_execution_evidence.py, aurora_execution_recording.py, aurora_recording_store.py, aurora_recording_browser.py |
| Goals/scenes | aurora_goal_store.py, aurora_gameplay_scene.py |
| Retrieval | aurora_episodic_retrieval.py, aurora_search_query.py, aurora_retrieval_commands.py, aurora_retrieval_results.py |
| Providers | aurora_codex_oauth.py (legacy), aurora_chatgpt_auth.py / aurora_chatgpt_transport.py (Aurora subscription), aurora_subscription_worker.py (optional bounded inference), aurora_responses_reasoning.py |
| Offline console | aurora_validation_console.py, aurora_validation_worker.py, aurora_validation_web/ |

## Flow and evidence

Input enters the shared inbox/admission path, then command preparation/worker execution produces correlated receipts. Settings have observed state/version and supported same-session rollback. Held inputs retain original ownership/routing through cancellation; uncertain cleanup must not be reported as released.

`enqueue_or_execute_command` stamps batch/task/origin request identities. `ingest_command_result` preserves sanitized typed receipts. Optional `CommandReadbacks` selects bounded same-task results for `send_prompt_to_chatgpt`; preparation/submission/response/uncertainty stay distinct. The serialized turn wrapper records local starts and provider-reported usage, with missing values unknown. Discovery scope and legacy continuation remain defaults.

`CaptureService` owns acquisition/request/lifecycle generations. Capture/drawing/persistence carry immutable frames and geometry; publication cannot acknowledge the wrong request or use pre-action pixels as a fresh observation. Optional time/attempt limits default to zero. Active native calls can survive cancellation; hard OS-call interruption is not implemented.

`evaluate_turn_scheduler` respects queue/result/observation boundaries. Optional bounded turn/time admission and readback wakes can continue a visible task without unnecessary periodic waits. New images still require new inference. Optional declared done/wait/approval/error outcomes, command reservations, reported-token thresholds, progress/latency evidence and independent plan/proposal carry policies now share that task authority. They do not independently verify success, hard-limit spending or cancel already admitted work. Optional durable queued-input recovery, cancellation and explicit retry are implemented; full task-state resume remains open.

`auth.subscription_policy=bounded` owns one hidden inference child with read-idle/deadline limits and local cancellation; `legacy` remains default. Complete output is revalidated in the parent. Authentication/catalog preflight stays in the parent under its own timeouts. There is no automatic request replay, billing fallback or claim of provider-side cancellation.

## Memory and compatibility

Recursive goal save/load and nested ID allocation are repaired. Everyday memory commands have scoped receipts, complete argument checks and explicit unchanged/failure states. Advisory hierarchy dispatch and preserved explicit horizons are selectable, with legacy defaults and personal/system profile support. Optional coherent projection, recent-journal ordering, completion annotation and horizon/goal identity are implemented. Granular edits/provenance, fuller horizons/caps and manual-versus-derived preservation remain open. History edit/pin uses revisions; old exact-timestamp commands retain their semantics. Ordinary-message/person/date-range search and deletion are not implied by episodic filtering.

All commands, legacy policies, action modes and valid configurations remain. Feature visibility, enablement, permissions, billing and scheduling are separate. Read current state rather than inferring it from a UI selection or historical log.

## Validation boundary

Earlier ten-minute gameplay used a per-turn test controller. New separate 25-minute and 20-minute runs used Aurora's normal input/capture/inference workers with bounded supervisors and copied game state. The latter verified Parcel/Pokédex and goal completion through Terra low and bounded subscription transport. Interrupted network/setup trials are separately reported; native mixed-DPI input calibration, long-session OAuth recovery and broader website acceptance remain open. No private runtime state, test captures or live credentials ship with this snapshot.

Use the adjacent generated map, call tree, symbol index and function skeletons to locate functions. `tools/generate_aurora_references.py --check` verifies the exported source and references agree.
