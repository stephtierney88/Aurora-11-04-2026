import ast
import json
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aurora_control_plane import (
    COMMAND_RECEIPT_SCHEMA_VERSION,
    MUTATION_ADMISSION_SCHEMA_VERSION,
    MutationAdmissionJournal,
    append_bridge_request,
    append_jsonl_record,
    build_operator_dashboard,
    build_mutation_decision_receipt,
    collect_command_receipts,
    control_plane_paths,
    extract_request_identity,
    format_operator_dashboard,
    journal_offsets,
    mutation_admission_id,
    mutation_command_digest,
    read_jsonl_from,
    wait_for_command_receipt,
)


class AuroraControlPlaneTests(unittest.TestCase):
    def test_append_bridge_request_writes_correlated_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record = append_bridge_request(
                temp_dir,
                "SHOW_RUNTIME()",
                raw=True,
                source="test_client",
                client_id="test_client",
                request_id="request-123",
                metadata={
                    "request_id": "stale-request",
                    "message_id": "stale-message",
                    "client_id": "stale-client",
                },
            )
            paths = control_plane_paths(temp_dir)
            written = json.loads(paths["inbox"].read_text(encoding="utf-8"))

            self.assertEqual(record["request_id"], "request-123")
            self.assertEqual(written["request_id"], "request-123")
            self.assertEqual(written["metadata"]["request_id"], "request-123")
            self.assertEqual(written["metadata"]["message_id"], written["message_id"])
            self.assertEqual(written["metadata"]["client_id"], "test_client")
            self.assertEqual(written["metadata"]["ingest_mode"], "raw")
            self.assertNotEqual(written["message_id"], written["request_id"])

    def test_wait_for_receipt_ignores_unrelated_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            offsets = journal_offsets(temp_dir)
            append_jsonl_record(
                paths["command_log"],
                {"event": "command_result", "request_id": "other", "status": "processed"},
            )
            append_jsonl_record(
                paths["command_log"],
                {
                    "event": "command_result",
                    "request_id": "request-456",
                    "message_id": "message-456",
                    "status": "processed",
                },
            )

            receipt = wait_for_command_receipt(
                temp_dir,
                "request-456",
                offsets=offsets,
                timeout_seconds=0.1,
            )

            self.assertEqual(receipt["request_id"], "request-456")
            self.assertEqual(receipt["status"], "processed")
            self.assertEqual(receipt["receipt_schema_version"], COMMAND_RECEIPT_SCHEMA_VERSION)
            self.assertTrue(receipt["terminal"])

    def test_incremental_reader_retries_partial_tail_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "journal.jsonl"
            path.write_text('{"event":"command_', encoding="utf-8")

            rows, offset = read_jsonl_from(path, 0)
            self.assertEqual(rows, [])
            self.assertEqual(offset, 0)

            with path.open("a", encoding="utf-8") as handle:
                handle.write('result","request_id":"request-tail"}\n')

            rows, offset = read_jsonl_from(path, offset)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["request_id"], "request-tail")
            self.assertEqual(offset, path.stat().st_size)

    def test_receipt_wait_and_lookup_respect_client_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            for client_id in ("other_client", "aurora_cli"):
                append_jsonl_record(paths["command_log"], {
                    "event": "command_result", "client_id": client_id,
                    "request_id": "shared-id", "status": "processed",
                })
            receipt = wait_for_command_receipt(
                temp_dir, "shared-id", client_id="aurora_cli", timeout_seconds=0,
            )
            rows = collect_command_receipts(
                temp_dir, request_id="shared-id", client_id="aurora_cli",
            )
            self.assertEqual(receipt["client_id"], "aurora_cli")
            self.assertEqual([row["client_id"] for row in rows], ["aurora_cli"])
            self.assertEqual(len(collect_command_receipts(temp_dir, request_id="shared-id")), 2)

    def test_receipt_wait_ignores_other_clients_bridge_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            for event in ("message_rejected", "message_ingested"):
                append_jsonl_record(paths["bridge_log"], {
                    "event": event, "client_id": "other_client",
                    "request_id": "shared-id", "dispatched_as_command": True,
                })
            receipt = wait_for_command_receipt(
                temp_dir, "shared-id", client_id="aurora_cli", timeout_seconds=0,
            )
            self.assertEqual(receipt["status"], "queued")
            self.assertEqual(receipt["client_id"], "aurora_cli")

    def test_receipt_wait_supports_legacy_identity_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            append_jsonl_record(control_plane_paths(temp_dir)["command_log"], {
                "event": "command_result", "source": "legacy_client",
                "message_id": "legacy-request", "status": "processed",
            })
            receipt = wait_for_command_receipt(
                temp_dir, "legacy-request", client_id="legacy_client", timeout_seconds=0,
            )
            self.assertEqual(receipt["status"], "processed")

    def test_control_panel_receipt_worker_respects_client_identity(self):
        source = Path(__file__).resolve().parents[1] / "aurora2_control_panel.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == "_wait_for_settings_transaction_receipt")
        with tempfile.TemporaryDirectory() as temp_dir:
            for client in ("other_client", "aurora_control_panel"):
                append_jsonl_record(control_plane_paths(temp_dir)["command_log"], {
                    "event": "command_result", "client_id": client,
                    "request_id": "panel-request", "status": "processed",
                })
            scope = {"ROOT": temp_dir, "wait_for_command_receipt": wait_for_command_receipt}
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), scope)
            panel = SimpleNamespace(settings_transaction_result_queue=queue.Queue())
            scope[method.name](panel, "panel-request", {}, "aurora_control_panel")
            result = panel.settings_transaction_result_queue.get_nowait()
            self.assertEqual(result["error"], "")
            self.assertEqual(result["receipt"]["client_id"], "aurora_control_panel")

    def test_wait_reports_raw_text_routed_as_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            offsets = journal_offsets(temp_dir)
            append_jsonl_record(
                paths["bridge_log"],
                {
                    "event": "message_ingested",
                    "request_id": "request-789",
                    "message_id": "message-789",
                    "dispatched_as_command": False,
                },
            )

            receipt = wait_for_command_receipt(
                temp_dir,
                "request-789",
                offsets=offsets,
                timeout_seconds=0.1,
            )

            self.assertEqual(receipt["status"], "routed_as_input")
            self.assertEqual(receipt["outcome_status"], "not_dispatched")
            self.assertTrue(receipt["terminal"])

    def test_wait_reports_bridge_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            offsets = journal_offsets(temp_dir)
            append_jsonl_record(
                paths["bridge_log"],
                {
                    "event": "message_rejected",
                    "request_id": "request-rejected",
                    "message_id": "message-rejected",
                    "reason": "operator authorization required",
                },
            )

            receipt = wait_for_command_receipt(
                temp_dir,
                "request-rejected",
                offsets=offsets,
                timeout_seconds=0.1,
            )

            self.assertEqual(receipt["status"], "rejected")
            self.assertEqual(receipt["delivery_status"], "rejected")
            self.assertTrue(receipt["terminal"])

    def test_identity_falls_back_to_message_id_for_legacy_records(self):
        identity = extract_request_identity(
            {"message_id": "legacy-message", "source": "legacy_client"}
        )
        self.assertEqual(identity["request_id"], "legacy-message")
        self.assertEqual(identity["client_id"], "legacy_client")

    def test_request_filtered_receipts_search_beyond_recent_tail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            command_log = control_plane_paths(temp_dir)["command_log"]
            append_jsonl_record(
                command_log,
                {"event": "command_result", "request_id": "older-target", "status": "processed"},
            )
            for index in range(250):
                append_jsonl_record(
                    command_log,
                    {"event": "command_result", "request_id": f"other-{index}", "status": "processed"},
                )

            rows = collect_command_receipts(
                temp_dir,
                request_id="older-target",
                limit=1,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["request_id"], "older-target")

    def test_dashboard_uses_structured_sanitized_receipt_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = control_plane_paths(temp_dir)
            paths["state"].write_text(
                json.dumps(
                    {
                        "timestamp": "2026-08-08 12:00:00",
                        "session_id": "dashboard-test",
                        "runtime_summary": "offline dashboard test",
                        "modes": {
                            "auth": "api_key",
                            "live": False,
                            "execution": "safe",
                            "action": "none",
                            "game_profile": "firered",
                        },
                        "models": {
                            "text": "gpt-test",
                            "vision": "gpt-test",
                            "reasoning": "gpt-test",
                            "reasoning_effort": "low",
                            "verbosity": "low",
                        },
                        "scheduler": {"profile": "balanced", "mode": "hybrid"},
                        "monitors": {"overall_status": "ok", "summary": "all checks passed"},
                        "queue_bridge": {
                            "pending_count": 0,
                            "bridge_caught_up": True,
                            "command_result_caught_up": True,
                        },
                        "mutation_admission": {
                            "reserved_count": 1,
                            "terminal_count": 1,
                            "uncertain_count": 0,
                            "no_automatic_replay": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            append_jsonl_record(
                paths["command_log"],
                {
                    "event": "command_result",
                    "timestamp": "2026-08-08 12:00:01",
                    "request_id": "dashboard-request",
                    "client_id": "dashboard-client",
                    "command": 'SET_OPERATOR_PASSCODE("top-secret")',
                    "status": "processed",
                    "delivery_status": "completed",
                    "terminal": True,
                },
            )

            dashboard = build_operator_dashboard(temp_dir, event_limit=3)
            rendered = format_operator_dashboard(dashboard)
            serialized = json.dumps(dashboard)

            self.assertEqual(dashboard["schema_version"], "aurora_operator_dashboard_v1")
            self.assertEqual(dashboard["events"]["count"], 1)
            self.assertEqual(dashboard["events"]["rows"][0]["command_name"], "SET_OPERATOR_PASSCODE")
            self.assertNotIn("command", dashboard["events"]["rows"][0])
            self.assertNotIn("top-secret", serialized)
            self.assertNotIn("top-secret", rendered)
            self.assertEqual(dashboard["settings"]["count"], 39)
            self.assertEqual(dashboard["settings"]["scope"], "runtime_session")
            self.assertEqual(dashboard["settings"]["writable_count"], 0)
            self.assertFalse(dashboard["summary"]["automatic_replay"])

    def test_mutation_admission_reserves_identity_before_terminal_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir, session_id="test-session")
            decision = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-admit",
                message_id="message-one",
                command_name="SET_LIVE",
            )

            self.assertEqual(decision["decision"], "admitted")
            self.assertFalse(decision["duplicate_suppressed"])
            self.assertEqual(
                decision["admission_id"],
                mutation_admission_id("test-client", "request-admit"),
            )
            rows, _ = read_jsonl_from(control_plane_paths(temp_dir)["mutation_log"], 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "mutation_admitted")
            self.assertEqual(rows[0]["command_digest"], mutation_command_digest("SET_LIVE(on)"))
            self.assertEqual(rows[0]["schema_version"], MUTATION_ADMISSION_SCHEMA_VERSION)
            self.assertEqual(journal.summary()["uncertain_count"], 1)

    def test_duplicate_mutation_without_terminal_result_is_uncertain_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-uncertain",
                message_id="message-one",
            )

            decision = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-uncertain",
                message_id="message-two",
            )
            receipt = build_mutation_decision_receipt(
                decision,
                command="SET_LIVE(on)",
                source="test",
                message_id="message-two",
            )

            self.assertEqual(decision["decision"], "duplicate_uncertain")
            self.assertTrue(decision["duplicate_suppressed"])
            self.assertFalse(decision["replay_attempted"])
            self.assertEqual(receipt["status"], "uncertain")
            self.assertFalse(receipt["terminal"])
            self.assertFalse(receipt["replayed"])
            rows, _ = read_jsonl_from(control_plane_paths(temp_dir)["mutation_log"], 0)
            self.assertEqual(len(rows), 1)

    def test_reused_mutation_identity_with_changed_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-conflict",
            )

            decision = journal.reserve(
                "SET_LIVE(off)",
                client_id="test-client",
                request_id="request-conflict",
                message_id="message-conflict",
            )
            receipt = build_mutation_decision_receipt(
                decision,
                command="SET_LIVE(off)",
                source="test",
                message_id="message-conflict",
            )

            self.assertEqual(decision["decision"], "request_conflict")
            self.assertEqual(receipt["status"], "request_conflict")
            self.assertEqual(receipt["delivery_status"], "rejected")
            self.assertTrue(receipt["terminal"])

            append_jsonl_record(
                control_plane_paths(temp_dir)["command_log"],
                {"event": "command_result", **receipt},
            )
            restarted = MutationAdmissionJournal(temp_dir)
            original = restarted.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-conflict",
                message_id="message-original-retry",
            )
            self.assertEqual(original["decision"], "duplicate_uncertain")

    def test_duplicate_mutation_returns_prior_terminal_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            admitted = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-terminal",
                message_id="message-one",
            )
            terminal = {
                "event": "command_result",
                "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
                "receipt_id": "receipt-request-terminal",
                "request_id": "request-terminal",
                "message_id": "message-one",
                "client_id": "test-client",
                "command": "SET_LIVE(on)",
                "status": "processed",
                "outcome_status": "processed",
                "delivery_status": "completed",
                "terminal": True,
                "mutation_admission_id": admitted["admission_id"],
                "command_digest": admitted["command_digest"],
                "settings_transaction_receipts": [{"transaction_id": "settings-one"}],
            }
            self.assertTrue(journal.record_terminal(terminal))

            decision = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-terminal",
                message_id="message-two",
            )
            receipt = build_mutation_decision_receipt(
                decision,
                command="SET_LIVE(on)",
                source="test",
                message_id="message-two",
            )

            self.assertEqual(decision["decision"], "duplicate_terminal")
            self.assertEqual(receipt["status"], "processed")
            self.assertEqual(receipt["delivery_status"], "duplicate_suppressed")
            self.assertTrue(receipt["terminal"])
            self.assertEqual(receipt["original_message_id"], "message-one")
            self.assertEqual(
                receipt["settings_transaction_receipts"],
                [{"transaction_id": "settings-one"}],
            )

    def test_restart_recovers_terminal_result_from_command_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            admitted = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-restart",
                message_id="message-one",
            )
            append_jsonl_record(
                control_plane_paths(temp_dir)["command_log"],
                {
                    "event": "command_result",
                    "receipt_id": "receipt-request-restart-wrong-digest",
                    "request_id": "request-restart",
                    "message_id": "message-wrong-digest",
                    "client_id": "test-client",
                    "command": "SET_LIVE(off)",
                    "status": "processed",
                    "terminal": True,
                    "mutation_admission_id": admitted["admission_id"],
                    "command_digest": mutation_command_digest("SET_LIVE(off)"),
                },
            )
            append_jsonl_record(
                control_plane_paths(temp_dir)["command_log"],
                {
                    "event": "command_result",
                    "receipt_id": "receipt-request-restart",
                    "request_id": "request-restart",
                    "message_id": "message-one",
                    "client_id": "test-client",
                    "command": "SET_LIVE(on)",
                    "status": "processed",
                    "terminal": True,
                    "mutation_admission_id": admitted["admission_id"],
                    "command_digest": admitted["command_digest"],
                },
            )

            restarted = MutationAdmissionJournal(temp_dir, session_id="restarted")
            decision = restarted.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-restart",
                message_id="message-two",
            )

            self.assertEqual(decision["decision"], "duplicate_terminal")
            self.assertEqual(decision["terminal_receipt"]["status"], "processed")
            self.assertEqual(restarted.summary()["terminal_count"], 1)

    def test_same_request_id_from_different_clients_is_independent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            first = journal.reserve(
                "SET_LIVE(on)",
                client_id="client-one",
                request_id="shared-request",
            )
            second = journal.reserve(
                "SET_LIVE(on)",
                client_id="client-two",
                request_id="shared-request",
            )

            self.assertEqual(first["decision"], "admitted")
            self.assertEqual(second["decision"], "admitted")
            self.assertNotEqual(first["admission_id"], second["admission_id"])
            self.assertEqual(journal.summary()["reserved_count"], 2)

    def test_rejected_mutation_identity_returns_same_terminal_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            journal = MutationAdmissionJournal(temp_dir)
            rejected = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-rejected-mutation",
                message_id="message-one",
                admitted=False,
                reason="operator session locked",
            )
            terminal = {
                "event": "command_result",
                "receipt_id": "receipt-request-rejected-mutation",
                "request_id": "request-rejected-mutation",
                "message_id": "message-one",
                "client_id": "test-client",
                "command": "SET_LIVE(on)",
                "status": "rejected",
                "delivery_status": "rejected",
                "terminal": True,
                "mutation_admission_id": rejected["admission_id"],
                "command_digest": rejected["command_digest"],
            }
            self.assertTrue(journal.record_terminal(terminal))

            duplicate = journal.reserve(
                "SET_LIVE(on)",
                client_id="test-client",
                request_id="request-rejected-mutation",
                message_id="message-two",
                admitted=True,
            )

            self.assertEqual(rejected["decision"], "rejected")
            self.assertEqual(duplicate["decision"], "duplicate_terminal")
            self.assertEqual(duplicate["terminal_receipt"]["status"], "rejected")
            self.assertEqual(journal.summary()["rejected_count"], 1)


if __name__ == "__main__":
    unittest.main()
