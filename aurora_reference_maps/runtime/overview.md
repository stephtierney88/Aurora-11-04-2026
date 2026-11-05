# Aurora 2 Runtime Overview

Public snapshot: November 5, 2026, release 54, runtime through Implementation 53 plus the GUI subscription-policy snapshot repair. **387 bindings / 157 reviewed argument contracts / 48 shared settings / 24 views.** Start with [AI guide](../../README_FOR_AI.md), [release evidence](../../RELEASE_NOTES.md) and [active roadmap](../../docs/notes/aurora_runtime_roadmap.md). Generated catalogs/skeletons describe implemented code; optional future work is kept in the roadmap.

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
| Goals/scenes | aurora_goal_store.py, aurora_gameplay_scene.py |
| Retrieval | aurora_episodic_retrieval.py, aurora_search_query.py, aurora_retrieval_commands.py, aurora_retrieval_results.py |
| Providers | aurora_codex_oauth.py (legacy), aurora_chatgpt_auth.py / aurora_chatgpt_transport.py (Aurora subscription), aurora_subscription_worker.py (optional bounded inference), aurora_responses_reasoning.py |
| Offline console | aurora_validation_console.py, aurora_validation_worker.py, aurora_validation_web/ |

## Flow and evidence

Input enters the shared inbox/admission path, then command preparation/worker execution produces correlated receipts. Settings have observed state/version and supported same-session rollback. Held inputs retain original ownership/routing through cancellation; uncertain cleanup must not be reported as released.

`enqueue_or_execute_command` stamps batch/task/origin request identities. `ingest_command_result` preserves sanitized typed receipts. Optional `CommandReadbacks` selects bounded same-task results for `send_prompt_to_chatgpt`; preparation/submission/response/uncertainty stay distinct. The serialized turn wrapper records local starts and provider-reported usage, with missing values unknown. Discovery scope and legacy continuation remain defaults.

`CaptureService` owns acquisition/request/lifecycle generations. Capture/drawing/persistence carry immutable frames and geometry; publication cannot acknowledge the wrong request or use pre-action pixels as a fresh observation. Optional time/attempt limits default to zero. Active native calls can survive cancellation; hard OS-call interruption is not implemented.

`evaluate_turn_scheduler` respects queue/result/observation boundaries. Optional bounded turn/time admission and readback wakes can continue a visible task without unnecessary periodic waits. New images still require new inference. Optional declared done/wait/approval/error outcomes, command reservations, reported-token thresholds, progress/latency evidence and independent plan/proposal carry policies now share that task authority. They do not independently verify success, hard-limit spending or cancel already admitted work. Durable queue/task recovery and same-task resume remain open.

`auth.subscription_policy=bounded` owns one hidden inference child with read-idle/deadline limits and local cancellation; `legacy` remains default. Complete output is revalidated in the parent. Authentication/catalog preflight stays in the parent under its own timeouts. There is no automatic request replay, billing fallback or claim of provider-side cancellation.

## Memory and compatibility

Recursive goal save/load and nested ID allocation are repaired. Everyday memory commands have scoped receipts, complete argument checks and explicit unchanged/failure states. Advisory hierarchy dispatch and preserved explicit horizons are selectable, with legacy defaults and personal/system profile support. Coherent projection, entry ownership, fuller horizons/caps and stale-plan reconciliation remain open. History edit/pin uses revisions; old exact-timestamp commands retain their semantics. Ordinary-message/person/date-range search and deletion are not implied by episodic filtering.

All commands, legacy policies, action modes and valid configurations remain. Feature visibility, enablement, permissions, billing and scheduling are separate. Read current state rather than inferring it from a UI selection or historical log.

## Validation boundary

Earlier ten-minute gameplay used a per-turn test controller. New separate 25-minute and 20-minute runs used Aurora's normal input/capture/inference workers with bounded supervisors and copied game state. The latter verified Parcel/Pokédex and goal completion through Terra low and bounded subscription transport. Interrupted network/setup trials are separately reported; native mixed-DPI input calibration, long-session OAuth recovery and broader website acceptance remain open. No private runtime state, test captures or live credentials ship with this snapshot.

Use the adjacent generated map, call tree, symbol index and function skeletons to locate functions. `tools/generate_aurora_references.py --check` verifies the exported source and references agree.
