from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


READ_REQUESTS = frozenset({
    "GetVersion", "GetSceneList", "GetInputList", "GetSceneItemList",
    "GetRecordStatus", "GetStreamStatus",
})
MAX_MESSAGE_BYTES = 256 * 1024
PASSWORD_ENV = "AURORA_OBS_WEBSOCKET_PASSWORD"


class ObsReadOnlyError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_obs_config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"


@dataclass(frozen=True)
class ObsConfiguration:
    reason: str
    enabled: bool | None = None
    auth_required: bool | None = None
    port: int | None = None
    password: str = field(default="", repr=False)


def read_obs_configuration(path: Path) -> ObsConfiguration:
    try:
        with path.open("rb") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            return ObsConfiguration("configuration_invalid")
        data = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(data, dict):
            return ObsConfiguration("configuration_invalid")
    except FileNotFoundError:
        return ObsConfiguration("configuration_missing")
    except (OSError, UnicodeError, ValueError):
        return ObsConfiguration("configuration_unreadable")
    port = data.get("server_port")
    password = data.get("server_password")
    return ObsConfiguration(
        reason="read",
        enabled=data.get("server_enabled") if type(data.get("server_enabled")) is bool else None,
        auth_required=data.get("auth_required") if type(data.get("auth_required")) is bool else None,
        port=port if type(port) is int and 1 <= port <= 65535 else None,
        password=password if isinstance(password, str) and 0 < len(password) <= 4096 else "",
    )


def obs_authority() -> dict[str, bool]:
    return {
        "observation": True, "loopback_client_only": True,
        "recording_control": False, "streaming_control": False,
        "scene_mutation": False, "source_settings": False, "screenshots": False,
        "config_mutation": False, "launch_obs": False, "arbitrary_requests": False,
        "aurora_control": False, "automatic_replay": False,
    }


def request_token(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
        raise ObsReadOnlyError("invalid_request_identity")
    return value


def _text(value: Any, limit: int = 256) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(character for character in value[:limit] if ord(character) >= 32 and ord(character) != 127)


def _number(value: Any) -> int | float | None:
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _flag(value: Any) -> bool | None:
    return value if type(value) is bool else None


def authentication_response(password: str, authentication: Mapping[str, Any]) -> str:
    salt, challenge = authentication.get("salt"), authentication.get("challenge")
    if not all(isinstance(value, str) and 0 < len(value) <= 1024 for value in (salt, challenge)):
        raise ObsReadOnlyError("invalid_authentication_challenge")
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


def _list_readback(data: Mapping[str, Any], key: str, kind: str, limit: int) -> dict[str, Any]:
    rows = data.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ObsReadOnlyError("invalid_response")
    name_key = {"scenes": "sceneName", "inputs": "inputName", "items": "sourceName"}[kind]
    if any(not isinstance(row.get(name_key), str) for row in rows):
        raise ObsReadOnlyError("invalid_response")
    result = []
    for row in rows[:limit]:
        clean = {"name": _text(row[name_key])}
        if kind == "scenes":
            clean.update(uuid=_text(row.get("sceneUuid"), 64), index=_number(row.get("sceneIndex")))
        elif kind == "inputs":
            clean.update(uuid=_text(row.get("inputUuid"), 64), kind=_text(row.get("inputKind"), 128))
        else:
            clean.update(
                id=_number(row.get("sceneItemId")), kind=_text(row.get("inputKind"), 128),
                enabled=_flag(row.get("sceneItemEnabled")), locked=_flag(row.get("sceneItemLocked")),
                is_group=_flag(row.get("isGroup")),
            )
        result.append(clean)
    return {"available": True, "total": len(rows), "returned": len(result), "truncated": len(rows) > limit, "items": result}


def _output_readback(data: Mapping[str, Any], *, recording: bool) -> dict[str, Any]:
    active = _flag(data.get("outputActive"))
    if active is None:
        raise ObsReadOnlyError("invalid_response")
    secondary = "outputPaused" if recording else "outputReconnecting"
    flag = _flag(data.get(secondary))
    if flag is None:
        raise ObsReadOnlyError("invalid_response")
    return {
        "available": True, "active": active,
        "paused" if recording else "reconnecting": flag,
        "duration_ms": _number(data.get("outputDuration")),
        "bytes": _number(data.get("outputBytes")),
    }


class ObsReadOnlyClient:
    def __init__(self, *, config_path: Path | None = None, port: int | None = None,
                 timeout_seconds: float = 8.0, max_items: int = 100) -> None:
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise ObsReadOnlyError("invalid_port")
        if not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 30:
            raise ObsReadOnlyError("invalid_timeout")
        if type(max_items) is not int or not 1 <= max_items <= 500:
            raise ObsReadOnlyError("invalid_item_limit")
        self.config_path = Path(config_path) if config_path is not None else default_obs_config_path()
        self.port = port
        self.timeout_seconds = float(timeout_seconds)
        self.max_items = max_items

    def configuration_snapshot(self) -> dict[str, Any]:
        config = read_obs_configuration(self.config_path)
        return {
            "reason": config.reason, "server_enabled": config.enabled,
            "auth_required": config.auth_required, "configured_port": config.port,
            "client_port": self.port or config.port or 4455,
            "credential_available": bool(os.environ.get(PASSWORD_ENV) or config.password),
            "credential_source": "environment" if os.environ.get(PASSWORD_ENV) else "obs_configuration",
            "host": "127.0.0.1", "changes_configuration": False,
            "server_bind_address_verified": False,
        }

    def _connection_settings(self) -> tuple[int, str]:
        config = read_obs_configuration(self.config_path)
        password = os.environ.get(PASSWORD_ENV) or config.password
        # An explicit port plus environment credential can target an operator-owned test instance.
        explicit = self.port is not None and bool(os.environ.get(PASSWORD_ENV))
        if not explicit:
            if config.reason != "read":
                raise ObsReadOnlyError(config.reason)
            if config.enabled is not True:
                raise ObsReadOnlyError("server_disabled")
            if config.auth_required is not True:
                raise ObsReadOnlyError("authentication_required")
            if config.port is None:
                raise ObsReadOnlyError("invalid_port")
        if not password or len(password) > 4096:
            raise ObsReadOnlyError("credential_missing")
        return self.port or config.port or 4455, password

    @staticmethod
    def _receive(connection: Any, deadline: float, opcode: int) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        raw = connection.recv(timeout=remaining)
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ObsReadOnlyError("invalid_message")
        try:
            message = json.loads(raw)
        except (ValueError, RecursionError):
            raise ObsReadOnlyError("invalid_message") from None
        if not isinstance(message, dict) or type(message.get("op")) is not int or message["op"] != opcode or not isinstance(message.get("d"), dict):
            raise ObsReadOnlyError("unexpected_message")
        return message["d"]

    def _request(self, connection: Any, deadline: float, name: str,
                 data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = data or {}
        if name not in READ_REQUESTS:
            raise ObsReadOnlyError("request_not_allowlisted")
        if name == "GetSceneItemList":
            if set(data) != {"sceneName"} or not isinstance(data["sceneName"], str) or len(data["sceneName"]) > 1024:
                raise ObsReadOnlyError("invalid_scene_query")
        elif data:
            raise ObsReadOnlyError("unexpected_request_data")
        request_id = "aurora-obs-" + uuid.uuid4().hex
        connection.send(json.dumps({"op": 6, "d": {"requestType": name, "requestId": request_id, "requestData": data}}))
        response = self._receive(connection, deadline, 7)
        if response.get("requestId") != request_id or response.get("requestType") != name:
            raise ObsReadOnlyError("response_identity_mismatch")
        status = response.get("requestStatus")
        if not isinstance(status, dict) or type(status.get("result")) is not bool or type(status.get("code")) is not int:
            raise ObsReadOnlyError("invalid_request_status")
        if not status["result"]:
            raise ObsReadOnlyError("request_failed")
        if status["code"] != 100 or not isinstance(response.get("responseData"), dict):
            raise ObsReadOnlyError("invalid_response")
        return response["responseData"]

    def _inspect(self, connection: Any, deadline: float, password: str,
                 snapshot: dict[str, Any]) -> None:
        hello = self._receive(connection, deadline, 0)
        if type(hello.get("rpcVersion")) is not int or hello["rpcVersion"] < 1:
            raise ObsReadOnlyError("unsupported_rpc_version")
        if not isinstance(hello.get("authentication"), dict):
            raise ObsReadOnlyError("authentication_required")
        authentication = authentication_response(password, hello["authentication"])
        connection.send(json.dumps({"op": 1, "d": {"rpcVersion": 1, "authentication": authentication, "eventSubscriptions": 0}}))
        identified = self._receive(connection, deadline, 2)
        if type(identified.get("negotiatedRpcVersion")) is not int or identified["negotiatedRpcVersion"] != 1:
            raise ObsReadOnlyError("unsupported_rpc_version")
        snapshot["authenticated"] = True
        version = self._request(connection, deadline, "GetVersion")
        supported = version.get("availableRequests")
        if not isinstance(supported, list) or any(not isinstance(value, str) for value in supported) or not isinstance(version.get("obsVersion"), str) or not isinstance(version.get("obsWebSocketVersion"), str):
            raise ObsReadOnlyError("invalid_version_response")
        snapshot["version"] = {
            "obs": _text(version["obsVersion"], 64), "websocket": _text(version["obsWebSocketVersion"], 64),
            "rpc": 1, "supported_reads": sorted(READ_REQUESTS.intersection(supported)),
        }
        snapshot["available"] = True
        program_scene = None
        requests = (
            ("GetSceneList", "scenes"), ("GetInputList", "inputs"),
            ("GetRecordStatus", "recording"), ("GetStreamStatus", "streaming"),
            ("GetSceneItemList", "program_scene_items"),
        )
        for name, section in requests:
            if name not in supported:
                snapshot["sections"][section] = {"available": False, "reason": "unsupported_request"}
                continue
            if name == "GetSceneItemList" and not program_scene:
                snapshot["sections"][section] = {"available": False, "reason": "program_scene_unavailable"}
                continue
            try:
                data = self._request(connection, deadline, name, {"sceneName": program_scene} if name == "GetSceneItemList" else None)
                if section == "scenes":
                    clean = _list_readback(data, "scenes", "scenes", self.max_items)
                    program_scene = data.get("currentProgramSceneName")
                    if not isinstance(program_scene, str) or not 0 < len(program_scene) <= 1024:
                        raise ObsReadOnlyError("invalid_response")
                    clean.update(current_program=_text(program_scene), current_preview=_text(data.get("currentPreviewSceneName")))
                elif section == "inputs":
                    clean = _list_readback(data, "inputs", "inputs", self.max_items)
                elif section == "program_scene_items":
                    clean = _list_readback(data, "sceneItems", "items", self.max_items)
                    clean.update(scene_name=_text(program_scene), recursive=False)
                else:
                    clean = _output_readback(data, recording=section == "recording")
                snapshot["sections"][section] = clean
            except ObsReadOnlyError as error:
                snapshot["sections"][section] = {"available": False, "reason": error.reason}
                if error.reason not in {"request_failed", "invalid_response"}:
                    raise
        snapshot["complete"] = all(row.get("available") for row in snapshot["sections"].values())
        snapshot["reason"] = "ready" if snapshot["complete"] else "partial_readback"

    def observe(self) -> dict[str, Any]:
        started = time.monotonic()
        snapshot: dict[str, Any] = {
            "schema_version": "aurora_obs_observation_v1", "read_only": True,
            "available": False, "complete": False, "authenticated": False,
            "reason": "not_observed", "started_at": utc_now(), "atomic": False,
            "cached": False, "sections": {}, "authority": obs_authority(),
        }
        try:
            port, password = self._connection_settings()
            try:
                from websockets.sync.client import connect
                from websockets.exceptions import ConnectionClosed, InvalidHandshake
            except ImportError:
                raise ObsReadOnlyError("dependency_missing") from None
            logger = logging.Logger("aurora.obs.private")
            logger.disabled = True
            deadline = started + self.timeout_seconds
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=self.timeout_seconds) as sock:
                    # Supplied sockets retain their timeout; the library owns receive deadlines.
                    sock.settimeout(None)
                    with connect(
                        f"ws://127.0.0.1:{port}", sock=sock, proxy=None,
                        subprotocols=["obswebsocket.json"], compression=None,
                        open_timeout=max(0.001, deadline - time.monotonic()), close_timeout=0.2,
                        ping_interval=None, max_size=MAX_MESSAGE_BYTES, max_queue=4, logger=logger,
                    ) as connection:
                        self._inspect(connection, deadline, password, snapshot)
            except ConnectionClosed as error:
                code = error.rcvd.code if error.rcvd is not None else None
                raise ObsReadOnlyError("authentication_failed" if code == 4009 else "connection_closed") from None
            except InvalidHandshake:
                raise ObsReadOnlyError("websocket_handshake_failed") from None
        except ObsReadOnlyError as error:
            snapshot["reason"] = error.reason
        except TimeoutError:
            snapshot["reason"] = "timeout"
        except OSError:
            snapshot["reason"] = "connection_unavailable"
        snapshot["completed_at"] = utc_now()
        snapshot["duration_seconds"] = round(time.monotonic() - started, 3)
        return snapshot

    def observation_receipt(self, client_id: str, request_id: str) -> dict[str, Any]:
        client_id, request_id = request_token(client_id), request_token(request_id)
        command = {"command": "obs.observe", "client_id": client_id, "request_id": request_id}
        digest = hashlib.sha256(json.dumps(command, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        snapshot = self.observe()
        return {
            "schema_version": "aurora_obs_observation_receipt_v1",
            "receipt_id": "obs-" + uuid.uuid4().hex, "client_id": client_id, "request_id": request_id,
            "normalized_command_digest": digest,
            "result": "observed" if snapshot["complete"] else ("partial" if snapshot["available"] else "unavailable"),
            "terminal": True, "uncertain": False, "mutation_attempted": False,
            "automatic_replay_allowed": False, "observation": snapshot,
        }
