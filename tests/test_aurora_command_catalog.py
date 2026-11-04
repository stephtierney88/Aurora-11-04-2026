import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aurora_command_catalog import build_command_catalog, parse_dispatch
from aurora_cli import _shell_cli_argv, filter_command_catalog, load_command_catalog, main
from aurora_mcp_server import AuroraReadOnlyMcpServer
from aurora_command_contracts import REGISTERED_SETTING_COMMANDS

ROOT = Path(__file__).resolve().parents[1]


class CommandCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_command_catalog(ROOT)

    def test_all_runtime_and_desktop_bindings_are_callable_and_unique(self):
        rows = self.catalog["commands"]
        tree = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
        runtime = parse_dispatch(tree, "command_dispatch")
        desktop = parse_dispatch(tree, "pyautogui_dispatch")
        self.assertEqual({row["command"] for row in rows}, set(runtime) | {"pyag:" + name for name in desktop})
        self.assertEqual(len(rows), len({row["command"].upper() for row in rows}))
        self.assertTrue(all(name == name.upper() for name in runtime))
        self.assertTrue(all(row["callable"] for row in rows))
        self.assertIn("TASKS", runtime)
        self.assertNotIn("GB", runtime)
        self.assertNotIn("PYAG", runtime)

    def test_alias_and_validation_coverage_are_explicit(self):
        rows = {row["command"]: row for row in self.catalog["commands"]}
        self.assertIn("pyag:leftclick", rows["pyag:click"]["aliases"])
        self.assertEqual(rows["WAIT"]["contract"]["parameter_validation"], "pre_dispatch")
        self.assertEqual(rows["SHOW_RUNTIME"]["contract"]["parameter_validation"], "legacy_handler")
        self.assertIsNone(rows["SHOW_RUNTIME"]["contract"]["parameters"])
        desktop = [row for row in rows.values() if row["binding_kind"] == "desktop"]
        self.assertEqual(len(desktop), 19)
        self.assertTrue(all(row["contract"]["parameter_validation"] == "pre_dispatch" for row in desktop))
        self.assertTrue(all(row["signature_source"] == "reviewed_contract" for row in desktop))
        self.assertEqual(rows["pyag:press"]["contract"]["parameters"][1]["minimum"], 1)
        self.assertEqual(rows["pyag:click"]["contract"], rows["pyag:leftclick"]["contract"])

    def test_duplicate_bindings_fail_generation_instead_of_shadowing(self):
        tree = ast.parse("command_dispatch = {'A': first, 'A': second}")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_dispatch(tree, "command_dispatch")

    def test_setting_contracts_and_reasoning_alias_share_registry_metadata(self):
        rows = {row["command"]: row for row in self.catalog["commands"]}
        for name, definition in REGISTERED_SETTING_COMMANDS.items():
            contract = rows[name]["contract"]
            self.assertEqual(contract["parameter_validation"], "pre_dispatch")
            self.assertEqual(contract["setting_key"], definition.key)
            self.assertEqual(contract["lock_key"], definition.lock_key)
            self.assertEqual(contract["parameters"][0]["omitted"], "read_current_value")
            self.assertEqual(contract["result"]["receipt_field"], "setting_results")
        self.assertIn("SET_REASONING_EFFORT", rows["SET_SESSION_REASONING_EFFORT"]["aliases"])
        self.assertIn("SET_SESSION_REASONING_EFFORT", rows["SET_REASONING_EFFORT"]["aliases"])
        self.assertEqual(sum(row["contract"]["parameter_validation"] == "pre_dispatch" for row in rows.values()), 98)

    def test_history_contract_changes_invalidate_published_catalog(self):
        with tempfile.TemporaryDirectory(prefix="aurora-history-catalog-") as folder:
            root = Path(folder)
            path = root / "aurora_reference_maps/commands/commands.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.catalog), encoding="utf-8")
            authority = root / "aurora_history_controls.py"
            authority.write_bytes((ROOT / authority.name).read_bytes())
            self.assertEqual(len(load_command_catalog(root)), 360)
            with authority.open("a", encoding="utf-8") as handle:
                handle.write("\n# changed history contract\n")
            with self.assertRaisesRegex(ValueError, "stale"):
                load_command_catalog(root)

    def test_registry_changes_invalidate_published_contracts(self):
        with tempfile.TemporaryDirectory(prefix="aurora-registry-catalog-") as folder:
            root = Path(folder)
            path = root / "aurora_reference_maps/commands/commands.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.catalog), encoding="utf-8")
            registry = root / "aurora_settings_registry.py"
            registry.write_bytes((ROOT / registry.name).read_bytes())
            self.assertEqual(len(load_command_catalog(root)), 360)
            with registry.open("a", encoding="utf-8") as handle:
                handle.write("\n# changed validation authority\n")
            with self.assertRaisesRegex(ValueError, "stale"):
                load_command_catalog(root)

    def test_transaction_validation_changes_invalidate_published_contracts(self):
        with tempfile.TemporaryDirectory(prefix="aurora-transaction-catalog-") as folder:
            root = Path(folder)
            path = root / "aurora_reference_maps/commands/commands.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.catalog), encoding="utf-8")
            authority = root / "aurora_settings_transactions.py"
            authority.write_bytes((ROOT / authority.name).read_bytes())
            self.assertEqual(len(load_command_catalog(root)), 360)
            with authority.open("a", encoding="utf-8") as handle:
                handle.write("\n# changed transaction validator\n")
            with self.assertRaisesRegex(ValueError, "stale"):
                load_command_catalog(root)

    def test_cli_and_mcp_share_compact_and_detailed_catalog(self):
        with tempfile.TemporaryDirectory(prefix="aurora-catalog-") as folder:
            root = Path(folder)
            path = root / "aurora_reference_maps/commands/commands.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.catalog), encoding="utf-8")
            rows = load_command_catalog(root)
            compact = filter_command_catalog(rows, query="WAIT", limit=1)
            self.assertEqual(compact[0]["command"], "WAIT")
            self.assertNotIn("contract", compact[0])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--root", str(root), "commands", "WAIT", "--detail", "--json"])
            self.assertEqual(code, 0)
            detail = json.loads(output.getvalue())["commands"]
            wait = next(row for row in detail if row["command"] == "WAIT")
            self.assertTrue(wait["contract"]["parameters"][0]["finite"])
            server = AuroraReadOnlyMcpServer(root)
            mcp = server._tool_search_commands({"query": "WAIT", "detail": True})
            self.assertIn(wait, mcp["commands"])
            self.assertFalse(mcp["execution_enabled"])
            with self.assertRaisesRegex(ValueError, "boolean"):
                server._tool_search_commands({"detail": "false"})
            (root / "aurora2.py").write_text("# changed checkout\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                load_command_catalog(root)

    def test_explicit_desktop_and_game_namespace_route_to_bridge(self):
        rows = self.catalog["commands"]
        for command in ('pyag:press("a")', 'PYAG:CLICK(1, 2)', 'GB:press(a)', 'tasks()'):
            self.assertEqual(_shell_cli_argv(command, rows), ["command", command])


if __name__ == "__main__":
    unittest.main()
