"""Registered setters, admission and receipts using real runtime functions, without native I/O."""
import ast
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_aurora_command_ingress as ingress
from test_aurora_settings_registry import sample_state
from aurora_command_catalog import parse_dispatch
from aurora_command_contracts import (
    REGISTERED_SETTING_COMMANDS, parse_setting_command_arguments, setting_command_result, setting_shortcut_definition,
)
from aurora_runtime_work import WorkCancelled
from aurora_responses_reasoning import ResponsesReasoningSession
from aurora_settings_registry import SETTING_DEFINITIONS, build_setting_readback, build_settings_version
from aurora_settings_transactions import build_setting_command_invocation, setting_values_equal
from offline_runtime_smoke import CONTRACT_FIXTURE, MODEL_FIXTURE


SETTERS = """set_auth_mode set_live_mode set_execution_mode set_action_mode set_game_profile
set_text_model set_vision_model set_reasoning_model set_model_transport set_default_reasoning_effort set_model_verbosity
set_model_temperature apply_turn_scheduler_profile set_turn_scheduler_mode set_turn_heartbeat_seconds
set_turn_min_gap_seconds set_turn_capture_wake_enabled set_turn_capture_wake_debounce_seconds
set_turn_post_action_settle_seconds set_screenshot_interval set_demand_capture_enabled set_image_detail
set_live_init_mode""".split()

VALUES = {
    "auth.mode": "auto", "runtime.live": True, "runtime.execution": "safe", "runtime.action": "pyag",
    "game.profile": "blue", "model.text": "future text model", "model.vision": "future vision model",
    "model.reasoning": "future reasoning model", "model.transport": "responses", "inference.reasoning_effort": "xhigh",
    "inference.verbosity": "high", "inference.temperature": 0.3, "scheduler.profile": "responsive",
    "scheduler.mode": "event", "scheduler.heartbeat_seconds": 1.0, "scheduler.min_gap_seconds": 0.2,
    "scheduler.capture_wake_enabled": False, "scheduler.capture_wake_debounce_seconds": 0.4,
    "scheduler.post_action_settle_seconds": 0.3, "capture.screenshot_interval": 0.15,
    "capture.demand_enabled": False, "vision.image_detail": "original", "runtime.live_init": True,
}


def command(name, *args):
    return name + "(" + ",".join(json.dumps(str(value)) for value in args) + ")"


class SettingCommandTests(unittest.TestCase):
    def setUp(self):
        self.harness = ingress.RuntimeIngressTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.scope = scope = self.harness.scope
        state = sample_state()
        self.locks = {key: False for key in state["locks"]}
        bindings = parse_dispatch(ingress.TREE, "command_dispatch")
        names = set(SETTERS) | {bindings[name] for name in REGISTERED_SETTING_COMMANDS} | {
            "observe_registered_setting", "execute_registered_setting_command", "build_registered_settings_runtime_state",
            "normalize_model_verbosity", "_parse_boolean_command_arg", "infer_turn_scheduler_profile_name",
            "refresh_turn_scheduler_profile_state", "initialize_turn_scheduler_runtime_state",
            "execute_settings_transaction_request", "_invoke_registered_setting_change",
        }
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in sorted(names)], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), scope)
        profiles = next(ast.literal_eval(n.value) for n in ingress.TREE.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "TURN_SCHEDULER_PROFILES" for t in n.targets))
        scope.update({
            "parse_setting_command_arguments": parse_setting_command_arguments,
            "setting_shortcut_definition": setting_shortcut_definition,
            "setting_command_result": setting_command_result, "build_setting_readback": build_setting_readback,
            "build_settings_version": build_settings_version, "build_setting_command_invocation": build_setting_command_invocation,
            "setting_values_equal": setting_values_equal, "SETTINGS_TRANSACTION_LOCK": threading.RLock(),
            "AUTH_MODE": "api_key", "EXECUTION_MODE": "assist", "ACTIVE_ACTION_MODE": "none",
            "SEND_TO_MODEL": False, "ENABLE_MODEL_RESPONSES": False, "LOAD_LIVE_INIT_PROMPT": False,
            "ACTIVE_GAME_PROFILE": "firered", "GAME_PROFILE_SOURCE": "env", "time_interval": 0.12,
            "ACTIVE_TEXT_MODEL": "fixture", "ACTIVE_VISION_MODEL": "fixture", "ACTIVE_REASONING_MODEL": "fixture",
            "MODEL_TRANSPORT": "chat_completions", "MODEL_IO": SimpleNamespace(busy=False),
            "RESPONSES_REASONING": ResponsesReasoningSession(),
            "DEFAULT_REASONING_EFFORT": "none", "DEFAULT_MODEL_VERBOSITY": "medium", "DEFAULT_MODEL_TEMPERATURE": 0.0,
            "ALLOWED_MODEL_VERBOSITY": {"low", "medium", "high"}, "image_detail": "low",
            "TURN_SCHEDULER_PROFILES": profiles, "TURN_SCHEDULER_PROFILE_NAME": "balanced",
            "TURN_SCHEDULER_MODE": "hybrid", "TURN_SCHEDULER_HEARTBEAT_SECONDS": 2.25,
            "TURN_SCHEDULER_MIN_GAP_SECONDS": 0.55, "TURN_SCHEDULER_CAPTURE_WAKE_ENABLED": True,
            "TURN_SCHEDULER_CAPTURE_WAKE_DEBOUNCE_SECONDS": 0.9, "TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS": 0.55,
            "DEMAND_CAPTURE_ENABLED": True, "screenshot_capture_wake_event": threading.Event(),
            "get_active_game_profile": lambda: scope["ACTIVE_GAME_PROFILE"],
            "get_active_game_profile_label": lambda: scope["ACTIVE_GAME_PROFILE"],
            "get_game_profile_save_note": lambda *args: "fixture note",
            "get_runtime_mode_summary": lambda: "fixture mode", "get_auth_status_summary": lambda: "fixture auth",
            "build_turn_scheduler_summary": lambda: "fixture scheduler",
            "get_turn_scheduler_profile_description": lambda profile: profile,
            "get_turn_scheduler_description": lambda mode: mode,
            "build_queue_next_action_runtime_cue": lambda: "fixture cue",
            "update_auth_runtime_state": lambda *args: None,
            "set_runtime_value": lambda key, value: scope["runtime_state"].__setitem__(key, value),
            "get_runtime_lock_snapshot": lambda: dict(self.locks),
            "get_default_profiles_status": lambda: copy.deepcopy(state["defaults"]),
            "require_runtime_setting_unlocked": self.require_unlocked,
        })
        scope["command_dispatch"].update({name: scope[bindings[name]] for name in REGISTERED_SETTING_COMMANDS})

    def require_unlocked(self, name, *args):
        if self.locks.get(name):
            raise RuntimeError("fixture setting lock: " + name)

    def run_batch(self, text):
        return self.scope["handle_commands"](text)

    def version(self):
        return build_settings_version(self.scope["build_registered_settings_runtime_state"]())

    def test_all_registered_commands_observe_the_requested_value(self):
        self.assertEqual(len(REGISTERED_SETTING_COMMANDS), 24)
        for name, definition in REGISTERED_SETTING_COMMANDS.items():
            with self.subTest(name=name):
                value = VALUES[definition.key]
                result = self.run_batch(command(name, value))
                self.assertTrue(result["success"], result)
                outcome = result["setting_results"][0]
                self.assertEqual(outcome["value"], value)
                self.assertEqual(outcome["requested_value"], value)
                self.assertEqual(outcome["effect_status"], "observed")
                self.assertEqual(outcome["after_version"], self.version())
                json.dumps(outcome, allow_nan=False)

    def test_zero_argument_queries_preserve_every_setting_and_work_when_locked(self):
        self.locks.update({key: True for key in self.locks})
        before = self.version()
        for name in REGISTERED_SETTING_COMMANDS:
            with self.subTest(name=name):
                result = self.run_batch(command(name))
                self.assertTrue(result["success"], result)
                self.assertEqual(result["setting_results"][0]["operation"], "read")
                self.assertEqual(result["setting_results"][0]["before_version"], before)
                self.assertEqual(self.version(), before)

    def test_invalid_tails_reject_before_any_prior_mutation(self):
        before = self.version()
        for name, definition in REGISTERED_SETTING_COMMANDS.items():
            bad = [(VALUES[definition.key], "ignored extra")]
            if definition.value_type in {"enum", "boolean"}:
                bad += [("unknown-mode",), ("",)]
            elif definition.value_type == "float":
                bad += [(v,) for v in ("nan", "inf", "-inf", "-1", "nope")]
            else:
                bad += [("",)]
            for args in bad:
                text = command(name, *args)
                with self.subTest(text=text):
                    result = self.run_batch("SET_TIME_LOGGING(on); " + text)
                    self.assertFalse(result["success"])
                    self.assertEqual(result["executed_commands"], [])
                    self.assertEqual(self.harness.executed, [])
                    self.assertEqual(self.version(), before)

    def test_supported_value_aliases_reach_the_same_canonical_runtime_values(self):
        for definition in SETTING_DEFINITIONS:
            for alias, canonical in definition.value_aliases:
                with self.subTest(key=definition.key, alias=alias):
                    result = self.run_batch(command(definition.command.split("(")[0], alias))
                    self.assertTrue(result["success"], result)
                    self.assertEqual(result["setting_results"][0]["value"], canonical)

    def test_locked_setter_blocks_tail_without_a_handler_call(self):
        self.locks["temperature"] = True
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = lambda *args: self.fail("locked setter was invoked")
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(result["setting_results"][0]["effect_status"], "not_started")
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(self.harness.executed, [])

    def test_lock_is_checked_at_execution_allowing_an_explicit_prior_unlock(self):
        self.locks["temperature"] = True
        self.scope["command_dispatch"]["UNLOCK_SETTING"] = lambda *args: self.locks.__setitem__("temperature", False)
        result = self.run_batch("UNLOCK_SETTING(temperature); SET_TEMPERATURE(0.5)")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["setting_results"][0]["value"], 0.5)

    def test_partial_setter_failure_is_uncertain_and_not_replayed_or_rolled_back(self):
        calls = []
        def partial(*args):
            calls.append(1)
            self.scope["DEFAULT_MODEL_TEMPERATURE"] = 0.7
            return False
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = partial
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(calls, [1])
        self.assertEqual(result["setting_results"][0]["effect_status"], "uncertain")
        self.assertEqual(result["setting_results"][0]["value"], 0.7)
        self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.7)
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_success_return_without_matching_readback_is_a_failure(self):
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = lambda *args: True
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertIn("readback", result["setting_results"][0]["reason"])
        self.assertEqual(result["setting_results"][0]["value"], 0.0)
        self.assertEqual(self.harness.executed, [])

    def test_failed_readback_after_change_does_not_claim_unchanged_state(self):
        observe = self.scope["observe_registered_setting"]
        calls = []
        def fail_after(definition):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("fixture readback failure")
            return observe(definition)
        self.scope["observe_registered_setting"] = fail_after
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        outcome = result["setting_results"][0]
        self.assertFalse(result["success"])
        self.assertEqual(outcome["effect_status"], "uncertain")
        self.assertEqual(outcome["after_version"], "")
        self.assertIsNone(outcome["value"])
        self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.5)

    def test_cancellation_retains_setting_evidence_and_cancels_tail(self):
        def cancel(*args):
            self.scope["DEFAULT_MODEL_TEMPERATURE"] = 0.5
            raise WorkCancelled("fixture cancellation")
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = cancel
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["setting_results"][0]["value"], 0.5)
        self.assertEqual(result["setting_results"][0]["effect_status"], "uncertain")
        self.assertEqual(result["cancelled_commands"], ["SET_TEMPERATURE(0.5)", "SET_TIME_LOGGING(on)"])

    def test_duplicate_failure_retains_setting_evidence_without_redispatch(self):
        self.harness.authorize()
        calls = []
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = lambda *args: calls.append(1) or False
        text = "SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)"
        for _ in range(2):
            self.harness.send(text, "failed-setting")
            self.harness.poll()
        receipts = [row for row in self.harness.events if row.get("event") == "command_result"]
        self.assertTrue(receipts[-1]["duplicate_suppressed"])
        self.assertEqual(receipts[-1]["setting_results"], receipts[-2]["setting_results"])
        self.assertEqual(receipts[-1]["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(calls, [1])

    def test_raw_setter_waits_for_the_existing_transaction_lock(self):
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        results = []
        def transaction(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("fixture transaction timed out")
            return True, {}
        self.scope["_execute_settings_preview_or_apply"] = transaction
        owner = threading.Thread(target=lambda: self.scope["execute_settings_transaction_request"]({"operation": "preview"}), daemon=True)
        setter = threading.Thread(target=lambda: (results.append(self.run_batch("SET_TEMPERATURE(0.5)")), completed.set()), daemon=True)
        self.addCleanup(release.set)
        owner.start()
        self.assertTrue(entered.wait(1))
        setter.start()
        try:
            self.assertFalse(completed.wait(0.03))
            self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.0)
        finally:
            release.set()
            owner.join(1)
            setter.join(1)
        self.assertFalse(owner.is_alive() or setter.is_alive())
        self.assertTrue(results[0]["success"], results)

    def test_lower_level_numeric_setters_reject_nonfinite_values_before_writes(self):
        names = ["set_model_temperature", "set_screenshot_interval", "set_turn_heartbeat_seconds",
                 "set_turn_min_gap_seconds", "set_turn_capture_wake_debounce_seconds", "set_turn_post_action_settle_seconds"]
        before = self.version()
        for name in names:
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        self.scope[name](value)
                    self.assertEqual(self.version(), before)

    def test_invalid_profiles_no_longer_fall_back_to_a_different_value(self):
        self.scope["set_game_profile"]("blue")
        self.scope["apply_turn_scheduler_profile"]("responsive")
        before = self.version()
        for name in ("set_game_profile", "apply_turn_scheduler_profile", "set_turn_scheduler_mode"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.scope[name]("misspelled-profile")
                self.assertEqual(self.version(), before)

    def test_invalid_previous_value_can_be_repaired_with_json_safe_receipt(self):
        self.scope["DEFAULT_MODEL_TEMPERATURE"] = float("nan")
        result = self.run_batch("SET_TEMPERATURE(0.5)")
        self.assertTrue(result["success"], result)
        self.assertIsNone(result["setting_results"][0]["before_value"])
        self.assertEqual(result["setting_results"][0]["value"], 0.5)
        json.dumps(result, allow_nan=False)

    def test_image_detail_handler_reports_invalid_value_and_supports_query(self):
        handler = self.scope["set_image_detail_command"]
        self.assertIs(handler(["invalid"], True), False)
        self.assertIs(handler([], True), True)
        self.assertEqual(self.scope["image_detail"], "low")

    def test_registered_failure_does_not_undo_earlier_valid_mutation(self):
        self.locks["models"] = True
        result = self.run_batch("SET_TEMPERATURE(0.5); SET_TEXT_MODEL(fixture-new); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.5)
        self.assertEqual(len(result["setting_results"]), 2)
        self.assertEqual(result["executed_commands"], ["SET_TEMPERATURE(0.5)"])
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_direct_fixtures_apply_parsed_startup_flags_before_main(self):
        self.assertNotIn("sys.addaudithook", CONTRACT_FIXTURE, "Permanent audit hooks belong only in the child-process bootstrap.")
        for fixture in (CONTRACT_FIXTURE, MODEL_FIXTURE):
            with self.subTest(fixture="contract" if fixture is CONTRACT_FIXTURE else "model"):
                calls = []
                flags = SimpleNamespace(offline=True, lock_live=True)
                runtime = SimpleNamespace(requests=SimpleNamespace(), keyboard=SimpleNamespace(), pyautogui=SimpleNamespace(),
                                          build_cli_parser=lambda: SimpleNamespace(parse_args=lambda: flags),
                                          apply_cli_args=lambda args: calls.append(("apply", args)),
                                          main=lambda: calls.append(("main", None)))
                with patch.dict("sys.modules", {"aurora2": runtime}):
                    exec(compile(fixture, "<runtime-fixture>", "exec"), {})
                self.assertEqual(calls, [("apply", flags), ("main", None)])


if __name__ == "__main__":
    unittest.main()
