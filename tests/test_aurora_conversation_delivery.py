import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aurora_conversation_delivery import SessionOutbox, conversation_activity


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-outbox-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.box = SessionOutbox(self.root)

    def receipt(self, record, **overrides):
        value = {key: record[key] for key in ("request_id", "message_id", "client_id")}
        return {**value, "event": "message_ingested", "delivery_status": "routed_as_input", "timestamp": "test-time", **overrides}

    def append(self, *records):
        with self.box.path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")

    def test_received_requires_all_identity_fields_and_never_claims_provider_delivery(self):
        record = self.box.prepare("Identical text is not a delivery identity")
        self.box.track(record)
        self.append(self.receipt(record, client_id="other"), self.receipt(record, message_id="other"),
                    self.receipt(record, request_id="other"), self.receipt(record, event="model_turn", status="success"))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "queued")
        self.append(self.receipt(record))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "received")
        self.assertIn("Model delivery unconfirmed", self.box.summary())
        self.assertNotIn(record["text"], self.box.summary(include_text=False))
        self.assertIn("Received by runtime", self.box.summary(include_text=False))

    def test_uncertain_write_can_be_resolved_by_later_exact_receipt(self):
        record = self.box.prepare("A write can succeed before its caller sees an error")
        self.box.track(record, uncertain=True)
        self.assertIn("Write unconfirmed", self.box.summary())
        self.assertIn("inspect before resending", self.box.summary(include_text=False))
        self.append(self.receipt(record))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "received")

    def test_rejection_partial_tail_and_log_replacement(self):
        record = self.box.prepare("Test")
        self.box.track(record)
        partial = json.dumps(self.receipt(record))
        self.box.path.write_text(partial, encoding="utf-8")
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "queued")
        replacement = self.root / "replacement"
        replacement.write_text(json.dumps(self.receipt(record, event="message_rejected", reason="invalid envelope")) + "\n", encoding="utf-8")
        replacement.replace(self.box.path)
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "rejected")

    def test_unavailable_log_preserves_evidence_and_never_retries_send(self):
        record = self.box.prepare("Test")
        self.box.track(record)
        with patch("aurora_conversation_delivery.read_jsonl_batch", side_effect=PermissionError()):
            self.box.poll()
        self.assertIn("unavailable", self.box.error)
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "queued")

    def test_bounds_disclose_omissions_without_changing_submitted_text(self):
        box = SessionOutbox(self.root, max_rows=2, max_text=5)
        for text in ("first", "second", "third long message"):
            record = box.prepare(text)
            box.track(record)
        self.assertEqual(record["text"], "third long message")
        self.assertEqual(len(box.rows), 2)
        self.assertEqual(box.omitted, 1)
        row = next(reversed(box.rows.values()))
        self.assertTrue(row["shortened"])
        self.assertEqual(row["text"], "third")

    def test_existing_log_is_not_imported_as_new_panel_history(self):
        self.box.path.write_text(json.dumps({"event": "old"}) + "\n", encoding="utf-8")
        box = SessionOutbox(self.root)
        self.assertEqual(box.offset, box.path.stat().st_size)
        self.assertEqual(box.rows, {})

    def model_receipt(self, record, phase, sequence, **overrides):
        fields = dict(event="message_model_delivery", delivery_schema=1,
                      inference_request_id="turn-fixture", sequence=sequence, phase=phase,
                      requested_model="fixture-model")
        fields.update(overrides)
        return self.receipt(record, **fields)

    def test_exact_turn_stages_and_response_remove_waiting_row(self):
        record = self.box.prepare("Waiting message")
        self.box.track(record)
        for number, phase in enumerate(("preparing", "prepared", "submitted", "responded"), 1):
            self.append(self.model_receipt(record, phase, number, request_started=number >= 3,
                                          provider_model="reported-model" if number == 4 else ""))
            self.box.poll()
            self.assertEqual(self.box.rows[record["request_id"]]["phase"], phase)
        self.assertEqual(self.box.awaiting_rows(), [])
        self.assertIn("Response received", self.box.summary())
        self.assertNotIn("unconfirmed", self.box.summary())
        self.assertEqual(self.box.rows[record["request_id"]]["provider_model"], "reported-model")

    def test_cancelled_receipt_survives_duplicate_delayed_and_other_turn_events(self):
        record = self.box.prepare("Cancel fixture")
        self.box.track(record)
        self.append(self.model_receipt(record, "prepared", 2),
                    self.model_receipt(record, "responded", 3, inference_request_id="wrong-turn"),
                    self.model_receipt(record, "submitted", True),
                    self.model_receipt(record, "submitted", 1),
                    self.model_receipt(record, "submitted", 3, delivery_schema=99))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "prepared")
        self.append(self.model_receipt(record, "cancelled", 4, request_started=True),
                    self.receipt(record), self.model_receipt(record, "responded", 5))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "cancelled")
        self.assertEqual(len(self.box.awaiting_rows()), 1)
        self.assertIn("Remote cancellation unconfirmed", self.box.summary())

    def test_failed_turn_has_no_automatic_retry_or_success_inference(self):
        record = self.box.prepare("Failure fixture")
        self.box.track(record)
        self.append(self.model_receipt(record, "failed", 2, reason="Auth error"),
                    self.receipt(record, event="model_turn", status="success"))
        self.box.poll()
        self.assertEqual(self.box.rows[record["request_id"]]["phase"], "failed")
        self.assertIn("inspect before resending", self.box.summary())
        self.assertEqual(len(self.box.rows), 1)

    def test_activity_prioritizes_actual_work_over_paused_inference_and_stale_state(self):
        state = {"processes": {"runtime": {"active": True}}, "modes": {"live": False},
                 "work": {"model_io": {"active_network_calls": 1, "requested_model": "fixture-model", "state": "running", "elapsed_seconds": 2}}}
        self.assertIn("Thinking with fixture-model", conversation_activity(state))
        state["work"]["model_io"]["state"] = "draining"
        self.assertIn("Cancelling", conversation_activity(state))
        self.assertIn("stale", conversation_activity(state, fresh=False))
        state["work"] = {"commands": {"active_scopes": 1}}
        self.assertIn("Running commands · inference paused", conversation_activity(state))
        state["work"] = {}
        self.assertIn("Inference paused", conversation_activity(state))

    def test_activity_reports_approval_capture_failure_queue_and_ready(self):
        state = {"processes": {"runtime": {"active": True}}, "modes": {"live": True}}
        self.assertIn("Ready", conversation_activity(state))
        state["pending_commands"] = [{}]
        self.assertIn("awaiting review", conversation_activity(state))
        state["pending_commands"] = []
        state["scheduler"] = {"demand_capture_pending": True}
        self.assertIn("requested screenshot", conversation_activity(state))
        state["scheduler"] = {}
        state["conversation_io"] = {"last_model_turn_status": "api_error_429"}
        self.assertIn("failed", conversation_activity(state))
        state["conversation_io"] = {"queued_input_count": 2}
        self.assertIn("2 queued", conversation_activity(state))
        state["processes"]["runtime"]["active"] = False
        self.assertIn("Runtime stopped", conversation_activity(state))


if __name__ == "__main__":
    unittest.main()
