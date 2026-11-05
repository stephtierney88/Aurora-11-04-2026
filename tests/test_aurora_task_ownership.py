"""Cross-task queued artifacts: compatibility, admission, races and manual holds."""
import ast
import copy
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import test_aurora_command_ingress as ingress
import test_aurora_pending_commands as pending_fixture
from aurora_command_contracts import inference_plan_version, normalize_next_inference_pairs
from aurora_history_controls import history_actor_scope
from aurora_task_continuation import (TASK_ORIGIN_SCHEMA, TASK_TRANSITION_SCHEMA, TaskContinuation,
                                     command_task_scope, reconcile_task_artifacts, scoped_task_id)


OLD, NEW = "task-" + "a" * 32, "task-" + "b" * 32


def artifact(identity=OLD, kind="model", **fields):
    return dict(task_origin=dict(schema=TASK_ORIGIN_SCHEMA, kind=kind, task_id=identity), **fields)


class ArtifactPolicyTests(unittest.TestCase):
    def test_carry_is_detached_without_changing_content(self):
        plan = artifact(plan_id="plan-1", note="private plan")
        pending = [artifact(pending_id="p1", command="WAIT(0)")]
        new_plan, rows, receipt = reconcile_task_artifacts(plan, pending, NEW)
        self.assertEqual((new_plan, rows), (plan, pending))
        rows[0]["task_origin"]["task_id"] = NEW
        self.assertEqual(scoped_task_id(pending[0]), OLD)
        self.assertNotIn("private plan", str(receipt))
        self.assertNotIn("WAIT(0)", str(receipt))
        self.assertFalse(receipt["rollback_supported"])

    def test_strict_policies_preserve_operator_unattributed_malformed_and_same_task(self):
        for value in ({}, {"task_origin": "old format"}, {"task_origin": ["unknown"]},
                      artifact(kind=[]), artifact(kind="operator"), artifact(identity="not-a-task"), artifact(identity=NEW)):
            with self.subTest(value=value):
                plan, rows, _ = reconcile_task_artifacts(value, [value], NEW, "discard_previous", "discard_previous")
                self.assertEqual(plan, value)
                self.assertEqual(rows, [value])

    def test_discard_never_cancels_reserved_or_uncertain_submissions(self):
        pending = [artifact(pending_id=state, pending_state=state) for state in ("held", "task_held", "reserved", "uncertain")]
        plan, rows, receipt = reconcile_task_artifacts(artifact(plan_id="p"), pending, NEW, "discard_previous", "discard_previous")
        self.assertIsNone(plan)
        self.assertEqual([r["pending_state"] for r in rows], ["reserved", "uncertain"])
        self.assertEqual(receipt["pending_dispositions"], {"discarded": 2, "in_flight_or_uncertain_preserved": 2})

    def test_hold_is_operator_only_and_carry_does_not_release_it(self):
        _, rows, _ = reconcile_task_artifacts({}, [artifact(pending_id="p")], NEW, pending_policy="hold_previous")
        self.assertEqual(rows[0]["pending_state"], "task_held")
        self.assertTrue(rows[0]["manual_approval_required"])
        _, carried, _ = reconcile_task_artifacts({}, rows, "task-" + "c" * 32)
        self.assertEqual(carried, rows)

    def test_receipt_detail_is_bounded_with_complete_counts(self):
        rows = [artifact(pending_id=str(n)) for n in range(90)]
        _, kept, receipt = reconcile_task_artifacts({}, rows, NEW, pending_policy="discard_previous")
        self.assertEqual(kept, [])
        self.assertEqual(receipt["pending_dispositions"]["discarded"], 90)
        self.assertEqual((len(receipt["pending_items"]), receipt["pending_items_omitted"]), (64, 26))

    def test_invalid_policies_fail_before_mutation(self):
        rows = [artifact(pending_id="p")]
        before = copy.deepcopy(rows)
        for kwargs in ({"plan_policy": "typo"}, {"pending_policy": "typo"}, {"task_id": "bad"}):
            with self.assertRaises(ValueError):
                reconcile_task_artifacts({}, rows, **{"task_id": NEW, **kwargs})
        self.assertEqual(rows, before)

    def test_policy_and_transition_snapshot_latch_and_detach(self):
        task = TaskContinuation()
        task.reserve(max_turns=8, max_seconds=120, plan_carry_policy="discard_previous", pending_carry_policy="hold_previous")
        identity = task.snapshot()["task_id"]
        task.reserve(max_turns=100, max_seconds=1000)
        self.assertEqual(task.snapshot()["pending_carry_policy"], "hold_previous")
        receipt = dict(task_id=identity, pending_items=[{"pending_id": "p"}])
        self.assertTrue(task.record_artifact_transition(receipt))
        receipt["pending_items"].clear()
        self.assertNotIn("pending_items", task.snapshot()["artifact_transition"])
        self.assertEqual(len(task.snapshot(include_progress=True)["artifact_transition"]["pending_items"]), 1)
        self.assertFalse(task.record_artifact_transition(dict(task_id=OLD)))


class OwnershipRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = pending_fixture.PendingRuntimeTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.s, self.rows = self.fixture.scope, self.fixture.store
        self.s.update(SETTINGS_TRANSACTION_LOCK=threading.RLock(), TASK_CONTINUATION_MODE="bounded",
                      TASK_MAX_MODEL_TURNS=20, TASK_MAX_SECONDS=120, TASK_OUTCOME_REPORTING=False,
                      TASK_MAX_COMMANDS=0, TASK_MAX_REPORTED_TOKENS=0, TASK_UNKNOWN_USAGE_POLICY="continue",
                      TASK_PLAN_CARRY_POLICY="carry", TASK_PENDING_CARRY_POLICY="carry",
                      TASK_TRANSITION_SCHEMA=TASK_TRANSITION_SCHEMA, reconcile_task_artifacts=reconcile_task_artifacts,
                      inference_plan_version=inference_plan_version, normalize_next_inference_pairs=normalize_next_inference_pairs,
                      require_runtime_setting_unlocked=lambda *a: None)
        names = "create_empty_next_inference_plan get_next_inference_plan_snapshot build_next_inference_plan_summary has_effective_next_inference_plan set_next_inference_plan_from_pairs reserve_task_continuation_for_turn".split()
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[n] for n in names], type_ignores=[]), str(ingress.ROOT / "aurora2.py"), "exec"), self.s)
        self.s["agent_state"].next_inference_plan = self.s["create_empty_next_inference_plan"]()

    def start(self):
        self.assertTrue(self.s["reserve_task_continuation_for_turn"](operator_input=True))
        return self.s["TASK_CONTINUATION"].snapshot()["task_id"]

    def queue_owned(self, task_id, command="WAIT(0)"):
        with history_actor_scope("model:fixture"), command_task_scope(dict(task_id=task_id, inference_request_id="r1")):
            row = self.fixture.add(command)
            plan = self.s["set_next_inference_plan_from_pairs"]({"note": "fixture private plan", "target_turn": 99})
        return row, plan

    def stop(self):
        self.s["TASK_CONTINUATION"].stop("operator_cancelled")

    def test_default_transition_retains_artifact_identity_and_versions(self):
        old = self.start()
        row, plan = self.queue_owned(old)
        before = self.s["get_pending_command_snapshot"]()["version"]
        self.stop()
        self.assertNotEqual(self.start(), old)
        self.assertIs(self.rows[0], row)
        self.assertEqual(self.s["get_next_inference_plan_snapshot"](), plan)
        self.assertEqual(self.s["get_pending_command_snapshot"]()["version"], before)
        receipt = self.s["TASK_CONTINUATION"].snapshot()["artifact_transition"]
        self.assertEqual(receipt["before_plan_version"], receipt["after_plan_version"])

    def test_strict_transition_and_late_publication_never_touch_operator_artifacts(self):
        old = self.start()
        self.queue_owned(old)
        with history_actor_scope("operator"):
            manual = self.fixture.add("WAIT(1)")
        self.s.update(TASK_PLAN_CARRY_POLICY="discard_previous", TASK_PENDING_CARRY_POLICY="discard_previous")
        self.stop()
        current = self.start()
        self.assertEqual(self.rows, [manual])
        self.assertFalse(self.s["get_next_inference_plan_snapshot"]()["target_turn"])
        with history_actor_scope("operator"):
            plan = self.s["set_next_inference_plan_from_pairs"]({"note": "manual"})
        with history_actor_scope("model:fixture"), command_task_scope(dict(task_id=old)):
            with self.assertRaises(RuntimeError):
                self.fixture.add("WAIT(2)")
            with self.assertRaises(RuntimeError):
                self.s["set_next_inference_plan_from_pairs"]({"note": "late"})
        self.assertEqual(self.s["get_next_inference_plan_snapshot"](), plan)
        self.assertEqual(self.rows, [manual])
        self.assertNotEqual(old, current)

    def test_midtask_changes_do_not_reconcile_until_a_new_task(self):
        old = self.start()
        row, plan = self.queue_owned(old)
        self.s.update(TASK_PLAN_CARRY_POLICY="discard_previous", TASK_PENDING_CARRY_POLICY="hold_previous")
        self.assertEqual(self.start(), old)
        self.assertEqual(self.rows, [row])
        self.assertEqual(self.s["get_next_inference_plan_snapshot"](), plan)
        self.assertEqual(self.s["TASK_CONTINUATION"].snapshot()["pending_carry_policy"], "carry")
        self.stop()
        self.start()
        self.assertEqual(self.rows[0]["pending_state"], "task_held")

    def test_task_hold_blocks_auto_model_clear_and_model_approval_but_operator_can_approve(self):
        old = self.start()
        self.queue_owned(old)
        self.s["TASK_PENDING_CARRY_POLICY"] = "hold_previous"
        self.stop()
        self.start()
        row = self.rows[0]
        self.assertFalse(self.s["is_pending_entry_auto_approvable"](row)[0])
        self.assertFalse(self.s["execute_pending_approval"](["all"])["success"])
        self.assertFalse(self.s["clear_pending_commands_command"](["all"], False)["success"])
        self.assertEqual(self.rows, [row])
        with self.assertRaises(ValueError):
            self.fixture.add("WAIT(0)")
        self.assertTrue(self.s["execute_pending_approval"](["all"], operator=True)["success"])
        self.assertEqual(self.rows, [])
        self.assertEqual(self.fixture.fixture.executed, [("WAIT", ["0"])])

    def test_unstarted_manual_submission_restores_task_hold(self):
        old = self.start()
        self.queue_owned(old)
        self.s["TASK_PENDING_CARRY_POLICY"] = "hold_previous"
        self.stop()
        self.start()
        ledger = self.s["PENDING_COMMAND_LEDGER"]
        reservations = ledger.reserve(self.rows, [0], prepare=lambda e: {}, check=lambda: None, allow_task_held=True)
        ledger.finish(self.rows, reservations[0], {"status": "not_started"})
        self.assertEqual(self.rows[0]["pending_state"], "task_held")

    def test_transition_preparation_failure_retains_stores_and_stops_task(self):
        old = self.start()
        row, plan = self.queue_owned(old)
        legacy = {"command": "WAIT(1)"}
        self.rows.append(legacy)
        self.stop()
        self.s["reconcile_task_artifacts"] = lambda *a: (_ for _ in ()).throw(ValueError("fixture failure"))
        with self.assertRaises(ValueError):
            self.start()
        self.assertIs(self.rows[0], row)
        self.assertIs(self.rows[1], legacy)
        self.assertEqual(legacy, {"command": "WAIT(1)"})
        self.assertEqual(self.s["get_next_inference_plan_snapshot"](), plan)
        self.assertEqual(self.s["TASK_CONTINUATION"].snapshot()["stop_reason"], "artifact_transition_failed")

    def test_publication_at_transition_boundary_is_serialized_without_deadlock(self):
        old = self.start()
        self.s.update(TASK_PLAN_CARRY_POLICY="discard_previous", TASK_PENDING_CARRY_POLICY="discard_previous")
        self.stop()
        barrier = threading.Barrier(2)
        def late_publish():
            barrier.wait(timeout=2)
            try:
                self.queue_owned(old)
            except RuntimeError:
                pass
        def transition():
            barrier.wait(timeout=2)
            self.start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(late_publish), pool.submit(transition)]
            for future in futures:
                future.result(timeout=3)
        self.assertEqual(self.rows, [])
        self.assertFalse(self.s["get_next_inference_plan_snapshot"]()["target_turn"])

    def test_journal_failure_does_not_revert_committed_transition_or_drop_turn(self):
        old = self.start()
        self.queue_owned(old)
        self.s.update(TASK_PLAN_CARRY_POLICY="discard_previous", TASK_PENDING_CARRY_POLICY="discard_previous")
        self.stop()
        self.s["write_command_execution_log"] = lambda *a, **kw: (_ for _ in ()).throw(OSError("disk fixture"))
        self.start()
        active = self.s["TASK_CONTINUATION"].snapshot()
        self.assertEqual(active["status"], "running")
        self.assertEqual(active["artifact_transition"]["journal_status"], "failed")
        self.assertEqual(self.rows, [])
        self.assertFalse(self.s["get_next_inference_plan_snapshot"]()["target_turn"])

    def test_reserved_row_keeps_identity_until_original_submitter_acknowledges(self):
        old = self.start()
        row, _ = self.queue_owned(old)
        ledger = self.s["PENDING_COMMAND_LEDGER"]
        with ledger.lock:
            reserved = ledger.reserve(self.rows, [0], prepare=lambda e: [], check=lambda: None)[0]
        self.s["TASK_PENDING_CARRY_POLICY"] = "discard_previous"
        self.stop()
        self.start()
        self.assertIs(self.rows[0], row)
        result = ledger.finish(self.rows, reserved, {"status": "queued"})
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.rows, [])


if __name__ == "__main__":
    unittest.main()
