# Aurora adaptive reasoning

Updated September 6, 2026. Implementation 09 adds an opt-in Astra Responses transport. Chat Completions remains the startup default. This reference describes Aurora's controller, not a mechanism for changing a running Codex inference.

## Queued plan contract — Implementation 11

These existing controls apply to both transports:

- SET_NEXT_INFERENCE() and SET_NEXT_REASONING_EFFORT() inspect without changing state; SHOW_NEXT_INFERENCE() is the explicit read.
- SET_NEXT_INFERENCE(key=value; ...) replaces the whole queued plan. Omitted fields do not carry forward. Fields: reasoning_effort, verbosity, summary_mode, image_detail, latest_image_detail, temperature, model, text_model, vision_model, reasoning_model, note, target_turn.
- Existing aliases remain: reasoning, verbosity_level, summary, detail, latest_detail. Equal/colon assignment, separate arguments, semicolons/newlines and quoted values remain supported. Blank fields are omitted; malformed/unknown options and conflicting aliases reject before any batch effects.
- Effort values remain none/minimal/low/medium/high/xhigh/max, subject to the selected model's compatibility rules. Verbosity is low/medium/high; summary is auto/none/brief/detailed; image details remain low/high/auto/original. Temperature is finite 0–2 and retains its two-decimal queued representation.
- target_turn is an integer from 0 through 9223372036854775807. Zero/omission selects the next turn; future targets wait and past targets are due at the next resolution. A note-only plan remains available.
- SET_NEXT_REASONING_EFFORT(effort, optional_note) replaces the queued plan with that one-turn effort. CLEAR_NEXT_INFERENCE() clears it; both read and clear remain available with setting locks enabled.
- Model/reasoning/temperature writes, replacement and consumption serialize with the shared settings lock. A concurrent consume cannot erase a newer plan. Failed writes retain observed state and block the remaining command batch.
- Receipts carry inference_plan_results (aurora_inference_plan_result_v1), including requested options, before/after queued plans and content fingerprints, success/effect status and reason. Unique plan_id follows the consumed override as inference_plan_id in resolved model controls. Duplicates retain original evidence without requeueing.
- A plan is consumed when turn controls resolve. A later provider failure does not automatically replay it. Queued-state evidence does not prove provider acceptance; inspect effective model controls as well.

All original commands, session defaults, saved profiles, reasoning modes and transport choices remain. Read docs/notes/aurora_capability_compatibility.md before future simplification; AI-facing breadth and searchable Advanced controls are intentional. Evidence: docs/reviews/2026-09-06/implementation-11.md.

## Operator workflow

Use existing API-key authentication and choose `gpt-6-astra` for text, vision and reasoning model roles. Select `responses` in the Control Panel's Transport field, or use `SET_MODEL_TRANSPORT(responses)`. This session setting does not turn Live on and is not saved in personal/system defaults. Existing live, execution, authorization and setting locks still apply.

For a predictable low/high/low demonstration, set session and battle effort to low and disable automatic dynamic inference and review/critique cadence. During ordinary operation the configured policy can select a different effort; the controller restores that policy, not an unconditional low setting.

```text
SHOW_MODEL_STATUS()
SET_NEXT_REASONING_EFFORT(high, difficult puzzle)
SHOW_NEXT_INFERENCE()
```

The next model turn consumes the override. The following turn sends an explicit effort update if its normal policy differs. A valid assistant-issued `SET_NEXT_REASONING_EFFORT` can proceed in assist or auto mode while reasoning is unlocked; safe mode holds it. The policy still holds broader model/session settings for review. Invalid arguments reject the whole batch; a failed effort command stops its batch tail. No-argument calls inspect the current plan.

Use `RESET_RESPONSES_SESSION()` between requests after an uncertain failure, an explicit history edit, an intervening Chat Completions turn, or a context-budget stop. It clears local continuation IDs, starts the next request from current Aurora context, and does not replay a prior request or delete provider-side history. It respects the reasoning lock and rejects active/draining requests. Returning to Chat Completions uses `SET_MODEL_TRANSPORT(chat_completions)`; transport selection itself is reversible and does not clear the chain.

## Request and state contract

`aurora_responses_reasoning.py` owns one process-local conversation with `previous_response_id` and `store=true`. It accepts exactly the currently documented standard `gpt-6-astra` model and efforts low, medium, high, xhigh, max. Aurora normalizes the existing broader effort controls per model. This first lane has text/image input and completed assistant text output; API tools, multi-agent/pro modes and reasoning summaries are not enabled.

The original request-level `reasoning.effort` remains fixed. `build_reasoning_configuration_update()` emits `{"type":"configuration_update","reasoning":{"effort":"high"}}` before the current user message when selected effort changes. Provider-linked history preserves prior updates. Initial bootstrap may include local recent history; continuations send current snapshots and current text/images without duplicating that history. Snapshot authority roles and image detail are preserved. Latest snapshots and execution receipts supersede older state and proposed commands.

Model Status exposes `responses_reasoning`: request-level effort, effective effort after the last committed response, API-reported effort, selected effort on the pending/last request, continuation ID, generation, completion uncertainty, context/cached-token counts and block reason. The API-reported effort may still equal the original baseline after an update. Cache counts are telemetry, not a promise of savings; the offline fixture's counts are synthetic.

The controller permits one pending request, caps output at 16,384 tokens and request bytes at 32 MiB, stops after a response reports 800,000 input tokens, and uses a 180-second I/O timeout. New input can still exceed provider limits before usage is known; such failures block continuation. No automatic retries, fallback, compaction or truncation are enabled. Incomplete, refused, tool-bearing, malformed and stale responses never reach action execution. Cancellation/history invalidation prevents a late response from committing.

Explicit local history edits invalidate a linked provider session. Ordinary local history retention/decay does not erase already retained provider history. Active Prompt Inclusion/Do-Not-Include enforcement is rejected before send until history-filter parity is implemented. IDs are not restored across process restarts, and provider expiration requires an explicit new session.

## Source map and validation

- `aurora_responses_reasoning.py`: item builder, message converter, final-output parser and `ResponsesReasoningSession.prepare/complete/fail/invalidate/reset/snapshot`.
- `aurora2.py`: `post_openai_turn_request`, `send_prompt_to_chatgpt`, `infer_turn_model_controls`, assistant policy/queue, `set_model_transport`, `reset_responses_session_command`, `invalidate_responses_history`.
- `aurora_settings_registry.py` / `aurora_command_contracts.py`: transport setting and reviewed effort/reset admission. CLI, panel and read-only MCP use the shared catalog/status service.
- `tests/test_aurora_responses_reasoning.py`: controller, policy, admission, cancellation, bounds and output contract tests. `tests/offline_responses_smoke.py`: actual runtime turn/command path with fake provider and native/network guards.
- Evidence: `docs/reviews/2026-09-06/implementation-09.md` and its validation/runtime-proof JSON. No real provider acceptance, measured cache benefit, native GUI or gameplay proof is claimed.

## Follow-up order

4B3 input ownership and 4B4a inference plans are implemented. 4B4b defaults is implemented with retained reapply and optional changed_only. Continue 4B4c pending-command handling and remaining critical mutation services, then 4C measured performance and 4D GUI/install proof. Adaptive-reasoning follow-ups are a bounded live API/text proof and real usage readback, explicit compaction with desired-effort reapplication, prompt-filter/history parity, measured escalation budgets/latency, and fresh-observation checks before delayed physical actions. These do not reopen Browser ownership or deferred OBS proof.

Official API contract checked September 6: [reasoning updates](https://developers.openai.com/api/docs/guides/reasoning#change-reasoning-mid-conversation), [Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [conversation state](https://developers.openai.com/api/docs/guides/conversation-state). Configuration updates work between responses, persist until replaced and preserve the original request prefix; ordinary cache rules still apply. Automatic truncation/compaction and `/responses/compact` are incompatible with retained updates. Explicit `compaction_trigger` is documented but is not implemented in this Aurora slice.
