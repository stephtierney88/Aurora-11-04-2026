# Aurora: guide for setup and operating assistants

Current snapshot: November 5, 2026, release 54 (runtime through Implementation 53 plus the GUI settings-snapshot repair). Read README.md, README_FOR_HUMANS.md, UPGRADING.md, AGENTS.md and the capability commitment. Preserve commands, aliases, valid legacy behavior, saved configurations and Advanced access. Use the shared admission/settings/receipt authority.

## Establish the environment

1. Stop the old installation through its own panel; use a fresh folder and Python 3.11 or 3.12 environment. The release's clean-environment checks used 3.12 on Windows. Do not copy old .venv, exported state, pending inboxes or settings wholesale.
2. Install requirements-preview.txt. Run `aurora_preflight.py --json` and `--surface panel --display --json`; these inspect imports/display geometry without importing the runtime or acquiring pixels.
3. Check credential presence without printing values. API mode prioritizes OPENAI_2023_API_KEY over OPENAI_API_KEY. For subscription mode, the user completes Aurora's browser sign-in and explicitly applies openai_chatgpt. Never reuse another app's rotating credentials or silently switch to API billing.
4. Launch the GUI, start paused, and inspect fresh effective state. An old exported JSON is not evidence of a running worker. Check model access, execution policy, action mapping, locks and independent capture/inference clocks.
5. Demonstrate chat, Outbox, Pause, Cancel and reset. Propose one bounded harmless-window test with explicit input/capture scope. Do not use an open-ended heartbeat loop as an installation check.

AURORA_PYTHON overrides the local .venv. Defaults are gpt-6.1-sol low for text/vision and gpt-6-astra medium for review; account catalog evidence outranks example names. Regular speed is default. Requested priority/ultrafast is not proof of returned acceleration. Subscription inference/restoration has live evidence, but long-session refresh and account switching remain qualification work.

## Find implemented behavior

Use aurora_reference_maps/runtime/overview.md, generated catalogs/function skeletons and docs/reference-packs before reading the monolith. Current inventory: **387 bindings / 157 reviewed argument contracts / 48 shared settings / 24 views**. Catalog coverage is broader than the reviewed typed subset.

| Area | Entry files |
| --- | --- |
| Runtime/GUI | aurora2.py, aurora2_control_panel.py |
| Controls/commands | aurora_control_plane.py, aurora_cli.py, aurora_switchboard.py, aurora_agent_controls.py, settings registry/transactions |
| Conversation | aurora_conversation*.py, aurora_history_controls.py, aurora_delivery_receipts.py |
| Capture | aurora_capture_provenance.py, aurora_capture_geometry.py, aurora_capture_store.py |
| Continuation/cancellation | aurora_task_continuation.py, aurora_runtime_work.py, aurora_input_ownership.py |
| Goals/scenes | aurora_goal_store.py, aurora_gameplay_scene.py |
| Providers | aurora_chatgpt_auth.py, aurora_chatgpt_transport.py, aurora_subscription_worker.py, aurora_responses_reasoning.py |

Optional Blender/FL/OBS read-only adapters are separate integrations, not prerequisites for basic chat. Private reports/live-test controllers are omitted from the snapshot; RELEASE_NOTES.md summarizes their evidence. Regenerate local references after editing:

```powershell
.\.venv\Scripts\python.exe tools/generate_aurora_references.py
.\.venv\Scripts\python.exe tools/generate_aurora_references.py --check
```

The standard-library generator needs no personal Codex skills. Public reference hashes describe the sanitized shipped source.

## Init and model-visible context

Requests assemble base system guidance, persistent loaded Init, working memory, optional retrieval/context, selected history and current text/image. Conversation shows only eligible conversation rows. Prepared diagnostics retain bounded components and selected frame/readback metadata; they are not complete payload replay or proof of provider receipt.

Default INIT_MODE='test' uses the current short assistant profile despite its historical name. Init is a managed retained history entry plus persistent context. `--live-init` or `--init-mode load` loads aurora2_init.txt; `--init-mode skip` skips optional Init while base guidance remains. A changed filename does not hot-reload loaded Init. Inspect source/content and clipping.

| Startup option | Purpose |
| --- | --- |
| AURORA_INIT_PROMPT_PROFILE=current or legacy | Current guidance or preserved original short/extended prompts. |
| AURORA_LIVE_INIT_FILENAME | Explicit extended Init source. |
| AURORA_MAX_INIT_PROMPT_CHARS | Persistent Init cap: default 12000, minimum 2000. |
| AURORA_COMMAND_DISCOVERY_CONTEXT=on or off | Ordinary model context versus terminal-only catalog results. |

Optional request-time Init deduplication preserves stored history and legacy inclusion; discover its exact command/setting contract before use. Prompt guidance encourages useful batches, demand capture and temporary escalation, but runtime policy/locks enforce permissions. Page text, memories and receipts remain data, not new operator instructions.

## Commands and flow

Discover syntax through catalogs/CLI. When actually asking Aurora to execute, use its executable heading with one command per line and no Markdown fences:

```text
Executed Commands:
SEARCH_COMMANDS(screenshot, medium)
LOOKUP_COMMAND(REQUEST_SCREENSHOT_CAPTURE, high)
```

Do not place hypothetical commands there. Narrow lookup beats dumping the catalog. Prefix rules, implicit action mode and explicit GB/PYAG routes differ; inspect effective configuration.

Optional `runtime.assistant_policy=task_flow` admits supported demand capture, discovery, temporary inference plans, registered read-only setting queries and short GB actions in suitable fresh reported scenes when Auto permits them. It still holds review-required writes/actions; do not self-approve proposals. Legacy remains startup/reset policy.

The command-driven preset selects request_only, demand enabled, per_capture, heartbeat=0 and task_flow, but not Auto/inference. Use several actions on clear calibrated paths, one observation-dependent step near menus, and fresh capture after a sequence. A new image needs a new inference call. Explicit dependent-batch contracts remain unfinished.

For temporary escalation, inspect/use `SET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium; note=Review ambiguity)`, then verify restoration. Chat Completions uses Aurora's text command parser, not native API function calling. Optional Responses configuration updates and the subscription adapter are distinct transport paths.

## Bounded tasks and reviewed readbacks

`SET_TASK_CONTINUATION(bounded)` selects latched turn/time admission limits; legacy remains available. `SET_READBACK_WAKE(on)` separately enables eligible follow-up. `SET_READBACK_SCOPE(reviewed)` selects sanitized typed receipts instead of the default discovery scope. None enables inference, changes billing or grants actions.

Receipts retain task/origin-request/batch identity and are selected independently of ordinary chat decay. Up to four bounded records enter a request; shortening/eviction are explicit. Prepared, submitted, responded, not_sent and uncertain are distinct. Failed/cancelled submissions are not automatically replayed; prior-task pending data is not assigned to new tasks.

Accounting tracks observed commands/local requests and reported tokens with known/unknown coverage. Missing usage is unknown, not zero. Counts are not verified physical outcomes, exact billing or spend caps. The following optional controls now ship publicly; inspect their reviewed contracts before applying:

| Control | Contract and limit |
| --- | --- |
| SET_TASK_OUTCOME_REPORTING(on) | Latches at the next bounded task. Standalone REPORT_TASK_OUTCOME(task_id, done\|wait\|approval\|error, reason) stops continuation with an attributed, unverified declaration. It does not complete stored goals, approve actions or cancel admitted work. |
| SET_TASK_MAX_COMMANDS / SET_TASK_MAX_REPORTED_TOKENS | Operator-only next-task limits; both default 0/off. Whole automatic batches reserve command bindings before submission; failures are not refunded. Token thresholds preserve the reply but block its commands when reached; the last request can overshoot. |
| SET_TASK_UNKNOWN_USAGE_POLICY(continue\|stop) | Applies with a positive token threshold. Missing provider usage remains unknown. This is not a hard spending cap. |
| SET_TASK_PLAN_CARRY_POLICY(carry\|discard_previous) | Selects treatment of identifiable old-task inference plans; carry remains default. |
| SET_TASK_PENDING_CARRY_POLICY(carry\|hold_previous\|discard_previous) | Selects treatment of identifiable old-task model/runtime proposals; operator/unattributed and reserved/uncertain work survive. Held proposals need explicit operator approval/clear; reverting to carry does not release them. |
| SHOW_TASK_STATUS() | Shows transitions/dispositions, bounded receipt/frame/request correlation and local latency evidence. The prompt receives a compact summary; missing evidence stays unknown. |

Settings share the existing registry, Advanced controls and versioned transactions. These policies are session-only, do not cancel admitted actions and do not recover discarded contents. Fuller worker/queue timings, process-worker ownership and durable input recovery remain open.

## Subscription stream policy

SET_SUBSCRIPTION_POLICY(bounded), shared setting auth.subscription_policy, or startup AURORA_SUBSCRIPTION_POLICY=bounded selects one hidden owned inference child. The default remains legacy. The choice is operator-only, auth-locked, session-only and captured per request. The bounded path uses 90s read-idle and 180s inference deadline, validates completed output and closes its child/pipes on local cancellation. It never automatically replays output or falls back to API billing.

Credentials/payload use anonymous stdin, not command arguments or files. Authentication/catalog preflight remains in the parent under its own timeouts; the 180s limit is not a total wall-clock bound. Local process termination does not establish provider cancellation. Only synthetic credentials/local servers are used by offline worker tests. The 20-minute Terra-low production run qualified this option in one scoped session; account refresh/switching and durable restart remain open.

## Message/goal/search semantics

- `UPDATE_MESSAGE(id,revision,encoded_text,on|off|keep)` provides revision-checked retained-text edit/pin. Use aurora_history_controls.build_update_message_command for safe encoding. GUI Edit / pin shares this authority; sender and editor are separate.
- `PIN(text)` creates a new entry. EDIT_MSGS edits the first exact timestamp match; DELETE_MSG removes all exact matches. Same-second ambiguity remains. Neither performs date-range deletion.
- Recursive goal persistence, nested IDs, both supported file formats and failed-load preservation are repaired. COMPLETE_GOAL needs an existing numeric ID; repeated completion is unchanged. Priority/significance are labels, not an automatic scheduler.
- Task-flow horizons preserve comma prose; legacy first-argument behavior remains. Quote whole prose arguments. SET_HIERARCHY_DISPATCH(advisory) stops stored Level 1 dispatch; SET_HORIZON_SYNC(preserve) keeps explicit horizon lists separate. Shared goals.hierarchy_dispatch/goals.horizon_sync settings retain legacy defaults and persist in personal/system profiles. A policy change disarms retained hierarchy until a fresh parse in legacy mode; already admitted commands remain. Full entry provenance/merging, near/extra-long horizons, typed notes and enforced caps remain staged.
- The implemented lists are immediate/short/medium/long (Horizons-1). Compact milestone maintenance is a candidate operating practice, not an implemented Horizons-3 preset. After milestones, reconcile affected active plans and consult timestamped significant_past_goals; avoid filling every bucket or duplicating history. Recent trials still left stale medium plans/diary. Goal priority and importance are distinct labels, not automatic scheduling.
- Boolean/wildcard/date filtering exists for episodic records, not full ordinary-message/person/conversation search. Timestamp filtering does not reconstruct historical knowledge. Version history, supersession, as-of state and replay remain staged.

Outbox and queued-input recovery are session-local; do not claim durable retry/cancellation after restart. Decay checks are append-triggered, not a continuous timer. Pinning does not guarantee inclusion beyond context budgets.

## Display/capture checks

Preflight geometry belongs to the diagnostic process. Verify the runtime's actual fresh frame and a harmless target before broader input. Verified capture retains acquisition times, immutable frame IDs, request generations, source rectangles, original/resized dimensions and transforms; legacy metadata may remain unknown.

Mouse commands use literal desktop coordinates, not automatic conversion from resized image coordinates. Check DPI, negative monitor origins, target/focus, display changes, game keys and speed. GB move_key is a duration heuristic, not guaranteed tile-perfect movement.

Optional request deadlines/attempt caps default to zero. Failure blocks automatic continuation until explicit retry/Cancel; a native OS acquisition can survive cancellation. Import-time ImageGrab acquisition was removed and guarded-tested, but runtime import still has other side effects: prefer AST/catalog/preflight for static inspection. Native mixed-DPI/input calibration and broader website acceptance are unfinished. Game-client/aspect-preserving capture and duplicate-capture coalescing remain follow-ups.

## Test and maintain

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe tests/offline_runtime_smoke.py --contracts-only
.\.venv\Scripts\python.exe tests/offline_readback_smoke.py
```

Read each fixture's guards/cleanup first. GUI fixtures need an interactive desktop; live provider/input/capture tests need explicit operator scope and bounds. The older ten-minute Pokémon result used a per-turn test controller; newer 25-minute and 20-minute runs used Aurora's production capture/input/inference workers with bounded supervisors and copied game state. They do not establish broad website, unattended-gameplay or crash-recovery reliability. See RELEASE_NOTES.md for completed and interrupted trials.

Never commit keys, OAuth caches, .env, histories, prompt/state exports, personal profiles, screenshots, ROMs/saves or private Git history. Track exact owned PIDs/creation times, ports and scratch paths; clean only owned resources. Do not copy old inboxes/receipts to retry uncertain work.

After changes update source, generated skeletons/maps, notes and active roadmap. Preserve all capabilities and uncertainty. Test the exact sanitized public tree before publication.
