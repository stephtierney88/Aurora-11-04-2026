import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aurora_cli import (
    _shell_cli_argv,
    append_shell_history,
    clear_shell_history,
    complete_shell_line,
    execute_shell_line,
    filter_command_catalog,
    load_command_catalog,
    main,
    read_shell_history,
    shell_history_is_sensitive,
)
from aurora_control_plane import append_bridge_request, append_jsonl_record, control_plane_paths


COMMAND_INDEX = """command\tsignature\tcategory\thandler\tsummary
SHOW_RUNTIME\tSHOW_RUNTIME()\tStatus Commands\tshow_runtime\tDisplay runtime status.
SET_LIVE\tSET_LIVE(on|off)\tRuntime Commands\tset_live\tChange live mode.
GB\tGB\tAction Commands\t\tExecute emulator commands.
"""


class AuroraCliShellTests(unittest.TestCase):
    def _root(self, temp_dir: str) -> Path:
        root = Path(temp_dir)
        index = control_plane_paths(root)["command_index"]
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(COMMAND_INDEX, encoding="utf-8")
        return root

    def test_command_catalog_loads_and_filters_offline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            rows = load_command_catalog(root)

            self.assertEqual([row["command"] for row in rows], ["SHOW_RUNTIME", "SET_LIVE", "GB"])
            filtered = filter_command_catalog(rows, query="live", limit=10)
            self.assertEqual([row["command"] for row in filtered], ["SET_LIVE"])

    def test_completion_covers_runtime_commands_settings_and_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            catalog = load_command_catalog(root)

            runtime = complete_shell_line("sho", root=root, catalog=catalog)
            setting = complete_shell_line("settings get model.", root=root, catalog=catalog)
            value = complete_shell_line("settings apply live=o", root=root, catalog=catalog)
            dashboard = complete_shell_line("dashboard --", root=root, catalog=catalog)

            self.assertIn("SHOW_RUNTIME()", runtime["candidates"])
            self.assertIn("model.text", setting["candidates"])
            self.assertEqual(value["candidates"], ["live=off", "live=on"])
            self.assertEqual(value["replace_start"], len("settings apply "))
            self.assertIn("--watch", dashboard["candidates"])
            self.assertIn("--events", dashboard["candidates"])

    def test_shell_raw_command_preserves_quotes_and_direct_command_form(self):
        catalog = [
            {
                "command": "SHOW_RUNTIME",
                "signature": "SHOW_RUNTIME()",
                "category": "Status Commands",
                "handler": "show_runtime",
                "summary": "Display runtime status.",
            }
        ]

        self.assertEqual(
            _shell_cli_argv('command SET_NOTE("hello world")', catalog),
            ["command", 'SET_NOTE("hello world")'],
        )
        self.assertEqual(
            _shell_cli_argv("SHOW_RUNTIME()", catalog),
            ["command", "SHOW_RUNTIME()"],
        )
        self.assertEqual(_shell_cli_argv("status", catalog), ["status"])
        self.assertEqual(_shell_cli_argv("dashboard", catalog), ["dashboard"])
        self.assertEqual(_shell_cli_argv("dir", catalog), ["dir"])

    def test_dashboard_command_emits_shared_json_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            control_plane_paths(root)["state"].write_text(
                json.dumps(
                    {
                        "timestamp": "2026-08-08 12:00:00",
                        "session_id": "cli-dashboard-test",
                        "modes": {"auth": "api_key", "live": False},
                        "monitors": {"overall_status": "ok"},
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    ["--root", str(root), "dashboard", "--events", "0", "--json"]
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], "aurora_operator_dashboard_v1")
            self.assertEqual(payload["events"]["count"], 0)
            self.assertEqual(payload["settings"]["count"], 39)

    def test_direct_runtime_command_routes_through_stopped_control_plane(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = execute_shell_line("SHOW_RUNTIME()", root=root)

            self.assertEqual(exit_code, 0)
            inbox = control_plane_paths(root)["inbox"]
            record = json.loads(inbox.read_text(encoding="utf-8"))
            self.assertEqual(record["text"], "SHOW_RUNTIME()")
            self.assertEqual(record["metadata"]["surface"], "cli")
            self.assertIn("runtime is not active", output.getvalue())

    def test_history_persists_safe_lines_and_refuses_sensitive_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)

            self.assertTrue(append_shell_history(root, "status", 0))
            self.assertFalse(
                append_shell_history(root, "SET_OPERATOR_PASSCODE(super-secret)", 0)
            )
            self.assertTrue(shell_history_is_sensitive("api_key=secret-value"))
            self.assertTrue(shell_history_is_sensitive("session_token=opaque-value"))
            self.assertFalse(shell_history_is_sensitive("LOGIN_CODEX_OAUTH()"))
            rows = read_shell_history(root, limit=10)

            self.assertEqual([row["command"] for row in rows], ["status"])
            clear_shell_history(root)
            self.assertEqual(read_shell_history(root, limit=10), [])

    def test_history_clear_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)
            append_shell_history(root, "status", 0)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                refused = main(["--root", str(root), "history", "clear"])
            with contextlib.redirect_stdout(io.StringIO()):
                cleared = main(["--root", str(root), "history", "clear", "--yes"])

            self.assertEqual(refused, 2)
            self.assertIn("Refusing to clear", stderr.getvalue())
            self.assertEqual(cleared, 0)
            self.assertEqual(read_shell_history(root), [])

    def test_command_wait_does_not_accept_another_clients_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root(temp_dir)

            def submit_with_results(*args, **kwargs):
                record = append_bridge_request(*args, **kwargs)
                for client, status in (("other_client", "failed"), (record["client_id"], "processed")):
                    append_jsonl_record(control_plane_paths(root)["command_log"], {
                        "event": "command_result", "client_id": client,
                        "request_id": record["request_id"], "status": status,
                    })
                return record

            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch(
                "aurora_cli.append_bridge_request", side_effect=submit_with_results,
            ), patch("aurora_cli.build_operator_status", return_value={"runtime": {"running": True}}):
                exit_code = main([
                    "--root", str(root), "command", "SHOW_RUNTIME()",
                    "--request-id", "shared-id", "--json",
                ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["client_id"], "aurora_cli")

    def test_receipts_command_filters_by_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for client in ("other_client", "aurora_cli"):
                append_jsonl_record(control_plane_paths(temp_dir)["command_log"], {
                    "event": "command_result", "client_id": client,
                    "request_id": "shared-id", "status": "processed",
                })
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([
                    "--root", temp_dir, "receipts", "--request-id", "shared-id",
                    "--client-id", "aurora_cli", "--json",
                ])
            self.assertEqual(exit_code, 0)
            self.assertEqual([row["client_id"] for row in json.loads(output.getvalue())], ["aurora_cli"])


if __name__ == "__main__":
    unittest.main()
