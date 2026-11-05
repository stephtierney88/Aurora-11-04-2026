import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import aurora_goal_store as goals
from aurora_command_contracts import validate_command_arguments, command_failure_stops_batch, describe_command_contract


class GoalStoreTests(unittest.TestCase):
    def test_panel_goals_show_real_ids_labels_and_status_without_object_repr(self):
        source = Path(__file__).resolve().parents[1] / "aurora2.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_trim_panel_goals")
        scope = {"Goal": goals.Goal, "GOAL_LOCK": goals.GOAL_LOCK,
                 "normalize_memory_item": lambda value: " ".join(str(value).split())}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), scope)
        goal = goals.Goal("Reach\n town", "High", "Critical", sub_goals=[goals.Goal("Leave home")])
        rows = scope["_trim_panel_goals"]([goal, "legacy text", goals.Goal("omitted")], limit=2)
        self.assertEqual(rows, [f"ID {goal.id}: Reach town | priority=High | significance=Critical | status=Incomplete | subgoals=1",
                                "legacy text"])
        goal.status = "Complete"
        self.assertIn("status=Complete", scope["_trim_panel_goals"]([goal])[0])
        self.assertEqual(len(goal.sub_goals), 1)

    def test_memory_commands_validate_before_dispatch_and_stop_failed_batches(self):
        for name in goals.MEMORY_COMMANDS:
            self.assertTrue(command_failure_stops_batch(name))
            self.assertEqual(describe_command_contract(name)["result"]["receipt_field"], "memory_command_results")
            if name != "TASKS":
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_command_arguments(name, [])

    def test_memory_validation_keeps_valid_legacy_forms_without_dropped_fields(self):
        for args in (["Reach town", "High", "Critical"], ["Reach town;High;Critical"]):
            self.assertEqual(goals.parse_memory_command_arguments("ADD_GOAL", args),
                             {"text": "Reach town", "priority": "High", "significance": "Critical"})
        # Empty labels keep their positions; free-form numeric/custom labels remain valid.
        self.assertEqual(goals.parse_memory_command_arguments("ADD_GOAL", ["town;;0.8"])["significance"], "0.8")
        self.assertEqual(goals.parse_memory_command_arguments("ADD_GOAL", ["town", "0.4", "custom"])["priority"], "0.4")
        for name, args in [("ADD_GOAL", [" "]), ("ADD_GOAL", ["x", "p", "s", "lost"]),
                           ("ADD_GOAL", ["x;p;s;lost"]), ("ADD_JOURNAL", ["x", "lost"]),
                           ("ADD_APRIORITY_GOAL", [""]), ("UPDATE_NOTES", ["x", "lost"]),
                           ("UPDATE_NOTES", ["bad\x00"]), ("COMPLETE_GOAL", ["0"]),
                           ("COMPLETE_GOAL", ["-1"]), ("COMPLETE_GOAL", ["1.2"]), ("TASKS", ["unused"])]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                validate_command_arguments(name, args)

    def test_horizon_compatibility_and_explicit_empty_list(self):
        for name in goals.HORIZON_COMMANDS:
            legacy = goals.parse_memory_command_arguments(name, ["first", "second"])
            flow = goals.parse_memory_command_arguments(name, ["first", "second"], assistant_policy="task_flow")
            self.assertEqual((legacy["text"], legacy["ignored_argument_count"]), ("first", 1))
            self.assertEqual((flow["text"], flow["ignored_argument_count"]), ("first, second", 0))
            self.assertEqual(goals.parse_memory_command_arguments(name, [""])["text"], "")
        self.assertEqual(goals.parse_memory_command_arguments("UPDATE_NOTES", [""])["text"], "")

    def tree(self):
        return [goals.Goal("Parent café", "High", "Critical", sub_goals=[
            goals.Goal("Child", status="Complete", sub_goals=[goals.Goal("Grandchild")]), goals.Goal("Sibling")])]

    def test_recursive_roundtrip_preserves_ids_labels_and_unicode(self):
        rows = goals.encode_goals(self.tree())
        for format in ("legacy", "versioned"):
            with self.subTest(format=format), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "tasks.json"
                receipt = goals.write_document(path, {"goals_list": rows, "notes": ["preserve"]}, format=format)
                state, digest, observed_format = goals.read_document(path)
                self.assertEqual(goals.encode_goals(goals.decode_goals(state["goals_list"])), rows)
                self.assertEqual(state["notes"], ["preserve"])
                self.assertEqual((digest, observed_format), (receipt["after_hash"], format))

    def test_new_ids_stay_unique_after_restoring_high_ids(self):
        row = {"id": 100000, "text": "saved", "sub_goals": []}
        normalized = goals.validate_document({"goals_list": [row]})
        goals.decode_goals(normalized["goals_list"])
        ids = [goals.Goal("new").id for _ in range(10)]
        self.assertEqual(len(set(ids)), 10)
        self.assertGreater(min(ids), 100000)

    def test_duplicate_nested_ids_rejected_without_changing_input(self):
        state = {"goals_list": [{"id": 1, "text": "parent", "sub_goals": [{"id": 1, "text": "child"}]}]}
        before = json.dumps(state)
        with self.assertRaisesRegex(ValueError, "unique"):
            goals.validate_document(state)
        self.assertEqual(json.dumps(state), before)

    def test_malformed_metadata_and_future_schema_rejected(self):
        for state in ({"goals_list": [], "notes": "bad"}, {"goals_list": [], "route_state": {"field_meta": []}},
                      {"schema_version": "future", "state": {"goals_list": []}}, {"notes": []},
                      {"goals_list": [], "future_field": "must not disappear"},
                      {"schema_version": goals.SCHEMA, "state": {"goals_list": []}, "future_field": True}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                goals.validate_document(state)

    def test_failed_replace_leaves_old_file_and_no_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            goals.write_document(path, {"goals_list": []})
            before = path.read_bytes()
            with patch.object(goals.os, "replace", side_effect=OSError("locked")), self.assertRaises(OSError):
                goals.write_document(path, {"goals_list": goals.encode_goals(self.tree())})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_cancel_before_replace_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            goals.write_document(path, {"goals_list": []})
            before = path.read_bytes()
            calls = []
            def cancel():
                calls.append(True)
                if len(calls) == 2:
                    raise RuntimeError("cancelled")
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                goals.write_document(path, {"goals_list": goals.encode_goals(self.tree())}, check_cancel=cancel)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_malformed_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text('{"goals_list":')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                goals.write_document(path, {"goals_list": []})
            self.assertEqual(path.read_bytes(), before)

    def test_duplicate_json_fields_and_oversized_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            path.write_text('{"goals_list":[],"goals_list":[]}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                goals.read_document(path)
            with patch.object(goals, "MAX_BYTES", 4), self.assertRaisesRegex(ValueError, "size"):
                goals.read_document(path)

    def test_cyclic_tree_is_rejected_before_file_write(self):
        parent = goals.Goal("Parent")
        parent.sub_goals.append(parent)
        with self.assertRaises(ValueError):
            goals.encode_goals([parent])

    def test_save_and_load_have_whole_batch_argument_validation(self):
        for name in ("SAVE_TASKS", "LOAD_TASKS"):
            validate_command_arguments(name, [])
            self.assertTrue(command_failure_stops_batch(name))
            for args in ([""], ["a", "b"], ["bad\x00path"]):
                with self.assertRaises(ValueError):
                    validate_command_arguments(name, args)


if __name__ == "__main__":
    unittest.main()
