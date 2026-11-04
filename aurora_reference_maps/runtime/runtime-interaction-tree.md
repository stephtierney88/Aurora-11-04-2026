# Aurora 2 Runtime Interaction Tree

## Episodic retrieval — Implementation 15

RETRIEVAL_PULL / RECALL / MEM -> _build_retrieval_request -> run_episodic_retrieval -> sanitized JSONL records -> required tag/source filters -> build_embedding_context (cache, bounded transport, coverage, atomic merge) -> _compute_retrieval_candidate (optional relevance gate and age decay) -> existing distribution selection -> preview/state/log. Planning assist uses the same runtime path with unchanged defaults. Explicit promotion remains separate. Cancellation tokens are checked before/after transport and before result publication.

## Local history command flow — Implementation 14

Raw/CLI/panel request -> complete command/argument admission -> execute_history_command -> HISTORY_LOCK + retention gate -> detached plan -> cancel stale model generation and invalidate active Responses -> publish local history -> version/count receipt. A failed derived refresh restores local history and reports retained cancellation; an incomplete provider invalidation reports uncertainty. Reads/exports take a detached snapshot; SAVECH exclusively creates and verifies its text file outside the history lock. history_command_results survive duplicate receipts; history_control publishes the latest result. All original history commands remain. Advanced retention/prompt-state services are next; native testing remains paused.

## Pending command flow — Implementation 13

Raw/CLI/panel -> prepare_command_batch (including nested commands) -> queue_pending_model_command under PendingCommandLedger.mutation -> stable held ID plus frozen route -> SHOW_PENDING / pending_queue snapshot. Approval -> resolve all selectors + optional version -> preflight all selected rows -> reserve IDs/attempts under lock -> release lock -> enqueue/execute -> acknowledge each result. Accepted requests leave the held list and emit correlated execution receipts; unstarted rows stay held, uncertain acknowledgements stay quarantined. Automatic approval shares this path and preserves manual sub-agent gates. Clear removes only matches; replace/scene/outcome maintenance skips reserved/uncertain rows. Legacy independent queued submissions remain; no group rollback or blind replay.

## Defaults operation path — 4B4b

Raw/CLI/panel -> whole-batch command admission -> original defaults handler -> execute_default_profile_command -> shared settings RLock -> validate every profile field/lock -> existing setters -> observed readback -> commit pruning or attempt/verify restoration -> typed default_profile_results -> command log and duplicate delivery. Personal save -> bounded read/classification -> merge unknown extension fields -> destination-local temporary file + fsync -> change check -> replace -> byte readback -> exact temporary cleanup. This is not cross-process CAS or native-effect rollback. Existing reapply remains default; changed_only is an explicit command option.

## One-turn plan path — 4B4a

Raw/CLI/Control Panel input -> prepare_command_batch -> shared inference option validation -> existing queue -> execute_inference_plan_command under SETTINGS_TRANSACTION_LOCK -> detached before/after plan receipt -> command log and deduplicated delivery. Model turn -> resolve_next_inference_plan_for_turn under the same lock -> normal compatibility selection -> inference_plan_id in resolved controls -> existing Chat Completions or opt-in Responses transport. Context-plan fingerprints are separate from settings versions and provider-application evidence. Keep the full command arsenal and existing behavior choices; 4B4b defaults is implemented; 4B4c is implemented; prompt/history controls are next.

## Owned input lifecycle (4B3)

Request identity -> execute_command_entry owner scope -> prepared GB/PYAG action -> frozen native callbacks -> HeldInputLedger lease before down -> timed/indefinite action -> release by lease ID.

Standalone CANCEL_ACTIVE_WORK / RELEASE_HELD_INPUTS overtakes queued commands -> closes command generation -> releases old-generation leases in reverse order -> reports released / pending_operation / release_uncertain. The action worker finishes deferred cleanup after a native call returns. Stale cleanup cannot release a newer lease. Runtime shutdown uses the same service. Receipts and work.held_inputs expose results; repeated request IDs do not replay cleanup. Move/drag performs immediate native moves separated by cooperative waits.


## Opt-in adaptive effort path

```text
assistant completed text -> process_assistant_response -> reviewed one-turn effort policy
  -> command admission/receipt -> next_inference_plan
next model turn -> infer_turn_model_controls -> post_openai_turn_request
  -> ResponsesReasoningSession.prepare -> configuration_update + current user input
  -> existing bounded MODEL_IO worker -> completed final text validation
  -> commit provider ID/effective effort -> ordinary assistant command processing
normal following turn -> explicit effort return if policy differs
stop/history edit -> cancel generation -> reject late completion -> explicit local reset
```

Chat Completions remains default. Only standard Astra/API-key is accepted by the Responses lane. No automatic fallback/replay/compaction/truncation. See the adaptive reasoning reference for history/filter limits.

## Boot to Steady State

`launch_aurora2.cmd`
-> `aurora2.py`
-> `build_cli_parser`
-> `apply_cli_args`
-> `main`
-> initialize directories and bridge files
-> `Context()`
-> `initialize_overlay`
-> `initialize_application`
-> optional `launch_control_panel`
-> start text/screenshot/drawing/command workers
-> steady-state loop

## Steady-State Loop

`main`
-> `monitor_and_restart_processes`
-> `maybe_run_smoke_test_step`
-> `poll_external_reply_bridges`
-> `write_control_panel_state_snapshot`
-> drain worker queues
-> handle user/operator input

## Responsive model I/O and cancellation (September 5)

`send_prompt_to_chatgpt` -> `serialized_model_turn` -> frozen payload/auth packet ->
`post_openai_model_request` -> `BoundedModelIO.call` -> one network-only daemon worker.
While waiting, the main thread runs `service_runtime_control_during_model_wait`:
bridge ingress -> cancellation checkpoint -> command results -> latest processed
capture -> state export. Logical callers keep the synchronous return contract.

A standalone stop follows the ordinary whole-batch authorization and durable
admission path, then `is_urgent_control_command` selects immediate execution through
`execute_command_entry`. `CANCEL_ACTIVE_WORK` invalidates model and command generations;
`SHUTDOWN_RUNTIME` also stops the runtime; `SET_LIVE_MODE(off)` cancels model work and
disables live inference while honoring the live setting lock. Old queued batches
return cancelled receipts with completed steps preserved. A cancelled network result
is discarded; state says draining until the occupied slot is released. Future live
turns remain possible after the one-shot cancel. Native calls already in progress
may finish before their next checkpoint; explicit indefinite holds require release.

`screenshot_capture` -> `drawing_worker` -> `drain_runtime_processed_capture` ->
`persist_runtime_capture` -> `save_capture` -> one no-overwrite image ID -> matching
sidecar/hash/scheduler reference -> history. `take_screenshot` uses the same persistence
function. New IDs are opaque epoch-nanoseconds + UUID stems; legacy paths remain valid.

## External Raw Command Path

`aurora_cli.py`, `aurora2_control_panel.py`, or another producer
-> shared `aurora_control_plane.append_bridge_request`
-> append `aurora_bridge_request_v1` JSONL record to `aurora_external_inbox.jsonl`
-> `poll_external_inbox_messages`
-> strict whole-batch preparation/expansion, then operator security check
-> `validate_command_arguments` / `desktop_command_arguments`: WAIT, 19 desktop actions and 23 registered-setting command names validate before any dispatch; desktop keys/text and shared setting coercion are checked in full
-> classify the batch as a mutation if any prepared command mutates
-> fsync an `aurora_mutation_admission_v1` reservation keyed by normalized `client_id + request_id`
-> exact terminal duplicate: emit a duplicate-suppressed receipt that re-exposes the prior outcome, without dispatch
-> unresolved duplicate: emit explicit uncertain/no-automatic-replay receipt, without dispatch
-> same identity with changed command digest: emit terminal `request_conflict`, without dispatch
-> `enqueue_or_execute_command`
-> queue with frozen prepared commands and cancellation generation, or execute an admitted standalone urgent stop
-> `execute_command_entry` -> `handle_commands`
-> legacy runtime handler, `execute_registered_setting_command` under the transaction lock, or `execute_desktop_command` through one selected backend
-> desktop results distinguish submitted input/observed focus/uncertainty; registered-setting results observe values/versions or report not-started/uncertain failure; either reviewed action family blocks the tail after failure
-> `command_result_failed`: literal false / `success=false` counts as failure; legacy runtime None still means completion without a typed value and its previous continuation policy remains
-> carry `request_id`, `message_id`, `client_id`, `mutation_admission_id`, and `command_digest` through the command worker
-> append correlated `aurora_command_receipt_v1`, retaining `desktop_results`, `setting_results`, `blocked_commands` and cancellation evidence
-> append terminal mutation reconciliation after the ordinary command-result row is durable
-> logs and state snapshot update

CLI and Control Panel waits match the normalized `client_id + request_id` pair in both bridge events and command receipts. Legacy identity falls back to `source` / `message_id`; timestamp-based monitor compatibility does not replace exact client receipt matching. Read-only commands bypass mutation admission and remain repeatable. On restart, a matching terminal command-result row can repair a missing terminal-journal row; a reservation with no durable result remains uncertain and is never automatically replayed.

Desktop terminal duplicates preserve the original typed outcomes and blocked tail. Key sequences checkpoint between inputs and waits; timed holds/chords release in cleanup, partial hold setup attempts rollback, and multi-release attempts all requested releases after one error. This is cleanup, not reversal of earlier application effects. Explicit indefinite holds remain until released. Native calls already in progress may finish before a checkpoint, and failed release remains uncertain. Guarded offline proof verifies routing/receipts/cleanup with fake input, not native app/game effects.

## Operator Shell and Discovery Path

`aurora2.py` runtime/desktop dispatch tables -> static `aurora_command_catalog.build_command_catalog`
-> 335 runtime + 19 desktop entries with aliases, provenance and explicit reviewed coverage
-> repository `tools/generate_aurora_references.py` -> `commands.json` and Markdown/TSV
-> CLI `load_command_catalog` verifies source hashes -> compact discovery or `--detail`
-> MCP `aurora_search_commands` shares filtering, with optional `detail=true`.
GB/PYAG namespace notes do not create callable commands. The generated UI command
reference uses the same inventory; execution continues through ordinary admission.

`aurora shell`
-> load generated `commands.json` (legacy TSV fallback) and typed setting definitions
-> load non-sensitive `aurora_cli_history_v1` rows unless `--no-history`
-> Windows TTY: standard-library line editor provides Tab, arrows, Home/End, and delete; redirected streams use `input()`
-> `commands` / `? query`: offline command/settings discovery
-> `complete`: `aurora_cli_completion_v1` candidates and replacement offsets
-> bare CLI builtin: invoke the one-shot parser locally
-> known runtime/desktop binding or GB namespace input: route through `command` and the External Raw Command Path above
-> unknown raw command: require explicit `command` or `send`
-> append normalized command and client exit code only when the line is non-sensitive

The shell has no operating-system command escape. An interrupted wait warns the operator to inspect receipts/status; it does not retry or replay the request. Shell history is local convenience, while exact receipts, command results, and mutation admission remain authoritative.

## Typed Settings Read Path

Prepared action path: initial action mode -> ordered projection of known mode setters/apply-transaction changes -> canonical command + immutable DesktopActionContext -> complete argument/key/backend validation -> durable admission -> queue -> context-local execution scope -> existing native handler -> desktop_results.action_route. Explicit GB/PYAG meaning and effective key/backend do not change with foreground heuristics or later settings. GB uses confirmed focus even with the PyAutoGUI game backend; release needs no new focus. Unknown profile/rollback mode effects require explicit prefixes or a subsequent mode selector. Original/duplicate/cancelled receipts preserve route evidence.

Registered setting path: registry commands/value aliases or five setting shortcuts -> whole-batch argument validation -> `execute_registered_setting_command` -> `SETTINGS_TRANSACTION_LOCK` -> before observation -> execution-time lock check -> existing handler once -> after observation -> `setting_results` -> original/duplicate receipt. Raw setters query with zero arguments; five shortcuts always write/toggle and accept no arguments. All 22 low-level setters share registry coercion. Raw batches have no CAS/automatic rollback.

Lock path: shared `RUNTIME_LOCK_ALIASES` -> `parse_lock_command_arguments` -> `execute_runtime_lock_command` -> same transaction lock -> observed lock snapshots/versions -> `lock_results`. No-argument lock calls query all locks. Settings values are unchanged.

Transaction path: bounded strict token decode -> `inspect_settings_transaction_request` for static validation -> admission -> existing transaction service with fresh version/lock/readback checks -> preview/apply/rollback receipt. Planner reuses the static validator. A rejected/failed transaction blocks remaining commands. Unexpected service failure becomes `failed_uncertain`; readback versions are included when available. Atomic apply restoration stays inside the transaction service; earlier raw commands are not undone.

`aurora settings list|get|describe|version`
-> `aurora_settings_registry`
-> strict key/alias resolution
-> read `aurora_control_panel_state.json`
-> validate the observed value against the shared type contract
-> attach source path, freshness, scope, maturity, lock, and apply timing
-> compute/report the opaque version when a complete effective snapshot is available
-> return `effective`, `stale`, `last_observed`, `invalid_runtime_value`, or `unavailable`

No command is sent and no setting is mutated in this path. Compatibility defaults come from the runtime-exported `defaults.system_profile` where available.

## Atomic Settings Transaction Path

`aurora settings preview|apply KEY=VALUE...`, `aurora settings rollback HANDLE`, or the Control Panel atomic settings controls
-> require a fresh active runtime snapshot and `expected_version`
-> `aurora_settings_transactions` normalizes the request and encodes the internal wire command
-> correlated external raw-command path
-> `PREVIEW_SETTINGS_TRANSACTION`, `APPLY_SETTINGS_TRANSACTION`, or `ROLLBACK_SETTINGS_TRANSACTION`
-> build the complete registered runtime state under `SETTINGS_TRANSACTION_LOCK`
-> strict schema/scope/key/type/range/duplicate/version/lock validation
-> preview returns projected readback without mutation, or apply invokes the existing registered setter handlers
-> verify effective readback and compute the after-version
-> append a nested `aurora_settings_transaction_receipt_v1` inside the correlated command result
-> successful apply may issue a bounded same-session single-use rollback handle

Rollback requires the handle's expected current version and unchanged after-state, restores registered values plus the six-field scheduler bundle, verifies the result, and consumes the handle. Transactions require a running runtime; they are not persisted or replayed after shutdown.

Control Panel client path:

`Preview Atomic` / `Apply Atomic` / `Rollback`
-> build registered changes and filter semantic no-ops
-> require a fresh effective 22-setting snapshot
-> submit one correlated transaction with the expected version
-> wait for the exact client/request receipt on a background thread
-> drain the result on Tk's refresh loop
-> display version/diff/rejections/readback/rollback metadata
-> refresh on success or version conflict without automatic replay

`Apply Additional` and disclosed profile follow-ups remain independent commands outside the registry. Profile follow-ups are queued only after successful registered apply.

## FL Studio Read-Only Observation Path

FL Studio MIDI scripting lifecycle (`OnInit`, `OnIdle`, `OnProjectLoad`, `OnRefresh`)
-> `fl_studio_device_script._snapshot`
-> `fl_studio_device_script._emit_readback`
-> bounded Aurora-prefixed SysEx on linked `Aurora FL Bridge` MIDI output
-> `FlStudioReadOnlyMcpServer._capture_readback_from_midi`
-> prefix/size/schema/privacy validation, unique temporary file, and atomic fixed `%LOCALAPPDATA%\Aurora\aurora_readback.json`
-> `FlStudioReadOnlyMcpServer.bridge_status`
-> `_cached_bridge_status`: bounded bytes and metadata from the same file handle
-> source capture time plus file-age validation, then freshness/active-state evaluation
-> `fl_studio_observe(client_id, request_id)`
-> terminal `aurora_fl_studio_observation_receipt_v1`

Stale, inactive, or invalid-capture-time readback is unavailable; malformed/oversized/unreadable telemetry returns a failed observation receipt. Missing input or capture timeout is reported separately from any still-fresh cached observation. Rewriting an old snapshot does not renew source freshness. The FL-side path has no MIDI-input callback or filesystem I/O; the full path has no transport/project/plugin mutation, GUI automation, Aurora bridge write, or automatic replay.

## Screenshot to Model/Action Path

`screenshot_capture`
-> writes processed screenshot
-> updates `runtime_state["last_screenshot_path"]`
-> `handle_queued_input`
-> model/review inference selection
-> assistant command proposal
-> pending queue or direct execution
-> outcome logging

## Runtime to UI Path

runtime state
-> `build_control_panel_state_snapshot`
-> `aurora_control_panel_state.json`
-> control panel `refresh_now()`
-> widget rendering and viewer refresh

## Clean Timeout Path

watchdog
-> append raw `SHUTDOWN_RUNTIME()`
-> `poll_external_inbox_messages`
-> reserve shutdown mutation before dispatch
-> `shutdown_runtime_command`
-> `set_agent_running(False)`
-> bounded final worker-result drain writes the terminal command receipt and reconciles the journal before worker termination
-> `main` finally block
-> worker cleanup
-> `terminate_launched_control_panel`
-> process exit
