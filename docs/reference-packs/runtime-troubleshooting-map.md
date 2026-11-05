# Runtime Troubleshooting Map

## Capture request failed or worker remains blocked (Implementation 43)

Inspect `capture_service.current_failure` (deadline_exceeded/attempts_exhausted), the failed generation/reason/latched limits, `acquisitions_inflight` and `worker_shutdown_survivors`. A terminal request is no longer pending; it is not a successful screenshot or native cancellation. Automatic inference cannot cross its failed observation boundary. Operator text remains usable without the stale image. Request a fresh capture explicitly, or Cancel work to acknowledge the wait; historical last_failure remains inspectable. A native call that never returns may need runtime restart; do not accumulate replacement workers.

`SET_CAPTURE_REQUEST_TIMEOUT(0)` and `SET_CAPTURE_REQUEST_ATTEMPTS(0)` preserve unlimited legacy behavior for future requests. Positive limits are optional and latch; changing them does not extend an existing request. Max-attempt exhaustion also observes the one-second final publication lease, so slow drawing/storage can exhaust it. Active cursor GDI resources now release on all tested success/error paths; this repair alone does not establish the cause of earlier host lag.

## Capture coordinates or foreground image disagree (Implementation 42)

Inspect the exact selected request's `last_prompt_diagnostics.capture_frame.geometry`, not current setting values or the newest background frame. Its `acquired_size`, `image_size`, `crop_bounds`, `image_to_desktop`, `dpi_context` and target HWND/PID/DPI describe that acquisition. `bracketed` means matching pre/post geometry, not atomic capture or proof against occlusion. Unknown geometry is not usable as calibration.

`SET_CAPTURE_GEOMETRY_POLICY(legacy)` restores prior capture/scaling; `SET_CAPTURE_TARGET(foreground)` requires verified geometry and selects the visible window rectangle, clipped to the virtual desktop (including window borders). Target movement/minimization, changed DPI/desktop bounds or mismatched pixel size rejects acquisition. Retry remains pending only within the selected limits; inspect CaptureService.last_error/current_failure and use explicit retry or cancellation. Cursor/overlays are later, game tile overlays are presets, and existing input commands do not automatically apply the transform. Native backend calibration is still an acceptance gate.

## Purpose
- Map common Aurora runtime symptoms to likely causes and the safest next checks.

## Symptom: state snapshot stops updating
- Likely causes:
- control-panel export loop stalled
- runtime hung while still alive
- file write blocked by exception or lock
- Next checks:
- inspect `aurora_control_panel_state.json` mtime
- inspect `aurora_command_execution_log.jsonl` for recent activity
- confirm runtime process is still alive

## Symptom: screenshot path or hash stops changing
- Likely causes:
- screenshot worker stalled or crashed
- emulator view static because wrong window is foreground
- screenshot capture fault injected or recovery in progress
- Next checks:
- inspect latest screenshot path in state export
- inspect monitor log for screenshot worker restart
- inspect gameplay visibility and foreground window

## Symptom: pending queue grows and does not drain
- Likely causes:
- assist/safe mode holding commands
- approval path not running
- raw command or command-family routing drift
- Next checks:
- inspect execution mode and pending queue mode
- inspect pending commands in control panel
- approve or clear pending items deliberately

## Symptom: Aurora feels too chatty or spins too many turns
- Likely causes:
- `per_capture` legacy mode is still active
- `turn_min_gap_seconds` is too low
- hybrid capture wake is firing too aggressively for the current scene
- Next checks:
- inspect `scheduler.mode`
- inspect `scheduler.last_wake_reason`
- inspect `scheduler.capture_counter` versus `scheduler.last_submitted_capture_counter`
- increase `turn_min_gap_seconds` or `turn_capture_wake_debounce_seconds`

## Symptom: Aurora feels too sleepy or delayed between turns
- Likely causes:
- event mode is too sparse for the current workflow
- heartbeat is too long
- capture wake is disabled in hybrid mode
- Next checks:
- inspect `scheduler.mode`
- inspect `scheduler.heartbeat_seconds`
- inspect `scheduler.capture_wake_enabled`
- inspect whether command-result followups are being marked

## Symptom: gameplay visibility is obstructed
- Likely causes:
- Codex/editor/terminal foreground
- VBA-RR dropdown or menu left open
- emulator minimized or not foreground
- stale obstruction text not yet decayed
- Next checks:
- inspect `gameplay.foreground_window`
- inspect `gameplay.visibility_reason`
- run focus recovery path
- dismiss emulator menu with `Esc`

## Symptom: last key updates but game does not move
- Likely causes:
- input dispatched to wrong target
- emulator menu layer intercepted input
- focus recovery succeeded only partially
- Next checks:
- inspect `last_input_focus_ok`
- inspect `last_input_focus_reason`
- verify visible scene changed after the key
- retry one small movement after explicit refocus

## Symptom: process multiplication or orphan processes
- Likely causes:
- launcher wrapper not shutting down cleanly
- control panel or worker restart path drift
- forced stop interrupted cleanup
- Next checks:
- inspect soak report orphan check
- inspect runtime shutdown command path
- verify launched control-panel PID is closed on runtime exit
