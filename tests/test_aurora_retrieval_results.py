"""Immutable retrieval evidence, direct runtime and panel wiring, without native effects."""
import ast
import datetime
import json
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import aurora_retrieval_results as results
from aurora_command_contracts import validate_command_arguments, command_failure_stops_batch, describe_command_contract
from aurora_runtime_work import WorkCancelled
import test_aurora_episodic_retrieval as fixtures


class StoreTests(unittest.TestCase):
    def publish(self, store, text="one", count=12):
        rows = [{"record": fixtures.memory(text, tags=["tag"]), "adjusted_score": index} for index in range(count)]
        prepared = store.prepare(rows, {"query": text}, {"date_window": {"anchor_epoch": 42}}, "manual")
        return store.publish(prepared), rows

    def test_full_content_paging_and_copy_isolation(self):
        store = results.RetrievalResultStore()
        info, rows = self.publish(store, "long " * 100)
        rows[8]["record"]["summary_text"] = "changed input"
        first = store.read(info["handle"])
        self.assertEqual(first["next_offset"], 8)
        tail = store.read(info["handle"], 8)
        self.assertEqual(len(tail["items"]), 4)
        self.assertEqual(tail["items"][0]["item_index"], 9)
        self.assertEqual(tail["items"][0]["candidate"]["record"]["summary_text"], "long " * 100)
        tail["items"][0]["candidate"]["record"]["tags"].append("mutate copy")
        item, digest = store.item(info["handle"], 9)
        self.assertEqual(item["candidate"]["record"]["tags"], ["tag"])
        self.assertEqual(digest, info["content_sha256"])
        self.assertEqual(first["search"]["date_window"]["anchor_epoch"], 42)

    def test_duplicate_snapshot_ids_keep_distinct_record_identity(self):
        store = results.RetrievalResultStore()
        a, _ = self.publish(store, "one", 1)
        b, _ = self.publish(store, "two", 1)
        self.assertNotEqual(store.item(a["handle"], 1)[0]["record_sha256"], store.item(b["handle"], 1)[0]["record_sha256"])

    def test_expiry_capacity_restart_and_reads_do_not_refresh(self):
        now = [0]
        store = results.RetrievalResultStore(max_batches=2, ttl_seconds=10, clock=lambda: now[0])
        a, _ = self.publish(store)
        now[0] = 5
        store.read(a["handle"])
        b, _ = self.publish(store)
        c, _ = self.publish(store)
        with self.assertRaisesRegex(ValueError, "unavailable"): store.read(a["handle"])
        now[0] = 15
        with self.assertRaises(ValueError): store.read(b["handle"])
        self.assertEqual(store.bytes_used, 0)
        with self.assertRaises(ValueError): results.RetrievalResultStore().read(c["handle"])

    def test_byte_cap_and_bad_preparation_do_not_destroy_previous(self):
        store = results.RetrievalResultStore(max_bytes=4000, max_batch_bytes=3000)
        a, _ = self.publish(store, count=1)
        with self.assertRaises(ValueError): self.publish(store, "x" * 5000, 1)
        with self.assertRaises(ValueError): store.publish(b'{}')
        self.assertEqual(store.read(a["handle"])["returned_count"], 1)
        self.publish(store, "b" * 1000, 1)
        self.publish(store, "c" * 1000, 1)
        self.assertLessEqual(store.bytes_used, 4000)
        with self.assertRaises(ValueError): store.read(a["handle"])

    def test_empty_and_invalid_page_boundaries(self):
        store = results.RetrievalResultStore()
        empty, _ = self.publish(store, count=0)
        self.assertEqual(store.read(empty["handle"])["items"], [])
        for offset, limit in [(1, 8), (-1, 8), (0, 0), (0, 25), (0.2, 8)]:
            with self.assertRaises(ValueError): store.read(empty["handle"], offset, limit)
        with self.assertRaises(ValueError): store.item(empty["handle"], 1)

    def test_concurrent_readers_and_publishers_keep_exact_handles(self):
        store = results.RetrievalResultStore(max_batches=32)
        def work(index):
            info, _ = self.publish(store, str(index), 1)
            return store.item(info["handle"], 1)[0]["candidate"]["record"]["summary_text"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(work, range(24))), [str(i) for i in range(24)])

    def test_contracts_share_validation_and_failures_stop_batch(self):
        handle = "rr_" + "a" * 32
        for command, args in [("SHOW_RETRIEVAL_RESULT", [handle, "8", "24"]),
                              ("PROMOTE_EPISODIC_MEMORY", ["9.0", "note", "prefix", handle])]:
            validate_command_arguments(command, args)
            self.assertTrue(command_failure_stops_batch(command))
            self.assertEqual(describe_command_contract(command)["parameter_validation"], "pre_dispatch")
        for command, args in [("SHOW_RETRIEVAL_RESULT", []), ("SHOW_RETRIEVAL_RESULT", ["latest"]),
                              ("PROMOTE_EPISODIC_MEMORY", ["1.5", "notes"]), ("PROMOTE_EPISODIC_MEMORY", ["0", "notes"]),
                              ("PROMOTE_EPISODIC_MEMORY", ["1", "nonsense"]),
                              ("PROMOTE_EPISODIC_MEMORY", ["1", "notes", "", ""]),
                              ("PROMOTE_EPISODIC_MEMORY", ["NaN", "notes"])]:
            with self.assertRaises(ValueError): validate_command_arguments(command, args)


class RuntimeResultTests(unittest.TestCase):
    call = fixtures.RuntimeTests.call
    request = fixtures.RuntimeTests.request
    write = fixtures.RuntimeTests.write

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.scope.update(vars(results))
        self.scope["datetime"] = datetime
        self.scope["agent_state"] = SimpleNamespace(inference_counter=0, notes=[], journal_entries=[],
            recent_context_events=[], pinned_immediate_actions=[], pinned_short_term_actions=[], overarching_goals=[])
        self.scope.update(apriority_tasks=[], EPISODIC_PROMOTION_TARGET_ALIASES=results.PROMOTION_TARGET_ALIASES,
            EPISODIC_PROMOTION_TARGETS=tuple(set(results.PROMOTION_TARGET_ALIASES.values())),
            EPISODIC_PROMOTION_TARGET_LABELS={}, MAX_NOTES=20, MAX_ROUTE_ITEMS=20)
        self.scope["append_memory_store"] = lambda target, rows, limit=None: target.extend(row for row in rows if row not in target)
        names = "_normalize_episodic_promotion_target _get_last_episodic_retrieval_items _build_episodic_promotion_text _episodic_promotion_target_state promote_episodic_retrieval_item promote_episodic_memory_command show_retrieval_result_command".split()
        exec(compile(ast.Module(body=[fixtures.FUNCTIONS[name] for name in names], type_ignores=[]), "aurora2.py", "exec"), self.scope)
        self.write([fixtures.memory(f"rocket item {i}: " + "full detail " * 30, created_at_epoch=i) for i in range(12)])

    def search(self, **options):
        return self.call("run_episodic_retrieval", {**self.request("k=12", "sort=oldest", "result_mode=retained"), **options})

    def test_retained_item_beyond_preview_uses_original_full_record(self):
        original = self.search()
        handle = original["search"]["retained_result"]["handle"]
        self.assertEqual(len(self.scope["runtime_state"]["episodic_memory_last_retrieval_items"]), 8)
        expected = original["items"][8]["record"]["summary_text"].strip()
        self.write([fixtures.memory("replacement query")])
        self.search()
        receipt = self.call("promote_episodic_memory_command", ["9", "notes", "", handle], True)
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["summary"], expected)
        self.assertEqual(receipt["selection_mode"], "retained")
        self.assertNotEqual(receipt["before"], receipt["after"])
        self.assertEqual(self.scope["agent_state"].notes, [expected])
        again = self.call("promote_episodic_memory_command", ["9", "notes", "", handle], True)
        self.assertEqual(again["effect_status"], "unchanged")

    def test_legacy_default_has_no_store_and_preserves_preview_text(self):
        result = self.search(result_mode="legacy")
        self.assertIsNone(result["search"]["retained_result"])
        self.assertEqual(self.scope["RETRIEVAL_RESULTS"].bytes_used, 0)
        expected = self.scope["runtime_state"]["episodic_memory_last_retrieval_items"][0]["summary_text"]
        receipt = self.call("promote_episodic_memory_command", ["1", "notes"], True)
        self.assertEqual(receipt["summary"], expected)
        self.assertEqual(receipt["selection_mode"], "legacy_preview")
        self.assertFalse(self.call("promote_episodic_memory_command", ["9", "notes"], True)["success"])

    def test_unavailable_handle_and_cancel_have_no_memory_effect(self):
        handle = self.search()["search"]["retained_result"]["handle"]
        self.scope["RETRIEVAL_RESULTS"] = results.RetrievalResultStore()
        receipt = self.call("promote_episodic_memory_command", ["1", "notes", "", handle], True)
        self.assertFalse(receipt["success"])
        self.assertEqual(self.scope["agent_state"].notes, [])
        with self.scope["COMMAND_WORK"].scope():
            self.scope["COMMAND_WORK"].cancel("fixture")
            with self.assertRaises(WorkCancelled): self.call("promote_episodic_memory_command", ["1", "notes"], True)
        self.assertEqual(self.scope["agent_state"].notes, [])

    def test_failed_retention_and_cancel_do_not_publish_or_commit_feedback(self):
        previous = self.search(feedback_mode="skip")
        before = json.dumps(self.scope["runtime_state"], sort_keys=True)
        self.scope["RETRIEVAL_RESULTS"].max_batch_bytes = 10
        failed = self.search(feedback_mode="skip", feedback_action="reject_last", feedback_token=previous["search"]["feedback"]["token"])
        self.assertFalse(failed["ok"])
        self.assertEqual(json.dumps(self.scope["runtime_state"], sort_keys=True), before)
        self.scope["RETRIEVAL_RESULTS"].max_batch_bytes = 1024 * 1024
        self.assertEqual(self.search(feedback_mode="skip")["items"][0]["record"], previous["items"][0]["record"])
        original = self.scope["_build_episodic_embedding_context"]
        def cancel(*args, **kwargs):
            value = original(*args, **kwargs)
            self.scope["COMMAND_WORK"].cancel("fixture")
            return value
        count = len(self.scope["RETRIEVAL_RESULTS"].entries)
        self.scope["_build_episodic_embedding_context"] = cancel
        with self.assertRaises(WorkCancelled): self.search()
        self.assertEqual(len(self.scope["RETRIEVAL_RESULTS"].entries), count)

    def test_inspection_has_full_page_no_provider_and_reports_failure(self):
        handle = self.search()["search"]["retained_result"]["handle"]
        receipt = self.call("show_retrieval_result_command", [handle, "8", "4"], True)
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["page"]["items"][0]["item_index"], 9)
        self.scope["post_openai_embeddings"].assert_not_called()
        self.assertFalse(self.call("show_retrieval_result_command", ["rr_" + "0" * 32], True)["success"])

    def test_mutation_exception_reports_uncertainty_and_keeps_evidence(self):
        self.search()
        def fail(target, rows, **kwargs):
            target.extend(rows)
            raise OSError("fixture")
        self.scope["append_memory_store"] = fail
        receipt = self.call("promote_episodic_memory_command", ["1", "notes"], True)
        self.assertEqual(receipt["effect_status"], "uncertain")
        self.assertEqual(len(self.scope["agent_state"].notes), 1)


class SnapshotIdentityTests(unittest.TestCase):
    def test_same_second_snapshots_are_distinct_without_changing_old_records(self):
        fixed = datetime.datetime(2026, 11, 4, 12)
        scope = {"datetime": SimpleNamespace(datetime=SimpleNamespace(now=lambda: fixed)), "uuid": uuid,
                 "hashlib": fixtures.hashlib, "COMMAND_LOG_SESSION_ID": "test",
                 "agent_state": SimpleNamespace(route_state={}), "runtime_state": {},
                 "build_episodic_snapshot_summary": lambda: "same content", "normalize_text_content": str,
                 "normalize_memory_item": str, "summarize_runtime_text": lambda text, **_: text,
                 "sanitize_sensitive_payload": lambda value: value, "_build_episodic_snapshot_tags": lambda **_: [],
                 "_estimate_episodic_snapshot_importance": lambda **_: 1, "_estimate_episodic_snapshot_confidence": lambda: 1,
                 "_estimate_episodic_snapshot_outcome": lambda: 1, "get_active_game_profile": lambda: "fixture"}
        exec(compile(ast.Module(body=[fixtures.FUNCTIONS["build_episodic_snapshot_record"]], type_ignores=[]), "runtime", "exec"), scope)
        a, b = scope["build_episodic_snapshot_record"](), scope["build_episodic_snapshot_record"]()
        self.assertEqual(a["timestamp"], b["timestamp"])
        self.assertNotEqual(a["snapshot_id"], b["snapshot_id"])


class PanelResultTests(unittest.TestCase):
    def test_explicit_handle_forwarding_inspection_and_legacy_blank(self):
        tree = ast.parse((fixtures.ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        names = {"send_episodic_promotion", "use_displayed_retrieval_handle", "inspect_retained_retrieval"}
        scope = {"json": json, "messagebox": Mock(), "parse_retrieval_result_arguments": results.parse_retrieval_result_arguments}
        exec(compile(ast.Module(body=[n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), "panel", "exec"), scope)
        handle = ["rr_" + "a" * 32]
        ui = SimpleNamespace(episodic_result_handle_var=SimpleNamespace(get=lambda: handle[0], set=lambda v: handle.__setitem__(0, v)),
            episodic_promote_index_var=SimpleNamespace(get=lambda: "9"), episodic_promote_target_var=SimpleNamespace(get=lambda: "notes"),
            episodic_promote_prefix_var=SimpleNamespace(get=lambda: "prefix"), episodic_promotion_status_var=Mock(),
            send_raw=Mock(), after=Mock(), refresh_now=Mock(), _episodic_displayed_result_handle="rr_" + "b" * 32)
        scope["send_episodic_promotion"](ui)
        self.assertIn(handle[0], ui.send_raw.call_args[0][0])
        scope["inspect_retained_retrieval"](ui)
        self.assertIn("0, 24", ui.send_raw.call_args[0][0])
        scope["use_displayed_retrieval_handle"](ui)
        self.assertEqual(handle[0], ui._episodic_displayed_result_handle)
        handle[0] = ""
        scope["send_episodic_promotion"](ui)
        self.assertEqual(ui.send_raw.call_args[0][0], 'PROMOTE_EPISODIC_MEMORY("9", "notes", "prefix")')
        handle[0] = "invalid"
        ui.send_raw.reset_mock()
        scope["send_episodic_promotion"](ui)
        ui.send_raw.assert_not_called()
        scope["messagebox"].showerror.assert_called_once()


if __name__ == "__main__":
    unittest.main()
