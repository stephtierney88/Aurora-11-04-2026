# Aurora Typed Settings and Transactions Reference

## November 5 — subscription stream boundary (Implementation 53)

Registry: **48 settings / 387 bindings / 157 reviewed contracts**. `auth.subscription_policy` / `SET_SUBSCRIPTION_POLICY([legacy|bounded])` is operator-only for changes, auth-locked, session-only and effective on the next subscription request. The startup environment selector is `AURORA_SUBSCRIPTION_POLICY`; legacy remains the default. Zero arguments query. Shared CLI/Advanced/Preview/Apply/Undo observe the same value; existing saved preference documents are unchanged. This does not change auth route, enable inference, retry a failed request or switch billing.

Bounded runs one hidden owned inference process with 90-second socket-idle and a 180-second parent inference deadline. Cancel terminates that local worker; validated complete output alone can return. Auth/catalog preflight stays in the parent with existing timeouts/cooperative checks, so the deadline is not a full-request or provider-side cancellation guarantee. Safe phase/timing/cleanup diagnostics are in Model Status. The legacy stream reader remains available. Read Implementation 53 (development reference omitted from this snapshot) for evidence and limits.

## November 5 — task outcome opt-in (Implementation 46)

Current registry **40 settings / 379 bindings / 149 reviewed contracts**; preview reset 36, persisted preference fields remain 69. `task.outcome_reporting` / `SET_TASK_OUTCOME_REPORTING([on|off])` uses the execution lock and is operator-only for changes; zero arguments query. Default off preserves prior behavior. Startup `AURORA_TASK_OUTCOME_REPORTING` and session commands/Advanced/Agent controls share one authority; the setting latches at the next bounded task, so changing the configured value does not silently rewrite an active task. The panel displays both active and next-task values. Preview/Apply/Undo and reset affect configuration, not an already recorded outcome. No new saved-profile field is claimed.

`SHOW_TASK_STATUS()` and `REPORT_TASK_OUTCOME(task_id, done|wait|approval|error, reason)` have reviewed standalone controller contracts. The latter stops automatic continuation only for the exact opted-in task and records an unverified declaration. It does not approve pending work, complete goals or cancel admitted actions. Full semantics are in the [scheduler reference](scheduler-reference.md).

## November 5 — reviewed receipt scope (Implementation 44)

Current registry **39 settings / 376 bindings / 146 reviewed contracts**; preview reset 35, persisted preference fields remain 69.

`scheduler.readback_scope` / `SET_READBACK_SCOPE(discovery|reviewed)` is a session-only Advanced selector using the reasoning lock, shared typed commands and versioned Preview/Apply/Undo. Zero arguments query. Default `discovery` preserves history-based lookup delivery; `reviewed` additionally captures future supported model-command receipts and includes pending evidence in the next bounded-task request. It is not backfilled from old logs. Startup configuration: `AURORA_READBACK_SCOPE=reviewed`; existing shell/CLI raw-command access remains.

Automatic continuation separately requires `SET_READBACK_WAKE(on)` and `SET_TASK_CONTINUATION(bounded)`. Selecting receipt scope does not enable inference, change execution permission or billing. Retained receipts are bounded and task-scoped; changing back to discovery suppresses their automatic wakes/inclusion while retaining inspectable records. No failed command or uncertain request is automatically replayed. Read Implementation 44 (development reference omitted from this snapshot) for exact scope and limits.

## November 5 — CF1b2 request limits (Implementation 43)

Current registry: **38 settings / 375 bindings / 145 reviewed contracts**; reset 34, runtime preference snapshots 69 fields. Counts in older dated sections are historical.

- `capture.request_timeout_seconds` / `SET_CAPTURE_REQUEST_TIMEOUT(seconds)`: finite nonnegative seconds, default 0 (unlimited). CLI `--capture-request-timeout`, environment `AURORA_CAPTURE_REQUEST_TIMEOUT`.
- `capture.request_max_attempts` / `SET_CAPTURE_REQUEST_ATTEMPTS(count)`: nonnegative integer, default 0 (unlimited). CLI `--capture-request-attempts`, environment `AURORA_CAPTURE_REQUEST_ATTEMPTS`.
- Both are latched on the next request, use the screenshot_interval lock, shared validation/receipts/source/scope and Preview/Apply/Undo. Zero arguments query. Saved profiles and preview reset include them. Existing requests retain their original limits when settings change.
- Deadline includes settle, acquisition, drawing and publication admission. Attempt exhaustion occurs on final failure or the final attempt's existing one-second publication lease; a dropped/slow pipeline can exhaust that lease. Legacy recapture shares its parent attempt. Heartbeats cannot bypass the cap.
- Limits fence request completion; they do not interrupt a running native call. Inspect `capture_service.current_failure`, `last_failure` and `acquisitions_inflight`. Explicit fresh capture or Cancel acknowledges a terminal wait; a never-returning native call may require runtime restart. No new defaults were applied to the user's saved configuration.

Implementation 43 (development reference omitted from this snapshot) owns verification and remaining boundaries.

## November 5 — CF1b geometry controls

The registry now has 36 settings (373 command bindings, 143 reviewed contracts). Preview reset has 32 settings; runtime preference snapshots contain 67 fields. Historical counts below describe their dated revisions.

- `capture.geometry_policy`: `verified` (default) or `legacy`; command `SET_CAPTURE_GEOMETRY_POLICY(value)`, zero arguments query. Verified geometry uses explicit physical rectangles; legacy retains default desktop grabs/startup scaling/current-window recapture and unknown calibration.
- `capture.target`: `legacy_options` (default), `primary`, `virtual`, `foreground`; command `SET_CAPTURE_TARGET(value)`, zero arguments query. The selector takes effect on the next verified acquisition. Legacy geometry ignores it, as disclosed by setting notes. Existing native-cursor flag wins first (primary), then current_window, then entire_screen, then primary.
- Both use the screenshot_interval lock and shared versioned settings Preview/Apply/Undo, Advanced controls, saved profiles, CLI `--capture-geometry-policy` / `--capture-target`, and `AURORA_CAPTURE_GEOMETRY_POLICY` / `AURORA_CAPTURE_TARGET`. Existing in-flight frames retain their own geometry.
- `capture.provenance_policy` remains independent: acquisition freshness versus legacy counter checks. Capture mode, cadence, demand and inference scheduling remain separate. Geometry describes pixels; it does not convert or qualify existing input backends.

Implementation 42 (development reference omitted from this snapshot) owns validation and native-testing limits.

## September 7 defaults service — Implementation 12 / 4B4b

The four existing defaults commands now return default_profile_results (aurora_default_profile_result_v1) with before/after profile state and content versions, requested/changed/attempted fields, explicit failure/restoration and file evidence where relevant. Failures stop the remaining command batch; duplicate receipts retain original evidence without another apply/save.

- SAVE_PERSONAL_DEFAULTS() atomically saves the existing 60-field profile format. It retains unknown fields from a valid existing document. SHOW_DEFAULT_PROFILES() distinguishes available, missing, invalid and unreadable files; the panel shows the same status.
- APPLY_PERSONAL_DEFAULTS() and APPLY_SYSTEM_DEFAULTS() retain full reapply by default, including setter/refresh effects and successful-apply drip pruning. Optional mode changed_only skips unchanged setters; mode reapply makes the default explicit. Both are available through CLI/raw commands and the panel's Advanced/raw-command access; existing Apply buttons keep the default.
- Validate the complete profile and its locks before mutation. Retain old partial profiles, blank optional fields, boolean/off/zero values, all existing fields, negative/all high-detail modes and custom six-knob scheduler state. Explicit fields override a named scheduler preset as before.
- A failed apply attempts state restoration and reports restored or uncertain from readback. Pruning waits until settings validation/readback succeeds. This does not promise reversal of already-rendered overlays, feedback, OS effects or external writers.
- Files use bounded 8 MiB reads and destination-local temporary/fsync/replace/readback. Malformed/unreadable files are not silently replaced. Repair or move a malformed personal file before saving a new one. Unknown fields remain unapplied and reported; they are not arbitrary instructions.
- Profile scope remains its existing 60 fields. The 23-setting registry is separate and authoritative for registered values; Live, transport, one-turn inference, held inputs and credentials are not newly persisted in profiles. Raw defaults commands do not add version preconditions or cross-process CAS.

Keep the capability commitment at docs/notes/aurora_capability_compatibility.md. Evidence: docs/reviews/2026-09-06/implementation-12.md. 4B4d local history is implemented; 4B4e retention/prompt-state controls are next; native testing remains paused. Earlier Window 23 details below describe the foundation.

## September 6 registry extension

There are now 23 registered settings / 24 raw setting names. `model.transport` is an advanced, session-only enum (`chat_completions` or `responses`) under the models lock. It has observed/versioned readback and does not enable Live or persist in defaults. Selection is reversible; active/draining model I/O blocks changes. Astra adds model-specific max effort. See [adaptive reasoning](adaptive-reasoning-reference.md).

Freshness: 2026-09-05. Implementations 06/07 add shared raw-setting validation, transaction admission and typed setting/lock controls to the existing Window 23 foundation.

## Current Status

Window 23 Slices 2-4 implement the settings contract and are validated locally. Slice 5 adds durable admission/no-replay around recognized external mutations without changing the registry's runtime-session scope; Slice 7 reuses the same readbacks in the shared read-only dashboard without adding another settings store or write path.

- `aurora_settings_registry.py` owns typed definitions, aliases, constraints, defaults paths, readback, and opaque settings-version calculation.
- `aurora_settings_transactions.py` owns the request token, complete-batch planner, command invocation metadata, and transaction schemas.
- `aurora2.py` executes plans under one runtime lock through the existing setting command handlers and exports transaction status.
- `aurora_cli.py` exposes readback plus preview, apply, and rollback commands.
- `aurora2_control_panel.py` is a nonblocking transaction client with preview, version/readback details, atomic apply, receipt visibility, same-session rollback, and a read-only Dashboard settings summary over the shared snapshot.

This remains one Aurora runtime. The registry and transaction modules do not own a parallel settings store.

September 5: all 22 low-level setters use `coerce_setting_value`; 23 raw command names derive contracts from the same definitions, including the backward-compatible reasoning-effort command alias. `SettingDefinition.command_aliases` and `value_aliases` make those accepted spellings discoverable. Value aliases apply to writes; observed state must still contain valid canonical values. Non-finite numbers and unknown game/scheduler profiles are rejected instead of silently selecting another value. No-argument raw commands query; one value sets; extras reject the complete batch before prior actions. `SET_IMAGE_DETAIL()` now queries and errors return explicit failure.

`execute_registered_setting_command` shares `SETTINGS_TRANSACTION_LOCK` with transactions, checks locks at execution and obtains each before/after readback and version from one in-memory snapshot. Correlated `setting_results` use `aurora_setting_command_result_v1`: observed value, not-started rejection or uncertain partial/readback failure. Failed reviewed setters block the batch tail; duplicates preserve original evidence without replay. Raw setters do not require an expected version or gain batch rollback. Encoded transactions retain their existing atomic preview/apply/rollback service and receipts. Lock/toggle mutations outside these 23 wrappers remain a later review boundary.

Implementation 07: five zero-argument shortcuts reuse `setting_results`: live and global image-detail toggles, and GB/PYAG/none action-mode shortcuts. A toggle requires an effective current value. Low image detail toggles to high; every other supported detail toggles to low. `LOCK_SETTING([lock])` and `UNLOCK_SETTING([lock])` query when omitted, or change one runtime lock using all existing aliases. Their `lock_results` contain operation/key, before/after lock snapshots and versions, success/effect status/reason and original input. Lock mutations and setting shortcuts use the same transaction lock as raw setters. Failed controls block the tail; duplicates retain observed evidence. Runtime locks are configuration controls, not an access-control boundary.

Encoded preview/apply/rollback requests are statically validated before any batch action. Bounded strict base64/JSON rejects malformed tokens, duplicate JSON fields and non-finite JSON numbers. `inspect_settings_transaction_request` supplies the same registry/shape/conflict checks to admission and the planner; runtime versions, current values, locks and rollback handles are checked at execution. Any rejected/failed transaction blocks the batch tail. Unexpected execution failure produces `failed_uncertain` with available versions and no automatic replay; the receipt does not claim unchanged state. Admission failures may have only the outer rejection receipt. Existing atomic apply restoration and explicit rollback remain; preceding raw commands are outside their rollback scope.

Implementation 08 action-mode semantics: a known `SET_ACTION_MODE(value)`, GB/PYAG/none shortcut, or successful apply-transaction intent guides later unprefixed actions during admission. Queued actions keep the resolved namespace/backend/key. Query and preview do not project changes. Rollback/default-profile/visual-probe outcomes require an explicit action prefix or a following explicit mode selector before later implicit actions. Failed reviewed mode writes/transactions block the tail. The execution-time settings service and its version checks remain authoritative; projected mode does not bypass a lock or guarantee the transaction will succeed.

Validation: The full suite passed 226 tests in 97.777 seconds. Guarded runtime proof: 57 receipt checks in 18.83 seconds, exit 0; WAIT cancellation receipt 117.44 ms and shutdown receipt 163.72 ms. Offline/live-lock startup state was verified. Input/capture/model guards stayed unused and zero captures were recorded. See Implementation 08. These proofs do not establish credentials/provider availability, native app effects, GUI usability or a clean runtime installation.

Current schemas:

- registry: `aurora_settings_registry_v1`;
- readback: `aurora_setting_readback_v1`;
- snapshot: `aurora_settings_snapshot_v1`;
- version: `aurora_settings_version_v1`;
- raw command result: `aurora_setting_command_result_v1` in `setting_results`;
- transaction request: `aurora_settings_transaction_request_v1`;
- transaction plan: `aurora_settings_transaction_plan_v1`;
- transaction receipt: `aurora_settings_transaction_receipt_v1`; and
- rollback handle: `aurora_settings_rollback_handle_v1`.

The registry contains 22 canonical high-value settings and 36 aliases with boolean, enum, float, and non-empty string validation.

## CLI

Read and discovery:

```powershell
.\aurora.cmd settings list
.\aurora.cmd settings list --category scheduler
.\aurora.cmd settings get runtime.live
.\aurora.cmd settings describe capture.screenshot_interval
.\aurora.cmd settings version
```

Transactions:

```powershell
.\aurora.cmd settings preview inference.temperature=0.25 scheduler.min_gap_seconds=0.65
.\aurora.cmd settings apply inference.temperature=0.25 scheduler.min_gap_seconds=0.65
.\aurora.cmd settings apply runtime.live=off --expected-version <sv1:...>
.\aurora.cmd settings rollback <settings-rb-...>
```

Every command also works through `auroractl.cmd`. `get`, `describe`, `preview`, and `apply` accept canonical keys or documented aliases.

Mutating settings commands require an active runtime. They do not leave a delayed mutation in the durable inbox while Aurora is stopped. When `--expected-version` is omitted, the CLI derives it only from a fresh effective runtime snapshot.

## Registered Core

| Canonical key | Type / constraint | Runtime readback | Lock |
| --- | --- | --- | --- |
| `auth.mode` | `api_key`, `codex_oauth`, `auto` | `modes.auth` | `auth` |
| `runtime.live` | boolean | `modes.live` | `live` |
| `runtime.execution` | `safe`, `assist`, `auto` | `modes.execution` | `execution` |
| `runtime.action` | `none`, `gb`, `pyag` | `modes.action` | `action` |
| `game.profile` | `firered`, `blue` | `modes.game_profile` | none |
| `model.text` | non-empty model name | `models.text` | `models` |
| `model.vision` | non-empty model name | `models.vision` | `models` |
| `model.reasoning` | non-empty model name | `models.reasoning` | `models` |
| `inference.reasoning_effort` | `minimal` through `xhigh` | `models.reasoning_effort` | `reasoning` |
| `inference.verbosity` | `low`, `medium`, `high` | `models.verbosity` | `reasoning` |
| `inference.temperature` | float `0.0..2.0` | `models.temperature` | `temperature` |
| `scheduler.profile` | named profile | `scheduler.profile` | `reasoning` |
| `scheduler.mode` | `per_capture`, `event`, `hybrid` | `scheduler.mode` | `reasoning` |
| `scheduler.heartbeat_seconds` | float, minimum `0.25` | `scheduler.heartbeat_seconds` | `reasoning` |
| `scheduler.min_gap_seconds` | float, minimum `0.0` | `scheduler.min_gap_seconds` | `reasoning` |
| `scheduler.capture_wake_enabled` | boolean | `scheduler.capture_wake_enabled` | `reasoning` |
| `scheduler.capture_wake_debounce_seconds` | float, minimum `0.0` | `scheduler.capture_wake_debounce_seconds` | `reasoning` |
| `scheduler.post_action_settle_seconds` | float, minimum `0.0` | `scheduler.post_action_settle_seconds` | `reasoning` |
| `capture.screenshot_interval` | float, minimum `0.02` | `modes.screenshot_interval` | `screenshot_interval` |
| `capture.demand_enabled` | boolean | `scheduler.demand_capture_enabled` | `screenshot_interval` |
| `vision.image_detail` | `low`, `high`, `auto`, `original` | `advanced.image_detail` | none |
| `runtime.live_init` | boolean | `modes.load_live_init_prompt` | `live_init` |

`scheduler.profile=custom` remains readback-only. A transaction cannot combine `scheduler.profile` with any manual scheduler leaf change because the profile owns mode, heartbeat, min gap, capture wake, debounce, and post-action settle as one bundle.

## Readback and Version

`value_status` means:

| Status | Meaning |
| --- | --- |
| `effective` | Runtime is active and the exported state is fresh. |
| `stale` | Runtime is active, but the export is older than the freshness threshold. |
| `last_observed` | Runtime is stopped; the value is historical. |
| `invalid_runtime_value` | Exported value violates the registry contract. |
| `unavailable` | The setting path or state export is absent. |

`source.kind=runtime_state_export` names the evidence source, not a layered-config winner. Most origins remain `not_tracked`; `game.profile` reuses its existing source field. Compatibility defaults come from exported `defaults.system_profile` when available.

The opaque `sv1:<sha256>` settings version changes when any registered value or matching lock changes. Scheduler capture wake, debounce, and settle are first-class registered values, so named-profile and custom-leaf changes share one version contract. Unrelated runtime state does not change the version.

## Atomic Contract

Preview and apply perform complete-batch validation before any setting mutation:

- strict request/schema/operation/scope checks;
- canonical alias resolution and duplicate-key rejection;
- all type, enum, and numeric validation errors collected together;
- `expected_version` comparison;
- current-value availability checks;
- per-setting scope and lock checks; and
- scheduler-profile conflict checks.

Apply then runs changed rows through Aurora's existing command handlers under `SETTINGS_TRANSACTION_LOCK`. Control-panel state export and model-turn admission share that lock, so they do not observe a partially applied batch. Effective values are read back before success is reported.

If an apply step or effective readback fails, Aurora restores attempted rows. A failure receipt distinguishes `failed_rolled_back` from `rollback_failed`. Successful non-noop apply returns an in-memory rollback handle tied to the exact after-version.

Rollback is accepted only while:

- the handle is available in the same runtime session;
- caller `expected_version` matches current settings;
- current settings still match the handle's recorded after-version; and
- no covered lock/value or scheduler-bundle field has diverged.

Scheduler-profile rollback restores all six bundled scheduler fields, including capture wake, debounce, and settle. Handles are single-use, bounded in memory, and expire at runtime shutdown.

## Boundaries

- Writable scope is only `runtime_session`; personal/project persistence remains off.
- Transaction IDs are correlation, not durable idempotency. Slice 5 duplicate suppression is keyed by the enclosing external request's normalized `client_id + request_id`, not by the settings transaction ID.
- Neither CLI nor runtime automatically replays an uncertain mutation.
- `--no-wait` is operator-selected uncertainty; inspect receipts/state before retrying.
- Preview changes receipt/audit metadata but does not change registered settings.
- Control Panel registered-setting Apply is atomic; `Apply Additional` and documented profile follow-up commands remain independent bridge commands.
- No auth default, model call, agent spawn, desktop action, sibling-app integration, or Portal path was broadened.

## Control Panel Boundary

Window 23 Slice 4 moved the Control Panel's 22 registered Basic/Advanced values onto the same transaction service as the CLI.

- `Preview Atomic` validates and displays the projected diff without mutating registered values.
- `Apply Atomic` derives a fresh effective expected version, submits one correlated transaction, waits off the Tk thread, and never automatically retries an uncertain or conflicted write.
- `Settings Details` shows version, source, value status, lock, scope/maturity/risk, and apply timing.
- `Rollback` uses the latest successful same-session handle and restores its exact baseline only while the handle/version guards still pass.
- named scheduler profiles submit the profile only; editing any scheduler leaf selects `custom` and submits all six leaves.
- `Capture Now` uses `REQUEST_SCREENSHOT_CAPTURE(control_panel)` without changing cadence or approval state.

The broader `SETTING_SAFETY_INVENTORY` remains useful operator guidance. Controls not yet in the registry use `Apply Additional` or clearly disclosed post-transaction independent commands. They are sent only after a successful registered apply when part of a model/operator profile and are not described as atomic.

## Validation Evidence

Validation on 2026-08-08 used `C:\Anaconda\envs\aurora\python.exe`.

- Six-file `py_compile` passed for runtime, Control Panel, control plane, registry, transaction module, and CLI.
- Thirty-one focused tests passed: 7 transport, 12 registry/readback/version, 7 transaction-contract, and 5 Control Panel client tests.
- Complete-batch tests cover malformed/unknown/duplicate keys, invalid values, locks, version conflicts, and scheduler bundle conflicts.
- Bounded offline no-UI proof produced 7 correlated transaction receipts: `previewed`, `applied`, stale-version `rejected`, `rolled_back`, lock `rejected`, scheduler-profile `applied`, and scheduler-profile `rolled_back`.
- Preview preserved values/version; a two-setting apply changed both with effective readback; stale and locked batches changed neither value; rollback restored the exact baseline version.
- A custom scheduler state survived `custom -> responsive -> rollback` with mode, heartbeat, min gap, capture wake, debounce, and settle all restored exactly.
- A real withdrawn Tk panel constructed all transaction controls and the nine-command episodic follow-up builder without layout/runtime errors.
- A bounded offline runtime proof drove the Control Panel client itself: the 22-setting snapshot was effective, preview preserved the exact version, apply changed temperature `0.0 -> 0.2` and the version, rollback restored the exact baseline version/value, and Capture Now returned a correlated `processed` receipt.
- A separate actual `--with-ui` smoke started both runtime and Control Panel, exported 22 settings plus a version, processed correlated `SHOW_RUNTIME()` and capture receipts, and shut both processes down gracefully.
- Final baseline was live off, temperature `0.0`, scheduler `balanced/hybrid`, min gap `0.55`, and zero locks.
- Runtime shutdown was clean, stderr was empty, and zero Aurora runtime/Control Panel processes remained.
