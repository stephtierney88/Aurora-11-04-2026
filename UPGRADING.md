# Upgrade to Aurora Preview 84

Use a **new folder** so old state/settings cannot silently affect the new preview. Do not run both copies against the same inbox, ports or runtime files.

1. In the old panel, Pause inference, Cancel work, then Stop runtime. Close its panel after shutdown. Keep other applications running.
2. Rename the old folder, for example `Aurora-preview54-backup`, or leave it untouched elsewhere. Keep its credentials and valuable state private. There is no need to delete it.
3. Download tag `preview-2026.11.06-r84` into `Aurora-preview84`, or clone the public repository into that new folder and check out the tag. Do not copy the old `.venv`, caches, inbox, PID files or runtime exports into it.
4. Follow [README_FOR_HUMANS.md](README_FOR_HUMANS.md) to create the environment, install requirements, run preflight and launch `launch_aurora2_ui.cmd` using `AURORA_PYTHON`. Confirm the title says Preview 84.
5. Configure your own credentials securely or complete sign-in. Start paused, inspect auth/model/settings, and demonstrate the cancellation/default-reset controls before a bounded live task.

Existing valid legacy configurations remain supported, but inspect and import settings deliberately after the clean start. Preserve originals before migrating memory or recovery data. Durable recovery v1/v2 remains supported; the new archive preview does not migrate it. Never retry an uncertain old input merely because it is in another folder: the protection depends on retaining the correct identity store. Do not share a live recovery store between two runtimes.

If you prefer Git updates in an existing checkout, first back up local changes and private data, stop its runtime, then fetch and inspect the new tag. Avoid destructive reset/clean commands. A clean separate checkout is the easiest way to compare releases or return to the previous one.

After the new version works and you have preserved anything valuable, you may delete the exact old backup folder yourself. Deletion is optional; do not delete shared credential stores, emulator saves or unrelated project folders. This update contains no user state to restore automatically.
