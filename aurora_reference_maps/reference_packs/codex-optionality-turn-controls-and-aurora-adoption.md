# Codex Optionality, Turn Controls, and Aurora Adoption Notes

Original research: 2026-08-08. Comparative addendum: 2026-09-06; local Codex version observations below are historical.

## September comparative addendum

User confirmation 2026-09-06: capability breadth and extensive AI-facing settings are deliberate. Preserve old and new valid behaviors/states, command aliases and saved configurations; expose alternatives through toggles, profiles, configuration and searchable Advanced controls. Canonical reminder: docs/notes/aurora_capability_compatibility.md. H0–H5 is accepted as a staged adoption direction; these features are not enabled by this note.

See repository report docs/reviews/2026-09-06/agent-harness-survey.md for current public-source comparisons and H0–H5 research candidates. This extends the optionality contract without enabling new behavior. Implemented Aurora baseline is Implementation 14 / 4B4d local history; 4B4e retention/prompt-state controls are next. Defaults demonstrate the optionality rule: existing reapply remains default, with changed_only available explicitly through both Apply commands.

The proposed dimensions are discovery detail, result/evidence presentation, isolated analysis execution, worker persistence, specialist/RLM budgets, provider-aware context policy, memory refinement and loop diagnostics. Map adopted controls into the existing registry rather than adding a second settings authority. Distinguish what the model initially sees, what is enabled, and what may execute. Profiles should expose their setting diff; all old commands and full detail stay reachable. Show effective value/source/scope, maturity, apply timing, versioned receipt and rollback. Do not infer a production REPL or recursive agent loop from the existing registry/readiness metadata.

Status: research, design contract, and proposed roadmap input only. This file does not enable a new transport, change Aurora defaults, add autonomous desktop control, alter authentication, or claim that the current `hybrid` scheduler is a true Codex-style tool loop.

## Executive Judgment

Aurora should borrow Codex's control-plane patterns before borrowing more Codex-like behaviors.

The strongest additions are:

1. one typed settings registry that drives runtime validation, the Control Panel, commands, CLI flags, status output, help, profiles, export/import, and maps;
2. layered settings with an effective value and source for every key;
3. atomic settings transactions with version preconditions and receipts;
4. feature maturity labels and conservative defaults;
5. separate controls for observation, turn scheduling, action dispatch, approvals, and persistence;
6. a canonical event timeline for turns, captures, actions, approvals, and hooks; and
7. an optional future interleaved tool adapter for genuinely Codex-like action/observation loops.

Aurora already has many of the individual switches. Window 23 now gives the first 22 high-value controls one typed, versioned transaction path across CLI and Control Panel. The remaining design work is to expand that contract deliberately, preserve visible boundaries for legacy independent commands, and keep source, scope, validation, and readback truthful as optionality grows.

The desired posture is:

- compatible defaults;
- new behavior opt-in unless it is a proven safety or correctness fix;
- a small Basic surface for frequent choices;
- a searchable Advanced surface for full control;
- command and CLI parity for every setting;
- visible effective value, source, scope, maturity, and restart/apply semantics;
- profiles as named collections, not hidden behavior; and
- no misleading `codex_like` label until Aurora can interleave model tool calls, action results, and continued reasoning inside one turn.

## Research Pin

This review used four kinds of evidence.

### Local Codex installation

- `codex-cli 0.141.0` on this Windows machine.
- Generated local app-server schema from `codex app-server generate-json-schema --experimental`.
- Local stable feature flags include apps, browser use, Computer Use, goals, hooks, image generation, multi-agent, plugins, tool suggestions, and workspace dependencies.
- Local experimental or under-development flags include memories, multi-agent v2, realtime conversation, token budget, network proxy, and request-permission work.
- The local desktop package was observed as ChatGPT/Codex app version `26.803.5235.0`.
- No authoritative first-party changelog file was found in the local app resources. The official online changelog remains the release authority.

### Version caution

The official changelog listed Codex CLI `0.147.0` on 2026-08-07, while the installed CLI was `0.141.0`. Changelog ideas below are design input, not proof that every capability is active in the local build. Generated local schema and `codex features list` are better evidence for this machine.

### Official material reviewed

- [Codex changelog](https://developers.openai.com/codex/changelog)
- [Config basics](https://developers.openai.com/codex/config-basic)
- [Advanced config](https://developers.openai.com/codex/config-advanced)
- [Config reference](https://developers.openai.com/codex/config-reference)
- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Hooks](https://developers.openai.com/codex/hooks)
- [Computer Use](https://developers.openai.com/codex/computer-use)
- [Appshots](https://developers.openai.com/codex/appshots)
- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Developer commands](https://developers.openai.com/codex/developer-commands)

### Aurora source surfaces inspected

- `aurora2.py`: model call, response parsing, command routing, turn scheduler, demand capture, action policy, command handlers, runtime status, and CLI arguments.
- `aurora2_control_panel.py`: safety inventory, operator profiles, Settings, Turn Timing, Recovery, Screenshot, locks, raw commands, and settings apply behavior.
- Aurora command catalog and reference maps for current public controls.

## What Codex Suggests

### 1. Layered configuration with visible origins

Codex resolves configuration through ordered layers: one-run flags, trusted project config, selected profile, user config, system policy, and built-in defaults. Its app-server config read response can report both the resolved config and origin metadata.

Aurora implication: every setting should be queryable as:

```text
requested value: hybrid
effective value: hybrid
source: profile/balanced
scope: session
version: 184
locked by: none
apply mode: immediate
maturity: stable
```

A displayed checkbox without source and scope is incomplete. The operator should know whether the value came from a built-in default, profile, persisted preference, project file, session override, one-turn override, or safety lock.

### 2. Typed feature lifecycle

Codex exposes feature name, enabled state, default state, description, display name, and lifecycle stage. Stages include stable, beta, under development, deprecated, and removed.

Aurora implication: feature toggles need maturity and availability, not only boolean state. A Control Panel should distinguish:

| State | Meaning |
| --- | --- |
| stable | supported and suitable for normal use |
| beta | available for operator testing with known caveats |
| experimental | incomplete, high-change, or lightly tested |
| unavailable | designed but missing a required adapter or dependency |
| deprecated | retained for compatibility; avoid new use |
| removed | accepted only as a migration or diagnostic marker |

This prevents a future `Codex Interactive` profile from appearing equivalent to the current scheduler before the transport exists.

### 3. Atomic writes with optimistic concurrency

The local app-server schema has `config/batchWrite` with:

- a list of edits;
- replace or upsert merge strategy;
- `expectedVersion` to reject stale writes;
- an optional target file; and
- optional hot reload into loaded tasks.

Aurora implication: the Control Panel should not apply a large settings form by sending dozens of unrelated commands and hoping all succeed. It should preview and validate a complete transaction, then apply all or none.

Recommended lifecycle:

```text
draft -> validated -> previewed -> applied | deferred | rejected | locked
                                      -> rolled_back
```

The receipt should include requested edits, effective edits, unchanged keys, rejected keys, lock reasons, deferred/restart-required keys, previous version, new version, and rollback token.

### 4. A turn is an event stream, not only a final answer

Codex app-server has thread start/resume/fork, `turn/start`, `turn/steer`, streamed item events, tool progress, approvals, `turn/completed`, and `turn/interrupt`. Non-interactive JSON output similarly exposes thread, turn, item, error, command, file, plan, and reasoning-summary events.

Aurora implication: the useful pattern is a canonical item timeline with stable IDs, status, timestamps, parent turn, source, and result. It should cover:

- observation requested, started, completed, or failed;
- model turn requested, started, streamed, completed, interrupted, or failed;
- command proposed, allowed, held, rejected, approved, dispatched, completed, uncertain, or rolled back;
- hook started and completed;
- child task admitted, active, waiting, completed, or cancelled; and
- settings previewed, applied, deferred, rejected, or rolled back.

This is more reliable than deriving state from log prose or a few last-value runtime fields.

### 5. Approvals are capability-specific

Codex separates sandbox policy, approval policy, app action approval, Computer Use app access, and managed constraints. Recent changelog entries also describe a writes-only app approval mode and automatic approval review as explicit modes.

Aurora implication: avoid one giant `safe/assist/auto` interpretation for every capability. Keep it as a convenient profile, but allow granular categories:

| Category | Examples |
| --- | --- |
| observe | screenshot, read status, inspect window |
| memory | add or update bounded internal memory |
| desktop_pointer | move, click, drag, scroll |
| desktop_keyboard | type, hotkey, key down/up |
| filesystem_read | read local files |
| filesystem_write | edit, create, delete, move |
| process | start, stop, or signal a process |
| network | outbound request or remote bridge |
| auth | login, token refresh, credential selection |
| persistent_policy | profile, lock, prompt, skill, or global-setting change |

Profiles can map those categories to allow, ask, review, or deny. Authentication and persistent-policy changes should remain operator-controlled.

### 6. GUI control is foreground, scoped, and permissioned

Official Computer Use guidance says Windows control operates on the visible active desktop and can take over pointer and keyboard focus. It also exposes per-app access and an always-allowed app list. Appshots provide a separate manual capture gesture and attach visible context without implying autonomous control.

Aurora implication:

- make target window/app policy explicit;
- expose foreground ownership and current controller;
- separate `Capture now` from continuous capture;
- add app/window allowlists before broader desktop autonomy;
- use a visible keyboard-control indicator;
- include a release-all-input recovery action; and
- treat manual appshot-like capture as a first-class observation source.

### 7. Hooks are deterministic boundaries

Codex hooks can run at prompt submission, before and after tools, permission requests, compaction, subagent start/stop, turn stop, and session start/end. Non-managed hooks require trust tied to the exact hook definition hash.

Aurora implication: add a later hook/event subscription layer, but keep it host-owned and trust-gated. Initial hooks should be observational or validating. Executable hooks need source, hash, scope, timeout, output bound, failure policy, and trust state.

Useful Aurora hook points:

```text
ObservationRequested
ObservationCompleted
TurnStarting
CommandProposed
ApprovalRequested
BeforeAction
AfterAction
TurnCompleted
ContextCompacting
ContextCompacted
ChildStarting
ChildStopped
SettingsChanging
SettingsChanged
RuntimeStopping
```

### 8. Changelog patterns worth importing

Recent official Codex releases reinforce several durable ideas:

- branch or checkpoint when editing/retrying earlier work instead of overwriting the only history;
- bound command output and metadata volume;
- redact secrets and full bearer tokens in display and replay;
- keep item timestamps and canonical event types;
- make agent roles, model, effort, and concurrency configurable;
- require explicit trust for unfamiliar projects and changed hooks;
- improve Windows process interruption and path handling; and
- warn when a high-cost mode combines with high concurrency.

These should become general Aurora contracts, not isolated UI patches.

## Aurora's Current Baseline

### Already available

Aurora already has meaningful controls:

- `REQUEST_SCREENSHOT_CAPTURE(reason, settle)` for one-off capture;
- `SET_DEMAND_CAPTURE(on|off)`;
- screenshot interval and capture persistence controls;
- scheduler modes `per_capture`, `event`, and `hybrid`;
- named scheduler profiles;
- capture wake, debounce, heartbeat, minimum turn gap, and post-action settle;
- action modes `gb`, `pyag`, and `none`;
- execution modes `safe`, `assist`, and `auto`;
- pending queue modes `normal`, `replace`, and `insert`;
- next-turn model/reasoning controls;
- locks, operator authorization, runtime status, and pending review;
- PyAutoGUI move, click, drag, scroll, type, hotkey, press, hold, release, screenshot, and focus operations; and
- Control Panel operator profiles, safety classifications, raw commands, and Advanced/Recovery surfaces.

This means the recommended work is consolidation and clearer semantics before adding many new switches.

### Current turn and action semantics

Aurora's primary model path currently:

1. builds a complete prompt and state snapshot;
2. makes a non-streaming Chat Completions request;
3. receives the full assistant text;
4. parses its command and task sections;
5. policy-checks proposed commands;
6. joins all currently executable commands into one queued batch;
7. executes that batch sequentially; and
8. requests a later post-action capture/model wake when command results arrive.

That is configurable end-of-response batch execution. It is not an in-flight model tool loop. The model does not normally see the result of action 1 before action 2 in the same response batch.

The current `codex_like -> hybrid` scheduler alias is therefore only scheduler shorthand. It should be renamed or clearly labeled `legacy alias` so it does not imply turn-level tool interleaving.

### Current Control Panel apply behavior

Window 23 Slice 4 moved 22 registered values onto one nonblocking `SETTINGS_TRANSACTION(...)` client. `Preview Atomic`, `Apply Atomic`, settings details, exact-request receipts, version-conflict refresh, and same-session rollback now share the CLI/runtime contract. Named scheduler profiles submit one bundle; editing a scheduler leaf switches the form to `custom` and submits all six leaves.

Controls outside that registry remain visible through `Apply Additional` or disclosed profile follow-up batches. They are independent commands, and profile follow-ups run only after the registered transaction succeeds. This preserves compatibility without overstating atomicity. Future registry expansion should continue shrinking this boundary.

### Small source cleanup flagged

Resolved in Window 23 Slice 4: duplicate `global` declarations in `aurora2.py::apply_turn_scheduler_profile()` were removed while the six-field scheduler bundle was promoted into the shared registry.

The reference-pack manifest/generator and `aurora2.py::AURORA_REFERENCE_PACK_PATHS` are also separate registries. This review synchronized the three new research packs and their aliases, but the longer-term fix is to load validated manifest entries or generate the runtime registry so future packs cannot be mirrored yet unreachable through `SHOW_REFERENCE_PACK`.

## Optionality Contract

Every new Prime-, Codex-, or community-inspired behavior should satisfy this contract before it is considered integrated.

1. **Typed key.** Name, type, default, allowed values/range, validation, and description are defined once.
2. **Compatibility default.** Existing behavior remains the default unless a measured safety/correctness reason justifies migration.
3. **Explicit maturity.** Stable, beta, experimental, unavailable, deprecated, or removed.
4. **Explicit scope.** System, profile, project, session, next turn, or next action.
5. **Visible source.** Effective value reports the winning layer and any lock/constraint.
6. **GUI placement.** Basic, Advanced, Recovery, or hidden/internal is declared.
7. **Command parity.** Read, describe, set, reset, preview, and status are available without the GUI.
8. **CLI parity.** Startup/session overrides exist when the setting matters before the GUI connects.
9. **Apply semantics.** Immediate, next turn, next action, process restart, or unavailable.
10. **Safety class.** Normal, advanced, risky, recovery-critical, or managed-only.
11. **Dependencies.** Required transport, feature, app/window policy, model capability, and conflicts are declared.
12. **Receipt and rollback.** Persistent or risky changes have versioned readback and a reversal route.
13. **No silent persistence.** A GUI action states whether it changes only this run, the selected profile, project defaults, or personal defaults.
14. **No silent broadening.** Profiles cannot silently expand auth, network, destructive, keyboard, or persistent-policy permissions.

## Proposed Settings Registry

One machine-readable registry should become the source of truth. A simplified entry could look like:

```json
{
  "key": "turn.action_dispatch_mode",
  "type": "enum",
  "default": "end_of_response_batch",
  "allowed": [
    "end_of_response_batch",
    "one_action_then_observe",
    "tool_call_immediate",
    "approval_stepwise",
    "queued_next_turn",
    "disabled"
  ],
  "maturity": "stable",
  "gui_tier": "advanced",
  "scopes": ["profile", "project", "session", "next_turn"],
  "apply": "next_turn",
  "risk": "advanced",
  "lock_key": "execution",
  "requires": [],
  "conflicts": [],
  "command_aliases": ["SET_ACTION_DISPATCH_MODE"],
  "cli_aliases": ["--action-dispatch-mode"]
}
```

Generate or validate these surfaces from the registry:

- runtime defaults and validators;
- Control Panel controls, labels, tooltips, and disabled reasons;
- command handlers and help;
- CLI arguments;
- named profiles;
- snapshot/status serialization;
- export/import schema;
- lock inventory;
- lite/deep maps and function skeleton annotations; and
- migration checks for renamed or removed keys.

## Proposed Precedence

Lowest to highest effective influence:

1. built-in defaults;
2. persisted personal defaults;
3. selected named profile;
4. persisted project defaults;
5. session overrides;
6. next-turn or next-action overrides;
7. safety locks and managed constraints.

Locks and managed constraints are caps, not ordinary high-precedence values. A session override may narrow a permission but must not defeat a lock that forbids broader access.

The Control Panel should provide `Apply to: This action | Next turn | This session | Project | Personal profile`. Persistent targets should require a clearer confirmation than session changes.

## Proposed Command Surface

Keep current specific commands as compatibility aliases, then add a generic settings API:

```text
LIST_SETTINGS(optional_filter)
DESCRIBE_SETTING(name)
GET_SETTING(name)
SHOW_EFFECTIVE_SETTINGS(optional_filter)
SET_SETTING(name, value, scope=session, expected_version=optional)
RESET_SETTING(name, scope=session, expected_version=optional)
PREVIEW_SETTINGS_BATCH(json_or_profile, scope=session)
APPLY_SETTINGS_BATCH(json_or_profile, scope=session, expected_version=optional)
ROLLBACK_SETTINGS(receipt_or_version)
DIFF_SETTINGS(left_scope, right_scope, optional_filter)
EXPORT_SETTINGS(scope, optional_path)
IMPORT_SETTINGS(path, scope=session, preview=true)
APPLY_PROFILE(name, scope=session, preview=true)
SHOW_FEATURES(optional_maturity)
SET_FEATURE(name, on_or_off, scope=session)
```

All writes return a structured receipt. Unknown keys should fail in strict mode rather than being ignored.

## Control Panel Layout

### Basic

Keep frequent operator choices visible:

- Run/pause and current controller/foreground owner;
- Live model on/off;
- execution profile;
- action mode;
- scheduler profile;
- capture trigger summary;
- a camera-icon `Capture now` button using `REQUEST_SCREENSHOT_CAPTURE`;
- pending approval count and review action;
- selected app/window target; and
- current profile plus `session override` indicator.

### Advanced

Use searchable grouped settings, not one enormous form:

- Turn Engine;
- Observation and Screenshots;
- Action Dispatch;
- Pointer and Keyboard;
- Approvals and Locks;
- Models and Inference;
- Context and Output Budgets;
- Hooks and Events;
- Persistence and Profiles;
- Network, Auth, and Bridges; and
- Experimental Features.

Each row should show effective value, source badge, maturity badge, apply timing, and reset-to-inherited control. A disabled control should state the missing requirement, such as `interactive adapter not installed`.

### Recovery

Keep recovery actions isolated and always easy to find:

- stop model turns;
- stop action dispatch;
- release all held keys/buttons;
- clear or quarantine pending actions;
- restore last known-good settings receipt;
- capture current screen without acting;
- show locks/owners/leases; and
- export a diagnostic snapshot.

## Observation and Screenshot Modes

Observation trigger and turn scheduling must be independent controls.

Recommended triggers:

| Trigger | Meaning |
| --- | --- |
| periodic | capture on interval |
| event | capture after input, action result, or explicit event |
| visual_change | capture/wake after meaningful frame change |
| post_action | capture after settle following an action |
| manual | capture only when operator/model requests it |
| pre_action | optional evidence capture immediately before a risky action |

Recommended settings include capture region/window, image detail, settle delay, change threshold, persistence/retention, privacy masks, include-accessible-text when available, and whether a capture wakes the model or only updates state.

`Capture now` should be available in Basic, via command, and via hotkey. It should not alter interval, queue order, execution mode, or approval state.

## Turn Engine Modes

Use names that describe actual behavior.

| Mode | Behavior | Initial maturity |
| --- | --- | --- |
| `snapshot_batch` | current full response, then policy/routing and optional action batch | stable/default |
| `stepwise_observe` | one action, settle/capture, then a new model turn | beta candidate |
| `review_then_act` | model proposes; operator/guardian selects; actions run after approval | stable profile over existing controls |
| `plan_only` | model may plan and update bounded memory but cannot dispatch actions | stable |
| `interactive_tools` | model emits tool call, receives result, and continues inside one turn | unavailable until new adapter |

`stepwise_observe` can be built over the current scheduler and command-result wake path. It will be slower and consume more turns, but it gives the model fresh visual evidence between actions.

`interactive_tools` requires a Responses-style or app-server-style adapter with tool schemas, streamed/canonical items, result reinjection, interrupt, and approval handling. It is not a scheduler-profile rename.

## Action Dispatch Modes

Action dispatch is separate from the model transport and capture trigger.

| Mode | Meaning |
| --- | --- |
| `end_of_response_batch` | execute all policy-allowed commands after full response |
| `one_action_then_observe` | dispatch one command, capture/readback, schedule next turn |
| `tool_call_immediate` | execute an in-turn tool call and return result to same model turn |
| `approval_stepwise` | request approval for each action or bounded action group |
| `queued_next_turn` | hold proposals for later support/review |
| `disabled` | never dispatch actions |

Additional settings:

- maximum actions per batch;
- maximum pointer/keyboard actions before observation;
- inter-action delay;
- pre-action and post-action capture;
- stop batch on first failure or uncertain result;
- require target-window match;
- auto-release held inputs on interruption;
- idempotency/readback policy; and
- action result timeout.

## Pointer and Keyboard Controls

PyAutoGUI-like behavior deserves a dedicated Advanced group because keyboard state can outlive one command.

Recommended settings:

- keyboard mode: disabled, text-only, common keys, hotkeys, full;
- pointer mode: disabled, move-only, click, drag/full;
- maximum typed characters per action;
- typing interval;
- hotkey allowlist/denylist;
- held-key timeout;
- release-all on error, interrupt, focus loss, or runtime stop;
- require focused-window identity before each action;
- clipboard use on/off;
- paste versus per-key typing;
- coordinate basis: screen, active window, captured region, normalized;
- pointer move duration;
- double-click interval;
- scroll unit/limit;
- fail-safe corner behavior; and
- operator activity pause/takeover policy.

The GUI should show a clear `Keyboard control enabled` state and the currently targeted app/window. Commands and status output must expose the same information.

## Named Profiles

Profiles should be transparent bundles whose diffs can be previewed.

Candidate profiles:

| Profile | Intent |
| --- | --- |
| Legacy Conveyor | preserve current per-capture behavior |
| Balanced Snapshot | current compatible hybrid snapshot behavior |
| Manual Observe | manual capture, no autonomous action |
| Review Then Act | proposals and explicit review before action |
| Stepwise Visual | one action, observation, new turn |
| Desktop Cautious | app allowlist, pointer limited, keyboard restricted |
| Desktop Full | broad GUI control with visible warning and recovery controls |
| Codex Interactive | unavailable/experimental until interleaved adapter exists |

Applying a profile should display the exact setting diff and never silently persist it beyond the selected scope.

## Prime Agent and Refinement Interaction

Prime-style harness refinement should consume this settings contract rather than bypass it.

- A child or refinement pass may propose a setting/profile change.
- It may preview a transaction and attach evidence.
- It may not silently apply risky, auth, network, keyboard, controller, or persistent-policy changes.
- Experiments should record profile name, effective settings version, model/effort, evidence, and outcome.
- One controller and one writer remain mandatory.
- Failed experiments should restore a known receipt or branch/checkpoint instead of guessing at prior values.

This makes proposed self-improvement reproducible without granting silent self-modification.

## Candidate Roadmap

These are candidate lanes, not commitments in the primary roadmap.

| ID | Slice | Outcome | Risk |
| --- | --- | --- | --- |
| CX-0 | Research/policy | this optionality and turn-control contract | low, complete as research |
| CX-T0 | Correlated operator transport | shared bridge envelope, request/result receipts, thin CLI, Control Panel sender parity | low-medium, complete as Window 23 Slice 1 |
| CX-1 | Settings registry | typed read-only source of truth plus strict validation and generated inventory | medium, complete as Window 23 Slice 2 and expanded to 22 controls in Slice 4 |
| CX-2 | Transactions/receipts | atomic preview/apply, expected version, effective readback, rollback | medium, complete as Window 23 Slice 3 for runtime-session settings |
| CX-3 | Control Panel | transaction client, source/maturity/details, atomic apply/rollback, Capture Now | medium, complete as Window 23 Slice 4 |
| CX-T1 | Mutation admission | fsynced journal-before-dispatch, duplicate suppression, payload conflict, terminal recovery, uncertain/no replay | medium, complete as Window 23 Slice 5 |
| CX-T2 | Operator shell | generated command/settings discovery, context-aware completion, local safe history, no OS escape | low-medium, complete as Window 23 Slice 6 |
| CX-T3 | Shared dashboard | one structured read-only status/settings/admission/recent-receipt model for terminal and Control Panel | low-medium, complete as Window 23 Slice 7 |
| CX-4 | Stepwise observe | one action, settle, capture, later turn; batch bounds and stop-on-uncertain | medium-high |
| CX-5 | Event timeline/hooks | canonical item IDs/status/timestamps plus trusted bounded hooks | medium-high |
| CX-6 | Interactive adapter | in-turn tool calls, result reinjection, steer/interrupt/approval | high, separate transport |
| CX-7 | App Server bridge | optional read-only intake first, later bounded control with leases | high, separate lane |

Recommended implementation order:

1. CX-T0 correlated operator transport and thin CLI - complete as Window 23 Slice 1;
2. CX-1 read-only settings registry - complete as Window 23 Slice 2;
3. CX-2 transactions and receipts - complete as Window 23 Slice 3;
4. CX-3 GUI transaction-client migration and Capture Now - complete as Window 23 Slice 4;
5. CX-T1 mutation admission and uncertain/no-replay recovery - complete as Window 23 Slice 5;
6. CX-T2 operator shell, autocomplete, discovery, and history over the same API - complete as Window 23 Slice 6;
7. CX-T3 shared structured terminal/Control Panel dashboard - complete as Window 23 Slice 7;
8. choose the next lane explicitly, with CX-4 stepwise observation first in the planned queue only if opened;
9. CX-5 canonical timeline and hooks after a separate review; and
10. evaluate CX-6/CX-7 only after the control plane is trustworthy.

CLI and Control Panel `Capture Now` use the existing demand-capture command and do not alter scheduler cadence, queue order, execution mode, or approval state.

Window 23 Slice 1 provided correlation rather than idempotency: `request_id`, `message_id`, and `client_id` reached terminal command results. Slice 5 now adds the separate mutation-admission layer described below. See `aurora-control-plane-cli-reference.md`.

Window 23 Slice 2 provided the first shared typed read plane: 19 high-value settings, 33 aliases, strict key/value validation, system-profile default lookup, lock/source/scope/maturity/apply metadata, and CLI `settings list|get|describe`. Slice 4 promoted capture wake, debounce, and post-action settle to first-class entries, bringing the registry to 22 settings and 36 aliases.

Window 23 Slice 3 added opaque settings versions plus `settings version|preview|apply|rollback`. It validates the full batch before mutation, invokes the existing runtime setters under one transaction lock, verifies effective readback, rejects stale versions and locked settings without partial apply, and issues bounded same-session single-use rollback handles. At that slice boundary it did not yet provide durable admission/no-replay, persistent settings writes, or Control Panel migration. See `aurora-settings-registry-reference.md`.

Window 23 Slice 4 makes the Control Panel a client of that contract. It filters semantic no-ops, requires a fresh effective snapshot, performs receipt waits off Tk's event thread, never automatically replays uncertainty/conflicts, exposes details and rollback, and keeps nonregistered commands explicitly independent. A bounded runtime proof covered preview, apply, exact rollback, and correlated Capture Now.

Window 23 Slice 5 adds `aurora_mutation_admission_v1`: Aurora fsyncs a normalized `client_id + request_id` reservation before dispatching a mutating external command, stores the command name and digest, reconciles terminal outcomes, suppresses exact duplicates, rejects changed-payload conflicts, and reports unresolved admissions as uncertain without automatic replay. Read-only commands remain repeatable. This supplies the safety boundary needed by later stepwise control, but does not add persistent settings, leases, peer-agent delivery, or broader authority.

Window 23 Slice 6 adds a dependency-free local operator shell over the same service. Generated command discovery, setting-aware completion, Windows line editing, and sensitive-command-excluding history improve inspectability without creating an OS command escape or a second execution path. Known direct runtime commands still become ordinary correlated bridge requests; unknown raw forms require explicit `command`/`send`, and interrupted or uncertain writes are never automatically replayed.

Window 23 Slice 7 adds `aurora_operator_dashboard_v1` plus sanitized `aurora_operator_dashboard_event_v1` rows. The terminal's one-shot/watch text and JSON/JSONL modes and the Control Panel Dashboard tab/popout consume the same structured status, settings, receipt, and mutation-admission snapshot rather than scraping each other's rendered output. Raw command arguments are excluded from dashboard events, and the dashboard adds no replay, persistence, model calls, worker spawn, or broader control authority.

## Acceptance Gates for Future Implementation

A settings/turn-control slice is not complete until:

1. registry validation rejects unknown keys and invalid values;
2. GUI, command, CLI, status, profile, and documentation surfaces agree;
3. an all-or-none settings transaction test proves no partial apply;
4. stale `expected_version` is rejected;
5. effective values report source, scope, lock, maturity, and apply timing;
6. persistent changes have export and rollback evidence;
7. recovery releases held pointer/keyboard state;
8. screenshot-now does not alter scheduler or pending-action state;
9. stepwise mode proves one action occurs before each observation; and
10. interactive mode, if present, proves tool result reinjection inside the same turn rather than a later scheduled turn.

For CX-2/CX-3, registry, atomicity, stale-version, effective-readback, runtime-session rollback, CLI/GUI agreement, and screenshot-now isolation passed focused tests and bounded runtime proofs. Persistent-change rollback remains outside the contract because writes deliberately support only `runtime_session` scope.

## Staleness Watch

Recheck this note when any of these change:

- installed Codex CLI or desktop app version;
- local app-server schema;
- Aurora model transport;
- Control Panel settings apply path;
- scheduler/action batching semantics;
- Computer Use Windows background/foreground behavior;
- feature maturity names; or
- auth, approval, and managed-constraint behavior.

Do not copy a Codex changelog feature into Aurora merely because it exists. Verify the local Codex version, the Aurora need, the required transport, and the intended default first.
