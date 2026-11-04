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

1. Open the panel. It starts on **Conversation**. Use **Maximize window** if space is tight.
2. Select **Start runtime**. This starts a worker with inference paused, safe execution policy and no implicit gameplay mapping. It does not start paid inference.
3. Open **Advanced settings** to inspect models and execution policy. **Hide settings** returns to chat; **Dock settings** keeps settings alongside it. Search helps find a section. The new routine default is Sol low; the review model is Astra medium. Saved settings can differ.
4. Write a short task and select **Send message**, or press Ctrl+Enter. Enter inserts a new line. Your message queues locally; it appears in the conversation when its inference turn begins.
5. Select **Enable inference** when ready for paid requests. It keeps the current settings. Start with a simple text question. Check the response and use **Pause inference** when finished.

Enabling inference starts an agent loop, not a guaranteed single billable reply. Screenshot/timer scheduling and automatic review settings can cause further turns. Keep early experiments short, inspect Dashboard/runtime details, and pause when done. `safe` execution and action mode are different controls: action mode `none` removes implicit prefixes; explicit GB/PYAG capabilities still exist and execution policy determines what may run.

The older orb double-click still applies its activation profile and enables inference. Use the labeled main buttons for the simpler workflow.

## What the buttons mean

| Control | Effect |
| --- | --- |
| Start runtime | Start the worker with inference paused |
| Enable inference | Allow model requests using current settings |
| Pause inference | Stop new model requests; it is not the work-cancellation control |
| Cancel work | Cancel active work through the runtime service |
| Stop runtime | Shut down the worker |
| Capture now | Request a screenshot; inspect the result before relying on it |
| Quick start | Open short guidance inside the panel |

Closing the panel is not the same as stopping the worker. Stop runtime when you want the agent to end. The View selector exposes Pending, Recovery, Commands and the other operator pages.

## Which conversation am I seeing?

**Current context** shows currently eligible conversation from runtime memory. A deleted, decayed or out-of-window message disappears from this view. It does not show every system instruction, memory block or image payload sent to the provider. **System details** reveals system rows in this view; **Context details** explains other prompt material.

**Retained messages** shows conversation still stored in the runtime, including messages outside the current selection. **Historical log** opens the old Chat log view, which can contain events no longer in current memory. Sending while paused queues a message; it does not turn inference on. This queue is session-local, not a durable outbox.

## If something is confusing

- No response: check runtime active, inference enabled, provider credentials/access, locks and Dashboard errors. Do not repeatedly press Send; the earlier message may be queued.
- Actions did not happen: inspect Pending and the command receipt. A proposal or accepted command is not proof of visible success. The initial safe policy deliberately restricts actions.
- Controls seem cut off: maximize, expand settings, and use the scrollbars. Compact views retain the full controls. The native Tk interface still has limited accessibility metadata and some dense advanced pages.
- Wrong model: inspect effective settings and personal defaults. The main Enable button keeps your settings; the orb shortcut applies an activation profile.
- A setting changed but the prompt did not: Live Init affects the next initialization, not an immediate reload. See the AI guide for exact prompt selection.

## What has actually been tested?

The November 4 preview passed 512 automated tests after the walkthrough and prompt changes, a fresh virtual-environment install and guarded runtime checks, and an isolated native panel check across 23 views. A bounded paid test used Sol to recognize a random screen token and click a test button, Astra to inspect the changed image, then restored Sol low. Current policy held the commands and the fixture explicitly approved them. The follow-up capture used a fixture adapter; production background capture is still a follow-up.

This is useful friend-preview evidence, not broad desktop reliability, current Pokemon qualification, cross-platform support or a second-PC install guarantee. Start in a harmless test window. Screenshots can contain private information, so choose the visible workspace deliberately.

Give your coding assistant [README_FOR_AI.md](README_FOR_AI.md) for architecture, prompts, discovery, tests and limitations. No public-release ETA is promised.
