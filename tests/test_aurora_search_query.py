"""Search grammar, date boundaries and actual runtime integration; no native/API I/O."""
import ast
import datetime as dt
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import aurora_search_query as search
from aurora_command_protocol import CommandSyntaxError, split_command_batch
from aurora_runtime_work import WorkCancelled
import test_aurora_episodic_retrieval as fixtures


def matches(text, expression, mode="boolean", **values):
    compiled = search.compile_search_filter({"text_filter": expression, "text_mode": mode, **values})
    return search.match_search_filter(fixtures.memory(text), compiled) is not None


class SearchPolicyTests(unittest.TestCase):
    def test_literal_word_phrase_are_distinct_and_case_insensitive(self):
        self.assertTrue(matches("Passworded rocket", "WORD", "literal"))
        self.assertFalse(matches("Passworded rocket", "word", "word"))
        self.assertTrue(matches("The SECRET key!", "secret key", "phrase"))
        self.assertFalse(matches("secret keys", "secret key", "phrase"))
        self.assertFalse(matches("secret very key", "secret key", "phrase"))
        self.assertTrue(matches("literal a*b", "a*b", "word"))
        self.assertFalse(matches("literal ab", "a*b", "word"))
        self.assertTrue(matches("STRASSE", "Straße", "literal"))

    def test_boolean_precedence_groups_negation_and_cross_field_matches(self):
        self.assertTrue(matches("alpha", "alpha OR beta AND gamma"))
        self.assertFalse(matches("alpha", "(alpha OR beta) AND gamma"))
        self.assertTrue(matches("rocket secret key", '(rocket OR badge) AND "secret key" AND NOT failed'))
        self.assertFalse(matches("rocket secret key failed", '(rocket OR badge) AND "secret key" AND NOT failed'))
        self.assertTrue(matches("rocket", "NOT NOT rocket"))
        compiled = search.compile_search_filter({"text_filter": "rocket AND victory", "text_mode": "boolean"})
        match = search.match_search_filter(fixtures.memory("rocket", tags=["victory"]), compiled)
        self.assertIn("combined summary/tags", match["reasons"][0])

    def test_boolean_errors_and_bounds(self):
        for expression in ["alpha beta", "alpha AND", "AND alpha", "(alpha", "alpha)", '"unclosed',
                           '""', "()", "NOT", "alpha OR OR beta", "x\\", "(" * 18 + "x" + ")" * 18,
                           " OR ".join(["x"] * 70), "x" * 2049]:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                search.compile_text_filter(expression, "boolean")

    def test_wildcards_and_escaping(self):
        self.assertTrue(matches("rocket rockit", "rock?t", "wildcard"))
        self.assertTrue(matches("team rocket", "rock*", "wildcard"))
        self.assertFalse(matches("team rock et", "rock*t", "wildcard"))
        self.assertTrue(matches("literal * a?b", r"\* AND a\?b"))
        self.assertFalse(matches("literal abc", r"\*"))
        self.assertTrue(matches("AND", '"AND"'))
        self.assertTrue(matches("AND", r"\AND"))
        self.assertTrue(matches("a(b)", r"a\(b\)"))
        self.assertFalse(matches("rocket", '"rock*"'))
        for expression in ["two patterns", "x\\"]:
            with self.assertRaises(ValueError):
                search.compile_text_filter(expression, "wildcard")

    def test_glob_pathological_pattern_is_bounded_without_regex_backtracking(self):
        self.assertFalse(matches("a" * 10000, "*a" * 100 + "b", "wildcard"))

    def test_fields_do_not_manufacture_cross_tag_phrases(self):
        compiled = search.compile_search_filter({"text_filter": "secret key", "text_mode": "phrase", "text_field": "tags"})
        self.assertIsNone(search.match_search_filter(fixtures.memory("secret key", tags=["secret", "key"]), compiled))
        self.assertIsNotNone(search.match_search_filter(fixtures.memory("irrelevant", tags=["secret key"]), compiled))

    def test_dates_inclusive_start_full_end_day_and_exclusive_datetime(self):
        zone = search.search_timezone("UTC")
        start = search.date_boundary("2026-10-16", zone)
        end = search.date_boundary("2026-10-16", zone, end=True)
        self.assertEqual(end - start, 86400)
        compiled = search.compile_search_filter({"date_start": "2026-10-16", "date_end": "2026-10-16"})
        for epoch, expected in [(start - .001, False), (start, True), (end - .001, True), (end, False)]:
            self.assertEqual(search.match_search_filter(fixtures.memory(created_at_epoch=epoch), compiled) is not None, expected)
        self.assertEqual(search.date_boundary("2026-10-16T00:00:00Z", zone, end=True), start)
        self.assertEqual(search.date_boundary("2026-10-16T07:00:00Z", zone), search.date_boundary("2026-10-16", search.search_timezone("-07:00")))

    def test_open_ranges_invalid_dates_and_timezone(self):
        self.assertIsNotNone(search.match_search_filter(fixtures.memory(), search.compile_search_filter({"date_start": "2026-10-15"})))
        self.assertIsNotNone(search.match_search_filter(fixtures.memory(), search.compile_search_filter({"date_end": "2026-10-16"})))
        for options in [{"date_start": "tomorrow"}, {"date_start": "2026-02-30"}, {"date_end": "9999-12-31"},
                        {"date_start": "2026-10-17", "date_end": "2026-10-15"}, {"timezone": "local"},
                        {"timezone": "+24:00"}, {"timezone": "+01:61"}, {"text_mode": "regex"}, {"sort": "rating"},
                        {"offset": -1}, {"offset": 1.5}, {"offset": 1000001}, {"offset": 1}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                search.normalize_search_options(options)

    def test_dst_gap_fold_and_calendar_days(self):
        zone = search.search_timezone("America/Los_Angeles")
        for value in ["2026-03-08T02:30:00", "2026-11-01T01:30:00"]:
            with self.assertRaises(ValueError):
                search.date_boundary(value, zone)
        self.assertIsNotNone(search.date_boundary("2026-11-01T01:30:00-07:00", zone))
        for day, hours in [("2026-03-08", 23), ("2026-11-01", 25)]:
            self.assertEqual((search.date_boundary(day, zone, end=True) - search.date_boundary(day, zone))/3600, hours)

    def test_epoch_authority_missing_dates_and_ambiguous_legacy_dates(self):
        compiled = search.compile_search_filter({"date_start": "1970-01-01", "date_end": "1970-01-01"})
        self.assertIsNotNone(search.match_search_filter(fixtures.memory(created_at_epoch=0), compiled))
        for record in [fixtures.memory(timestamp=""), fixtures.memory(timestamp="bad", created_at_epoch="nan")]:
            self.assertIsNone(search.match_search_filter(record, compiled))
            self.assertIsNotNone(search.match_search_filter(record, search.compile_search_filter({})))
        self.assertIsNone(search.record_search_epoch(fixtures.memory(timestamp="2026-11-01 01:30:00"), search.search_timezone("America/Los_Angeles")))
        self.assertIsNone(search.record_search_epoch(fixtures.memory(timestamp="bad", created_at_epoch=1e100), search.search_timezone("UTC")))

    def test_strict_named_options_preserve_legacy_and_allow_explicit_json(self):
        allowed = set(search.SEARCH_DEFAULTS) | {"query"}
        for args in [["author=me"], ["date_from=yesterday"], ["oops"], ["query=a", "query=b"]]:
            with self.assertRaises(ValueError):
                search.parse_search_options(args, allowed)
        self.assertEqual(search.parse_search_options(['query="C:\\tools"'], allowed)["query"], "C:\\tools")
        encoded = json.dumps('a "quote" and \\ path')
        result = search.parse_search_options(["value_encoding=json", "query=" + encoded], allowed)
        self.assertEqual(result["query"], 'a "quote" and \\ path')


class SearchRuntimeTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    call = fixtures.RuntimeTests.call
    request = fixtures.RuntimeTests.request
    write = fixtures.RuntimeTests.write

    def test_relative_filter_only_resolves_once_and_reports_window(self):
        self.write([fixtures.memory(snapshot_id="inside", created_at_epoch=100),
                    fixtures.memory(snapshot_id="outside", created_at_epoch=86400)])
        request = self.call("_build_retrieval_request", ["date_period=yesterday", "date_anchor=1970-01-02T12:00:00Z", "semantic_backend=force"])
        result = self.call("run_episodic_retrieval", request)
        self.assertTrue(result["ok"], result)
        self.assertEqual([item["record"]["snapshot_id"] for item in result["items"]], ["inside"])
        self.assertEqual(result["search"]["date_window"]["start_epoch"], 0)
        self.assertEqual(result["search"]["date_window"]["end_epoch"], 86400)
        self.assertEqual(result["search"]["date_window"]["anchor_utc"], "1970-01-02T12:00:00+00:00")
        self.scope["post_openai_embeddings"].assert_not_called()

    def test_after_exclusive_evidence_and_mem_forwarding(self):
        self.write([fixtures.memory(snapshot_id="boundary", created_at_epoch=0),
                    fixtures.memory(snapshot_id="inside", created_at_epoch=1)])
        request = self.call("_build_retrieval_shorthand_request", ["after=1970-01-01T00:00:00Z", "before=1970-01-02", "semantic_backend=force"])
        result = self.call("run_episodic_retrieval", request)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["items"]), 1)
        self.assertIsNone(result["search"]["start_epoch_inclusive"])
        self.assertEqual(result["search"]["start_epoch_exclusive"], 0)
        self.scope["post_openai_embeddings"].assert_not_called()

    def test_combined_filters_run_before_embedding_and_score(self):
        self.write([fixtures.memory("rocket key", tags=["A"], snapshot_id="hit"),
                    fixtures.memory("rocket key failed", tags=["A"], importance_score=12),
                    fixtures.memory("rocket key", tags=["B"]), fixtures.memory("rocket key", tags=["A"], source_bucket="other"),
                    fixtures.memory("rocket key", tags=["A"], timestamp="2026-10-17T00:00:00Z")])
        captured = []
        self.scope["_build_episodic_embedding_context"] = lambda q, r, records, **kw: captured.extend(records) or {"backend_used": "lexical"}
        request = self.request('text_filter="rocket AND NOT failed"', "text_mode=boolean", "tags_required=A", "source_buckets=manual", "date_end=2026-10-16")
        result = self.call("run_episodic_retrieval", request)
        self.assertTrue(result["ok"])
        self.assertEqual(len(captured), 1)
        self.assertEqual(result["search"]["eligible_records"], 1)
        self.assertEqual(result["search"]["total_records"], 5)
        self.assertEqual(result["items"][0]["record"]["snapshot_id"], "hit")
        self.assertEqual(len(result["items"][0]["search_matches"]), 4)


    def test_filter_only_force_never_calls_provider_and_empty_filters_fail(self):
        self.write([fixtures.memory()])
        for args in [["date_end=2026-10-16"], ['text_filter="rocket"'], ["tags_required=none"]]:
            request = self.call("_build_retrieval_request", args + ["semantic_backend=force"])
            result = self.call("run_episodic_retrieval", request)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["search"]["filter_only"])
            self.assertEqual(result["embedding_context"]["backend_used"], "filter_only")
        self.scope["post_openai_embeddings"].assert_not_called()
        for args in [[], ["sort=newest"], ["date_end=2026-10-16", "min_relevance=.1"]]:
            with self.assertRaises(ValueError):
                self.call("_build_retrieval_request", args)


    def test_paging_sorting_counts_missing_dates_and_ties(self):
        self.write([fixtures.memory(snapshot_id="b", created_at_epoch=2), fixtures.memory(snapshot_id="a", created_at_epoch=2),
                    fixtures.memory(snapshot_id="c", created_at_epoch=1), fixtures.memory(snapshot_id="unknown", timestamp="")])
        for order, expected in [("newest", ["a", "b", "c", "unknown"]), ("oldest", ["c", "a", "b", "unknown"])]:
            ids = []
            for offset in (0, 2):
                result = self.call("run_episodic_retrieval", self.request("sort="+order, "k=2", "offset="+str(offset), "variance_bias=1"))
                ids.extend(item["record"]["snapshot_id"] for item in result["items"])
                self.assertEqual(result["search"]["matched_records"], 4)
                self.assertFalse(result["search"]["curve_applied"])
                self.assertEqual(result["search"]["next_offset"], 2 if offset == 0 else None)
            self.assertEqual(ids, expected)
        result = self.call("run_episodic_retrieval", self.request("sort=relevance", "offset=99"))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["search"]["matched_records"], 4)
        self.assertEqual(self.scope["runtime_state"]["episodic_memory_last_retrieval_search"], result["search"])


    def test_actual_command_framing_preserves_boolean_quotes_and_wildcard_escape(self):
        exec(compile(ast.Module(body=[fixtures.FUNCTIONS["extract_command_arguments"]], type_ignores=[]), "aurora2.py", "exec"), self.scope)
        self.scope["CommandSyntaxError"] = CommandSyntaxError
        expression = '(rocket OR "secret key") AND NOT failed AND \\*'
        command = "RECALL(query=" + json.dumps('a "quote"') + ", value_encoding=json, text_filter=" + json.dumps(expression) + ", text_mode=boolean)"
        framed = split_command_batch(command)[0]
        request = self.call("_build_retrieval_shorthand_request", self.call("extract_command_arguments", framed))
        self.assertEqual(request["text_filter"], expression)
        self.assertEqual(request["query"], 'a "quote"')
        self.assertTrue(matches("rocket *", request["text_filter"]))
        for args in [["rocket", "unknown=x"], ["rocket", "query=other"], ["rocket", "stray"]]:
            with self.assertRaises(ValueError):
                self.call("_build_retrieval_request", args)


    def test_cancel_during_filter_scan_publishes_no_results(self):
        self.write([fixtures.memory()] * 5)
        original = self.scope["match_search_filter"]
        def cancel(record, compiled):
            self.scope["COMMAND_WORK"].cancel("fixture")
            return original(record, compiled)
        self.scope["match_search_filter"] = cancel
        with self.assertRaises(WorkCancelled):
            self.call("run_episodic_retrieval", self.request("text_filter=rocket"))
        self.scope["post_openai_embeddings"].assert_not_called()
        self.assertNotIn("episodic_memory_last_retrieval_search", self.scope["runtime_state"])


    def test_force_failure_does_not_retain_stale_search_counts(self):
        self.write([fixtures.memory()])
        self.scope["runtime_state"]["episodic_memory_last_retrieval_search"] = {"matched_records": 999}
        self.scope["_build_episodic_embedding_context"] = lambda *a, **kw: {"backend_requested": "force", "complete": False, "error": "fixture"}
        result = self.call("run_episodic_retrieval", self.request("semantic_backend=force"))
        self.assertFalse(result["ok"])
        self.assertEqual(self.scope["runtime_state"]["episodic_memory_last_retrieval_search"], {})

    def test_displayed_equivalent_round_trips_legacy_backslashes_and_quotes(self):
        exec(compile(ast.Module(body=[fixtures.FUNCTIONS["extract_command_arguments"]], type_ignores=[]), "aurora2.py", "exec"), self.scope)
        self.scope["CommandSyntaxError"] = CommandSyntaxError
        request = self.request('text_filter="secret key"')
        request["query"] = 'C:\\tools and "quoted"'
        command = self.call("_format_retrieval_pull_equivalent", request)
        restored = self.call("_build_retrieval_request", self.call("extract_command_arguments", command))
        self.assertEqual(restored["query"], request["query"])
        self.assertEqual(restored["text_filter"], request["text_filter"])
        self.assertEqual(restored["value_encoding"], "json")



class FeedbackRuntimeTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    call = fixtures.RuntimeTests.call
    request = fixtures.RuntimeTests.request
    write = fixtures.RuntimeTests.write
    def test_reject_batch_skips_before_provider_and_plain_repeats_do_not_reject(self):
        self.write([fixtures.memory("rocket one", snapshot_id="a"), fixtures.memory("rocket two", snapshot_id="b")])
        request = self.request("feedback_mode=skip", "k=1", "sort=relevance", "time_weight=0", "semantic_weight=1")
        first = self.call("run_episodic_retrieval", request)
        again = self.call("run_episodic_retrieval", request)
        self.assertEqual(first["items"][0]["record"]["snapshot_id"], again["items"][0]["record"]["snapshot_id"])
        rejected = again["items"][0]["record"]
        captured = []
        self.scope["_build_episodic_embedding_context"] = lambda q,r,rows,**kw: captured.extend(rows) or {}
        result = self.call("run_episodic_retrieval", {**request, "feedback_action":"reject_last", "feedback_token":again["search"]["feedback"]["token"]})
        self.assertTrue(result["ok"], result)
        self.assertNotIn(rejected, captured)
        self.assertNotEqual(result["items"][0]["record"], rejected)
        self.assertEqual(result["search"]["feedback"]["excluded_records"], 1)
        self.assertEqual(self.call("run_episodic_retrieval", request)["items"][0]["record"], result["items"][0]["record"])
        restored = self.call("run_episodic_retrieval", {**request,"feedback_action":"reset"})
        self.assertEqual(restored["items"][0]["record"], rejected)

    def test_penalty_changes_score_and_can_be_disabled(self):
        self.write([fixtures.memory("rocket", snapshot_id="a")])
        request = self.request("feedback_mode=penalize", "feedback_factor=.2", "sort=relevance")
        first = self.call("run_episodic_retrieval", request)
        result = self.call("run_episodic_retrieval", {**request,"feedback_action":"reject_last","feedback_token":first["search"]["feedback"]["token"]})
        self.assertAlmostEqual(result["items"][0]["weighted_total"], first["items"][0]["weighted_total"]*.2)
        self.assertAlmostEqual(sum(result["items"][0]["score_contributions"].values()), result["items"][0]["weighted_total"], places=3)
        off = self.call("run_episodic_retrieval", {**request,"feedback_mode":"off"})
        self.assertEqual(off["items"][0]["weighted_total"], first["items"][0]["weighted_total"])

    def test_failed_embedding_does_not_commit_rejection(self):
        self.write([fixtures.memory("rocket a", snapshot_id="a"),fixtures.memory("rocket b", snapshot_id="b")])
        request=self.request("feedback_mode=skip", "k=1", "sort=relevance")
        first=self.call("run_episodic_retrieval",request)
        original=self.scope["_build_episodic_embedding_context"]
        self.scope["_build_episodic_embedding_context"] = lambda *a,**kw: {"backend_requested":"force","complete":False,"error":"fixture"}
        result=self.call("run_episodic_retrieval",{**request,"feedback_action":"reject_last","feedback_token":first["search"]["feedback"]["token"]})
        self.assertFalse(result["ok"])
        self.scope["_build_episodic_embedding_context"]=original
        retry=self.call("run_episodic_retrieval",request)
        self.assertEqual(first["items"][0]["record"],retry["items"][0]["record"])


class FeedbackPolicyTests(unittest.TestCase):
    def test_tokens_sessions_changed_content_and_optimistic_publish(self):
        ledger=search.SearchFeedbackLedger(max_queries=2,max_rejected=2)
        request={**search.normalize_search_options({"feedback_mode":"skip"}),"query":"rocket"}
        record=fixtures.memory()
        one=ledger.prepare(request)
        stale=ledger.prepare(request)
        receipt=ledger.publish(one,[{"record":record}])
        with self.assertRaises(ValueError): ledger.publish(stale,[])
        rejecting={**request,"feedback_action":"reject_last","feedback_token":receipt["token"]}
        for changes in [{"query":"other"},{"feedback_session":"other"},{"feedback_token":"stale"}]:
            with self.assertRaises(ValueError): ledger.prepare({**rejecting,**changes})
        plan=ledger.prepare({**rejecting,"distribution_shape":"gaussian"})
        self.assertEqual(ledger.factor(plan,record),0)
        self.assertEqual(ledger.factor(plan,{**record,"summary_text":"new evidence"}),1)
        receipt=ledger.publish(plan,[])
        ledger.publish(ledger.prepare({**request,"query":"second"}),[])
        ledger.publish(ledger.prepare({**request,"query":"third"}),[])
        self.assertEqual(len(ledger._entries),2)
        with self.assertRaises(ValueError): ledger.prepare({**rejecting,"feedback_token":receipt["token"]})

    def test_feedback_options_validate_and_zero_is_exclusion(self):
        for options in [{"feedback_mode":"bad"},{"feedback_factor":"nan"},{"feedback_factor":-1},
                        {"feedback_factor":2},{"feedback_action":"reject_last"},
                        {"feedback_mode":"skip","offset":2,"sort":"relevance"},
                        {"feedback_mode":"penalize","sort":"newest"},{"feedback_session":""}]:
            with self.subTest(options=options),self.assertRaises(ValueError): search.normalize_search_options(options)
        ledger=search.SearchFeedbackLedger()
        request={**search.normalize_search_options({"feedback_mode":"penalize","feedback_factor":0}),"query":"rocket"}
        record=fixtures.memory()
        token=ledger.publish(ledger.prepare(request),[{"record":record}])["token"]
        plan=ledger.prepare({**request,"feedback_action":"reject_last","feedback_token":token})
        self.assertEqual(ledger.factor(plan,record),0)


class PanelSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((fixtures.ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        cls.methods = {node.name: node for node in ast.walk(cls.tree) if isinstance(node, ast.FunctionDef)}

    def test_panel_filter_only_json_forwarding_and_validation(self):
        scope = {"retrieval_commands": fixtures.retrieval_commands, **vars(search), "finite_number": fixtures.retrieval.finite_number, "json": json, "messagebox": Mock()}
        exec(compile(ast.Module(body=[self.methods["_episodic_retrieval_segments"]], type_ignores=[]), "panel", "exec"), scope)
        ui = SimpleNamespace()
        values = {"query": "", "limit": "4", "time_weight": ".5", "semantic_weight": ".5", "tag_weight": "0",
                  "backend": "force", "embedding_model": "fixture", "shape": "balanced", "center": "0", "spread": ".22", "variance": "0",
                  "tags_required": "", "tags_preferred": "", "source_buckets": "", "time_mode": "ordinal", "age_half_life_hours": "24",
                  "min_relevance": "0", "semantic_tag_weight": ".5", "embedding_fallback": "lexical", "time_anchor": "", "time_scale": "1", "score_mode": "legacy"}
        for key, value in values.items():
            setattr(ui, "episodic_" + key + "_var", SimpleNamespace(get=lambda v=value: v))
        ui.episodic_score_weights = {}
        options = {**search.SEARCH_DEFAULTS, "text_filter": '"secret key" AND \\*', "text_mode": "boolean", "value_encoding": "json"}
        ui.episodic_search_vars = {key: SimpleNamespace(get=lambda v=value: str(v)) for key, value in options.items()}
        segments = scope["_episodic_retrieval_segments"](ui)
        decoded = search.parse_search_options(segments, set(options) | set(values) | {"k", "semantic_backend", "distribution_shape", "distribution_center", "distribution_spread", "variance_bias"})
        self.assertEqual(decoded["text_filter"], options["text_filter"])
        self.assertEqual(decoded["query"], "")
        ui.episodic_search_vars["date_period"] = SimpleNamespace(get=lambda: "yesterday")
        ui.episodic_search_vars["date_anchor"] = SimpleNamespace(get=lambda: "2026-11-04T12:00:00Z")
        relative = scope["_episodic_retrieval_segments"](ui)
        forwarded = search.parse_search_options(relative, set(options) | set(values) | {"k", "semantic_backend", "distribution_shape", "distribution_center", "distribution_spread", "variance_bias"})
        self.assertEqual(forwarded["date_period"], "yesterday")
        self.assertEqual(forwarded["date_anchor"], "2026-11-04T12:00:00Z")
        ui.episodic_search_vars["argument_policy"] = SimpleNamespace(get=lambda: "strict")
        ui.episodic_time_weight_var = SimpleNamespace(get=lambda: "nan")
        self.assertIsNone(scope["_episodic_retrieval_segments"](ui))
        scope["messagebox"].showerror.assert_called_once()
        scope["messagebox"].showerror.reset_mock()
        ui.episodic_time_weight_var = SimpleNamespace(get=lambda: ".5")
        ui.episodic_search_vars["date_start"] = SimpleNamespace(get=lambda: "yesterday")
        self.assertIsNone(scope["_episodic_retrieval_segments"](ui))
        scope["messagebox"].showerror.assert_called_once()

    def test_foreign_or_missing_result_clears_feedback_token(self):
        scope = {}
        exec(compile(ast.Module(body=[self.methods["_update_episodic_feedback_token"]], type_ignores=[]), "panel", "exec"), scope)
        token = Mock()
        ui = SimpleNamespace(episodic_search_vars={"feedback_session": SimpleNamespace(get=lambda: "mine"), "feedback_token": token})
        for info, expected in [({"feedback":{"session":"mine","token":"valid"}},"valid"), ({"feedback":{"session":"other","token":"foreign"}},""), ({},"")]:
            scope["_update_episodic_feedback_token"](ui, info)
            token.set.assert_called_with(expected)

    def test_refresh_does_not_refill_a_deliberately_cleared_query(self):
        guard = next(node for node in self.methods["render_episodic"].body
                     if isinstance(node, ast.If) and "_episodic_query_initialized" in ast.unparse(node.test))
        holder = [""]
        ui = SimpleNamespace(episodic_query_var=SimpleNamespace(get=lambda: holder[0], set=lambda value: holder.__setitem__(0, value)))
        scope = {"self": ui, "episodic": {"last_search_query": "old query"}}
        code = compile(ast.Module(body=[guard], type_ignores=[]), "panel", "exec")
        exec(code, scope)
        self.assertEqual(holder[0], "old query")
        holder[0] = ""
        exec(code, scope)
        self.assertEqual(holder[0], "")


if __name__ == "__main__":
    unittest.main()
