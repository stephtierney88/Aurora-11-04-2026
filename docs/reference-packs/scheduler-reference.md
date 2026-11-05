# Turn Scheduler Reference

## Private Implementation 49 — queued artifact ownership

The next bounded-task reservation latches `task.plan_carry_policy` (`carry`, `discard_previous`) and `task.pending_carry_policy` (`carry`, `hold_previous`, `discard_previous`). Both default carry. Operator-only commands `SET_TASK_PLAN_CARRY_POLICY` / `SET_TASK_PENDING_CARRY_POLICY`, shared Advanced/Agent controls/transactions/reset and `AURORA_TASK_PLAN_CARRY_POLICY` / `AURORA_TASK_PENDING_CARRY_POLICY` use one registry. Settings are session-only; they do not rewrite profiles or release existing holds when changed back to carry.

Trusted `task_origin` comes from actor/delivery/command scope and records task/request/batch IDs. No owner is guessed from a source label. Only v1 model/runtime origins with valid bounded task IDs qualify for strict prior-task policies. Operator, unknown/invalid origin and same-task work remain; reserved/uncertain rows remain regardless of policy. Origin follows the current representative; adding support without replacing it does not reassign ownership. This is an explicit workflow policy, not complete isolation for legacy/unattributed data or process workers.

`reserve_task_continuation_for_turn` takes settings → pending → task locks, prepares detached replacements/versions (including legacy identity normalization), then commits before model selection. Same-task turns do not repeat the transition. Existing unchanged row identities survive in-flight acknowledgements. A preparation failure stops with `artifact_transition_failed` before a provider request and leaves stores unchanged. A journal-write failure is recorded in the in-memory transition and does not reverse the committed change or drop the turn.

`task_held` rows are ineligible for automatic approval and ordinary replacement/eviction/scoring mutation. Models cannot approve or clear them. Explicit operator `APPROVE_PENDING` uses existing full admission/reserve/submit receipts; unstarted submissions restore the hold, uncertain submissions stay quarantined. Operator clear remains available. Late prior-task setters/proposal publications reject before mutation under the active strict policy. Discard does not cancel already admitted actions, complete/delete goals, replay work or provide automatic rollback.

`SHOW_TASK_STATUS`/Raw State expose the bounded transition summary and up to 64 ID/disposition records; prompts omit item details. Counts/loss, before/after plan/queue versions, prior/new task IDs and journal status remain explicit. Discarded command/plan text is not copied into this receipt. Implementation 49 (development reference omitted from this snapshot). CP1c durable input recovery is next; full process-worker task authority, same-task durable wait/resume and native acceptance remain open.

## Private Implementation 48 — controller progress and latency

`SHOW_TASK_STATUS()` / `continuation.active_task.progress` reports an `aurora_task_progress_v1` diagnostic ledger for the current bounded task. Full command/request/event collections retain at most 64 entries each; `events_evicted`, `batches_evicted`, `requests_evicted` disclose loss. The prompt receives only compact latest-record/counter data, never those collections. There is no new setting, scheduling gate, permission or completion rule; legacy mode and existing task controls remain.

Command admission records batch/task/origin request and expanded binding count. Controller receipt ingestion records the exact receipt/status. An observation wait binds the affected batch IDs to its observation generation, capture session/lifecycle, requested generation and acquisition boundary. A published frame joins only those matching requirements; a newer wait clears the older frame association for that batch. A prepared inference joins only the exact selected frame ID and actual included readback batch IDs. It does not infer links from nearby timestamps, image hashes or similar text. Image path mismatch leaves selected frame identity unknown.

Latency milliseconds distinguish admission→controller receipt, requested observation→frame publication observed, receipt→frame observed, receipt→readback prepared, frame observed→request prepared, preparation, prepared→submitted, submitted→responded and submitted→terminal. These are local observation boundaries, not direct OS execution duration, provider queue time, network transit alone or visual success. Capture-service monotonic timestamps validate freshness within their own service; they are never subtracted from controller clocks. Missing/negative/nonfinite evidence is null. Receipt-before-frame latency can be unknown if the frame arrived before its delayed receipt.

Task, batch, receipt, capture/observation generations and inference request IDs remain inspectable without raw command arguments, prompt text, file paths, pixels or provider error bodies. Stale task events do not mutate a new task. Request phases cannot regress or replace a terminal cancellation/failure; observer failures increment request `progress_errors` without losing input or retrying a request. Full queue/worker timing, cross-task retention policy and native qualification remain separate follow-ups. Implementation 48 (development reference omitted from this snapshot).

## Private Implementation 47 — optional task budgets

In bounded mode, the operator can configure `SET_TASK_MAX_COMMANDS(20)`, `SET_TASK_MAX_REPORTED_TOKENS(10000)` and `SET_TASK_UNKNOWN_USAGE_POLICY(continue|stop)` before a new task. Commands and tokens default to **0/off**, unknown usage to **continue**. Startup variables are `AURORA_TASK_MAX_COMMANDS`, `AURORA_TASK_MAX_REPORTED_TOKENS`, `AURORA_TASK_UNKNOWN_USAGE_POLICY`. These session-only values latch across model switches at task start; changing configured values affects the next task. The model cannot enlarge them. Agent controls, Switchboard Advanced and Preview/Apply/Undo/reset share the existing registry; no inference, Auto or billing change is implied.

Commands count expanded bindings reserved at automatic admission. One binding may issue several physical inputs. A whole batch must fit; no prefix executes when it exceeds the remaining allowance. Reservations are not refunded after failure, cancellation or uncertain submission. An exactly filled allowance permits the reserved batch to finish and stops the next inference. Direct operator commands and standalone task inspection/outcome reports are exempt. A pending approval's submitted child is automatic work and consumes the budget, even when the approval itself was manual. Unstarted pending proposals remain held for inspection rather than disappearing.

Nested thread-worker submissions carry parent task/request/controller identity. Stale work cannot spend a newer task's allowance. A legacy process worker presented with another controller's budget rejects nested resubmission (`controller_required`); it must not spend a child-local allowance. Already admitted batches still run under existing execution rules. This is not a new process-mode or native acceptance claim. Reservation identities cap at 4096; a positive command budget stops at capacity rather than admitting untracked work. Zero command limits keep the older path and do not create this reservation ledger.

Provider-reported `total_tokens` is charged once per request, before processing its commands. A response reaching the threshold remains a usable/visible reply but launches no commands or automatic action tail. Missing/invalid totals remain unknown; they are not derived from partial counts. `continue` permits more work with unknown coverage; `stop` ends automatic continuation after the first unmetered request, only if a token threshold is positive. The last request can exceed the limit; neither policy caps a bill, cancels remote inference or changes provider billing. A positive token threshold also stops at the 4096-request accounting capacity. Existing cancellation, timeout or failure reasons remain authoritative.

Use `SHOW_TASK_STATUS()` for active versus configured state and typed receipts for reservation outcomes. New operator input starts a new task after a stop; goals, plans and pending work are preserved. Full correlated progress/latency, cross-task carry/discard choices and durable wait/resume remain open. Implementation 47 (development reference omitted from this snapshot).

## Private Implementation 46 — declared task outcomes

Enable `SET_TASK_OUTCOME_REPORTING(on)` as the operator before starting a new bounded task. It defaults off, is latched with task limits, and does not enable inference, Auto or a billing route. The startup equivalent is `AURORA_TASK_OUTCOME_REPORTING=on`; shared Advanced and Agent controls offer Preview/Apply/Undo. `SHOW_TASK_STATUS()` reports configured versus active state. This slice is session-only; saved profile formats are unchanged.

After inspecting evidence, the model can send a standalone `REPORT_TASK_OUTCOME(task-<32hex>, done, "reason and evidence")`; alternatives are `wait`, `approval` and `error`. Use the actual task ID from the prompt/status. All four stop automatic continuation. The `reported_outcome` records outcome/reason, trusted actor, origin request, UTC report time and `verification=reported_not_verified`; status stays `stopped` with a `reported_*` reason. No stored goal is completed and no approval is granted. Repeating an identical actor/outcome/reason is unchanged; conflicting, stale, disabled, cancelled or expired reports fail. Reports cannot reset task budgets.

`SHOW_TASK_STATUS` and `REPORT_TASK_OUTCOME` run in the controller through normal admission/typed receipts, bypassing worker queue state copies. They must be standalone and cannot be pending wrappers. Mixed report/action batches fail before command effects. On a report attempt the response's automatic immediate/pending/focus-recovery tail is suppressed; accepted stops also block later automatic command admission/proposals and scheduler wakes. Manual controls remain. Already admitted work may finish and is not retroactively cancelled. Use existing Pause/Cancel controls when needed.

Goals, pending proposals and one-turn plans remain available. A later operator input starts a new task; an uncleared one-turn plan can apply there under existing consumption rules. Waiting/approval is a terminal declaration for this bounded task, not a durable suspended task or automatic resume. Same-task resume, explicit carry/discard policies, richer progress/latency and operation/usage budgets remain CF2c/CP1c work. Implementation 46 (development reference omitted from this snapshot).

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
