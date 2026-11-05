# Aurora: start here

Aurora is an experimental Windows desktop agent. **Control Panel → Conversation** is the simplest entry point; the Switchboard, shell and Advanced settings retain the full controls. This guide describes the November 5, 2026 refresh (release 54, including the GUI settings-snapshot repair). For an older download, follow [UPGRADING](UPGRADING.md) first.

## Install and open

Use Windows and Python 3.11 or 3.12 with Tkinter. The examples select 3.11; use `py -3.12` instead if that is your installed version. Open PowerShell in the new repository folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --json
.\.venv\Scripts\python.exe aurora_preflight.py --surface panel --display --json
.\launch_aurora2_ui.cmd
```

Activation is unnecessary with those explicit paths. Resolve missing Python/Tkinter/imports before enabling the agent. Display preflight reads monitor geometry without taking a screenshot or sending input.

The launcher prefers `AURORA_PYTHON`, this folder's `.venv`, the historical Anaconda location, then PATH. If an old override points elsewhere:

```powershell
$env:AURORA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
.\launch_aurora2_ui.cmd
```

## Choose your connection

**API:** configure `OPENAI_API_KEY` through your normal secure environment setup and select `api_key`. The older `OPENAI_2023_API_KEY` also works and takes precedence if both exist. Launch from that environment. Never paste keys into chat, source or Git. This route uses API billing.

**ChatGPT subscription:** click **Sign in / OpenAI**, finish browser login yourself, return to the connection dialog, check account/models, then explicitly apply `openai_chatgpt` in Agent controls. Sign-in does not enable inference or switch billing by itself. Aurora stores its own Windows-protected registration outside this checkout; do not copy another app's auth files or share the cache.

Real subscription inference and Sol → Astra → Sol restoration passed on the development account. Your plan/model access can differ. Long-session refresh/account switching still needs qualification. There is no automatic subscription-to-API billing fallback.

For subscription experiments, Advanced setting **auth.subscription_policy = bounded** adds a locally cancellable inference worker, a 90-second read-idle limit and a 180-second inference deadline. This optional path completed the latest 20-minute Pokémon run. The compatibility default is **legacy**; the choice is session-only and affects the next request. Authentication/catalog checks have separate timeouts, and local cancellation cannot guarantee provider-side cancellation. After a failure, inspect the outcome before explicitly sending another task; unfinished output is not replayed automatically.

## Your first conversation

1. Open the panel and select **Start runtime**. This starts paused, with safe execution and no implicit action mapping.
2. Expand **Agent controls**. Check auth, models and effective modes. Routine defaults are `gpt-6.1-sol` low and `gpt-6-astra` medium for review; saved settings and account access may differ.
3. Send one short task using **Send message** or Ctrl+Enter. Enter adds a newline. **Awaiting reply / Outbox** keeps queued text visible while paused.
4. Select **Enable inference**, inspect the response and **Pause inference** when finished.
5. Before desktop actions, inspect proposals and deliberately choose execution/action settings. Safe/Assist/Auto, action mapping and inference are separate controls.

Enabling inference starts an agent loop, not a guaranteed single request. Timers, screenshots and reviews can cause more calls. Optional bounded tasks limit new model calls by turns/time; they are not a dollar cap or instant remote cancellation.

| Control | Meaning |
| --- | --- |
| Pause inference | Prevent new inference; inspect already-running work separately. |
| Cancel work | Cancel active model/command work locally and release owned held inputs where possible. Does not delete queued chat or guarantee remote cancellation. |
| Stop runtime | Shut down the worker. Closing a chat popout/panel alone is not a substitute. |
| Reset to preview defaults | Review/apply the listed paused/safe/action-none baseline with Sol low/Astra, request-only capture and compatibility continuation settings. This is a scoped settings reset, not every Advanced option. Credentials, files, history and saved profiles survive. |

Reset is under **Panel options**, Switchboard and Commands. Same-session Undo is version-checked. Use Cancel separately for active work; inspect pending proposals too. The older orb double-click applies its activation profile and enables inference; labeled buttons are simpler for first use.

## Conversation and mini-preview

**Current context** shows currently eligible conversation, not the entire exact API request. **Retained messages** and **Historical log** expose other material. A deleted/decayed row can remain in an archive without remaining in current model context. Model-window estimates are approximate.

The mini-preview defaults to readable text. Scroll, click an excerpt to jump, dock left/right, collapse or pop out. Closing its popout returns it to the dock. **View options** includes the legacy colored map and metadata controls. Sender/model, timestamp, pin/decay and edited-by details are available; missing provenance stays unknown.

Select a retained text message and choose **Edit / pin…**. Stale revisions fail visibly; reopen rather than overwrite. Generated/managed rows, historical revisions and clipped text can be read-only. The command `PIN(text)` creates a new pinned row. Exact-timestamp deletion exists; date-range deletion does not.

Outbox distinguishes queued, runtime receipt, prepared, request started and usable response. Do not resend simply because a reply is slow. Outbox/queued-input recovery is still session-local; durable restart, queued cancellation and controlled retry remain unfinished.

“Decay 10 min” is an age threshold checked when history is appended, not a continuous timer. Pinned/important rows and images have separate retention. Archive views and snapshot age matter.

## Switchboard and smoother flow

**The Switchboard** shows observed models, cadence, modes and a simple flow graph. Hover/click context nodes for loaded Init, prepared prompt components and screenshot metadata. It describes configuration, not a complete execution trace.

- Adjust drafts → **Preview switches** → **Apply switches** → inspect receipts. Amber means not applied. **Undo last settings apply** uses versioned rollback.
- Model selectors apply only their model/effort drafts. The header distinguishes configured primary, active requested model and last prepared request. One-turn overrides are useful for a temporary Astra burst; verify restoration.
- Yellow prepares a command; green submits it. Submission is not proof of execution.
- **Command-driven preset** selects request-only capture, demand enabled, per-capture scheduling, zero periodic turn heartbeat and optional `task_flow` policy. It does not enable Auto or inference.
- **Task continuation & prompt delivery** offers bounded turns/time, readback wake and optional duplicate-Init removal. Reviewed receipt scope is also available through Advanced settings/commands. These options do not grant permissions or change billing.

Several commands may run from one response. Use short batches on a clear path and fresh observations at uncertain transitions. Command-driven capture can avoid unnecessary heartbeat waits; interpreting its image still takes a new model call.

## Goals and experimental task controls

Aurora currently has **immediate, short, medium and long** horizon lists, goal priority/importance labels, notes, diary and inventory-related memory. Save/load is repaired. Fuller Horizons-2/3 profiles, near/extra-long stores and per-category hard caps are still planned. Recent trials favored keeping active plans small and updating affected steps at milestones, but did not establish a universal best preset.

For advisory planning, select **goals.hierarchy_dispatch = advisory** and **goals.horizon_sync = preserve** in Advanced. Advisory stops stored Level 1 hierarchy from automatically dispatching; preserve keeps explicit horizon lists separate from derived hierarchy. Both retain **legacy** defaults and are included in saved personal/system profiles. These choices do not cancel commands already admitted. Inspect completed-goal history too: a stale medium-term plan or diary can remain after the goal itself completes.

Optional bounded-task controls can stop on declared done/wait/approval/error, reserve a command allowance, stop at a reported-token threshold, and choose how old-task plans/proposals carry forward. They are disabled or compatibility-preserving by default. A reported completion is a model declaration; token thresholds are not dollar caps and may overshoot on the last request. Unknown usage remains unknown. Use the command lookup/Advanced help and inspect **SHOW_TASK_STATUS()** before relying on these controls.

## Before clicking on another PC

Run display preflight, then verify one fresh capture and one harmless target with your setup AI. Verified capture carries frame identity, acquisition time, origin, dimensions and image-to-desktop geometry. Guarded worker tests cover this path; native mixed-DPI/input calibration is still incomplete. Mouse commands use literal desktop coordinates, not automatic conversion from a resized image.

Check capture target, display layout/DPI, foreground focus, emulator keys and game speed. Recheck after window/monitor changes. Legacy capture remains available with unknown calibration. Optional request timeout/attempt limits default to zero (legacy unlimited); a blocked OS call can finish after cancellation.

Capture and inference timing are independent. Paused GUI startup uses a 2-second capture interval, direct legacy startup 0.12 seconds, the orb profile 15 seconds, and preview reset request-only. Inspect effective state.

## Shell and validation console

For shell-only operation, start a paused worker in one terminal:

```powershell
.\.venv\Scripts\python.exe aurora2.py --offline --no-live-init --no-smoke-test --no-sound --action-mode none --execution-mode safe --no-ui
```

In another terminal in the same folder:

```powershell
.\.venv\Scripts\python.exe aurora_cli.py status
.\.venv\Scripts\python.exe aurora_cli.py shell
.\.venv\Scripts\python.exe aurora_cli.py commands screenshot --limit 10
.\.venv\Scripts\python.exe aurora_cli.py command "SHOW_RUNTIME()"
```

The operator shell controls Aurora; it is not an OS shell. `launch_aurora_validation.cmd` opens the local command/offline-validation console. Browsing commands does not call a model.

Recent FireRed tests completed **25 minutes** through the rival battle/healing/Route 1 to Viridian, and a later **20-minute continuation** delivered Oak's Parcel and verified the Pokédex before completing the goal. Both used Aurora's normal workers, with bounded supervisors and owned emulator/save copies. Earlier attempts also exposed connection and scene issues; one successful run does not qualify every game situation. Bring your own emulator/game and copied save. Website screenshot/click/type primitives are available, but comparable production-worker website acceptance is still pending. See [Release notes](RELEASE_NOTES.md) and [roadmap](docs/notes/aurora_runtime_roadmap.md).
