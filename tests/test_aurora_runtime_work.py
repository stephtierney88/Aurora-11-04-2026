"""Cancellation races, real dispatcher receipts, and immutable capture identity."""
import ast
from aurora_capture_provenance import CaptureService
import datetime
import hashlib
import math
import queue
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_aurora_command_ingress as ingress
from aurora_capture_store import save_capture
from aurora_runtime_work import BoundedModelIO, CancellationDomain, WorkCancelled


class ModelWorkTests(unittest.TestCase):
    def test_cancel_returns_promptly_discards_late_reply_and_bounds_workers(self):
        domain, io = CancellationDomain(), BoundedModelIO()
        entered, release = threading.Event(), threading.Event()
        seen, returned, errors = [], [], []
        packet = {"messages": [{"text": "original"}], "auth": {"mode": "original"}, "payload": {"model": "model-A"}}

        def transport(frozen):
            seen.append(frozen)
            entered.set()
            release.wait(60)  # Simulate a blocked provider; released by test cleanup.
            return "SET_TIME_LOGGING(on)"

        def caller():
            try:
                returned.append(io.call(transport, packet, domain.token()))
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=caller, daemon=True)
        worker.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(1))
        self.assertEqual(io.snapshot()["requested_model"], "model-A")
        packet["payload"]["model"] = "model-B"
        packet["messages"][0]["text"] = "changed"
        packet["auth"]["mode"] = "changed"
        started = time.perf_counter()
        domain.cancel("stop")
        worker.join(0.5)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertIsInstance(errors[0], WorkCancelled)
        self.assertEqual(returned, [])
        self.assertEqual(seen[0]["messages"][0]["text"], "original")
        self.assertEqual(seen[0]["auth"]["mode"], "original")
        self.assertEqual(io.snapshot()["state"], "draining")
        self.assertEqual(io.snapshot()["requested_model"], "model-A")

        # Cancellation while waiting for the occupied slot cannot start a second request.
        next_token = domain.token()
        with self.assertRaises(WorkCancelled):
            io.call(transport, packet, next_token, service_control=lambda: domain.cancel("stop again"))
        self.assertEqual(len(seen), 1)
        release.set()
        deadline = time.monotonic() + 1
        while io.busy and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(io.busy)
        self.assertEqual(io.snapshot()["discarded_results"], 1)
        self.assertEqual(io.snapshot()["requested_model"], "")
        self.assertEqual(io.call(lambda frozen: frozen, {"ok": True}, domain.token()), {"ok": True})

    def test_service_can_cancel_before_transport_completes(self):
        domain, io = CancellationDomain(), BoundedModelIO()
        release = threading.Event()
        self.addCleanup(release.set)
        with self.assertRaises(WorkCancelled):
            io.call(lambda _: release.wait(60), {}, domain.token(),
                    service_control=lambda: domain.cancel("control received"))

    def test_cancelled_token_never_starts_transport(self):
        domain, io = CancellationDomain(), BoundedModelIO()
        token = domain.token()
        domain.cancel("already stopped")
        calls = []
        with self.assertRaises(WorkCancelled):
            io.call(lambda packet: calls.append(packet), {}, token)
        self.assertFalse(io.busy)
        self.assertEqual(calls, [])


class RuntimeCancellationTests(unittest.TestCase):
    def setUp(self):
        self.harness = ingress.RuntimeIngressTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.scope = self.harness.scope
        self.scope.update({"queue": queue, "threading": threading, "traceback": traceback,
                           "math": math, "cancel_capture_requests": lambda reason: None, "is_agent_running": lambda: True, "TASK_CONTINUATION_MODE": "legacy"})
        names = ["wait_command", "cancel_active_work_command", "command_handler",
                 "pyautogui_hold", "pyautogui_hold_click", "handle_pyautogui_command",
                 "persist_runtime_capture", "perform_model_http_request", "set_live_mode",
                 "should_request_turn_after_command_result"]
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), self.scope)
        self.scope["command_dispatch"].update({"WAIT": self.scope["wait_command"],
                                              "CANCEL_ACTIVE_WORK": self.scope["cancel_active_work_command"]})

    def test_stop_overtakes_wait_keeps_receipts_and_cancels_queued_batch(self):
        self.harness.authorize()
        self.scope["active_command_queue"] = queue.Queue()
        self.harness.send("SHOW_RUNTIME(); WAIT(60); SHOW_AUTH()", "long")
        self.harness.send("SHOW_AUTH()", "queued")
        self.harness.poll()
        work_queue = self.scope["active_command_queue"]
        active = work_queue.get_nowait()
        queued = work_queue.get_nowait()
        results = []
        runner = threading.Thread(target=lambda: results.append(self.scope["execute_command_entry"](active)), daemon=True)
        runner.start()
        self.addCleanup(lambda: self.scope["COMMAND_WORK"].cancel("test cleanup"))
        deadline = time.monotonic() + 1
        while not self.harness.executed and time.monotonic() < deadline:
            time.sleep(0.001)
        started = time.perf_counter()
        self.harness.send("CANCEL_ACTIVE_WORK()", "cancel")
        self.harness.poll()
        runner.join(0.5)
        self.assertFalse(runner.is_alive())
        self.assertLess(time.perf_counter() - started, 0.5)
        receipt = next(row for row in self.harness.events if row.get("request_id") == "cancel" and row["event"] == "command_result")
        self.assertEqual(receipt["status"], "processed")
        self.assertTrue(receipt["mutation_admission_id"])
        self.assertEqual(results[0]["status"], "cancelled")
        self.assertEqual(results[0]["executed_commands"], ["SHOW_RUNTIME()"])
        self.assertEqual(results[0]["cancelled_commands"], ["WAIT(60)", "SHOW_AUTH()"])
        cancelled = self.scope["execute_command_entry"](queued)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["executed_commands"], [])
        self.assertEqual([name for name, _ in self.harness.executed], ["SHOW_RUNTIME"])
        # A fresh, intentional request is still available after one-shot cancellation.
        fresh = self.scope["handle_commands"]("SHOW_AUTH()")
        self.assertTrue(fresh["success"])

    def test_locked_stop_still_requires_authorization(self):
        generation = self.scope["COMMAND_WORK"].token().generation
        self.harness.send("CANCEL_ACTIVE_WORK()", "locked")
        self.harness.poll()
        self.assertEqual(self.scope["COMMAND_WORK"].token().generation, generation)
        receipt = next(row for row in self.harness.events if row["event"] == "command_result")
        self.assertEqual(receipt["status"], "rejected")

    def test_commands_admitted_after_shutdown_do_not_start(self):
        self.scope["is_agent_running"] = lambda: False
        result = self.scope["handle_commands"]("SHOW_RUNTIME(); SET_TIME_LOGGING(on)")
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["executed_commands"], [])
        self.assertEqual(self.harness.executed, [])

    def test_cancelled_unexecuted_batch_does_not_schedule_an_action_followup(self):
        result = {"status": "cancelled", "action": "pyag:press(a)",
                  "executed_commands": [], "worker_last_command": "pyag:press(a)"}
        self.assertFalse(self.scope["should_request_turn_after_command_result"](result))
        result["executed_commands"] = ["pyag:press(a)"]
        self.assertTrue(self.scope["should_request_turn_after_command_result"](result))

    def test_mixed_stop_batch_does_not_overtake_queue(self):
        self.scope["active_command_queue"] = queue.Queue()
        self.scope["enqueue_or_execute_command"]("WAIT(0); CANCEL_ACTIVE_WORK()", True)
        self.assertEqual(self.scope["active_command_queue"].qsize(), 1)

    def test_live_off_cancels_model_and_honors_existing_setting_lock(self):
        domain = self.scope["MODEL_WORK"]
        token = domain.token()
        def locked(*args):
            raise RuntimeError("locked")
        self.scope["require_runtime_setting_unlocked"] = locked
        with self.assertRaises(RuntimeError):
            self.scope["set_live_mode"](False)
        token.check()
        self.scope["require_runtime_setting_unlocked"] = lambda *args: None
        self.scope["set_live_mode"](False)
        with self.assertRaises(WorkCancelled):
            token.check()
        self.assertFalse(self.scope["SEND_TO_MODEL"])
        self.assertFalse(self.scope["ENABLE_MODEL_RESPONSES"])

    def test_repeated_commands_keep_cancelled_occurrence(self):
        count = []
        def handler(args, is_user):
            count.append(1)
            if len(count) == 2:
                self.scope["COMMAND_WORK"].cancel("stop")
                self.scope["COMMAND_WORK"].current().check()
        self.scope["command_dispatch"]["SHOW_AUTH"] = handler
        result = self.scope["handle_commands"]("SHOW_AUTH(); SHOW_AUTH(); SHOW_RUNTIME()")
        self.assertEqual(result["executed_commands"], ["SHOW_AUTH()"])
        self.assertEqual(result["cancelled_commands"], ["SHOW_AUTH()", "SHOW_RUNTIME()"])

    def test_wait_rejects_nonfinite_negative_and_missing_duration(self):
        for text in ("WAIT()", "WAIT(nan)", "WAIT(inf)", "WAIT(-1)", "WAIT(1, 2)"):
            with self.subTest(text=text):
                self.assertFalse(self.scope["handle_commands"](text)["success"])

    def test_timed_holds_release_once_and_never_fall_back_after_cancel(self):
        for function, args, game in (("pyautogui_hold_click", ["1", "2", "60"], False),
                                     ("pyautogui_hold", ["a", "60"], False),
                                     ("pyautogui_hold", ["a", "60"], True)):
            with self.subTest(function=function, game=game):
                domain, pressed, calls = CancellationDomain(), threading.Event(), []
                self.scope["COMMAND_WORK"] = domain
                def down(*args, **kwargs):
                    calls.append("down")
                    pressed.set()
                    return "keyboard"
                def up(*args, **kwargs):
                    calls.append("up")
                self.scope.update({"pyautogui": SimpleNamespace(mouseDown=down, mouseUp=up, keyDown=down, keyUp=up, KEYBOARD_KEYS=["a"], _normalizeButton=lambda button: button),
                    "keyboard": SimpleNamespace(press=down, release=up, key_to_scan_codes=lambda key: (key,)),
                    "get_game_input_backend": lambda: "keyboard",
                    "is_valid_keyboard_key_token": lambda key: True, "set_last_key_value": lambda key: None,
                    "should_use_game_input_backend": lambda key: game, "EMULATOR_WINDOW_TITLE_HINT": "test",
                    "focus_game_input_target": lambda hint: {"success": True},
                    "record_focus_recovery_result": lambda *args: None, "translate_game_backend_key": lambda key: key,
                    "game_backend_key_down": down, "game_backend_key_up": up})
                errors = []
                def run():
                    try:
                        with domain.scope():
                            self.scope[function](args)
                    except WorkCancelled as error:
                        errors.append(error)
                worker = threading.Thread(target=run, daemon=True)
                worker.start()
                self.assertTrue(pressed.wait(1))
                domain.cancel("stop")
                worker.join(0.5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(calls, ["down", "up"])
                self.assertEqual(len(errors), 1)

    def test_cancel_prevents_oauth_retry(self):
        domain, posts, refreshes = CancellationDomain(), [], []
        class Manager:
            def __init__(self, **kwargs):
                self.cache_path = kwargs["cache_path"]
            def get_api_access_token(self, force_refresh=False):
                refreshes.append(force_refresh)
                return "test-token"
        def post(*args, **kwargs):
            posts.append(1)
            domain.cancel("stop after 401")
            return SimpleNamespace(status_code=401)
        self.scope.update({"Path": Path, "CodexOAuthManager": Manager, "CodexOAuthError": ValueError,
                           "requests": SimpleNamespace(post=post)})
        packet = {"url": "https://example.invalid", "payload": {}, "timeout": 60,
                  "auth": {"mode": "codex_oauth", "api_key": "", "cache_path": "unused", "auth_path": ""}}
        token = domain.token()
        with self.assertRaises(WorkCancelled):
            self.scope["perform_model_http_request"](packet, token)
        self.assertEqual(posts, [1])
        self.assertEqual(refreshes, [False])


class CaptureTests(unittest.TestCase):
    class Image:
        def __init__(self, value):
            self.value = value
        def save(self, output, format):
            output.write(self.value)

    def test_burst_and_clock_rollback_cannot_overwrite_history(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("aurora_capture_store.time.time_ns", side_effect=[100] * 30 + [1] * 30):
                paths = [save_capture(self.Image(str(i).encode()), folder) for i in range(60)]
            self.assertEqual(len(set(paths)), 60)
            self.assertEqual([Path(p).read_bytes() for p in paths], [str(i).encode() for i in range(60)])
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    def test_collision_preserves_existing_file_and_uses_new_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "5-same.png"
            old.write_bytes(b"original")
            with patch("aurora_capture_store.time.time_ns", return_value=5), patch(
                    "aurora_capture_store.uuid.uuid4", side_effect=[SimpleNamespace(hex="same"), SimpleNamespace(hex="new")]):
                new = save_capture(self.Image(b"new"), folder)
            self.assertEqual(old.read_bytes(), b"original")
            self.assertEqual(Path(new).read_bytes(), b"new")

    def test_failed_encode_and_temp_collision_do_not_publish_or_delete_foreign_file(self):
        with tempfile.TemporaryDirectory() as folder:
            foreign = Path(folder) / ".5-same.tmp"
            foreign.write_bytes(b"owned by another writer")
            with patch("aurora_capture_store.time.time_ns", return_value=5), patch(
                    "aurora_capture_store.uuid.uuid4", return_value=SimpleNamespace(hex="same")):
                with self.assertRaises(FileExistsError):
                    save_capture(self.Image(b"new"), folder)
            self.assertEqual(foreign.read_bytes(), b"owned by another writer")
            self.assertFalse(list(Path(folder).glob("*.png")))
            class Broken:
                def save(self, output, format):
                    output.write(b"partial")
                    raise OSError("encoder failed")
            with self.assertRaises(OSError):
                save_capture(Broken(), folder)
            self.assertEqual(list(Path(folder).iterdir()), [foreign])

    def test_real_persistence_function_shares_identity_with_sidecar_and_scheduler(self):
        with tempfile.TemporaryDirectory() as folder:
            state, sidecars, scheduler = {}, [], []
            scope = {"datetime": datetime, "time": time, "runtime_state": state, "CAPTURE_SERVICE": CaptureService(),
                "mirror_capture_service_state": lambda: None, "save_capture": save_capture, "logging_folder": folder,
                "set_image_timestamp_value": lambda value: value, "set_runtime_value": state.__setitem__,
                "remember_screenshot_persist_result": lambda *args: None,
                "compute_image_fingerprint": lambda path, **kwargs: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "write_image_context_sidecar": lambda path, **kwargs: sidecars.append((path, kwargs)) or "fixture.sidecar",
                "build_image_context_capture_reason": lambda reason: reason,
                "register_turn_scheduler_capture": lambda path, **kwargs: scheduler.append((path, kwargs))}
            exec(compile(ast.Module(body=[ingress.FUNCTIONS["persist_runtime_capture"]], type_ignores=[]),
                         "aurora2.py", "exec"), scope)
            paths = [scope["persist_runtime_capture"](self.Image(value), value.hex(), "test")[0]
                     for value in (b"first", b"second")]
            self.assertNotEqual(*paths)
            self.assertEqual([row[0] for row in sidecars], paths)
            self.assertEqual([row[0] for row in scheduler], paths)
            for path, metadata in sidecars:
                self.assertEqual(metadata["file_hash"], hashlib.sha256(Path(path).read_bytes()).hexdigest())
            self.assertEqual(state["last_screenshot_path"], paths[-1])


if __name__ == "__main__":
    unittest.main()
