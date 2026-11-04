"""Shared admission and correlated query/snapshot receipts, without native/provider effects."""
import ast
import json
import unittest
from unittest.mock import Mock, patch

import aurora_retrieval_commands as commands
from aurora_command_contracts import validate_command_arguments, describe_command_contract, command_failure_stops_batch
from aurora_runtime_work import WorkCancelled
import test_aurora_command_ingress as ingress
import test_aurora_episodic_retrieval as fixtures


class AdmissionTests(unittest.TestCase):
    def test_all_six_commands_have_reviewed_contracts(self):
        for name in commands.EPISODIC_COMMANDS:
            self.assertEqual(describe_command_contract(name)["parameter_validation"], "pre_dispatch")
            self.assertEqual(describe_command_contract(name)["result"]["receipt_field"], "retrieval_results")
            self.assertTrue(command_failure_stops_batch(name))
        options = describe_command_contract("RECALL")["named_options"]
        self.assertEqual(options["argument_policy"]["choices"], ["legacy", "strict"])
        self.assertEqual(options["result_mode"]["default"], "legacy")
        self.assertIn("runtime configuration", options["embedding_model"]["default_source"])

    def test_legacy_defaults_and_coercions_remain_explicit(self):
        result = commands.build_retrieval_request(["rocket", "k=inf", "time_weight=2", "semantic_weight=nan", "distribution_shape=other", "distribution_spread=2"])
        self.assertEqual(result["argument_policy"], "legacy")
        self.assertEqual(result["k"], 4)
        self.assertEqual(result["time_weight"], 1)
        self.assertEqual(result["semantic_weight"], .5)
        self.assertEqual(result["distribution_shape"], "balanced")
        self.assertEqual(result["distribution_spread"], .05)

    def test_strict_rejects_bad_legacy_fields_before_clamping(self):
        for option in ["k=inf", "k=2.5", "k=0", "k=25", "time_weight=2", "semantic_weight=nan",
                       "tag_weight=-1", "variance_bias=1.1", "time_scale=0", "distribution_spread=2",
                       "distribution_center=101", "distribution_shape=other", "semantic_backend=other",
                       "embedding_model=", "time_anchor=unknown", "time_anchor=inf"]:
            with self.subTest(option=option), self.assertRaises(ValueError):
                validate_command_arguments("RETRIEVAL_PULL", ["rocket", "argument_policy=strict", option])

    def test_strict_keeps_percent_controls_zeros_and_shorthand(self):
        result = commands.parse_episodic_command("MEM", ["rocket", "12.0", "argument_policy=strict", "time_weight=0",
            "distribution_center=50", "distribution_spread=20", "semantic_backend=off", "time_anchor=early"])
        self.assertEqual(result["k"], 12)
        self.assertEqual(result["time_weight"], 0)
        self.assertEqual((result["distribution_center"], result["distribution_spread"]), (.5, .2))

    def test_named_grammar_dates_and_filter_requirements_always_validate(self):
        for args in [[], ["sort=newest"], ["date_start=not-a-date"], ["date_start=2026-11-04", "date_end=2026-11-03"],
                     ["rocket", "k=4", "k=5"], ["rocket", "person=me"], ["text_filter=rocket AND", "text_mode=boolean"],
                     ["date_end=2026-11-04", "min_relevance=.5"], ["rocket", "argument_policy=unknown"]]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_command_arguments("RECALL", args)
        request = commands.parse_episodic_command("RETRIEVAL_PULL", ["text_filter=rocket", "semantic_backend=force"])
        self.assertEqual(request["query"], "")

    def test_quoted_values_tags_and_runtime_defaults_are_preserved(self):
        result = commands.build_retrieval_request(['query="C:\\tools"', 'tags_required="A; a; B"', 'source_buckets="Manual"'],
            embedding_mode="off", embedding_model="custom", max_tags=1)
        self.assertEqual(result["query"], "C:\\tools")
        self.assertEqual(result["tags_required"], ["A"])
        self.assertEqual(result["source_buckets"], ["manual"])
        self.assertEqual((result["semantic_backend"], result["embedding_model"]), ("off", "custom"))
        value = 'quote "a"; path \\literal'
        encoded = commands.build_retrieval_request(["query=" + json.dumps(value), "value_encoding=json"])
        self.assertEqual(encoded["query"], value)

    def test_snapshot_limits_keep_finite_legacy_behavior_and_reject_extras(self):
        self.assertEqual(commands.parse_episodic_command("LIST_EPISODIC_SNAPSHOTS", ["30"])["limit"], 24)
        self.assertEqual(commands.parse_episodic_command("SEARCH_EPISODIC_SNAPSHOTS", ["rocket", "3.8"])["limit"], 3)
        self.assertEqual(commands.parse_episodic_command("LIST_EPISODIC_SNAPSHOTS", [], list_limit=40)["limit"], 40)
        self.assertEqual(commands.parse_episodic_command("WRITE_EPISODIC_SNAPSHOT", ["", "a;b"]), {"reason": "", "tags": "a;b"})
        for name, args in [("LIST_EPISODIC_SNAPSHOTS", ["nan"]), ("LIST_EPISODIC_SNAPSHOTS", ["2", "extra"]),
                           ("SEARCH_EPISODIC_SNAPSHOTS", [""]), ("SEARCH_EPISODIC_SNAPSHOTS", ["rocket", "inf"]),
                           ("WRITE_EPISODIC_SNAPSHOT", ["a", "b", "ignored"]), ("MEM", [None])]:
            with self.assertRaises(ValueError): validate_command_arguments(name, args)


class BatchAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.harness = ingress.RuntimeIngressTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.harness.authorize()
        self.scope = self.harness.scope
        for name in commands.EPISODIC_COMMANDS:
            self.scope["command_dispatch"][name] = lambda args, user, n=name: self.harness.executed.append(n) or commands.episodic_receipt(n)

    def test_bad_tail_rejects_before_any_prior_mutation(self):
        for index, suffix in enumerate(['RECALL(rocket,person=me)', 'MEM(rocket,k=nan,argument_policy=strict)',
                                        'WRITE_EPISODIC_SNAPSHOT(a,b,extra)', 'SEARCH_EPISODIC_SNAPSHOTS("")']):
            self.harness.send("UPDATE_NOTES(must not happen);" + suffix, request_id=f"bad-search-{index}")
            self.harness.poll()
            self.assertEqual(self.harness.executed, [])
            self.assertTrue(self.harness.inputs.empty())
        self.assertTrue(all(row["status"] == "rejected" for row in self.harness.events if row["event"] == "command_result"))

    def test_execution_failure_retains_receipt_and_stops_tail(self):
        self.scope["command_dispatch"]["RECALL"] = lambda args, user: commands.episodic_receipt("retrieve", success=False, effect_status="not_published", reason="fixture backend failure")
        result = self.scope["handle_commands"]("RECALL(rocket);UPDATE_NOTES(must not happen)")
        self.assertFalse(result["success"])
        self.assertEqual(result["retrieval_results"][0]["reason"], "fixture backend failure")
        self.assertEqual(result["blocked_commands"], ["UPDATE_NOTES(must not happen)"])
        self.assertEqual(self.harness.executed, [])


class RuntimeReceiptTests(unittest.TestCase):
    call = fixtures.RuntimeTests.call
    write = fixtures.RuntimeTests.write
    request = fixtures.RuntimeTests.request

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.write([fixtures.memory("rocket clue", created_at_epoch=1)])
        names = "execute_episodic_snapshot_command write_episodic_snapshot_command list_episodic_snapshots_command search_episodic_snapshots_command _coerce_episodic_snapshot_count".split()
        exec(compile(ast.Module(body=[fixtures.FUNCTIONS[name] for name in names], type_ignores=[]), "runtime", "exec"), self.scope)
        self.scope["EPISODIC_MEMORY_DEFAULT_LIST_LIMIT"] = 8

    def test_query_receipt_has_matching_id_effective_settings_and_bounded_evidence(self):
        receipt = self.call("retrieval_pull_command", ["rocket", "semantic_backend=off", "result_mode=retained", "argument_policy=strict"], True)
        self.assertTrue(receipt["success"], receipt)
        self.assertEqual(receipt["effective"]["argument_policy"], "strict")
        self.assertEqual(receipt["search"]["returned_records"], 1)
        self.assertEqual(receipt["retrieval_id"], self.scope["runtime_state"]["episodic_memory_last_retrieval_search"]["retrieval_id"])
        self.assertEqual(receipt["search"]["retained_result"]["returned_count"], 1)
        self.assertEqual(receipt["backend"]["backend_used"], "lexical")
        self.assertNotIn("query_vector", receipt["backend"])
        self.assertEqual(receipt["preview"][0]["summary_text"], "rocket clue")

    def test_filter_only_and_shorthand_receipts_keep_full_precision(self):
        receipt = self.call("memory_retrieval_shorthand_command", ["date_end=2026-11-04", "semantic_backend=force", "time_scale=1.234567"], True)
        self.assertTrue(receipt["success"], receipt)
        self.assertEqual(receipt["effective"]["time_scale"], 1.234567)
        self.assertEqual(receipt["backend"]["backend_used"], "filter_only")
        self.scope["post_openai_embeddings"].assert_not_called()

    def test_direct_validation_failure_and_backend_failure_are_typed(self):
        invalid = self.call("retrieval_pull_command", ["rocket", "k=nan", "argument_policy=strict"], True)
        self.assertFalse(invalid["success"])
        self.assertEqual(invalid["effect_status"], "not_applied")
        self.scope["_build_episodic_embedding_context"] = lambda *args, **kwargs: {"backend_requested": "force", "complete": False, "error": "fixture required backend failure"}
        failed = self.call("retrieval_pull_command", ["rocket", "semantic_backend=force"], True)
        self.assertFalse(failed["success"])
        self.assertEqual(failed["effect_status"], "not_published")
        self.assertEqual(failed["backend"]["error"], "fixture required backend failure")

    def test_cancellation_keeps_correlation_and_does_not_publish(self):
        with self.scope["COMMAND_WORK"].scope():
            self.scope["COMMAND_WORK"].cancel("fixture cancellation")
            receipt = self.call("retrieval_pull_command", ["rocket"], True)
        self.assertTrue(receipt["cancelled"])
        self.assertFalse(receipt["success"])
        self.assertTrue(receipt["retrieval_id"].startswith("retrieval_"))
        self.assertNotIn("episodic_memory_last_retrieval_items", self.scope["runtime_state"])

    def test_unexpected_exception_is_uncertain_not_success(self):
        self.scope["_read_episodic_snapshot_records"] = Mock(side_effect=OSError("fixture unreadable file"))
        receipt = self.call("retrieval_pull_command", ["rocket"], True)
        self.assertFalse(receipt["success"])
        self.assertEqual(receipt["effect_status"], "uncertain")

    def test_snapshot_list_and_lexical_search_have_counts_and_preview(self):
        listed = self.call("list_episodic_snapshots_command", [], True)
        searched = self.call("search_episodic_snapshots_command", ["rocket"], True)
        for receipt in [listed, searched]:
            self.assertTrue(receipt["success"], receipt)
            self.assertEqual(receipt["returned_count"], 1)
            self.assertEqual(receipt["preview"][0]["snapshot_id"], "same-id")
        missing = self.call("search_episodic_snapshots_command", ["no match"], True)
        self.assertEqual(missing["returned_count"], 0)
        self.scope["post_openai_embeddings"].assert_not_called()

    def test_snapshot_write_observes_count_and_identity_without_claiming_fsync(self):
        def append(**options):
            self.scope["runtime_state"]["episodic_memory_snapshot_count"] = 1
            return fixtures.memory(snapshot_id="saved")
        self.scope["append_episodic_snapshot"] = append
        receipt = self.call("write_episodic_snapshot_command", ["reason", "tag"], True)
        self.assertTrue(receipt["success"], receipt)
        self.assertEqual((receipt["snapshot_count_before"], receipt["snapshot_count_after"]), (0, 1))
        self.assertEqual(receipt["snapshot"]["snapshot_id"], "saved")
        self.assertIn("fsync not verified", receipt["durability"])

    def test_snapshot_no_record_error_and_late_cancel_are_not_claimed_success(self):
        for value in [None, OSError("fixture append may be partial"), WorkCancelled("fixture late cancellation")]:
            self.scope["append_episodic_snapshot"] = Mock(side_effect=value) if isinstance(value, Exception) else Mock(return_value=None)
            receipt = self.call("write_episodic_snapshot_command", [], True)
            self.assertFalse(receipt["success"])
            self.assertEqual(receipt["effect_status"], "not_applied" if value is None else "uncertain")


if __name__ == "__main__":
    unittest.main()
