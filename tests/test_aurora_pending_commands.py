"""Real queue/admission functions with harmless handlers; no native runtime import."""
import ast
import copy
import queue
import threading
import unittest
from types import SimpleNamespace

import aurora_pending_commands as pending
import test_aurora_command_ingress as ingress
from aurora_command_contracts import describe_command_contract


class PendingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ingress.RuntimeIngressTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope = s = self.fixture.scope
        self.store = []
        s.update({name: getattr(pending, name) for name in (
            "PENDING_WRAPPER_MODES", "pending_entry_available", "pending_queue_version", "pending_result", "validate_pending_arguments")})
        s.update(copy=copy, PENDING_COMMAND_LEDGER=pending.PendingCommandLedger(),
                 agent_state=SimpleNamespace(inference_counter=10, pending_model_commands=self.store),
                 EXECUTION_MODE="assist", DEFAULT_PENDING_QUEUE_MODE="normal", PENDING_COMMAND_SUPPORT_WINDOW=3,
                 ALLOWED_PENDING_QUEUE_MODES={"normal", "insert", "replace"},
                 MAX_PENDING_MODEL_COMMANDS=20, AUTO_EXECUTE_PENDING_MIN_SUPPORT=2,
                 route_timestamp=lambda: "fixture-time", get_command_name=lambda text: text.split("(")[0],
                 build_semantic_command_identity=lambda command, **kw: {
                     "family_key": command.lower(), "conflict_key": "", "semantic_label": command.lower()},
                 should_replace_pending_representative=lambda *a: True,
                 evaluate_assistant_command_policy=self.policy,
                 infer_operating_context=lambda: {"context": "unknown"},
                 is_non_action_command_text=lambda text: False,
                 classify_assistant_command=lambda text: "runtime",
                 set_runtime_value=lambda key, value: s["runtime_state"].__setitem__(key, value),
                 build_command_drip_item=lambda **kw: kw,
                 format_agent_pending_candidate_status=lambda: "metadata only",
                 format_agent_pending_gate_status=lambda: "closed",
                 format_agent_pending_insert_dry_run_status=lambda: "closed",
                 build_queue_next_action_runtime_cue=lambda: "fixture")
        for name in ("append_recent_command_proposal", "append_recent_action_intent", "append_command_drip_item", "append_command_drip_note"):
            s[name] = lambda *a, **kw: None
        names = """
            get_pending_command_store get_pending_command_snapshot evaluate_pending_command_policy prepare_pending_entry
            record_pending_command_result submit_pending_entry execute_pending_approval infer_pending_queue_directive
            _resolve_pending_indexes _queue_pending_from_wrapper queue_pending_command_command insert_pending_command_command
            replace_pending_command_command approve_pending_command clear_pending_commands_command show_pending_commands_command
            queue_pending_model_command normalize_pending_queue_mode score_pending_entry apply_pending_entry_scores
            _mark_pending_entry_shifted shift_pending_entries_for_insert replace_immediate_pending_entries
            supersede_conflicting_pending_entries refresh_pending_command_estimates is_pending_entry_auto_approvable
            auto_execute_pending_commands route_assistant_commands adjust_pending_support_from_outcome build_pending_command_summary
        """.split()
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), s)
        handlers = {"QUEUE_PENDING": "queue_pending_command_command", "INSERT_PENDING": "insert_pending_command_command",
                    "REPLACE_PENDING": "replace_pending_command_command", "OVERRIDE_PENDING": "replace_pending_command_command",
                    "APPROVE_PENDING": "approve_pending_command", "CLEAR_PENDING_COMMANDS": "clear_pending_commands_command",
                    "CLEAR_PENDING": "clear_pending_commands_command", "SHOW_PENDING": "show_pending_commands_command",
                    "SHOW_PENDING_COMMANDS": "show_pending_commands_command"}
        s["command_dispatch"].update({name: s[handler] for name, handler in handlers.items()})
        s["command_dispatch"]["WAIT"] = lambda args, user: self.fixture.executed.append(("WAIT", args))
        s["command_dispatch"]["FAIL"] = lambda args, user: {"success": False, "reason": "fixture execution failure"}

    def policy(self, command):
        memory = command.startswith("UPDATE_")
        return {"decision": "allow" if memory else "hold", "risk": "low" if memory else "medium",
                "category": "memory" if memory else "runtime", "operating_context": "unknown", "policy_reason": "fixture"}

    def add(self, command="WAIT(0)", mode="normal"):
        return self.scope["queue_pending_model_command"](command, queue_mode=mode)

    def run_command(self, command):
        return self.scope["handle_commands"](command)

    def test_unmatched_category_clear_does_not_clear_anything(self):
        self.add()
        before = copy.deepcopy(self.store)
        result = self.run_command("CLEAR_PENDING(memory)")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.store, before)
        self.assertEqual(result["pending_command_results"][0]["cleared_count"], 0)

    def test_bad_selector_stops_tail_and_preserves_items(self):
        self.add()
        result = self.run_command("CLEAR_PENDING(all,typo); UPDATE_NOTES(tail)")
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_commands"], ["UPDATE_NOTES(tail)"])
        self.assertEqual(len(self.store), 1)
        self.assertEqual(self.fixture.executed, [])

    def test_empty_queue_does_not_hide_invalid_selector(self):
        for command in ("APPROVE_PENDING(1)", "CLEAR_PENDING(typo)", "CLEAR_PENDING(all,999)"):
            with self.subTest(command=command):
                self.assertFalse(self.run_command(command)["success"])
        self.assertTrue(self.run_command("CLEAR_PENDING(memory)")["success"])
        self.assertTrue(self.run_command("APPROVE_PENDING()")["success"])

    def test_surplus_blank_and_bad_nested_commands_reject_whole_batch(self):
        for text in ("QUEUE_PENDING()", 'QUEUE_PENDING("")', "QUEUE_PENDING(WAIT(0),WAIT(1))",
                     "INSERT_PENDING(NO_SUCH_COMMAND())", "QUEUE_PENDING(WAIT(nan))",
                     'QUEUE_PENDING("WAIT(0); WAIT(-1)")', "SHOW_PENDING(extra)", "CLEAR_PENDING(0)"):
            with self.subTest(text=text):
                result = self.run_command("UPDATE_NOTES(before); " + text)
                self.assertFalse(result["success"], result)
                self.assertEqual(self.fixture.executed, [])
                self.assertEqual(self.store, [])

    def test_nested_batches_and_aliases_remain_supported(self):
        result = self.run_command('QUEUE_PENDING("WAIT(0); UPDATE_NOTES(\'a,b\')")')
        self.assertTrue(result["success"], result)
        result = self.run_command("APPROVE_PENDING()")
        self.assertTrue(result["success"], result)
        self.assertEqual([row[0] for row in self.fixture.executed], ["WAIT", "UPDATE_NOTES"])
        self.assertTrue(self.run_command("OVERRIDE_PENDING(WAIT(0)); SHOW_PENDING(); CLEAR_PENDING()")["success"])

    def test_nested_depth_is_bounded(self):
        text = "WAIT(0)"
        for _ in range(34):
            text = "QUEUE_PENDING(" + text + ")"
        result = self.run_command(text)
        self.assertFalse(result["success"])
        self.assertIn("32", str(result["failed_commands"]))

    def test_normal_support_insert_replace_and_scoring_are_preserved(self):
        first = self.add("WAIT(0)")
        identity = first["pending_id"]
        self.add("WAIT(0)")
        self.assertEqual(first["support_count"], 2)
        self.assertEqual(first["pending_id"], identity)
        second = self.add("WAIT(1)", "insert")
        self.assertEqual(first["execute_by_inference"], 13)
        self.assertEqual(second["execute_by_inference"], 11)
        result = self.run_command("REPLACE_PENDING(WAIT(2))")
        self.assertTrue(result["success"], result)
        self.assertEqual([row["command"] for row in self.store], ["WAIT(0)", "WAIT(2)"])
        self.assertIn(second["pending_id"], result["pending_command_results"][0]["removed_ids"])
        self.assertGreater(first["priority_score"], 0)

    def test_version_and_identity_prevent_stale_targeting(self):
        first = self.add("WAIT(0)")
        version = self.scope["get_pending_command_snapshot"]()["version"]
        self.add("WAIT(1)")
        stale = self.run_command(f"CLEAR_PENDING(id:{first['pending_id']},version:{version})")
        self.assertFalse(stale["success"])
        current = self.run_command(f"CLEAR_PENDING(id:{first['pending_id']})")
        self.assertTrue(current["success"])
        self.assertEqual([row["command"] for row in self.store], ["WAIT(1)"])
        self.assertFalse(self.run_command(f"APPROVE_PENDING(id:{first['pending_id']})")["success"])
        self.assertEqual(self.fixture.executed, [])

    def test_mixed_selectors_deduplicate_and_validate_all(self):
        first = self.add("WAIT(0)")
        second = self.add("UPDATE_NOTES(note)")
        resolve = self.scope["_resolve_pending_indexes"]
        self.assertEqual(resolve(["1", "runtime", "WAIT(0)", "id:" + second["pending_id"]]), [0, 1])
        self.assertEqual(resolve([]), [0])
        self.assertEqual(resolve([], True), [0, 1])
        for args in (["all", "no-match"], ["all", "99"], ["version:" + "0" * 64, "all"], ["id:bad"]):
            with self.assertRaises(ValueError):
                resolve(args)

    def test_full_selection_preflight_precedes_removal(self):
        first = self.add()
        self.store.append({"command": "WAIT(-1)"})
        result = self.run_command("APPROVE_PENDING(all)")
        self.assertFalse(result["success"])
        self.assertEqual(len(self.store), 2)
        self.assertEqual(first["pending_state"], "held")
        self.assertEqual(self.fixture.executed, [])

    def test_async_acknowledgement_correlates_execution_and_removes_once(self):
        entry = self.add()
        commands = queue.Queue()
        self.scope["active_command_queue"] = commands
        result = self.scope["execute_pending_approval"]([])
        self.assertEqual(result["submissions"][0]["status"], "queued")
        self.assertEqual(self.store, [])
        submitted = commands.get_nowait()
        self.assertEqual(submitted["pending_id"], entry["pending_id"])
        self.assertEqual(submitted["pending_attempt_id"], result["submissions"][0]["pending_attempt_id"])
        self.assertFalse(self.run_command(f"APPROVE_PENDING(id:{entry['pending_id']})")["success"])
        terminal = self.scope["execute_command_entry"](submitted)
        self.assertEqual(terminal["pending_id"], entry["pending_id"])
        self.assertTrue(terminal["success"])

    def test_direct_execution_failure_stops_later_approvals_and_batch_tail(self):
        self.add("FAIL()")
        second = self.add("WAIT(0)")
        result = self.run_command("APPROVE_PENDING(all); UPDATE_NOTES(tail)")
        self.assertFalse(result["success"])
        outcomes = result["pending_command_results"][0]["submissions"]
        self.assertEqual([row["status"] for row in outcomes], ["failed", "not_started"])
        self.assertEqual(self.store, [second])
        self.assertEqual(second["pending_state"], "held")
        self.assertEqual(self.fixture.executed, [])

    def test_uncertain_queue_put_keeps_quarantine_and_blocks_replay(self):
        first = self.add()
        second = self.add("WAIT(1)")
        calls = []
        def uncertain_put(entry):
            calls.append(entry)
            raise OSError("acknowledgement lost after put")
        self.scope["active_command_queue"] = SimpleNamespace(put=uncertain_put)
        result = self.run_command("APPROVE_PENDING(all)")
        self.assertFalse(result["success"])
        self.assertEqual(first["pending_state"], "uncertain")
        self.assertEqual(second["pending_state"], "held")
        self.assertFalse(self.run_command(f"APPROVE_PENDING(id:{first['pending_id']})")["success"])
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            self.add()
        clear = self.run_command(f"CLEAR_PENDING(id:{first['pending_id']})")["pending_command_results"][0]
        self.assertFalse(clear["execution_cancelled"])
        self.assertEqual(clear["uncertain_ids"], [first["pending_id"]])

    def test_optional_audit_failure_cannot_requeue_accepted_execution(self):
        self.add()
        self.scope["append_recent_command_proposal"] = lambda *a, **kw: (_ for _ in ()).throw(OSError("audit failed"))
        result = self.scope["execute_pending_approval"]([])
        self.assertTrue(result["success"], result)
        self.assertTrue(result["warnings"])
        self.assertEqual(self.store, [])
        self.assertEqual(len(self.fixture.executed), 1)

    def test_planning_failure_restores_queue_and_original_objects(self):
        original = self.add()
        before = copy.deepcopy(self.store)
        self.scope["append_recent_action_intent"] = lambda *a, **kw: (_ for _ in ()).throw(OSError("fixture audit failure"))
        result = self.run_command("INSERT_PENDING(WAIT(1))")
        self.assertFalse(result["success"])
        self.assertEqual(self.store, before)
        self.assertIs(self.store[0], original)

    def test_cancellation_between_items_does_not_adopt_new_generation(self):
        self.add("WAIT(0)")
        second = self.add("WAIT(1)")
        commands = []
        def put(entry):
            commands.append(entry)
            self.scope["COMMAND_WORK"].cancel("fixture stop")
        self.scope["active_command_queue"] = SimpleNamespace(put=put)
        result = self.scope["execute_pending_approval"](["all"])
        self.assertFalse(result["success"])
        self.assertTrue(result["cancelled"])
        self.assertEqual(len(commands), 1)
        self.assertEqual(self.store, [second])
        terminal = self.scope["execute_command_entry"](commands[0])
        self.assertTrue(terminal["cancelled"])
        self.assertEqual(self.fixture.executed, [])

    def test_reservation_excludes_concurrent_approve_clear_replace_and_support(self):
        first = self.add()
        entered, release = threading.Event(), threading.Event()
        result = []
        def put(entry):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test release missing")
        self.scope["active_command_queue"] = SimpleNamespace(put=put)
        thread = threading.Thread(target=lambda: result.append(self.scope["execute_pending_approval"]([])))
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertFalse(self.run_command("APPROVE_PENDING()")["success"])
            self.assertFalse(self.run_command("CLEAR_PENDING(all)")["success"])
            with self.assertRaises(ValueError):
                self.add()
            self.add("WAIT(1)", "replace")
            self.assertIn(first, self.store)
            self.scope["adjust_pending_support_from_outcome"]({"family_key": first["family_key"], "outcome_score": 1})
            self.assertIn(first, self.store)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result[0]["success"])
        self.assertEqual([row["command"] for row in self.store], ["WAIT(1)"])

    def test_auto_policy_keeps_manual_and_uncertain_gates(self):
        manual = self.add("UPDATE_NOTES(manual)")
        manual.update(manual_approval_required=True, source="sub_agent_pending_insert")
        uncertain = self.add("UPDATE_NOTES(uncertain)")
        uncertain["pending_state"] = "uncertain"
        normal = self.add("UPDATE_NOTES(allowed)")
        self.scope["EXECUTION_MODE"] = "auto"
        accepted = self.scope["auto_execute_pending_commands"]()
        self.assertEqual([row["pending_id"] for row in accepted], [normal["pending_id"]])
        self.assertEqual(self.store, [manual, uncertain])
        self.assertTrue(self.run_command(f"APPROVE_PENDING(id:{manual['pending_id']})")["success"])

    def test_auto_policy_checks_every_batch_member(self):
        self.add("UPDATE_NOTES(allowed); WAIT(0)")
        self.scope["EXECUTION_MODE"] = "auto"
        self.assertEqual(self.scope["auto_execute_pending_commands"](), [])
        self.assertEqual(len(self.store), 1)

    def test_model_malformed_proposal_cannot_supersede_or_gain_support(self):
        first = self.add()
        before = copy.deepcopy(self.store)
        for command in ("WAIT(nan)", "QUEUE_PENDING(WAIT(0),WAIT(1))", "NO_SUCH_COMMAND()", "WAIT(0"):
            result = self.scope["route_assistant_commands"](command)
            self.assertEqual(result["rejected_count"], 1, result)
        self.assertEqual(self.store, before)

    def test_representative_risk_is_compared_before_metadata_update(self):
        self.scope["build_semantic_command_identity"] = lambda *a, **kw: {"family_key": "same-family", "conflict_key": ""}
        node = ingress.FUNCTIONS["should_replace_pending_representative"]
        exec(compile(ast.Module(body=[node], type_ignores=[]), "runtime-representative", "exec"), self.scope)
        self.scope["get_risk_rank"] = lambda risk: {"low": 0, "medium": 1, "high": 2}[risk]
        self.scope["get_pyag_action_name"] = lambda command: ""
        self.scope["evaluate_assistant_command_policy"] = lambda command: {
            **self.policy(command), "risk": "low" if command == "WAIT(0)" else "high"}
        first = self.add("WAIT(1)")
        self.add("WAIT(0)")
        self.assertEqual(first["command"], "WAIT(0)")
        self.assertEqual(first["risk"], "low")
        self.add("WAIT(2)")
        self.assertEqual(first["command"], "WAIT(0)")
        self.assertEqual(first["risk"], "low")
        self.assertEqual(first["support_count"], 3)

    def test_capacity_never_evicts_uncertain_ownership(self):
        self.scope["MAX_PENDING_MODEL_COMMANDS"] = 1
        first = self.add()
        first["pending_state"] = "uncertain"
        result = self.run_command("REPLACE_PENDING(WAIT(1))")
        self.assertFalse(result["success"])
        self.assertEqual(self.store, [first])
        self.assertIs(self.store[0], first)

    def test_projected_mode_allows_valid_nested_implicit_action(self):
        self.scope["command_dispatch"]["GB_MODE"] = lambda *a: None
        prepared = self.scope["prepare_command_batch"]("GB_MODE(); QUEUE_PENDING(press(a))")
        self.assertEqual(len(prepared), 2)

    def test_duplicate_receipt_preserves_pending_transition(self):
        self.add()
        terminal = self.scope["execute_pending_approval"]([])
        receipt = {"pending_command_results": [terminal], "pending_id": "fixture-id", "pending_attempt_id": "fixture-attempt"}
        from aurora_control_plane import build_mutation_decision_receipt
        duplicate = build_mutation_decision_receipt({"decision": "duplicate_terminal", "terminal_receipt": receipt},
                                                    command="APPROVE_PENDING()", source="fixture", message_id="fixture")
        self.assertEqual(duplicate["pending_command_results"], [terminal])
        self.assertEqual(duplicate["pending_attempt_id"], "fixture-attempt")

    def test_frozen_desktop_route_survives_mode_changes(self):
        entry = self.add("GB:press(a)")
        route = entry["_prepared_commands"][0][3]
        self.assertEqual(route.namespace, "gb")
        self.scope["ACTIVE_ACTION_MODE"] = "pyag"
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.scope["active_command_queue"] = queue.Queue()
        result = self.scope["execute_pending_approval"]([])
        self.assertTrue(result["success"])
        queued = self.scope["active_command_queue"].get_nowait()
        self.assertEqual(queued["prepared_commands"][0][3], route)

    def test_snapshot_and_show_hide_private_prepared_payload(self):
        self.add()
        snapshot = self.scope["get_pending_command_snapshot"]()
        self.assertNotIn("_prepared_commands", snapshot["entries"][0])
        snapshot["entries"][0]["command"] = "changed"
        self.assertEqual(self.store[0]["command"], "WAIT(0)")
        result = self.run_command("SHOW_PENDING()")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["pending_command_results"][0]["entries"][0]["pending_id"], self.store[0]["pending_id"])


class PendingContractTests(unittest.TestCase):
    def test_all_existing_aliases_share_reviewed_contracts(self):
        self.assertEqual(len(pending.PENDING_COMMANDS), 9)
        for name in pending.PENDING_COMMANDS:
            contract = describe_command_contract(name)
            self.assertEqual(contract["parameter_validation"], "pre_dispatch")
            self.assertEqual(contract["result"]["receipt_field"], "pending_command_results")

    def test_version_ignores_estimates_but_tracks_meaning_and_order(self):
        rows = [{"command": "WAIT(0)", "support_count": 1, "turns_until_due": 3}]
        version = pending.pending_queue_version(rows)
        rows[0]["turns_until_due"] = 2
        self.assertEqual(pending.pending_queue_version(rows), version)
        rows[0]["support_count"] = 2
        self.assertNotEqual(pending.pending_queue_version(rows), version)

    def test_panel_selection_prefers_ids_and_version_with_legacy_fallback(self):
        tree = ast.parse((ingress.ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "pending_selection_arguments")
        scope = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "panel-selection", "exec"), scope)
        fake = SimpleNamespace(pending_tree=SimpleNamespace(item=lambda *a: ["2"]),
                               pending_item_selectors={"item": "id:pending-" + "a" * 32}, pending_snapshot_version="b" * 64)
        self.assertEqual(scope[method.name](fake, ["item"]), ["id:pending-" + "a" * 32, "version:" + "b" * 64])
        self.assertEqual(scope[method.name](fake, ["legacy"]), ["2"])


if __name__ == "__main__":
    unittest.main()
