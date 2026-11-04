import ast
import re
import queue
import unittest
from pathlib import Path

from aurora_conversation import build_conversation_snapshot, build_conversation_view, conversation_text, build_init_context, build_prompt_materials
from aurora_responses_reasoning import ASTRA_MODEL, ASTRA_EFFORTS


def message(text, role="user"):
    return {"role": role, "content": {"type": "text", "text": text}, "timestamp": "2026-11-04"}


class ConversationTests(unittest.TestCase):
    def test_attribution_and_display_preferences_preserve_message(self):
        entry = message("[2026-11-04] Answer", "assistant")
        entry.update(timestamp_iso="2026-11-04T15:00:00-08:00", model="gpt-6.1-sol",
                     model_source="provider_reported", edited_by="model:gpt-6-astra",
                     edited_at="2026-11-04T15:01:00-08:00")
        view = build_conversation_view([entry], source="test")
        shown = conversation_text(view)
        for value in (entry["timestamp_iso"], entry["model"], entry["edited_by"], entry["edited_at"]):
            self.assertIn(value, shown)
        compact = conversation_text(view, show_time=False, show_model=False, show_edits=False)
        self.assertEqual(compact.strip(), "Assistant  \nAnswer")
        self.assertEqual(entry["content"]["text"], "[2026-11-04] Answer")

    def test_missing_and_requested_model_attribution_are_explicit(self):
        entry = message("Answer", "assistant")
        self.assertIn("model unknown", conversation_text(build_conversation_view([entry], source="test")))
        entry.update(model="gpt-6-astra", model_source="requested")
        self.assertIn("gpt-6-astra (requested)", conversation_text(build_conversation_view([entry], source="test")))

    def test_init_reports_loaded_text_and_limit_without_reading_configured_file(self):
        view = build_init_context("  loaded content  ", source="short profile", profile="current",
                                  configured_file="missing-file.txt", configured_mode="load", prompt_limit=6)
        self.assertEqual(view["text"], "loaded")
        self.assertEqual(view["total_chars"], 14)
        self.assertTrue(view["truncated"])
        self.assertEqual(view["source"], "short profile")

    def test_prepared_components_are_bounded_and_not_claimed_delivered(self):
        view = build_prompt_materials(system="s"*25000, memory="goals", current="question",
                                      retrieval="", prepared_at="2026-11-04T12:00:00", model="test-model")
        self.assertEqual(len(view["sections"]["system"]["text"]), 24000)
        self.assertTrue(view["sections"]["system"]["truncated"])
        self.assertEqual(view["sections"]["memory"]["text"], "goals")
        self.assertIn("does not prove delivery", view["note"])
        self.assertEqual(view["sections"]["retrieval"]["total_chars"], 0)

    def test_current_window_and_retained_are_distinct_and_deletion_disappears(self):
        old, current = message("old"), message("current", "assistant")
        state = {"history_store": [old, current], "recent_prompt_history": [current]}
        before = build_conversation_snapshot(state)
        self.assertNotIn("old", conversation_text(before["current"]))
        self.assertIn("old", conversation_text(before["retained"]))
        state["history_store"].remove(current)
        state["recent_prompt_history"].clear()
        after = build_conversation_snapshot(state)
        self.assertEqual(after["current"]["rows"], [])
        self.assertNotIn("current", conversation_text(after["retained"]))
        self.assertIn("current", conversation_text(before["current"]))

    def test_effective_omissions_can_empty_current_without_falling_back(self):
        row = message("excluded")
        view = build_conversation_snapshot({"history_store": [row], "recent_prompt_history": [row]}, [])
        self.assertEqual(view["current"]["rows"], [])
        self.assertEqual(view["retained"]["total"], 1)

    def test_image_bytes_are_not_exported_and_multiline_text_is_preserved(self):
        rows = [message("one\ntwo"), {"role": "user", "content": {"type": "image", "data": "PRIVATE_BASE64"}}]
        view = build_conversation_view(rows, source="test")
        text = conversation_text(view)
        self.assertIn("one\ntwo", text)
        self.assertIn("Screenshot", text)
        self.assertNotIn("PRIVATE_BASE64", str(view))

    def test_limits_keep_newest_and_disclose_omission(self):
        view = build_conversation_view([message(str(i) * 100) for i in range(5)], source="test",
                                       max_chars=30, max_message_chars=20, max_rows=3)
        self.assertGreater(view["omitted"], 0)
        self.assertGreater(view["shortened"], 0)
        self.assertIn("444", view["rows"][-1]["text"])


class ModelCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
        names = {"uses_max_completion_tokens", "supports_reasoning_effort", "_parse_gpt_model_version",
                 "get_supported_reasoning_efforts", "supports_temperature_override", "supports_model_verbosity"}
        cls.scope = {"re": re, "ASTRA_MODEL": ASTRA_MODEL, "ASTRA_EFFORTS": ASTRA_EFFORTS,
                     "normalize_memory_item": str, "ALLOWED_REASONING_EFFORTS": {"none", "minimal", "low", "medium", "high", "xhigh", "max"}}
        exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[]), "runtime-model-functions", "exec"), cls.scope)

    def test_sol_and_astra_request_compatibility(self):
        for model in ("gpt-6.1-sol", "gpt-6-astra"):
            with self.subTest(model=model):
                self.assertTrue(self.scope["uses_max_completion_tokens"](model))
                self.assertTrue(self.scope["supports_model_verbosity"](model))
                self.assertFalse(self.scope["supports_temperature_override"](model))
                self.assertEqual(self.scope["get_supported_reasoning_efforts"](model), set(ASTRA_EFFORTS))

    def test_older_and_other_models_preserved(self):
        self.assertIn("none", self.scope["get_supported_reasoning_efforts"]("gpt-5.4"))
        self.assertIn("none", self.scope["get_supported_reasoning_efforts"]("gpt-6.1-terra"))
        self.assertTrue(self.scope["supports_temperature_override"]("gpt-4o"))

    def test_paused_inference_keeps_queued_messages(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "handle_queued_input")
        messages = queue.Queue()
        messages.put("Keep this draft")
        scope = {"SEND_TO_MODEL": False, "ENABLE_MODEL_RESPONSES": True, "get_input_queue_store": lambda: messages}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "runtime-queue", "exec"), scope)
        self.assertFalse(scope["handle_queued_input"]("", ""))
        self.assertEqual(messages.get_nowait(), "Keep this draft")


if __name__ == "__main__":
    unittest.main()
