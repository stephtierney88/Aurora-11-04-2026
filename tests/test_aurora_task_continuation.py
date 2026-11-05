import unittest

from aurora_task_continuation import TaskContinuation, CommandReadbacks, prepare_init_delivery, reported_token_usage
from aurora_settings_registry import coerce_setting_value, InvalidSettingValueError


class TaskContinuationTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = TaskContinuation(clock=lambda: self.now)

    def reserve(self, **kwargs):
        return self.task.reserve(max_turns=2, max_seconds=30, **kwargs)

    def test_slots_share_one_limit_and_automatic_wakes_cannot_restart(self):
        self.assertTrue(self.reserve(trigger="user_input"))
        task_id = self.task.snapshot()["task_id"]
        self.assertTrue(self.reserve(trigger="command_readback"))
        self.assertTrue(self.task.check_deadline())  # final allowed response is usable
        self.assertFalse(self.reserve(trigger="heartbeat"))
        self.assertEqual(self.task.snapshot()["stop_reason"], "turn_limit")
        self.assertEqual(self.task.snapshot()["task_id"], task_id)
        self.assertTrue(self.reserve(operator_input=True))
        self.assertNotEqual(self.task.snapshot()["task_id"], task_id)

    def test_limits_latch_and_expiry_is_not_reset_by_a_model_switch(self):
        self.reserve()
        self.now = 129
        self.assertTrue(self.task.reserve(max_turns=100, max_seconds=1000, trigger="review"))
        self.assertEqual(self.task.snapshot()["max_seconds"], 30)
        self.now = 130
        self.assertFalse(self.task.check_deadline())
        self.assertEqual(self.task.snapshot()["stop_reason"], "time_limit")
        self.assertFalse(self.task.can_dispatch())

    def test_failure_and_cancel_do_not_resurrect_on_automatic_capture(self):
        for reason in ("operator_cancelled", "inference_paused", "request_exception"):
            self.reserve(operator_input=True)
            self.task.stop(reason)
            self.assertFalse(self.task.can_dispatch())
            self.assertEqual(self.task.snapshot()["stop_reason"], reason)

    def test_cancel_before_first_request_blocks_startup_wakes(self):
        self.task.stop("operator_cancelled")
        self.assertFalse(self.task.can_dispatch())
        self.assertEqual(self.task.snapshot()["turns"], 0)
        self.assertTrue(self.reserve(operator_input=True))

    def test_readback_ack_cannot_drop_result_published_during_inference(self):
        first = self.task.publish_readback("lookup1")
        self.task.publish_readback("lookup2")
        self.task.acknowledge_readback(first)
        self.assertTrue(self.task.readback()["pending"])
        self.task.acknowledge_readback(self.task.readback()["generation"])
        self.assertFalse(self.task.readback()["pending"])
        self.task.acknowledge_readback(0)
        self.assertFalse(self.task.readback()["pending"])

    def test_turn_limit_rejects_fractional_nonfinite_and_bool_values(self):
        self.assertEqual(coerce_setting_value("task.max_model_turns", "8.0"), 8)
        for value in ("8.1", "nan", "inf", True, 0, 10001):
            with self.subTest(value=value), self.assertRaises(InvalidSettingValueError):
                coerce_setting_value("task.max_model_turns", value)


class InitDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.init = "Use commands carefully.\nKeep evidence."
        self.row = {"role": "system", "Exemption": "Init", "content": {"type": "text", "text": self.init}}

    def prepare(self, rows, **kwargs):
        return prepare_init_delivery(rows, self.init, "Persistent init context:\n" + self.init,
                                     mode="system_once", **kwargs)

    def test_exact_duplicate_is_request_only_and_legacy_unchanged(self):
        history = [self.row]
        retained, prompt, report = self.prepare(history, current_prompt=self.init, exemption="Init")
        self.assertEqual(retained, [])
        self.assertEqual(history, [self.row])
        self.assertNotEqual(prompt, self.init)
        self.assertTrue(report["shortened_initialization_trigger"])
        self.assertEqual(report["removed_history_chars"], len(self.init))
        legacy, prompt, report = prepare_init_delivery(history, self.init, "Persistent init context:\n" + self.init,
                                                        current_prompt=self.init, exemption="Init")
        self.assertEqual(legacy, history)
        self.assertEqual(prompt, self.init)
        self.assertEqual(report["removed_history_copies"], 0)

    def test_edited_init_and_ordinary_user_quotes_are_retained(self):
        quote = dict(self.row, Exemption="None", role="user")
        edited = dict(self.row, content={"type": "text", "text": self.init + "\nNew instruction."})
        kept, prompt, report = self.prepare([self.row, quote, edited], current_prompt=self.init, exemption="None")
        self.assertEqual(kept, [quote, edited])
        self.assertEqual(prompt, self.init)

    def test_truncated_system_copy_does_not_lose_full_history(self):
        kept, _, report = prepare_init_delivery([self.row], self.init, "Persistent init context:\n" + self.init[:10], mode="system_once")
        self.assertEqual(kept, [self.row])
        self.assertFalse(report["eligible"])

    def test_only_the_recorded_timestamp_wrapper_is_recognized(self):
        stamp = "2026-11-04 11:00:00"
        wrapped = dict(self.row, timestamp=stamp, content={"type": "text", "text": f"[{stamp}] {self.init}"})
        mismatched = dict(wrapped, timestamp="different")
        kept, _, report = self.prepare([wrapped, mismatched])
        self.assertEqual(kept, [mismatched])
        self.assertEqual(report["removed_history_copies"], 1)


class ReviewedReadbackTests(unittest.TestCase):
    def receipt(self, key="b1", **updates):
        return dict(command_batch_id=key, task_id="t1", inference_request_id="i1", is_user=False,
                    receipt_id="receipt-"+key, status="processed", command_generation=2,
                    setting_results=[{"key": "capture.mode", "success": True, "after_value": "request_only"}], **updates)

    def test_only_correlated_model_reviewed_results_are_retained(self):
        store = CommandReadbacks()
        row = self.receipt()
        for field, value in (("is_user", True), ("task_id", ""), ("inference_request_id", ""),
                             ("command_batch_id", ""), ("setting_results", [])):
            self.assertFalse(store.publish(dict(row, **{field: value})))
        self.assertTrue(store.publish(row))
        self.assertFalse(store.publish(row))
        row["setting_results"][0]["after_value"] = "changed later"
        manifest = store.prepare("t1", "i2")
        selected = manifest["records"][0]
        self.assertEqual(selected["results"]["setting_results"][0]["after_value"], "request_only")
        selected["results"].clear()
        self.assertTrue(store.snapshot()["records"][0]["results"])
        self.assertNotIn("results", store.snapshot(include_results=False)["records"][0])

    def test_selection_is_task_scoped_bounded_and_does_not_consume_later_receipts(self):
        store = CommandReadbacks()
        for i in range(5):
            store.publish(self.receipt(str(i)))
        self.assertFalse(store.prepare("another task", "i2")["records"])
        selected = store.prepare("t1", "i2")
        self.assertEqual(len(selected["records"]), 4)
        self.assertEqual(selected["remaining_pending"], 1)
        store.publish(self.receipt("later"))
        store.mark_request("i2", "submitted")
        store.mark_request("i2", "responded")
        next_rows = store.prepare("t1", "i3")["records"]
        self.assertEqual([r["command_batch_id"] for r in next_rows], ["4", "later"])

    def test_preparation_failure_and_submitted_uncertainty_do_not_replay(self):
        for submitted in (False, True):
            with self.subTest(submitted=submitted):
                store = CommandReadbacks()
                store.publish(self.receipt())
                store.prepare("t1", "i2")
                if submitted:
                    store.mark_request("i2", "submitted")
                store.mark_request("i2", "cancelled")
                store.mark_request("i2", "responded")  # a late result cannot revive it
                self.assertEqual(store.snapshot()["records"][0]["phase"], "uncertain" if submitted else "not_sent")
                self.assertFalse(store.pending("t1"))

    def test_truncation_and_retention_loss_are_explicit(self):
        store = CommandReadbacks(max_records=2, record_chars=100, request_chars=6000)
        for i in range(3):
            row = self.receipt(str(i))
            row["memory_command_results"] = [{"text": "long goal "*100}]
            store.publish(row)
        manifest = store.prepare("t1", "i2")
        self.assertEqual(manifest["evicted_pending_total"], 1)
        self.assertEqual(len(manifest["records"]), 2)
        for row in manifest["records"]:
            self.assertTrue(row["payload_truncated"])
            self.assertEqual(len(row["payload_preview"]), 100)
            self.assertGreater(row["payload_chars"], 100)
            self.assertEqual(len(row["payload_sha256"]), 64)

    def test_request_size_bound_and_concurrent_publication(self):
        import concurrent.futures
        store = CommandReadbacks(record_chars=3000, request_chars=5048)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda i: store.publish(self.receipt(str(i))), range(20)))
        seen = []
        while store.pending("t1"):
            request = "request-" + str(len(seen))
            manifest = store.prepare("t1", request)
            self.assertTrue(manifest["records"])
            seen.extend(r["record_id"] for r in manifest["records"])
            store.mark_request(request, "submitted")
            store.mark_request(request, "responded")
        self.assertEqual(len(set(seen)), 20)
        self.assertEqual(len(seen), 20)

    def test_unknown_usage_is_never_zero_or_derived(self):
        for usage in (None, {}, [], {"input_tokens": True, "output_tokens": -1, "total_tokens": "5"}):
            self.assertEqual(reported_token_usage(usage), dict(input_tokens=None, output_tokens=None, total_tokens=None))
        self.assertEqual(reported_token_usage({"prompt_tokens": 12, "completion_tokens": 0}),
                         dict(input_tokens=12, output_tokens=0, total_tokens=None))

    def test_accounting_deduplicates_and_keeps_unknown_usage_coverage(self):
        task = TaskContinuation()
        task.reserve(max_turns=10, max_seconds=60)
        identity = task.snapshot()["task_id"]
        receipt = dict(self.receipt(), task_id=identity, executed_commands=["one", "two"], failed_commands=[{}], blocked_commands=["tail"])
        self.assertTrue(task.record_command(receipt))
        self.assertFalse(task.record_command(receipt))
        self.assertFalse(task.record_command(dict(receipt, task_id="old")))
        task.record_request(identity, "r1", started=True, phase="responded", model="primary",
                            usage={"prompt_tokens": 12, "completion_tokens": 3}, readback_ids=["readback-b1"], frame_id="f1")
        task.record_request(identity, "r1", started=True, phase="responded", usage={"total_tokens": 999})
        task.record_request(identity, "r2", started=True, phase="cancelled")
        task.record_request(identity, "r3", started=False, phase="not_sent")
        report = task.snapshot()["accounting"]
        self.assertEqual((report["command_batches"], report["executed_commands"], report["failed_commands"], report["blocked_commands"]), (1, 2, 1, 1))
        self.assertEqual((report["requests_started"], report["responses_received"], report["request_failures"]), (2, 1, 1))
        self.assertEqual(report["usage"]["input_tokens"], dict(known_total=12, known_requests=1, unknown_requests=1))
        self.assertEqual(report["usage"]["total_tokens"]["unknown_requests"], 2)
        task.stop("operator_cancelled")
        task.reserve(max_turns=10, max_seconds=60, operator_input=True)
        self.assertFalse(task.record_command(receipt))
        self.assertEqual(task.snapshot()["accounting"]["command_batches"], 0)

    def test_accounting_capacity_is_visible_without_stopping_task(self):
        task = TaskContinuation()
        task.reserve(max_turns=10, max_seconds=60)
        task._seen_batches = set(str(i) for i in range(4096))
        self.assertFalse(task.record_command(dict(self.receipt(), task_id=task.snapshot()["task_id"])))
        self.assertTrue(task.snapshot()["accounting"]["capacity_exceeded"])
        self.assertTrue(task.can_dispatch())

    def test_adaptive_responses_wrapper_preserves_reported_model_and_usage(self):
        import ast
        from types import SimpleNamespace as NS
        from test_aurora_turn_flow import FUNCTIONS
        for usage in (None, {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}):
            data = {"model": "server-reported-model", "usage": usage}
            scope = {"AUTH_MODE": "api_key", "MODEL_TRANSPORT": "responses", "DEFAULT_REASONING_EFFORT": "low",
                     "ASTRA_MODEL": "requested-model", "normalize_reasoning_effort_for_model": lambda *a, **k: "low",
                     "MODEL_WORK": NS(current=lambda: NS(check=lambda: None)),
                     "RESPONSES_REASONING": NS(prepare=lambda *a, **k: NS(payload={}), complete=lambda *a: "answer"),
                     "post_openai_model_request": lambda *a, **k: (NS(status_code=200, json=lambda: data), "api_key")}
            exec(compile(ast.Module(body=[FUNCTIONS["post_openai_turn_request"]], type_ignores=[]), "responses-wrapper", "exec"), scope)
            response, mode = scope["post_openai_turn_request"]({"model": "requested-model"}, current_messages=[])
            self.assertEqual(response.json()["model"], "server-reported-model")
            self.assertEqual(response.json()["usage"], usage)
            self.assertEqual(mode, "api_key")


if __name__ == "__main__":
    unittest.main()
