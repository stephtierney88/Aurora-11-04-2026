# Memory Retrieval Reference

## Shared command admission — Implementation 21 / R2b2a

RETRIEVAL_PULL, RECALL, MEM, WRITE_EPISODIC_SNAPSHOT, LIST_EPISODIC_SNAPSHOTS and SEARCH_EPISODIC_SNAPSHOTS now validate complete raw arguments before **any** command in the batch executes. Unknown/duplicate options, missing query/filter, invalid Boolean/date constraints and extra snapshot arguments reject the batch. Runtime-dependent conditions (provider availability, stale feedback tokens, filesystem errors) are checked at execution; a failed command stops the remaining tail without undoing prior effects. Existing operator security classification remains unchanged. Query inspection can invoke embeddings and update caches/feedback/results; it is not a promise of zero cost or zero state effects.

The same pure authority, `aurora_retrieval_commands`, is used by static admission and runtime adapters. Execution reads current embedding/model/tag/list defaults again, rather than freezing static fallback defaults. The Control Panel validates its actual serialized query before sending it. Catalog contracts expose named query defaults and choices, with runtime configuration sources identified.

`argument_policy=legacy` is the default: old K/weight/curve/backend clamps and fallbacks remain available. `argument_policy=strict` rejects nonfinite/out-of-range values, fractional K, invalid backend/shape, empty model names and invalid ordinal time anchors before those legacy conversions. K is 1–24; weights/jitter 0–1; time_scale .1–5; center accepts 0–1 or percentage values through 100; spread accepts .05–1 or 5–100 percent. Old search/scorer options still validate in both modes. Explicit weighted-axis normalization and date rules are unchanged. Relative date anchors are resolved at execution and do not reconstruct historical knowledge.

```text
RECALL(rocket, 12, argument_policy=strict, time_weight=0, semantic_backend=off, result_mode=retained)
MEM(rocket, k=99, argument_policy=legacy, semantic_backend=off)
WRITE_EPISODIC_SNAPSHOT("route check", "route;verified")
LIST_EPISODIC_SNAPSHOTS(8)
SEARCH_EPISODIC_SNAPSHOTS("route", 8)
```

The second query retains the old clamp-to-24 behavior. Query receipt `effective` records that resulting K. Snapshot list/lexical-search finite numeric limits retain their truncate/clamp behavior; missing limits use runtime configuration. Nonfinite limits and surplus arguments reject. These conventional snapshot commands remain distinct from scored/retained retrieval.

All six commands return `aurora_retrieval_result_v1` in the existing correlated `retrieval_results` receipt field. Retrieval carries its unique retrieval_id into search state and the retrieval event log; includes parsed requested/effective options, date/filter/count evidence, backend requested/used/coverage/errors, an eight-item preview and optional retained handle. A successful empty search is an explicit zero-result publication. Backend vectors are omitted. Missing backend evidence remains unknown. Failure states distinguish invalid/not_applied, not_published, cancelled and uncertain; cache work and failure-status state updates can precede a failed result publication, and unexpected exceptions do not establish rollback. Cancellation receipts preserve correlation even when the raw batch is cancelled.

Snapshot write receipts contain the returned snapshot ID/timestamp, canonical record SHA-256 and before/after runtime counts; file-write closure is observed, **fsync durability is not verified**. Listing/lexical search return counts and bounded previews, including lexical scores/hits for the latter. A possibly partial write or failure after effects reports uncertainty; prior committed effects are not undone. Static rejection has the existing batch rejection receipt rather than a fabricated execution receipt. Snapshot mutations continue using durable request-ID admission/deduplication; ordinary query retries retain their existing read-command classification and are not promised durable exactly-once execution.

Next R2b2b addresses coherent manual/planning/export publication, serialized/failure-safe snapshot appends and broader promotion/memory authority. Current hashes and counts are observations, not CAS or a cross-editor transaction. No native visual proof, live embedding proof, historical-state reconstruction or new automatic memory policy is claimed.

## Retained K-sets — Implementation 20 / R2b1

The optional `result_mode=retained` keeps the full returned K-set (maximum 24), including complete normalized source records, scores and resolved query/date evidence. The default `legacy` retains the existing eight-item display/promotion preview only. Every old command, scorer, filter, alias and global configuration remains available.

```text
RECALL(rocket, k=12, semantic_backend=off, result_mode=retained)
SHOW_RETRIEVAL_RESULT(rr_<returned 32 hex digits>, 8, 4)
PROMOTE_EPISODIC_MEMORY(9, notes, "route clue", rr_<returned 32 hex digits>)
PROMOTE_EPISODIC_MEMORY(1, notes, "legacy preview")
```

Use the actual handle from `search.retained_result.handle`; the example placeholder is not valid syntax. Inspection offsets are zero-based; promotion indices are one-based. Inspection defaults to offset 0 / limit 8 and permits limits through 24. An offset equal to the returned count yields an empty page; beyond it rejects. The explicit handle never resolves against a later search. Retained selection passes the full summary through existing memory normalization/deduplication/limits; legacy selection continues using the preview summary. Neither path restores live state or automatically promotes anything.

The process-local store allows 32 sets, 8 MiB total, 1 MiB per set and a 30-minute monotonic lifetime. Oldest published sets are evicted for capacity; reads do not renew them. Overlarge sets fail before result/feedback publication; choose a smaller K or legacy mode explicitly. A restart drops every handle. Missing, expired, evicted and foreign handles report unavailable without silent rescoring, fallback or provider access. Retained results can contain stale observations; they are exact evidence of one search, not proof of current world state. A new search's offset still ranges over its live corpus. The handle pages only its returned K-set, not all matches.

Inspection returns `aurora_retained_retrieval_v1`: request (including evaluation time), resolved filter/search counts, full candidates, item indices/IDs and record SHA-256. The handle metadata and readback report canonical batch SHA-256 and capacity/expiry scope. Duplicate legacy snapshot IDs do not alias different content. New snapshots use session-prefixed UUID IDs, while old records remain intact; no predecessor/supersession graph or historical as-of reconstruction is introduced.

SHOW_RETRIEVAL_RESULT and PROMOTE_EPISODIC_MEMORY share strict whole-batch parameter validation, `aurora_retrieval_result_v1` receipts in `retrieval_results`, and stop the batch tail on failure. Mutation replay uses existing durable admission/deduplication. Promotion reports requested arguments, source mode/handle/identity, before/after target count/hash, and applied/unchanged/not_applied/uncertain. Existing aliases remain. Fractional, zero, nonfinite or surplus promotion arguments now reject rather than being silently coerced/ignored. Exceptions after possible writes report uncertainty, not rollback; do not auto-retry with a fresh ID.

Control Panel: choose Retain full results under Search filters. The separate handle field defaults blank (legacy). Use displayed handle explicitly or paste an older handle; automatic refresh does not change that selection. Inspect retained (Chat) requests all returned records through the same read command. The view reports displayed versus returned count. Native visual/scaling acceptance remains paused; command/controller wiring is offline-tested.

Implementation 21 adds reviewed retrieval/snapshot admission and receipts. Remaining R2b2b work includes coherent exported publication, snapshot append concurrency/failure, and wider memory-target mutation/cancellation integration. Retained handle safety is implemented; whole-system serializability and persistent versioned memory are not claimed.

## Date conveniences — Implementation 19 / R2a2

RETRIEVAL_PULL, RECALL and MEM now accept optional `after`, `before`, `date_period` and `date_anchor`. Existing date_start/date_end, scoring/distributions and SEARCH_EPISODIC_SNAPSHOTS behavior remain available. `date_period=none` (default) leaves explicit date controls in use; no new global/default-profile setting is added.

- `date_start` remains inclusive. A date-only `date_end` still includes the entire day; a timestamp end is exclusive.
- `after=2026-11-04` excludes that whole calendar day (starts at the next midnight). `after=2026-11-04T12:00:00Z` strictly excludes that instant. `before=2026-11-04` stops exclusively at that day's midnight; timestamp Before also excludes its instant.
- Use only one lower bound (`date_start` or `after`) and one upper bound (`date_end` or `before`). Ambiguous duplicates and empty/reversed explicit ranges fail. Relative periods cannot be combined with explicit bounds.
- `date_period`: none, today, yesterday, last_24_hours, last_7_days, last_30_days, this_week, last_week, this_month, last_month. Current calendar periods run from local start through the exclusive anchor; yesterday/last_week/last_month cover complete calendar periods. Weeks begin Monday. Rolling last-N periods use exact elapsed hours/days; calendar days honor 23/25-hour DST transitions. A current period at its start may validly be empty.
- `date_anchor` is an ISO date/time in the query timezone or with an explicit offset. Blank resolves once at retrieval execution. Ambiguous/nonexistent local times require an offset; a date alone is not a valid anchor. Paging/feedback with a relative period requires an explicit anchor, preventing silent window changes. Reuse the returned `date_window.anchor_utc`. Existing corpus/scorer changes can still affect offset results; this is not an immutable result cursor.

```text
RECALL(date_period=yesterday, date_anchor=2026-11-04T12:00:00-08:00, timezone=America/Los_Angeles, semantic_backend=off)
MEM(after=2026-11-01T12:00:00Z, before=2026-11-04, timezone=UTC, sort=newest, semantic_backend=off)
RETRIEVAL_PULL(query=rocket, date_period=last_7_days, date_anchor=2026-11-04T12:00:00Z, feedback_mode=skip, semantic_backend=off)
```

Exported search evidence includes `date_window` (resolved UTC/epoch bounds, lower inclusion flag, exclusive end, period, timezone and anchor), plus execution `evaluation_epoch`. Legacy `start_epoch_inclusive` remains correct for inclusive starts; strict After uses `start_epoch_exclusive`. Summaries show resolved windows for the new options. Missing/unparseable record dates fail active date filters. Date-only/filter-only retrieval calls no embedding provider even with `semantic_backend=force`. Date anchors govern filtering; age relevance scoring retains its separate evaluation time. Time-window search still does not reconstruct historical knowledge state (planned V2).

The Control Panel Search filters exposes all four options through the same parser/normalizer for Preview and Recall. Current input/capture/native visual acceptance stays paused; offline date/parser/scorer/panel wiring and guarded command-ingress checks cover this delivery.

## Repeat-search feedback — Implementation 17

Implementation 17 (2026-10-17) adds optional repeat-search feedback before the next date-convenience slice. feedback_mode=off|skip|penalize preserves ordinary searches by default; feedback_factor (0–1, default .25) is a score multiplier per explicit rejection. feedback_action=reject_last marks the previously returned K results using an exact feedback_token; reset clears marks for that query/session. Feedback is bounded in runtime memory (32 query/session entries, 2048 rejected content identities each), not persistent training or probability sampling. Plain repetition never labels results unhelpful. Skip removes marked records before embeddings; penalty modifies ranking contributions, and zero excludes. Query/text/date/tag/source/session define the scope; changing weights, shape or K preserves marks, while changed record content is new evidence. Tokens prevent stale/concurrent batch feedback; failed/cancelled searches do not commit marks. Separate feedback_session values isolate AI operators; panel sessions use their PID.

The panel exposes these controls under Advanced repeat-search feedback, with Batch unhelpful → search next and Reset feedback & search. Existing four-axis scoring, legacy weights, shape/center/spread/jitter, date/text filters and raw commands remain. Penalty requires relevance/legacy ordering; feedback uses offset=0 because exclusions change the pool. Distributions are rank reshaping/jitter, not a calibrated sampling distribution; K is a result count, not implemented semantic clustering. Native GUI/input/capture acceptance remains paused.

```text
RECALL("route clue", feedback_mode=skip, feedback_session=agent-a, k=4)
RECALL("route clue", feedback_mode=skip, feedback_session=agent-a, k=4, feedback_action=reject_last, feedback_token="TOKEN_FROM_LAST_RESULT")
RECALL("route clue", feedback_mode=penalize, feedback_factor=.25, feedback_session=agent-a, sort=relevance)
RECALL("route clue", feedback_mode=skip, feedback_session=agent-a, feedback_action=reset)
```

Each successful enabled search returns `last_retrieval_search.feedback`: mode, factor, token, session, query key, rejection/exclusion counts and limits. A 0.25 factor leaves 25% of the previous score after one rejection, 6.25% after two; 1 leaves rank unchanged. Skipped records never reach embedding requests. Penalties may still return a rejected result when alternatives are scarce; only Skip guarantees exclusion. Restart/eviction forgets feedback; stale tokens explicitly fail. The UI's returned token is tied to the original query/session, so editing filters before marking a previous batch causes a clear mismatch rather than marking unrelated results. Result rows retain pre_feedback_score, feedback_factor and adjusted contribution bars.

## Conventional search — Implementation 16 / R2a1

The semantic `query` still controls ranking with its original meaning. Independent hard filters exclude records before provider requests or scoring. Use `text_filter` for conventional text search; wildcard/Boolean characters in `query` still have their legacy meaning. No person/conversation index is claimed.

| Option | Default | Meaning |
| --- | --- | --- |
| `text_filter` | empty | Required text predicate, ANDed with tags/source/date predicates. |
| `text_mode` | `literal` | `literal` substring, `word` bounded whole text, `phrase` contiguous bounded phrase, `wildcard` one whitespace-delimited token, or `boolean`. All case-insensitive using Unicode casefold; punctuation/spacing otherwise literal. |
| `text_field` | `any` | `summary`, `tags` or both; phrases never span separate tags or fields. Boolean AND may combine hits across fields. |
| `date_start`, `date_end` | empty | ISO date/date-time, either boundary optional. Start inclusive; date-time end exclusive; date-only end includes the entire day. |
| `timezone` | `UTC` | UTC, fixed `±HH:MM` or available IANA name (e.g. `America/Los_Angeles`). Used for naive boundary and legacy record timestamps. |
| `sort` | `legacy` | Legacy retains curve/jitter; `relevance` sorts by base weighted score, `newest`/`oldest` by parsed epoch. Explicit sorts bypass curve/jitter and use snapshot ID then original file ordinal for ties. Missing times last. |
| `offset` | `0` | Skip 0–1,000,000 matched results; existing `k` remains page size 1–24. Nonzero offsets require an explicit sort. |
| `value_encoding` | `legacy` | Existing named values retain old quote-stripping/backslash behavior. `json` decodes JSON-quoted values once; panel uses json. New search fields always decode one JSON quoting layer. |

Boolean precedence is NOT, AND, OR; use explicit operators and parentheses. Double quotes mean exact phrase, while unquoted Boolean terms match whole words and may contain `*`/`?`. Wildcards match within one whitespace-delimited token, including its punctuation; `*` is zero or more characters and `?` one character. Backslash escapes wildcards, operators or grouping characters. Outer command quoting is a separate layer: JSON strings require doubled backslashes and escaped inner quotes. No arbitrary regex is executed. Expressions are bounded to 2,048 characters, 128 tokens and 16 nested levels.

```text
RECALL(text_filter="(rocket OR badge) AND NOT failed", text_mode=boolean, tags_required="route", source_buckets="manual;review", date_start=2026-10-01, date_end=2026-10-16, timezone=America/Los_Angeles, sort=newest, k=4)
RETRIEVAL_PULL(query="route recovery", text_filter="rock*", text_mode=wildcard, date_start=2026-10-01T00:00:00Z, sort=relevance, offset=4, k=4)
MEM(text_filter="secret key", text_mode=phrase, text_field=summary, sort=oldest, semantic_backend=off)
RECALL(text_filter="\\*", text_mode=wildcard, sort=newest)
```

A record's finite, representable `created_at_epoch` is authoritative; otherwise its timestamp is parsed. Naive timestamps use the explicit search timezone. Invalid/missing/ambiguous record dates cannot pass a date predicate; they remain searchable without dates. Ambiguous or nonexistent local query boundaries are errors: supply an offset. Calendar-day ranges follow daylight-saving transitions (23/25-hour days), not a fixed 24-hour assumption. Existing age *scoring* retains its separate host-local fallback for compatibility; date filtering and age scoring are distinct controls.

Empty semantic text is allowed when at least one hard text/date/required-tag/source filter exists. Such filter-only requests make zero embedding calls, including force mode; `min_relevance` must be zero. Blank query without filters remains an error. Use a wildcard `*` to select records with at least one token, or a source/date filter for broader browsing.

Exported `last_retrieval_search` records effective options, inclusive/exclusive epochs, total/eligible/matched/returned counts, offset, next offset and whether the curve applied. Results include hard-match explanations, parsed epoch and source ordinal. The panel retains the eight-item preview/promotion limit and labels it; raw output can return 24. Offset paging is reproducible only while corpus/scoring inputs remain unchanged (age scores can move with time). It is not a snapshot cursor. R2b owns immutable full-result handles, request correlation, whole-batch reviewed contracts and safe full promotion.

Unknown/duplicate named options, invalid filter syntax and bad ranges now fail rather than being ignored. Valid legacy positional query, shorthand K, aliases, scoring, distributions and global profiles remain. `SEARCH_EPISODIC_SNAPSHOTS` remains the original lexical-only command; the new options belong to RETRIEVAL_PULL/RECALL/MEM. Before/after and anchored relative periods are delivered in R2a2 above; person/role/conversation filters require R4's message/log index. Unsupported fields (including regex) return explicit errors.

## Visual workbench and four-axis scoring

The user then requested a more visual Control Panel search surface. Implementation 15 now includes a Visual retrieval workbench: `score_mode=legacy|weighted` (legacy default), four linked Description/Keywords/Time/Ratings dials totaling one, pure-axis and balanced presets, a shared-function rank curve with jitter band, and colored result contribution bars. Weighted mode adds no hidden rating bonus. Its normalized query keys are `description_weight`, `keyword_weight`, `recency_weight`, `rating_weight` (defaults .3/.3/.3/.1); old time/semantic/preferred-tag weights remain active in Legacy. Relevance uses the existing lexical/embedding channel scores, so backend off is lexical. Curves/jitter are rank adjustments, not probability sampling or true temperature. R4 now records the separate message/log index, person/conversation filters, attributed editable topic metadata and later optional sampling/temperature. This GUI currently searches episodic snapshots; native visual/scaling proof is still paused.

```text
RECALL("rocket passcode", score_mode=weighted, description_weight=1, keyword_weight=0, recency_weight=0, rating_weight=0, semantic_backend=off)
RETRIEVAL_PULL(query="rocket passcode", score_mode=weighted, description_weight=.3, keyword_weight=.3, recency_weight=.3, rating_weight=.1, time_mode=age, min_relevance=.1)
```

Weighted mode normalizes the four nonnegative weights to total one and rejects an all-zero vector. Description and keyword channels use the existing max(lexical, shifted-cosine) score; it does not claim a new pure-embedding calibration. The rating axis uses the existing bounded importance/confidence/outcome composite, scaled to 0–1. Required tag/source filters and the relevance gate remain active; preferred-tag weight and semantic tag mix affect Legacy only. Distribution shaping/jitter follows base ranking in both modes. Source authors/persons are not yet indexed.

## Implemented hardening — October 16, Implementation 15

The legacy ranking remains the default: ordinal file-position recency, no minimum relevance, the same lexical/embedding blend, heuristic rating bonus and distribution options. Zero semantic tag mix now means text-only; RECALL/MEM preserve all options and precision. Preview and Recall in the Episodic view share those controls, including a collapsed **Advanced retrieval (this query only)** section. Global settings, existing saved profiles and planning-assist defaults are unchanged.

| Query option | Default | Meaning |
| --- | --- | --- |
| `time_mode` | `ordinal` | Existing relative file order; choose `age` for actual elapsed time. |
| `age_half_life_hours` | `168` | With age mode, score is `2 ** (-age_hours / half_life_hours)`; range 0.001–876000. |
| `min_relevance` | `0` | 0 retains permissive ranking. A positive value gates on the maximum lexical text/tag hit fraction or positive raw cosine, before time/rating bonuses; range 0–1. This is not a probability. |
| `embedding_fallback` | `lexical` | On incomplete `auto` coverage, use lexical only. `partial` explicitly permits available embeddings and reports `embedding_partial`. `force` still requires complete coverage. |
| `semantic_tag_weight` | `0.5` | Existing text/tag semantic mix; zero and one now work as written. |
| `time_anchor`, `time_scale` | empty, `1` | Existing ordinal anchor/scale; an anchor combined with age mode is rejected rather than ignored. |

Age uses `created_at_epoch` first, then ISO/legacy timestamps. A naive legacy timestamp uses the host's local timezone. Missing/invalid times score zero in age mode; future times clamp to age zero and are labeled `future_clamped`. Ordinal recency remains visible separately. The old shifted cosine ranking `(cosine + 1) / 2` is retained; the optional relevance gate uses positive raw cosine so cosine zero does not become evidence of relevance.

```text
RECALL("rocket passcode", 4, semantic_backend=off, semantic_tag_weight=0, time_mode=age, age_half_life_hours=168, min_relevance=0.1)
RETRIEVAL_PULL(query="rocket passcode", semantic_backend=auto, embedding_fallback=partial, time_mode=ordinal, min_relevance=0)
```

Provider responses are mapped by index and require finite, nonzero, dimension-compatible vectors. Content-based internal keys prevent duplicate snapshot IDs from swapping vectors. Tags/buckets filter before embedding; identical text is requested once, in batches of at most 64. There is one locked atomic cache save per retrieval, retaining the existing version-1 model/kind/text keys. Cache-save failure reports a warning while valid in-memory results remain usable; previous disk/global cache content survives a failed replacement. Bad cache vectors are misses. Cached dimension conflicts become explicit incomplete coverage rather than false similarity.

`force` fails on any missing required query/nonempty eligible summary/tag vector. `auto` handles transport/response failures with explicit fallback. Empty or completely filtered stores do not call the provider. Cancellation is rethrown, checked between local phases/batches and before results are published; the existing bounded model-I/O worker still owns transport. No extra retrieval workers are created. A cancellation after a completed cache save may retain reusable cache entries; it does not publish a successful retrieval result.

Results/state/logs expose relevance, time mode/source/age, effective fallback, eligible-record counts and available/required vector coverage. Invalid JSON/non-object rows are skipped; malformed tags/ratings are sanitized for safe scoring. Ratings remain heuristics. New query options are validated; the full older argument/admission family remains legacy and is scheduled for R2.

Remaining R2b2b/R3: coherent publication and append concurrency, skipped-row diagnostics, cache invalidation/retention, total request budgets and indexing, measured relevance/calibration/diversity. Implementation 20 now supplies unique new snapshot IDs and optional full retained K-set inspection/promotion; legacy preview remains eight items/220 characters. Full-file reads and whole-cache serialization still exist, and 64-item batches are not a total cost limit. No live API or native GUI acceptance is claimed. See docs/reviews/2026-10-16/implementation-15.md and the October 16 roadmap section.

## Purpose
- Give Aurora and operators a shared reference for future retrieval-backed memory work.
- Keep the design concrete without pretending the full vector-memory system already exists.

## Current foundation
- Aurora now has a first-pass episodic snapshot layer:
  - periodic compact snapshot writing
  - scene-change snapshot writing
  - manual snapshot writing
  - JSONL-backed inspectable storage at `aurora_memory/episodic_snapshots.jsonl`
  - simple lexical search over stored snapshots
  - optional embedding-backed semantic scoring with cached OpenAI embeddings
- This is still the proving-ground stage. The goal is to observe what Aurora actually writes, how retrieval behaves, and whether the semantic layer improves recall enough to justify a richer embedding-backed system.
- Current command surface:
  - `SHOW_EPISODIC_MEMORY_STATUS()`
  - `SET_EPISODIC_MEMORY(on|off)`
  - `SET_EPISODIC_MEMORY_INTERVAL(seconds)`
  - `SET_EPISODIC_MEMORY_PERIODIC(on|off)`
  - `SET_EPISODIC_MEMORY_SCENE_TRIGGER(on|off)`
  - `SET_EPISODIC_EMBEDDINGS(off|auto|force)`
  - `SET_EPISODIC_EMBEDDING_MODEL(name)`
  - `WRITE_EPISODIC_SNAPSHOT(optional_reason, optional_tags)`
  - `LIST_EPISODIC_SNAPSHOTS(optional_limit)`
  - `SEARCH_EPISODIC_SNAPSHOTS(query, optional_limit)`
  - `RETRIEVAL_PULL(query="...", k=4, time_weight=0.5, semantic_weight=0.5, semantic_backend=off|auto|force, embedding_model="text-embedding-3-small", ...)`
  - `PROMOTE_EPISODIC_MEMORY(item_index, target, optional_prefix)`
- Current retrieval backend is intentionally inspectable:
  - lexical summary matching
  - lexical query-to-tag matching
  - explicit required/preferred tag filters
  - recency or anchored-time score
  - small importance/confidence/outcome bonus
  - optional embedding-backed text and tag similarity using normalized OpenAI embeddings
  - optional shaped rank weighting plus bounded jitter via `distribution_shape`, `distribution_center`, `distribution_spread`, and `variance_bias`
- Embeddings mode currently works like this:
  - `off`: lexical-only semantic scoring
  - `auto`: try embeddings, fall back to lexical if auth/network/model lookup fails
  - `force`: require embeddings for the request to succeed
- Embedding cache entries are stored locally so repeated retrieval over the same snapshot/query text is cheaper and more stable.
- Aurora now also supports a bounded operator/runtime bridge from retrieval into live working memory:
  - promote a cached retrieval item into notes
  - append a journal entry
  - merge a retrieved clue into recent context
  - append into pinned immediate / pinned short-term actions
  - promote to open-goal or overarching-goal buckets
- Aurora also now supports a bounded planning-loop assist:
  - review or critique turns can retrieve a very small number of episodic memories
  - retrieved memories are injected as advisory continuity clues, not as hard truth
  - this path is mode-gated, cooldown-gated, and inspectable in runtime state
- This is intentionally bounded. Promotion is operator-visible and explicit; bounded review/critique planning injection is implemented, while broader autonomous consumption remains later work.

## Recommended staged approach
1. Keep current structured memory (`goals`, `route_state`, `notes`, `journal`, pinned context) as the primary live working memory.
2. Add episodic snapshot writing on bounded triggers:
   - periodic timer
   - meaningful scene change
   - important operator message
   - route milestone
   - battle outcome
   - repeated failure / recovery event
3. Add embedding-backed search over those snapshots.
4. Add explicit promotion/use actions so good retrieved memories can move into live working memory deliberately.
5. Add bounded planning-turn retrieval injection on review/critique turns only.
6. Add cooldown / repeat-suppression tuning so planning retrieval helps without running on every eligible turn.
7. Blend retrieval results back into live context selectively instead of dumping large raw histories.

## Current planning-assist default
- Automatic planning retrieval stays bounded to review/critique turns.
- The gameplay-friendly default cooldown is now 12 inference turns, so Aurora does not inject episodic memory into every routine review during live play.
- Planning-assist queries now prefer structured route/goals/context/scene/blocker/path/movement/notes/recent-context sources before compact turn-prompt text, skip generic `unknown`/`none` values, and expose `planning_last_query_source_mix` for later UI/status explainability.
- `rehydration.explainability` now carries planning-assist use/skip/fail posture, source mix, query preview, and operator hint; the Control Panel Overview and Episodic views display those fields.
- Window 4 validation proved the retrieval/promote path offline: `SHOW_REFERENCE_PACK(rehydration)`, planning-assist off/ready gate checks, tagged snapshot writing, lexical-only `RETRIEVAL_PULL(... semantic_backend=off ...)`, and `PROMOTE_EPISODIC_MEMORY(... notes ...)` all processed through the raw inbox without a model call.
- Manual `RETRIEVAL_PULL(...)` and explicit promotion remain available when the operator wants a targeted memory probe.
- Exported state now reports cooldown remaining, next eligible turn, and turns since the last planning retrieval so "quiet by design" is visible.
- Window 4 has a separate rehydration map at `SHOW_REFERENCE_PACK(rehydration)`, covering how episodic retrieval should work with notes, chat history, pinned context, logs, and reference packs.

## What the current foundation should prove first
- Are the snapshot summaries actually useful, or just noisy compressed state dumps?
- Which triggers create meaningful memories versus clutter?
- Do operators trust the written tags, reason fields, and summary text enough to debug retrieval later?
- Does the lexical plus optional embedding blend surface meaningfully better history than lexical alone?
- Does the score breakdown remain understandable once embeddings are in play?

## Snapshot shape
- `timestamp`
- `summary_text`
- `source_bucket`
- `tags`
- `importance_score`
- `confidence_score`
- `outcome_score`
- optional `scene_type`, `game_profile`, `area`, `landmark`, `goal_id`

## Retrieval dimensions
- `semantic_score`: combined text/tag similarity between the current query and stored memory text/tags
- `time_score`: recency or closeness to a requested time window
- `tag_score`: overlap with required or preferred tags
- `importance_score`: how strongly the memory was marked when stored
- `diversity_bias`: optional spread so retrieval does not always return near-duplicates

## Semantic backend notes
- Aurora currently computes semantic retrieval from two inspectable layers:
  - lexical text and tag similarity
  - embedding text and tag similarity when embeddings are enabled and available
- Aurora keeps those parts visible instead of hiding them in one opaque score:
  - `lexical_text_score`
  - `lexical_tag_score`
  - `embedding_text_score`
  - `embedding_tag_score`
  - `semantic_backend_used`
- The effective semantic text/tag contributions currently use the strongest available signal from lexical or embedding scoring so semantic retrieval can improve without making fallback behavior mysterious.

## Time and score model
- Aurora should treat time as a normalized retrieval signal, for example `0` = oldest retained memory and `100` = newest/current memory.
- Time bias should be able to work in two ways:
  - plain recency bias: "prefer newer memories"
  - anchored time bias: "prefer memories near this rough point in time"
- Semantic score and tag score should be independently inspectable even when Aurora combines them into one retrieval pass.
- Default semantic behavior should usually weigh free-text semantic similarity and tag semantic similarity evenly unless the caller explicitly tilts them.

## Operator-friendly guidance
- Lean toward semantic-heavy retrieval when the user knows what concept they want.
- Lean toward time-heavy retrieval when the user knows when something happened.
- Use tags for hard filtering, not as a vague substitute for the query itself.
- Keep `k` modest by default and show why each entry was chosen.
- Use bounded variance when you want some exploration around the best cluster without making the pull feel random.

## Example request shape
- Prefer structured parameters first:
  - `RETRIEVAL_PULL(query="team rocket passcodes", k=4, time_weight=0.5, semantic_weight=0.5, tag_weight=0.0, distribution_shape=balanced)`
- When testing semantic behavior explicitly:
  - `RETRIEVAL_PULL(query="team rocket passcodes", k=4, time_weight=0.5, semantic_weight=0.5, semantic_backend=auto, embedding_model="text-embedding-3-small", distribution_shape=balanced)`
- Add shorthand syntax later only if the structured form proves too cumbersome.

## Proposed advanced knobs
- `query`
- `k`
- `time_weight`
- `semantic_weight`
- `tag_weight`
- `semantic_tag_weight`
- `tags_required`
- `tags_preferred`
- `time_anchor`
- `time_scale`
- `distribution_shape`
- `distribution_center`
- `distribution_spread`
- `variance_bias`
- `source_buckets`

## Planned distribution behavior
- `balanced`: simple top-k with only light diversity bias
- `gaussian`: sample near a center point with smooth falloff
- `geometric`: strongly favor the front of the ranked list with a few farther pulls
- `exponential`: very steep preference toward the best-scoring band
- Curve controls such as `distribution_center` and `distribution_spread` should let Aurora "pinch" or widen the search band without changing the entire scoring model.

## Planned shorthand examples
- Example intent: `retrieval_pull("team rocket passcodes", ..., time_weight=.5, semantic_weight=.5, k=4)`
  - equal time and semantic weighting
  - no tags required
  - a little bounded variance so repeated pulls are not perfectly identical
- Example intent: `retrieval_pull("the house where fly is offered", ..., tags=(route 16, Celadon, outskirts, house, old man, CUT), time_weight=.3, semantic_weight=.7, k=8, distribution=gaussian)`
  - stronger semantic pull than time pull
  - route/location tags enabled
  - eight memories drawn mostly from the strongest semantic neighborhood with modest spread
- The concrete syntax can change later; the behavior goal is more important than the exact punctuation right now.

## Explainability expectations
- Every returned memory should expose a score breakdown:
  - semantic contribution
  - tag contribution
  - time contribution
  - importance bonus if any
  - diversity / variance adjustment if any
- When embeddings are enabled, returned memories should also expose:
  - whether lexical or embedding semantic scoring actually drove the match
  - whether embeddings were unavailable and Aurora fell back
- Retrieval logs should record both the requested knobs and the final chosen items so operators can understand why Aurora resurfaced an older memory.
- Promotion logs should record which retrieval item moved into which live-memory target so operators can audit continuity changes.
- Planning-assist logs should record when a review/critique turn used episodic retrieval, what query was built, what backend was used, and how many memories were injected.
- Planning-assist state should also record when retrieval was intentionally skipped due to mode/cooldown so operators can tell "quiet by design" from "did not work."

## Design cautions
- Retrieval should support continuity, not become a hidden second brain that operators cannot inspect.
- Every retrieved item should remain explainable: what matched, how recent it was, and why it beat other candidates.
- Avoid writing snapshots on every turn. Favor important moments and periodic summaries.
