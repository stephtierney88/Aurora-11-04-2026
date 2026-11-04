import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from blender_readonly_mcp_server import (
    INVENTORY_MARKER,
    BlenderReadOnlyError,
    BlenderReadOnlyMcpServer,
    discover_blender_executable,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PROJECT_ROOT / "blender_readonly_mcp_server.py"
LAUNCHER_PATH = PROJECT_ROOT / "blender-readonly-mcp.cmd"


class BlenderReadOnlyMcpServerTests(unittest.TestCase):
    def make_server(self, temp_dir: str):
        root = Path(temp_dir) / "allowed"
        root.mkdir()
        blender = Path(temp_dir) / "blender.exe"
        blender.write_bytes(b"fake")
        inspector = Path(temp_dir) / "inventory.py"
        inspector.write_text("# fixture\n", encoding="utf-8")
        server = BlenderReadOnlyMcpServer(
            root,
            blender_executable=blender,
            allowed_roots=[root],
            inspector_script=inspector,
        )
        return server, root, blender, inspector

    def request(self, server, method, params=None, request_id=1):
        return server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )

    def test_explicit_blender_discovery_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "blender.exe"
            executable.write_bytes(b"fixture")
            self.assertEqual(discover_blender_executable(executable), executable.resolve())
            self.assertIsNone(discover_blender_executable(Path(temp_dir) / "missing.exe"))

    def test_tools_have_only_read_only_authority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _ = self.make_server(temp_dir)
            tools = self.request(server, "tools/list")["result"]["tools"]
            with mock.patch(
                "blender_readonly_mcp_server.subprocess.run",
                side_effect=OSError("The fixture is not an executable."),
            ):
                posture = server.capability_posture()

        self.assertEqual({row["name"] for row in tools}, {
            "blender_get_installation",
            "blender_inspect_scene_file",
        })
        self.assertTrue(all(row["annotations"]["readOnlyHint"] for row in tools))
        self.assertTrue(all(not row["annotations"]["destructiveHint"] for row in tools))
        self.assertNotIn("script", json.dumps(tools).lower().replace("description", ""))
        self.assertTrue(posture["security_boundary"]["transitive_linked_asset_reads_possible"])
        self.assertFalse(posture["security_boundary"]["operating_system_sandbox"])

    def test_scene_path_must_be_blend_file_inside_allowlist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, _, _ = self.make_server(temp_dir)
            allowed = root / "scene.blend"
            allowed.write_bytes(b"BLENDER")
            non_blend = root / "scene.py"
            non_blend.write_text("pass\n", encoding="utf-8")
            outside = Path(temp_dir) / "outside.blend"
            outside.write_bytes(b"BLENDER")

            self.assertEqual(server._validate_scene_path(allowed), allowed.resolve())
            with self.assertRaisesRegex(BlenderReadOnlyError, "Only existing .blend"):
                server._validate_scene_path(non_blend)
            with self.assertRaisesRegex(BlenderReadOnlyError, "outside the configured"):
                server._validate_scene_path(outside)

    def test_scene_size_limit_is_enforced_before_blender_launch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, _, _ = self.make_server(temp_dir)
            server.max_scene_bytes = 3
            scene = root / "large.blend"
            scene.write_bytes(b"1234")

            with self.assertRaisesRegex(BlenderReadOnlyError, "exceeds"):
                server.inspect_scene_file(scene)

    def test_inspection_uses_fixed_headless_arguments_and_parses_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, blender, inspector = self.make_server(temp_dir)
            scene = root / "semi;colon scene.blend"
            scene.write_bytes(b"BLENDER")
            payload = {
                "schema_version": "blender_readonly_scene_inventory_v1",
                "read_only": True,
                "counts": {"scenes": 1, "objects": 3},
            }
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Blender log\n" + INVENTORY_MARKER + json.dumps(payload) + "\nBlender quit\n",
                stderr="",
            )
            with mock.patch(
                "blender_readonly_mcp_server.subprocess.run", return_value=completed
            ) as run:
                result = server.inspect_scene_file(
                    scene, object_limit=12, timeout_seconds=30
                )

        command = run.call_args.args[0]
        self.assertEqual(command[0], str(blender))
        self.assertIn("--background", command)
        self.assertIn("--factory-startup", command)
        self.assertIn("--disable-autoexec", command)
        self.assertIn("--disable-depsgraph-on-file-load", command)
        self.assertNotIn("--python-expr", command)
        self.assertEqual(command.count(str(scene.resolve())), 1)
        self.assertEqual(command[command.index("--python") + 1], str(inspector))
        self.assertEqual(command[-2:], ["--object-limit", "12"])
        self.assertFalse(result["mcp_authority"]["scene_mutation"])
        self.assertEqual(result["source_file"]["path"], str(scene.resolve()))

    def test_missing_inventory_marker_is_a_tool_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, _, _ = self.make_server(temp_dir)
            scene = root / "scene.blend"
            scene.write_bytes(b"BLENDER")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Blender quit\n",
                stderr=r"Could not load C:\private\linked-asset.blend",
            )
            with mock.patch(
                "blender_readonly_mcp_server.subprocess.run", return_value=completed
            ):
                result = self.request(
                    server,
                    "tools/call",
                    {
                        "name": "blender_inspect_scene_file",
                        "arguments": {"path": str(scene)},
                    },
                )["result"]

        self.assertTrue(result["isError"])
        self.assertIn("valid read-only inventory", result["content"][0]["text"])
        self.assertIn("marker_found=False", result["content"][0]["text"])
        self.assertNotIn("linked-asset", result["content"][0]["text"])

    def test_resources_and_prompt_are_discoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, _, _, _ = self.make_server(temp_dir)
            resources = self.request(server, "resources/list")["result"]["resources"]
            prompts = self.request(server, "prompts/list")["result"]["prompts"]
            prompt = self.request(
                server,
                "prompts/get",
                {
                    "name": "blender_readonly_preflight",
                    "arguments": {"scene_path": "C:/allowed/test.blend"},
                },
            )["result"]

        self.assertEqual(len(resources), 2)
        self.assertEqual(len(prompts), 1)
        text = prompt["messages"][0]["content"]["text"]
        self.assertIn("C:/allowed/test.blend", text)
        self.assertIn("Do not save", text)

    def test_stdio_round_trip_and_notification_silence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server, root, blender, _ = self.make_server(temp_dir)
            del server
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SERVER_PATH),
                    "--root",
                    str(root),
                    "--blender",
                    str(blender),
                    "--allowed-root",
                    str(root),
                ],
                input="".join(json.dumps(row) + "\n" for row in messages),
                text=True,
                capture_output=True,
                timeout=10,
                check=True,
            )

        responses = [
            json.loads(line) for line in completed.stdout.splitlines() if line.strip()
        ]
        self.assertEqual([row["id"] for row in responses], [1, 2])
        self.assertEqual(len(responses[1]["result"]["tools"]), 2)
        self.assertEqual(completed.stderr, "")

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher regression")
    def test_windows_launcher_forwards_self_check(self):
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "call", str(LAUNCHER_PATH), "--self-check"],
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["server_name"], "blender-readonly")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["installation_found"])


if __name__ == "__main__":
    unittest.main()
