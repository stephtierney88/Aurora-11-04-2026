# Aurora Control Panel: start here

Aurora is an experimental Windows desktop agent harness. The GUI is still called **Aurora 2 Control Panel**. It combines conversation, visual controls, a searchable command arsenal and optional memory/recovery tools. Start with a harmless, bounded task; it is a technical preview rather than an unattended assistant.

## Install and open

Use Windows 10/11 and Python 3.11 or 3.12 with Tk. Download this release into its own folder or clone the repository. In PowerShell, inside that folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --surface panel --display --json
$env:AURORA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
.\launch_aurora2_ui.cmd
```

If Python 3.12 is installed instead, use `py -3.12`. Missing optional integrations can remain disabled. Read the preflight findings; monitor geometry alone does not prove click coordinates are calibrated. For an older installation, follow [UPGRADING.md](UPGRADING.md) instead of copying files over it.

## Sign in and try chat

The top-right **Sign in** button uses the last provider; the OpenAI circle always opens OpenAI sign-in. Complete consent yourself. Select the intended authentication route in settings and inspect the effective model/auth status. API-key access uses your own configured `OPENAI_API_KEY` (or legacy `OPENAI_2023_API_KEY`); keep credentials outside source files and screenshots. ChatGPT subscription inference was verified in earlier scoped tests, but account/model availability and long-session refresh still need checking. Signing in does not silently authorize API-key fallback.

Start the runtime with inference paused. Conversation shows the current eligible context by default; logs and alternate views are separate. A queued message may wait while paused. Check its delivery stage before retrying. Use **Enable inference** for a small chat test, then Pause again. The visible model selectors and Agent controls show the configured slots and next-turn overrides; actual provider evidence is recorded separately when available.

## The controls you need first

| Control | What it does |
| --- | --- |
| Pause inference | Stops starting new inference; it is not a cancellation guarantee for work already in flight. |
| Cancel work | Cancels outstanding work through the controller and releases owned held inputs. |
| Stop runtime | Shuts down Aurora's runtime; the panel may remain open. |
| Reset to preview defaults | Restores the defined preview settings. Inspect the result; this is not a history wipe, credential reset or undo of desktop actions. |
| The Switchboard | Browse settings/commands. Yellow primes a command; green submits it. Read its receipt for success/refusal. |
| Execution inspector | Inspect request/frame/action/receipt evidence. Historical views do not restore the live computer. |
| Outbox / Recoverable input | Inspect delivery and optional durable recovery. Retry is explicit, especially when earlier delivery is uncertain. |

Advanced settings retain the broad legacy controls. Durable recovery and execution recording are opt-in; they store private local data. Archive preview estimates a candidate and changes nothing. Do not delete recovery files to make capacity warnings disappear: doing so can remove duplicate protection.

For desktop/game use, choose the intended target, verify a fresh capture and coordinate mapping, set a time/turn budget and start with a harmless action. Multi-monitor, DPI, crop, resizing and focus require local checks. Pokémon requires your own lawful emulator/game/save setup; no ROMs or saves are included. Prior scoped runs completed parcel delivery and exercised goals/multi-command batches, but navigation and long-session behavior still need work.

The shell-only entry point is `launch_aurora2.cmd` using the same `AURORA_PYTHON`. Ask your AI to read [README_FOR_AI.md](README_FOR_AI.md) for command syntax and test boundaries. See [release notes](RELEASE_NOTES.md) and [roadmap](docs/notes/aurora_runtime_roadmap.md) for what is proven and still open.
