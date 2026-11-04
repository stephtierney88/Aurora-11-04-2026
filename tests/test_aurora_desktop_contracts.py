"""Real runtime dispatch and handlers with simulated input APIs; no desktop access."""
import ast
import unittest
from types import SimpleNamespace

import test_aurora_command_ingress as ingress
from aurora_command_catalog import parse_dispatch
from aurora_command_contracts import DesktopCommandError, parse_desktop_arguments
from aurora_runtime_work import CancellationDomain


class FakeDesktop:
    KEYBOARD_KEYS = [chr(code) for code in range(32, 127)] + [
        "enter", "ctrl", "shift", "alt", "space", "up", "down", "left", "right", "\n", "\r", "\t"]
    PAUSE = 0

    def __init__(self):
        self.calls = []
        self.fail = None
        self.on_call = None
        self.xy = (0, 0)

    def position(self):
        return self.xy

    def _normalizeButton(self, button):
        return {"primary": "left", "secondary": "right"}.get(button, button)

    def emit(self, name, *args, **kwargs):
        call = (name, args, kwargs)
        self.calls.append(call)
        if name == "moveTo":
            self.xy = (kwargs["x"], kwargs["y"])
        if self.on_call:
            self.on_call(call)
        if self.fail and self.fail(call):
            self.fail = None
            raise RuntimeError(f"fixture {name} failure")

    def __getattr__(self, name):
        if name not in {"press", "keyDown", "keyUp", "mouseDown", "mouseUp", "click", "doubleClick", "moveTo", "dragTo", "scroll", "screenshot"}:
            raise AttributeError(name)
        return lambda *args, **kwargs: self.emit(name, *args, **kwargs)


class DesktopContractTests(unittest.TestCase):
    def setUp(self):
        self.harness = ingress.RuntimeIngressTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.scope = self.harness.scope
        self.desktop = FakeDesktop()
        self.game = False
        self.focus = {"success": True, "title": "fixture target"}
        self.focus_calls = []
        bindings = parse_dispatch(ingress.TREE, "pyautogui_dispatch")
        names = set(bindings.values()) | {
            "desktop_command_arguments", "release_desktop_keys", "send_desktop_key_sequence",
            "execute_desktop_command", "handle_pyautogui_command", "move_key",
            "translate_game_backend_key", "is_valid_keyboard_key_token", "game_backend_press",
            "game_backend_key_down", "game_backend_key_up", "send_scancode_backend_press", "send_keyboard_backend_press",
            "get_game_input_backend", "send_pyautogui_game_press"}
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in sorted(names)], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), self.scope)
        self.scope.update({
            "pyautogui": self.desktop,
            "pyautogui_dispatch": {name: self.scope[handler] for name, handler in bindings.items()},
            "set_last_key_value": lambda value: None,
            "set_runtime_value": lambda key, value: self.scope["runtime_state"].__setitem__(key, value),
            "get_foreground_window_title": lambda: "fixture target",
            "should_use_game_input_backend": lambda key: self.game,
            "focus_window_by_title": self.focus_target,
            "focus_game_input_target": self.focus_target,
            "EMULATOR_WINDOW_TITLE_HINT": "fixture emulator",
            "GAME_INPUT_BACKEND": "scancode", "GAME_CONFIRM_KEYS": {"a", "b", "start"},
            "GAME_CONFIRM_HOLD_SECONDS": 0.08,
            "record_focus_recovery_result": lambda *args: None,
            "record_game_input_attempt": lambda **kwargs: None,
            "send_scancode_key_event": lambda key, is_key_up=False, **kwargs: self.desktop.emit("scancode_up" if is_key_up else "scancode_down", key),
            "keyboard": SimpleNamespace(press=lambda key: self.desktop.emit("keyboard_down", key),
                                        release=lambda key: self.desktop.emit("keyboard_up", key),
                                        key_to_scan_codes=lambda key: (key,)),
        })

    def focus_target(self, title):
        self.focus_calls.append(title)
        return dict(self.focus)

    def execute(self, name, args):
        return self.scope["execute_desktop_command"](name, args)

    def test_invalid_desktop_tail_never_runs_earlier_mutation(self):
        invalid = [
            "pyag:move(1)", "pyag:move(nan,2)", "pyag:drag(1,2,-1)", "pyag:drag(1,2,0,bogus)",
            "pyag:scroll_up(1.5)", "pyag:scroll_down(1,2)", "pyag:press(a,0)", "pyag:press(a,1.5)",
            "pyag:press(a,1,inf)", "pyag:press(a,1e999999)", "pyag:press(unknown_key)",
            "pyag:hold(a,-1)", "pyag:release()", "pyag:move_key(up,0)", "pyag:focus_window(\"\")",
            "pyag:hotkey(ctrl,unknown_key)", "pyag:multi_press(a,unknown_key)",
            "pyag:multi_hold(ctrl,unknown_key)", "pyag:multi_release(ctrl,unknown_key)",
            "pyag:type(\"a🙂\")", "pyag:type(text,nan)", "pyag:click(1,2,bogus)",
            "pyag:leftclick(1,2,left,4)", "pyag:doubleclick(1.5,2)",
            "pyag:hold_click(1,2,inf)", "pyag:screenshot(\"\")",
        ]
        for command in invalid:
            with self.subTest(command=command):
                result = self.scope["handle_commands"]("SET_TIME_LOGGING(on); " + command)
                self.assertFalse(result["success"])
                self.assertEqual(result["executed_commands"], [])
                self.assertEqual(self.harness.executed, [])
                self.assertEqual(self.desktop.calls, [])

    def test_defaults_coordinates_and_buttons_reach_backend_exactly(self):
        for name, args, expected in [
            ("click", [], {"x": None, "y": None, "button": "left"}),
            ("leftclick", ["-120", "20", "RIGHT"], {"x": -120, "y": 20, "button": "right"}),
            ("click", ["None", "null", "secondary"], {"x": None, "y": None, "button": "right"}),
            ("move", ["-10", "2", "0.25"], {"x": -10, "y": 2, "duration": 0}),
        ]:
            with self.subTest(name=name, args=args):
                result = self.execute(name, args)
                self.assertTrue(result["success"])
                self.assertEqual(result["effect_status"], "submitted")
                self.assertEqual(self.desktop.calls[-1][2], dict(expected, _pause=False))
        self.execute("scroll_down", ["-3"])
        self.assertEqual(self.desktop.calls[-1][1], (3,))

    def test_key_chords_are_complete_normalized_and_released_in_reverse(self):
        result = self.execute("hotkey", ["CTRL", "c"])
        self.assertTrue(result["success"])
        self.assertEqual([(name, args[0]) for name, args, _ in self.desktop.calls],
                         [("keyDown", "ctrl"), ("keyDown", "c"), ("keyUp", "c"), ("keyUp", "ctrl")])

    def test_text_preserves_case_and_empty_text_is_a_valid_noop(self):
        self.assertTrue(self.execute("type", ["Ab c", "0"])["success"])
        self.assertEqual([args[0] for name, args, _ in self.desktop.calls if name == "press"], list("Ab c"))
        before = len(self.desktop.calls)
        self.assertTrue(self.execute("type", [""])["success"])
        self.assertEqual(len(self.desktop.calls), before)

    def test_integral_press_count_is_used_without_silent_rounding(self):
        self.assertTrue(self.execute("press", ["A", "2.0", "0"])["success"])
        self.assertEqual([args[0] for name, args, _ in self.desktop.calls], ["a", "a"])
        with self.assertRaises(ValueError):
            parse_desktop_arguments("press", ["a", "2.1"])

    def test_failed_focus_blocks_later_typing_and_mutation(self):
        self.focus = {"success": False, "reason": "target absent"}
        result = self.scope["handle_commands"]('pyag:focus_window("missing"); pyag:type("danger"); SET_TIME_LOGGING(on)')
        self.assertFalse(result["success"])
        self.assertEqual(result["executed_commands"], [])
        self.assertEqual(len(result["blocked_commands"]), 2)
        self.assertEqual(result["desktop_results"][0]["effect_status"], "uncertain")
        self.assertIn("target absent", result["failed_commands"][0]["reason"])
        self.assertEqual(self.desktop.calls, [])
        self.assertEqual(self.harness.executed, [])

    def test_confirmed_focus_is_observed_but_input_is_only_submitted(self):
        result = self.scope["handle_commands"]('pyag:focus_window("fixture"); pyag:type("ok")')
        self.assertTrue(result["success"])
        self.assertEqual([row["effect_status"] for row in result["desktop_results"]], ["observed", "submitted"])

    def test_input_exception_is_uncertain_without_automatic_retry(self):
        self.desktop.fail = lambda call: call[0] == "press"
        result = self.scope["handle_commands"]('pyag:press(a,3); pyag:click()')
        self.assertFalse(result["success"])
        self.assertEqual([call[0] for call in self.desktop.calls], ["press", "keyUp"])
        self.assertEqual(result["desktop_results"][0]["effect_status"], "uncertain")
        self.assertEqual(result["blocked_commands"], ["pyag:click()"])

    def test_game_focus_failure_sends_no_input_and_release_needs_no_focus(self):
        self.game = True
        self.focus = {"success": False, "reason": "wrong target"}
        for name in ("press", "hold"):
            result = self.execute(name, ["a"])
            self.assertFalse(result["success"])
            self.assertEqual(result["effect_status"], "not_started")
        self.assertEqual(self.desktop.calls, [])
        focused = len(self.focus_calls)
        self.assertTrue(self.execute("release", ["start"])["success"])
        self.assertEqual(len(self.focus_calls), focused)
        self.assertEqual(self.desktop.calls[-1][:2], ("scancode_up", ("enter",)))

    def test_partial_multi_hold_releases_attempted_keys(self):
        self.desktop.fail = lambda call: call[0] == "keyDown" and call[1] == ("shift",)
        result = self.execute("multi_hold", ["ctrl", "shift"])
        self.assertFalse(result["success"])
        self.assertEqual([(name, args[0]) for name, args, _ in self.desktop.calls],
                         [("keyDown", "ctrl"), ("keyDown", "shift"), ("keyUp", "shift"), ("keyUp", "ctrl")])

    def test_release_attempts_remaining_keys_after_one_failure(self):
        self.desktop.fail = lambda call: call[0] == "keyUp" and call[1] == ("ctrl",)
        result = self.execute("multi_release", ["ctrl", "shift"])
        self.assertFalse(result["success"])
        self.assertEqual([args[0] for _, args, _ in self.desktop.calls], ["ctrl", "shift"])

    def test_repeated_desktop_press_cancels_before_next_input(self):
        self.desktop.on_call = lambda call: self.scope["COMMAND_WORK"].cancel("fixture stop") if call[0] == "press" else None
        result = self.scope["handle_commands"]("pyag:press(a,50,60); SHOW_AUTH()")
        self.assertTrue(result["cancelled"])
        self.assertEqual([call[0] for call in self.desktop.calls], ["press"])
        self.assertEqual(len(result["cancelled_commands"]), 2)
        self.assertEqual(result["desktop_results"][0]["effect_status"], "uncertain")

    def test_game_press_cancellation_releases_without_switching_backends(self):
        self.game = True
        for backend in ("scancode", "keyboard"):
            with self.subTest(backend=backend):
                self.scope["GAME_INPUT_BACKEND"] = backend
                self.scope["COMMAND_WORK"] = CancellationDomain()
                self.desktop.calls.clear()
                self.desktop.on_call = lambda call: self.scope["COMMAND_WORK"].cancel("fixture stop") if call[0].endswith("_down") else None
                result = self.scope["handle_commands"]("GB:press(a,50,60)")
                self.assertTrue(result["cancelled"])
                self.assertEqual([call[0] for call in self.desktop.calls], [backend + "_down", backend + "_up"])

    def test_move_key_propagates_hold_failure(self):
        waits = []
        self.scope["COMMAND_WORK"] = SimpleNamespace(current=lambda: SimpleNamespace(check=lambda: None, wait=waits.append))
        def fail_hold(args):
            raise DesktopCommandError("fixture hold failed")
        self.scope["pyautogui_hold"] = fail_hold
        result = self.execute("move_key", ["up", "9"])
        self.assertFalse(result["success"])
        self.assertIn("hold failed", result["reason"])
        self.assertEqual(waits, [1.35])

    def test_duplicate_failure_keeps_desktop_evidence_without_redispatch(self):
        self.harness.authorize()
        self.focus = {"success": False, "reason": "target absent"}
        command = "pyag:focus_window(missing); SET_TIME_LOGGING(on)"
        self.harness.send(command, "failed-focus")
        self.harness.poll()
        self.harness.send(command, "failed-focus")
        self.harness.poll()
        receipts = [row for row in self.harness.events if row.get("event") == "command_result"]
        self.assertTrue(receipts[-1]["duplicate_suppressed"])
        self.assertEqual(receipts[-1]["desktop_results"], receipts[-2]["desktop_results"])
        self.assertEqual(receipts[-1]["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(len(self.focus_calls), 1)


if __name__ == "__main__":
    unittest.main()
