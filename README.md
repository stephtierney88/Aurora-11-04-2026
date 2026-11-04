# Aurora — November 4, 2026 developer preview

Aurora is a personal Windows desktop-agent harness with a Control Panel and an operator CLI. This is an experimental source snapshot for technically curious users, with the same broad commands and advanced settings available behind a simpler conversation view. It is not a general-purpose, unattended desktop automation release.

**Start here:** [For humans](README_FOR_HUMANS.md) · [For AI assistants](README_FOR_AI.md)

## Start here

Use Windows and Python 3.11 with Tkinter. In PowerShell, inside this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --json
.\launch_aurora2_ui.cmd
```

The panel opens without starting model inference. Configure your own API key through your normal secure environment setup (`OPENAI_API_KEY`; the older `OPENAI_2023_API_KEY` also works and takes precedence). Never paste a key into the conversation or commit it. Launch the panel from an environment that has your key. OAuth code is present but is not a verified subscription-access path for this preview.

In the panel, Start runtime starts paused; Enable inference then keeps the current settings. The older orb double-click still applies its activation profile. Alternatively, start a paused worker in a second terminal:

```powershell
.\.venv\Scripts\python.exe aurora2.py --offline --no-live-init --no-smoke-test --no-sound --action-mode none --execution-mode safe --no-ui
```

This starts the runtime with inference off and no implicit action mapping. The main Start runtime button additionally selects safe execution policy. In the panel, inspect the model/settings and then choose **Enable inference** when ready for paid requests. **Pause inference** stops new inference; **Cancel work** cancels current work; **Stop runtime** shuts down the worker. Those are separate controls. Choose an action mode/execution policy explicitly in Advanced settings before trying desktop actions. Do not begin with private or important windows on screen.

## Conversation and context

Before desktop actions on another PC, run `aurora_preflight.py --display --json` and follow the AI README's display/preset checklist. Panel/popout sizing adapts to work areas, but legacy screenshot resizing and mouse coordinates need calibration, especially with different DPI or multiple monitors. Main paused GUI startup uses a 2-second capture interval; reset chooses request-only. The full settings and command arsenal remain available. This is not universal automatic screen adaptation.

- **Conversation → Current context** is the currently eligible conversation window from runtime memory. Messages disappear when deleted, decayed or outside that window. System details are an optional display checkbox. This is not a dump of the complete API prompt.
- **Retained messages** includes messages still held by the runtime but outside the current window.
- **Historical log** opens the existing Chat log view, including older events. **Context details** exposes memory/prompt organization.
- Write below the transcript and use **Send message** or Ctrl+Enter. A queued message enters history when its inference turn begins. Sending does not turn inference on. Queues are session-local, not a durable outbox.
- **Advanced settings**, the full View selector, Dashboard, Screenshots, Recovery, command entry and CLI retain the operator capabilities. **Reopen last view** restores the previous startup preference instead of opening Conversation.

## Models and verification

**Known issues from the final Pokemon test:** an 83-second copied-save run moved the character once, updated goals/four horizons and verified Sol -> Astra -> Sol when stuck. It stopped because the text scene classifier mislabeled a bedroom as a battle. Goal save/load, nested serialization and nested IDs also need repair. Message review/edit/exact-timestamp deletion work; range deletion and near/extra-long horizons are not implemented. Treat gameplay and durable goal memory as unfinished. The assistant GB-routing defect discovered during that test was fixed and all 526 existing regression tests pass. This preview is suitable for supervised exploration, not unattended play.

**The Switchboard** adds a simple default flow map, observed primary/vision/review models and cadence, expandable switches and timing dials, all 360 command bindings, yellow prepare / green run, and correlated receipts. Hover/click context nodes to inspect loaded Init, current conversation, last prepared system/memory/user text and screenshot metadata. The flow is observed configuration, not an execution trace. One prominent chat shortcut pair avoids duplicate button rows; Portal animation can be disabled. All older Advanced controls and legacy paths remain.

Primary/Vision/Review dropdowns apply independently of other drafts; clicking the header model status opens them. Conversation timestamps, model labels and last-edit attribution are on by default and can be hidden. **Reset to preview defaults**, available beside the main runtime controls and in Switchboard/Commands, opens a review/apply/undo workflow for 22 controls. It returns to paused/safe/action-none with Sol low, Astra and capture on request, preserving credentials, chat/files, saved profiles and other Advanced settings. Recovery retains the broader System/Personal profile actions.

New defaults are `gpt-6.1-sol` with low reasoning for text/vision, and `gpt-6-astra` for the review/reasoning role with medium review effort. Older model choices, explicit effort settings, profiles and Chat Completions remain available. This harness uses text-form Aurora commands; the smoke does not claim native API function calling on Chat Completions. The optional Astra Responses/configuration-update path remains separate.

November 4 final bounded live proof: Sol recognized a random token and loaded Init marker, proposed commands and clicked an isolated test button using explicit native-widget coordinates; Astra read the changed screenshot; the next turn returned to Sol low. Provider-returned model IDs matched the requested sequence, and prompt/message/edit attribution checks passed. Two earlier screenshot-only coordinate attempts were rejected by the fixture, so coordinate grounding still needs work. Existing policy held the commands, and the fixture explicitly approved them. A demand-capture request was queued and fulfilled by a bounded test-window capture, not the production background capture worker. This does not establish current Pokemon performance, unattended autonomy, cross-platform support or broad desktop reliability.

Validation: 526 automated tests passed in the development workspace. The Switchboard's isolated native panel smoke covered 24 views, draft preservation, settings preview/apply/rollback, context inspection and raw-command receipts; the prominent popout was also checked manually. A guarded three-turn fake-provider run verified prompt-material export and reasoning restoration with zero API calls. The earlier preview installed into a fresh virtual environment and passed preflight plus the guarded real-runtime fixture. This evidence is from one Windows host, not a second clean PC.

The normal setup requires your own Windows environment and provider access. Audio/game/emulator/companion integrations can require additional programs and configuration. Provider costs and availability can change. The full public snapshot has no private Git history, saved conversations, personal defaults, credentials, runtime state or screenshots.

## Operator entry points

```powershell
.\.venv\Scripts\python.exe aurora_cli.py status
.\.venv\Scripts\python.exe aurora_cli.py commands --limit 20
.\.venv\Scripts\python.exe aurora_cli.py doctor
```

See `aurora_reference_maps/runtime/overview.md`, the function skeletons and `docs/reference-packs/` for capability discovery. The maps describe implementation; dated historical notes are not proof of current behavior. The project is still evolving, and no public-release ETA is promised.

Prompt refresh: current short/extended guidance now covers discovery, command syntax, permissions, fresh observations and current model controls. Model-requested catalog results enter context by default. The original prompts and terminal-only lookup behavior remain selectable through documented startup environment settings. See the AI guide.
