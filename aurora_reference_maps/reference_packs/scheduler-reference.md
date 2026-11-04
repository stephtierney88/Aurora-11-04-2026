# Turn Scheduler Reference

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
- `turn_heartbeat_seconds`: safety heartbeat so Aurora does not stay silent forever.
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
