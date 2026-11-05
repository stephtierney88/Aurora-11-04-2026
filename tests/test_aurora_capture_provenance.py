"""Acquisition/publication races without screens, native input or network."""
from dataclasses import FrozenInstanceError, replace
import ast
import pickle
import threading
from types import SimpleNamespace
import unittest

from aurora_capture_provenance import CaptureService, CapturedFrame
import test_aurora_turn_flow as turn_flow


class CaptureServiceTests(unittest.TestCase):
    def setUp(self):
        self.wall, self.mono = 1000.0, 100.0
        self.service = CaptureService(epoch=lambda: self.wall, monotonic=lambda: self.mono)

    def tick(self, seconds):
        self.mono += seconds
        self.wall += seconds

    def frame(self):
        return self.service.finish(self.service.begin("synthetic"))

    def publish(self, frame):
        return self.service.publish(frame, path="fixture.png", timestamp="fixture", capture_hash="same", counter=1)

    def test_acquisition_is_not_completion_and_stamp_is_immutable(self):
        self.service.request("command", .2)
        self.tick(.2)
        stamp = self.frame()
        self.assertEqual(stamp.request_generation, 1)
        with self.assertRaises(FrozenInstanceError):
            stamp.sequence = 9
        self.assertTrue(self.service.snapshot()["pending"])
        self.tick(1)
        self.assertTrue(self.publish(stamp))
        result = self.service.snapshot()
        self.assertFalse(result["pending"])
        self.assertEqual(result["last_completion"]["latency_ms"], 1200)
        self.assertLess(result["latest"]["provenance"]["acquired_start_epoch"], result["latest"]["published_at_epoch"])

    def test_new_request_survives_old_frame_publication(self):
        self.service.request("first")
        first = self.frame()
        self.service.request("second")
        self.publish(first)
        self.assertEqual(self.service.snapshot()["pending"]["generation"], 2)
        self.assertEqual(self.service.snapshot()["completed_count"], 0)
        self.publish(self.frame())
        self.assertFalse(self.service.snapshot()["pending"])

    def test_deadline_crossing_during_publication_never_publishes_failed_frame(self):
        self.service.request("deadline boundary", timeout_seconds=1)
        frame = self.frame()
        clock = iter((100.9, 101.1))
        self.service.monotonic = lambda: next(clock, 101.1)
        self.assertFalse(self.publish(frame))
        state = self.service.snapshot()
        self.assertEqual(state["current_failure"]["code"], "deadline_exceeded")
        self.assertFalse(state["latest"])
        self.assertEqual(state["completed_count"], 0)

    def test_capture_started_before_settle_cannot_complete_request(self):
        self.service.request("settling", 2)
        before = self.service.begin("synthetic")
        self.tick(5)
        self.publish(self.service.finish(before))
        self.assertTrue(self.service.snapshot()["pending"])
        self.publish(self.frame())
        self.assertFalse(self.service.snapshot()["pending"])

    def test_late_persistence_does_not_make_old_pixels_fresh(self):
        old = self.frame()
        self.tick(1)
        boundary = self.service.boundary(.2)
        self.tick(10)
        self.publish(old)
        self.assertFalse(self.service.is_fresh(self.service.snapshot()["latest"], boundary))
        self.publish(self.frame())
        self.assertTrue(self.service.is_fresh(self.service.snapshot()["latest"], boundary))

    def test_wall_clock_jumps_do_not_change_settle_or_latency(self):
        self.service.request("jump", 2)
        self.wall += 3600
        self.assertEqual(self.service.demand_wait(), 2)
        self.mono += 2
        self.wall -= 7200
        # Wall time can go backwards, but actual epoch remains positive.
        self.wall = 500
        self.publish(self.frame())
        self.assertEqual(self.service.snapshot()["last_completion"]["latency_ms"], 2000)

    def test_cancelled_and_previous_session_frames_cannot_publish(self):
        self.service.request("old")
        stamp = self.frame()
        self.service.cancel("operator")
        self.service.request("new")
        self.assertFalse(self.publish(stamp))
        self.assertFalse(self.publish(replace(self.frame(), session_id="other")))
        self.assertTrue(self.service.snapshot()["pending"])
        self.publish(self.frame())
        self.assertEqual(self.service.snapshot()["completed_count"], 1)

    def test_duplicate_and_out_of_order_frames_rejected(self):
        old, new = self.frame(), self.frame()
        self.assertTrue(self.publish(new))
        self.assertFalse(self.publish(old))
        self.assertFalse(self.publish(new))

    def test_dropped_frame_retries_and_unchanged_pixels_can_complete(self):
        self.service.request("dropped")
        dropped = self.frame()
        self.assertEqual(self.service.demand_wait(), 1)
        self.tick(1)
        self.assertEqual(self.service.demand_wait(), 0)
        replacement = self.frame()
        self.assertNotEqual(dropped.frame_id, replacement.frame_id)
        self.publish(replacement)
        self.assertFalse(self.service.snapshot()["pending"])

    def test_acquisition_drawing_and_persistence_failures_do_not_ack(self):
        for stage in ("acquisition", "drawing", "publication"):
            with self.subTest(stage=stage):
                self.service.request(stage)
                stamp = self.frame()
                self.service.fail(stage, OSError("private details"), stamp)
                self.assertTrue(self.service.snapshot()["pending"])
                self.assertEqual(self.service.demand_wait(), .5)
                self.assertNotIn("private", self.service.snapshot()["last_error"])
                self.tick(.5)
                self.publish(self.frame())
                self.assertFalse(self.service.snapshot()["pending"])

    def test_old_failure_does_not_poison_cancelled_recovery(self):
        old = self.frame()
        self.service.cancel("stop")
        self.service.fail("late", OSError(), old)
        self.assertEqual(self.service.snapshot()["failure_count"], 0)
        self.assertIsNone(self.service.begin("cancelled recapture", parent=old))

    def test_disabling_demand_preserves_periodic_observation_boundary(self):
        boundary = self.service.boundary()
        self.service.request("auxiliary")
        frame = self.frame()
        self.service.cancel("demand disabled", invalidate_frames=False)
        self.assertTrue(self.publish(frame))
        self.assertTrue(self.service.is_fresh(self.service.snapshot()["latest"], boundary))
        self.assertEqual(self.service.snapshot()["completed_count"], 0)

    def test_replacement_has_its_own_acquisition_and_parent_identity(self):
        old = self.frame()
        self.tick(2)
        new = self.service.finish(self.service.begin("recapture", replaces_frame_id=old.frame_id))
        self.assertNotEqual(old.frame_id, new.frame_id)
        self.assertEqual(new.replaces_frame_id, old.frame_id)
        self.assertGreater(new.acquired_start_monotonic, old.acquired_end_monotonic)

    def test_unknown_frames_and_foreign_boundaries_are_not_fresh(self):
        self.assertFalse(self.service.is_fresh({"provenance": {"status": "unknown"}}, self.service.boundary()))
        boundary = self.service.boundary()
        self.publish(self.frame())
        boundary["session_id"] = "other"
        self.assertFalse(self.service.is_fresh(self.service.snapshot()["latest"], boundary))

    def test_snapshot_is_detached_and_settle_validation_is_strict(self):
        self.service.request("actual")
        view = self.service.snapshot()
        view["pending"]["reason"] = "edited"
        self.assertEqual(self.service.snapshot()["pending"]["reason"], "actual")
        for invalid in (float("nan"), float("inf"), -1):
            with self.assertRaises(ValueError):
                self.service.request("invalid", invalid)

    def test_threaded_request_during_acquisition_is_not_erased(self):
        self.service.request("first")
        acquired = threading.Event()
        resume = threading.Event()
        errors = []
        def worker():
            try:
                frame = self.service.begin("slow acquisition")
                acquired.set()
                if not resume.wait(2):
                    raise AssertionError("fixture timeout")
                self.publish(self.service.finish(frame))
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=worker, name="owned-capture-race-fixture")
        thread.start()
        try:
            self.assertTrue(acquired.wait(2))
            self.service.request("new during capture")
        finally:
            resume.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(self.service.snapshot()["pending"]["reason"], "new during capture")

    def test_frame_envelope_survives_queue_serialization(self):
        frame = CapturedFrame(b"fixture pixels", self.frame(), "hash")
        self.assertEqual(pickle.loads(pickle.dumps(frame)), frame)

    def test_total_deadline_includes_settle_and_ignores_wall_clock_jump(self):
        self.service.request("slow settle", 10, timeout_seconds=5)
        self.wall += 3600
        self.assertEqual(self.service.demand_wait(), 5)
        self.tick(5)
        view = self.service.snapshot()
        self.assertFalse(view["pending"])
        self.assertEqual(view["current_failure"]["code"], "deadline_exceeded")
        self.assertEqual(view["current_failure"]["attempts"], 0)
        self.assertIsNone(self.service.begin("too late", require_demand=True))
        self.assertEqual(self.service.snapshot()["failed_request_count"], 1)

    def test_expired_native_acquisition_is_visible_until_it_returns(self):
        self.service.request("blocked", timeout_seconds=1)
        stamp = self.service.begin("blocked synthetic native call")
        self.tick(2)
        view = self.service.snapshot()
        self.assertEqual(view["acquisitions_inflight"][0]["status"], "discard_on_return")
        self.assertFalse(view["current_failure"]["native_call_cancelled"])
        self.assertFalse(self.publish(self.service.finish(stamp)))
        self.assertFalse(self.service.snapshot()["acquisitions_inflight"])
        self.assertEqual(self.service.snapshot()["completed_count"], 0)

    def test_final_failure_exhausts_attempts_and_explicit_retry_recovers(self):
        self.service.request("two tries", max_attempts=2)
        first = self.frame()
        self.service.fail("acquisition", OSError("private"), first)
        self.assertTrue(self.service.snapshot()["pending"])
        self.tick(.5)
        final = self.frame()
        self.assertEqual(final.request_attempt, 2)
        self.service.fail("publication", OSError("private"), final)
        failure = self.service.snapshot()["current_failure"]
        self.assertEqual((failure["code"], failure["attempts"]), ("attempts_exhausted", 2))
        self.assertNotIn("private", str(failure))
        self.assertIsNone(self.service.begin("no extra try", require_demand=True))
        self.service.request("explicit retry", timeout_seconds=10, max_attempts=1)
        self.service.fail("late old error", OSError(), final)
        self.assertTrue(self.publish(self.frame()))
        self.assertFalse(self.service.snapshot()["current_failure"])

    def test_heartbeat_cannot_bypass_attempt_budget_and_recapture_shares_attempt(self):
        self.service.request("one attempt", max_attempts=1)
        original = self.frame()
        self.assertIsNone(self.service.begin("heartbeat"))
        self.tick(.2)
        replacement = self.service.finish(self.service.begin("legacy recapture", parent=original))
        self.assertEqual(replacement.request_attempt, 1)
        self.assertEqual(self.service.snapshot()["pending"]["attempts"], 1)
        self.assertTrue(self.publish(replacement))

    def test_dropped_final_attempt_expires_without_infinite_recapture(self):
        self.service.request("dropped", max_attempts=1)
        dropped = self.frame()
        self.tick(1)
        self.assertIsNone(self.service.demand_wait())
        self.assertEqual(self.service.snapshot()["current_failure"]["code"], "attempts_exhausted")
        self.assertIsNone(self.service.begin("late recapture", parent=dropped))
        self.assertFalse(self.publish(dropped))

    def test_unlimited_compatibility_keeps_retrying(self):
        self.service.request("legacy unlimited")
        for _ in range(4):
            self.service.fail("acquisition", OSError(), self.frame())
            self.tick(1000)
            self.assertTrue(self.service.snapshot()["pending"])
        self.assertTrue(self.publish(self.frame()))
        self.assertEqual(self.service.snapshot()["failed_request_count"], 0)

    def test_old_error_or_publication_does_not_change_new_retry_backoff(self):
        self.service.request("old")
        old = self.frame()
        self.service.request("new", timeout_seconds=10)
        current = self.frame()
        self.service.fail("acquisition", OSError(), current)
        before = self.service.snapshot()["failure_count"]
        self.service.fail("old", OSError(), old)
        self.assertEqual(self.service.snapshot()["failure_count"], before)
        self.assertTrue(self.publish(old))
        self.assertEqual(self.service.retry_wait(), .5)
        self.assertEqual(self.service.snapshot()["pending"]["reason"], "new")

    def test_cancel_acknowledges_failure_without_erasing_terminal_evidence(self):
        self.service.request("expires", timeout_seconds=1)
        self.tick(1)
        failed = self.service.snapshot()["last_failure"]
        self.service.cancel("operator")
        self.assertFalse(self.service.snapshot()["current_failure"])
        self.assertEqual(self.service.snapshot()["last_failure"], failed)

    def test_invalid_request_limits_cannot_supersede_valid_request(self):
        self.service.request("keep")
        for values in ({"timeout_seconds": float("nan")}, {"timeout_seconds": -1}, {"timeout_seconds": True},
                       {"max_attempts": True}, {"max_attempts": 1.5}, {"max_attempts": -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.service.request("invalid", **values)
        self.assertEqual(self.service.snapshot()["pending"]["reason"], "keep")

    def test_stateful_capture_workers_share_authority_in_process_mode(self):
        def capture():
            pass
        def drawing():
            pass
        scope = {"USE_PROCESS_WORKERS": True, "threading": threading,
                 "screenshot_capture": capture, "drawing_worker": drawing,
                 "command_handler": lambda: None, "chatgpt_process": lambda: None}
        node = turn_flow.FUNCTIONS["start_process"]
        exec(compile(ast.Module(body=[node], type_ignores=[]), "worker_route", "exec"), scope)
        for target in (capture, drawing):
            worker = scope["start_process"](target, ())
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(worker.pid)

    def test_slow_publication_fence_does_not_delay_model_cancel_or_input_release(self):
        for name, args in (("set_agent_running", (False,)), ("cancel_active_work_command", ([], True))):
            with self.subTest(command=name):
                fenced, release = threading.Event(), threading.Event()
                effects, failures = [], []
                def fence(reason):
                    fenced.set()
                    if not release.wait(2):
                        raise AssertionError("fixture fence timed out")
                scope = {"agent_state": SimpleNamespace(running=True),
                         "MODEL_WORK": SimpleNamespace(cancel=lambda reason: effects.append("model_cancelled")),
                         "cancel_command_inputs": lambda reason: effects.append("inputs_released") or {"success": True},
                         "cancel_capture_requests": fence, "TASK_CONTINUATION_MODE": "legacy",
                         "validate_command_arguments": lambda *a: None, "append_runtime_feedback": lambda *a: None}
                exec(compile(ast.Module(body=[turn_flow.FUNCTIONS[name]], type_ignores=[]), "cancellation_order", "exec"), scope)
                def run():
                    try:
                        scope[name](*args)
                    except Exception as error:
                        failures.append(error)
                thread = threading.Thread(target=run, name="owned-capture-cancellation-fence-fixture")
                thread.start()
                try:
                    self.assertTrue(fenced.wait(1))
                    self.assertEqual(effects, ["model_cancelled", "inputs_released"])
                finally:
                    release.set()
                    thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertFalse(failures)


class VerifiedSchedulerTests(unittest.TestCase):
    setUp = turn_flow.TurnFlowTests.setUp
    decision = turn_flow.TurnFlowTests.decision
    pending_capture = turn_flow.TurnFlowTests.pending_capture

    def test_expiry_before_observation_binding_keeps_failed_request_identity(self):
        service = self.scope["CAPTURE_SERVICE"]
        generation = service.request("immediate", timeout_seconds=.1)
        self.now += 1
        self.scope.update(TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS=0,
                          get_demand_capture_settle_seconds=lambda value: value)
        exec(compile(ast.Module(body=[turn_flow.FUNCTIONS["mark_turn_scheduler_command_result_pending"]], type_ignores=[]),
                     "fast_expiry", "exec"), self.scope)
        self.scope["mark_turn_scheduler_command_result_pending"](request_capture=False)
        self.assertEqual(self.state["turn_scheduler_capture_request_generation"], generation)
        self.assertIn("deadline_exceeded", self.decision()["detail"])

    def test_failed_observation_blocks_background_but_allows_text_interruption(self):
        service = self.scope["CAPTURE_SERVICE"]
        generation = service.request("deadline", timeout_seconds=1)
        self.pending_capture()
        self.state["turn_scheduler_capture_request_generation"] = generation
        self.scope["TURN_SCHEDULER_MODE"] = "per_capture"
        self.scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = .1
        self.now += 2
        self.state["turn_scheduler_capture_counter"] = 3
        failure = self.decision()
        self.assertFalse(failure["should_run"])
        self.assertIn("deadline_exceeded", failure["detail"])
        interrupted = self.scope["evaluate_turn_scheduler"](input_pending=True)
        self.assertTrue(interrupted["should_run"])
        self.assertTrue(interrupted["omit_capture"])
        self.assertNotIn("command_result", interrupted["reasons"])
        self.assertTrue(self.state["turn_scheduler_pending_command_result"])
    def test_verified_stale_frame_blocks_heartbeat_and_legacy_is_selectable(self):
        service = self.scope["CAPTURE_SERVICE"]
        old = service.finish(service.begin("synthetic"))
        self.now += 1
        self.state["turn_scheduler_post_action_boundary"] = service.boundary()
        self.state["last_capture_frame"] = {"path": "old.png", "counter": 2, "provenance": old.to_dict()}
        self.pending_capture(wait_until=self.now)
        self.scope["CAPTURE_PROVENANCE_POLICY"] = "verified"
        self.scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = .1
        self.assertFalse(self.decision()["should_run"])
        self.scope["CAPTURE_PROVENANCE_POLICY"] = "legacy"
        self.assertTrue(self.decision()["should_run"])
        self.scope["CAPTURE_PROVENANCE_POLICY"] = "verified"
        fresh = service.finish(service.begin("synthetic"))
        self.state["last_capture_frame"]["provenance"] = fresh.to_dict()
        self.assertIn("command_result", self.decision()["reasons"])

    def test_dispatch_uses_selected_frame_not_later_publication(self):
        selected = {"path": "selected.png", "counter": 2, "hash": "selected", "timestamp": "then"}
        self.state["turn_scheduler_capture_counter"] = 99
        self.state["turn_scheduler_last_capture_hash"] = "later"
        self.scope["mark_turn_scheduler_dispatch"](["capture_tick"], capture_frame=selected, image_timestamp="then")
        self.assertEqual(self.state["turn_scheduler_last_submitted_capture_counter"], 2)
        self.assertEqual(self.state["turn_scheduler_last_submitted_capture_hash"], "selected")
        self.assertEqual(self.state["turn_scheduler_last_submitted_frame"]["path"], "selected.png")

    def test_operator_interrupt_omits_unproven_pixels_without_clearing_boundary(self):
        self.scope["CAPTURE_PROVENANCE_POLICY"] = "verified"
        self.pending_capture()
        self.inputs.put("Stop and explain")
        calls = []
        self.scope["send_prompt_to_chatgpt"] = lambda *a, **k: calls.append(k)
        self.assertTrue(self.scope["maybe_run_due_inference_turn"]())
        self.assertFalse(calls[0]["image_path"])
        self.assertTrue(self.state["turn_scheduler_pending_command_result"])

    def test_verified_settle_does_not_wait_for_wall_clock_to_catch_up(self):
        service = self.scope["CAPTURE_SERVICE"]
        self.scope["CAPTURE_PROVENANCE_POLICY"] = "verified"
        self.state["turn_scheduler_post_action_boundary"] = service.boundary()
        fresh = service.finish(service.begin("synthetic"))
        self.state["last_capture_frame"] = {"path": "fresh.png", "counter": 2, "provenance": fresh.to_dict()}
        self.pending_capture(wait_until=self.now + 999)
        self.assertIn("command_result", self.decision()["reasons"])

    def test_dispatch_does_not_clear_newer_observation_generation(self):
        self.pending_capture()
        self.state["turn_scheduler_observation_generation"] = 2
        self.scope["mark_turn_scheduler_dispatch"](["command_result"], observation_generation=1)
        self.assertTrue(self.state["turn_scheduler_pending_command_result"])
        self.scope["mark_turn_scheduler_dispatch"](["command_result"], observation_generation=2)
        self.assertFalse(self.state["turn_scheduler_pending_command_result"])


if __name__ == "__main__":
    unittest.main()
