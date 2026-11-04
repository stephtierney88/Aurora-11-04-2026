# Aurora Control Plane and Operator CLI Reference

## Local history controls — October 1 / Implementation 14

INIT(text...) and PIN(text...) retain the important-history gates; disabled retention produces an explicit failure without deleting old Init. CLEAR()/CLEAR_NONPIN() keep typed or legacy Init/Pinned/Handoff entries. CLEAR_NOPIN%(percentage[, random|oldest|newest]) keeps random selection by default and removes only unprotected positions. CLEAR%(percentage) retains its total recency budget with protected priority; 100 clears everything. Percentages must be finite 0–100. Existing command names and valid modes remain.

EDIT_MSGS(timestamp,text[,timestamp,text...]) validates every pair/target before publishing, permits empty text and edits the first timestamp match per pair. DELETE_MSG(timestamp) retains all-match deletion. Unknown targets fail and stop the batch tail. Timestamps can collide; use the returned added_timestamps for new entries while respecting these legacy selection semantics. Raw history commands have no compare-and-swap or cross-command rollback.

SAVECH([path_prefix]) exports a detached text snapshot with image previews. It returns its actual path, bytes/hash and exported_history_version, avoids overwriting earlier same-second exports and reports cleanup/readback failures. This is not a restorable checkpoint or atomic file publication. DHISTORY() keeps full terminal display and adds typed counts/version readback.

Receipts contain history_command_results using aurora_history_command_result_v1: before/after versions/counts, removed/edited/added counts, added timestamps and cancellation/invalidation evidence. Explicit changed history cancels stale model work and invalidates active Responses continuation; RESET_RESPONSES_SESSION() remains an explicit next action. No-op clear/read/export does not cancel. A restored local failure can retain model/provider context effects; incomplete invalidation is uncertain. Duplicate requests retain original evidence. Panel snapshots expose history_control; CLI/raw/panel command paths share the service.

All 358 bindings remain and 89 are reviewed. All existing defaults, transports and controls remain available; native testing is paused. Retention/decay/image-limit and advanced prompt/context services remain the next review. Evidence: docs/reviews/2026-10-01/implementation-14.md.

## Pending queue service — September 7 / Implementation 13

The nine existing QUEUE_PENDING / INSERT_PENDING / REPLACE_PENDING / OVERRIDE_PENDING / APPROVE_PENDING / CLEAR_PENDING_COMMANDS / CLEAR_PENDING / SHOW_PENDING_COMMANDS / SHOW_PENDING bindings have shared reviewed contracts. No command or queue mode was removed. A wrapper takes exactly one command, or one quoted batch; nested parameters are validated before earlier commands in the outer batch run. Normal/insert/replace, support scoring, explicit operator approval and eligible auto approval remain. Sub-agent insertion still requires its exact dry-run confirmation and subsequent manual approval.

SHOW_PENDING() returns item IDs, queue content version, held/reserved/uncertain state, frozen action_routes and recovery evidence. Existing index, all/*, risk, category, exact command, family and semantic-label selectors remain. APPROVE_PENDING() defaults to first; CLEAR_PENDING() defaults to all. A recognized category/risk with no matches changes nothing. Every selector is checked, even after all.

Prefer APPROVE_PENDING(id:pending-<id>,version:<hash>) or CLEAR_PENDING(id:pending-<id>,version:<hash>) using exact readback values. IDs prevent index-shift targeting; the optional version also detects changes to a held representative, support or queue order. Index-only callers retain execution-time selection. The panel uses IDs plus its displayed version and keeps a stable selected item across refresh; older snapshots fall back to index behavior.

Receipts use pending_command_results / aurora_pending_command_result_v1 with before/after versions/counts and affected or removed IDs. Approval reports submissions and distinct pending_attempt_id values. The subsequent command_result carries pending_id and pending_attempt_id. Queued means accepted, not executed or observed in an application. Duplicate delivery preserves the original receipt without replay.

An unstarted submission remains held; a lost/uncertain acknowledgement remains quarantined and cannot auto-approve or be supported/replaced/expired away. Inspect correlated execution evidence before explicitly clearing/requeueing. Clearing an uncertain record does not cancel work that may already have been accepted. Reserved items cannot be cleared mid-submission. Cancellation retains the original work generation and stops later unstarted approvals.

Several approved items remain independent queued requests for compatibility. Failure of a later execution does not revoke already accepted siblings. Use one quoted pending batch when commands have dependencies and need reviewed stop-tail semantics inside a request. Raw batches have no cross-command rollback. Queue identity/reservations are process-local and are not a restart-persistence guarantee.

Capability reminder: docs/notes/aurora_capability_compatibility.md. Native capture/input/GUI acceptance remains paused; this service is verified by guarded offline tests. Evidence: docs/reviews/2026-09-07/implementation-13.md.

## Adaptive reasoning control

Implementation 09 adds opt-in Astra Responses adaptive reasoning. SET_MODEL_TRANSPORT(responses) selects the session transport without enabling Live; RESET_RESPONSES_SESSION() explicitly starts a new provider chain. Existing one-turn effort requests drive configuration_update while the original request baseline stays fixed; the next normal turn explicitly restores its selected policy. Model Status distinguishes selected/effective/API-reported effort and exposes continuation, limits and uncertainty. Commands: SHOW_MODEL_STATUS(), SHOW_NEXT_INFERENCE(), SET_NEXT_REASONING_EFFORT(high, note), RESET_RESPONSES_SESSION(). `model.transport` uses the existing settings service; all normal authorization/lock/receipt rules apply. See [adaptive reasoning](adaptive-reasoning-reference.md).

Freshness: 2026-09-05; reviewed desktop/registered-setting contracts, source-backed discovery, client-scoped receipts, whole-batch admission, bounded inbox framing, responsive cancellation and immutable capture references.

## Command discovery and contract coverage

The actual runtime and explicit desktop dispatch tables own callability. `aurora_reference_maps/commands/commands.json` contains all 339 runtime commands and 19 `pyag:` bindings, aliases, source locations, signature provenance and reviewed coverage. `GB:` is a controller-input namespace; standalone `GB()` and `PYAG()` are not commands. The repaired `TASKS()` binding accepts ordinary case-insensitive command input. CLI shell routing also recognizes explicit desktop commands.

Use `aurora commands WAIT --detail --json` for full parameter/result coverage, `aurora commands pyag: --limit 30 --json` for desktop discovery, or MCP `aurora_search_commands` with `detail=true`. Compact output is the default. The MCP tool remains observation-only. A source/hash mismatch refuses stale discovery and requests regeneration.

WAIT and all 19 desktop bindings now have reviewed pre-dispatch positional validation. Discovery detail includes types, defaults, arity, finite/minimum constraints, key-space requirements, effects and desktop result schemas. The runtime validates the complete active key/text set before any batch member executes. For example, `SET_TIME_LOGGING(on); pyag:press(a,2.5)` rejects the complete batch before the setter runs. WAIT still requires exactly one finite, non-negative duration. Omitted unquoted positions are rejected; quoted empty strings and trailing commas retain their syntax.

Desktop outcomes are stored in each correlated receipt's `desktop_results` array using `aurora_desktop_result_v1`: `command`, `success`, `effect_status`, `reason`, plus the original `input`. `submitted` means the input API completed, not that the application reacted correctly; `observed` is used for confirmed foreground-window focus. `not_started` denotes rejected execution parameters; `uncertain` means a failed or cancelled action may have partially occurred. Admission rejection happens earlier and need not contain a desktop result. Any failed desktop action stops the remaining batch and records `blocked_commands`; identical terminal redelivery preserves that evidence without redispatch. Inspect and reconcile uncertainty before issuing a new request; the runtime does not automatically retry input through another backend.

September 5 routing repair: explicit `PYAG:press(a)` sends literal desktop `a`, even with an emulator foreground. `GB:press(a)` uses the admitted game mapping/backend and confirmed focus; configured `pyautogui` game input now preserves that translation/focus path. `PYAG_MODE(); press(a)` and `GB_MODE(); Start` resolve in order; apply transactions changing `runtime.action` also guide later implicit actions. Preview/query commands do not change that projection. After rollback/default-profile/visual-probe commands with unknown projected mode, use explicit prefixes or a mode selector before an implicit action. Malformed/ambiguous batches reject before prior actions. Queued actions retain their admitted route even when mode/backend/mappings later change.

`desktop_results[].action_route` records namespace, explicit/implicit origin, projected action mode, backend and requested/effective key for prepared actions. It survives failure, cancellation and duplicate delivery. The route record is immutable and JSON/pickle-compatible; its execution scope is local to the current thread and restores nested callers. This freezes action meaning, not target-window identity for literal desktop input; focus confirmation and application effects remain separate. Indefinite holds still need attributable ownership/release work in the next slice.

Timed holds and chords attempt key/button release on completion, cancellation or partial setup failure. Explicit indefinite holds require matching releases in the appropriate desktop/GB context; release failure remains uncertain. Native calls already running may finish before a cancellation checkpoint.

The 22 registered settings now cover 23 raw command names, including `SET_REASONING_EFFORT` / `SET_SESSION_REASONING_EFFORT`. `aurora commands SET_TEMPERATURE --limit 1 --detail --json` exposes registry-owned types, bounds, aliases, lock key, application timing and result schema. No argument reads the current value; one sets it; extras reject before any batch action. All underlying registered setters use registry coercion, including finite-number and strict profile/mode validation. Existing value aliases remain. Model names remain open non-empty strings; successful readback does not establish provider/model availability.

Each raw-setting receipt includes `setting_results` (`aurora_setting_command_result_v1`): command/key/operation, normalized requested value, before/current value, value status, before/after settings versions, success/effect status/reason and original input. `observed` proves the registered runtime readback at execution; `not_started` denotes a rejected value/lock before the handler; `uncertain` denotes possible partial effects or failed readback. Duplicate receipts retain that original observation rather than re-observing/replaying. These setters share the existing transaction lock and recheck locks at execution, allowing an explicit preceding unlock. Failed reviewed setters block the remaining batch, including later desktop actions.

Raw batches are sequential, without expected-version checks or automatic rollback; use the existing preview/apply/rollback service for versioned atomic settings changes. Coverage is now 53 reviewed bindings; 301 runtime bindings retain `legacy_handler` coverage and previous continuation policy. The five zero-argument setting shortcuts emit `setting_results`; lock/unlock calls emit `lock_results` with before/after lock snapshots and settings versions. Three encoded transaction commands now validate before batch execution and stop the tail after a rejected/failed transaction. Unexpected transaction errors report `failed_uncertain` with available versions. Literal false / `success=false` still marks failure; legacy `None` remains untyped completion. MCP remains observation-only.

Use `aurora commands APPLY_SETTINGS_TRANSACTION --limit 1 --detail --json` or `LOCK_SETTING`/`TOGGLE_LIVE_MODE` for the exact reviewed contracts. Lock names/aliases come from the shared registry. `UNLOCK_SETTING(temp); SET_TEMPERATURE(0.5)` remains supported because locks are checked at execution. Stale transaction versions reject at execution and do not undo an earlier raw command; use a fresh version for the intended atomic change.

Generate from the target checkout with `regenerate_aurora_skill_refs.ps1 -Force`; use `-Check` to verify without publishing and `-SyncSkills` to export installed skill references. The repository-owned stdlib driver is `tools/generate_aurora_references.py`. Curated maps live in `aurora_reference_maps`; reference packs are authored in `docs/reference-packs`. Installed skills are exports, not generation inputs. The manifest records normalized source/output hashes and portable paths. Generator portability has isolated-Python/moved-checkout proof; full runtime clean-install proof is still pending.

## Cancellation and work state

Submit `CANCEL_ACTIVE_WORK()` as a standalone raw command to cancel the current model turn and active/queued batches once. Existing authorization and durable mutation admission still apply. `SET_LIVE_MODE(off)` cancels the model turn and disables live inference, honoring the live setting lock. `SHUTDOWN_RUNTIME()` cancels work and requests normal shutdown. Mixed batches keep their queue order. Cancellation does not undo completed actions or clear held-for-review proposals; the one-shot cancel leaves live mode unchanged.

Terminal batch receipts use `status=cancelled`, preserve `executed_commands`, and report `cancelled_commands` plus `cancellation_reason`. Inspect the receipt before intentionally issuing a new request ID. `aurora status --json` exposes the snapshot's `work` section: model I/O can remain `draining` after local cancellation while the provider call finishes. Late replies are discarded. Native calls already in progress may finish before a cancellation checkpoint; explicit indefinite holds require matching release commands. Snapshot age and runtime liveness still qualify this readback.

Capture filenames now use an epoch-nanoseconds plus UUID stem. Treat IDs as opaque; do not parse them as seconds. Sidecar `image_id`, image path, file hash and scheduler references identify the same saved frame. Legacy images remain readable.

## Current Status

Window 23 Slices 1-7 are implemented and validated locally:

- correlated operator transport and terminal command receipts;
- a thin Windows CLI over the existing file-backed bridge;
- a 22-setting typed registry with 36 aliases;
- version-preconditioned atomic runtime-session settings preview/apply/rollback; and
- a nonblocking Control Panel client over that same service, with details, conflict refresh, receipts, and rollback;
- fsynced mutation admission keyed by `client_id + request_id`, duplicate suppression, changed-payload conflict detection, terminal-result recovery, and explicit uncertain/no-replay behavior; and
- a local operator shell with generated command/settings discovery, context-aware completion, Windows line editing, and sensitive-command-excluding history; and
- a shared read-only `aurora_operator_dashboard_v1` model consumed by the terminal and the Control Panel Dashboard tab/popout.

Core files:

- `aurora_control_plane.py`: shared request envelope, JSONL readers, receipt wait, durable mutation-admission journal, process/status helpers, and dashboard snapshot/formatting contract;
- `aurora_settings_registry.py`: typed definitions, constraints, readback, and settings version;
- `aurora_settings_transactions.py`: request token, planner, transaction schemas, command invocation contract;
- `aurora_cli.py`: one-shot operator commands, dashboard/watch output, settings UX, command discovery/completion, history, and interactive shell;
- `aurora.cmd` / `auroractl.cmd`: Windows launchers; and
- `aurora2.py`: authoritative ingress admission, setter execution, transaction lock, effective readback, receipt logging/reconciliation, and rollback store.

This does not create a second runtime. CLI and Control Panel remain clients of Aurora's existing bridge/state surfaces.

## Entry Points

```powershell
.\aurora.cmd status
.\aurora.cmd status --watch
.\aurora.cmd dashboard --events 8
.\aurora.cmd dashboard --watch --interval 1.5
.\aurora.cmd dashboard --json
.\aurora.cmd shell
.\aurora.cmd commands screenshot --limit 10
.\aurora.cmd complete --json "settings apply live=o"
.\aurora.cmd history --limit 20
.\aurora.cmd command "SHOW_RUNTIME()"
.\aurora.cmd capture now --reason operator
.\aurora.cmd receipts --limit 10
.\aurora.cmd receipts --client-id aurora_cli --request-id <request-id>
.\aurora.cmd doctor

.\aurora.cmd settings list
.\aurora.cmd settings get runtime.live
.\aurora.cmd settings describe capture.screenshot_interval
.\aurora.cmd settings version
.\aurora.cmd settings preview inference.temperature=0.25 scheduler.min_gap_seconds=0.65
.\aurora.cmd settings apply inference.temperature=0.25 scheduler.min_gap_seconds=0.65
.\aurora.cmd settings rollback <settings-rb-...>
```

`auroractl.cmd` is an alias. Both launchers default to `C:\Anaconda\envs\aurora\python.exe`; set `AURORA_PYTHON` to choose another compatible interpreter deliberately.

The map-regeneration wrapper uses that same interpreter override/default; it does not require bare `python` on PATH. Either generator's nonzero exit aborts before workspace mirror sync.

Inside `aurora shell`, use ordinary CLI forms such as `status`, `dashboard`, `receipts`, `capture now`, and `settings describe live`. A known generated Aurora command such as `SHOW_RUNTIME()` can be entered directly; use `command <RAW>` or `send <RAW>` for an intentional raw form that is not in the catalog. `? query` searches command and setting descriptions. Bare shell/CLI names take precedence over same-named runtime aliases, so `status` is local while `STATUS()` is a runtime command.

On a Windows console, Tab completes shell commands, generated runtime commands, setting keys/aliases, and boolean or enum assignment values; arrow keys navigate local history. Redirected stdin uses the ordinary `input()` fallback, which keeps scripted shell transcripts portable but does not provide interactive key handling.

## Request Envelope

CLI and Control Panel send `aurora_bridge_request_v1` records to `aurora_external_inbox.jsonl`:

```json
{
  "schema_version": "aurora_bridge_request_v1",
  "request_id": "aurora_cli-request-...",
  "message_id": "aurora_cli-message-...",
  "client_id": "aurora_cli",
  "author": "operator",
  "source": "aurora_cli",
  "subject": "[AURORA CLI]",
  "text": "SHOW_RUNTIME()",
  "metadata": {
    "ingest_mode": "raw",
    "surface": "cli"
  }
}
```

- `request_id`: one end-to-end operator intent and receipt correlation key;
- `message_id`: one inbox delivery attempt; and
- `client_id`: producer identity such as `aurora_cli` or `aurora_control_panel`.

For mutating raw commands, `client_id + request_id` is now the durable admission identity. `message_id` remains one delivery attempt, so a retried intent should keep its request ID and receive a new message ID. Read-only commands do not reserve mutation identities and remain repeatable.

Legacy records without request ID still fall back to message ID. That fallback can suppress an exact legacy redelivery, but clients should send explicit request and client IDs for intentional idempotency.

## Mutation Admission Journal

September 5 command contract: raw requests are complete command batches. Separate
commands with semicolons or newlines outside arguments; quote literal separators.
Nested parentheses/brackets/braces and quoted `#` are preserved. A `#` outside
arguments starts a line comment. Every expanded command name and the batch syntax
are validated before any handler runs, and every member is authorized against
the admission-time operator state. An authorization command must complete in a
separate request before it can authorize a later mutation. Queued actions retain
the resolved action mode. Unknown or malformed raw commands produce a rejection;
they are never silently routed to model input.

This is admission validation, not an atomic transaction across arbitrary commands.
Handlers still validate their parameters and can fail after earlier batch members
execute. Inspect `executed_commands` and `failed_commands`; use the typed settings
transaction API when atomic settings changes are required. Parameter/result
contracts across the full legacy catalog are the next quality pass.

Inbox commits require a terminating newline, even for otherwise valid JSON.
Polling reads at most 128 records/4 MiB, with a 1 MiB per-record bound and bounded
discard/recovery for oversized records. Invalid JSON/object/metadata types are
reported by reason and byte offset. The runtime persists file identity, byte
cursor and oversize-discard state atomically and retries a failed cursor save.
File replacement or truncation resets reading; durable mutation identities
prevent replay. Exact raw envelope redelivery also receives a duplicate receipt.
Historical receipt readers retain support for larger existing records.

Launcher diagnostics: `launch_aurora2.cmd --preflight` or
`launch_aurora2_ui.cmd --preflight`. These only resolve imports; the opt-in
`python tests/offline_runtime_smoke.py` proves real offline startup/ingress/exit
in a disposable source copy using the interpreter that invokes it.

Before Aurora queues or executes a recognized raw command outside the canonical `READONLY_OPERATOR_COMMANDS` set, it fsyncs an `aurora_mutation_admission_v1` row to `aurora_mutation_admission_log.jsonl`:

```json
{
  "schema_version": "aurora_mutation_admission_v1",
  "event": "mutation_admitted",
  "admission_id": "mutation-...",
  "client_id": "aurora_cli",
  "request_id": "...",
  "message_id": "...",
  "command_name": "SET_TIME_LOGGING",
  "command_digest": "<sha256>",
  "disposition": "admitted",
  "replay_attempted": false
}
```

The journal stores a command hash and name rather than another unsanitized command copy. After the ordinary terminal `command_result` is written, Aurora appends a fsynced `mutation_terminal` row containing the sanitized terminal receipt. On restart, it also recovers a terminal receipt from the command log when a crash happened after command-result logging but before terminal-journal reconciliation.

| Admission decision | Runtime behavior |
| --- | --- |
| `admitted` | First occurrence is journaled before dispatch. |
| `rejected` | The identity is reserved with its terminal security rejection, so later authorization changes do not silently repurpose the same request ID. |
| `duplicate_terminal` | Command is not executed; Aurora emits the prior terminal status/details with `delivery_status=duplicate_suppressed`. |
| `duplicate_uncertain` | Command is not executed; Aurora returns nonterminal `uncertain`, `replay_attempted=false`, and CLI exit code `4`. |
| `request_conflict` | Same client/request with a different command hash is terminally rejected. |

Uncertain admission is intentionally sticky. Aurora does not infer that a missing receipt means failure, and it does not automatically replay the write after a timeout or restart.

## Command Receipt

Executed external commands append `aurora_command_receipt_v1` fields to a `command_result` row:

```json
{
  "event": "command_result",
  "receipt_schema_version": "aurora_command_receipt_v1",
  "receipt_id": "receipt-<request-id>",
  "request_id": "...",
  "message_id": "...",
  "client_id": "...",
  "status": "processed",
  "delivery_status": "completed",
  "terminal": true
}
```

Command, expanded/executed/failed rows, timings, context, input metadata, and source remain attached.

CLI submissions and Control Panel transaction waits match the normalized `client_id + request_id` pair, including bridge ingestion/rejection events. Another client's reuse of a request ID cannot complete or reject this client's wait. Legacy identity extraction still falls back to `source` / `message_id`. The shared reader's optional client filter preserves compatibility; `receipts --client-id CLIENT [--request-id REQUEST]` scopes lookup, while unfiltered history remains cross-client.

| Status | Meaning |
| --- | --- |
| `processed` | Runtime handled the command and logged a terminal result. |
| `failed` | Command handling ran, but one or more operations failed. |
| `rejected` | Operator security refused the raw command. |
| `request_conflict` | The mutation identity was already reserved for a different payload. |
| `routed_as_input` | Text was not recognized as a command. |
| `queued` | Durable generic command was written while runtime was unavailable. |
| `uncertain` | Bridge admitted the command but no terminal result arrived before timeout. |

Do not automatically retry an uncertain side effect.

## Settings Transaction Receipt

The outer command receipt carries one nested `aurora_settings_transaction_receipt_v1` row in `settings_transaction_receipts`.

It reports:

- transaction and receipt IDs;
- operation and runtime-session scope;
- expected, before, and after settings versions;
- previewed/requested/normalized/before/after values;
- effective readback with source, lock, maturity, and apply timing;
- all validation rejections;
- apply/restore commands;
- terminal status; and
- an optional single-use rollback handle.

Transaction statuses include `previewed`, `applied`, `applied_noop`, `rejected`, `failed_rolled_back`, `rollback_failed`, and `rolled_back`.

Settings versions are opaque `sv1:<sha256>` tokens over all registered values and their matching locks. The six scheduler bundle fields are first-class registered values. Callers compare tokens; they do not interpret them.

## CLI Behavior

Generic `command` and `capture` wait for their exact correlated result by default. `--no-wait` is deliberate asynchronous submission.

Generic commands can remain queued while Aurora is stopped. Settings preview/apply/rollback are stricter: they require an active runtime, and automatic expected-version derivation requires a fresh effective state snapshot. This prevents a delayed stale mutation from sitting in the inbox.

Exit codes:

- `0`: processed, previewed/applied/rolled back, displayed, or deliberately queued generic command;
- `2`: failed, rejected, invalid, or unavailable transaction context;
- `3`: routed as normal input;
- `4`: admitted outcome uncertain at timeout; and
- `130`: interrupted `status --watch` or `dashboard --watch`.

Runtime finalization now gives pending worker results a short bounded drain, so ordinary `SHUTDOWN_RUNTIME()` calls can receive terminal receipts. A crash or forced termination can still preempt that drain; the durable admission then remains uncertain and the same request identity will not replay shutdown after restart.

## Shell Discovery, Completion, and History

- `commands [query]` searches the generated `aurora_reference_maps/commands/commands-index.tsv` catalog offline; `--category`, `--limit`, and `--json` are available.
- `complete <partial line>` exposes the same `aurora_cli_completion_v1` candidates used by interactive Tab completion, including replacement offsets for external adapters.
- `history [show]` reads local `aurora_cli_history_v1` rows from `aurora_cli_history.jsonl`; `--search`, `--limit`, and `--json` are available.
- `history clear --yes` is the only history-clearing form. It replaces the local file atomically and refuses deletion without explicit confirmation.
- Stored rows contain timestamp, epoch, source, normalized command text, and exit code. Empty, oversized, or plausibly secret-bearing lines are not stored; this includes passcode, password, API-key, secret, access/refresh-token, bearer, and authorization text.
- History is operator convenience, not command-result or mutation-admission authority. Receipts and the admission journal remain the execution truth.
- `shell --no-history` disables both persistence and navigation loading for a session; `--no-banner` supports compact scripted proofs.
- The shell does not run operating-system commands, does not infer unknown text as a runtime command, and does not automatically retry interrupted or uncertain writes. After an interrupted wait it tells the operator to inspect status/receipts before choosing a new action.

The current editor is dependency-free: it uses the standard-library Windows console API when both streams are terminals. A future richer terminal UI can replace or wrap that front end while keeping these completion/history schemas and the shared control-plane calls stable.

## Shared Operator Dashboard

`build_operator_dashboard()` returns `aurora_operator_dashboard_v1`. It combines:

- runtime and Control Panel process/state freshness;
- mode, model, scheduler, and monitor summaries;
- compact queue/bridge and mutation-admission posture;
- all 22 typed setting readbacks with version/status counts; and
- a bounded recent-event list using `aurora_operator_dashboard_event_v1`.

Recent events expose command name and receipt lifecycle metadata, but never copy raw command arguments. `format_operator_dashboard()` is the shared text formatter. One-shot `--json` is pretty JSON; watched JSON is one compact snapshot per line (JSONL). Interactive watched text clears and redraws in place; redirected output and `--no-clear` append snapshots.

The Control Panel calls the same builder directly for its Dashboard tab and optional popout. It does not parse terminal output. The view is read-only and does not create a second command path.

## Current Guarantees

- exact request/result correlation;
- durable JSONL submission for generic commands;
- fsynced journal-before-dispatch admission for recognized mutating raw commands;
- duplicate suppression across runtime restarts by `client_id + request_id`;
- command-hash conflict rejection and prior-terminal-result re-exposure;
- explicit uncertain/no-automatic-replay receipts;
- partial-tail-safe JSONL reads;
- terminal processed/failed/security-rejected receipts;
- typed settings discovery and effective/last-observed readback;
- complete-batch transaction validation;
- opaque expected-version preconditions;
- lock and runtime-session scope enforcement;
- all-or-none apply through existing setters;
- state-export and model-turn exclusion while a transaction applies;
- effective readback before success;
- rollback after apply failure;
- same-session single-use rollback handles; and
- offline generated command discovery and structured completion;
- local sensitive-command-excluding shell history;
- shared structured dashboard snapshots and sanitized recent receipt events; and
- no model call required for control-plane operations.

## Remaining Boundaries

- No automatic replay of uncertain writes.
- No automatic operator reconciliation or retry-under-a-new-id workflow for uncertain writes yet.
- No personal/project settings persistence.
- Rollback handles are bounded in memory and expire at runtime shutdown.
- Control Panel registered settings use the transaction client; broader unregistered controls remain explicit independent commands.
- Dashboard surfaces are read-only; they do not yet provide active timeline hooks, reconciliation actions, or stepwise control.
- No operating-system command escape, remote shell-history sync, history encryption, or multi-process history transaction layer.
- No auth broadening, agent spawn, desktop-action expansion, or sibling-app mutation was introduced.

## Control Panel Relationship

The Control Panel sender uses `aurora_control_plane.append_bridge_request()` and displays request IDs. Its registered settings now derive a fresh effective version, submit one `SETTINGS_TRANSACTION(...)` request, wait for the exact correlated receipt on a background thread, and handle the result on Tk's refresh loop.

The panel surfaces Preview Atomic, Apply Atomic, version/count/rollback status, detailed source/scope/maturity/lock/apply metadata, nested receipt details, version-conflict refresh, and same-session rollback. Queue/Bridge status and the Overview raw detail expose reserved/terminal/uncertain mutation counts and the journal path. The Dashboard tab/popout adds shared process, operation, control-plane, settings, and recent-receipt views without terminal scraping. The panel does not automatically replay missing/uncertain receipts or version conflicts. `Apply Additional` is the named boundary for controls outside the 22-setting registry; profile follow-up commands wait for successful atomic apply and remain explicitly independent.

## Roadmap From Here

1. **W23-S1 / CX-T0 - complete:** correlated transport, thin CLI, Control Panel sender parity.
2. **W23-S2 / CX-1 - complete:** typed settings registry and readback.
3. **W23-S3 / CX-2 - complete:** atomic preview/apply, expected version, effective readback, receipt, rollback.
4. **W23-S4 / CX-3 - complete:** Control Panel transaction client, readback/details, atomic Apply, receipt/conflict handling, rollback, and Capture Now.
5. **W23-S5 - complete:** durable mutation admission, terminal reconciliation/recovery, duplicate suppression, payload conflict, uncertain/no-replay behavior, and shutdown-result drain.
6. **W23-S6 - complete:** local shell, generated command/settings discovery, context-aware completion, Windows line editing, and sensitive-command-excluding history.
7. **W23-S7 - complete:** shared dashboard snapshot/event schemas, terminal text/JSON/watch/JSONL, shell builtin, and Control Panel Dashboard tab/popout.
8. **Next only when explicitly opened:** CX-4 stepwise observation, or another selected bounded lane such as uncertainty reconciliation, persistent scopes, leases/peer delivery, or CX-5 timeline/hooks.
9. **Later Prime/RLM lanes:** bounded context query, Goal contract v2, refinement candidates, agent receipts/leases, and selective delegation.

## Validation Evidence

Validation on 2026-08-08 used the canonical Aurora interpreter.

- Six-file compile passed.
- Forty-one focused tests passed across dashboard sanitization/surfaces, shell/discovery/completion/history, transport/admission/restart recovery, registry/readback/version, and transactions.
- CLI help/version/list/get/describe and stopped-runtime mutation refusal passed.
- Bounded offline no-UI runtime proof emitted 7 nested correlated transaction receipts across preview, apply, two rejections, and two rollback paths.
- A two-setting apply and rollback restored the exact baseline version.
- Locked mixed batches and stale expected versions changed no setting.
- Scheduler-profile rollback restored all six bundled fields from a custom baseline.
- The real Tk panel constructed the new transaction controls, and a bounded offline proof drove Control Panel preview/apply/rollback plus correlated Capture Now against a live runtime. Preview preserved the version; apply changed effective readback/version; rollback restored the exact baseline.
- A separate actual `--with-ui` launch proved runtime/Control Panel process startup, fresh 22-setting versioned state, exact `SHOW_RUNTIME()` and capture receipts, and graceful two-process shutdown.
- Slice 5 live proof executed `SET_TIME_LOGGING(on)` once, returned the prior processed result for an identical second delivery without execution, rejected changed payload under the same identity, executed two same-ID `SHOW_RUNTIME()` reads independently, and restored time logging off under a fresh identity.
- Restart proof retained one deliberately unresolved admission, returned `duplicate_uncertain` with CLI exit code `4`, left the restarted runtime alive, and then produced a terminal receipt for a fresh shutdown identity through the bounded final result drain.
- Slice 6 isolated-root proof kept bare `status` local, routed direct `SHOW_RUNTIME()` and a passcode-bearing raw command into only the temporary inbox, stored five safe history rows, and stored zero secret-bearing rows.
- Slice 6 real-runtime proof launched Aurora offline with no UI, used `aurora shell --no-history` for local status plus a direct `SHOW_RUNTIME()` command, received an exact terminal receipt, preserved the retained uncertain admission without replay, and shut down under a fresh request identity.
- Both Windows launchers rendered the Slice 7 dashboard in text and JSON. Direct Tk construction selected the Dashboard tab and opened its popout; geometry probes found no child outside its content surface. The bundled Computer Use screenshot helper was unavailable with `node_repl exec context not found`, so this slice records construction/geometry evidence rather than a screenshot artifact.
- Slice 7 bounded offline `--with-ui` smoke `w23-s7-dashboard-1786251038885` observed active runtime and Control Panel processes, 22 effective settings, five recent dashboard events, exact terminal `SHOW_RUNTIME()` and fresh-ID shutdown receipts, monitor `ok`, and retained mutation uncertainty exactly `1`.
- Runtime returned to live off, temperature `0.0`, scheduler balanced, and zero locks.
- Final monitor was `ok | checks=16 | warnings=0 | errors=0 | watch=0`; PID files were removed and zero Aurora runtime/Control Panel processes remained.
