from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SERVER_NAME = "blender-readonly"
SERVER_TITLE = "Blender Read-Only Scene Inspector"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
INVENTORY_MARKER = "AURORA_BLENDER_INVENTORY_JSON="
DEFAULT_MAX_SCENE_BYTES = 2 * 1024 * 1024 * 1024
SERVER_INSTRUCTIONS = (
    "This Blender server is strictly read-only. It may inspect only explicit existing .blend "
    "files beneath configured allowlisted roots. It launches Blender headless with factory "
    "settings and Python auto-execution disabled. It cannot save, render, import, export, run "
    "operators or caller-supplied Python, drive Blender's GUI, or control Aurora. The target "
    "path is allowlisted, but Blender may resolve linked dependencies named inside that file; "
    "this adapter is not an operating-system sandbox."
)


class BlenderReadOnlyError(ValueError):
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


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise BlenderReadOnlyError("Boolean values are not valid integer arguments.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise BlenderReadOnlyError("Expected an integer value.") from error
    return max(minimum, min(maximum, parsed))


def _version_key(path: Path) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(path.parent.name))
    return tuple(int(value) for value in numbers) or (0,)


def discover_blender_executable(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    if explicit:
        try:
            resolved = Path(explicit).expanduser().resolve(strict=True)
        except OSError:
            return None
        return resolved if resolved.is_file() else None

    candidates: list[Path] = []
    env_path = str(os.environ.get("BLENDER_EXECUTABLE") or "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    command = shutil.which("blender")
    if command:
        candidates.append(Path(command))
    if os.name == "nt":
        install_root = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
        blender_root = install_root / "Blender Foundation"
        if blender_root.exists():
            candidates.extend(
                sorted(
                    blender_root.glob("Blender */blender.exe"),
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


class BlenderReadOnlyMcpServer:
    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        blender_executable: str | os.PathLike[str] | None = None,
        allowed_roots: Sequence[str | os.PathLike[str]] | None = None,
        inspector_script: str | os.PathLike[str] | None = None,
        max_scene_bytes: int = DEFAULT_MAX_SCENE_BYTES,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.blender_executable = discover_blender_executable(blender_executable)
        self.inspector_script = Path(
            inspector_script or (Path(__file__).resolve().parent / "blender_scene_inventory.py")
        ).expanduser().resolve()
        configured_roots = list(allowed_roots or ())
        if not configured_roots:
            configured_roots.append(self.root)
            if self.blender_executable is not None:
                configured_roots.append(self.blender_executable.parent)
        roots = []
        for value in configured_roots:
            path = Path(value).expanduser().resolve()
            if path not in roots:
                roots.append(path)
        self.allowed_roots = tuple(roots)
        self.max_scene_bytes = max(1, int(max_scene_bytes))
        self._installation_cache: dict[str, Any] | None = None
        self._tools = {
            "blender_get_installation": self._tool_get_installation,
            "blender_inspect_scene_file": self._tool_inspect_scene_file,
        }

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
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
                "name": "blender_get_installation",
                "title": "Get Blender Installation",
                "description": (
                    "Read the discovered Blender executable, version/build summary, bundled "
                    "proof-scene candidate, allowlisted roots, and disabled authority posture."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "annotations": annotations,
            },
            {
                "name": "blender_inspect_scene_file",
                "title": "Inspect Blender Scene File",
                "description": (
                    "Open one explicit existing .blend file beneath an allowlisted root in "
                    "headless Blender and return a bounded read-only scene/object inventory."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute path, or path relative to the configured root, to an existing .blend file.",
                        },
                        "object_limit": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 500,
                            "default": 100,
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 180,
                            "default": 60,
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "annotations": annotations,
            },
        ]

    @staticmethod
    def resource_definitions() -> list[dict[str, Any]]:
        return [
            {
                "uri": "blender://capabilities",
                "name": "blender-readonly-capabilities",
                "title": "Blender Read-Only Capability Posture",
                "description": "Tool counts, allowlisted roots, and disabled authority lanes.",
                "mimeType": "application/json",
            },
            {
                "uri": "blender://installation",
                "name": "blender-installation",
                "title": "Blender Installation",
                "description": "Discovered local Blender executable and version/build summary.",
                "mimeType": "application/json",
            },
        ]

    @staticmethod
    def prompt_definitions() -> list[dict[str, Any]]:
        return [
            {
                "name": "blender_readonly_preflight",
                "title": "Blender Read-Only Preflight",
                "description": "Verify installation and inspect an explicit scene without mutation.",
                "arguments": [
                    {
                        "name": "scene_path",
                        "description": "Explicit allowlisted .blend path to inspect.",
                        "required": True,
                    }
                ],
            }
        ]

    @staticmethod
    def _authority_posture() -> dict[str, bool]:
        return {
            "scene_save": False,
            "scene_mutation": False,
            "render": False,
            "import": False,
            "export": False,
            "operators": False,
            "arbitrary_python": False,
            "gui_control": False,
            "aurora_control": False,
        }

    @staticmethod
    def _security_boundary() -> dict[str, bool]:
        return {
            "primary_scene_path_allowlisted": True,
            "symlink_target_revalidated": True,
            "transitive_linked_asset_reads_possible": True,
            "operating_system_sandbox": False,
        }

    def _subprocess_flags(self) -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0

    def _bundled_proof_scene(self) -> Path | None:
        if self.blender_executable is None:
            return None
        candidates = sorted(self.blender_executable.parent.glob("**/startup.blend"))
        for candidate in candidates:
            if "Sculpting" in candidate.parts:
                return candidate.resolve()
        return candidates[0].resolve() if candidates else None

    def installation_snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._installation_cache is not None and not refresh:
            return dict(self._installation_cache)
        executable = self.blender_executable
        output = ""
        version = ""
        return_code: int | None = None
        error = ""
        if executable is not None:
            try:
                completed = subprocess.run(
                    [str(executable), "--version"],
                    text=True,
                    capture_output=True,
                    timeout=20,
                    check=False,
                    creationflags=self._subprocess_flags(),
                )
                return_code = int(completed.returncode)
                output = str(completed.stdout or completed.stderr or "")
                version = output.splitlines()[0].strip() if output.splitlines() else ""
            except (OSError, subprocess.SubprocessError) as caught:
                error = str(caught)
        proof_scene = self._bundled_proof_scene()
        payload = {
            "schema_version": "blender_readonly_installation_v1",
            "read_only": True,
            "found": executable is not None,
            "executable": str(executable or ""),
            "version": version,
            "version_probe_return_code": return_code,
            "version_probe_error": error,
            "bundled_proof_scene": str(proof_scene or ""),
            "allowed_roots": [str(path) for path in self.allowed_roots],
            "inspector_script": str(self.inspector_script),
            "authority": self._authority_posture(),
            "launch_policy": {
                "background": True,
                "factory_startup": True,
                "python_autoexec_disabled": True,
                "dependency_graph_on_file_load": False,
                "arbitrary_arguments": False,
            },
            "security_boundary": self._security_boundary(),
        }
        self._installation_cache = dict(payload)
        return payload

    def capability_posture(self) -> dict[str, Any]:
        installation = self.installation_snapshot()
        return {
            "schema_version": "blender_readonly_capability_posture_v1",
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "read_only": True,
            "tool_count": len(self.tool_definitions()),
            "resource_count": len(self.resource_definitions()),
            "prompt_count": len(self.prompt_definitions()),
            "installation_found": bool(installation.get("found", False)),
            "blender_version": str(installation.get("version") or ""),
            "allowed_roots": [str(path) for path in self.allowed_roots],
            "max_scene_bytes": self.max_scene_bytes,
            "authority": self._authority_posture(),
            "security_boundary": self._security_boundary(),
        }

    def _validate_scene_path(self, value: Any) -> Path:
        raw = str(value or "").strip()
        if not raw:
            raise BlenderReadOnlyError("path is required.")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise BlenderReadOnlyError(f"Blender scene file is unavailable: {candidate}") from error
        if not resolved.is_file() or resolved.suffix.lower() != ".blend":
            raise BlenderReadOnlyError("Only existing .blend files may be inspected.")
        if not any(self._path_is_within(resolved, root) for root in self.allowed_roots):
            raise BlenderReadOnlyError(
                "Scene path is outside the configured Blender read-only roots."
            )
        size = resolved.stat().st_size
        if size > self.max_scene_bytes:
            raise BlenderReadOnlyError(
                f"Scene file exceeds the configured {self.max_scene_bytes}-byte limit."
            )
        return resolved

    @staticmethod
    def _path_is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def inspect_scene_file(
        self,
        path: Any,
        *,
        object_limit: Any = 100,
        timeout_seconds: Any = 60,
    ) -> dict[str, Any]:
        if self.blender_executable is None:
            raise BlenderReadOnlyError("Blender executable was not found.")
        if not self.inspector_script.is_file():
            raise BlenderReadOnlyError(
                f"Bundled Blender inventory script is unavailable: {self.inspector_script}"
            )
        scene_path = self._validate_scene_path(path)
        limit = _bounded_int(object_limit, default=100, minimum=0, maximum=500)
        timeout = _bounded_int(timeout_seconds, default=60, minimum=10, maximum=180)
        command = [
            str(self.blender_executable),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--disable-depsgraph-on-file-load",
            str(scene_path),
            "--python",
            str(self.inspector_script),
            "--",
            "--object-limit",
            str(limit),
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=self._subprocess_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise BlenderReadOnlyError(
                f"Blender read-only inspection exceeded {timeout} seconds."
            ) from error
        except OSError as error:
            raise BlenderReadOnlyError(f"Unable to launch Blender: {error}") from error
        elapsed = round(time.monotonic() - started, 3)
        marker_line = next(
            (
                line[len(INVENTORY_MARKER) :]
                for line in str(completed.stdout or "").splitlines()
                if line.startswith(INVENTORY_MARKER)
            ),
            "",
        )
        if completed.returncode != 0 or not marker_line:
            raise BlenderReadOnlyError(
                "Blender did not produce a valid read-only inventory "
                f"(return_code={completed.returncode}, marker_found={bool(marker_line)})."
            )
        try:
            inventory = json.loads(marker_line)
        except json.JSONDecodeError as error:
            raise BlenderReadOnlyError("Blender inventory JSON was invalid.") from error
        if not isinstance(inventory, dict):
            raise BlenderReadOnlyError("Blender inventory result was not an object.")
        stat = scene_path.stat()
        inventory["source_file"] = {
            "path": str(scene_path),
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }
        inventory["inspection"] = {
            "elapsed_seconds": elapsed,
            "object_limit": limit,
            "timeout_seconds": timeout,
            "return_code": int(completed.returncode),
            "background": True,
            "factory_startup": True,
            "python_autoexec_disabled": True,
            "dependency_graph_on_file_load": False,
        }
        inventory["security_boundary"] = self._security_boundary()
        inventory["mcp_authority"] = self._authority_posture()
        return inventory

    def _tool_get_installation(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self.installation_snapshot(refresh=True)

    def _tool_inspect_scene_file(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self.inspect_scene_file(
            arguments.get("path"),
            object_limit=arguments.get("object_limit", 100),
            timeout_seconds=arguments.get("timeout_seconds", 60),
        )

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _tool_result({"error": "Tool arguments must be an object."}, is_error=True)
        handler = self._tools.get(name)
        if handler is None:
            return _tool_result({"error": f"Unknown Blender read-only tool: {name}"}, is_error=True)
        try:
            return _tool_result(handler(arguments))
        except BlenderReadOnlyError as error:
            return _tool_result({"error": str(error), "tool": name}, is_error=True)

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "blender://capabilities":
            payload = self.capability_posture()
        elif uri == "blender://installation":
            payload = self.installation_snapshot(refresh=True)
        else:
            raise McpRequestError(-32602, f"Unknown Blender resource URI: {uri}")
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
        arguments = params.get("arguments", {})
        if name != "blender_readonly_preflight":
            raise McpRequestError(-32602, f"Unknown Blender prompt: {name}")
        if not isinstance(arguments, Mapping):
            raise McpRequestError(-32602, "Prompt arguments must be an object.")
        scene_path = str(arguments.get("scene_path") or "").strip()
        if not scene_path:
            raise McpRequestError(-32602, "scene_path is required.")
        text = (
            "Run a read-only Blender preflight. Call blender_get_installation, verify the "
            "installation and allowlisted roots, then call blender_inspect_scene_file for "
            f"this explicit path: {scene_path}. Report scene/object/asset counts and any "
            "missing external-asset count. Do not save, render, import, export, run operators, "
            "or control the Blender GUI."
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
        payload["inspector_exists"] = self.inspector_script.is_file()
        payload["tool_names"] = [row["name"] for row in self.tool_definitions()]
        payload["resource_uris"] = [row["uri"] for row in self.resource_definitions()]
        return payload


def run_stdio(server: BlenderReadOnlyMcpServer, *, verbose: bool = False) -> int:
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
            print(f"blender-readonly-mcp handled {method}", file=sys.stderr, flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only MCP facade for Blender scene files.")
    parser.add_argument(
        "--root",
        default=os.environ.get("AURORA_ROOT") or str(Path(__file__).resolve().parent),
        help="Base path for relative scene paths and the default allowlist root.",
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get("BLENDER_EXECUTABLE") or "",
        help="Optional explicit Blender executable.",
    )
    parser.add_argument(
        "--allowed-root",
        action="append",
        default=[],
        help="Repeatable root beneath which .blend files may be inspected.",
    )
    parser.add_argument("--max-scene-bytes", type=int, default=DEFAULT_MAX_SCENE_BYTES)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--inspect", default="", help="Inspect one .blend file and exit.")
    parser.add_argument("--object-limit", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = BlenderReadOnlyMcpServer(
        args.root,
        blender_executable=args.blender or None,
        allowed_roots=args.allowed_root or None,
        max_scene_bytes=args.max_scene_bytes,
    )
    if args.self_check:
        print(_json_text(server.self_check()))
        return 0
    if args.inspect:
        try:
            payload = server.inspect_scene_file(
                args.inspect,
                object_limit=args.object_limit,
                timeout_seconds=args.timeout_seconds,
            )
        except BlenderReadOnlyError as error:
            print(_json_text({"error": str(error)}), file=sys.stderr)
            return 2
        print(_json_text(payload))
        return 0
    return run_stdio(server, verbose=bool(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
