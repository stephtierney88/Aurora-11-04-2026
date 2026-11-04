# Aurora: start here

Aurora is an experimental Windows assistant that can chat, inspect screenshots, remember context and propose desktop or gameplay actions. The Control Panel is the simplest starting point. Its advanced settings and command arsenal remain available, but you do not need to learn them all at once.

## Install and open

Use Windows and Python 3.11 with Tkinter. Open PowerShell in this repository:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --json
.\launch_aurora2_ui.cmd
```

If you already have a suitable environment, set `AURORA_PYTHON` to its Python executable. The launcher prefers that override, then this folder's `.venv`, then the established Anaconda environment if present, then PATH Python.

Configure your own OpenAI API key through your normal secure environment setup. Aurora accepts `OPENAI_API_KEY`; the older `OPENAI_2023_API_KEY` takes precedence if both exist. Launch from an environment containing the key. Never paste it into Aurora chat, a README or Git. API calls use your API billing; OAuth code exists but subscription access is not verified for this preview.

## Your first conversation

On a different PC, also run `.\.venv\Scripts\python.exe aurora_preflight.py --display --json`. It reports monitor work areas and the diagnostic process's DPI awareness without taking a screenshot or sending input. Ask your setup AI to check the running runtime's screen settings before trying clicks; this report is not automatic coordinate calibration.

1. Open the panel. It starts on **Conversation**. Use **Maximize window** if space is tight.
2. Select **Start runtime**. This starts a worker with inference paused, safe execution policy and no implicit gameplay mapping. It does not start paid inference.
3. Open **Advanced settings** to inspect models and execution policy. **Hide settings** returns to chat; **Dock settings** keeps settings alongside it. Search helps find a section. The new routine default is Sol low; the review model is Astra medium. Saved settings can differ.
4. Write a short task and select **Send message**, or press Ctrl+Enter. Enter inserts a new line. Your message queues locally; it appears in the conversation when its inference turn begins.
5. Select **Enable inference** when ready for paid requests. It keeps the current settings. Start with a simple text question. Check the response and use **Pause inference** when finished.

Enabling inference starts an agent loop, not a guaranteed single billable reply. Screenshot/timer scheduling and automatic review settings can cause further turns. Keep early experiments short, inspect Dashboard/runtime details, and pause when done. `safe` execution and action mode are different controls: action mode `none` removes implicit prefixes; explicit GB/PYAG capabilities still exist and execution policy determines what may run.

The older orb double-click still applies its activation profile and enables inference. Use the labeled main buttons for the simpler workflow.

The defaults are a starting posture, not a reduced command set. Advanced settings retain Assist/Auto execution and PYAG/GB action modes, model overrides, capture controls and saved profiles. Change them deliberately and inspect the effective receipt. Main **Start runtime** now uses a 2-second capture interval; the legacy direct-runtime default remains 0.12 seconds and the orb activation profile uses 15 seconds. **Reset to preview defaults** selects request-only capture. Saved settings and environment overrides can differ; the Switchboard shows the effective state. Capture timing and paid inference timing are independent.

## Moving to another monitor or PC

The main panel sizes to monitor work areas and has scrollbars; dashboard, settings, banner and image popouts now clamp to the current work area too. Maximize or use the scrollbars if a dense page needs more space. Mixed-DPI layouts and a second PC still need hands-on verification.

Desktop targeting is less portable than the panel layout. The legacy capture path resizes to 1366×768 and calculates scale from startup dimensions. PYAG coordinates are desktop coordinates, not automatically converted from that resized image. Other aspect ratios, display scaling, negative monitor origins, changed monitor layouts and game overlays need checking. Restart and recalibrate after display changes; do not trust an old screenshot or saved tile grid. Have your setup AI verify one fresh capture and one harmless test-window target before broader actions. The runtime currently samples a screenshot during import, even before capture workers start; importing it is not a capture-free diagnostic. Preflight avoids importing it.

## The Switchboard

Open **The Switchboard** beside the View selector. The simple flow map opens first, with observed models, review cadence, modes and timing above it. **Overview**, **Switches**, **Commands** and **Init · contents** jump to the relevant section. Everything scrolls inside the workspace; runtime controls and one Conversation / Popout chat pair remain above it.

- **Switches:** adjust a draft, choose **Preview switches**, then **Apply switches**. Read the receipt and observed value. **Undo last settings apply** uses the shared versioned rollback service; it can reject if someone else changed the settings. More settings are tucked into expandable sections, and the full Advanced settings remain available.
- **Model choices:** editable Primary, Vision and Review selectors sit above the flow map. Choose **Apply model choices** to apply only those model/effort drafts. Clicking the model summary in the main header opens these selectors. The header distinguishes configured Primary, an active requested model, and the last prepared request; catalog membership alone does not prove your account can use a model.
- **Lost in the settings?** **Reset to preview defaults** is available in the persistent controls, Switchboard header, command desk and Commands view. It opens a before/after review of 22 controls; **Validate reset** is read-only, **Apply preview defaults** resets the session, and Undo uses the same rollback service. The baseline pauses inference, selects safe execution with action mode none, Sol low / Astra, and screenshots on request. Authentication, game profile, chat/files, saved custom profiles and other Advanced settings remain unchanged. Use **Cancel work** for pending/in-flight work and Recovery for System/Personal profile restoration. This is a bounded setup reset, not a full factory wipe.
- **Screenshots:** `heartbeat` keeps the original periodic capture behavior; `request_only` captures only for due requests. The request switch controls whether commands can ask for a fresh frame. With requests only and demand capture disabled, no new capture is expected. A frame already in flight may finish. The seconds dial is convenient from 0.1–60; the entry accepts the full valid range. Idle capture may be slower than the configured interval.
- **Inference timing is separate:** turn scheduling can call a paid model when inference is enabled. A request-only screenshot setting does not disable model-turn heartbeats. Pause inference to stop new requests.
- **Command desk:** search any of the 360 source-derived bindings and filter by subsystem. **Yellow Prepare selected** fills the editor without sending. Replace every `<placeholder>`. **Green Run selected** immediately queues a complete no-argument command; commands needing arguments first become drafts. **Run command draft** sends your edited batch. Locks, policy and runtime validation still apply. Queued is not proof of execution; inspect the receipt and Dashboard.
- **Flow map:** choose Overview, Groups or Functions. Solid routes are enabled by observed configuration; dashed routes are inactive or unknown. Labeled loops distinguish screenshot cadence from turn cadence. This is a topology/status view, not a live trace or proof that an action succeeded. Click a node to inspect its subsystem.
- **Context nodes:** hover System text, Init, Conversation, Working memory or Screenshot for a preview; click for a scrollable contents viewer. Init and conversation describe currently exported runtime data. System, memory, retrieval and last user-prompt text describe the last prepared request, with time and clipping disclosed. Before any request they remain unavailable. Preparation does not prove provider delivery, and the latest screenshot may differ from the one last sent.

The Portal ring rotates clockwise beside the chat shortcut. **Animate Portal icon** disables motion without removing the shortcuts. Settings changes apply to the runtime session; saving personal defaults is a separate explicit action.

## Button reference

| Control | Effect |
| --- | --- |
| Start runtime | Start the worker with inference paused |
| Enable inference | Allow model requests using current settings |
| Pause inference | Stop new model requests; it is not the work-cancellation control |
| Cancel work | Cancel active work through the runtime service |
| Stop runtime | Shut down the worker |
| Reset to preview defaults | Review and restore the 22 Switchboard defaults for this session |
| Capture now | Request a screenshot; inspect the result before relying on it |
| Quick start | Open short guidance inside the panel |

Closing the panel is not the same as stopping the worker. Stop runtime when you want the agent to end. The View selector exposes Pending, Recovery, Commands and the other operator pages.

## Which conversation am I seeing?

**Current context** shows currently eligible conversation from runtime memory. A deleted, decayed or out-of-window message disappears from this view. It does not show every system instruction, memory block or image payload sent to the provider. **System details** reveals system rows in this view; **Context details** explains other prompt material.

**Retained messages** shows conversation still stored in the runtime, including messages outside the current selection. **Historical log** opens the old Chat log view, which can contain events no longer in current memory. Sending while paused queues a message; it does not turn inference on. This queue is session-local, not a durable outbox.

Message times, assistant model labels and last-edit attribution are visible by default. **Times**, **Models** and **Edits** toggle their display and are remembered by the panel. New timestamps include a timezone offset; older rows keep their legacy time or unknown attribution. A provider-reported model is shown when available; otherwise the requested model is labeled as such. Edits retain the original author/time and show the recorded editor separately. These labels are provenance, not a complete immutable edit history.

## Shell-only option

For a paused, safe runtime without the panel:

```powershell
.\.venv\Scripts\python.exe aurora2.py --offline --no-live-init --no-smoke-test --no-sound --action-mode none --execution-mode safe --no-ui
```

Use `aurora_cli.py status`, `aurora_cli.py doctor` and `aurora_cli.py commands` from a second terminal to inspect it. Ask your coding assistant to explain the command syntax and inference gate before enabling a paid loop. The GUI is the recommended first route.

## If something is confusing

- No response: check runtime active, inference enabled, provider credentials/access, locks and Dashboard errors. Do not repeatedly press Send; the earlier message may be queued.
- Actions did not happen: inspect Pending and the command receipt. A proposal or accepted command is not proof of visible success. The initial safe policy deliberately restricts actions.
- Controls seem cut off: maximize, expand settings, and use the scrollbars. Compact views retain the full controls. The native Tk interface still has limited accessibility metadata and some dense advanced pages.
- Wrong model: inspect effective settings and personal defaults. The main Enable button keeps your settings; the orb shortcut applies an activation profile.
- A setting changed but the prompt did not: Live Init affects the next initialization, not an immediate reload. See the AI guide for exact prompt selection.

## What has actually been tested?

Screenshot timing has two controls in the Switchboard: **heartbeat** captures periodically, while **demand capture** permits `REQUEST_SCREENSHOT_CAPTURE(reason, 0)` to request a fresh frame sooner. Both can be enabled; **request_only** removes periodic captures. Model-turn scheduling is separate. Reset to preview defaults selects request-only capture. A queued request is not proof the model has seen a new image; inspect its timestamp and receipt. Multiple commands per response are supported. The final Pokemon test deliberately used one short input per turn and five-second test pacing; those are not general Aurora limits.

**Final Pokemon check:** an 83-second copied-save run verified one visible game movement, goal labels/four horizon updates, and Sol calling Astra when stuck then returning to Sol. It stopped because Aurora incorrectly classified a bedroom as a battle. Gameplay is still experimental. Goal save/load and nested goal IDs are also confirmed broken; use disposable sessions and do not rely on that path for durable plans. Message review, edits and exact-timestamp deletion work; date-range deletion and near/extra-long horizons are not implemented. The assistant game-routing bug found during testing was fixed, with all 526 existing tests passing afterward.

The November 4 Switchboard update passed 526 automated tests and an isolated native panel check across 24 views, including drafts, settings preview/apply/rollback and raw-command receipts. A guarded three-turn fake-provider test verified prompt-text export and effort restoration without API calls. The preceding preview also passed a fresh virtual-environment install and guarded runtime checks. Its bounded paid test used Sol to recognize a screen token and click a test button, Astra to inspect the changed image, then restored Sol low. Current policy held the commands and the fixture explicitly approved them. That follow-up capture used a fixture adapter; production background-capture acceptance is still a follow-up.

This is useful friend-preview evidence, not broad desktop reliability, current Pokemon qualification, cross-platform support or a second-PC install guarantee. Start in a harmless test window. Screenshots can contain private information, so choose the visible workspace deliberately.

The final Switchboard live check also verified the loaded Init marker, actual exported prompt text and message/edit model attribution. Provider-returned IDs matched Sol -> Astra -> Sol. It used explicit native-widget coordinates for the successful click: two screenshot-only coordinate attempts were rejected, so visual targeting remains experimental. Five paid requests across these final attempts cost about $0.11 by reported tokens and documented rates (estimate, not an invoice); two additional focus failures made no API request.

Give your coding assistant [README_FOR_AI.md](README_FOR_AI.md) for architecture, prompts, discovery, tests and limitations. No public-release ETA is promised.
