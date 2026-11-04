import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aurora_mcp_server import AuroraReadOnlyMcpServer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PROJECT_ROOT / "aurora_mcp_server.py"
LAUNCHER_PATH = PROJECT_ROOT / "aurora-mcp.cmd"


class AuroraReadOnlyMcpServerTests(unittest.TestCase):
    def make_root(self, temp_dir: str) -> Path:
        root = Path(temp_dir)
        command_dir = root / "aurora_reference_maps" / "commands"
        command_dir.mkdir(parents=True)
        (command_dir / "commands-index.tsv").write_text(
            "command\tsignature\tcategory\thandler\tsummary\n"
            "SHOW_RUNTIME\tSHOW_RUNTIME()\tinspection\thandle_show_runtime\tShow runtime state.\n"
            "SET_LIVE\tSET_LIVE(enabled)\tmode\thandle_set_live\tSet live mode.\n",
            encoding="utf-8",
        )
        (root / "aurora_control_panel_state.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-12 12:00:00",
                    "session_id": "mcp-test",
                    "modes": {"live": False, "execution": "safe"},
                    "scheduler": {"profile": "balanced", "mode": "hybrid"},
                    "monitors": {"overall_status": "ok"},
                    "queue_bridge": {"pending_count": 0},
                    "mutation_admission": {
                        "uncertain_count": 0,
                        "no_automatic_replay": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        map_dir = root / "aurora_reference_maps" / "runtime"
        map_dir.mkdir(parents=True)
        (map_dir / "overview.md").write_text("# Lite map\n", encoding="utf-8")
        (map_dir / "runtime-domains.md").write_text("# Deep map\n", encoding="utf-8")
        pack_dir = root / "docs" / "reference-packs"
        pack_dir.mkdir(parents=True)
        (pack_dir / "roadmap-reference.md").write_text("# Roadmap\n", encoding="utf-8")
        notes_dir = root / "docs" / "notes"
        notes_dir.mkdir(parents=True)
        (notes_dir / "aurora_current_status.md").write_text(
            "# Current status\nNext: a bounded observation proof.\n", encoding="utf-8"
        )
        (notes_dir / "aurora_next_thread_handoff.md").write_text(
            "# Historical handoff\nOld activation is pending.\n", encoding="utf-8"
        )
        return root

    def request(self, server, method, params=None, request_id=1):
        return server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )

    def test_initialize_declares_read_only_instructions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = AuroraReadOnlyMcpServer(self.make_root(temp_dir))
            response = self.request(
                server,
                "initialize",
                {"protocolVersion": "2025-11-25", "capabilities": {}},
            )

        result = response["result"]
        self.assertEqual(result["serverInfo"]["name"], "aurora-readonly")
        self.assertIn("read-only", result["instructions"].lower())
        self.assertIn("tools", result["capabilities"])

    def test_tools_are_annotated_read_only_and_have_no_write_surface(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = AuroraReadOnlyMcpServer(self.make_root(temp_dir))
            tools = self.request(server, "tools/list")["result"]["tools"]

        self.assertEqual(len(tools), 5)
        self.assertTrue(all(row["annotations"]["readOnlyHint"] for row in tools))
        self.assertTrue(all(not row["annotations"]["destructiveHint"] for row in tools))
        names = {row["name"] for row in tools}
        write_tokens = ("submit", "apply", "set_")
        self.assertFalse(any(token in name for name in names for token in write_tokens))

    def test_tool_calls_read_status_catalog_and_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = AuroraReadOnlyMcpServer(self.make_root(temp_dir))

            status = self.request(
                server, "tools/call", {"name": "aurora_get_status", "arguments": {}}
            )["result"]
            commands = self.request(
                server,
                "tools/call",
                {
                    "name": "aurora_search_commands",
                    "arguments": {"query": "runtime", "limit": 10},
                },
            )["result"]
            settings = self.request(
                server, "tools/call", {"name": "aurora_get_settings", "arguments": {}}
            )["result"]

        self.assertFalse(status["isError"])
        self.assertEqual(
            status["structuredContent"]["schema_version"], "aurora_operator_status_v1"
        )
        self.assertFalse(commands["structuredContent"]["execution_enabled"])
        self.assertEqual(
            commands["structuredContent"]["commands"][0]["command"], "SHOW_RUNTIME"
        )
        self.assertEqual(settings["structuredContent"]["count"], 24)
        self.assertFalse(
            settings["structuredContent"]["mcp_authority"]["settings_mutation"]
        )

    def test_resources_and_prompts_are_discoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = AuroraReadOnlyMcpServer(self.make_root(temp_dir))
            resources = self.request(server, "resources/list")["result"]["resources"]
            lite = self.request(
                server, "resources/read", {"uri": "aurora://maps/runtime-lite"}
            )["result"]
            prompts = self.request(server, "prompts/list")["result"]["prompts"]
            prompt = self.request(
                server,
                "prompts/get",
                {"name": "aurora_map_first", "arguments": {"focus": "scheduler work"}},
            )["result"]
            unknown = self.request(
                server, "resources/read", {"uri": "aurora://unknown"}, request_id=9
            )

        self.assertEqual(len(resources), 8)
        self.assertEqual(lite["contents"][0]["text"], "# Lite map\n")
        self.assertEqual(len(prompts), 2)
        self.assertIn("scheduler work", prompt["messages"][0]["content"]["text"])
        self.assertEqual(unknown["error"]["code"], -32602)

    def test_current_handoff_uses_compact_status_without_historical_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self.make_root(temp_dir)
            server = AuroraReadOnlyMcpServer(root)
            handoff = self.request(
                server, "resources/read", {"uri": "aurora://handoff/current"}
            )["result"]
            prompt = self.request(
                server, "prompts/get", {"name": "aurora_map_first"}
            )["result"]["messages"][0]["content"]["text"]
            (root / "docs" / "notes" / "aurora_current_status.md").unlink()
            missing = self.request(
                server, "resources/read", {"uri": "aurora://handoff/current"}
            )

        self.assertEqual(
            handoff["contents"][0]["text"],
            "# Current status\nNext: a bounded observation proof.\n",
        )
        self.assertIn("aurora://roadmap/current only", prompt)
        self.assertIn("function skeleton", prompt)
        self.assertIn("error", missing)

    def test_stdio_round_trip_and_notification_silence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self.make_root(temp_dir)
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
                [sys.executable, str(SERVER_PATH), "--root", str(root)],
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
        self.assertEqual(len(responses[1]["result"]["tools"]), 5)
        self.assertEqual(completed.stderr, "")

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher regression")
    def test_windows_launcher_forwards_self_check_after_root(self):
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "call", str(LAUNCHER_PATH), "--self-check"],
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["server_name"], "aurora-readonly")
        self.assertTrue(payload["read_only"])


if __name__ == "__main__":
    unittest.main()
