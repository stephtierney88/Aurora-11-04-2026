# Aurora Read-Only MCP and External-App Integration Reference

## Purpose

- Expose Aurora status, maps, command metadata, and typed-setting readback to local Codex clients without granting mutation authority.
- Keep external-app integrations optional, local-first, and separately gated.
- Prefer free/open-source application editions and direct first-party control surfaces. The existing paid FL Studio installation is the one planned exception.

## Current Slices

- Window 24 Slice 1: dependency-free local stdio MCP server in `aurora_mcp_server.py`.
- Server name/version: `aurora-readonly` / `0.1.1` (compact-current-status routing updated 2026-09-04).
- Windows helper: `aurora-mcp.cmd`.
- The server reuses Aurora's existing control-plane, command-catalog, and typed-settings read helpers.
- It does not enter the Aurora command bridge and does not make Aurora a general MCP client or host.
- Window 24 Slice 2: official free Blender `5.2.0 LTS` plus a separate local `blender-readonly` MCP/CLI adapter. The Blender adapter inventories explicit allowlisted `.blend` files and does not add Blender tools to `aurora-readonly`.
- Durable Blender details: `blender-readonly-mcp-reference.md`, mirrored as `SHOW_REFERENCE_PACK(blender_readonly_mcp)`.
- Window 24 Slice 3: separate local `fl-studio-readonly` MCP/CLI adapter plus an Aurora-specific FL MIDI device script. Installation, linked-port assignment, live heartbeat capture, correlated observation, and real stdio proof are complete.
- Durable FL Studio details: `fl-studio-readonly-mcp-reference.md`, mirrored as `SHOW_REFERENCE_PACK(fl_studio_readonly_mcp)`.

## Authority Boundary

The server has no tools for:

- command submission or raw-text dispatch
- settings preview, apply, or rollback
- uncertain-mutation replay or reconciliation
- model/API calls
- desktop, Blender, FL Studio, OBS, or Resolve control
- arbitrary file reads
- loading third-party MCP servers

Command and setting records may describe capabilities that Aurora itself can perform. That metadata is not authority for this MCP connection. Command search returns `execution_enabled=false`; settings responses return `mcp_authority.settings_mutation=false`.

## Tools

- `aurora_get_status`: process, state freshness, mode, monitor, queue/bridge, and mutation-admission summaries.
- `aurora_get_dashboard(event_limit)`: shared operator dashboard with bounded sanitized receipt events.
- `aurora_search_commands(query, category, limit)`: search the generated 336-command catalog without executing anything.
- `aurora_get_settings(category, maturity)`: read all or filtered typed-setting definitions and observed values.
- `aurora_describe_setting(key)`: read one setting's schema, constraints, aliases, lock posture, and observed value.

All five tools advertise MCP read-only, nondestructive, idempotent, closed-world annotations.

## Resources and Prompts

Resources:

- `aurora://mcp/capabilities`
- `aurora://operator/status`
- `aurora://operator/dashboard`
- `aurora://settings/current`
- `aurora://maps/runtime-lite`
- `aurora://maps/runtime-deep`
- `aurora://roadmap/current`: detailed roadmap/validation ledger
- `aurora://handoff/current`: compact `docs/notes/aurora_current_status.md`; the historical handoff is linked, not loaded by default

Prompts:

- `aurora_map_first`: load the lite map and compact current status; use function skeleton lookup, then the deep map or detailed roadmap when needed.
- `aurora_operator_preflight`: inspect status/dashboard freshness and unresolved mutation posture before operational claims.

Static resources use a fixed allowlist beneath the Aurora root and are capped at 300,000 characters. Dashboard events omit raw command arguments.

## Local Use

Self-check:

```powershell
.\aurora-mcp.cmd --self-check
```

Register the stdio server with the shared local Codex configuration:

```powershell
codex mcp add aurora-readonly -- "C:\Anaconda\envs\aurora\python.exe" "C:/Users/YourName" --root "C:/Users/YourName"
```

Inspect or remove it:

```powershell
codex mcp get aurora-readonly
codex mcp remove aurora-readonly
```

Restart the Codex/ChatGPT desktop client after adding or changing a local server. The desktop app, Codex CLI, and IDE extension share MCP configuration on the same host.

## Local Application Inventory - 2026-08-12

- FL Studio 2025: present, paid/licensed installation, `25.2.5.5319` (previous Aurora notes identify Producer/All Plugins capability). Aurora's separate read-only device script is installed and assigned to linked `Aurora FL Bridge` input/output port `0`; live heartbeat and stdio observation proofs passed on 2026-08-13.
- OBS Studio: present, `31.0.3`. OBS 28 and newer bundle obs-websocket; use localhost, authentication, and a dedicated secret.
- Blender: present, official free Blender `5.2.0 LTS`, installed through Winget as `BlenderFoundation.Blender`; executable `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`.
- DaVinci Resolve: not found in standard install paths or uninstall records.
- loopMIDI `1.0.16.27`: installed, with an `Aurora FL Bridge` virtual port used for the read-only controller assignment.
- Legacy FL Studio 20/21 uninstall entries exist; new work targets the active FL Studio 2025 executable only.

Do not record FL Studio account/customer identifiers in Aurora notes, logs, or receipts.

## Selected Integration Ladder

### 1. Read-Only Aurora MCP Facade

Slice 1 complete and checkpointed. Discovery, status, resources, prompts, and stdio lifecycle are proved while every mutation lane remains absent, not merely disabled by a flag.

### 2. Codex Coordinating Aurora Plus Blender

- Slice 2 complete in source and validation: official free Blender `5.2.0 LTS` is installed, and the first-party Python API/command-line surface is wrapped by separate `blender_readonly_mcp_server.py` / `blender_scene_inventory.py` files.
- Version/capability discovery and a real read-only scene inventory passed against Blender's bundled Sculpting startup file: one scene, three objects, one material, one linked library, with background/factory-startup true and Python autoexec disabled.
- The adapter exposes two read-only tools, two resources, and one preflight prompt. It accepts only explicit `.blend` files under configured roots and cannot run caller-supplied Python or Blender operators. It is not an OS sandbox: trusted scenes may reference linked dependencies that Blender resolves transitively.
- First write proof must use a disposable scene or explicit Save As copy, bounded object operations, a request ID, and before/after evidence.
- Keep Blender control as a separate local tool/MCP or CLI. Aurora remains the read-only context server and receipt destination until a later integration slice is authorized.
- Any community Blender MCP must be optional, source-reviewed, version-pinned, localhost-only, and replaceable by a thin first-party API adapter.

### 3. Guarded FL Studio Prototype

- Slice 3 source is implemented around the paid FL Studio 2025 installation and free loopMIDI; no additional paid connector is required.
- `fl_studio_device_script.py` is installed in its own Aurora controller folder and does not modify vendor scripts. From lifecycle/idle callbacks it emits only a bounded ASCII-JSON heartbeat over the linked MIDI output, with version, device port, project-changed flag, and bounded transport readback.
- `fl_studio_readonly_mcp_server.py` captures only the Aurora-prefixed SysEx packet, validates and sanitizes its allowlisted schema, atomically writes the fixed outer readback, and exposes installation, bridge status, and correlated observation receipts through three read-only tools, three resources, and one preflight prompt. Missing/stale readback is explicit unavailable evidence.
- The device script has no MIDI-input callback or transport/project/plugin mutation call. The MCP server cannot install the script, launch or drive FL, execute arbitrary Python, or replay unavailable work.
- Activation proof passed on 2026-08-13 after preserving the active project as `Aurora_FL_Bridge_Activation_Recovery_2026-08-12_2341.flp` and restarting FL. The embedded runtime rejected `os.mkdir`, `os.makedirs`, and `_io.FileIO`, so bridge `0.2.0` moved FL-side telemetry from filesystem I/O to bounded SysEx. Activation sequences advanced through `7`, `20`, `21`, and stdio `30`; final closure status/observe/stdio proofs captured `325`, `331`, and `339`. Receipts remained terminal, certain, read-only, and non-replayable; all 77 discovered tests passed, including 16 focused FL tests.
- Carrying `client_id`, `request_id`, normalized command digest, admission decision, and terminal/uncertain receipt semantics is implemented for observations. A tiny transport prototype remains a separately authorized future slice against a backed-up disposable project.
- The separate hum-transcription roadmap may produce MIDI/artifacts for FL Studio, but does not gain DAW-control authority implicitly.

### 4. OBS and Resolve Media Chain

- OBS first: use its bundled v5 WebSocket on localhost with authentication. Start read-only with version, scene, source, recording, and streaming status; gate scene changes and recording controls later.
- Resolve second: use the free edition if its installed version exposes the required local scripting operations. Probe availability before choosing an adapter; do not assume Studio-only external scripting works in Resolve Free.
- Treat media import, timeline edits, render queue changes, file overwrite, streaming, and recording as separate mutation classes with previews/checkpoints and receipts.
- A basic OBS chain can proceed without Resolve. Resolve is optional, not a paid prerequisite.

### 5. General Aurora MCP Host/Client

Later architectural project only. It requires server lifecycle ownership, capability discovery, transport/auth policy, tool namespaces, leases, cancellation, receipts, secret handling, trust tiers, UI/settings, and failure isolation. Do not grow the read-only facade into this role accidentally.

## Relationship to the Runtime Roadmap

The external-app ladder and Aurora runtime ladder are independent:

- Current selected work: Window 24 MCP/app integration ladder; Slices 1-2 prove read-only Aurora and Blender surfaces, and Slice 3 proves the live FL Studio read-only heartbeat/receipt path. OBS read-only discovery is the next selected gate.
- Retained runtime candidate: CX-4 stepwise observation, `action -> settle -> capture -> inspect`, with stop-on-uncertain behavior.
- Retained follow-ups: operator reconciliation/new-request-ID workflow, persistent personal/project settings, agent leases/peer receipts, and CX-5 event timelines/hooks.
- App Server/OAuth, broader desktop authority, sibling-project mutations, and general MCP hosting remain separately authorized lanes.

## Primary References

- OpenAI Codex MCP: `https://developers.openai.com/codex/mcp`
- Blender Python API: `https://docs.blender.org/api/current/`
- FL Studio MIDI scripting: `https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm`
- OBS WebSocket: `https://github.com/obsproject/obs-websocket`
- Resolve developer docs: installed application, `Help > Documentation > Developer`; release notes at `https://documents.blackmagicdesign.com/`
