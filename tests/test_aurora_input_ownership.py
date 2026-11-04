"""Owned-input races and real dispatch with fake native APIs; no desktop access."""
import ast
import threading
import time
import unittest
from unittest.mock import patch

import test_aurora_action_context as actions
import test_aurora_command_ingress as ingress
from aurora_input_ownership import HeldInputLedger, InputOwnershipError, cooperative_move
from aurora_runtime_work import CancellationDomain, WorkCancelled


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = HeldInputLedger()
        self.domain = CancellationDomain()
        self.events = []
        self.route = {"namespace": "gb", "kind": "key", "requested": "a", "effective": "x", "backend": "scancode"}

    def acquire(self, *, route=None, down=None, release=None, **kwargs):
        return self.ledger.acquire(self.domain.token(), route or self.route,
                                   down or (lambda: self.events.append("down")),
                                   release or (lambda: self.events.append("up")), **kwargs)

    def test_owner_is_attributable_without_retaining_raw_arguments(self):
        with self.ledger.owner_scope({"request_id": "request-1", "client_id": "ai", "command": "secret text", "is_user": False}):
            with self.ledger.owner_scope(command="pyag:hold"):
                self.acquire(persistent=True)
        row = self.ledger.snapshot()["held"][0]
        self.assertEqual(row["owner"]["request_id"], "request-1")
        self.assertEqual(row["owner"]["command"], "pyag:hold")
        self.assertIn("batch_id", row["owner"])
        self.assertNotIn("secret", str(row))

    def test_conflicting_hold_does_not_release_existing_owner(self):
        lease = self.acquire(persistent=True)
        with self.assertRaises(InputOwnershipError) as error:
            self.acquire(route=dict(self.route, namespace="pyag", backend="keyboard", requested="x"))
        self.assertEqual(error.exception.effect_status, "not_started")
        self.assertEqual(self.events, ["down"])
        self.assertEqual(self.ledger.snapshot()["held"][0]["lease_id"], lease)

    def test_partial_down_and_release_failure_stay_visible_for_explicit_retry(self):
        def down():
            self.events.append("partial_down")
            raise RuntimeError("down failed")
        def up():
            self.events.append("up")
            if self.events.count("up") == 1:
                raise RuntimeError("release failed")
        with self.assertRaisesRegex(RuntimeError, "down failed"):
            self.acquire(down=down, release=up)
        state = self.ledger.snapshot()
        self.assertEqual(state["uncertain_count"], 1)
        self.assertIn("release failed", state["held"][0]["error"])
        self.assertTrue(self.ledger.release(state["held"][0]["lease_id"])["success"])
        self.assertEqual(self.events, ["partial_down", "up", "up"])
        self.assertEqual(self.ledger.snapshot()["held_count"], 0)

    def test_cancel_releases_all_attempts_even_after_failure(self):
        self.acquire(persistent=True)
        def fail():
            self.events.append("failed_up")
            raise RuntimeError("fixture")
        self.acquire(route=dict(self.route, requested="b", effective="z"), release=fail)
        result = self.ledger.cancel_through(self.domain.cancel("stop"), "stop")
        self.assertFalse(result["success"])
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(self.events[-2:], ["failed_up", "up"])
        self.assertEqual(self.ledger.snapshot()["held_count"], 1)

    def test_stale_cleanup_never_releases_newer_same_key(self):
        old = self.acquire(persistent=True)
        self.ledger.cancel_through(self.domain.cancel("stop"), "stop")
        new = self.acquire(persistent=True)
        self.assertNotEqual(old, new)
        self.assertTrue(self.ledger.release(old)["success"])
        self.assertEqual(self.events, ["down", "up", "down"])
        self.assertEqual(self.ledger.snapshot()["held"][0]["lease_id"], new)

    def test_delayed_stop_cleanup_preserves_new_generation(self):
        generation = self.domain.cancel("stop")
        self.acquire(persistent=True)
        self.ledger.cancel_through(generation, "delayed cleanup")
        self.assertEqual(self.events, ["down"])
        self.assertEqual(self.ledger.snapshot()["held_count"], 1)

    def test_cancel_during_native_down_reports_pending_then_owner_releases(self):
        entered, resume = threading.Event(), threading.Event()
        errors = []
        def down():
            self.events.append("down")
            entered.set()
            if not resume.wait(2):
                raise RuntimeError("fixture timed out")
        def run():
            try:
                self.acquire(down=down, persistent=True)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            result = self.ledger.cancel_through(self.domain.cancel("stop"), "stop")
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertFalse(result["success"])
            self.assertEqual(result["results"][0]["status"], "pending_operation")
        finally:
            resume.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(errors[0], WorkCancelled)
        self.assertEqual(self.events, ["down", "up"])
        self.assertEqual(self.ledger.snapshot()["held_count"], 0)

    def test_repeated_release_and_unknown_key_are_distinct(self):
        self.acquire(persistent=True)
        for _ in range(2):
            self.assertTrue(self.ledger.release_requested("gb", "key", "a")["success"])
        self.assertEqual(self.events, ["down", "up"])
        self.assertIsNone(self.ledger.release_requested("pyag", "key", "a"))

    def test_atomic_success_has_no_extra_up_but_failure_does_cleanup(self):
        self.acquire(atomic=True)
        self.assertEqual(self.events, ["down"])
        self.assertEqual(self.ledger.snapshot()["held_count"], 0)
        def fail():
            raise RuntimeError("partial press")
        with self.assertRaises(RuntimeError):
            self.acquire(down=fail, atomic=True)
        self.assertEqual(self.events, ["down", "up"])

    def test_pointer_cancel_uses_only_immediate_native_moves(self):
        def move(**kwargs):
            self.events.append(kwargs)
            self.domain.cancel("stop")
        with self.assertRaises(WorkCancelled):
            cooperative_move(move, lambda: (2, 3), self.domain.token(), 100, 200, 60)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["duration"], 0)

    def test_large_duration_is_chunked_without_removing_capability(self):
        token = self.domain.token()
        def stop(seconds):
            self.assertLessEqual(seconds, 60)
            self.domain.cancel("test stop")
            return True
        with patch.object(token.event, "wait", side_effect=stop), self.assertRaises(WorkCancelled):
            token.wait(1e200)


class HeldRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = actions.ActionContextTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope, self.desktop = self.fixture.scope, self.fixture.desktop
        names = {"cancel_active_work_command", "release_held_inputs_command", "show_held_inputs_command", "shutdown_runtime_command", "set_agent_running"}
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                     str(ingress.ROOT/'aurora2.py'), 'exec'), self.scope)
        self.scope["command_dispatch"].update({name: self.scope[handler] for name, handler in {
            "CANCEL_ACTIVE_WORK": "cancel_active_work_command", "RELEASE_HELD_INPUTS": "release_held_inputs_command",
            "SHOW_HELD_INPUTS": "show_held_inputs_command", "SHUTDOWN_RUNTIME": "shutdown_runtime_command"}.items()})

    def run_batch(self, text):
        return self.scope["handle_commands"](text)

    def test_indefinite_hold_survives_then_releases_original_mapping_backend_and_scan(self):
        seen = []
        self.scope["send_scancode_key_event"] = lambda key, **kwargs: seen.append((key, kwargs))
        entry = {"command": "GB:hold(a)", "is_user": True, "request_id": "hold-1", "source": "fixture"}
        result = self.scope["execute_command_entry"](entry)
        self.assertTrue(result["success"], result)
        held = result["desktop_results"][0]["input_ownership"]["held"][0]
        self.assertEqual(held["owner"]["request_id"], "hold-1")
        native = dict(held["route"]["native"])
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.scope["GAME_CONTROL_KEY_TRANSLATIONS"]["a"] = "unsupported_new_mapping"
        self.scope["GAME_INPUT_SCANCODES"]["x"] = 999
        self.scope["GAME_INPUT_EXTENDED_SCANCODE_KEYS"].add("x")
        result = self.run_batch("PYAG_MODE(); GB:release(a)")
        self.assertTrue(result["success"], result)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1], ("x", dict(native, is_key_up=True)))
        self.assertTrue(self.run_batch("GB:release(a)")["success"])
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["held_count"], 0)

    def test_keyboard_scan_code_and_mouse_button_are_frozen(self):
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.scope["keyboard"].key_to_scan_codes = lambda key: (45,)
        self.assertTrue(self.run_batch("GB:hold(a)")["success"])
        self.scope["keyboard"].key_to_scan_codes = lambda key: (99,)
        self.assertTrue(self.run_batch("GB:release(a)")["success"])
        self.assertEqual(self.fixture.calls(), [("keyboard_down", 45), ("keyboard_up", 45)])
        self.desktop.calls.clear()
        def change_button(call):
            if call[0] == "mouseDown":
                self.desktop._normalizeButton = lambda button: "right"
        self.desktop.on_call = change_button
        self.assertTrue(self.run_batch("PYAG:hold_click(None,None,0,primary)")["success"])
        self.assertEqual([kw["button"] for name, _, kw in self.desktop.calls], ["left", "left"])

    def test_cancel_owned_holds_only_and_show_readback(self):
        self.assertTrue(self.run_batch("PYAG:multi_hold(ctrl,shift)")["success"])
        shown = self.run_batch("SHOW_HELD_INPUTS()")
        self.assertEqual(shown["held_input_results"][0]["held_count"], 2)
        self.assertEqual(self.fixture.calls(), [("keyDown", "ctrl"), ("keyDown", "shift")])
        result = self.run_batch("CANCEL_ACTIVE_WORK()")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.fixture.calls()[-2:], [("keyUp", "shift"), ("keyUp", "ctrl")])
        self.assertEqual(len(result["input_cleanup_results"][0]["results"]), 2)

    def test_failed_release_blocks_tail_and_retry_preserves_ownership(self):
        self.assertTrue(self.run_batch("PYAG:multi_hold(ctrl,shift)")["success"])
        self.desktop.fail = lambda call: call[:2] == ("keyUp", ("shift",))
        result = self.run_batch("RELEASE_HELD_INPUTS(); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        cleanup = result["input_cleanup_results"][0]
        self.assertEqual([row["success"] for row in cleanup["results"]], [False, True])
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["uncertain_count"], 1)
        self.assertTrue(self.run_batch("RELEASE_HELD_INPUTS()")["success"])
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["held_count"], 0)
        self.assertEqual(sum(name == "keyDown" for name, _, _ in self.desktop.calls), 2)

    def test_uncertain_modifier_blocks_unrelated_typing_and_mouse_movement_until_recovered(self):
        self.assertTrue(self.run_batch("PYAG:hold(ctrl)")["success"])
        self.desktop.fail = lambda call: call[0] == "keyUp"
        self.assertFalse(self.run_batch("CANCEL_ACTIVE_WORK()")["success"])
        before = len(self.desktop.calls)
        for command in ('PYAG:type("b")', 'PYAG:move(10,20)'):
            result = self.run_batch(command)
            self.assertFalse(result["success"])
            self.assertEqual(result["desktop_results"][0]["effect_status"], "not_started")
        self.assertEqual(len(self.desktop.calls), before)
        self.assertTrue(self.run_batch("RELEASE_HELD_INPUTS()")["success"])
        self.assertTrue(self.run_batch('PYAG:type("b")')["success"])

    def test_tap_cannot_release_an_existing_indefinite_hold(self):
        self.assertTrue(self.run_batch("PYAG:hold(a)")["success"])
        result = self.run_batch("PYAG:press(a)")
        self.assertFalse(result["success"])
        self.assertEqual(result["desktop_results"][0]["effect_status"], "not_started")
        self.assertEqual(self.fixture.calls(), [("keyDown", "a")])

    def test_implicit_typing_modifier_cannot_release_an_owned_shift(self):
        self.assertTrue(self.run_batch("PYAG:hold(shift)")["success"])
        result = self.run_batch('PYAG:type("A")')
        self.assertFalse(result["success"])
        self.assertEqual(result["desktop_results"][0]["effect_status"], "not_started")
        self.assertEqual(self.fixture.calls(), [("keyDown", "shift")])

    def test_cancelled_drag_releases_button_and_reports_cancelled_tail(self):
        def stop(call):
            if call[0] == "moveTo":
                self.scope["cancel_command_inputs"]("fixture stop")
        self.desktop.on_call = stop
        result = self.run_batch("PYAG:drag(100,200,60); PYAG:type(never)")
        self.assertTrue(result["cancelled"], result)
        self.assertEqual([name for name, _, _ in self.desktop.calls], ["mouseDown", "moveTo", "mouseUp"])
        self.assertEqual(self.desktop.calls[1][2]["duration"], 0)
        self.assertEqual(result["desktop_results"][0]["input_ownership"]["held_count"], 0)

    def test_concurrent_stop_release_does_not_turn_cancelled_drag_into_failure(self):
        up_entered, finish_up = threading.Event(), threading.Event()
        workers = []
        def callback(call):
            if call[0] == "mouseUp":
                up_entered.set()
                if not finish_up.wait(2):
                    raise RuntimeError("fixture release timed out")
            elif call[0] == "moveTo":
                generation = self.scope["COMMAND_WORK"].cancel("fixture stop")
                worker = threading.Thread(target=lambda: self.scope["HELD_INPUTS"].cancel_through(generation, "stop"), daemon=True)
                workers.append(worker)
                worker.start()
                self.assertTrue(up_entered.wait(1))
        self.desktop.on_call = callback
        try:
            result = self.run_batch("PYAG:drag(100,200,60)")
            self.assertTrue(result["cancelled"], result)
            self.assertEqual(result["failed_commands"], [])
            self.assertEqual(result["desktop_results"][0]["input_ownership"]["held"][0]["state"], "releasing")
        finally:
            finish_up.set()
            for worker in workers:
                worker.join(2)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["held_count"], 0)
        self.assertEqual(sum(name == "mouseUp" for name, _, _ in self.desktop.calls), 1)

    def test_owned_release_bypasses_only_pyautogui_failsafe_decorator(self):
        def guarded_up(*args, **kwargs):
            raise RuntimeError("fake fail-safe corner")
        guarded_up.__wrapped__ = lambda *args, **kwargs: self.desktop.emit("keyUp", *args, **kwargs)
        self.desktop.keyUp = guarded_up
        self.assertTrue(self.run_batch("PYAG:hold(a)")["success"])
        self.assertTrue(self.run_batch("CANCEL_ACTIVE_WORK()")["success"])
        self.assertEqual(self.fixture.calls(), [("keyDown", "a"), ("keyUp", "a")])

    def test_release_only_preserves_model_token_and_shutdown_cleans_holds(self):
        model_token = self.scope["MODEL_WORK"].token()
        self.assertTrue(self.run_batch("PYAG:hold(a)")["success"])
        self.assertTrue(self.run_batch("RELEASE_HELD_INPUTS()")["success"])
        model_token.check()
        self.assertTrue(self.run_batch("PYAG:hold(b)")["success"])
        result = self.run_batch("SHUTDOWN_RUNTIME()")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["held_count"], 0)
        self.assertFalse(self.scope["agent_state"].running)
        with self.assertRaises(WorkCancelled):
            model_token.check()

    def test_current_release_is_explicit_legacy_escape_and_keeps_other_owned_route(self):
        self.assertTrue(self.run_batch("GB:hold(a)")["success"])
        self.scope["GAME_CONTROL_KEY_TRANSLATIONS"]["a"] = "z"
        self.assertTrue(self.run_batch("GB:release(a,current)")["success"])
        self.assertEqual(self.fixture.calls(), [("scancode_down", "x"), ("scancode_up", "z")])
        self.assertEqual(self.scope["HELD_INPUTS"].snapshot()["held_count"], 1)
        self.assertTrue(self.run_batch("GB:release(a)")["success"])
        self.assertEqual(self.fixture.calls()[-1], ("scancode_up", "x"))

    def test_stop_argument_errors_reject_entire_batch(self):
        for name in ("CANCEL_ACTIVE_WORK", "RELEASE_HELD_INPUTS", "SHOW_HELD_INPUTS", "SHUTDOWN_RUNTIME"):
            result = self.run_batch(f"PYAG:hold(a); {name}(extra)")
            self.assertFalse(result["success"])
            self.assertEqual(result["executed_commands"], [])
        self.assertEqual(self.desktop.calls, [])


if __name__ == '__main__':
    unittest.main()
