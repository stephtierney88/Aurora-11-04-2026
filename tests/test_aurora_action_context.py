"""Real command preparation, settings and input routing with simulated native APIs."""
import ast
import json
import pickle
import threading
import unittest
from types import SimpleNamespace

import test_aurora_command_ingress as ingress
import test_aurora_mutation_commands as mutations
from test_aurora_desktop_contracts import FakeDesktop
from aurora_command_catalog import parse_dispatch
from aurora_command_contracts import DesktopActionContext, current_desktop_action_context, desktop_action_scope
from aurora_settings_transactions import build_settings_transaction_command


class ActionContextTests(unittest.TestCase):
    def setUp(self):
        self.settings = mutations.MutationCommandTests(methodName="runTest")
        self.settings.setUp()
        self.addCleanup(self.settings.doCleanups)
        self.scope = s = self.settings.scope
        self.harness = self.settings.harness
        self.desktop = FakeDesktop()
        self.foreground = "fixture desktop"
        self.focus = {"success": True, "title": "fixture emulator"}
        self.focus_calls = []
        bindings = parse_dispatch(ingress.TREE, "pyautogui_dispatch")
        names = set(bindings.values()) | {
            "execute_desktop_command", "release_desktop_keys", "send_desktop_key_sequence", "move_key",
            "should_use_game_input_backend", "is_valid_keyboard_key_token", "get_game_input_backend",
            "game_backend_press", "game_backend_key_down", "game_backend_key_up", "send_scancode_backend_press",
            "send_keyboard_backend_press", "send_pyautogui_game_press",
        }
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in sorted(names)], type_ignores=[]),
                     str(ingress.ROOT / 'aurora2.py'), 'exec'), s)
        s.update({"pyautogui": self.desktop, "pyautogui_dispatch": {name: s[handler] for name, handler in bindings.items()},
                  "get_foreground_window_title": lambda: self.foreground,
                  "window_title_matches": lambda title, hint: hint in title,
                  "EMULATOR_WINDOW_TITLE_HINT": "fixture emulator", "GAME_NAVIGATION_KEYS": {"up", "down", "left", "right"},
                  "GAME_CONFIRM_KEYS": {"a", "b", "start"}, "GAME_CONFIRM_HOLD_SECONDS": 0.01,
                  "set_last_key_value": lambda key: None, "record_game_input_attempt": lambda **kwargs: None,
                  "record_focus_recovery_result": lambda *args: None,
                  "focus_game_input_target": self.focus_target, "focus_window_by_title": self.focus_target,
                  "send_scancode_key_event": lambda key, is_key_up=False, **kwargs: self.desktop.emit("scancode_up" if is_key_up else "scancode_down", key),
                  "keyboard": SimpleNamespace(press=lambda key: self.desktop.emit("keyboard_down", key), release=lambda key: self.desktop.emit("keyboard_up", key), key_to_scan_codes=lambda key: (key,))})

    def focus_target(self, title):
        self.focus_calls.append(title)
        return dict(self.focus)

    def run_batch(self, text):
        return self.scope["handle_commands"](text)

    def calls(self):
        return [(name, args[0] if args else None) for name, args, _ in self.desktop.calls]

    def test_explicit_pyag_stays_literal_while_emulator_is_foreground(self):
        self.foreground = "fixture emulator"
        self.scope["runtime_state"]["operating_context"] = "game"
        result = self.run_batch("PYAG:press(a)")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls(), [("press", "a")])
        self.assertEqual(self.focus_calls, [])
        route = result["desktop_results"][0]["action_route"]
        self.assertEqual((route["namespace"], route["backend"], route["effective_key"]), ("pyag", "pyautogui", "a"))

    def test_explicit_pyag_game_alias_rejects_even_in_game_context(self):
        self.foreground = "fixture emulator"
        result = self.run_batch("SET_TIME_LOGGING(on); PYAG:press(start)")
        self.assertFalse(result["success"])
        self.assertEqual(self.harness.executed, [])
        self.assertEqual(self.desktop.calls, [])
        self.assertEqual(self.focus_calls, [])

    def test_gb_translates_and_focuses_for_every_configured_backend(self):
        for backend, event in (("scancode", "scancode"), ("keyboard", "keyboard"), ("pyautogui", "key")):
            with self.subTest(backend=backend):
                self.scope["GAME_INPUT_BACKEND"] = backend
                self.desktop.calls.clear()
                self.focus_calls.clear()
                result = self.run_batch("GB:Start")
                self.assertTrue(result["success"], result)
                self.assertEqual(self.focus_calls, ["fixture emulator"])
                expected = [("keyDown", "enter"), ("keyUp", "enter")] if event == "key" else [(event+"_down", "enter"), (event+"_up", "enter")]
                self.assertEqual(self.calls(), expected)
                self.assertEqual(result["desktop_results"][0]["action_route"]["backend"], backend)

    def test_game_focus_failure_blocks_all_backends_and_release_needs_no_focus(self):
        self.focus = {"success": False, "reason": "fixture target missing"}
        for backend in ("scancode", "keyboard", "pyautogui"):
            self.scope["GAME_INPUT_BACKEND"] = backend
            result = self.run_batch("GB:press(a); PYAG:press(b)")
            self.assertFalse(result["success"], result)
            self.assertEqual(result["desktop_results"][0]["effect_status"], "not_started")
            self.assertEqual(self.desktop.calls, [])
            self.assertEqual(result["blocked_commands"], ["PYAG:press(b)"])
        focused = len(self.focus_calls)
        result = self.run_batch("GB:release(start)")
        self.assertTrue(result["success"], result)
        self.assertEqual(len(self.focus_calls), focused)
        self.assertEqual(self.calls(), [("keyUp", "enter")])

    def test_known_mode_setters_guide_later_implicit_commands_in_order(self):
        result = self.run_batch("GB_MODE(); press(a); PYAG_MODE(); press(a); SET_ACTION_MODE(game); Start")
        self.assertTrue(result["success"], result)
        routes = [row["action_route"] for row in result["desktop_results"]]
        self.assertEqual([row["namespace"] for row in routes], ["gb", "pyag", "gb"])
        self.assertEqual([row["origin"] for row in routes], ["implicit"] * 3)
        self.assertEqual(self.calls(), [("scancode_down", "x"), ("scancode_up", "x"), ("press", "a"),
                                        ("scancode_down", "enter"), ("scancode_up", "enter")])

    def test_mode_query_does_not_project_a_change_and_none_rejects_implicit_actions(self):
        self.scope["ACTIVE_ACTION_MODE"] = "pyag"
        result = self.run_batch("SET_ACTION_MODE(); press(a)")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls(), [("press", "a")])
        self.desktop.calls.clear()
        result = self.run_batch("NO_ACTION_MODE(); press(a)")
        self.assertFalse(result["success"])
        self.assertEqual(result["executed_commands"], [])
        self.assertEqual(self.scope["ACTIVE_ACTION_MODE"], "pyag")
        self.assertEqual(self.desktop.calls, [])

    def test_explicit_prefixes_override_mode_and_each_other(self):
        result = self.run_batch("GB_MODE(); PYAG:press(a); PYAG_MODE(); GB:press(b)")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls(), [("press", "a"), ("scancode_down", "z"), ("scancode_up", "z")])

    def test_apply_transaction_projects_action_mode_but_preview_does_not(self):
        self.scope["ACTIVE_ACTION_MODE"] = "gb"
        preview = self.settings.request("preview", changes={"action": "desktop"})
        result = self.run_batch(build_settings_transaction_command(preview) + "; Start")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["desktop_results"][0]["action_route"]["namespace"], "gb")
        request = self.settings.request(changes={"action": "desktop"})
        result = self.run_batch(build_settings_transaction_command(request) + "; press(a)")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["desktop_results"][0]["action_route"]["namespace"], "pyag")
        self.assertEqual(self.calls()[-1], ("press", "a"))

    def test_locked_mode_change_blocks_the_projected_action(self):
        self.settings.fixture.locks["action"] = True
        result = self.run_batch("GB_MODE(); Start")
        self.assertFalse(result["success"])
        self.assertEqual(result["setting_results"][0]["effect_status"], "not_started")
        self.assertEqual(result["blocked_commands"], ["Start"])
        self.assertEqual(self.desktop.calls, [])

    def test_unknown_profile_or_rollback_mode_requires_explicit_action_or_selector(self):
        for name in ("APPLY_PERSONAL_DEFAULTS", "APPLY_SYSTEM_DEFAULTS", "ARM_LIVE_VISUAL_HARNESS_PROBE"):
            self.scope["command_dispatch"][name] = lambda *args: True
            result = self.run_batch(f"SET_TIME_LOGGING(on); {name}(); press(a)")
            self.assertFalse(result["success"])
            self.assertIn("may change action mode", result["failed_commands"][0]["reason"])
            self.assertEqual(self.harness.executed, [])
            result = self.run_batch(f"{name}(); PYAG_MODE(); press(a)")
            self.assertTrue(result["success"], result)
        rollback = self.settings.request("rollback", rollback_handle="fixture unknown")
        result = self.run_batch(build_settings_transaction_command(rollback) + "; press(a)")
        self.assertFalse(result["success"])
        self.assertIn("may change action mode", result["failed_commands"][0]["reason"])

    def test_queued_action_retains_admitted_namespace_backend_and_mapping(self):
        self.scope["ACTIVE_ACTION_MODE"] = "gb"
        prepared = self.scope["prepare_command_batch"]("press(a)")
        context = prepared[0][3]
        self.assertEqual(pickle.loads(pickle.dumps(context)), context)
        json.dumps(prepared, allow_nan=False)
        with self.assertRaises(AttributeError):
            context.backend = "keyboard"
        self.scope["ACTIVE_ACTION_MODE"] = "none"
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.scope["GAME_CONTROL_KEY_TRANSLATIONS"]["a"] = "z"
        result = self.scope["handle_commands"]("press(a)", prepared_commands=prepared)
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls(), [("scancode_down", "x"), ("scancode_up", "x")])
        self.assertEqual(result["desktop_results"][0]["action_route"]["effective_key"], "x")

    def test_timed_release_keeps_backend_and_mapping_after_runtime_change(self):
        def change_backend(call):
            if call[0] == "scancode_down":
                self.scope["GAME_INPUT_BACKEND"] = "keyboard"
                self.scope["GAME_CONTROL_KEY_TRANSLATIONS"]["a"] = "z"
        self.desktop.on_call = change_backend
        result = self.run_batch("GB:hold(a,0)")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.calls(), [("scancode_down", "x"), ("scancode_up", "x")])

    def test_cancellation_keeps_route_evidence_and_restores_scope(self):
        self.desktop.on_call = lambda call: self.scope["COMMAND_WORK"].cancel("fixture stop") if call[0] == "scancode_down" else None
        result = self.run_batch("GB:hold(a,30); PYAG:press(b)")
        self.assertTrue(result["cancelled"], result)
        self.assertEqual(self.calls(), [("scancode_down", "x"), ("scancode_up", "x")])
        self.assertEqual(result["desktop_results"][0]["action_route"]["namespace"], "gb")
        self.assertIsNone(current_desktop_action_context())

    def test_mapping_and_backend_key_errors_reject_before_prior_mutation(self):
        self.scope["GAME_CONTROL_KEY_TRANSLATIONS"]["a"] = "ctrl"
        result = self.run_batch("SET_TIME_LOGGING(on); GB:press(a)")
        self.assertFalse(result["success"])
        self.assertIn("scancode", result["failed_commands"][0]["reason"])
        self.assertEqual(self.harness.executed, [])
        self.assertEqual(self.desktop.calls, [])
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.assertTrue(self.run_batch("GB:press(a)")["success"])

    def test_duplicate_receipt_retains_original_route_without_redispatch(self):
        self.harness.authorize()
        self.harness.send("GB:press(a)", "route-duplicate")
        self.harness.poll()
        self.scope["GAME_INPUT_BACKEND"] = "keyboard"
        self.harness.send("GB:press(a)", "route-duplicate")
        self.harness.poll()
        receipts = [row for row in self.harness.events if row.get("event") == "command_result"]
        self.assertTrue(receipts[-1]["duplicate_suppressed"])
        self.assertEqual(receipts[-1]["desktop_results"], receipts[-2]["desktop_results"])
        self.assertEqual(receipts[-1]["desktop_results"][0]["action_route"]["backend"], "scancode")
        self.assertEqual(self.calls(), [("scancode_down", "x"), ("scancode_up", "x")])

    def test_context_scopes_are_thread_local_and_restore_nested_callers(self):
        outer = DesktopActionContext("gb", "explicit", "none", "scancode", "a", "x")
        inner = DesktopActionContext("pyag", "explicit", "none", "pyautogui", "a", "a")
        observed = []
        with desktop_action_scope(outer):
            worker = threading.Thread(target=lambda: observed.append(current_desktop_action_context()))
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(observed, [None])
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with desktop_action_scope(inner):
                    self.assertEqual(current_desktop_action_context(), inner)
                    raise RuntimeError("fixture nested failure")
            self.assertEqual(current_desktop_action_context(), outer)
        self.assertIsNone(current_desktop_action_context())


if __name__ == '__main__':
    unittest.main()
