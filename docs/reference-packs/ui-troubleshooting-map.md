# UI Troubleshooting Map

## Pending selection correctness — Implementation 13

Pending selected-item Approve/Clear now sends stable item IDs plus the version of the displayed queue. A changed queue is rejected with a receipt instead of targeting a different index. Selection survives refresh when the same ID remains visible. Existing index/risk/category/family/raw selectors and normal/insert/replace modes remain available; old snapshots retain index fallback. Reserved/uncertain state appears beside the mode, and full entries/routes/recovery evidence are available in pending_queue and SHOW_PENDING(). Model/parent authority and sub-agent manual gates remain unchanged. AST/guarded-state verification passes; visible GUI/scaling acceptance is still open under the native-testing pause. See docs/reviews/2026-09-07/implementation-13.md.

## Purpose
- Give Aurora and operators a compact map of common control-panel drift and the safest next checks.

## Current layout and refresh (September 5)
- Runtime pause/cancel/stop/capture stays in the fixed header; each work view and settings pane scroll independently.
- Use `Ctrl+K` or the full-name selector for all 22 views, `Ctrl+,` for settings, and F11 to toggle maximize. Expand settings for broad controls; filter/collapse sections for density. Preferences are presentation-only.
- Unfinished settings edits survive refresh. Use Reload observed to reset the form; Preview Atomic, Apply Atomic and Rollback still use shared correlated receipts.
- Refresh errors show a stale-data warning and retry automatically. `last_error`, `consecutive_errors` and `recoveries` in `_last_refresh_perf` distinguish failures from a stopped runtime. Accepted file revisions and text caches are committed after successful work.
- Dashboard receipt selection reveals full sanitized IDs/results. Wrap detail changes tab/popout presentation; both retain the shared report.
- Final native visual/keyboard/scaling QA remains open after severe user-reported lag during Computer Use. Do not resume desktop capture automatically; hidden Tk/runtime proof passed.

## Symptom: control panel looks alive but data is stale
- Likely causes:
- state file not refreshing
- refresh loop lagging
- runtime export stalled
- Next checks:
- inspect `aurora_control_panel_state.json` mtime
- use `Refresh`
- compare panel values against raw state snapshot

## Symptom: raw command send does nothing
- Likely causes:
- external inbox write path failed
- command parsing rejected the text
- runtime is offline or not polling inbox
- Next checks:
- inspect external inbox file
- inspect command log for parse/dispatch entries
- test a read-only command such as `SHOW_RUNTIME()` and match its client/request IDs to the terminal receipt

## Symptom: screenshot or image-memory viewer drifts
- Likely causes:
- underlying file list changed while browsing
- cached index no longer matches available items
- corrupt image fallback path triggered
- Next checks:
- hit `Refresh`
- check latest screenshot path in state
- verify popout still opens the current item

## Symptom: pending approve or clear is inconsistent
- Likely causes:
- queue changed during refresh
- selection index stale
- execution mode or queue mode changed mid-run
- Next checks:
- refresh queue view
- compare pending count in state
- re-run approve/clear against a known fresh item

## Symptom: chat strip and history pane disagree
- Likely causes:
- local optimistic UI state not yet reconciled with runtime
- chat history tail not refreshed yet
- runtime open/close flag changed elsewhere
- Next checks:
- refresh panel
- inspect `panel.chat_head_open`
- inspect `chat_history_tail`
