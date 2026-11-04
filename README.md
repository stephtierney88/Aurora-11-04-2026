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

- **Conversation → Current context** is the currently eligible conversation window from runtime memory. Messages disappear when deleted, decayed or outside that window. System details are an optional display checkbox. This is not a dump of the complete API prompt.
- **Retained messages** includes messages still held by the runtime but outside the current window.
- **Historical log** opens the existing Chat log view, including older events. **Context details** exposes memory/prompt organization.
- Write below the transcript and use **Send message** or Ctrl+Enter. A queued message enters history when its inference turn begins. Sending does not turn inference on. Queues are session-local, not a durable outbox.
- **Advanced settings**, the full View selector, Dashboard, Screenshots, Recovery, command entry and CLI retain the operator capabilities. **Reopen last view** restores the previous startup preference instead of opening Conversation.

## Models and verification

New defaults are `gpt-6.1-sol` with low reasoning for text/vision, and `gpt-6-astra` for the review/reasoning role with medium review effort. Older model choices, explicit effort settings, profiles and Chat Completions remain available. This harness uses text-form Aurora commands; the smoke does not claim native API function calling on Chat Completions. The optional Astra Responses/configuration-update path remains separate.

November 4 bounded live proof: Sol recognized a random token, proposed commands and clicked an isolated test button; Astra read the changed screenshot; the next turn returned to Sol low. Existing policy held these commands, and the fixture explicitly approved them. A demand-capture request was queued and fulfilled by a bounded test-window capture, not the production background capture worker. This does not establish current Pokemon performance, unattended autonomy, cross-platform support or broad desktop reliability.

Validation: 512 automated tests passed in the development workspace; a fresh virtual environment installed the preview dependencies and passed preflight plus the guarded real-runtime fixture. The isolated native panel smoke covered 23 views, drafts, composer visibility, message expiry and settings rollback. This was on one Windows host, not a second clean PC.

The normal setup requires your own Windows environment and provider access. Audio/game/emulator/companion integrations can require additional programs and configuration. Provider costs and availability can change. The full public snapshot has no private Git history, saved conversations, personal defaults, credentials, runtime state or screenshots.

## Operator entry points

```powershell
.\.venv\Scripts\python.exe aurora_cli.py status
.\.venv\Scripts\python.exe aurora_cli.py commands --limit 20
.\.venv\Scripts\python.exe aurora_cli.py doctor
```

See `aurora_reference_maps/runtime/overview.md`, the function skeletons and `docs/reference-packs/` for capability discovery. The maps describe implementation; dated historical notes are not proof of current behavior. The project is still evolving, and no public-release ETA is promised.

Prompt refresh: current short/extended guidance now covers discovery, command syntax, permissions, fresh observations and current model controls. Model-requested catalog results enter context by default. The original prompts and terminal-only lookup behavior remain selectable through documented startup environment settings. See the AI guide.
