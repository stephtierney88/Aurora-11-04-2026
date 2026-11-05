"""Controller observations remain bounded, correlated and distinct from success."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import unittest

from aurora_task_continuation import TaskContinuation, _elapsed_ms
from aurora_delivery_receipts import delivery_turn


class TaskProgressTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = TaskContinuation(clock=lambda: self.now)
        self.task.reserve(max_turns=20, max_seconds=120)
        self.identity = self.task.snapshot()["task_id"]

    def entry(self, identity="b1", **kwargs):
        return dict(task_id=self.identity, command_batch_id=identity, inference_request_id="r1",
                    prepared_commands=[("PRIVATE_ARGUMENT", "UPDATE_NOTES", ["PRIVATE_TEXT"])], **kwargs)

    def receipt(self, identity="b1"):
        return dict(task_id=self.identity, command_batch_id=identity, inference_request_id="r1",
                    receipt_id="receipt-" + identity, status="processed", executed_commands=["PRIVATE_TEXT"])

    def delivery(self, identity="r2", frame_id="", batch_ids=()):
        return NS(task_id=self.identity, inference_request_id=identity, model="fixture-model", frame_id=frame_id,
                  command_readbacks={"records": [{"command_batch_id": value} for value in batch_ids]})

    def progress(self):
        return self.task.snapshot(include_progress=True)["progress"]

    def test_admission_receipt_frame_and_request_join_exact_identities(self):
        self.task.record_command_admission(self.entry())
        self.now += 2
        self.task.record_command(self.receipt())
        self.task.record_observation_wait([self.entry()], dict(session_id="capture", lifecycle=4, after_monotonic=900), 5, 6)
        self.now += 3
        frame = {"path": "PRIVATE_PATH", "provenance": dict(status="acquired", frame_id="f1", session_id="capture",
                     lifecycle=4, request_generation=6, acquired_start_monotonic=905)}
        self.assertTrue(self.task.record_frame_observed(frame))
        self.now += 1
        delivery = self.delivery(frame_id="f1", batch_ids=["b1"])
        self.task.record_request_progress(delivery, "preparing")
        self.now += .5
        self.task.record_request_progress(delivery, "prepared")
        self.now += .25
        self.task.record_request_progress(delivery, "submitted")
        self.now += 4
        self.task.record_request_progress(delivery, "responded")
        progress = self.progress()
        batch, request = progress["commands"][0], progress["requests"][0]
        self.assertEqual(batch["latency_ms"], dict(admission_to_receipt=2000, observation_wait=3000,
            receipt_to_frame_observed=3000, receipt_to_readback_prepared=4500, frame_observed_to_request_prepared=1500))
        self.assertEqual(request["latency_ms"], dict(preparation=500, prepared_to_submitted=250,
                         submitted_to_response=4000, submitted_to_terminal=4000))
        self.assertEqual(request["readback_batch_ids"], ["b1"])
        self.assertEqual(request["frame_batch_ids"], ["b1"])
        self.assertEqual((batch["frame_request_id"], batch["capture_request_generation"]), ("r2", 6))
        self.assertNotIn("PRIVATE_", json.dumps(progress))

    def test_unknown_or_unrelated_frames_cannot_fabricate_observation(self):
        self.task.record_command(self.receipt())
        self.task.record_observation_wait([self.entry()], dict(session_id="s", lifecycle=1, after_monotonic=10), 2, 3)
        valid = dict(status="acquired", frame_id="f", session_id="s", lifecycle=1, request_generation=3, acquired_start_monotonic=11)
        for replacement in ({"status": "unknown"}, {"session_id": "other"}, {"lifecycle": 0},
                            {"request_generation": 2}, {"request_generation": True},
                            {"acquired_start_monotonic": 9}, {"acquired_start_monotonic": float("nan")}):
            self.assertFalse(self.task.record_frame_observed({"provenance": dict(valid, **replacement)}))
        row = self.progress()["commands"][0]
        self.assertNotIn("frame_id", row)
        self.assertIsNone(row["latency_ms"]["admission_to_receipt"])
        self.assertIsNone(row["latency_ms"]["receipt_to_frame_observed"])

    def test_selected_frame_and_readbacks_do_not_use_nearest_by_time(self):
        self.task.record_command_admission(self.entry())
        self.task.record_command(self.receipt())
        self.task.record_request_progress(self.delivery(frame_id="unrelated", batch_ids=["missing"]), "prepared")
        request = self.progress()["requests"][0]
        self.assertEqual(request["readback_batch_ids"], [])
        self.assertEqual(request["frame_batch_ids"], [])
        self.assertIsNone(self.progress()["commands"][0]["latency_ms"]["receipt_to_readback_prepared"])

    def test_new_observation_boundary_cannot_inherit_an_early_frame(self):
        self.task.record_command_admission(self.entry())
        self.task.record_observation_wait([self.entry()], dict(session_id="s", lifecycle=1, after_monotonic=10), 2, 3)
        old = dict(status="acquired", frame_id="early", session_id="s", lifecycle=1, request_generation=3, acquired_start_monotonic=11)
        self.assertTrue(self.task.record_frame_observed({"provenance": old}))
        self.task.record_observation_wait([self.entry()], dict(session_id="s", lifecycle=1, after_monotonic=20), 3, 4)
        self.assertNotIn("frame_id", self.progress()["commands"][0])
        self.assertFalse(self.task.record_frame_observed({"provenance": old}))
        self.task.record_observation_wait([self.entry()], dict(session_id="s", lifecycle=1, after_monotonic=10), 2, 3)
        self.assertEqual(self.progress()["commands"][0]["observation_generation"], 3)
        self.assertTrue(self.task.record_frame_observed({"provenance": dict(old, frame_id="later", request_generation=4, acquired_start_monotonic=21)}))
        self.assertEqual(self.progress()["commands"][0]["frame_id"], "later")

    def test_old_task_cannot_modify_new_task_progress(self):
        entry, receipt, delivery = self.entry(), self.receipt(), self.delivery()
        self.task.stop("cancelled")
        self.task.reserve(max_turns=20, max_seconds=120, operator_input=True)
        self.assertFalse(self.task.record_command_admission(entry))
        self.assertFalse(self.task.record_command(receipt))
        self.assertFalse(self.task.record_request_progress(delivery, "responded"))
        self.task.record_observation_wait([entry], dict(session_id="s"), 1, 1)
        self.assertEqual(self.progress()["events_total"], 0)

    def test_duplicates_and_concurrent_receipts_count_once(self):
        self.task.record_command_admission(self.entry())
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.task.record_command(self.receipt()), range(20)))
        self.assertEqual(sum(results), 1)
        self.assertFalse(self.task.record_command_admission(self.entry()))
        self.assertEqual(self.progress()["events_total"], 2)

    def test_terminal_and_out_of_order_phases_cannot_relabel_response(self):
        delivery = self.delivery()
        for phase in ("prepared", "submitted", "cancelled"):
            self.assertTrue(self.task.record_request_progress(delivery, phase))
        for phase in ("prepared", "responded", "nonsense"):
            self.assertFalse(self.task.record_request_progress(delivery, phase))
        row = self.progress()["requests"][0]
        self.assertEqual(row["phase"], "cancelled")
        self.assertIsNone(row["latency_ms"]["submitted_to_response"])
        self.assertEqual(row["latency_ms"]["submitted_to_terminal"], 0)

    def test_invalid_time_is_unknown_never_zero(self):
        for start, end in ((None, 1), (1, None), (2, 1), (False, 1), (0, float("inf")), ("0", 1)):
            self.assertIsNone(_elapsed_ms(start, end))
        self.assertEqual(_elapsed_ms(0, 0), 0)

    def test_retention_eviction_is_explicit_and_prompt_summary_has_no_ledger(self):
        for n in range(70):
            self.task.record_command_admission(self.entry("b" + str(n)))
            self.task.record_request_progress(self.delivery("r" + str(n)), "prepared")
        full, compact = self.progress(), self.task.snapshot()["progress"]
        self.assertEqual((len(full["commands"]), len(full["requests"]), len(full["events"])), (64, 64, 64))
        self.assertEqual((full["batches_evicted"], full["requests_evicted"], full["events_evicted"]), (6, 6, 76))
        self.assertNotIn("commands", compact)
        self.assertNotIn("requests", compact)
        self.assertNotIn("events", compact)
        self.assertLess(len(json.dumps(compact)), 2500)
        self.task.record_command(self.receipt("b0"))
        self.assertIsNone(self.progress()["commands"][-1]["latency_ms"]["admission_to_receipt"])

    def test_snapshots_are_detached_and_do_not_claim_completion(self):
        self.task.record_command(self.receipt())
        snapshot = self.progress()
        snapshot["commands"][0]["status"] = "fabricated"
        self.assertEqual(self.progress()["commands"][0]["status"], "processed")
        self.assertEqual(self.task.snapshot()["status"], "running")
        self.assertIn("not verified task completion", self.progress()["scope"])

    def test_observer_failure_cannot_change_delivery_or_duplicate_request(self):
        logs = []
        def broken(delivery, phase):
            raise RuntimeError("private error")
        with delivery_turn(lambda *args, **row: logs.append(row), [], observer=broken) as turn:
            turn.emit("prepared")
            turn.emit("submitted")
            turn.emit("responded")
        self.assertEqual(turn.phase, "responded")
        self.assertEqual(turn.observer_errors, 4)
        self.assertEqual(turn.receipt_errors, 0)
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
