import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from aurora_switchboard import command_draft, validate_switchboard_batch, switchboard_flow, context_contents, preview_default_changes, next_inference_label
from aurora_settings_registry import coerce_setting_value
from aurora_settings_transactions import build_setting_command_invocation

ROOT = Path(__file__).resolve().parents[1]


class SwitchboardTests(unittest.TestCase):
    def test_empty_plan_is_not_a_queued_override(self):
        self.assertEqual(next_inference_label({}), "unknown")
        self.assertEqual(next_inference_label({"planning": {"next_inference": {"model": "", "target_turn": 0, "source": "default"}}}), "none")
        self.assertEqual(next_inference_label({"planning": {"next_inference": {"temperature": 0}}}), "queued")
    def test_preview_reset_is_paused_bounded_and_preserves_auth(self):
        baseline = {row["key"]: row["value"] for row in preview_default_changes()}
        self.assertEqual(len(baseline), 22)
        self.assertFalse(baseline["runtime.live"])
        self.assertEqual(baseline["runtime.execution"], "safe")
        self.assertEqual(baseline["runtime.action"], "none")
        self.assertEqual(baseline["capture.mode"], "request_only")
        self.assertNotIn("auth.mode", baseline)
        self.assertNotIn("game.profile", baseline)

    def test_context_inspection_keeps_current_and_prepared_evidence_separate(self):
        state = {"init_context": {"text": "loaded init", "source": "test profile"},
                 "conversation": {"current": {"rows": [{"role": "user", "text": "new question"}]}},
                 "prompt_materials": {"prepared_at": "earlier", "sections": {"current": {"text": "old question"}}}}
        self.assertIn("loaded init", context_contents(state, "init"))
        self.assertIn("new question", context_contents(state, "conversation"))
        self.assertNotIn("old question", context_contents(state, "conversation"))
        self.assertIn("old question", context_contents(state, "current"))
        self.assertIn("unknown", context_contents({}, "screen"))
        self.assertIn("No request preparation", context_contents({}, "system"))

    def test_flow_details_remain_connected_at_each_level(self):
        for level, count in (("Overview", 3), ("Groups", 4), ("Functions", 8)):
            graph = switchboard_flow({}, level=level)
            self.assertEqual(len(graph["nodes"]), count)
            for edge in graph["edges"]:
                self.assertLess(edge["from"], count)
                self.assertLess(edge["to"], count)
            self.assertTrue(all(node["destination"] for node in graph["nodes"]))

    def test_drafts_require_explicit_arguments(self):
        self.assertEqual(command_draft({"command": "SHOW_RUNTIME", "signature": "SHOW_RUNTIME()"}), "SHOW_RUNTIME()")
        self.assertEqual(command_draft({"command": "SET_CAPTURE_MODE", "signature": "SET_CAPTURE_MODE(mode)"}), "SET_CAPTURE_MODE(<mode>)")
        self.assertEqual(command_draft({"command": "UNKNOWN", "signature": "UNKNOWN"}), "UNKNOWN(<arguments>)")

    def test_prepare_placeholders_and_invalid_batches_cannot_queue(self):
        rows = [{"command": name} for name in ("SHOW_RUNTIME", "SET_CAPTURE_MODE")]
        for text in ("", "SHOW_RUNTIME(); NOT_REAL()", "SET_CAPTURE_MODE(<mode>)", "SHOW_RUNTIME("):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_switchboard_batch(text, rows)
        self.assertEqual(len(validate_switchboard_batch("SHOW_RUNTIME(); SET_CAPTURE_MODE(request_only)", rows)), 2)

    def test_flow_distinguishes_capture_and_inference_and_staleness(self):
        state = {"processes": {"runtime": {"active": True}},
                 "modes": {"live": False, "capture_mode": "heartbeat", "effective_screenshot_interval": 10},
                 "scheduler": {"mode": "hybrid", "heartbeat_seconds": 2, "demand_capture_enabled": True}}
        graph = switchboard_flow(state, fresh=True)
        self.assertTrue(graph["loops"][0]["on"])
        self.assertFalse(graph["loops"][1]["on"])
        self.assertEqual(graph["loops"][0]["label"], "Capture 10s")
        state["modes"].update(live=True, capture_mode="request_only")
        graph = switchboard_flow(state, fresh=True)
        self.assertFalse(graph["loops"][0]["on"])
        self.assertTrue(graph["loops"][1]["on"])
        for node in switchboard_flow(state, fresh=False)["nodes"]:
            self.assertFalse(node["on"])
        self.assertIn("unknown", switchboard_flow({})["nodes"][0]["detail"])

    def test_capture_mode_contract(self):
        self.assertEqual(build_setting_command_invocation("capture.mode", "request_only"), ("SET_CAPTURE_MODE", ["request_only"], "SET_CAPTURE_MODE(request_only)"))
        with self.assertRaises(ValueError):
            coerce_setting_value("capture.mode", "offf")

    def test_capture_wait_request_only_never_periodically_captures(self):
        tree = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        scope = {"CAPTURE_MODE": "heartbeat", "time": SimpleNamespace(time=lambda: 100),
                 "get_next_demand_capture_due_at": lambda now: 0}
        exec(compile(ast.Module(body=[functions["get_next_screenshot_capture_wait_seconds"]], type_ignores=[]), "capture", "exec"), scope)
        wait = scope["get_next_screenshot_capture_wait_seconds"]
        self.assertEqual(wait(0), 0)
        self.assertEqual(wait(110), 10)
        scope["CAPTURE_MODE"] = "request_only"
        self.assertEqual(wait(0), 3600)
        scope["get_next_demand_capture_due_at"] = lambda now: 104
        self.assertEqual(wait(0), 4)
        scope["get_next_demand_capture_due_at"] = lambda now: 99
        self.assertEqual(wait(0), 0)
        scope["CAPTURE_MODE"] = "heartbeat"
        self.assertEqual(wait(101), 0)


if __name__ == "__main__":
    unittest.main()
