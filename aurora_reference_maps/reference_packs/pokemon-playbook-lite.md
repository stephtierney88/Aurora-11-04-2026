# Pokemon Playbook Lite

## Adaptive effort for gameplay

For an opted-in Astra Responses session, routine low effort may request a single high turn with SET_NEXT_REASONING_EFFORT(high, puzzle). Aurora validates the unlocked request in assist/auto mode and explicitly returns to the normal battle/review/dynamic policy afterward. A high-effort decision is not a fixed duration; check a fresh observation before delayed inputs. Held-input ownership and stale-observation gameplay proof remain open at 4B3/4B4; do not resume native capture automatically. See [adaptive reasoning](adaptive-reasoning-reference.md).

September 5, Implementation 08: explicit GB uses admitted game mapping, backend and confirmed focus, including when the configured game backend is PyAutoGUI. Explicit PYAG stays literal desktop input. Known mode selectors before unprefixed actions are projected in order; queued/timed actions retain their admitted route and report it in desktop_results.action_route. This has guarded/fake-input proof, not new live gameplay/calibration proof. Indefinite held-key ownership remains next.


## Purpose
- Give Aurora and operator-side models a compact gameplay guide for VBA-RR Pokemon runs without loading large code sections.

## Default profile
- FireRed is the default live-test profile.
- Blue remains supported for secondary regression and profile plumbing checks.

## Core input model

September 5 runtime contract update: existing `GB:` translation, configurable mappings and scan-code selection remain. Invalid arguments/keys reject the complete batch; an unconfirmed game focus sends no game input and does not fall back to another backend. Input failures block later batch commands and produce typed uncertain/not-started results. A submitted result does not prove movement, menu progress or the requested number of tiles. Timed input attempts release on cancellation; explicit indefinite holds still require a matching release using the same GB/backend context. Tile calibration and live gameplay proof are unchanged by this offline-tested repair.
- Aurora issues gameplay actions through `GB:` commands, then routes them into the emulator window through normal desktop focus plus keyboard input.
- `h` maps to Start in the current setup.
- Directional movement remains single-step by default unless a longer hold is explicitly chosen.
- VBA-RR gameplay input currently depends on the emulator window actually owning focus. A correct command can still fail to move the game if a menu, editor, or other window is foreground.

## FireRed notes
- FireRed is visually easier for the model than Blue because it has richer color and stronger scene contrast.
- In-game `SAVE` is not treated as trusted emulator persistence for soak runs.
- Operator save-state behavior is informational only:
- `F1` saves to slot 1.
- `Shift+F1` loads slot 1.
- `Shift+F2` through `Shift+F10` save to slots 2 through 10.
- `F2` through `F10` load from slots 2 through 10.
- These are operator/manual notes, not callable Aurora runtime commands.

## Suggested slot discipline
- FireRed main branch: slot 1.
- FireRed side experiments: slots 2 and 3.
- Blue main branch: slot 4.
- Blue side experiments: slots 5 and 6.
- Slots 7 through 10 remain free for future use.

## Recovery playbook
- If gameplay seems obstructed, first suspect wrong foreground window, dropdown menus, or editor/desktop dominance.
- Safe recovery order:
- refocus VBA-RR
- dismiss stray menu or dropdown with `Esc`
- click the emulator client area center if needed
- retry one small movement or Start press
- If a run remains obstructed, prefer diagnosis over spamming inputs.

## What to report during debugging
- visible scene guess
- foreground window guess
- whether gameplay looks unobstructed
- last input attempted
- whether the attempt visibly changed the scene
- safest next action if confidence is low

## Known weak points
- Foreground can look correct while a menu layer still steals input.
- Stale chat/runtime text can briefly mislabel the current view after recovery.
- Overlay/input logs can show a dispatched key even when the game itself did not respond.
