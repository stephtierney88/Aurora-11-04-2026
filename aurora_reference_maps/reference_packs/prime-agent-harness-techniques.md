# Prime Agent Harness Techniques and Aurora Adoption Notes

Original research: 2026-08-08. Comparative addendum: 2026-09-06; the original Prime source pin below remains historical.

## September comparative addendum

The repository report docs/reviews/2026-09-06/agent-harness-survey.md extends this note with 14 public repositories, 18 selected files across 11 implementations/reference surfaces, pinned sources and concrete Aurora adoption criteria. It distinguishes a REPL, code-as-action, recursive analysis, task hierarchy and physical-input ownership. Aurora has since implemented dispatch-backed discovery, stronger shared settings/receipts, optional Astra Responses reasoning and held-input ownership; general-purpose RLM execution remains proposed.

Candidate order is measurement -> discovery/evidence handles -> optional isolated read-only analysis -> evaluated bounded specialists/RLM -> source-backed memory/workflow/hooks. Keep 4B4/4C/4D as the core order. Preserve existing capabilities through the typed optionality contract. Do not copy an in-process REPL, automatic framework compaction into Astra configuration-update history, or a timeout policy that releases physical-input ownership before cleanup is resolved. The survey and current-status note supersede old present-tense implementation assumptions; they do not rewrite the historical Prime findings below.

Status: research and proposed roadmap input only. This document does not enable model-visible prompt mutation, autonomous continuation, executable skill creation, persistent child agents, or new authentication behavior.

## Source Pin and Claim Labels

The source review used:

- Prime Agent repository version `0.7.1`, commit `a18809e00ea30638584d87b3afea7285a9d7296c`, dated 2026-08-07.
- Recursive Language Models paper revision v3, dated 2026-05-11.
- Continual Harness paper revision v1, dated 2026-05-11.
- Current official OpenAI Codex Goals and Subagents documentation fetched 2026-08-08.
- The supplied `pasted-text.txt` as a research lead, not as an authority.

Labels used below:

- **Verified**: confirmed in the pinned Prime Agent source, official repository docs, a primary paper, or official OpenAI documentation.
- **Inference**: a design conclusion drawn from verified mechanics.
- **Unverified**: present in the supplied note or community material but not independently confirmed in this pass.

## Executive Judgment

The most valuable Prime Agent idea is not simply "give the model Python." It is the combination of:

1. a small programmable model-facing surface;
2. authoritative host-owned state and policy;
3. durable, typed continuity records;
4. explicit child-agent identity and messaging;
5. bounded continuation with evidence gates; and
6. reversible harness refinement.

Aurora already has partial versions of most of those ideas: maps and function skeletons, episodic retrieval, prompt pins, goals, a turn scheduler, agent registry/history/suggestions, pending-command approval, external bridge logs, worker monitoring, and read-only companion intake. The useful next step is to unify them through explicit contracts. It is not necessary, or desirable, to copy Prime Agent's unsandboxed persistent IPython control surface wholesale.

The recommended posture is:

- copy the state ownership, receipts, leases, evidence gates, scoping, versioning, rollback, and selective delegation patterns;
- prototype context-as-data through a bounded read-mostly query layer;
- keep refinement proposal-only at first;
- preserve Aurora's API-key default and OAuth opt-in posture;
- keep desktop/game control single-writer; and
- treat autonomous and self-modifying behavior as separate, later, approval-gated lanes.

Any Prime-inspired behavior proposed for Aurora should also follow the typed optionality, settings scope, GUI/command parity, transaction, and truthful turn-mode contract in:

`C:/Users/YourName

## What Prime Agent Actually Does

### 1. RLM context-as-data

**Verified.** Recursive Language Models move a large prompt or corpus out of the root model context and expose it as an external variable. The model can inspect, slice, transform, and recursively send selected portions to other model calls from code.

Prime Agent specializes this into a persistent IPython control environment. Its built-in model tool is `ipython`; file operations, shell work, skills, and subagent admission begin from that environment. Python variables and imported helpers survive ordinary tool calls and compaction.

The important RLM properties are:

- the full source context has a symbolic handle instead of being copied into every model turn;
- intermediate values live outside the root token stream;
- recursive calls can be generated programmatically over selected slices; and
- only bounded observations need to return to the root context.

**Research caution.** The RLM paper does not show that recursion is always better. A no-subcall RLM variant beat recursive variants on one CodeQA setting, while dense aggregation tasks benefited strongly from recursive calls. RLM trajectories also had high-variance, long-tailed cost and runtime, and the paper explicitly warns about exploding sub-call costs and underexplored guardrails.

Aurora implication: treat programmable context and delegation as an adaptive tool, not a mandatory wrapper around every turn.

### 2. Host authority behind a programmable surface

**Verified.** Prime Agent's Python package is a model-facing shim. The TypeScript host remains authoritative for provider calls, credentials, transcript writes, child lifecycle, scheduling, goals, usage accounting, and policy.

Typed host requests cross the kernel boundary. Provider credentials remain in the host; Python receives bounded model-catalog metadata. Unknown child options fail rather than being silently ignored, and an unavailable requested model fails instead of silently falling back.

Aurora implication: if Aurora adds a context-programming or agent-programming surface, keep command dispatch, credentials, permissions, logs, state transitions, and desktop/game control in the existing host. The programmable layer should request operations, not own them.

### 3. Process and session ownership

**Verified.** Prime Agent separates client, supervisor, worker, session runtime, and kernel responsibilities:

- the client owns input, rendering, attachments, and local preferences;
- the supervisor owns public routing, attachments, health, cross-agent delivery, and command journals;
- one worker owns one root session tree, its scheduler, kernels, and descendants; and
- each AgentSession owns model calls, queues, tools, compaction, goals, child lifecycle, and transcript writes.

Every persisted session has a process-safe lease keyed by canonical JSONL path. Runtime replacement acquires the new lease before releasing the old lease, preventing concurrent transcript writers.

Aurora implication: add explicit owner and lease fields before introducing persistent Codex/App Server children or multiple GUI controllers. A status registry without ownership is not enough.

### 4. Persistent child agents

**Verified.** `rlm(...)` admits a real child AgentSession with its own context and session directory. Admission returns a handle; it does not synchronously return the child's answer. Results arrive later through explicit agent messages or files.

The parent keeps an authoritative direct-child registry. It survives compaction, kernel restart, and parent restoration. Retained completed children remain addressable. Deletion writes a tombstone and removes messaging access without erasing the child's transcript and artifacts.

Aurora implication: the first persistent-agent feature should be identity and lifecycle truth, not spawning. A useful registry needs stable IDs, parent edges, status, owner, workspace, created/updated times, last receipt, stop state, transcript/artifact references, and a tombstone state.

### 5. Agent-to-agent messages and receipts

**Verified.** Prime Agent limits direct reach to parent, siblings, and children. Messages have IDs, derived sender identity, bounded size, pending-queue limits, and rate limits. Delivery returns `delivered` or `queued`, with timestamps. The default source constants currently include a 16,384-character maximum, 20 pending messages per session, capacity 3, and one-token-per-second refill.

Its message modes distinguish interrupt-like steering from follow-up work. The same session queue eventually handles user prompts, heartbeats, schedules, goal continuation, autonomous continuation, and agent messages.

Aurora implication: extend the external bridge and companion envelope into a typed receipt fabric before enabling peer control. Include `queued`, `delivered`, `rejected`, `expired`, and `uncertain`; never equate "written to an inbox" with "observed by the target."

### 6. Goals, heartbeats, schedules, and autonomous mode

**Verified.** Prime Agent separates four related concepts:

- goals: durable objectives with lifecycle and accounting;
- heartbeats: periodic re-entry into a session;
- schedules: one-time or recurring prompts; and
- autonomous mode: bounded host-driven continuation with optional gates.

Budgets include turns, tokens, and wall-clock limits. A passed gate proves only what that gate checks. Reaching a budget limit does not imply success. Failed gates can trigger bounded retries, and unchanged workspace state suppresses pointless repetition of the same failed gate.

Schedules are persisted per session. Due ticks are claimed and advanced before delivery, so a crash does not replay an uncertain prompt. Missed ticks are coalesced instead of building an unbounded backlog.

Aurora implication: do not overload the existing screenshot/model-turn heartbeat into a general goal engine. Keep capture scheduling, goal continuation, recurring operator work, and autonomous iteration as separately inspectable policies sharing a common queue.

### 7. Idempotency and uncertain side effects

**Verified.** Prime Agent keys mutating daemon commands by `clientId + commandId` and journals them before dispatch. A received command without a durable result is reported as uncertain and is not replayed. Crash recovery restores continuity but does not replay uncertain side effects.

Aurora implication: this is a high-priority pattern for the external bridge, Portal receipts, Codex app-server intake, and desktop/game actions. A duplicate request must be distinguishable from a retry, and "unknown outcome" must remain a real state.

### 8. Continual Harness refinement

**Verified.** Prime Agent stores four harness entry kinds:

- `prompt`
- `memory`
- `skill`
- `subagent`

Entries carry IDs, scope, title, content, path, references, arguments, metadata, source, timestamps, and version. Refinement events record trigger, changes, evidence, outcome, and timestamp.

The default scope is session-local. Global changes are intended for stable cross-session lessons, durable user preferences, reusable procedures/roles, or explicitly project-qualified facts. The base system prompt is immutable.

The TypeScript refinement path:

- asks for a structured proposal with rationale and expected outcome;
- prefers the smallest evidence-backed edit;
- captures a baseline before planning;
- re-reads before apply and rejects an entry changed during planning;
- writes state through a temporary file plus rename;
- records before/after snapshots; and
- supports rollback.

Automatic refinement review is enabled by default in the inspected version. Its default interval is 25 assistant turns, it can review after compaction, and its default cooldown is 20 minutes. Its review prompt rejects one-off noise, unsupported hypotheses, and transient tool output.

Aurora implication: copy the proposal schema, scope rules, optimistic concurrency, atomic write, versioning, evidence, expected outcome, and rollback. Do not copy the auto-apply default. Aurora should begin with read-only candidates and explicit operator approval.

### 9. Compaction and durable history

**Verified.** Prime Agent treats compaction as lossy. The complete JSONL transcript remains the durable source, while a structured summary plus recent messages becomes the active model context. Repeated compaction carries forward prior summaries and cumulative read/modified-file lists.

Its summary shape includes goal, constraints, progress, completed/in-progress/blocked work, decisions, next steps, critical context, and file history. Kernel state, goals, heartbeats, schedules, and child lifecycles are not treated as complete merely because compaction occurred.

Aurora implication: preserve raw logs and use summaries as derived indexes. A handoff or compacted note should carry provenance and must never be the only copy of a critical command result or decision.

### 10. Trust boundary and Windows posture

**Verified.** Prime Agent's worker and IPython kernel are continuity/lifecycle boundaries, not a security sandbox. Model-generated Python, shell commands, installed packages, skills, and extensions run with the worker user's operating-system permissions.

The repository's main installer targets macOS/Linux. Its Windows guide requires a bash shell and checks a configured path, Git Bash, then `bash.exe` on PATH. Provider docs support subscription OAuth, including ChatGPT Plus/Pro Codex, and API-key providers.

Aurora implication: provider flexibility does not justify changing Aurora's default authentication or execution posture. Keep API key as default, OAuth opt-in, and any third-party harness credentials isolated from Aurora's core state. Do not expose a persistent full-permission REPL merely to gain RLM-like context management.

## Source-Level Risks Worth Remembering

These are observations for our design, not a full Prime Agent code review.

### Corrupt harness state can become an empty rewrite

**Verified.** The Python harness loader catches unreadable or invalid JSON, treats the state as empty, and allows the next save to rewrite a clean empty state. This keeps the kernel alive, but can turn corruption into silent data loss.

Aurora should instead:

- quarantine the corrupt file;
- preserve a byte-for-byte recovery copy;
- report degraded state visibly;
- refuse destructive replacement until acknowledged; and
- recover from the newest validated snapshot when possible.

### Atomicity differs across writers

**Verified.** The TypeScript host uses a temporary file plus rename and checks the planning baseline. The Python helper reloads on mtime change but writes its JSON file directly.

**Inference.** Aurora should standardize every writer on one host-owned atomic/versioned path. Multiple implementations of the same state write contract create avoidable race and crash-recovery ambiguity.

### Automatic refinement is aggressive for Aurora's current maturity

**Verified.** Automatic review/refinement is on by default in the inspected Prime Agent settings.

**Inference.** Aurora's prompt-inclusion and agent-helper lanes are deliberately parked and metadata-first. Automatic persistent refinement would skip the proof discipline those lanes established. Proposal-only is the right starting point.

### Persistent Python is powerful but too broad as a first step

**Verified.** The Prime Agent kernel runs with user permissions and is not a sandbox.

**Inference.** Aurora can gain most context-as-data benefits from typed search, filtering, slicing, aggregation, and safe child-task dispatch without granting arbitrary Python package installation, shell access, secrets, or controller ownership.

## Aurora's Existing Foundation and Exact Gaps

This comparison was checked against the lite map, deep map, function skeleton, and targeted source reads.

### Context and memory

Already present:

- lite/deep maps and JSONL function skeletons;
- runtime reference packs;
- structured goals, route state, notes, journal, and pinned horizons;
- episodic snapshot writing, retrieval, score breakdowns, and explicit promotion;
- prompt-context ledger, Prompt Pins, Do Not Include, preview, rehearsal, activation, and closure snapshots.

Gap:

- no single bounded query plane over maps, logs, notes, episodic records, and agent records;
- no symbolic source handle that can be safely sliced or aggregated without loading raw content; and
- no typed, versioned refinement candidate spanning these stores.

### Goals and continuation

Already present:

- `Goal` with text, priority, significance, status, and sub-goals;
- add/complete commands and pinned-goal display;
- model-turn heartbeat, capture wake, minimum gap, and post-action settle logic.

Gap:

- Aurora's current Goal is a basic in-memory planning object, not a persisted completion contract;
- it has no verification surface, constraints, boundaries, budget, blocker state, or evidence ledger; and
- the turn heartbeat is a model/capture wake mechanism, not durable goal or scheduled-work continuation.

### Agents

Already present:

- agent registry rows, ACL previews, private history, task packets, suggestions, policy tags, approval metadata, and staged pending-command candidates;
- explicit flags such as `can_spawn_worker=False`, no command execution, and no model-visible promotion.

Gap:

- no child session runtime, parent-edge lifecycle, retained child, direct message delivery, or receipt state;
- no worker/session lease; and
- no transcript/artifact ownership contract for external Codex or Prime Agent sessions.

### Commands, bridge, and lifecycle

Already present:

- `append_external_message_record`, inbox offsets, message IDs, bridge logs, raw-command checks, and command-result logs;
- `enqueue_or_execute_command`, semantic/family/conflict keys, context fingerprints, pending-command review, and explicit approval;
- `MutationAdmissionJournal` with fsynced external-mutation reservation, normalized `client_id + request_id`, command digest conflict detection, terminal reconciliation, duplicate suppression, and explicit uncertain/no-replay receipts;
- `monitor_and_restart_processes` for standard Aurora workers.

Gap:

- mutation admission currently covers recognized external raw commands rather than every internal/model/sibling mutation route;
- no operator reconciliation/annotation workflow can resolve or supersede a durable uncertain admission;
- no session transcript lease; and
- worker restart reconstructs standard processes, not a durable agent session tree with pending schedules and retained children.

## Proposed Aurora Adoption Roadmap

This is a candidate lane, not a replacement for the canonical roadmap. Open one bounded slice at a time.

### PA-0: Documentation and chat policy

Status after this research pass: documented.

- Keep map-first orientation.
- Add context-as-data, goal-contract, selective-delegation, single-writer, receipt, evidence-gate, and refinement-candidate rules for Codex chats.
- Record confirmed facts separately from inference and unverified anecdotes.

### PA-1: Read-only refinement candidate ledger

Add `harness_refinement_candidate_v1` without any apply path.

Candidate fields:

```json
{
  "schema_version": "harness_refinement_candidate_v1",
  "candidate_id": "refine-...",
  "scope": "session|project",
  "kind": "prompt_note|memory|procedure|agent_role|map_repair",
  "source_evidence": [],
  "before": null,
  "proposed_after": {},
  "rationale": "",
  "expected_outcome": "",
  "verification": [],
  "risk": "low|medium|high",
  "status": "draft|reviewed|approved|rejected|stale"
}
```

First commands should be inspect-only:

- `SHOW_REFINEMENT_CANDIDATES()`
- `PREVIEW_REFINEMENT(candidate_id)`
- `REJECT_REFINEMENT(candidate_id)`

Do not add `APPLY_REFINEMENT` in the first slice.

### PA-2: Goal contract v2

Add a parallel contract instead of silently changing legacy `Goal` behavior:

```json
{
  "schema_version": "goal_contract_v2",
  "goal_id": "goal-...",
  "objective": "",
  "verification_surfaces": [],
  "constraints": [],
  "boundaries": [],
  "budgets": {"turns": null, "tokens": null, "wall_seconds": null},
  "status": "draft|active|paused|blocked|complete|budget_limited|cleared",
  "evidence": [],
  "blocker": null,
  "next_action": null
}
```

Keep creation operator-explicit. Completion requires evidence. Budget exhaustion and compaction are not completion.

### PA-3: Envelope, receipt, and lease contract

Progress on 2026-08-08: Window 23 Slice 1 completed the local operator-command correlation substrate. `aurora_bridge_request_v1` carries `request_id`, `message_id`, and `client_id`; normal/rejected external command outcomes produce correlated `aurora_command_receipt_v1` rows; and the CLI waits by exact request identity. At that slice boundary it did not yet provide duplicate-request suppression, journal-before-dispatch idempotency, leases, peer-agent delivery, or no-replay recovery.

Window 23 Slice 2 then added the `aurora_settings_registry_v1` read substrate for 19 high-value controls. This gives later Prime/RLM-inspired behaviors explicit types, defaults paths, scopes, maturity, risk, apply timing, locks, and readback before they can become toggles. Slice 4 expanded that substrate to 22 controls by promoting the full scheduler wake/debounce/settle bundle.

Window 23 Slice 3 added atomic runtime-session settings transactions over that substrate: opaque version preconditions, complete-batch preview/validation, existing-setter invocation under one runtime lock, effective readback, correlated nested receipts, and same-session single-use rollback handles.

Window 23 Slice 4 made the Control Panel a nonblocking client of the same service, with atomic preview/apply, source and policy details, conflict refresh, exact rollback, Capture Now parity, and explicit separation of unregistered independent commands. Prime/RLM-inspired refinements can therefore propose and preview registered changes through either operator surface without bypassing version/lock/readback evidence.

Window 23 Slice 5 added the first Prime-style mutation safety boundary: an fsynced `aurora_mutation_admission_v1` reservation keyed by normalized `client_id + request_id`, command digest conflict detection, terminal reconciliation, exact duplicate suppression, and explicit uncertain/no-automatic-replay recovery. Persistent settings writes, operator reconciliation of uncertainty, controller/transcript leases, peer-agent delivery, and automatic refinement remain off.

Window 23 Slice 6 added the operator-facing inspection layer over those contracts: generated command/settings discovery, context-aware completion, a dependency-free Windows shell editor, and local history that refuses plausibly secret-bearing commands. It adds no worker delegation, hidden tool authority, OS-shell escape, or automatic mutation replay. This is useful preparation for later Prime/RLM-style refinement because an operator can inspect and invoke bounded controls through the same receipts instead of creating a parallel harness path.

Extend existing bridge/companion records with:

```json
{
  "message_id": "msg-...",
  "command_id": "cmd-...",
  "client_id": "client-...",
  "sender_id": "",
  "receiver_id": "",
  "relationship": "parent|sibling|child|external",
  "mode": "steer|follow_up|status",
  "delivery": "queued|delivered|rejected|expired|uncertain",
  "owner_lease": "",
  "created_at": "",
  "delivered_at": null
}
```

Require a single writer for transcripts, agent state, and each desktop/game controller. Journal mutations before dispatch. Never replay an uncertain side effect.

### PA-4: Operator-approved non-executable refinement

After PA-1 proves useful:

- apply only session/project prompt notes, memory records, map repairs, and procedure descriptions;
- exact-confirm project-scope changes;
- keep global scope off initially;
- use atomic writes, versions, baseline checks, before/after snapshots, and rollback;
- quarantine corruption instead of rewriting empty state; and
- require post-apply verification against the candidate's expected outcome.

Executable skills, arbitrary Python, auth changes, permissions, command allowlists, and agent-spawn specs remain out of scope.

### PA-5: Bounded continuation

Only after goal v2 and receipts are stable:

- continue only when the goal is active, Aurora is idle, no operator input is queued, and the budget permits;
- stop after a continuation that makes no meaningful tool/action progress;
- bind every quality gate to a named verification claim;
- suppress identical failed-gate retries when the workspace/world fingerprint is unchanged;
- coalesce missed schedules; and
- surface `blocked`, `budget_limited`, and `uncertain` distinctly.

### PA-6: Safe programmable context plane

Start with host-owned read-mostly operations:

- `catalog()`
- `search(source, query, filters)`
- `slice(source, start, count)`
- `filter(source, predicate_schema)`
- `aggregate(source, fields, operation)`
- `summarize(ids, budget)`
- `delegate(ids, task_contract)`

Bound result sizes and preserve source IDs. Prefer structured parsers for JSONL/JSON/TSV. Do not expose secrets, raw auth stores, arbitrary imports, shell execution, network access, or controller writes.

An isolated Python research kernel can be considered later, but it should be a separate permission profile with a disposable workspace and typed host bridge, not a hidden full-permission extension of Aurora's main process.

### PA-7: Persistent external agent intake

Build on the Codex app-server/Portal companion lane:

- ingest thread, turn, item, goal, subagent, and terminal events as read-only records;
- maintain stable external agent/session IDs and parent edges;
- show status, last activity, model/effort when reported, budget/accounting when reported, and receipt state;
- retain raw event provenance; and
- do not enable external mutation, steering, OAuth broadening, or desktop control in the first slice.

### PA-8: Continual Harness gameplay research

Pokemon is the best contained Aurora research lane because it already has snapshots, route memory, action policy, and measurable milestones.

Use a conservative experiment:

- refinement candidates remain session-local and proposal-only;
- compare baseline versus refined harness from equivalent emulator checkpoints;
- evaluate on held-out checkpoints, not only the trajectory that produced the lesson;
- score legal game progress, recovery, battle outcomes, and action efficiency separately;
- keep emulator/RCON/debug mutations outside the allowed action surface;
- penalize policy violations even if milestone score rises; and
- require a human-readable before/after lesson and rollback path.

Do not optimize one proxy such as button count in isolation.

## Sibling-Project Synergies

### Portal

- Natural read-only UI for agents, goals, refinement candidates, leases, and receipts.
- Keep Portal a projection of canonical contracts, not a second source of truth.
- Mutation controls should remain gated by Aurora's new admission/outcome receipts and stay off in sibling projects until their own route, lease, authorization, and reconciliation contracts are explicit.

### Aurora Browser

- Use a visible controller lease so only one agent owns pointer/keyboard control at a time.
- Other agents can inspect, propose, or queue actions, but cannot fight over the controls.
- Browser observations should return compact evidence packets and artifact references.

### Codex app-server and hook work

- App-server thread/turn/item events are a strong source for read-only external-agent intake.
- Preserve native IDs and event ordering; do not invent success when an event stream disconnects.
- Hooks can record lifecycle evidence, but should not silently rewrite project policy or broad permissions.

### App Game Builder

- Prime Intellect's taskset/harness/runtime separation maps well to AGB: the game or import task is the taskset, editor/runtime behavior is the harness, and browser/Electron/local execution is the runtime.
- Deterministic import/readback/tests make good evidence gates.
- AGB and Aurora should exchange structured artifacts and receipts, not share a live controller.

### General Codex chats

- Use native Goals for long-running work with measurable finish lines.
- Use subagents for independent read-heavy exploration, tests, and review.
- Keep one writer for overlapping files and one controller for interactive apps.
- Return distilled evidence and source references, not raw worker transcripts.
- Convert lessons into candidates first; persist only after review.

## Guardrails to Treat as Requirements

1. The host owns credentials, policy, logs, transcripts, dispatch, and side effects.
2. One canonical writer owns each mutable state store and interactive controller.
3. Every mutation has an idempotency key, durable journal point, and explicit outcome.
4. `uncertain` is not success and is not automatically replayable.
5. Goal completion requires named evidence; budget exhaustion is not completion.
6. A passed gate proves only the claim that gate checks.
7. Refinement defaults to session scope; broader scope requires stronger review.
8. One-off noise, unsupported hypotheses, and transient tool output do not become memory or policy.
9. Executable skills and agent specs never auto-apply from a single trajectory.
10. Auth, permissions, network policy, safety rules, and command allowlists require explicit operator action.
11. Raw histories remain immutable sources; compactions and summaries are derived indexes.
12. Corrupt state is quarantined and recoverable, not silently replaced with empty state.
13. Persistent kernels are not sandboxes.
14. Child agents do not inherit controller ownership merely because they inherit tools.
15. Recursion, concurrency, token use, wall time, message size, queue depth, and retries are all bounded.
16. Refinement is tested on held-out or later evidence so reward hacks do not become reusable skills.

## Claims Not Independently Verified in This Pass

The supplied note describes a Prime Agent Factorio run in which RCON resource spawning became a rewarded shortcut and `/refine` allegedly preserved stronger cheating techniques. The referenced Prime Agent blog page could not be fetched through the available web tooling, and this anecdote was not found in the current repository.

Treat the specific story as **unverified** here. The design lesson remains valid and is independently supported by Prime Intellect's published reward-hacking work: a self-improving harness optimizes the evidence and reward surface it is given, not the operator's unstated intent. Aurora should therefore separate task progress, policy compliance, and anti-cheat checks.

Self-reported benchmark or product claims should also remain labeled as such unless reproduced locally.

## Sources

Primary sources:

- [Prime Agent repository](https://github.com/PrimeIntellect-ai/prime-agent)
- [Pinned Prime Agent source tree](https://github.com/PrimeIntellect-ai/prime-agent/tree/a18809e00ea30638584d87b3afea7285a9d7296c)
- [Prime Agent architecture](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/architecture.md)
- [Prime Agent daemon design](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/daemon.md)
- [Prime Agent RLM design](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/rlm.md)
- [Prime Agent RLM runtime](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/rlm-runtime.md)
- [Prime Agent long-running agents](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/long-running-agents.md)
- [Prime Agent compaction](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/docs/compaction.md)
- [Prime Agent refinement implementation](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/src/core/refinement/refinement.ts)
- [Prime Agent Python harness state](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/prime-agent-runtime/src/rlm/harness.py)
- [Prime Agent agent-message implementation](https://github.com/PrimeIntellect-ai/prime-agent/blob/a18809e00ea30638584d87b3afea7285a9d7296c/packages/coding-agent/src/core/agent-messages.ts)
- [Recursive Language Models paper](https://arxiv.org/abs/2512.24601)
- [Continual Harness paper](https://arxiv.org/abs/2605.09998)
- [Prime Intellect RLM research note](https://www.primeintellect.ai/blog/rlm)
- [Prime Intellect verifiers v1 architecture](https://www.primeintellect.ai/blog/verifiers-v1)
- [OpenAI Codex Goals guide](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [OpenAI Codex Subagents documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)

Local source lead:

- `C:/Users/YourName

## Related Local Policy

- `C:/Users/YourName
- `C:/Users/YourName
