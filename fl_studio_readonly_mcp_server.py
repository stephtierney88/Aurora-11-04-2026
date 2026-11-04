from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SERVER_NAME = "fl-studio-readonly"
SERVER_TITLE = "FL Studio Read-Only Bridge Inspector"
SERVER_VERSION = "0.2.1"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
DEVICE_SCRIPT_FOLDER = "Aurora Read Only Bridge"
DEVICE_SCRIPT_FILENAME = "device_Aurora Read Only Bridge.py"
READBACK_FILENAME = "aurora_readback.json"
READBACK_SCHEMA = "aurora_fl_studio_readback_v1"
DEFAULT_STALE_AFTER_SECONDS = 10.0
DEFAULT_MAX_READBACK_BYTES = 64 * 1024
DEFAULT_MIDI_INPUT_NAME = "Aurora FL Bridge"
DEFAULT_MIDI_CAPTURE_SECONDS = 2.5
MIDI_SYSEX_PREFIX = bytes([0x7D, 0x41, 0x55, 0x52, 0x01])
SERVER_INSTRUCTIONS = (
    "This FL Studio server is strictly read-only. It may discover the local FL Studio 2025 "
    "installation and read the bounded Aurora device-script heartbeat. It cannot start or "
    "stop playback, record, seek, load plugins, save or overwrite projects, render, execute "
    "caller-supplied Python, drive the GUI, or control Aurora. Device-script installation is "
    "available only as an explicit local CLI maintenance action and is not an MCP tool."
)


class FlStudioReadOnlyError(ValueError):
    pass


class McpRequestError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = int(code)
        self.message = str(message)
        self.data = data


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "isError": bool(is_error),
    }
    if not is_error and isinstance(payload, dict):
        result["structuredContent"] = payload
    return result


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_iso(timestamp: float | None = None) -> str:
    value = time.time() if timestamp is None else float(timestamp)
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def decode_fl_studio_sysex_data(
    data: Any, *, maximum_bytes: int = DEFAULT_MAX_READBACK_BYTES
) -> dict[str, Any] | None:
    try:
        encoded = bytes(data)
    except (TypeError, ValueError):
        return None
    if not encoded.startswith(MIDI_SYSEX_PREFIX):
        return None
    payload = encoded[len(MIDI_SYSEX_PREFIX) :]
    if len(payload) > max(1024, int(maximum_bytes)):
        raise FlStudioReadOnlyError("FL Studio MIDI readback exceeds the size limit.")
    try:
        decoded = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlStudioReadOnlyError("FL Studio MIDI readback is not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise FlStudioReadOnlyError("FL Studio MIDI readback must be a JSON object.")
    return decoded


def _version_key(path: Path) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(path.parent.name))
    return tuple(int(value) for value in numbers) or (0,)


def _registry_string(root_name: str, subkey: str, value_name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        root = getattr(winreg, root_name)
        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except (AttributeError, OSError, ImportError):
        return ""
    return os.path.expandvars(str(value or "").strip())


def discover_fl_studio_executable(
    explicit: str | os.PathLike[str] | None = None,
) -> Path | None:
    if explicit:
        try:
            resolved = Path(explicit).expanduser().resolve(strict=True)
        except OSError:
            return None
        return resolved if resolved.is_file() else None

    candidates: list[Path] = []
    env_path = str(os.environ.get("FL_STUDIO_EXECUTABLE") or "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    install_path = _registry_string(
        "HKEY_CURRENT_USER", r"Software\Image-Line\Shared\Paths", "Install path"
    )
    if install_path:
        candidates.append(Path(install_path) / "FL64.exe")
    command = shutil.which("FL64") or shutil.which("FL64.exe")
    if command:
        candidates.append(Path(command))
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
        image_line = program_files / "Image-Line"
        if image_line.exists():
            candidates.extend(
                sorted(
                    image_line.glob("FL Studio */FL64.exe"),
                    key=_version_key,
                    reverse=True,
                )
            )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def discover_fl_studio_user_data_root(
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_path = str(os.environ.get("FL_STUDIO_USER_DATA") or "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    shared_data = _registry_string(
        "HKEY_CURRENT_USER", r"Software\Image-Line\Shared\Paths", "Shared data"
    )
    if shared_data:
        return Path(shared_data).expanduser().resolve()
    return (Path.home() / "Documents" / "Image-Line").resolve()


def discover_fl_studio_readback_path(
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_path = str(os.environ.get("AURORA_FL_STUDIO_READBACK") or "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "Aurora" / READBACK_FILENAME).resolve()


def discover_fl_studio_display_version() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for root, subkey in roots:
        try:
            with winreg.OpenKey(root, subkey) as uninstall:
                count = winreg.QueryInfoKey(uninstall)[0]
                for index in range(count):
                    name = winreg.EnumKey(uninstall, index)
                    try:
                        with winreg.OpenKey(uninstall, name) as app:
                            display_name = str(winreg.QueryValueEx(app, "DisplayName")[0])
                            if display_name.strip().lower() != "fl studio 2025":
                                continue
                            return str(winreg.QueryValueEx(app, "DisplayVersion")[0]).strip()
                    except OSError:
                        continue
        except OSError:
            continue
    return ""


def install_device_script(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    readback_path: str | os.PathLike[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve(strict=True)
    target_path = Path(target).expanduser().resolve(strict=False)
    source_bytes = source_path.read_bytes()
    first_line = source_bytes.splitlines()[0].decode("utf-8", errors="replace").strip()
    if first_line != "# name=Aurora Read-Only Bridge":
        raise FlStudioReadOnlyError("Device script is missing the required Aurora controller name.")

    readback_directory: Path | None = None
    if readback_path is not None:
        readback_directory = Path(readback_path).expanduser().resolve(strict=False).parent
        readback_directory.mkdir(parents=True, exist_ok=True)

    existing_bytes = target_path.read_bytes() if target_path.is_file() else None
    if existing_bytes == source_bytes:
        result = {
            "schema_version": "aurora_fl_studio_device_install_v1",
            "installed": True,
            "changed": False,
            "source_sha256": _sha256_bytes(source_bytes),
            "target": str(target_path),
        }
        if readback_directory is not None:
            result["readback_directory"] = str(readback_directory)
            result["readback_directory_prepared"] = True
        return result
    if existing_bytes is not None and not force:
        raise FlStudioReadOnlyError(
            "A different Aurora FL Studio device script already exists; use --force-install to replace it."
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_name(target_path.name + ".tmp")
    temporary.write_bytes(source_bytes)
    os.replace(temporary, target_path)
    result = {
        "schema_version": "aurora_fl_studio_device_install_v1",
        "installed": True,
        "changed": True,
        "source_sha256": _sha256_bytes(source_bytes),
        "target": str(target_path),
    }
    if readback_directory is not None:
        result["readback_directory"] = str(readback_directory)
        result["readback_directory_prepared"] = True
    return result


class FlStudioReadOnlyMcpServer:
    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        fl_executable: str | os.PathLike[str] | None = None,
        user_data_root: str | os.PathLike[str] | None = None,
        device_script_source: str | os.PathLike[str] | None = None,
        readback_path: str | os.PathLike[str] | None = None,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        max_readback_bytes: int = DEFAULT_MAX_READBACK_BYTES,
        midi_input_name: str = DEFAULT_MIDI_INPUT_NAME,
        midi_capture_seconds: float = DEFAULT_MIDI_CAPTURE_SECONDS,
        midi_capture_enabled: bool = True,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.fl_executable = discover_fl_studio_executable(fl_executable)
        self.user_data_root = discover_fl_studio_user_data_root(user_data_root)
        self.device_script_source = Path(
            device_script_source or (Path(__file__).resolve().parent / "fl_studio_device_script.py")
        ).expanduser().resolve()
        self.device_script_dir = (
            self.user_data_root
            / "FL Studio"
            / "Settings"
            / "Hardware"
            / DEVICE_SCRIPT_FOLDER
        )
        self.device_script_target = self.device_script_dir / DEVICE_SCRIPT_FILENAME
        self.readback_path = discover_fl_studio_readback_path(readback_path)
        self.stale_after_seconds = max(1.0, float(stale_after_seconds))
        self.max_readback_bytes = max(1024, int(max_readback_bytes))
        self.midi_input_name = str(midi_input_name or DEFAULT_MIDI_INPUT_NAME).strip()
        self.midi_capture_seconds = max(0.05, float(midi_capture_seconds))
        self.midi_capture_enabled = bool(midi_capture_enabled)
        self._last_midi_capture: dict[str, Any] = {
            "enabled": self.midi_capture_enabled,
            "reason": "not_attempted" if self.midi_capture_enabled else "disabled",
        }
        self._tools = {
            "fl_studio_get_installation": self._tool_get_installation,
            "fl_studio_get_bridge_status": self._tool_get_bridge_status,
            "fl_studio_observe": self._tool_observe,
        }

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        }

    @staticmethod
    def _authority_posture() -> dict[str, bool]:
        return {
            "transport_control": False,
            "recording_control": False,
            "song_position_control": False,
            "project_mutation": False,
            "project_save_or_overwrite": False,
            "plugin_loading": False,
            "render": False,
            "arbitrary_python": False,
            "gui_control": False,
            "aurora_control": False,
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        annotations = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        return [
            {
                "name": "fl_studio_get_installation",
                "title": "Get FL Studio Installation",
                "description": (
                    "Read the discovered FL Studio 2025 executable, Aurora device-script "
                    "deployment posture, and disabled authority surface without launching FL Studio."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "annotations": annotations,
            },
            {
                "name": "fl_studio_get_bridge_status",
                "title": "Get FL Studio Bridge Status",
                "description": (
                    "Read and validate the bounded Aurora heartbeat produced by the active "
                    "FL Studio MIDI device script."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "annotations": annotations,
            },
            {
                "name": "fl_studio_observe",
                "title": "Observe FL Studio",
                "description": (
                    "Return the latest read-only FL Studio readback inside a terminal receipt "
                    "that preserves caller and request identity."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                        },
                        "request_id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                        },
                    },
                    "required": ["client_id", "request_id"],
                    "additionalProperties": False,
                },
                "annotations": annotations,
            },
        ]

    @staticmethod
    def resource_definitions() -> list[dict[str, Any]]:
        return [
            {
                "uri": "fl-studio://capabilities",
                "name": "fl-studio-readonly-capabilities",
                "title": "FL Studio Read-Only Capability Posture",
                "description": "Available readbacks and absent mutation authority.",
                "mimeType": "application/json",
            },
            {
                "uri": "fl-studio://installation",
                "name": "fl-studio-installation",
                "title": "FL Studio Installation",
                "description": "Discovered local installation and device-script deployment posture.",
                "mimeType": "application/json",
            },
            {
                "uri": "fl-studio://bridge-status",
                "name": "fl-studio-bridge-status",
                "title": "FL Studio Bridge Status",
                "description": "Latest validated read-only heartbeat and freshness posture.",
                "mimeType": "application/json",
            },
        ]

    @staticmethod
    def prompt_definitions() -> list[dict[str, Any]]:
        return [
            {
                "name": "fl_studio_readonly_preflight",
                "title": "FL Studio Read-Only Preflight",
                "description": (
                    "Inspect installation, heartbeat freshness, and read-only transport state "
                    "without issuing a DAW command."
                ),
                "arguments": [],
            }
        ]

    def installation_snapshot(self) -> dict[str, Any]:
        source_exists = self.device_script_source.is_file()
        target_exists = self.device_script_target.is_file()
        source_digest = (
            _sha256_bytes(self.device_script_source.read_bytes()) if source_exists else ""
        )
        target_digest = (
            _sha256_bytes(self.device_script_target.read_bytes()) if target_exists else ""
        )
        return {
            "schema_version": "fl_studio_readonly_installation_v1",
            "read_only": True,
            "found": self.fl_executable is not None,
            "executable": str(self.fl_executable or ""),
            "display_version": discover_fl_studio_display_version(),
            "user_data_root": str(self.user_data_root),
            "device_script": {
                "source": str(self.device_script_source),
                "target": str(self.device_script_target),
                "source_exists": source_exists,
                "installed": target_exists,
                "matches_source": bool(source_digest and source_digest == target_digest),
                "source_sha256": source_digest,
                "target_sha256": target_digest,
            },
            "readback_path": str(self.readback_path),
            "readback_transport": {
                "kind": "midi_sysex",
                "input_name": self.midi_input_name,
                "capture_enabled": self.midi_capture_enabled,
            },
            "launch_policy": {
                "launch_fl_studio": False,
                "modify_midi_settings": False,
                "install_device_script_via_mcp": False,
            },
            "authority": self._authority_posture(),
        }

    @staticmethod
    def _bounded_text(value: Any, *, maximum: int = 128) -> str:
        return value[:maximum] if isinstance(value, str) else ""

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        if isinstance(value, bool):
            return default
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return parsed if math.isfinite(parsed) else default

    @classmethod
    def _integer(cls, value: Any, default: int = 0) -> int:
        return int(cls._number(value, float(default)))

    @staticmethod
    def _boolean(value: Any, default: bool = False) -> bool:
        return value if isinstance(value, bool) else bool(default)

    def _sanitize_readback(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if payload.get("schema_version") != READBACK_SCHEMA:
            raise FlStudioReadOnlyError("FL Studio readback schema is not recognized.")
        if payload.get("read_only") is not True:
            raise FlStudioReadOnlyError("FL Studio readback did not assert read-only posture.")
        fl = payload.get("fl") if isinstance(payload.get("fl"), Mapping) else {}
        device_row = payload.get("device") if isinstance(payload.get("device"), Mapping) else {}
        project = payload.get("project") if isinstance(payload.get("project"), Mapping) else {}
        transport = (
            payload.get("transport") if isinstance(payload.get("transport"), Mapping) else {}
        )
        capabilities = (
            payload.get("capabilities")
            if isinstance(payload.get("capabilities"), Mapping)
            else {}
        )
        return {
            "schema_version": READBACK_SCHEMA,
            "bridge_version": self._bounded_text(payload.get("bridge_version"), maximum=32),
            "read_only": True,
            "active": self._boolean(payload.get("active"), False),
            "session_id": self._bounded_text(payload.get("session_id"), maximum=64),
            "sequence": self._integer(payload.get("sequence"), 0),
            "captured_at_unix_ms": self._integer(payload.get("captured_at_unix_ms"), 0),
            "fl": {
                "version": self._bounded_text(fl.get("version"), maximum=64),
                "midi_scripting_api_version": self._integer(
                    fl.get("midi_scripting_api_version"), 0
                ),
            },
            "device": {
                "port": self._integer(device_row.get("port"), -1),
            },
            "project": {
                "changed_flag": self._integer(project.get("changed_flag"), -1),
            },
            "transport": {
                "is_playing": self._boolean(transport.get("is_playing"), False),
                "is_recording": self._boolean(transport.get("is_recording"), False),
                "loop_mode": self._integer(transport.get("loop_mode"), -1),
                "song_position_ms": self._number(transport.get("song_position_ms"), 0.0),
                "song_length_ms": self._integer(transport.get("song_length_ms"), 0),
                "position_hint": self._bounded_text(
                    transport.get("position_hint"), maximum=128
                ),
            },
            "capabilities": {
                "version_readback": self._boolean(
                    capabilities.get("version_readback"), False
                ),
                "project_dirty_readback": self._boolean(
                    capabilities.get("project_dirty_readback"), False
                ),
                "transport_readback": self._boolean(
                    capabilities.get("transport_readback"), False
                ),
                "transport_control": False,
                "project_mutation": False,
                "arbitrary_python": False,
            },
        }

    def _capture_readback_from_midi(self, timeout_seconds: float) -> None:
        if not self.midi_capture_enabled:
            self._last_midi_capture = {"enabled": False, "reason": "disabled"}
            return
        try:
            import mido
        except ImportError:
            self._last_midi_capture = {
                "enabled": True,
                "reason": "dependency_missing",
            }
            return

        try:
            names = list(mido.get_input_names())
        except Exception as error:
            self._last_midi_capture = {
                "enabled": True,
                "reason": "input_discovery_failed",
                "error_type": type(error).__name__,
            }
            return
        expected = self.midi_input_name.casefold()
        port_name = next(
            (
                name
                for name in names
                if name.casefold() == expected
                or name.casefold().startswith(expected + " ")
            ),
            "",
        )
        if not port_name:
            self._last_midi_capture = {
                "enabled": True,
                "reason": "input_missing",
            }
            return

        deadline = time.monotonic() + max(0.05, float(timeout_seconds))
        try:
            with mido.open_input(port_name) as port:
                while time.monotonic() < deadline:
                    message = port.poll()
                    if message is None:
                        time.sleep(0.01)
                        continue
                    if getattr(message, "type", "") != "sysex":
                        continue
                    decoded = decode_fl_studio_sysex_data(
                        getattr(message, "data", ()),
                        maximum_bytes=self.max_readback_bytes,
                    )
                    if decoded is None:
                        continue
                    readback = self._sanitize_readback(decoded)
                    self.readback_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = None
                    try:
                        # CLI and MCP processes can capture the same cable concurrently.
                        with tempfile.NamedTemporaryFile(
                            mode="w", encoding="utf-8", newline="\n", delete=False,
                            dir=self.readback_path.parent,
                            prefix=self.readback_path.name + ".", suffix=".tmp",
                        ) as handle:
                            temporary = Path(handle.name)
                            json.dump(readback, handle, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
                            handle.write("\n")
                        os.replace(temporary, self.readback_path)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                    self._last_midi_capture = {
                        "enabled": True,
                        "reason": "captured",
                        "input_name": self.midi_input_name,
                        "sequence": readback.get("sequence", 0),
                    }
                    return
        except (OSError, FlStudioReadOnlyError) as error:
            self._last_midi_capture = {
                "enabled": True,
                "reason": "capture_failed",
                "error_type": type(error).__name__,
            }
            return
        except Exception as error:
            self._last_midi_capture = {
                "enabled": True,
                "reason": "capture_failed",
                "error_type": type(error).__name__,
            }
            return
        self._last_midi_capture = {
            "enabled": True,
            "reason": "timeout",
            "input_name": self.midi_input_name,
        }

    def _cached_bridge_status(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "schema_version": "fl_studio_readonly_bridge_status_v1",
            "read_only": True,
            "available": False,
            "fresh": False,
            "active": False,
            "reason": "readback_missing",
            "stale_after_seconds": self.stale_after_seconds,
            "readback_path": str(self.readback_path),
            "midi_capture": dict(self._last_midi_capture),
            "authority": self._authority_posture(),
        }
        try:
            # Read bytes and metadata from the same file, even during atomic replacement.
            with self.readback_path.open("rb") as handle:
                raw = handle.read(self.max_readback_bytes + 1)
                stat = os.fstat(handle.fileno())
            if len(raw) > self.max_readback_bytes:
                raise FlStudioReadOnlyError("FL Studio readback exceeds the configured size limit.")
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, Mapping):
                raise FlStudioReadOnlyError("FL Studio readback must be a JSON object.")
            readback = self._sanitize_readback(decoded)
        except FileNotFoundError:
            return base
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FlStudioReadOnlyError("FL Studio readback could not be validated.") from error

        now = time.time()
        file_age_seconds = max(0.0, now - stat.st_mtime)
        captured_at = readback["captured_at_unix_ms"] / 1000.0
        valid_capture_time = 0 < captured_at <= now
        capture_age_seconds = now - captured_at if valid_capture_time else None
        age_seconds = max(file_age_seconds, capture_age_seconds) if valid_capture_time else None
        fresh = valid_capture_time and age_seconds <= self.stale_after_seconds
        active = bool(readback.get("active", False)) and fresh
        reason = "ready" if active else ("stale" if not fresh else "inactive")
        if not valid_capture_time:
            reason = "invalid_capture_time"
        base.update(
            {
                "available": True,
                "fresh": fresh,
                "active": active,
                "reason": reason,
                "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
                "capture_age_seconds": round(capture_age_seconds, 3) if capture_age_seconds is not None else None,
                "file_age_seconds": round(file_age_seconds, 3),
                "readback_sha256": _sha256_bytes(raw),
                "readback_modified_at": _utc_iso(stat.st_mtime),
                "readback_bytes": len(raw),
                "readback": readback,
            }
        )
        return base

    def bridge_status(self) -> dict[str, Any]:
        capture_seconds = self.midi_capture_seconds
        if self.midi_capture_enabled:
            try:
                if self._cached_bridge_status()["fresh"]:
                    capture_seconds = min(capture_seconds, 0.1)
            except FlStudioReadOnlyError:
                pass
        self._capture_readback_from_midi(capture_seconds)
        return self._cached_bridge_status()

    def capability_posture(self) -> dict[str, Any]:
        installation = self.installation_snapshot()
        try:
            bridge = self.bridge_status()
        except FlStudioReadOnlyError:
            bridge = {"available": False, "fresh": False, "active": False, "reason": "invalid"}
        return {
            "schema_version": "fl_studio_readonly_capability_posture_v1",
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "read_only": True,
            "tool_count": len(self.tool_definitions()),
            "resource_count": len(self.resource_definitions()),
            "prompt_count": len(self.prompt_definitions()),
            "installation_found": bool(installation.get("found", False)),
            "device_script_installed": bool(
                installation.get("device_script", {}).get("installed", False)
            ),
            "bridge_available": bool(bridge.get("available", False)),
            "bridge_fresh": bool(bridge.get("fresh", False)),
            "bridge_active": bool(bridge.get("active", False)),
            "authority": self._authority_posture(),
        }

    @staticmethod
    def _request_token(arguments: Mapping[str, Any], name: str) -> str:
        value = str(arguments.get(name) or "").strip()
        if not value:
            raise FlStudioReadOnlyError(f"{name} is required.")
        if len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
            raise FlStudioReadOnlyError(
                f"{name} may contain only letters, digits, dot, underscore, colon, and hyphen."
            )
        return value

    def observation_receipt(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        client_id = self._request_token(arguments, "client_id")
        request_id = self._request_token(arguments, "request_id")
        normalized = {
            "schema_version": "aurora_fl_studio_observation_command_v1",
            "command": "fl_studio.observe",
            "client_id": client_id,
            "request_id": request_id,
        }
        command_digest = _sha256_bytes(
            json.dumps(normalized, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
        try:
            observation = self.bridge_status()
            result = "observed" if observation.get("active") else "unavailable"
            error = ""
        except FlStudioReadOnlyError as caught:
            observation = {
                "schema_version": "fl_studio_readonly_bridge_status_v1",
                "read_only": True,
                "available": False,
                "fresh": False,
                "active": False,
                "reason": "invalid_readback",
                "authority": self._authority_posture(),
            }
            result = "failed"
            error = str(caught)
        terminal_material = (
            command_digest + ":" + str(observation.get("readback_sha256") or result)
        ).encode("utf-8")
        return {
            "schema_version": "aurora_fl_studio_observation_receipt_v1",
            "receipt_id": _sha256_bytes(terminal_material)[:24],
            "client_id": client_id,
            "request_id": request_id,
            "normalized_command_digest": command_digest,
            "admission": {
                "decision": "allow",
                "reason": "read_only_observation",
            },
            "result": result,
            "terminal": True,
            "uncertain": False,
            "mutation_attempted": False,
            "automatic_replay_allowed": False,
            "created_at": _utc_iso(),
            "error": error,
            "observation": observation,
        }

    def _tool_get_installation(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        del arguments
        return self.installation_snapshot()

    def _tool_get_bridge_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        del arguments
        return self.bridge_status()

    def _tool_observe(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self.observation_receipt(arguments)

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _tool_result({"error": "Tool arguments must be an object."}, is_error=True)
        handler = self._tools.get(name)
        if handler is None:
            return _tool_result({"error": f"Unknown FL Studio read-only tool: {name}"}, is_error=True)
        try:
            return _tool_result(handler(arguments))
        except FlStudioReadOnlyError as error:
            return _tool_result({"error": str(error), "tool": name}, is_error=True)

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "fl-studio://capabilities":
            payload = self.capability_posture()
        elif uri == "fl-studio://installation":
            payload = self.installation_snapshot()
        elif uri == "fl-studio://bridge-status":
            payload = self.bridge_status()
        else:
            raise McpRequestError(-32602, f"Unknown FL Studio resource URI: {uri}")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": _json_text(payload),
                }
            ]
        }

    def _get_prompt(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        if name != "fl_studio_readonly_preflight":
            raise McpRequestError(-32602, f"Unknown FL Studio prompt: {name}")
        text = (
            "Run an FL Studio read-only preflight. Call fl_studio_get_installation, then "
            "fl_studio_get_bridge_status. Report whether the Aurora device script is installed, "
            "whether its heartbeat is fresh and active, and the observed play/record/position "
            "state. Do not start or stop playback, record, seek, save, render, load plugins, "
            "execute Python, or drive the FL Studio GUI."
        )
        return {
            "description": self.prompt_definitions()[0]["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }

    def _dispatch(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION),
                "capabilities": self.capabilities(),
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": SERVER_TITLE,
                    "version": SERVER_VERSION,
                },
                "instructions": SERVER_INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tool_definitions()}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": self.resource_definitions()}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/read":
            return self._read_resource(str(params.get("uri") or "").strip())
        if method == "prompts/list":
            return {"prompts": self.prompt_definitions()}
        if method == "prompts/get":
            return self._get_prompt(params)
        if method == "completion/complete":
            return {"completion": {"values": [], "total": 0, "hasMore": False}}
        raise McpRequestError(-32601, f"Method not found: {method}")

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return self._error_response(None, -32600, "Invalid Request")
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str) or not method.strip():
            if "id" not in message:
                return None
            return self._error_response(request_id, -32600, "Invalid Request")
        if "id" not in message:
            return None
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            return self._error_response(request_id, -32602, "Params must be an object.")
        try:
            result = self._dispatch(method.strip(), params)
        except McpRequestError as error:
            return self._error_response(request_id, error.code, error.message, error.data)
        except Exception:
            return self._error_response(request_id, -32603, "Internal error")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error_response(
        request_id: Any, code: int, message: str, data: Any = None
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": int(code), "message": str(message)}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def self_check(self) -> dict[str, Any]:
        payload = self.capability_posture()
        payload["root"] = str(self.root)
        payload["root_exists"] = self.root.exists()
        payload["device_script_source_exists"] = self.device_script_source.is_file()
        payload["tool_names"] = [row["name"] for row in self.tool_definitions()]
        payload["resource_uris"] = [row["uri"] for row in self.resource_definitions()]
        return payload


def run_stdio(server: FlStudioReadOnlyMcpServer, *, verbose: bool = False) -> int:
    for raw_line in sys.stdin.buffer:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        message: Any = None
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = server._error_response(None, -32700, "Parse error")
        else:
            response = server.handle_message(message)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        if verbose:
            method = message.get("method", "") if isinstance(message, dict) else ""
            print(f"fl-studio-readonly-mcp handled {method}", file=sys.stderr, flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only MCP facade for FL Studio state.")
    parser.add_argument(
        "--root",
        default=os.environ.get("AURORA_ROOT") or str(Path(__file__).resolve().parent),
    )
    parser.add_argument(
        "--fl",
        default=os.environ.get("FL_STUDIO_EXECUTABLE") or "",
        help="Optional explicit FL64.exe path.",
    )
    parser.add_argument(
        "--user-data-root",
        default=os.environ.get("FL_STUDIO_USER_DATA") or "",
        help="Optional Image-Line user-data root.",
    )
    parser.add_argument("--readback", default="", help="Optional explicit readback JSON path.")
    parser.add_argument("--stale-after-seconds", type=float, default=DEFAULT_STALE_AFTER_SECONDS)
    parser.add_argument("--max-readback-bytes", type=int, default=DEFAULT_MAX_READBACK_BYTES)
    parser.add_argument(
        "--midi-input",
        default=os.environ.get("AURORA_FL_STUDIO_MIDI_INPUT") or DEFAULT_MIDI_INPUT_NAME,
    )
    parser.add_argument(
        "--midi-capture-seconds",
        type=float,
        default=DEFAULT_MIDI_CAPTURE_SECONDS,
    )
    parser.add_argument("--no-midi-capture", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--installation", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--observe", action="store_true")
    parser.add_argument("--client-id", default="aurora-cli")
    parser.add_argument("--request-id", default="manual-observation")
    parser.add_argument("--install-device-script", action="store_true")
    parser.add_argument("--force-install", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = FlStudioReadOnlyMcpServer(
        args.root,
        fl_executable=args.fl or None,
        user_data_root=args.user_data_root or None,
        readback_path=args.readback or None,
        stale_after_seconds=args.stale_after_seconds,
        max_readback_bytes=args.max_readback_bytes,
        midi_input_name=args.midi_input,
        midi_capture_seconds=args.midi_capture_seconds,
        midi_capture_enabled=not bool(args.no_midi_capture),
    )
    try:
        if args.install_device_script:
            print(
                _json_text(
                    install_device_script(
                        server.device_script_source,
                        server.device_script_target,
                        readback_path=server.readback_path,
                        force=bool(args.force_install),
                    )
                )
            )
            return 0
        if args.self_check:
            print(_json_text(server.self_check()))
            return 0
        if args.installation:
            print(_json_text(server.installation_snapshot()))
            return 0
        if args.status:
            print(_json_text(server.bridge_status()))
            return 0
        if args.observe:
            print(
                _json_text(
                    server.observation_receipt(
                        {"client_id": args.client_id, "request_id": args.request_id}
                    )
                )
            )
            return 0
    except FlStudioReadOnlyError as error:
        print(_json_text({"error": str(error)}), file=sys.stderr)
        return 2
    return run_stdio(server, verbose=bool(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
