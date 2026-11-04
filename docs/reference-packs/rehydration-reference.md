# Aurora Rehydration Reference

## Purpose
- Give Aurora and operators a compact map for Window 4 rehydration work.
- Keep continuity explainable: rehydration should surface useful context, not become a hidden second brain.
- Treat this as the bridge between live working memory, episodic retrieval, chat/log history, and reference packs.

## Current source surfaces
- Live structured memory:
  - route state, route intent, local path plan, route blockers, recent movement results
  - overarching goals, apriority goals, open task goals, active questions, known failures, candidate alternatives
  - notes, journal, recent context, pinned immediate actions, pinned short-term actions
- Pinned prompt context:
  - `update_pinned_information()` compacts structured memory into the pinned chat entry used by model turns
  - this remains the primary live continuity surface
- Recent chat evidence:
  - `chat_history_tail` appears in exported state and Control Panel views
  - recent chat is evidence, not the main durable memory substrate
- Episodic memory:
  - snapshots live at `aurora_memory/episodic_snapshots.jsonl`
  - embedding cache lives at `aurora_memory/episodic_embedding_cache.json`
  - current store has a real but still small history, so avoid overfitting to noisy snapshots
- Command and bridge logs:
  - `aurora_command_execution_log.jsonl`
  - `aurora_external_bridge_log.jsonl`
  - `aurora_chat_history_log.jsonl`
  - logs are best for auditing and diagnosis, not direct every-turn prompt stuffing
- Reference packs and maps:
  - `SHOW_REFERENCE_TOPICS()`
  - `SHOW_REFERENCE_PACK(pack)`
  - `SEARCH_REFERENCE_PACK(query, pack|all)`
  - `SHOW_PROGRAM_MAP(runtime|ui, section)`
  - `SEARCH_PROGRAM_MAP(query, runtime|ui)`

## Current automatic rehydration
- Pinned structured memory is rebuilt into chat history by `update_pinned_information()`.
- Recent prompt history is selected from bounded recent text and image entries.
- Episodic snapshot writing can happen on periodic and scene-change triggers.
- Bounded episodic planning assist can run on review/critique turns only.
- Planning assist default remains:
  - mode: `review_critique`
  - items: `2`
  - cooldown: `12` inference turns
  - weights: stronger semantic than time, with tag support
- Planning assist messages explicitly warn that current screenshot/runtime state is ground truth and retrieved memories are continuity clues.

## Current explicit/operator-pulled rehydration
- `SHOW_EPISODIC_MEMORY_STATUS()`: inspect snapshot/retrieval/planning-assist state.
- `LIST_EPISODIC_SNAPSHOTS(limit)`: inspect recent snapshots.
- `SEARCH_EPISODIC_SNAPSHOTS(query, limit)`: lexical snapshot search.
- `RECALL(query, optional_k)` / `MEM(query, optional_k)`: shorthand manual episodic retrieval; Aurora reports the equivalent `RETRIEVAL_PULL(...)` form and does not promote anything automatically.
- `RETRIEVAL_PULL(...)`: weighted episodic retrieval with score breakdowns.
- `PROMOTE_EPISODIC_MEMORY(index, target, prefix)`: copy one cached retrieval result into live memory.
- `REF(query_or_pack, optional_pack|all)` / `FIND_REFERENCE(query, optional_pack|all)`: shorthand reference lookup; exact pack names show a pack, other text searches packs.
- `SHOW_REFERENCE_PACK(pack)` and `SEARCH_REFERENCE_PACK(...)`: pull stable project knowledge.
- `UPDATE_NOTES(...)`, route-state update commands, pinned-action update commands, and journal promotion remain the durable live-memory channels.

## Shorthand Examples
- Use `RECALL(route clue, 3)` when you want a quick manual episodic retrieval preview.
- Use `RECALL(query="route clue", k=3, semantic_backend=off)` when you want shorthand with one or two explicit retrieval controls.
- Use `REF(roadmap)` to display the roadmap reference pack.
- Use `REF(queue semantics, roadmap)` to search one reference pack.
- Use `FIND_REFERENCE(rehydration, all)` when the more explicit command name reads better in a handoff or raw command.
- Promotion is still explicit: after a retrieval preview, use `PROMOTE_EPISODIC_MEMORY(index, target, prefix)` if one result should become live memory.

## Rehydration boundaries
- Do not dump raw chat history or raw logs into every turn.
- Do not let vector retrieval replace route state, goals, notes, or pinned actions.
- Do not treat old gameplay memories as truth when the current screenshot/state conflicts.
- Prefer small, scored, explainable retrieval results over large context loads.
- Keep automatic use narrower than manual pull until the operator can see why a memory surfaced.
- Keep Aurora Browser and AGB context operator-pulled unless an active bridge/runtime-control issue requires it.

## Window 4 working plan
- Slice 1: inventory the rehydration surfaces and add this reference pack.
- Slice 2: add an operator-visible rehydration status/readiness surface.
  - show current automatic gates, recent source counts, snapshot count, last retrieval, last promotion, and reference-pack availability
  - make "quiet by design" visible when cooldown/mode/turn type blocks automatic retrieval
  - status: complete via `SHOW_REHYDRATION_STATUS()` and exported `rehydration` state
- Slice 3: improve planning-query construction and source selection.
  - make query ingredients clearer
  - reduce noisy fields
  - prefer route/goals/notes/blockers/current scene over generic chat fragments
  - status: complete; planning-assist queries now prefer structured route/goals/context/scene/blocker/path/movement/notes/recent-context sources before compact turn-prompt text, skip generic `unknown`/`none` values, and export `planning_last_query_source_mix`
- Slice 4: improve explainability in exported state and Control Panel.
  - show why rehydration was used, skipped, or failed
  - expose the source mix and top score parts without bloating the UI
  - status: complete; `rehydration.explainability` exports last outcome, decision, query preview, source mix, backend/count/error, and operator hint, and the Control Panel shows those fields in Overview and Episodic surfaces
- Slice 5: validate with bounded offline smokes.
  - manual retrieval
  - promotion into live memory
  - planning-assist skip/use state
  - reference-pack lookup
  - status: complete; no-model raw-inbox validation proved reference-pack lookup, planning-assist off/ready gates, tagged snapshot write, lexical-only retrieval with embeddings off, promotion into notes, final rehydration status, and clean shutdown
- Optional Slice 6: not needed right now because offline state proved the behavior.

## Current status surface
- `SHOW_REHYDRATION_STATUS()` is cheap and offline-friendly.
- It does not call the model.
- It summarizes:
  - automatic planning assist mode, item count, cooldown, last decision, last query, last count
  - planning query source mix when a planning retrieval has built a query
  - use/skip/fail outcome and operator hint through `rehydration.explainability`
  - snapshot count and latest snapshot timestamp/summary
  - chat-history tail count and latest role/timestamp
  - live memory counts for notes, journal, recent context, route state, pinned actions, goals, and blockers
  - reference-pack names available from the mirrored manifest
  - last promotion target and summary
- `aurora_control_panel_state.json` also exports the same compact data under `rehydration`.

## Near-term best next slice
- Window 4 is completed and checkpointed.
- Window 5 stronger bounded monitors/assertions is complete and checkpointed after closure validation.
- Continue with Window 6 interrupt and queue ergonomics.
- Keep automatic use bounded to review/critique turns when entering later queue/ergonomics work.

## Test posture
- Prefer offline/no-model smokes first.
- Use cheap model tiers only when a model behavior needs direct testing.
- Keep screenshots and gameplay command tests separate from rehydration tests unless the slice explicitly crosses into gameplay.
