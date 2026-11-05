# Replace an older Aurora preview

Recommended: keep the old folder as a backup, install this snapshot into a new folder, and move selected data only after the new copy works. Do not unzip over the old installation or run two copies against the same files. This is the November 5 **release 54** refresh; the public repository retains its original November 4 name. If you already downloaded an earlier November 5 build, use a distinct `r54` folder below.

## 1. Stop and preserve the old copy

1. In the old Control Panel, choose **Pause inference**, then **Cancel work**, inspect pending work/held inputs, and choose **Stop runtime**. Close its panel/popouts and any local validation console you started. Closing only a window may leave a worker alive.
2. If unsure, ask your setup AI to identify the old worker by its full executable/script path and process creation time. Do not kill every Python process; other apps may use Python.
3. Preserve anything you want: goal exports, chat/history, custom Init, profiles and your own source changes. Keep those backups private. Do not copy their whole folder into the new installation.
4. In File Explorer, rename the stopped old folder, for example `Aurora-11-04-2026` → `Aurora-backup-before-r54`. Choose another backup name if that already exists. Also remove or retarget shortcuts that still open it. Renaming does not migrate the old virtual environment; leave it with the backup.

## 2. Get the new copy

Use GitHub **Code → Download ZIP**, extract it and give it a distinct name such as `Aurora-preview-2026-11-05-r54`. Or, from the parent folder where you want it:

```powershell
git clone https://github.com/stephtierney88/Aurora-11-04-2026.git Aurora-preview-2026-11-05-r54
cd Aurora-preview-2026-11-05-r54
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe aurora_preflight.py --json
.\.venv\Scripts\python.exe aurora_preflight.py --surface panel --display --json
$env:AURORA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
.\launch_aurora2_ui.cmd
```

The repository keeps its original November 4 name; its README/release notes identify the updated snapshot. Python 3.12 is also supported by the release checks; substitute `py -3.12` if that is installed. The explicit interpreter override prevents an old `AURORA_PYTHON` from selecting the previous environment. Do not copy the old `.venv` or install the historical dependency freeze over this one.

## 3. Start clean, then migrate deliberately

Start the new runtime paused. Follow [the human guide](README_FOR_HUMANS.md), check auth/model access and effective settings, and demonstrate chat/Pause/Cancel/reset before actions. Reset changes selected runtime settings; it does not erase saved files or authenticate you.

- Keep your API key in your secure environment setup. Never copy it into source/chat. Aurora's ChatGPT registration lives outside the checkout under your Windows account, so it may already be visible; folder deletion does not sign you out. Use Aurora's connection UI to manage it. Never copy that cache to another machine/person.
- Import selected goal/history data through supported commands after backing up the new state. Compare counts/text and check failures. Ask an AI to inspect compatibility before importing older complex profiles.
- Do not transfer exported `aurora_control_panel_state.json`, pending inboxes, execution/admission journals, request receipts, lock/PID files, temporary folders or the entire memory/settings directory blindly. Old queued work can conflict with fresh sessions.
- Keep custom prompts separately, compare them with current guidance, and explicitly choose the intended Init source. Do not silently replace updated command instructions with a stale prompt.
- Recalibrate the new runtime's display/emulator settings; old coordinates and timing are not portable.

## 4. Remove the backup only when satisfied

After the new copy works and needed data is preserved, close anything using the old folder, verify its exact path in File Explorer and delete that backup to the Recycle Bin. Keep it longer if uncertain. Deleting a checkout does not delete external auth stores, provider accounts or global environment variables. No history rewrite or destructive Git reset is needed.

If you maintain a customized Git checkout, commit/stash your work and have your AI review the incoming diff instead of blindly overwriting it. A fresh sibling installation remains the easiest way to avoid stale files and rollback safely.
