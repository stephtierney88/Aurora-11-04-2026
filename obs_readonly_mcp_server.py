from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from aurora_mcp_server import McpRequestError, _json_text, _tool_result
from obs_readonly_client import ObsReadOnlyClient, ObsReadOnlyError, READ_REQUESTS, obs_authority


SERVER_NAME = "obs-readonly"
SERVER_VERSION = "0.1.0"
SERVER_INSTRUCTIONS = (
    "This OBS server is strictly read-only. It uses an authenticated loopback connection "
    "for bounded version, scene/input inventory, current-scene items, recording, and streaming "
    "observations. It never starts OBS, changes configuration or scenes, records, streams, "
    "reads source settings or stream keys, captures media, or submits arbitrary requests. "
    "Readbacks are sequential, not an atomic OBS snapshot; unavailable means unknown, not stopped."
)
PROTOCOL_VERSIONS = ("2025-11-25", "2026-07-28", "2025-06-18", "2025-03-26", "2024-11-05")


def discover_obs_executable(explicit: str | None = None) -> Path | None:
    candidates = [Path(explicit)] if explicit else [
        Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "obs-studio" / "bin" / "64bit" / "obs64.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def installed_obs_version(path: Path | None) -> str | None:
    if os.name != "nt" or path is None:
        return None
    try:
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(ctypes.c_wchar_p(str(path)), None)
        if not 0 < size <= 65536:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(ctypes.c_wchar_p(str(path)), 0, size, buffer):
            return None
        pointer, length = ctypes.c_void_p(), ctypes.c_uint()
        if not version.VerQueryValueW(buffer, ctypes.c_wchar_p("\\"), ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
            return None
        fields = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        return ".".join(str(value) for value in (fields[2] >> 16, fields[2] & 65535, fields[3] >> 16, fields[3] & 65535))
    except (OSError, AttributeError):
        return None


class ObsReadOnlyMcpServer:
    def __init__(self, root: str | Path, *, client: ObsReadOnlyClient | None = None,
                 obs_executable: str | None = None) -> None:
        self.root = Path(root).resolve()
        self.client = client if client is not None else ObsReadOnlyClient()
        self.obs_executable = discover_obs_executable(obs_executable)

    def installation_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "aurora_obs_installation_v1", "read_only": True,
            "found": self.obs_executable is not None,
            "executable": str(self.obs_executable) if self.obs_executable else None,
            "installed_version": installed_obs_version(self.obs_executable),
            "connection": self.client.configuration_snapshot(), "authority": obs_authority(),
        }

    @staticmethod
    def tool_definitions() -> list[dict[str, Any]]:
        result = []
        for name, description in (
            ("obs_get_installation", "Inspect installation and sanitized connection configuration without connecting."),
            ("obs_get_status", "Read bounded, authenticated OBS version, scene/input, current-scene item, and output state."),
            ("obs_observe", "Return an OBS readback in a correlated terminal no-mutation receipt."),
        ):
            schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
            if name == "obs_observe":
                schema["properties"] = {
                    key: {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,128}$"}
                    for key in ("client_id", "request_id")
                }
                schema["required"] = ["client_id", "request_id"]
            result.append({
                "name": name, "description": description, "inputSchema": schema,
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            })
        return result

    @staticmethod
    def resource_definitions() -> list[dict[str, Any]]:
        return [
            {"uri": "obs://" + name, "name": "obs-" + name, "mimeType": "application/json"}
            for name in ("capabilities", "installation", "status")
        ]

    @staticmethod
    def prompt_definitions() -> list[dict[str, Any]]:
        return [{"name": "obs_readonly_preflight", "description": "Inspect OBS connection readiness and bounded state; stop before any app mutation.", "arguments": []}]

    def self_check(self) -> dict[str, Any]:
        return {
            "server_name": SERVER_NAME, "server_version": SERVER_VERSION,
            "read_only": True, "tool_count": 3, "resource_count": 3, "prompt_count": 1,
            "allowed_obs_requests": sorted(READ_REQUESTS), "authority": obs_authority(),
            "installation": self.installation_snapshot(), "opens_connection": False,
        }

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise McpRequestError(-32602, "Tool arguments must be an object.")
        allowed = {"client_id", "request_id"} if name == "obs_observe" else set()
        if set(arguments) - allowed:
            raise McpRequestError(-32602, "Unexpected tool arguments.")
        try:
            if name == "obs_get_installation":
                payload = self.installation_snapshot()
            elif name == "obs_get_status":
                payload = self.client.observe()
            elif name == "obs_observe":
                payload = self.client.observation_receipt(arguments.get("client_id"), arguments.get("request_id"))
            else:
                raise McpRequestError(-32602, "Unknown OBS tool.")
        except ObsReadOnlyError as error:
            raise McpRequestError(-32602, error.reason) from None
        return _tool_result(payload)

    def _dispatch(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}, "prompts": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}, "instructions": SERVER_INSTRUCTIONS,
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
            uri = params.get("uri")
            if uri == "obs://capabilities":
                payload = self.self_check()
            elif uri == "obs://installation":
                payload = self.installation_snapshot()
            elif uri == "obs://status":
                payload = self.client.observe()
            else:
                raise McpRequestError(-32602, "Unknown OBS resource.")
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": _json_text(payload)}]}
        if method == "prompts/list":
            return {"prompts": self.prompt_definitions()}
        if method == "prompts/get":
            if params.get("name") != "obs_readonly_preflight" or params.get("arguments", {}):
                raise McpRequestError(-32602, "Unknown prompt or unexpected arguments.")
            return {"messages": [{"role": "user", "content": {"type": "text", "text": "Call obs_get_installation, then obs_get_status. Distinguish configured from connected, and partial or unknown from stopped. Report the observation interval; it is not atomic. Do not enable the server, launch OBS, change scenes/settings, record, stream, or capture media."}}]}
        if method == "completion/complete":
            return {"completion": {"values": [], "total": 0, "hasMore": False}}
        raise McpRequestError(-32601, "Method not found.")

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        if "id" not in message:
            return None
        request_id = message["id"]
        if request_id is not None and type(request_id) not in (int, str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request ID"}}
        try:
            params = message.get("params", {})
            if not isinstance(params, dict):
                raise McpRequestError(-32602, "Params must be an object.")
            return {"jsonrpc": "2.0", "id": request_id, "result": self._dispatch(message["method"], params)}
        except McpRequestError as error:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": error.code, "message": error.message}}
        except Exception:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal error"}}


def run_stdio(server: ObsReadOnlyMcpServer) -> int:
    while True:
        raw = sys.stdin.buffer.readline(65537)
        if not raw:
            return 0
        oversized = len(raw) > 65536
        if oversized:
            while raw and not raw.endswith(b"\n"):
                raw = sys.stdin.buffer.readline(65537)
        elif not raw.strip():
            continue
        try:
            if oversized:
                raise ValueError()
            response = server.handle_message(json.loads(raw))
        except (ValueError, UnicodeError, RecursionError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid or oversized JSON"}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=True, separators=(",", ":")), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only, authenticated local OBS MCP/CLI adapter.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--obs", default="", help="Installation discovery only; never executes the path.")
    parser.add_argument("--obs-config", type=Path, help="Operator-selected OBS WebSocket config; never accepted via MCP.")
    parser.add_argument("--port", type=int, help="Explicit local port; use AURORA_OBS_WEBSOCKET_PASSWORD for a test instance.")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--max-items", type=int, default=100)
    modes = parser.add_mutually_exclusive_group()
    for mode in ("self-check", "installation", "status", "observe"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--client-id", default="aurora-cli")
    parser.add_argument("--request-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = ObsReadOnlyClient(config_path=args.obs_config, port=args.port,
                                   timeout_seconds=args.timeout_seconds, max_items=args.max_items)
        server = ObsReadOnlyMcpServer(args.root, client=client, obs_executable=args.obs or None)
        if args.self_check or args.installation:
            print(_json_text(server.self_check() if args.self_check else server.installation_snapshot()))
            return 0
        if args.status or args.observe:
            payload = client.observe() if args.status else client.observation_receipt(args.client_id, args.request_id or uuid.uuid4().hex)
            print(_json_text(payload))
            return 0 if (payload.get("complete") or payload.get("result") == "observed") else 2
        return run_stdio(server)
    except ObsReadOnlyError as error:
        print(_json_text({"error": error.reason}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
