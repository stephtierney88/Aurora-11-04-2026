# name=Aurora Read-Only Bridge

import json
import math
import time

import device
import general
import midi
import transport
import ui


BRIDGE_VERSION = "0.2.0"
READBACK_SCHEMA = "aurora_fl_studio_readback_v1"
HEARTBEAT_INTERVAL_SECONDS = 2.0
MAX_SYSEX_PAYLOAD_BYTES = 4096
SYSEX_PREFIX = bytes([0xF0, 0x7D, 0x41, 0x55, 0x52, 0x01])

_sequence = 0
_last_write_monotonic = 0.0
_last_status = ""
_session_id = format(int(time.time() * 1000), "x")


def _safe_call(callback, default):
    try:
        return callback()
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _fl_version():
    parts = []
    for mode in (0, 1, 2, 3):
        parts.append(str(_safe_call(lambda mode=mode: ui.getVersion(mode), 0)))
    return ".".join(parts)


def _snapshot(active):
    return {
        "schema_version": READBACK_SCHEMA,
        "bridge_version": BRIDGE_VERSION,
        "read_only": True,
        "active": bool(active),
        "session_id": _session_id,
        "sequence": _sequence,
        "captured_at_unix_ms": int(time.time() * 1000),
        "fl": {
            "version": _fl_version(),
            "midi_scripting_api_version": _safe_int(
                _safe_call(lambda: general.getVersion(), 0)
            ),
        },
        "device": {
            "port": _safe_int(_safe_call(lambda: device.getPortNumber(), -1), -1),
        },
        "project": {
            "changed_flag": _safe_int(
                _safe_call(lambda: general.getChangedFlag(), -1), -1
            ),
        },
        "transport": {
            "is_playing": bool(_safe_call(lambda: transport.isPlaying(), 0)),
            "is_recording": bool(_safe_call(lambda: transport.isRecording(), 0)),
            "loop_mode": _safe_int(_safe_call(lambda: transport.getLoopMode(), -1), -1),
            "song_position_ms": _safe_float(
                _safe_call(lambda: transport.getSongPos(midi.SONGLENGTH_MS), 0.0)
            ),
            "song_length_ms": _safe_int(
                _safe_call(lambda: transport.getSongLength(midi.SONGLENGTH_MS), 0)
            ),
            "position_hint": str(
                _safe_call(lambda: transport.getSongPosHint(), "") or ""
            )[:128],
        },
        "capabilities": {
            "version_readback": True,
            "project_dirty_readback": True,
            "transport_readback": True,
            "transport_control": False,
            "project_mutation": False,
            "arbitrary_python": False,
        },
    }


def _report_status(message):
    global _last_status
    if message != _last_status:
        print(message)
        _last_status = message


def _emit_readback(active=True, force=False):
    global _last_write_monotonic
    global _sequence

    now = time.monotonic()
    if not force and now - _last_write_monotonic < HEARTBEAT_INTERVAL_SECONDS:
        return

    try:
        if not bool(_safe_call(lambda: device.isAssigned(), False)):
            _report_status("Aurora read-only bridge waiting for linked MIDI output")
            return False
        _sequence += 1
        payload = _snapshot(active)
        encoded = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        if len(encoded) > MAX_SYSEX_PAYLOAD_BYTES:
            raise ValueError("snapshot exceeds SysEx payload limit")
        device.midiOutSysex(SYSEX_PREFIX + encoded + bytes([0xF7]))
        _last_write_monotonic = now
        _report_status("Aurora read-only bridge heartbeat active")
        return True
    except Exception as error:
        detail = str(error).replace("\r", " ").replace("\n", " ")[:160]
        suffix = ": " + detail if detail else ""
        _report_status(
            "Aurora read-only bridge heartbeat failed: "
            + type(error).__name__
            + suffix
        )
        return False


def OnInit():
    if _emit_readback(active=True, force=True):
        print("Aurora Read-Only Bridge init ok")
    else:
        print("Aurora Read-Only Bridge init incomplete")


def OnDeInit():
    _emit_readback(active=False, force=True)


def OnIdle():
    _emit_readback(active=True, force=False)


def OnProjectLoad(status):
    del status
    _emit_readback(active=True, force=True)


def OnRefresh(flags):
    del flags
    _emit_readback(active=True, force=False)
