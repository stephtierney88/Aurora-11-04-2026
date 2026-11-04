"""Real retrieval functions with disposable files and fake embedding transport only."""
import ast
import datetime
import hashlib
import json
import math
import os
import random
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import aurora_episodic_retrieval as retrieval
import aurora_search_query as search
import aurora_retrieval_results as results
import aurora_retrieval_commands as retrieval_commands
from aurora_runtime_work import CancellationDomain, WorkCancelled
from test_aurora_command_ingress import FUNCTIONS, ROOT


def memory(text="rocket password", **values):
    return {"snapshot_id": "same-id", "summary_text": text, "tags": [],
            "timestamp": "2026-10-16 00:00:00", "source_bucket": "manual", **values}


class PolicyTests(unittest.TestCase):
    def test_legacy_defaults_are_explicit(self):
        result = retrieval.normalize_retrieval_options({})
        self.assertEqual(result["time_mode"], "ordinal")
        self.assertEqual(result["min_relevance"], 0)

    def test_invalid_new_options_rejected(self):
        for options in [{"time_mode": "typo"}, {"min_relevance": "nan"}, {"min_relevance": 2},
                        {"age_half_life_hours": 0}, {"age_half_life_hours": "inf"},
                        {"embedding_fallback": "silent"}, {"time_mode": "age", "time_anchor": "latest"}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                retrieval.normalize_retrieval_options(options)

    def test_coupled_dials_preserve_total_and_relative_other_weights(self):
        weights = retrieval.rebalance_score_weights(retrieval.RETRIEVAL_OPTION_DEFAULTS, "description_weight", .6)
        self.assertAlmostEqual(sum(weights.values()), 1)
        self.assertAlmostEqual(weights["description_weight"], .6)
        self.assertAlmostEqual(weights["keyword_weight"] / weights["rating_weight"], 3)
        pure = retrieval.rebalance_score_weights(weights, "description_weight", 1)
        self.assertEqual(pure["keyword_weight"], 0)
        restored = retrieval.rebalance_score_weights(pure, "description_weight", .4)
        self.assertAlmostEqual(sum(restored.values()), 1)
        self.assertAlmostEqual(restored["keyword_weight"], .2)

    def test_weighted_axes_have_no_hidden_bonus(self):
        for index, key in enumerate(retrieval.RETRIEVAL_WEIGHT_KEYS):
            weights = {name: float(name == key) for name in retrieval.RETRIEVAL_WEIGHT_KEYS}
            parts = retrieval.weighted_score_components(weights, .2, .4, .6, .8)
            self.assertAlmostEqual(sum(parts.values()), (.2, .4, .6, .8)[index])
        with self.assertRaises(ValueError):
            retrieval.normalize_score_weights(dict.fromkeys(retrieval.RETRIEVAL_WEIGHT_KEYS, 0))

    def test_curve_preview_is_same_multiplier_and_bounded_jitter(self):
        for shape in ("balanced", "gaussian", "geometric", "exponential"):
            rows = retrieval.distribution_preview(shape, .4, .3, .2)
            for row in rows:
                self.assertEqual(row["weight"], retrieval.distribution_rank_weight(shape, row["position"], .4, .3))
                self.assertAlmostEqual(row["low"], row["weight"] * .8)
                self.assertAlmostEqual(row["high"], row["weight"] * 1.2)

    def test_age_decay_uses_elapsed_time_and_epoch_precedence(self):
        result = retrieval.age_time_score(memory(created_at_epoch=3600, timestamp="bad"), 3 * 3600, 2)
        self.assertEqual(result, {"time_score": .5, "age_hours": 2.0, "time_source": "created_at_epoch"})

    def test_age_timestamp_offsets_missing_and_future(self):
        epoch = datetime.datetime(2026, 10, 16, tzinfo=datetime.timezone.utc).timestamp()
        for stamp in ["2026-10-16T00:00:00Z", "2026-10-15T17:00:00-07:00"]:
            self.assertEqual(retrieval.age_time_score(memory(timestamp=stamp), epoch, 2)["time_score"], 1)
        self.assertEqual(retrieval.age_time_score(memory(timestamp="bad"), epoch, 2)["time_score"], 0)
        future = retrieval.age_time_score(memory(created_at_epoch=epoch+3600), epoch, 2)
        self.assertEqual(future["time_score"], 1)
        self.assertIn("future_clamped", future["time_source"])

    def test_malformed_record_values_are_bounded(self):
        self.assertIsNone(retrieval.normalize_snapshot_record(None))
        result = retrieval.normalize_snapshot_record(memory(tags="rocket", importance_score="NaN", outcome_score={}))
        self.assertEqual(result["tags"], ["rocket"])
        self.assertEqual(result["importance_score"], 0)
        self.assertEqual(result["outcome_score"], 0)

    def test_duplicate_ids_do_not_alias_different_content(self):
        self.assertNotEqual(retrieval.embedding_record_key(memory("one")), retrieval.embedding_record_key(memory("two")))

    def test_vector_validation_and_index_order(self):
        result = retrieval.parse_embedding_vectors({"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}, 2)
        self.assertEqual(result, [[1, 0], [0, 1]])
        for vector in [[], [0, 0], [float("nan")], [float("inf")], [True], ["oops"]]:
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                retrieval.validated_vector(vector)

    def test_invalid_response_shapes_rejected(self):
        for rows in [[{"index": 0, "embedding": [1]}, {"index": 0, "embedding": [2]}],
                     [{"index": 0, "embedding": [1]}, {"index": 1, "embedding": [1, 2]}],
                     [{"embedding": [1]}, {"index": 1, "embedding": [1]}], []]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                retrieval.parse_embedding_vectors({"data": rows}, 2)

    def test_atomic_cache_failure_preserves_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.json"
            path.write_text('{"old": true}')
            with patch.object(retrieval.os, "replace", side_effect=OSError("fixture")), self.assertRaises(OSError):
                retrieval.atomic_write_cache(path, {"new": True})
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(list(Path(folder).iterdir()), [path])
            retrieval.atomic_write_cache(path, {"new": True})
            self.assertEqual(json.loads(path.read_text()), {"new": True})


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.cache = {}
        self.calls = []
        self.saved = []
        def provider(texts, model):
            self.calls.append(texts)
            return {"ok": True, "vectors": [[1.0, 0.0] for _ in texts]}
        self.provider = provider

    def build(self, records=None, backend="auto", **options):
        return retrieval.build_embedding_context("query", options, records if records is not None else [memory()],
            model="fixture", backend=backend, auth_mode="fixture", truncate=lambda text: str(text)[:6000],
            get_cached=lambda model, text, kind: self.cache.get((kind, text)), request_vectors=self.provider,
            save_entries=lambda model, rows: self.saved.append(rows), check_cancel=options.get("check", lambda: None))

    def test_deduplicated_bounded_batches_and_one_save(self):
        records = [memory(f"text {i}", snapshot_id=str(i), tags=["shared"]) for i in range(130)]
        result = self.build(records)
        self.assertTrue(result["complete"])
        self.assertEqual([len(call) for call in self.calls], [64, 64, 4])
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(result["available_vectors"], 261)
        self.assertEqual(sum(call.count("shared") for call in self.calls), 1)

    def test_identical_records_are_covered_without_duplicate_calls(self):
        result = self.build([memory(), memory()])
        self.assertTrue(result["complete"])
        self.assertEqual(result["required_vectors"], 2)

    def test_off_empty_and_warm_cache_make_no_provider_calls(self):
        self.build(backend="off")
        self.build([])
        self.cache = {("query", "query"): [1, 0], ("summary", "rocket password"): [1, 0]}
        self.assertTrue(self.build()["complete"])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.saved, [])

    def test_force_cannot_succeed_with_only_cached_query(self):
        self.cache[("query", "query")] = [1, 0]
        self.provider = lambda *args: {"ok": False, "error": "fixture failure"}
        result = self.build(backend="force")
        self.assertEqual(result["backend_used"], "embedding_failed")
        self.assertFalse(result["complete"])
        self.assertIsNone(result["query_vector"])

    def test_auto_lexical_and_explicit_partial_are_distinct(self):
        self.cache = {("query", "query"): [1, 0], ("summary", "rocket password"): [1, 0]}
        self.provider = lambda *args: {"ok": False, "error": "fixture failure"}
        lexical = self.build([memory(tags=["missing"])])
        partial = self.build([memory(tags=["missing"])], embedding_fallback="partial")
        self.assertEqual(lexical["backend_used"], "lexical")
        self.assertEqual(lexical["summary_vectors"], {})
        self.assertEqual(partial["backend_used"], "embedding_partial")
        self.assertEqual(len(partial["summary_vectors"]), 1)

    def test_mismatched_cached_dimensions_are_not_scored(self):
        self.cache = {("query", "query"): [1, 0], ("summary", "rocket password"): [1, 0, 0]}
        result = self.build(backend="force")
        self.assertFalse(result["complete"])
        self.assertEqual(result["available_vectors"], 1)

    def test_cache_failure_keeps_valid_result_and_reports_warning(self):
        with patch.object(self, "saved", new=Mock(append=Mock(side_effect=OSError("fixture")))):
            result = self.build()
        self.assertTrue(result["complete"])
        self.assertIn("not saved", result["cache_error"])

    def test_cancellation_is_not_fallback_and_does_not_publish_cache(self):
        token = CancellationDomain().token()
        def provider(*args):
            token.event.set()
            return {"ok": True, "vectors": [[1, 0], [1, 0]]}
        self.provider = provider
        with self.assertRaises(WorkCancelled):
            self.build(check=token.check)
        self.assertEqual(self.saved, [])


RUNTIME_NAMES = """normalize_text_content normalize_memory_item strip_wrapping_quotes summarize_runtime_text
split_option_segments parse_named_option_pairs _parse_named_settings_payload _parse_snapshot_tags_arg
_normalize_episodic_embedding_mode _truncate_episodic_embedding_text _get_episodic_embedding_cache
_save_episodic_embedding_cache _episodic_embedding_cache_key _update_episodic_embedding_cache_entries
_update_episodic_embedding_cache_entry _get_cached_episodic_embedding _get_episodic_embedding_cache_entry_count
_request_openai_text_embeddings _build_episodic_embedding_context _read_episodic_snapshot_records
_dot_product _vector_norm _cosine_similarity _normalize_cosine_similarity
_score_episodic_record_lexical _normalize_retrieval_weight _normalize_retrieval_positive_float
_normalize_retrieval_int _normalize_distribution_shape _normalize_distribution_center _normalize_distribution_spread
_parse_optional_tag_list _parse_optional_source_buckets _build_retrieval_request _normalize_time_anchor_to_percent
_compute_retrieval_time_score _compute_distribution_rank_weight _compute_retrieval_candidate
_select_retrieval_candidates _build_retrieval_state_items run_episodic_retrieval
retrieval_pull_command _execute_retrieval_pull_command _build_retrieval_shorthand_request _format_retrieval_pull_equivalent memory_retrieval_shorthand_command
""".split()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.scope = {"retrieval_commands": retrieval_commands, **vars(retrieval), **vars(search), "math": math, "os": os, "re": re, "random": random,
                      "time": time, "json": json, "datetime": datetime, "hashlib": hashlib,
                      "EPISODIC_MEMORY_EMBEDDINGS_MODE": "off", "EPISODIC_MEMORY_EMBEDDING_MODEL": "fixture",
                      "EPISODIC_MEMORY_EMBEDDING_MAX_INPUT_CHARS": 6000, "EPISODIC_MEMORY_EMBEDDING_TIMEOUT_SECONDS": 10,
                      "EPISODIC_MEMORY_MAX_TAGS": 16, "ALLOWED_EPISODIC_EMBEDDING_MODES": {"off", "auto", "force"},
                      "ALLOWED_RETRIEVAL_DISTRIBUTION_SHAPES": {"balanced", "gaussian", "geometric", "exponential"},
                      "AUTH_MODE": "fixture", "runtime_state": {}, "agent_state": SimpleNamespace(inference_counter=0),
                      "RETRIEVAL_RESULTS": results.RetrievalResultStore(), "RETRIEVAL_PUBLICATION_LOCK": threading.RLock(),
                      "RETRIEVAL_FEEDBACK": search.SearchFeedbackLedger(), "MODEL_WORK": CancellationDomain(), "COMMAND_WORK": CancellationDomain(), "WorkCancelled": WorkCancelled,
                      "episodic_memory_path": str(self.folder / "snapshots.jsonl"),
                      "episodic_embedding_cache_path": str(self.folder / "cache.json"),
                      "episodic_embedding_cache_lock": threading.RLock(), "episodic_embedding_cache_data": None,
                      "write_command_execution_log": Mock(), "display_message": Mock(),
                      "post_openai_embeddings": Mock(side_effect=AssertionError("No provider in fixture"))}
        self.scope["set_runtime_value"] = self.scope["runtime_state"].__setitem__
        exec(compile(ast.Module(body=[FUNCTIONS[name] for name in RUNTIME_NAMES], type_ignores=[]), "aurora2.py", "exec"), self.scope)

    def call(self, name, *args, **kwargs):
        return self.scope[name](*args, **kwargs)

    def request(self, *args):
        return self.call("_build_retrieval_request", ["rocket", *args])

    def write(self, records):
        Path(self.scope["episodic_memory_path"]).write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    def test_zero_semantic_tag_weight_is_text_only(self):
        result = self.call("_compute_retrieval_candidate", memory(), "rocket", self.request("semantic_tag_weight=0"), 0, 1)
        self.assertEqual(result["semantic_score"], 1)

    def test_runtime_weighted_presets_and_result_evidence(self):
        row = memory("rocket", tags=["other"], importance_score=12, confidence_score=1, outcome_score=5)
        for key, expected in (("description_weight", 1), ("keyword_weight", 0), ("recency_weight", .5), ("rating_weight", 1)):
            args = ["score_mode=weighted"] + [f"{name}={int(name == key)}" for name in retrieval.RETRIEVAL_WEIGHT_KEYS]
            result = self.call("_compute_retrieval_candidate", row, "rocket", self.request(*args), 1, 3)
            self.assertEqual(result["weighted_total"], expected)
            self.assertEqual(result["importance_bonus"], 1 if key == "rating_weight" else 0)
            state = self.call("_build_retrieval_state_items", [result])[0]
            self.assertEqual(state["score_mode"], "weighted")
            self.assertAlmostEqual(sum(state["score_contributions"].values()), expected)

    def test_legacy_permissive_and_optional_threshold(self):
        row = memory("irrelevant")
        result = self.call("_compute_retrieval_candidate", row, "rocket", self.request(), 0, 1)
        self.assertEqual(result["weighted_total"], .515)
        self.assertIsNone(self.call("_compute_retrieval_candidate", row, "rocket", self.request("min_relevance=.01"), 0, 1))

    def test_zero_cosine_does_not_pass_relevance_gate(self):
        row = memory("irrelevant")
        context = {"query_vector": [1, 0], "summary_vectors": {retrieval.embedding_record_key(row): [0, 1]}}
        self.assertIsNone(self.call("_compute_retrieval_candidate", row, "rocket", self.request("min_relevance=.01"), 0, 1, context))
        self.assertEqual(self.call("_normalize_cosine_similarity", 0), .5)

    def test_age_mode_changes_time_without_changing_ordinal_default(self):
        row = memory(created_at_epoch=0)
        request = self.request("time_mode=age", "age_half_life_hours=1")
        request["_evaluation_epoch"] = 3600
        self.assertEqual(self.call("_compute_retrieval_candidate", row, "rocket", request, 0, 1)["time_score"], .5)
        self.assertEqual(self.call("_compute_retrieval_candidate", row, "rocket", self.request(), 0, 1)["time_score"], 1)

    def test_shorthand_preserves_every_option_without_reparse_or_rounding(self):
        captured = []
        self.scope["retrieval_pull_command"] = lambda args, is_user, request: captured.append(request) or True
        options = ["rocket", "3", "time_weight=0", "semantic_weight=0", "semantic_tag_weight=0", "time_anchor=early", "time_scale=1.234567", "min_relevance=.123456", "embedding_fallback=partial"]
        self.assertTrue(self.call("memory_retrieval_shorthand_command", options, True))
        result = captured[0]
        self.assertEqual(result["time_weight"], 0)
        self.assertEqual(result["semantic_weight"], 0)
        self.assertEqual(result["semantic_tag_weight"], 0)
        self.assertEqual(result["time_anchor"], "early")
        self.assertEqual(result["time_scale"], 1.234567)
        self.assertEqual(result["min_relevance"], .123456)
        text = self.call("_format_retrieval_pull_equivalent", result)
        self.assertIn("1.234567", text)

    def test_nonfinite_legacy_values_use_defaults(self):
        request = self.request("semantic_weight=nan", "time_weight=inf", "k=inf", "distribution_spread=nan")
        self.assertEqual(request["semantic_weight"], .5)
        self.assertEqual(request["time_weight"], .5)
        self.assertEqual(request["k"], 4)
        self.assertEqual(request["distribution_spread"], .22)

    def test_real_run_filters_before_provider_and_preserves_original_ordinal(self):
        self.write([memory("excluded", tags=["other"]), memory("rocket", tags=["keep"])])
        seen = []
        self.scope["_request_openai_text_embeddings"] = lambda texts, model: seen.extend(texts) or {"ok": True, "vectors": [[1, 0] for _ in texts]}
        result = self.call("run_episodic_retrieval", self.request("semantic_backend=force", "tags_required=keep"))
        self.assertTrue(result["ok"])
        self.assertNotIn("excluded", seen)
        self.assertEqual(result["items"][0]["time_score"], 1)
        self.assertIn("eligible=1/2", result["summary"])

    def test_empty_and_excluded_force_lookup_do_not_call_provider(self):
        self.write([memory(tags=["other"])])
        for request in [self.request("semantic_backend=force", "tags_required=missing")]:
            self.assertTrue(self.call("run_episodic_retrieval", request)["ok"])
        self.write([])
        self.assertTrue(self.call("run_episodic_retrieval", self.request("semantic_backend=force"))["ok"])
        self.scope["post_openai_embeddings"].assert_not_called()

    def test_real_force_failure_with_cached_query(self):
        self.write([memory()])
        self.call("_update_episodic_embedding_cache_entry", "fixture", "rocket", [1, 0], kind="query")
        self.scope["post_openai_embeddings"] = Mock(side_effect=TimeoutError("fixture"))
        result = self.call("run_episodic_retrieval", self.request("semantic_backend=force"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["embedding_context"]["backend_used"], "embedding_failed")
        self.assertEqual(self.scope["runtime_state"]["episodic_memory_last_retrieval_items"], [])

    def test_network_exception_auto_falls_back_but_cancellation_propagates(self):
        self.write([memory()])
        self.scope["post_openai_embeddings"] = Mock(side_effect=TimeoutError("sensitive fixture detail"))
        result = self.call("run_episodic_retrieval", self.request("semantic_backend=auto"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["embedding_context"]["backend_used"], "lexical")
        self.assertNotIn("sensitive", result["embedding_context"]["error"])
        self.scope["post_openai_embeddings"] = Mock(side_effect=WorkCancelled("fixture"))
        with self.assertRaises(WorkCancelled):
            self.call("run_episodic_retrieval", self.request("semantic_backend=auto"))

    def test_cancelled_result_not_published(self):
        self.write([memory()])
        def provider(texts, model):
            self.scope["COMMAND_WORK"].cancel("fixture")
            return {"ok": True, "vectors": [[1, 0] for _ in texts]}
        self.scope["_request_openai_text_embeddings"] = provider
        with self.assertRaises(WorkCancelled):
            self.call("run_episodic_retrieval", self.request("semantic_backend=auto"))
        self.assertNotIn("episodic_memory_last_retrieval_items", self.scope["runtime_state"])
        self.assertFalse(Path(self.scope["episodic_embedding_cache_path"]).exists())

    def test_bad_json_rows_and_ratings_do_not_crash_retrieval(self):
        self.write([None, [], memory(tags=None, importance_score="bad", confidence_score="NaN")])
        result = self.call("run_episodic_retrieval", self.request())
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(math.isfinite(result["items"][0]["weighted_total"]))

    def test_cache_merge_is_atomic_in_memory_and_serialized_across_threads(self):
        self.call("_update_episodic_embedding_cache_entry", "fixture", "old", [1, 0])
        before = json.loads(json.dumps(self.scope["episodic_embedding_cache_data"]))
        with patch.dict(self.scope, atomic_write_cache=Mock(side_effect=OSError("fixture"))), self.assertRaises(OSError):
            self.call("_update_episodic_embedding_cache_entry", "fixture", "new", [0, 1])
        self.assertEqual(before, self.scope["episodic_embedding_cache_data"])
        threads = [threading.Thread(target=self.call, args=("_update_episodic_embedding_cache_entry", "fixture", str(i), [1, 0])) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.call("_get_episodic_embedding_cache_entry_count"), 5)

    def test_large_finite_vectors_do_not_overflow_cosine(self):
        self.assertAlmostEqual(self.call("_cosine_similarity", [1e200, 0], [1e200, 0]), 1)

    def test_panel_preview_and_recall_share_all_visible_options(self):
        tree = ast.parse((ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        names = {"_episodic_retrieval_segments", "send_episodic_retrieval", "send_episodic_recall_shorthand"}
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
        scope = {"retrieval_commands": retrieval_commands, **vars(search), "finite_number": retrieval.finite_number, "json": json, "messagebox": Mock()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "aurora2_control_panel.py", "exec"), scope)
        ui = SimpleNamespace(send_raw=Mock(), after=Mock(), refresh_now=Mock(), episodic_retrieval_status_var=Mock())
        ui.episodic_search_vars = {key: SimpleNamespace(get=lambda v=value: str(v), set=Mock()) for key, value in search.SEARCH_DEFAULTS.items()}
        ui.episodic_score_mode_var = SimpleNamespace(get=lambda: "weighted")
        ui.episodic_score_weights = {key: SimpleNamespace(get=lambda k=key: retrieval.RETRIEVAL_OPTION_DEFAULTS[k]) for key in retrieval.RETRIEVAL_WEIGHT_KEYS}
        values = {"query": "rocket", "limit": "4", "time_weight": "0", "semantic_weight": ".5", "tag_weight": "0",
                  "backend": "off", "embedding_model": "fixture", "shape": "balanced", "center": "0", "spread": ".22", "variance": "0",
                  "tags_required": "", "tags_preferred": "", "source_buckets": "", "time_mode": "age", "age_half_life_hours": "24",
                  "min_relevance": ".1", "semantic_tag_weight": "0", "embedding_fallback": "partial", "time_anchor": "", "time_scale": "1"}
        for key, value in values.items():
            setattr(ui, "episodic_"+key+"_var", SimpleNamespace(get=lambda v=value: v))
        ui._episodic_retrieval_segments = lambda: scope["_episodic_retrieval_segments"](ui)
        scope["send_episodic_retrieval"](ui)
        scope["send_episodic_recall_shorthand"](ui)
        preview, recall = [call.args[0] for call in ui.send_raw.call_args_list]
        self.assertEqual(preview.removeprefix("RETRIEVAL_PULL"), recall.removeprefix("RECALL"))
        self.assertIn('time_mode="age"', preview)
        self.assertIn('semantic_tag_weight="0"', recall)
        self.assertIn('score_mode=weighted', recall)

    def test_visual_draw_is_bounded_and_works_with_legacy_state(self):
        tree = ast.parse((ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        names = {"_refresh_episodic_visuals", "_draw_episodic_score_results"}
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
        scope = {**vars(retrieval), "json": json}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "aurora2_control_panel.py", "exec"), scope)
        canvas = Mock(winfo_width=lambda: 1000, winfo_height=lambda: 220)
        ui = SimpleNamespace(episodic_curve_canvas=canvas, episodic_score_canvas=canvas,
                             episodic_weight_summary=Mock(), episodic_weight_labels={key: Mock() for key in retrieval.RETRIEVAL_WEIGHT_KEYS},
                             episodic_score_weights={key: SimpleNamespace(get=lambda k=key: retrieval.RETRIEVAL_OPTION_DEFAULTS[k]) for key in retrieval.RETRIEVAL_WEIGHT_KEYS})
        for name, value in {"score_mode": "legacy", "shape": "gaussian", "center": "50", "spread": "20", "variance": ".4"}.items():
            setattr(ui, "episodic_"+name+"_var", SimpleNamespace(get=lambda v=value: v))
        scope["_refresh_episodic_visuals"](ui)
        self.assertEqual(canvas.create_polygon.call_count, 1)
        self.assertLess(canvas.create_line.call_count, 10)
        scope["_draw_episodic_score_results"](ui, [{"summary_text": "legacy", "weighted_total": .4, "adjusted_score": .3}] * 24)
        self.assertEqual(len(ui._episodic_visual_results), 8)
        self.assertEqual(canvas.create_rectangle.call_count, 16)


if __name__ == "__main__":
    unittest.main()
