from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from aurora_cli import filter_command_catalog, load_command_catalog
from aurora_control_plane import (
    build_operator_dashboard,
    build_operator_status,
    control_plane_paths,
    read_json_file,
)
from aurora_settings_registry import (
    build_setting_readback,
    build_settings_snapshot,
    describe_setting_definition,
    registry_summary,
)


SERVER_NAME = "aurora-readonly"
SERVER_TITLE = "Aurora Read-Only Control Plane"
SERVER_VERSION = "0.1.1"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2026-07-28",
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
SERVER_INSTRUCTIONS = (
    "This Aurora server is read-only. Inspect status and dashboard freshness before "
    "drawing conclusions. Command search describes capabilities but never executes them. "
    "The server does not submit commands, change settings, replay mutations, call models, "
    "or control desktop applications. Treat uncertain receipts as unresolved."
)


class McpRequestError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = int(code)
        self.message = str(message)
        self.data = data


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    result = {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "isError": bool(is_error),
    }
    if not is_error and isinstance(payload, dict):
        result["structuredContent"] = payload
    return result


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid integer arguments.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Expected an integer value.") from error
    return max(minimum, min(maximum, parsed))


class AuroraReadOnlyMcpServer:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()
        self._tools = {
            "aurora_get_status": self._tool_get_status,
            "aurora_get_dashboard": self._tool_get_dashboard,
            "aurora_search_commands": self._tool_search_commands,
            "aurora_get_settings": self._tool_get_settings,
            "aurora_describe_setting": self._tool_describe_setting,
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        read_only_annotations = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        return [
            {
                "name": "aurora_get_status",
                "title": "Get Aurora Status",
                "description": (
                    "Read process liveness, exported-state freshness, active modes, scheduler, "
                    "monitor, queue/bridge, and mutation-admission summaries."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "annotations": read_only_annotations,
            },
            {
                "name": "aurora_get_dashboard",
                "title": "Get Aurora Dashboard",
                "description": (
                    "Read the shared structured operator dashboard, including sanitized recent "
                    "receipt events and all typed setting readbacks."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_limit": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 50,
                            "default": 8,
                            "description": "Maximum sanitized receipt events to include.",
                        }
                    },
                    "additionalProperties": False,
                },
                "annotations": read_only_annotations,
            },
            {
                "name": "aurora_search_commands",
                "title": "Search Aurora Commands",
                "description": (
                    "Search Aurora's generated command catalog by name, signature, category, or "
                    "summary. This describes commands and never submits or executes one."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "default": "",
                            "description": "Case-insensitive catalog search text.",
                        },
                        "category": {
                            "type": "string",
                            "default": "",
                            "description": "Optional exact generated command category.",
                        },
                        "detail": {
                            "type": "boolean", "default": False,
                            "description": "Include parameter/result contract coverage and source location.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                        },
                    },
                    "additionalProperties": False,
                },
                "annotations": read_only_annotations,
            },
            {
                "name": "aurora_get_settings",
                "title": "Get Aurora Settings",
                "description": (
                    "Read typed Aurora setting definitions and current or last-observed values. "
                    "This does not preview or apply a settings transaction."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "default": "",
                            "description": "Optional exact settings category.",
                        },
                        "maturity": {
                            "type": "string",
                            "default": "",
                            "description": "Optional exact settings maturity.",
                        },
                    },
                    "additionalProperties": False,
                },
                "annotations": read_only_annotations,
            },
            {
                "name": "aurora_describe_setting",
                "title": "Describe Aurora Setting",
                "description": (
                    "Read one setting's schema, aliases, constraints, defaults, lock metadata, "
                    "and current or last-observed value."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Canonical setting key or registered alias.",
                        }
                    },
                    "required": ["key"],
                    "additionalProperties": False,
                },
                "annotations": read_only_annotations,
            },
        ]

    def resource_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": "aurora://mcp/capabilities",
                "name": "aurora-mcp-capabilities",
                "title": "Aurora MCP Capability Posture",
                "description": "Read-only facade scope, counts, and disabled authority lanes.",
                "mimeType": "application/json",
            },
            {
                "uri": "aurora://operator/status",
                "name": "aurora-operator-status",
                "title": "Aurora Operator Status",
                "description": "Current process and exported-state status snapshot.",
                "mimeType": "application/json",
            },
            {
                "uri": "aurora://operator/dashboard",
                "name": "aurora-operator-dashboard",
                "title": "Aurora Operator Dashboard",
                "description": "Shared read-only dashboard with sanitized receipt events.",
                "mimeType": "application/json",
            },
            {
                "uri": "aurora://settings/current",
                "name": "aurora-settings-current",
                "title": "Aurora Typed Settings",
                "description": "All typed setting readbacks and version metadata.",
                "mimeType": "application/json",
            },
            {
                "uri": "aurora://maps/runtime-lite",
                "name": "aurora-runtime-lite-map",
                "title": "Aurora Runtime Lite Map",
                "description": "Fast architecture and current-state orientation.",
                "mimeType": "text/markdown",
            },
            {
                "uri": "aurora://maps/runtime-deep",
                "name": "aurora-runtime-deep-map",
                "title": "Aurora Runtime Domain Map",
                "description": "Deeper subsystem ownership and interaction guidance.",
                "mimeType": "text/markdown",
            },
            {
                "uri": "aurora://roadmap/current",
                "name": "aurora-current-roadmap",
                "title": "Aurora Current Roadmap",
                "description": "Detailed roadmap order and dated validation ledger.",
                "mimeType": "text/markdown",
            },
            {
                "uri": "aurora://handoff/current",
                "name": "aurora-current-handoff",
                "title": "Aurora Current Handoff",
                "description": "Compact current status, next steps, and lane boundaries.",
                "mimeType": "text/markdown",
            },
        ]

    def prompt_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "aurora_map_first",
                "title": "Aurora Map-First Orientation",
                "description": "Orient from current Aurora maps and lane notes before searching source.",
                "arguments": [
                    {
                        "name": "focus",
                        "description": "Optional task or subsystem to orient toward.",
                        "required": False,
                    }
                ],
            },
            {
                "name": "aurora_operator_preflight",
                "title": "Aurora Operator Preflight",
                "description": "Inspect runtime truth before making an Aurora operational claim.",
                "arguments": [],
            },
        ]

    def _read_state_and_status(self) -> tuple[dict[str, Any], dict[str, Any]]:
        paths = control_plane_paths(self.root)
        state = read_json_file(paths["state"], {})
        if not isinstance(state, dict):
            state = {}
        return state, build_operator_status(self.root, state_snapshot=state)

    def _settings_snapshot(self, *, category: str = "", maturity: str = "") -> dict[str, Any]:
        state, status = self._read_state_and_status()
        state_status = status.get("state", {}) or {}
        snapshot = build_settings_snapshot(
            state,
            runtime_active=bool((status.get("runtime", {}) or {}).get("running", False)),
            state_age_seconds=state_status.get("age_seconds"),
            state_timestamp=str(state.get("timestamp") or ""),
            category=category,
            maturity=maturity,
        )
        snapshot["mcp_authority"] = {"settings_mutation": False}
        return snapshot

    def _tool_get_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return build_operator_status(self.root)

    def _tool_get_dashboard(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        event_limit = _bounded_int(
            arguments.get("event_limit"), default=8, minimum=0, maximum=50
        )
        return build_operator_dashboard(self.root, event_limit=event_limit)

    def _tool_search_commands(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        detail = arguments.get("detail", False)
        if not isinstance(detail, bool):
            raise ValueError("detail must be a boolean")
        limit = _bounded_int(arguments.get("limit"), default=20, minimum=1, maximum=100)
        query = str(arguments.get("query") or "").strip()
        category = str(arguments.get("category") or "").strip()
        rows = load_command_catalog(self.root)
        matches = filter_command_catalog(
            rows,
            query=query,
            category=category,
            limit=limit,
            detail=detail,
        )
        return {
            "schema_version": "aurora_mcp_command_search_v1",
            "read_only": True,
            "execution_enabled": False,
            "query": query,
            "category": category,
            "catalog_count": len(rows),
            "count": len(matches),
            "commands": matches,
        }

    def _tool_get_settings(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._settings_snapshot(
            category=str(arguments.get("category") or "").strip(),
            maturity=str(arguments.get("maturity") or "").strip(),
        )

    def _tool_describe_setting(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        key = str(arguments.get("key") or "").strip()
        if not key:
            raise ValueError("key is required.")
        state, status = self._read_state_and_status()
        state_status = status.get("state", {}) or {}
        runtime_active = bool((status.get("runtime", {}) or {}).get("running", False))
        return {
            "schema_version": "aurora_mcp_setting_description_v1",
            "mcp_authority": {"settings_mutation": False},
            "definition": describe_setting_definition(key, state=state),
            "readback": build_setting_readback(
                key,
                state,
                runtime_active=runtime_active,
                state_age_seconds=state_status.get("age_seconds"),
                state_timestamp=str(state.get("timestamp") or ""),
            ),
        }

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _tool_result({"error": "Tool arguments must be an object."}, is_error=True)
        handler = self._tools.get(name)
        if handler is None:
            return _tool_result({"error": f"Unknown Aurora read-only tool: {name}"}, is_error=True)
        try:
            return _tool_result(handler(arguments))
        except (OSError, RuntimeError, ValueError) as error:
            return _tool_result({"error": str(error), "tool": name}, is_error=True)

    def _capability_posture(self) -> dict[str, Any]:
        try:
            command_count = len(load_command_catalog(self.root))
            command_catalog_status = "available"
        except (OSError, RuntimeError, ValueError):
            command_count = 0
            command_catalog_status = "unavailable"
        registry = registry_summary()
        return {
            "schema_version": "aurora_mcp_capability_posture_v1",
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "root": str(self.root),
            "read_only": True,
            "tool_count": len(self.tool_definitions()),
            "resource_count": len(self.resource_definitions()),
            "prompt_count": len(self.prompt_definitions()),
            "command_catalog_status": command_catalog_status,
            "described_runtime_command_count": command_count,
            "typed_setting_count": int(registry.get("setting_count", 0) or 0),
            "authority": {
                "command_submission": False,
                "settings_mutation": False,
                "mutation_replay": False,
                "model_calls": False,
                "desktop_control": False,
                "external_app_control": False,
                "mcp_client_hosting": False,
            },
        }

    def _read_static_resource(self, relative_path: str) -> str:
        path = (self.root / relative_path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise McpRequestError(-32602, "Resource path escaped the Aurora root.") from error
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise McpRequestError(-32002, f"Aurora resource is unavailable: {relative_path}") from error
        max_chars = 300_000
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n[Resource truncated by Aurora read-only MCP.]\n"
        return text

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "aurora://mcp/capabilities":
            mime_type = "application/json"
            text = _json_text(self._capability_posture())
        elif uri == "aurora://operator/status":
            mime_type = "application/json"
            text = _json_text(build_operator_status(self.root))
        elif uri == "aurora://operator/dashboard":
            mime_type = "application/json"
            text = _json_text(build_operator_dashboard(self.root, event_limit=8))
        elif uri == "aurora://settings/current":
            mime_type = "application/json"
            text = _json_text(self._settings_snapshot())
        else:
            static_resources = {
                "aurora://maps/runtime-lite": "aurora_reference_maps/runtime/overview.md",
                "aurora://maps/runtime-deep": "aurora_reference_maps/runtime/runtime-domains.md",
                "aurora://roadmap/current": "docs/reference-packs/roadmap-reference.md",
                "aurora://handoff/current": "docs/notes/aurora_current_status.md",
            }
            relative_path = static_resources.get(uri)
            if relative_path is None:
                raise McpRequestError(-32602, f"Unknown Aurora resource URI: {uri}")
            mime_type = "text/markdown"
            text = self._read_static_resource(relative_path)
        return {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}

    def _get_prompt(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise McpRequestError(-32602, "Prompt arguments must be an object.")
        if name == "aurora_map_first":
            focus = str(arguments.get("focus") or "the current task").strip()
            text = (
                f"Orient to Aurora for {focus}. Read aurora://maps/runtime-lite first, then "
                "aurora://handoff/current for compact status and next steps. Read "
                "aurora://roadmap/current only for detailed planning or dated evidence. "
                "Use the function skeleton for callable lookup and the deep map only if "
                "the task crosses subsystems. Inspect status/dashboard before operational claims. "
                "Do not infer write authority from the searchable command catalog."
            )
        elif name == "aurora_operator_preflight":
            text = (
                "Run a read-only Aurora operator preflight. Call aurora_get_status and "
                "aurora_get_dashboard, check state freshness and monitor status, summarize any "
                "uncertain mutation admission without replaying it, and distinguish effective "
                "settings from stale or last-observed values."
            )
        else:
            raise McpRequestError(-32602, f"Unknown Aurora prompt: {name}")
        return {
            "description": next(
                row["description"] for row in self.prompt_definitions() if row["name"] == name
            ),
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }

    def _dispatch(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
            return {
                "protocolVersion": requested,
                "capabilities": self.capabilities(),
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": SERVER_TITLE,
                    "version": SERVER_VERSION,
                },
                "instructions": SERVER_INSTRUCTIONS,
            }
        if method == "server/discover":
            return {
                "resultType": "complete",
                "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capabilities": self.capabilities(),
                "ttlMs": 300_000,
                "cacheScope": "private",
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    }
                },
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
        request_id: Any,
        code: int,
        message: str,
        data: Any = None,
    ) -> dict[str, Any]:
        error = {"code": int(code), "message": str(message)}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def self_check(self) -> dict[str, Any]:
        posture = self._capability_posture()
        posture["root_exists"] = self.root.exists()
        posture["status_schema_version"] = build_operator_status(self.root).get(
            "schema_version", ""
        )
        posture["tool_names"] = [row["name"] for row in self.tool_definitions()]
        posture["resource_uris"] = [row["uri"] for row in self.resource_definitions()]
        return posture


def run_stdio(server: AuroraReadOnlyMcpServer, *, verbose: bool = False) -> int:
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
        encoded = json.dumps(response, ensure_ascii=True, separators=(",", ":"))
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()
        if verbose:
            method = message.get("method", "") if isinstance(message, dict) else ""
            print(f"aurora-mcp handled {method}", file=sys.stderr, flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only MCP facade for Aurora's control plane.")
    parser.add_argument(
        "--root",
        default=os.environ.get("AURORA_ROOT") or str(Path(__file__).resolve().parent),
        help="Aurora project/runtime root.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Print a read-only capability check and exit instead of serving stdio.",
    )
    parser.add_argument("--verbose", action="store_true", help="Write request names to stderr.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = AuroraReadOnlyMcpServer(args.root)
    if args.self_check:
        print(_json_text(server.self_check()))
        return 0
    return run_stdio(server, verbose=bool(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
