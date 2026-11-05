# Turn Scheduler Reference

## Private Implementation 44 — reviewed readbacks and task accounting

The default discovery path remains. Optional `SET_READBACK_SCOPE(reviewed)` adds supported terminal setting/lock/transaction, inference-plan/defaults/pending/history, retained retrieval and goal/memory receipts to bounded-task requests. A successful handler Boolean alone is not fabricated into typed evidence. Only correlated model-origin receipts qualify; operator controls do not autonomously wake a task. Task-flow allows no-argument registered setting queries and SHOW_RETRIEVAL_RESULT, while permanent writes retain review.

`SET_READBACK_WAKE(on)` separately enables immediate follow-up. Scheduler command/result barriers and post-action observation boundaries still apply. Reviewed data bypasses ordinary chat decay/retention intentionally; the exact selected records appear in `last_prompt_diagnostics.command_readbacks`, with task/request/batch IDs, source receipt, content hash and shortening labels. It is a transient request component, not an ordinary retained message or complete Conversation-view manifest.

The session store keeps 64 receipt records, at most 6000 payload characters each; a request selects up to four under a 24000-character record budget plus envelope. Evicted pending evidence is counted. Submission errors/cancellation retain uncertain or not_sent records, never auto-replay; new tasks cannot inherit prior-task pending data. Raw State exports lightweight metadata. Existing command logs retain full source receipts.

`continuation.active_task.accounting` reports observed batches and executed/failed/blocked/cancelled command counts, local request starts/responses/failures, latest IDs/model/frame/readbacks and provider token coverage. known_total is the sum of reported counts, not a full bill; unknown_requests remains explicit. Deduplication covers up to 4096 request/batch identities per task; excess is flagged and counters remain partial without stopping work. No derived total tokens, spend estimate, cache claim, action budget or task-completion inference. Explicit done/wait/approval/error outcomes and operation/usage budgets remain CF2c work. Review (development reference omitted from this snapshot).

## Private Implementation 43 — bounded capture requests

Optional request timeout/attempt settings default zero (unlimited) and latch at request creation. Expiry/final attempt failure preserves a terminal generation; late acquisition/drawing/persistence cannot satisfy it. The scheduler binds the observation to that request generation, blocks automatic continuation after its failure, and admits new operator text without attaching a stale frame. Explicit retry binds a new generation; Cancel acknowledges the wait while retaining historical failure evidence.

`capture_service.acquisitions_inflight` exposes unfinished calls, elapsed time and discard-on-return status. `worker_shutdown_survivors` reports bounded-join survivors. Capture/drawing workers cannot attach themselves to a replacement controller. A native OS call is not forcibly interrupted, and the worker monitor does not create duplicates while it is alive. Shared command/Advanced/profile controls preserve existing cadence and unlimited retry. Review (development reference omitted from this snapshot).

## Private Implementation 42 — frame-specific geometry

`CapturedFrame.geometry` travels with the acquisition stamp through drawing and publication. Default verified geometry captures an explicit primary/virtual/foreground rectangle in a restored per-monitor thread context, rejecting before/after target or dimension mismatch. Drawing resizes once to its actual overlay canvas and records the resulting affine map; verified foreground frames are not recaptured. Sidecars, latest/scheduler frame and selected-request diagnostics carry that same record, and per-image prompt text names its coordinate mapping. Cursor/overlays are later composition; old/imported captures remain unknown.

`capture.geometry_policy=legacy` preserves old grabs/scaling/recapture. `capture.target=legacy_options` preserves flag priority; explicit targets are also selectable. Existing mouse input stays literal and native DPI/backend calibration is not established. Implementation 43 adds optional total deadlines/retry exhaustion and blocked-call diagnostics; hard interruption of a native call remains unimplemented. Backoff/attempt lease alone is not an overall timeout. Native multi-monitor/gameplay acceptance remains paused.

## Private Implementation 37 — optional bounded readback tasks

`SET_TASK_CONTINUATION(bounded)` selects a shared model-turn/time admission budget; `SET_TASK_MAX_MODEL_TURNS(8)` and `SET_TASK_MAX_SECONDS(120)` configure the next task. These settings are operator-only. All model slots/wake reasons consume one task; new operator input can replace a stopped task. Pause/Cancel/failure/limits stop automatic continuation. Time gates request admission and late response commands, not remote completion or already executing actions. `SET_TASK_CONTINUATION(legacy)` preserves prior scheduling.

`SET_READBACK_WAKE(on)` requires bounded mode plus command-discovery context. Model-requested LIST/LOOKUP/SEARCH results wake a text-only follow-up after batch completion and receipts, retaining any required post-action capture boundary. No heartbeat/image is required for a pure readback. Generation acknowledgement happens before dispatch. Memory-only writes do not repeatedly wake turns. Broader typed results, explicit task completion and token/spend budgets remain roadmap work.

`SET_INIT_DELIVERY(system_once)` removes exact duplicate Init request rows when the full text already exists in the base system prompt; stored history stays intact. Legacy duplication is available. Changed/truncated copies stay. Inspect `last_prompt_diagnostics.init_delivery` for counts; those are characters, not tokens or cache savings.

## Private Implementation 35 — continuation boundary

- A scheduled turn acknowledges the selected capture **before** synchronous inference. Background frames and capture requests produced by the response remain eligible for the next turn.
- Command work and unconsumed receipts block a new inference. Default thread queues track unfinished batches through receipt publication; legacy process workers retain queue/scope/result checks.
- An outstanding action/capture follow-up waits for its required processed frame and settle deadline. A capture tick/heartbeat cannot bypass that wait. Explicit operator text can interrupt an observation wait; urgent Pause/Cancel/Shutdown ingress remains independent.
- Typed batch-local desktop outcomes trigger observation after actual/uncertain input, including partial cancellation. Memory-only batches do not reuse persistent last-key fields to cause unnecessary wakes. Old untyped receipts keep the legacy fallback.
- `event` + heartbeat `0` can continue through `REQUEST_SCREENSHOT_CAPTURE(reason,0)`, even for unchanged requested pixels. This was tested with the real scheduler/command worker and synthetic persisted frames; native acquisition time/coordinate correctness and capture-request races remain CF1 work.
- This is not a durable task controller or a bounded-call budget. Discovery/readback-only continuation, strict command/dependency barriers, and task-level stop/error/budget policies remain CF2 work. Existing profiles/modes are retained.

## Purpose
- Explain how Aurora now separates screenshot capture from full model-turn scheduling.
- Preserve the legacy conveyor behavior as an operator-selectable mode.

## Default behavior
- The `balanced` scheduler profile is the default because it works best for visual worlds.
- `balanced` currently maps to `hybrid` mode with moderate wake spacing and a short post-action settle.
- Aurora still captures screenshots on its own cadence.
- Full model turns wake mainly on meaningful events, with an idle capture-change wake as a fallback.
- Review and critique turns remain fixed-cadence planning heartbeats.

## Modes
- `hybrid`: recommended default. Event-driven turns plus a capture-change wake after the image has settled.
- `event`: closest to a Codex-style tool loop. Turns wake on meaningful events plus the safety heartbeat.
- `per_capture`: legacy mode. Every fresh processed screenshot can wake a new turn.

## Profiles
- `balanced`: recommended general-use default. `hybrid` mode, moderate heartbeat, moderate minimum gap, capture wake on, moderate debounce, moderate post-action settle.
- `responsive`: quicker follow-ups when gameplay or desktop state changes rapidly. Lower minimum gap and shorter settle windows.
- `conservative`: quieter and cheaper. Prefers `event` mode with capture-wake disabled and longer gaps.
- `legacy`: reproduces the older conveyor feel by using `per_capture` with near-zero spacing.
- `custom`: not a fixed profile. Aurora infers `custom` whenever live threshold values do not match one of the named presets closely enough.

## Key scheduler settings
- `turn_scheduler_profile`: active named profile or `custom`.
- `turn_scheduler_profile_description`: short operator-facing description of the active profile.
- `turn_scheduler_mode`: active scheduler mode.
- `turn_heartbeat_seconds`: periodic fallback; `0` disables it for explicit event-driven continuation.
- `turn_min_gap_seconds`: minimum spacing between automatic turns.
- `turn_capture_wake_enabled`: whether hybrid mode can wake on a settled capture change.
- `turn_capture_wake_debounce_seconds`: how long a changed capture must settle before waking a turn.
- `turn_scheduler_post_action_settle_seconds`: short settle window after an action result before the next follow-up turn.

## Wake reasons you may see
- `queued_user_input`: operator or tester input is waiting.
- `command_result_followup`: an action finished and Aurora should re-check the world.
- `capture_tick`: legacy per-capture wake.
- `capture_change`: hybrid capture-change wake.
- `heartbeat`: safety heartbeat wake.

## Why this changed
- The old design tied model turns too tightly to screenshot cadence.
- Faster screenshot capture should not always mean more model calls.
- Visual/gameplay environments need a capture loop and a separate planning loop.

## Continuity notes
- Legacy behavior is still available through `per_capture`.
- The scheduler exports its profile, mode, recent wake reason, and counters in `aurora_control_panel_state.json`.
- Control-panel settings and runtime commands both expose the scheduler so operators can switch behavior deliberately.

## Useful commands
- `SHOW_TURN_SCHEDULER()`
- `SHOW_TURN_SCHEDULER_PROFILES()`
- `SET_TURN_SCHEDULER_PROFILE(balanced|responsive|conservative|legacy)`
- `SET_TURN_SCHEDULER_MODE(hybrid|event|per_capture)`
- `SET_TURN_HEARTBEAT_SECONDS(seconds)`
- `SET_TURN_MIN_GAP_SECONDS(seconds)`
- `SET_TURN_CAPTURE_WAKE(on|off)`
- `SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS(seconds)`
- `SET_TURN_POST_ACTION_SETTLE_SECONDS(seconds)`
