"""Production scheduler boundaries, exercised without importing native adapters."""
import ast
import copy
from aurora_capture_provenance import CaptureService
from pathlib import Path
import queue
from types import SimpleNamespace
import threading
import unittest

from aurora_runtime_work import CancellationDomain
from aurora_task_continuation import TaskContinuation, CommandReadbacks
from aurora_settings_registry import coerce_setting_value


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
FUNCTIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}


class StartupHeartbeatTests(unittest.TestCase):
    """Exercise the actual startup function without native/runtime imports."""

    def apply(self, value, initial=2.25):
        function = FUNCTIONS["apply_cli_args"]
        fields = {node.attr for node in ast.walk(function)
                  if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                  and node.value.id == "parsed_args"}
        arguments = SimpleNamespace(**dict.fromkeys(fields))
        arguments.turn_heartbeat_seconds = value
        scope = {"TURN_SCHEDULER_HEARTBEAT_SECONDS": initial,
                 "coerce_setting_value": coerce_setting_value,
                 "infer_turn_scheduler_profile_name": lambda: "custom"}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "startup", "exec"), scope)
        scope["apply_cli_args"](arguments)
        return scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"]

    def test_startup_preserves_explicit_off_and_valid_intervals(self):
        for value in (0, 0.1, 2.25, 30):
            with self.subTest(value=value):
                self.assertEqual(self.apply(value), value)
        self.assertEqual(self.apply(None), 2.25)

    def test_startup_rejects_invalid_intervals_instead_of_polling(self):
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.apply(value)


class TurnFlowTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.inputs = queue.Queue()
        self.state = {
            "last_screenshot_path": "frame-1.png", "last_screenshot_timestamp": "frame-1-time",
            "turn_scheduler_capture_counter": 1, "turn_scheduler_last_capture_hash": "hash-1",
            "turn_scheduler_last_submitted_capture_counter": 1,
            "turn_scheduler_last_submitted_capture_hash": "hash-1",
            "last_turn_completed_at_epoch": 90.0,
        }
        self.scope = {

            "INPUT_RECOVERY_LOCK": threading.RLock(), "get_input_recovery": lambda: None,            "runtime_state": self.state, "copy": copy, "CAPTURE_PROVENANCE_POLICY": "legacy",
            "CAPTURE_SERVICE": CaptureService(epoch=lambda: self.now, monotonic=lambda: self.now), "time": SimpleNamespace(time=lambda: self.now), "queue": queue,
            "SEND_TO_MODEL": True, "ENABLE_MODEL_RESPONSES": True,
            "CAPTURE_MODE": "request_only",
            "TASK_CONTINUATION_MODE": "legacy", "READBACK_WAKE_ENABLED": False, "READBACK_SCOPE": "discovery",
            "TASK_CONTINUATION": TaskContinuation(clock=lambda: self.now),
            "TURN_SCHEDULER_MODE": "event", "TURN_SCHEDULER_HEARTBEAT_SECONDS": 0,
            "TURN_SCHEDULER_MIN_GAP_SECONDS": 0, "TURN_SCHEDULER_CAPTURE_WAKE_ENABLED": True,
            "TURN_SCHEDULER_CAPTURE_WAKE_DEBOUNCE_SECONDS": 0,
            "MODEL_IO": SimpleNamespace(busy=False), "COMMAND_WORK": CancellationDomain(),
            "active_command_queue": None, "active_runtime_context": None,
            "normalize_text_content": lambda text: str(text or ""),
            "set_runtime_value": self.state.__setitem__, "get_input_queue_store": lambda: self.inputs,
            "summarize_runtime_text": lambda text, **kwargs: text,
            "build_turn_scheduler_summary": lambda: "fixture scheduler",
            "queued_input_identities": lambda rows: (),
            "split_commands_preserving_parentheses": lambda text: text.split(";"),
            "DEFAULT_SCREENSHOT_REVIEW_PROMPT": "Review fixture image",
        }
        for name in ("evaluate_turn_scheduler", "clear_turn_scheduler_command_result_pending",
                     "mark_turn_scheduler_dispatch", "handle_queued_input", "maybe_run_due_inference_turn",
                     "should_request_turn_after_command_result"):
            exec(compile(ast.Module(body=[FUNCTIONS[name]], type_ignores=[]), "scheduler", "exec"), self.scope)

    def decision(self):
        return self.scope["evaluate_turn_scheduler"]()

    def test_reviewed_readback_cannot_bypass_observation_boundary(self):
        task = self.scope["TASK_CONTINUATION"]
        task.reserve(max_turns=8, max_seconds=120)
        store = CommandReadbacks()
        store.publish(dict(command_batch_id="mixed-batch", task_id=task.snapshot()["task_id"],
                           inference_request_id="origin-turn", setting_results=[{"success": True}]))
        self.scope.update(TASK_CONTINUATION_MODE="bounded", READBACK_SCOPE="reviewed",
                          READBACK_WAKE_ENABLED=True, COMMAND_READBACKS=store)
        self.pending_capture()
        self.assertFalse(self.decision()["should_run"])
        self.state["turn_scheduler_capture_counter"] = 2
        self.assertIn("command_readback", self.decision()["reasons"])
        self.assertIn("command_result", self.decision()["reasons"])
        self.assertEqual(store.pending(task.snapshot()["task_id"]), 1)

    def pending_capture(self, required=2, wait_until=100.0):
        self.state.update(turn_scheduler_pending_command_result=True,
                          turn_scheduler_required_capture_after_action=required,
                          turn_scheduler_post_action_wait_until_epoch=wait_until)

    def test_response_capture_request_survives_dispatch_acknowledgement(self):
        self.inputs.put("Continue the task")
        def response(*args, **kwargs):
            self.pending_capture()
        self.scope["send_prompt_to_chatgpt"] = response
        self.assertTrue(self.scope["maybe_run_due_inference_turn"]())
        self.assertTrue(self.state["turn_scheduler_pending_command_result"])
        self.state["turn_scheduler_capture_counter"] = 2  # unchanged pixels are still a new observation
        self.assertIn("command_result", self.decision()["reasons"])

    def test_background_capture_is_not_claimed_as_already_submitted(self):
        self.inputs.put("Describe frame 1")
        seen = []
        def response(*args, **kwargs):
            seen.append(kwargs["image_path"])
            self.state.update(turn_scheduler_capture_counter=2, turn_scheduler_last_capture_hash="hash-2",
                              last_screenshot_path="frame-2.png")
        self.scope["send_prompt_to_chatgpt"] = response
        self.assertTrue(self.scope["maybe_run_due_inference_turn"]())
        self.assertEqual(seen, ["frame-1.png"])
        self.assertEqual(self.state["turn_scheduler_last_submitted_capture_counter"], 1)
        self.assertEqual(self.state["turn_scheduler_last_submitted_capture_hash"], "hash-1")

    def test_capture_and_heartbeat_cannot_bypass_post_action_wait(self):
        for mode in ("event", "hybrid", "per_capture"):
            with self.subTest(mode=mode):
                self.scope["TURN_SCHEDULER_MODE"] = mode
                self.scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = 1
                self.pending_capture(wait_until=101)
                self.state.update(turn_scheduler_capture_counter=2, turn_scheduler_last_capture_hash="hash-2")
                self.assertFalse(self.decision()["should_run"])
                self.now = 102
                self.assertTrue(self.decision()["should_run"])
                self.now = 100

    def test_missing_required_capture_waits_even_if_heartbeat_is_due(self):
        self.pending_capture()
        self.scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = 1
        self.assertFalse(self.decision()["should_run"])

    def test_explicit_operator_input_can_interrupt_capture_wait(self):
        self.pending_capture(wait_until=110)
        result = self.scope["evaluate_turn_scheduler"](input_pending=True)
        self.assertTrue(result["should_run"])
        self.assertIn("user_input", result["reasons"])

    def test_command_batch_and_undrained_results_block_new_turn(self):
        self.scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = 1
        with self.scope["COMMAND_WORK"].scope():
            self.assertFalse(self.decision()["should_run"])
        commands = queue.Queue()
        commands.put({"command": "fixture"})
        self.scope["active_command_queue"] = commands
        self.assertFalse(self.decision()["should_run"])
        commands.get_nowait()
        self.assertFalse(self.decision()["should_run"])  # dequeue-to-scope gap
        commands.task_done()
        results = queue.Queue()
        results.put({"success": True})
        self.scope["active_runtime_context"] = SimpleNamespace(command_result_queue=results)
        self.assertFalse(self.decision()["should_run"])
        results.get_nowait()
        self.assertTrue(self.decision()["should_run"])

    def test_paused_does_not_acknowledge_capture_or_consume_input(self):
        self.scope["SEND_TO_MODEL"] = False
        self.inputs.put("Keep my message")
        self.state["turn_scheduler_capture_counter"] = 2
        self.assertFalse(self.scope["maybe_run_due_inference_turn"]())
        self.assertEqual(self.inputs.qsize(), 1)
        self.assertEqual(self.state["turn_scheduler_last_submitted_capture_counter"], 1)

    def test_no_request_does_not_poll_model_with_heartbeat_disabled(self):
        self.assertFalse(self.decision()["should_run"])

    def test_readback_dispatches_without_image_and_preserves_new_readbacks(self):
        self.scope.update(TASK_CONTINUATION_MODE="bounded", READBACK_WAKE_ENABLED=True)
        task = self.scope["TASK_CONTINUATION"]
        task.publish_readback("lookup")
        seen = []
        def response(*args, **kwargs):
            seen.append(kwargs)
            task.publish_readback("next lookup")
        self.scope["send_prompt_to_chatgpt"] = response
        self.assertTrue(self.scope["maybe_run_due_inference_turn"]())
        self.assertNotIn("image_path", seen[0])
        self.assertEqual(seen[0]["wake_reason"], "command_readback")
        self.assertTrue(task.readback()["pending"])

    def test_readback_does_not_bypass_batch_capture_boundary_or_stopped_task(self):
        self.scope.update(TASK_CONTINUATION_MODE="bounded", READBACK_WAKE_ENABLED=True)
        task = self.scope["TASK_CONTINUATION"]
        task.publish_readback("lookup")
        self.pending_capture(wait_until=110)
        self.assertFalse(self.decision()["should_run"])
        self.state.update(turn_scheduler_capture_counter=2)
        self.now = 111
        self.assertTrue(self.decision()["should_run"])
        task.reserve(max_turns=1, max_seconds=10)
        task.stop("operator_cancelled")
        self.assertFalse(self.decision()["should_run"])
        self.assertTrue(self.scope["evaluate_turn_scheduler"](input_pending=True)["should_run"])

    def test_readback_toggle_does_not_expand_legacy_scheduler(self):
        self.scope["READBACK_WAKE_ENABLED"] = True
        self.scope["TASK_CONTINUATION"].publish_readback("lookup")
        self.assertFalse(self.decision()["should_run"])

    def test_operator_interruption_does_not_erase_pending_observation(self):
        self.pending_capture(wait_until=110)
        self.inputs.put("Give me a status update")
        self.scope["send_prompt_to_chatgpt"] = lambda *args, **kwargs: None
        self.assertTrue(self.scope["maybe_run_due_inference_turn"]())
        self.assertTrue(self.state["turn_scheduler_pending_command_result"])

    def test_only_this_batch_effects_drive_capture_not_stale_worker_fields(self):
        followup = self.scope["should_request_turn_after_command_result"]
        self.assertFalse(followup({"executed_commands": ["UPDATE_CONTEXT(No change)"],
                                  "desktop_results": [], "worker_last_key": "right"}))
        self.assertTrue(followup({"status": "cancelled", "executed_commands": [],
                                 "desktop_results": [{"effect_status": "uncertain", "success": False}]}))
        self.assertFalse(followup({"status": "cancelled", "executed_commands": [],
                                  "desktop_results": [{"effect_status": "not_started", "success": False}]}))
        self.assertTrue(followup({"worker_last_key": "legacy-field"}))


if __name__ == "__main__":
    unittest.main()
