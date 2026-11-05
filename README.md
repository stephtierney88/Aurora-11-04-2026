# Aurora — November 5, 2026 developer preview · release 54

Aurora is a Windows desktop-agent harness with a conversation-first Control Panel, a visual Switchboard and an operator shell. It gives models screenshots, executes permitted commands, maintains goals and memory, and continues tasks across observations. Its large command/settings arsenal is intentional; start in Conversation and open Advanced controls when needed.

**Start here:** [Human guide](README_FOR_HUMANS.md) · [AI setup guide](README_FOR_AI.md) · [Replacing an older copy](UPGRADING.md) · [What changed](RELEASE_NOTES.md)

This is a supervised developer preview, with no polished-release ETA. Start with Windows and Python 3.11 or 3.12; the commands below select 3.11, or substitute `py -3.12`. No ROM, emulator, saved game, credentials or captured screenshots are included.

## Install and open the GUI

Download/extract or clone into a fresh folder. Open PowerShell in that folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --json
.\.venv\Scripts\python.exe aurora_preflight.py --surface panel --display --json
$env:AURORA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
.\launch_aurora2_ui.cmd
```

Select **Start runtime** to start paused. Configure your own API key for API billing, or use **Sign in / OpenAI** and explicitly select **openai_chatgpt** in Agent controls for Aurora's ChatGPT subscription route. Sign-in alone does not switch billing or enable inference. Account/model availability is checked at runtime.

Send a short text task, then choose **Enable inference**. **Pause inference**, **Cancel work** and **Stop runtime** do different jobs. **Reset to preview defaults** offers a reviewed return to paused/safe settings without erasing your files or credentials. Read the human guide before enabling desktop actions.

## Progress since the previous public snapshot

- **Longer real gameplay:** a 25-minute FireRed run used Aurora's normal workers, won the rival battle, healed and reached Viridian after three wild victories. A later 20-minute Terra 6.1 low continuation delivered Oak's Parcel, verified the Pokédex and completed the saved goal. These were separate bounded runs, not a single 45-minute run or a promise of unattended play.
- **Subscription resilience:** optional locally cancellable inference workers add idle/deadline limits and discard unfinished responses safely. Legacy remains available/default. Real subscription inference and Sol → Astra → Sol restoration were already verified; long-session refresh/account switching still needs testing.
- **Task controls:** optional declared done/wait/approval/error stops, command allowances, reported-token thresholds and policies for carrying old plans/proposals into new tasks. Progress/readback/frame/request evidence is correlated. Token thresholds are not hard spending caps.
- **Goals and planning:** explicit advisory hierarchy and preserved manual horizons now coexist with legacy behavior. Goal previews show real IDs/labels; Init guidance and heartbeat-zero handling are repaired. Save/load works, but stale medium-term plans and journal projection still need attention.

The earlier refresh already added visible queued messages, delivery stages, revision-checked edit/pin, a readable detachable mini-preview, clearer Switchboard drafts/receipts, capture provenance and optional command-result continuation/Init deduplication. Those features remain. New screenshots still require another inference call.

Inventory: **387 command bindings, 157 reviewed argument contracts, 48 shared settings and 24 views**. Legacy behavior and Advanced settings remain available; experimental options have not silently replaced compatibility defaults. [Release notes](RELEASE_NOTES.md) distinguish live evidence, offline checks and unfinished work.

## Things to try

Start with chat, command discovery, goals/save/load, message editing/pinning and Switchboard Preview → Apply → Undo. Then try a small screenshot/click/type/readback task on a harmless local page. Aurora has the primitives for supervised website navigation, form entry and reading visible pages; broad internet-task reliability is not established.

For Pokémon, supply your own emulator/game and check focus, mapping, capture geometry and timing. Use a copied save. Begin with a short supervised run before trying longer sessions. No game, emulator, saves or captured screenshots ship here.

## Ask your coding AI

> Read README.md, README_FOR_HUMANS.md, README_FOR_AI.md, UPGRADING.md and AGENTS.md. Help me make a fresh Python 3.11 environment, run preflight, configure my own credentials securely and open the GUI paused. Check my monitor, model access and effective settings. Demonstrate chat, Outbox, Pause, Cancel work and Reset to preview defaults. Then propose one bounded test on a harmless window; do not enable wider actions or change billing without my instruction.

The snapshot includes runtime/UI source, offline tests, command catalogs, maps/function skeletons and technical references, plus five UI artwork assets used by the application. It excludes private development history, screenshots, conversation logs, state, personal profiles and auth caches. Pattern/configured-secret checks reduce accidental disclosure; they are not a formal security audit.
