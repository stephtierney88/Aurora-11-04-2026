"""History selection and real runtime handlers without native or provider I/O."""
import ast
import copy
import datetime
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aurora_history_controls as history
import test_aurora_command_ingress as ingress
from aurora_command_contracts import describe_command_contract
from aurora_runtime_work import WorkCancelled


def row(text, exemption="None", timestamp="2026-10-01 01:00:00"):
    return {"timestamp": timestamp, "role": "user", "Exemption": exemption,
            "content": {"type": "text", "text": text}}


class HistoryPlanTests(unittest.TestCase):
    def plan(self, rows, command, args):
        return history.plan_history_change(rows, history.parse_history_arguments(command, args))

    def test_percentage_boundaries_and_exact_decimal_counts(self):
        rows = [row(str(i)) for i in range(10)]
        for percentage, count in [("0", 10), ("100", 0), ("90", 1), ("70", 3), ("50", 5)]:
            with self.subTest(percentage=percentage):
                result, counts = self.plan(rows, "CLEAR%", [percentage])
                self.assertEqual(len(result), count)
                self.assertEqual(counts["removed_count"], 10 - count)

    def test_total_budget_prioritizes_protected_without_negative_zero_slice(self):
        rows = [row("old"), row("pin", "Pinned"), row("new")]
        self.assertEqual(self.plan(rows, "CLEAR%", ["66"])[0], [rows[1]])
        self.assertEqual(self.plan(rows, "CLEAR%", ["100"])[0], [])
        self.assertEqual(self.plan(rows, "CLEAR%", ["0"])[0], rows)

    def test_no_pin_clear_preserves_typed_and_timestamped_legacy_entries_once(self):
        rows = [row("ordinary"), row("pin", "Pinned"), row("init", "Init"), row("handoff", "Handoff"),
                row("[2026-10-01 00:00:00] Exemption: legacy"),
                {"content": "Pinned Init summary: old format"}]
        result, counts = self.plan(rows, "CLEAR_NOPIN%", ["100"])
        self.assertEqual(result, rows[1:])
        self.assertEqual(counts["removed_count"], 1)
        self.assertEqual(self.plan(result, "CLEAR_NOPIN%", ["100"])[0], result)

    def test_equal_valued_duplicates_are_selected_by_position(self):
        rows = [row("same"), row("same"), row("pin", "Pinned")]
        with patch.object(history.random, "sample", return_value=[0]):
            # Supply sampler explicitly: the default function is bound at import.
            result, counts = history.plan_history_change(rows, history.parse_history_arguments("CLEAR_NOPIN%", ["50"]), sample=history.random.sample)
        self.assertEqual(result, rows[1:])
        self.assertEqual(counts["removed_count"], 1)

    def test_random_default_and_optional_deterministic_selection(self):
        rows = [row(str(i)) for i in range(4)]
        self.assertEqual(history.parse_history_arguments("CLEAR_NOPIN%", ["50"])["selection"], "random")
        self.assertEqual(self.plan(rows, "CLEAR_NOPIN%", ["50", "oldest"])[0], rows[2:])
        self.assertEqual(self.plan(rows, "CLEAR_NOPIN%", ["50", "newest"])[0], rows[:2])
        self.assertEqual(self.plan(rows, "CLEAR_NOPIN%", ["0", "newest"])[0], rows)

    def test_invalid_arguments_have_no_implicit_field_drops(self):
        cases = [("INIT", []), ("PIN", [""]), ("CLEAR%", ["nan"]), ("CLEAR%", ["inf"]),
                 ("CLEAR%", ["-1"]), ("CLEAR%", ["101"]), ("CLEAR%", ["50", "unused"]),
                 ("CLEAR_NOPIN%", ["50", "typo"]), ("CLEAR_NOPIN%", []), ("CLEAR", ["extra"]),
                 ("EDIT_MSGS", ["t", "a", "t2"]), ("DELETE_MSG", ["t", "extra"]),
                 ("SAVECH", ["prefix", "extra"]), ("SAVECH", [""]), ("DHISTORY", ["extra"])]
        for name, args in cases:
            with self.subTest(command=name, args=args), self.assertRaises(ValueError):
                history.parse_history_arguments(name, args)

    def test_edit_validates_every_target_and_preserves_input(self):
        rows = [row("old")]
        before = copy.deepcopy(rows)
        with self.assertRaises(ValueError):
            self.plan(rows, "EDIT_MSGS", [rows[0]["timestamp"], "new", "missing", "oops"])
        self.assertEqual(rows, before)

    def test_edit_first_timestamp_match_and_delete_all_matches(self):
        rows = [row("one"), row("two"), {"content": "legacy without timestamp"}]
        edited, counts = self.plan(rows, "EDIT_MSGS", [rows[0]["timestamp"], ""])
        self.assertEqual(edited[0]["content"]["text"], "")
        self.assertEqual(edited[1], rows[1])
        self.assertEqual(counts["edited_count"], 1)
        deleted, counts = self.plan(rows, "DELETE_MSG", [rows[0]["timestamp"]])
        self.assertEqual(deleted, rows[2:])
        self.assertEqual(counts["removed_count"], 2)

    def test_legacy_init_and_handoff_classification_respects_explicit_types(self):
        self.assertEqual(history.history_exemption({"content": "Pinned Handoff context: x"}), "Handoff")
        self.assertEqual(history.history_exemption(row("Exemption: x", "Special")), "Special")
        self.assertEqual(history.history_exemption(row("unrelated", "Image")), "Image")

    def test_all_thirteen_bindings_have_reviewed_contracts(self):
        self.assertEqual(len(history.HISTORY_COMMANDS), 13)
        for name in history.HISTORY_COMMANDS:
            self.assertEqual(describe_command_contract(name)["result"]["receipt_field"], "history_command_results")


class HistoryExportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="aurora-history-export-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.prefix = str(self.directory / "chat")

    def test_legacy_strings_images_and_same_second_exports(self):
        entries = [{"content": "legacy"}, row("text"), {"content": {"type": "image", "data": "abcdef" * 20}}]
        fixed = datetime.datetime(2026, 10, 1)
        first = history.save_history_export(entries, self.prefix, now=fixed)
        second = history.save_history_export(entries, self.prefix, now=fixed)
        self.assertTrue(first["success"])
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(Path(first["path"]).read_bytes(), Path(second["path"]).read_bytes())
        self.assertIn("Message: legacy", Path(first["path"]).read_text())
        self.assertIn("[truncated]", Path(first["path"]).read_text())
        self.assertEqual(first["sha256"], second["sha256"])

    def test_flush_failure_removes_only_new_file(self):
        first = history.save_history_export([row("keep")], self.prefix)
        original = Path(first["path"]).read_bytes()
        with patch.object(history.os, "fsync", side_effect=OSError("fixture disk full")):
            failed = history.save_history_export([row("failed")], self.prefix)
        self.assertFalse(failed["success"])
        self.assertTrue(failed["partial_file_removed"])
        self.assertEqual(Path(first["path"]).read_bytes(), original)
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_readback_mismatch_reports_uncertainty(self):
        with patch.object(Path, "read_bytes", return_value=b"different"):
            result = history.save_history_export([row("x")], self.prefix)
        self.assertFalse(result["success"])
        self.assertEqual(result["effect_status"], "uncertain")
        self.assertTrue(Path(result["path"]).exists())


class HistoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ingress.RuntimeIngressTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope = s = self.fixture.scope
        self.store = []
        self.invalidations = []
        self.provider_state = {"previous_response_id": "", "status": "idle"}
        s.update({name: getattr(history, name) for name in ["HISTORY_RESULT_SCHEMA", "parse_history_arguments", "history_exemption",
                                                         "history_text", "history_summary", "plan_history_change", "save_history_export"]})
        s.update(copy=copy, HISTORY_LOCK=threading.RLock(), enable_important_messages=True, ADD_IMSGS_TO_HISTORY=True,
                 enable_unimportant_messages=True, ADD_UMSGS_TO_HISTORY=True,
                 CHECK_UMSGS_DECAY=True, CHECK_IMSGS_DECAY=True, UMSGS_DECAY=100000, IMGS_DECAY=100000,
                 RESPONSES_REASONING=SimpleNamespace(snapshot=lambda: dict(self.provider_state), invalidate=self.invalidations.append),
                 update_pinned_information=lambda: None, write_chat_history_log=lambda *a, **kw: None,
                 time_logger=lambda function: function, mouse_position_lock=threading.Lock(),
                 encode_image_to_base64=lambda path: "image-data", image_detail="low",
                 manage_image_history=lambda *a, **kw: None, clear_last_command_value=lambda: None,
                 safe_print=lambda *a: None)
        s["agent_state"].chat_history = self.store
        s["agent_state"].last_key = ""
        s["agent_state"].last_command = ""
        s["agent_state"].mouse_position = {"x": 0, "y": 0}
        s["pyautogui"].position = lambda: SimpleNamespace(x=0, y=0)
        names = """get_chat_history_store history_entry_age_minutes make_history_control_entry execute_history_command
            invalidate_responses_history update_chat_history init_command pin_command clear_nopin_percentage_command
            clear_percentage_command clear_all_command clear_nonpin_command clear_init_command clear_pin_command
            clear_handoff_command edit_msgs_command delete_msg_command save_chat_history_command display_history_command
            clear_chat_history clear_chat_history_except_pinned clear_history_entries_by_exemption clear_non_pinned_entries
        """.split()
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]), "runtime-history", "exec"), s)
        names = {"INIT": "init_command", "PIN": "pin_command", "CLEAR_NOPIN%": "clear_nopin_percentage_command",
                 "CLEAR%": "clear_percentage_command", "CLEAR": "clear_all_command", "CLEAR_NONPIN": "clear_nonpin_command",
                 "CLEAR_INIT": "clear_init_command", "CLEAR_PIN": "clear_pin_command", "CLEAR_HANDOFF": "clear_handoff_command",
                 "EDIT_MSGS": "edit_msgs_command", "DELETE_MSG": "delete_msg_command", "SAVECH": "save_chat_history_command",
                 "DHISTORY": "display_history_command"}
        s["command_dispatch"].update({name: s[handler] for name, handler in names.items()})

    def run_command(self, text):
        return self.scope["handle_commands"](text)

    def result(self, text):
        result = self.run_command(text)
        self.assertTrue(result["history_command_results"], result)
        return result["history_command_results"][0]

    def test_registered_percentage_commands_are_reachable(self):
        self.store.extend([row("a"), row("b")])
        self.assertTrue(self.run_command("CLEAR_NOPIN%(50,oldest)")["success"])
        self.assertEqual([history.history_text(r) for r in self.store], ["b"])
        self.assertTrue(self.run_command("CLEAR%(100)")["success"])
        self.assertEqual(self.store, [])
        self.assertFalse(self.run_command("UNKNOWN%(3)")["success"])

    def test_invalid_late_command_rejects_whole_batch_before_pin(self):
        for text in ["CLEAR%(nan)", "EDIT_MSGS(t,a,extra)", "DELETE_MSG(t,ignored)", "CLEAR_NONPIN(extra)"]:
            with self.subTest(text=text):
                result = self.run_command("PIN(before); " + text)
                self.assertFalse(result["success"])
                self.assertEqual(self.store, [])

    def test_init_replaces_legacy_and_has_correct_exemption(self):
        self.store.extend([row("[2026-10-01 00:00:00] Pinned Init summary: old"), row("normal")])
        result = self.result("INIT(new, text)")
        self.assertTrue(result["success"])
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(self.store[-1]["Exemption"], "Init")
        self.assertIn("new text", history.history_text(self.store[-1]))
        self.assertTrue(self.run_command("CLEAR_NONPIN()")["success"])
        self.assertEqual(len(self.store), 1)

    def test_retention_gates_reject_without_deleting_old_init(self):
        self.store.append(row("old", "Init"))
        self.scope["ADD_IMSGS_TO_HISTORY"] = False
        result = self.run_command("INIT(new); UPDATE_NOTES(tail)")
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_commands"], ["UPDATE_NOTES(tail)"])
        self.assertEqual(self.store, [row("old", "Init")])

    def test_clear_and_edit_invalidate_provider_but_noop_does_not(self):
        self.provider_state.update(previous_response_id="response-fixture", status="ready")
        self.store.append(row("pin", "Pinned"))
        no_op = self.result("CLEAR_NOPIN%(0)")
        self.assertFalse(no_op["model_work_cancelled"])
        self.assertEqual(self.invalidations, [])
        changed = self.result('EDIT_MSGS("2026-10-01 01:00:00",changed)')
        self.assertTrue(changed["responses_invalidated"])
        self.assertTrue(changed["model_work_cancelled"])
        self.assertEqual(len(self.invalidations), 1)
        self.assertNotEqual(changed["before_version"], changed["after_version"])

    def test_no_matching_timestamp_is_failure_and_stops_tail(self):
        self.store.append(row("old"))
        for command in ["EDIT_MSGS(missing,new)", "DELETE_MSG(missing)"]:
            result = self.run_command(command + "; UPDATE_NOTES(tail)")
            self.assertFalse(result["success"])
            self.assertEqual(result["blocked_commands"], ["UPDATE_NOTES(tail)"])
        self.assertEqual(self.store, [row("old")])

    def test_derived_refresh_failure_restores_local_history(self):
        self.store.extend([row("pin", "Pinned"), row("keep")])
        before = list(self.store)
        self.scope["update_pinned_information"] = lambda: (_ for _ in ()).throw(RuntimeError("fixture refresh error"))
        failed = self.result("CLEAR_PIN()")
        self.assertFalse(failed["success"])
        self.assertEqual(self.store, before)
        self.assertIs(self.store[0], before[0])
        self.assertTrue(failed["model_work_cancelled"])
        self.assertEqual(failed["effect_status"], "restored")
        self.assertEqual(failed["retained_context_effects"], ["model_cancellation"])

    def test_provider_invalidation_failure_preserves_history_and_reports_uncertainty(self):
        self.provider_state.update(previous_response_id="fixture", status="ready")
        self.store.append(row("keep"))
        self.scope["RESPONSES_REASONING"].invalidate = lambda reason: (_ for _ in ()).throw(RuntimeError("fixture provider failure"))
        failed = self.result("CLEAR%(100)")
        self.assertFalse(failed["success"])
        self.assertEqual(failed["effect_status"], "uncertain")
        self.assertTrue(failed["local_state_restored"])
        self.assertTrue(failed["model_work_cancelled"])
        self.assertEqual(self.store, [row("keep")])

    def test_clear_count_excludes_regenerated_pinned_metadata(self):
        self.store.append(row("pin", "Pinned"))
        self.scope["update_pinned_information"] = lambda: self.store.append(row("derived", "PinnedInfo"))
        result = self.result("CLEAR_PIN()")
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["before"]["count"], result["after"]["count"])

    def test_cancelled_model_cannot_append_late_history(self):
        token = self.scope["MODEL_WORK"].token()
        self.store.append(row("old"))
        entered, release = threading.Event(), threading.Event()
        outcome = []
        def append_later():
            try:
                with self.scope["MODEL_WORK"].scope(token.generation):
                    entered.set()
                    release.wait(3)
                    self.scope["update_chat_history"]("assistant", "stale output")
            except WorkCancelled:
                outcome.append("cancelled")
        worker = threading.Thread(target=append_later)
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertTrue(self.result("CLEAR%(100)")["success"])
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, ["cancelled"])
        self.assertEqual(self.store, [])

    def test_legacy_missing_timestamp_does_not_break_append_decay(self):
        self.store.append({"content": "legacy"})
        self.scope["update_chat_history"]("user", "new")
        self.assertEqual(len(self.store), 2)
        self.assertEqual(self.store[0], {"content": "legacy"})

    def test_read_snapshot_preserves_selected_identity_and_detaches_contents(self):
        self.store.extend([row("selected", "Pinned"), row("other", "Init")])
        self.scope.update(_history_context_content_type=lambda entry: entry["content"]["type"],
                          IMPORTANT_HISTORY_EXEMPTIONS={"Pinned", "Init", "Handoff"},
                          HISTORY_CONTEXT_READ_STATE_SCHEMA_VERSION="fixture")
        function = ingress.FUNCTIONS["_build_history_context_read_state"]
        exec(compile(ast.Module(body=[function], type_ignores=[]), "history-read-snapshot", "exec"), self.scope)
        result = self.scope["_build_history_context_read_state"](recent_prompt_history=[self.store[0]])
        self.assertEqual(result["important_text_count"], 2)
        self.assertEqual(result["important_text_selected_count"], 1)
        self.assertIs(result["recent_prompt_history"][0], result["history_store"][0])
        self.store[0]["content"]["text"] = "changed afterward"
        self.assertEqual(result["history_store"][0]["content"]["text"], "selected")

    def test_image_append_preserves_text_image_pair_and_retention_callback(self):
        seen = []
        self.scope["manage_image_history"] = lambda *args, **kwargs: seen.append((args, kwargs))
        self.scope["update_chat_history"]("user", "image label", image_path="fixture.png", sticky=True)
        self.assertEqual([entry["content"]["type"] for entry in self.store], ["text", "image"])
        self.assertEqual(self.store[1]["content"]["data"], "image-data")
        self.assertEqual(self.store[1]["Exemption"], "Image")
        self.assertTrue(seen[0][1]["sticky"])

    def test_failed_audit_is_visible_in_returned_and_published_state(self):
        self.scope["write_chat_history_log"] = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("fixture log unavailable"))
        result = self.result("PIN(saved)")
        self.assertTrue(result["success"])
        self.assertEqual(result["added_timestamps"], [self.store[0]["timestamp"]])
        self.assertIn("fixture log unavailable", result["warnings"][0])
        self.assertEqual(self.scope["runtime_state"]["last_history_command_result"]["warnings"], result["warnings"])

    def test_save_reports_actual_path_without_changing_context(self):
        self.store.append(row("saved"))
        prefix = str(Path(self.fixture.temp.name) / "export")
        result = self.result(f'SAVECH("{prefix}")')
        self.assertTrue(result["success"], result)
        self.assertTrue(Path(result["path"]).exists())
        self.assertFalse(result["model_work_cancelled"])
        self.assertEqual(result["before_version"], result["after_version"])

    def test_duplicate_receipts_retain_history_evidence(self):
        from aurora_control_plane import build_mutation_decision_receipt
        self.store.append(row("old"))
        result = self.result("CLEAR%(100)")
        duplicate = build_mutation_decision_receipt({"decision": "duplicate_terminal", "terminal_receipt": {"history_command_results": [result]}},
                                                    command="CLEAR%(100)", source="fixture", message_id="fixture")
        self.assertEqual(duplicate["history_command_results"], [result])


if __name__ == "__main__":
    unittest.main()
