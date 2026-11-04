# Blender Read-Only MCP Reference

## Purpose

- Let local Codex clients discover Blender and inspect explicit `.blend` files without scene mutation.
- Keep Blender outside the Aurora runtime and command bridge. Codex coordinates two sibling read-only servers: `aurora-readonly` for Aurora context and `blender-readonly` for Blender scene metadata.
- Establish a narrow proof before any future disposable-copy write experiment.

## Current Slice

- Window 24 Slice 2, opened and validated on 2026-08-12.
- Server: `blender_readonly_mcp_server.py`, name/version `blender-readonly` / `0.1.0`.
- In-Blender inventory: `blender_scene_inventory.py`.
- Windows launcher: `blender-readonly-mcp.cmd`.
- Blender installation: Blender `5.2.0 LTS`, installed through the official `BlenderFoundation.Blender` Winget package.
- Executable: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`.

## Authority Boundary

The adapter exposes no tool for:

- caller-supplied Python, Python expressions, scripts, or Blender arguments
- Blender operators or GUI control
- scene/object/material mutation
- save, Save As, render, import, or export
- Aurora commands, settings, bridge writes, or receipts
- arbitrary direct target paths or directory scans requested by the caller
- opening community MCP servers or general MCP hosting/client behavior

The outer server validates one explicit existing `.blend` path beneath configured roots. It then invokes only the bundled inventory script with this fixed posture:

```text
blender.exe --background --factory-startup --disable-autoexec --disable-depsgraph-on-file-load <scene.blend> --python blender_scene_inventory.py -- --object-limit <bounded-limit>
```

The object limit is clamped to `0..500` with default `100`, timeout to `10..180` seconds, and scene size defaults to a 2 GiB maximum. The server parses only the line prefixed by `AURORA_BLENDER_INVENTORY_JSON=`.

This is an application-level read-only contract, not an operating-system sandbox. The primary `.blend` path is resolved through symlinks and allowlisted, but Blender may resolve linked libraries or other dependencies named inside that file. Inspect only trusted scene files. The inventory reports linked-library basenames and external-image counts, but does not return their full paths or perform separate external-file existence checks. Raw Blender stdout/stderr is not returned on inspection errors because it may mention transitive asset paths.

## MCP Surface

Tools:

- `blender_get_installation(refresh=false)`: installation/version/build summary, allowlisted roots, bundled proof scene, and authority posture.
- `blender_inspect_scene_file(path, object_limit=100, timeout_seconds=60)`: bounded read-only scene, object, collection, datablock, animation, render-setting, and external-asset metadata.

Resources:

- `blender://capabilities`
- `blender://installation`

Prompt:

- `blender_readonly_preflight`: verify installation and roots before inspecting an explicit scene; stop before any requested mutation.

Both tools advertise read-only, nondestructive, idempotent, closed-world annotations.

## Allowed Roots

The checked-in Windows launcher and current Codex registration allow:

- `C:/Users/YourName
- `C:\Program Files\Blender Foundation\Blender 5.2`

Add another project root explicitly when its `.blend` files need inspection. Do not broaden this to a drive root or user profile by default.

## Local Use

```powershell
.\blender-readonly-mcp.cmd --self-check
.\blender-readonly-mcp.cmd --inspect "C:\path\to\scene.blend" --object-limit 250
```

Register with the shared local Codex configuration:

```powershell
codex mcp add blender-readonly -- "C:\Anaconda\envs\aurora\python.exe" "C:/Users/YourName" --root "C:/Users/YourName" --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --allowed-root "C:/Users/YourName" --allowed-root "C:\Program Files\Blender Foundation\Blender 5.2"
```

Restart Codex desktop after adding or changing a local MCP server so a new task receives the refreshed tool inventory.

## Validated Real Scene Proof

Proof file:

`C:\Program Files\Blender Foundation\Blender 5.2\5.2\scripts\startup\bl_app_templates_system\Sculpting\startup.blend`

Observed through the outer adapter on 2026-08-12:

- schema `blender_readonly_scene_inventory_v1`, `read_only=true`
- Blender `5.2.0 LTS`, build hash `fbe6228777e7`, platform `Windows`, background mode true
- one scene and three objects: one camera, one light, and one mesh named `Quad Sphere`
- one material and one linked library named `essentials_brushes-mesh_sculpt.blend`
- background/factory-startup true, Python autoexec and dependency-graph-on-load disabled, object/scene rows not truncated
- all save/render/import/export/operator/arbitrary-Python/GUI/Aurora-control authority flags false
- no scene or application write was attempted

## Coordination Contract

A Codex host may:

1. read Aurora status/maps through `aurora-readonly`;
2. read an explicit allowlisted Blender scene through `blender-readonly`;
3. synthesize a plan or comparison in the Codex task.

This does not route Blender data into Aurora state, create an Aurora receipt, or let either MCP server invoke the other. A future receipt/intake path needs its own schema, request identity, sanitization, and explicit authorization.

Protocol-level proof on 2026-08-12 initialized both stdio servers, listed five Aurora tools and two Blender tools, called `aurora_get_status` and `blender_inspect_scene_file`, and produced `aurora_operator_status_v1` plus `blender_readonly_scene_inventory_v1`. Aurora reported monitor `ok` while stopped; Blender reported `5.2.0 LTS`, three objects, all adapter-authority flags false, empty stderr, no cross-server calls, and no writes attempted.

## Next Gate

Window 24 Slice 2 stops at read-only inventory. Any first Blender write proof must be a separately opened slice with:

- a disposable scene or explicit Save As copy, never the original
- a tiny allowlisted operation set
- request/client identity and before/after evidence
- deterministic target selection and stop-on-uncertain behavior
- no arbitrary Python, plugin installation, broad filesystem access, or silent overwrite

The selected Window 24 progression has completed the guarded FL Studio read-only heartbeat and stdio observation proof. OBS read-only discovery is next; Blender mutation remains parked until explicitly reopened.

## Primary References

- Blender Python API quickstart: `https://docs.blender.org/api/current/info_quickstart.html`
- Blender command-line arguments: `https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html`
- OpenAI Codex MCP: `https://developers.openai.com/codex/mcp`
