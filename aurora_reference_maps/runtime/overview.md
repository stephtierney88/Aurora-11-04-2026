# Aurora 2 Runtime Overview

Public snapshot: November 5, 2026, through Implementation 44. **376 bindings / 146 reviewed argument contracts / 39 shared settings / 24 views.** Start with [AI guide](../../README_FOR_AI.md), [release evidence](../../RELEASE_NOTES.md) and [active roadmap](../../docs/notes/aurora_runtime_roadmap.md). Generated catalogs/skeletons describe implemented code; optional future work is kept in the roadmap.

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
| Providers | aurora_codex_oauth.py (legacy), aurora_chatgpt_auth.py / transport.py (Aurora subscription), aurora_responses_reasoning.py |
| Offline console | aurora_validation_console.py, aurora_validation_worker.py, aurora_validation_web/ |

## Flow and evidence

Input enters the shared inbox/admission path, then command preparation/worker execution produces correlated receipts. Settings have observed state/version and supported same-session rollback. Held inputs retain original ownership/routing through cancellation; uncertain cleanup must not be reported as released.

`enqueue_or_execute_command` stamps batch/task/origin request identities. `ingest_command_result` preserves sanitized typed receipts. Optional `CommandReadbacks` selects bounded same-task results for `send_prompt_to_chatgpt`; preparation/submission/response/uncertainty stay distinct. The serialized turn wrapper records local starts and provider-reported usage, with missing values unknown. Discovery scope and legacy continuation remain defaults.

`CaptureService` owns acquisition/request/lifecycle generations. Capture/drawing/persistence carry immutable frames and geometry; publication cannot acknowledge the wrong request or use pre-action pixels as a fresh observation. Optional time/attempt limits default to zero. Active native calls can survive cancellation; hard OS-call interruption is not implemented.

`evaluate_turn_scheduler` respects queue/result/observation boundaries. Optional bounded turn/time admission and readback wakes can continue a visible task without unnecessary periodic waits. New images still require new inference. Full done/wait/approval/error outcomes, operation/usage limits and durable task recovery remain unfinished.

## Memory and compatibility

Recursive goal save/load and nested ID allocation are repaired. Everyday memory commands have scoped receipts, complete argument checks and explicit unchanged/failure states. Manual horizon preservation and richer horizon options remain open. History edit/pin uses revisions; old exact-timestamp commands retain their semantics. Ordinary-message/person/date-range search and deletion are not implied by episodic filtering.

All commands, legacy policies, action modes and valid configurations remain. Feature visibility, enablement, permissions, billing and scheduling are separate. Read current state rather than inferring it from a UI selection or historical log.

## Validation boundary

The successful ten-minute gameplay run used a bounded test controller with the real parser/admission/subscription transport. Later capture/readback work has guarded production-worker evidence, not equivalent native endurance. Native mixed-DPI input calibration, long-session OAuth recovery and broader website acceptance remain open. No private runtime state, test captures or live credentials ship with this snapshot.

Use the adjacent generated map, call tree, symbol index and function skeletons to locate functions. `tools/generate_aurora_references.py --check` verifies the exported source and references agree.
