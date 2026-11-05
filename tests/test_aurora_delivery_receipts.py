import ast
import pickle
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest

from aurora_delivery_receipts import (
    TrackedInput, TurnDelivery, queued_input_identities, current_delivery, delivery_turn,
)


REF = {"request_id": "request-1", "message_id": "message-1", "client_id": "panel"}


class DeliveryReceiptTests(unittest.TestCase):
    def test_queue_string_compatibility_pickling_and_distinct_identical_text(self):
        one = TrackedInput("same text", REF)
        two = TrackedInput("same text", dict(REF, request_id="request-2", message_id="message-2"))
        copied = pickle.loads(pickle.dumps(one))
        self.assertEqual(" ".join([one, "shell", two]), "same text shell same text")
        self.assertEqual(str(copied), "same text")
        self.assertEqual(queued_input_identities([one, copied, two, "shell"]), (REF, two.delivery_refs[0]))
        self.assertEqual(TrackedInput("unidentified", {"request_id": "partial"}).delivery_refs, ())

    def test_terminal_receipt_cannot_be_overwritten_by_late_success(self):
        rows = []
        with delivery_turn(lambda event, **row: rows.append(dict(event=event, **row)), [REF, REF]) as turn:
            self.assertIs(current_delivery(), turn)
            turn.emit("prepared", model="requested-model")
            turn.emit("submitted")
            turn.emit("cancelled", reason="Local cancellation")
            turn.emit("responded", provider_model="late-model")
        self.assertIsNone(current_delivery())
        self.assertEqual([r["phase"] for r in rows], ["preparing", "prepared", "submitted", "cancelled"])
        self.assertEqual(len({r["inference_request_id"] for r in rows}), 1)
        self.assertEqual([r["sequence"] for r in rows], [1, 2, 3, 4])
        self.assertTrue(rows[-1]["request_started"])
        self.assertFalse(rows[-1]["remote_cancellation_confirmed"])
        self.assertNotIn("text", rows[-1])

    def test_nested_turn_context_and_exception_restore_original(self):
        rows = []
        writer = lambda event, **row: rows.append(row)
        with delivery_turn(writer, [REF]) as outer:
            with self.assertRaisesRegex(RuntimeError, "original failure"):
                with delivery_turn(writer, [dict(REF, request_id="second")]):
                    raise RuntimeError("original failure")
            self.assertIs(current_delivery(), outer)
            outer.emit("responded", provider_model="provider-model")
        self.assertEqual(rows[-2]["phase"], "failed")
        self.assertEqual(rows[-1]["provider_model"], "provider-model")
        self.assertNotIn("original failure", str(rows))

    def test_broken_log_never_sends_or_masks_work(self):
        def broken(*args, **kwargs):
            raise OSError("fixture disk failure")
        with delivery_turn(broken, [REF]) as turn:
            turn.emit("prepared")
            turn.emit("failed")
        self.assertEqual(turn.receipt_errors, 3)
        untracked = TurnDelivery(broken, [])
        untracked.emit("submitted")
        self.assertEqual(untracked.receipt_errors, 0)

    def test_real_queue_coalescer_preserves_legacy_text_and_identity(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "handle_queued_input")
        inputs, calls = queue.Queue(), []
        scope = {"SEND_TO_MODEL": True, "ENABLE_MODEL_RESPONSES": True, "queue": queue,
                 "get_input_queue_store": lambda: inputs, "queued_input_identities": queued_input_identities,
                 "send_prompt_to_chatgpt": lambda *a, **kw: calls.append((a, kw))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "runtime-queue", "exec"), scope)
        inputs.put(TrackedInput("panel text", REF))
        inputs.put("shell text")
        self.assertTrue(scope["handle_queued_input"]("", "", wake_reason="test"))
        self.assertEqual(calls[0][0], ("user input: panel text shell text",))
        self.assertEqual(calls[0][1]["delivery_refs"], (REF,))
        self.assertTrue(inputs.empty())

    def test_embedding_and_validation_calls_do_not_claim_input_submission(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "post_openai_model_request")
        token = SimpleNamespace(check=lambda: None)
        response = SimpleNamespace(status_code=200)
        readback_calls = []
        scope = dict(AUTH_MODE="api_key", API_KEY="", CODEX_OAUTH_CACHE_FILE="", CODEX_OAUTH_AUTH_FILE="",
                     codex_oauth_cache_path="fixture", MODEL_WORK=SimpleNamespace(current=lambda: token),
                     current_delivery=current_delivery, service_runtime_control_during_model_wait=lambda: None,
                     COMMAND_READBACKS=SimpleNamespace(mark_request=lambda *args: readback_calls.append(args)),
                     MODEL_IO=SimpleNamespace(call=lambda *a, **kw: (response, "api_key", "fixture")),
                     update_auth_runtime_state=lambda *args: None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "runtime-transport", "exec"), scope)
        rows = []
        with delivery_turn(lambda event, **row: rows.append(row), [REF]) as turn:
            scope["post_openai_model_request"]({"model": "validation"}, "chat/completions")
            scope["post_openai_model_request"]({"model": "embeddings"}, "embeddings")
            self.assertFalse(turn.request_started)
            turn.emit("prepared", model="chat-model")
            scope["post_openai_model_request"]({"model": "embeddings"}, "embeddings")
            self.assertFalse(turn.request_started)
            scope["post_openai_model_request"]({"model": "chat-model"}, "chat/completions")
            self.assertTrue(turn.request_started)
        self.assertEqual([r["phase"] for r in rows], ["preparing", "prepared", "submitted", "failed"])
        self.assertEqual(rows[-1]["requested_model"], "chat-model")
        self.assertEqual(readback_calls, [(turn.inference_request_id, "submitted")])


if __name__ == "__main__":
    unittest.main()
