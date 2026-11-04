# FL Studio Read-Only MCP Reference

## Purpose

- Let local Codex clients discover FL Studio and observe a small, sanitized state snapshot without DAW mutation.
- Keep the FL Studio bridge separate from Aurora's runtime command path. Codex coordinates sibling read-only servers; neither adapter calls the other.
- Establish installation, capability, freshness, and receipt semantics before any transport-control experiment is considered.

## Current Slice

- Window 24 Slice 3, implemented on 2026-08-12 and activated on 2026-08-13.
- Server: `fl_studio_readonly_mcp_server.py`, name/version `fl-studio-readonly` / `0.2.1` (freshness and concurrent-cache repair, 2026-09-04).
- FL device script source: `fl_studio_device_script.py`, version `0.2.0`, unchanged by the September adapter repair.
- Windows launcher: `fl-studio-readonly-mcp.cmd`.
- FL Studio: `25.2.5.5319`, executable `C:\Program Files\Image-Line\FL Studio 2025\FL64.exe`.
- loopMIDI: `1.0.16.27`, with local port `Aurora FL Bridge`.
- Installed device-script target: `C:/Users/YourName Studio\Settings\Hardware\Aurora Read Only Bridge\device_Aurora Read Only Bridge.py`.
- Linked MIDI route: `Aurora FL Bridge`, input/output port `0`.
- Sanitized adapter readback target: `%LOCALAPPDATA%\Aurora\aurora_readback.json`.

At the 2026-08-13 activation proof, the controller was installed, visible, enabled, and linked bidirectionally to the `Aurora FL Bridge` virtual cable. FL's Script Output reported `heartbeat active` and `init ok`; fresh CLI and stdio MCP observations passed. This is historical proof, not current connection status. Before the clean restart, the active untitled work was preserved as `C:/Users/YourName Studio\Projects\Aurora_FL_Bridge_Activation_Recovery_2026-08-12_2341.flp`.

## Authority Boundary

The MCP adapter and device script expose no tool or callback for:

- play, stop, record, seek, tempo, loop, or other transport control
- channel, pattern, playlist, mixer, project, or plugin mutation
- project save, overwrite, render, import, or export
- caller-supplied Python, expressions, scripts, MIDI messages, or FL arguments
- GUI automation or Aurora command/settings control
- automatic replay of an unavailable or uncertain request

The device script implements lifecycle/readback callbacks only: `OnInit`, `OnDeInit`, `OnIdle`, `OnProjectLoad`, and `OnRefresh`. It deliberately has no MIDI input callback such as `OnMidiMsg` or `OnControlChange`.

This is an application-level read-only contract, not an operating-system sandbox. FL Studio 2025's embedded scripting runtime rejected ordinary `os.mkdir`, `os.makedirs`, and `_io.FileIO` calls during the activation proof. The device script therefore performs no filesystem I/O: it emits one bounded manufacturer-specific SysEx observation over the linked MIDI output. The outer Aurora-side adapter validates and sanitizes that packet, then writes only the fixed readback file.

## Readback Contract

The device script emits schema `aurora_fl_studio_readback_v1` at most once every two seconds, plus forced lifecycle updates. JSON is ASCII-escaped, capped at 4096 bytes in FL, and framed with Aurora's noncommercial SysEx prefix. The snapshot is deliberately small:

- bridge version, active flag, session ID, sequence, and capture time
- FL version and MIDI scripting API version
- selected MIDI device port number
- project changed flag, without project title or path
- playing/recording flags, loop mode, song position/length, and a bounded position hint
- explicit capability flags showing transport control, project mutation, and arbitrary Python as false

The outer adapter uses optional `mido` / `python-rtmidi` capture against the named virtual input, ignores unrelated MIDI and SysEx packets, caps decoded data at 64 KiB, requires the exact schema and `read_only=true`, allowlists output fields, bounds text, substitutes defaults for nonfinite numbers, and refuses string-to-boolean coercion. Freshness requires both a valid positive, nonfuture `captured_at_unix_ms` and a file/capture age within ten seconds. `age_seconds` is the older age; `capture_age_seconds` and `file_age_seconds` expose both. Missing/invalid/future capture times return `invalid_capture_time`, `fresh=false`, and `active=false`; touching or rewriting old data cannot refresh the source observation.

Only the sanitized object is atomically written to `%LOCALAPPDATA%\Aurora\aurora_readback.json`, through a unique same-directory temporary file per capture. Failed replacement cleans only that capture's temporary file. Cache bytes and metadata are read from the same open handle. The short recapture wait is used only when the validated cache is fresh. Customer/account IDs, project names, paths, plugin inventories, and arbitrary device-script output are not returned.

## MCP Surface

Tools:

- `fl_studio_get_installation`: discovered FL installation, device-script deployment/match status, readback path, and denied authority.
- `fl_studio_get_bridge_status`: validated heartbeat availability, freshness, active posture, and bounded readback.
- `fl_studio_observe(client_id, request_id)`: the latest observation inside a correlated terminal receipt.

Resources:

- `fl-studio://capabilities`
- `fl-studio://installation`
- `fl-studio://bridge-status`

Prompt:

- `fl_studio_readonly_preflight`: inspect installation and heartbeat freshness, then stop before any DAW command.

All tools advertise read-only, nondestructive, idempotent, closed-world annotations. Device-script installation is an explicit local CLI maintenance action and is not exposed as an MCP tool.

## Receipt Contract

`fl_studio_observe` preserves normalized `client_id` and `request_id`, adds a normalized command digest, and returns `terminal=true`, `uncertain=false`, `mutation_attempted=false`, and `automatic_replay_allowed=false`.

A fresh active heartbeat returns `result=observed`. A missing, stale, inactive, or invalid-capture-time heartbeat returns explicit `unavailable` evidence rather than guessing that FL is connected. Malformed, oversized, or unreadable telemetry returns a validation error and a terminal `failed` observation receipt. Repeating a read-only observation is allowed, but the adapter never converts it into a transport action.

## Local Use

```powershell
.\fl-studio-readonly-mcp.cmd --self-check
.\fl-studio-readonly-mcp.cmd --install-device-script
.\fl-studio-readonly-mcp.cmd --status
.\fl-studio-readonly-mcp.cmd --observe --client-id codex.local --request-id window24-fl-readback-001
```

MIDI capture defaults to `Aurora FL Bridge` and can be redirected or disabled for fixture/offline work with `--midi-input`, `--midi-capture-seconds`, or `--no-midi-capture`. Runtime dependencies are pinned in `requirements.txt` as `mido==1.3.3` and `python-rtmidi==1.5.8`.

Force installation is intentionally separate and explicit:

```powershell
.\fl-studio-readonly-mcp.cmd --install-device-script --force-install
```

Register with the shared local Codex configuration:

```powershell
codex mcp add fl-studio-readonly -- cmd.exe /d /c "C:/Users/YourName"
```

Restart Codex desktop after adding or changing a local MCP server so new tasks receive the refreshed tool inventory.

## Validation Status

2026-09-04 audit: regression tests cover rewritten stale payloads, invalid/future timestamps, shortened recapture waits, unique temporary files, and failed atomic replacement. A cache-only `--status --no-midi-capture` check correctly returned stale/inactive for sequence `421` captured on Aug 13. Live FL activation was not repeated; the device script was not reinstalled. See [current status](../../docs/notes/aurora_current_status.md) for the combined test and map validation.

Validated through the 2026-08-13 activation proof:

- all eleven mapped Python surfaces compiled; all 77 discovered tests passed, including 16 focused FL unit/protocol tests
- FL Studio and user-data discovery
- idempotent installation plus guarded overwrite behavior
- strict privacy/size/freshness/schema sanitization
- correlated terminal observation receipts and explicit missing-heartbeat behavior
- controller discovery plus input/output linkage to `Aurora FL Bridge` port `0`
- no mutation callbacks or transport/project/plugin calls in the device script
- FL Script Output showed the original embedded-Python filesystem failures, then showed `heartbeat active` / `init ok` after the SysEx transport reload
- activation sequence advancement from `7` to `20` to `21`, followed by stdio MCP sequence `30`; final closure status/CLI-observe/stdio proofs then captured `325`, `331`, and `339`
- `--status` returned `available=true`, `fresh=true`, `active=true`, `reason=ready`, FL `25.2.5.5319`, scripting API `40`, and bridge `0.2.0`
- `--observe` requests `window24-fl-activation-proof-2026-08-13` and `window24-fl-activation-closure-2026-08-13` returned `observed`, `terminal=true`, `uncertain=false`, `mutation_attempted=false`, and `automatic_replay_allowed=false`
- real stdio `initialize` plus `tools/call` requests `window24-fl-stdio-proof-2026-08-13` and `window24-fl-stdio-closure-2026-08-13` returned the same certain no-mutation receipt

An earlier auxiliary FL menu/output surface had rendered as a large black box and was hidden to restore the workspace. In the activation run, the correct `View > Script output` surface was responsive and useful. Durable activation evidence remains the sanitized heartbeat and correlated adapter receipt, not the GUI alone.

## Next Gate

The FL activation gate is complete. The selected external-app ladder now moves to OBS version/auth/scene/source/recording-state inspection. Resolve remains optional and later.

A tiny FL transport mutation such as play/stop remains a separately authorized future slice and should use a backed-up disposable test project, a narrow allowlist, request identity, before/after evidence, and stop-on-uncertain behavior. It is not implied by this read-only proof.

## Primary References

- Image-Line MIDI scripting manual: `https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm`
- Image-Line MIDI settings manual: `https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_midi.htm`
- loopMIDI: `https://www.tobias-erichsen.de/software/loopmidi.html`
- mido: `https://pypi.org/project/mido/`
- python-rtmidi: `https://pypi.org/project/python-rtmidi/`
- OpenAI Codex MCP: `https://developers.openai.com/codex/mcp`
