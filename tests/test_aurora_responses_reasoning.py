"""Adaptive effort, continuation, and failures with real controller code and fake I/O."""
import ast
import copy
import json
import re
import threading
import uuid
import unittest
from types import SimpleNamespace

import test_aurora_command_ingress as ingress
from aurora_responses_reasoning import (
    ASTRA_EFFORTS, ASTRA_MODEL, ResponsesReasoningError, ResponsesReasoningSession,
    build_reasoning_configuration_update, completed_response_text, responses_input_messages,
)
from aurora_runtime_work import CancellationDomain, WorkCancelled
from aurora_settings_registry import coerce_setting_value
from aurora_command_contracts import (
    validate_command_arguments, INFERENCE_PLAN_RESULT_SCHEMA, parse_inference_plan_arguments,
    normalize_next_inference_pairs, inference_plan_version,
)


def payload(effort="low", message="Current screenshot context"):
    return {"model": ASTRA_MODEL, "reasoning_effort": effort, "verbosity": "low",
            "max_completion_tokens": 1937,
            "messages": [{"role": "system", "content": "Aurora instructions"},
                         {"role": "user", "content": message}]}


def completed(number=1, text="No action", **changes):
    data = {"id": f"resp_{number}", "model": ASTRA_MODEL, "status": "completed",
            "reasoning": {"effort": "low"},
            "usage": {"input_tokens": 1200, "input_tokens_details": {"cached_tokens": 256}},
            "output": [{"type": "reasoning", "encrypted_content": "provider-owned"},
                       {"type": "message", "role": "assistant", "status": "completed", "phase": "final_answer",
                        "content": [{"type": "output_text", "text": text}]}]}
    return dict(data, **changes)


class ResponsesSessionTests(unittest.TestCase):
    def test_low_high_low_retains_original_prefix_and_correct_effort_readback(self):
        session = ResponsesReasoningSession()
        requests = []
        for number, effort in enumerate(("low", "high", "low"), 1):
            request = session.prepare(payload(effort), base_effort="low")
            requests.append(request.payload)
            self.assertEqual(session.complete(request, completed(number)), "No action")
            state = session.snapshot()
            self.assertEqual(state["effective_effort"], effort)
            self.assertEqual(state["api_reported_effort"], "low")
        self.assertNotIn("previous_response_id", requests[0])
        for i in (1, 2):
            self.assertEqual(requests[i]["previous_response_id"], f"resp_{i}")
            self.assertEqual(requests[i]["input"][-2], build_reasoning_configuration_update(("high", "low")[i-1]))
            self.assertEqual(requests[i]["input"][-1]["role"], "user")
        for request in requests:
            self.assertEqual(request["reasoning"], {"effort": "low"})
            self.assertEqual(request["truncation"], "disabled")
            self.assertNotIn("context_management", request)
            self.assertTrue(request["store"])

    def test_first_turn_override_and_changed_session_default_do_not_rewrite_base(self):
        session = ResponsesReasoningSession()
        first = session.prepare(payload("high"), base_effort="low")
        self.assertEqual(first.payload["input"][-2]["reasoning"]["effort"], "high")
        session.complete(first, completed())
        second = session.prepare(payload("high"), base_effort="high")
        self.assertEqual(second.payload["reasoning"]["effort"], "low")
        self.assertFalse(second.configuration_update_sent)

    def test_bootstrap_history_is_not_duplicated_on_continuation(self):
        session = ResponsesReasoningSession()
        full = payload()
        full["messages"].insert(1, {"role": "assistant", "content": "OLD HISTORY"})
        fresh = payload(message="NEW SNAPSHOT")["messages"]
        first = session.prepare(full, base_effort="low", current_messages=fresh)
        self.assertIn("OLD HISTORY", json.dumps(first.payload))
        session.complete(first, completed())
        second = session.prepare(full, base_effort="low", current_messages=fresh)
        self.assertNotIn("OLD HISTORY", json.dumps(second.payload))
        self.assertIn("NEW SNAPSHOT", json.dumps(second.payload))

    def test_image_conversion_preserves_role_url_and_detail_without_mutating_caller(self):
        messages = [{"role": "system", "content": "authority"},
                    {"role": "user", "content": [{"type": "text", "text": "fresh"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,FAKE", "detail": "original"}}]}]
        before = copy.deepcopy(messages)
        converted = responses_input_messages(messages)
        self.assertEqual(messages, before)
        self.assertEqual(converted[-1]["content"][-1], {"type": "input_image", "image_url": "data:image/png;base64,FAKE", "detail": "original"})
        self.assertEqual(converted[0]["role"], "system")

    def test_unsupported_requests_fail_before_reserving_or_sending(self):
        cases = [dict(payload(), model="gpt-5.5"), dict(payload(), model="gpt-6-astra-pro"),
                 dict(payload(), temperature=0), dict(payload(), tools=[]),
                 dict(payload(), truncation="auto"), dict(payload(), context_management=[]),
                 dict(payload(), reasoning_effort="ultra"), dict(payload(), reasoning_effort="none")]
        for value in cases:
            with self.subTest(value=value):
                session = ResponsesReasoningSession()
                with self.assertRaises(ValueError):
                    session.prepare(value, base_effort="low")
                self.assertEqual(session.snapshot()["status"], "ready")
                self.assertEqual(session.snapshot()["last_request"], {})

    def test_missing_user_boundary_and_malformed_images_reject(self):
        for messages in [[], [{"role": "tool", "content": "x"}], [{"role": "system", "content": "x"}],
                         [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x", "detail": "bad"}}]}]]:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                responses_input_messages(messages)

    def test_pending_owner_reset_and_stale_completion(self):
        session = ResponsesReasoningSession()
        request = session.prepare(payload(), base_effort="low")
        with self.assertRaises(ResponsesReasoningError):
            session.prepare(payload(), base_effort="low")
        with self.assertRaises(ResponsesReasoningError):
            session.reset()
        session.fail(request, "lost completion")
        self.assertEqual(session.snapshot()["status"], "blocked")
        self.assertTrue(session.snapshot()["completion_uncertain"])
        with self.assertRaises(ResponsesReasoningError):
            session.prepare(payload(), base_effort="low")
        session.reset()
        with self.assertRaises(ResponsesReasoningError):
            session.complete(request, completed())
        self.assertEqual(session.snapshot()["previous_response_id"], "")

    def test_history_invalidation_discards_active_result_without_overwriting_new_generation(self):
        session = ResponsesReasoningSession()
        request = session.prepare(payload(), base_effort="low")
        session.invalidate("operator cleared history")
        with self.assertRaises(ResponsesReasoningError):
            session.complete(request, completed())
        session.fail(request, "late exception")
        self.assertEqual(session.snapshot()["blocked_reason"], "operator cleared history")
        session.reset()
        self.assertNotIn("previous_response_id", session.prepare(payload(), base_effort="low").payload)

    def test_incomplete_refused_commentary_and_tool_output_are_not_executable_answers(self):
        for data in [completed(status="incomplete"), completed(output=[]),
                     completed(output=[{"type": "function_call", "name": "press"}]),
                     completed(output=[{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "No"}]}]),
                     completed(output=[{"type": "message", "role": "assistant", "phase": "commentary", "content": [{"type": "output_text", "text": "PYAG:press(a)"}]}])]:
            with self.subTest(data=data), self.assertRaises(ResponsesReasoningError):
                completed_response_text(data)
        data = completed(text="Final result")
        data["output"].insert(1, {"type": "message", "role": "assistant", "phase": "commentary", "content": [{"type": "output_text", "text": "PYAG:press(a)"}]})
        data["output"].insert(1, {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Interim PYAG:press(b)"}]})
        self.assertEqual(completed_response_text(data), "Final result")

    def test_malformed_identity_model_and_usage_never_commit(self):
        for changes in [{"id": ""}, {"model": "different"}, {"usage": {}}, {"usage": {"input_tokens": -1}}, {"usage": {"input_tokens": True}}]:
            session = ResponsesReasoningSession()
            request = session.prepare(payload(), base_effort="low")
            with self.subTest(changes=changes), self.assertRaises(ResponsesReasoningError):
                session.complete(request, completed(**changes))
            self.assertEqual(session.snapshot()["completed_responses"], 0)

    def test_context_and_byte_limits_stop_without_silent_truncation(self):
        session = ResponsesReasoningSession(max_input_tokens=1200)
        request = session.prepare(payload(), base_effort="low")
        session.complete(request, completed())
        with self.assertRaises(ResponsesReasoningError):
            session.prepare(payload(), base_effort="low")
        tiny = ResponsesReasoningSession(max_request_bytes=20)
        with self.assertRaises(ValueError):
            tiny.prepare(payload(), base_effort="low")
        self.assertEqual(tiny.snapshot()["status"], "ready")

    def test_snapshot_is_bounded_metadata_and_not_caller_mutable(self):
        session = ResponsesReasoningSession()
        request = session.prepare(payload(message="PRIVATE PROMPT"), base_effort="low")
        snapshot = session.snapshot()
        self.assertNotIn("PRIVATE PROMPT", json.dumps(snapshot))
        snapshot["last_request"]["status"] = "forged"
        self.assertEqual(session.snapshot()["last_request"]["status"], "prepared")
        session.complete(request, completed())
        self.assertEqual(session.snapshot()["last_cached_tokens"], 256)

    def test_output_budget_honors_a_smaller_caller_limit_and_rejects_invalid_values(self):
        session = ResponsesReasoningSession()
        self.assertEqual(session.prepare(payload(), base_effort="low").payload["max_output_tokens"], 1937)
        for value in (0, -1, True, float("inf"), "2000"):
            data = payload()
            data["max_completion_tokens"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ResponsesReasoningSession().prepare(data, base_effort="low")


def runtime_scope():
    names = """post_openai_turn_request supports_reasoning_effort uses_max_completion_tokens
get_supported_reasoning_efforts get_default_reasoning_effort_for_model normalize_reasoning_effort_for_model
normalize_reasoning_effort supports_temperature_override supports_model_verbosity _parse_gpt_model_version
set_model_transport reset_responses_session_command invalidate_responses_history
create_empty_next_inference_plan set_next_inference_plan_from_pairs clear_next_inference_plan
resolve_next_inference_plan_for_turn set_next_reasoning_effort_command infer_turn_model_controls
get_next_inference_plan_snapshot execute_inference_plan_command""".split()
    scope = {"ASTRA_MODEL": ASTRA_MODEL, "ASTRA_EFFORTS": ASTRA_EFFORTS,
             "ResponsesReasoningError": ResponsesReasoningError, "RESPONSES_REASONING": ResponsesReasoningSession(),
             "MODEL_TRANSPORT": "responses", "AUTH_MODE": "api_key", "DEFAULT_SERVICE_TIER": "regular", "DEFAULT_REASONING_EFFORT": "low",
             "MODEL_WORK": CancellationDomain(), "MODEL_IO": SimpleNamespace(busy=False), "re": re, "uuid": uuid,
             "SETTINGS_TRANSACTION_LOCK": threading.RLock(), "INFERENCE_PLAN_RESULT_SCHEMA": INFERENCE_PLAN_RESULT_SCHEMA,
             "parse_inference_plan_arguments": parse_inference_plan_arguments,
             "normalize_next_inference_pairs": normalize_next_inference_pairs, "inference_plan_version": inference_plan_version,
             "normalize_memory_item": lambda value: str(value or ""), "normalize_text_content": lambda value: str(value or ""),
             "coerce_setting_value": coerce_setting_value, "validate_command_arguments": validate_command_arguments, "require_runtime_setting_unlocked": lambda *args: None,
             "display_message": lambda *args: None, "append_runtime_feedback": lambda *args: None,
             "ALLOWED_REASONING_EFFORTS": {"none", "minimal", *ASTRA_EFFORTS},
             "REASONING_EFFORT_CHOICES_TEXT": "none|minimal|low|medium|high|xhigh|max",
             "agent_state": SimpleNamespace(inference_counter=0, next_inference_plan={}, route_state={}),
             "normalize_nonnegative_int": lambda value, fallback=0: int(value or fallback),
             "build_next_inference_plan_summary": lambda plan=None: json.dumps(plan or {}),
             "build_queue_next_action_runtime_cue": lambda: "fixture", "normalize_model_name": lambda value: value,
             "infer_operating_context": lambda: {"signal_parts": []}, "refresh_gameplay_scene": lambda *args: {"scene": "overworld"},
             "BATTLE_REASONING_KEYWORDS": [], "signal_mentions_keyword": lambda *args: False,
             "GAMEPLAY_SCENE_POLICY": "evidence",
             "detect_blocked_progress_signal": lambda: False, "has_recent_known_failures": lambda **kwargs: False,
             "AUTO_DYNAMIC_INFERENCE_ENABLED": False, "DEFAULT_MODEL_VERBOSITY": "low", "DEFAULT_REASONING_SUMMARY_MODE": "auto",
             "normalize_model_verbosity": lambda value, fallback="medium": value or fallback,
             "normalize_reasoning_summary_mode": lambda value, fallback="auto": value or fallback,
             "normalize_image_detail": lambda value, fallback="low": value or fallback,
             "normalize_image_detail_for_model": lambda value, model, fallback="low": value or fallback,
             "image_detail": "low", "latest_image_detail": "low", "DEFAULT_MODEL_TEMPERATURE": 0,
             "set_runtime_value": lambda *args: None, "summarize_runtime_text": lambda text, **kwargs: text}
    exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                 str(ingress.ROOT/'aurora2.py'), "exec"), scope)
    return scope


class RuntimeResponsesTests(unittest.TestCase):
    def test_one_turn_service_priority_restores_session_default(self):
        scope = runtime_scope()
        scope["set_next_inference_plan_from_pairs"]({"service_tier": "priority"})
        first = scope["infer_turn_model_controls"]("one", ASTRA_MODEL, 1)
        second = scope["infer_turn_model_controls"]("two", ASTRA_MODEL, 2)
        self.assertEqual(first["service_tier"], "priority")
        self.assertEqual(second["service_tier"], "regular")
        self.assertEqual(scope["DEFAULT_SERVICE_TIER"], "regular")

    def setUp(self):
        self.scope = runtime_scope()
        self.calls = []
        def post(body, endpoint, timeout):
            self.calls.append((copy.deepcopy(body), endpoint, timeout))
            return SimpleNamespace(status_code=200, json=lambda: completed(len(self.calls))), "api_key"
        self.scope["post_openai_model_request"] = post

    def turn(self, effort="low"):
        return self.scope["post_openai_turn_request"](payload(effort), current_messages=payload()["messages"])

    def test_existing_assistant_one_turn_command_drives_high_then_explicit_return(self):
        self.turn()
        self.scope["agent_state"].inference_counter = 1
        self.assertTrue(self.scope["set_next_reasoning_effort_command"](["high", "puzzle"], False)["success"])
        plan_id = self.scope["agent_state"].next_inference_plan["plan_id"]
        controls = self.scope["infer_turn_model_controls"]("puzzle", ASTRA_MODEL, 2)
        self.assertEqual(controls["reasoning_effort"], "high")
        self.assertEqual(controls["inference_plan_id"], plan_id)
        self.turn(controls["reasoning_effort"])
        controls = self.scope["infer_turn_model_controls"]("solved", ASTRA_MODEL, 3)
        self.assertEqual(controls["reasoning_effort"], "low")
        self.assertEqual(controls["inference_plan_id"], "")
        self.turn(controls["reasoning_effort"])
        self.assertEqual([call[0]["reasoning"]["effort"] for call in self.calls], ["low"] * 3)
        self.assertEqual([call[0]["input"][-2]["reasoning"]["effort"] for call in self.calls[1:]], ["high", "low"])
        self.assertEqual({call[1] for call in self.calls}, {"responses"})
        self.assertEqual(self.scope["DEFAULT_REASONING_EFFORT"], "low")

    def test_reasoning_lock_blocks_assistant_override(self):
        def locked(*args):
            raise RuntimeError("locked")
        self.scope["require_runtime_setting_unlocked"] = locked
        self.assertFalse(self.scope["set_next_reasoning_effort_command"](["high"], False)["success"])
        self.assertEqual(self.scope["agent_state"].next_inference_plan, {})

    def test_astra_capabilities_and_legacy_normalization(self):
        self.assertEqual(self.scope["get_supported_reasoning_efforts"](ASTRA_MODEL), set(ASTRA_EFFORTS))
        self.assertTrue(self.scope["uses_max_completion_tokens"](ASTRA_MODEL))
        self.assertFalse(self.scope["supports_temperature_override"](ASTRA_MODEL))
        self.assertEqual(self.scope["normalize_reasoning_effort_for_model"]("none", ASTRA_MODEL), "low")
        self.assertEqual(self.scope["normalize_reasoning_effort_for_model"]("max", "gpt-5.4"), "xhigh")
        self.assertEqual(self.scope["get_supported_reasoning_efforts"]("gpt-4o"), set())

    def test_chat_completions_remains_a_direct_unchanged_lane(self):
        self.scope["MODEL_TRANSPORT"] = "chat_completions"
        seen = []
        self.scope["post_openai_chat_completions"] = lambda body, timeout: seen.append((body, timeout)) or ("chat", "api_key")
        self.assertEqual(self.turn(), ("chat", "api_key"))
        self.assertEqual(seen[0], (payload(), 60))
        self.assertEqual(self.calls, [])

    def test_reversible_transport_setting_preserves_chain_until_intervening_call(self):
        self.turn()
        session = self.scope["RESPONSES_REASONING"]
        before = session.snapshot()
        self.scope["set_model_transport"]("chat_completions")
        self.scope["set_model_transport"]("responses")
        self.assertEqual(session.snapshot(), before)
        self.scope["set_model_transport"]("chat_completions")
        self.scope["post_openai_chat_completions"] = lambda *args, **kwargs: ("chat", "api_key")
        self.turn()
        self.assertEqual(session.snapshot()["status"], "blocked")
        self.assertFalse(session.snapshot()["completion_uncertain"])

    def test_failure_and_cancellation_block_without_fallback_or_late_apply(self):
        for cancel in (False, True):
            self.scope = runtime_scope()
            sent = []
            def post(*args, **kwargs):
                sent.append(True)
                if cancel:
                    self.scope["MODEL_WORK"].cancel("stop")
                    return SimpleNamespace(status_code=200, json=lambda: completed(text="PYAG:press(a)")), "api_key"
                raise TimeoutError("lost completion")
            self.scope["post_openai_model_request"] = post
            with self.subTest(cancel=cancel), self.assertRaises((WorkCancelled, TimeoutError)):
                self.turn("high")
            with self.assertRaises(ResponsesReasoningError):
                self.turn("high")
            self.assertEqual(len(sent), 1)
            self.assertEqual(self.scope["RESPONSES_REASONING"].snapshot()["effective_effort"], "")

    def test_auth_filter_and_busy_guards_have_no_network_effect(self):
        self.scope["AUTH_MODE"] = "auto"
        with self.assertRaises(ResponsesReasoningError):
            self.turn()
        self.scope["AUTH_MODE"] = "api_key"
        with self.assertRaises(ResponsesReasoningError):
            self.scope["post_openai_turn_request"](payload(), current_messages=[], prompt_inclusion_effective=True)
        self.scope["MODEL_IO"].busy = True
        with self.assertRaises(ResponsesReasoningError):
            self.scope["set_model_transport"]("chat_completions")
        with self.assertRaises(ResponsesReasoningError):
            self.scope["reset_responses_session_command"]([], True)
        self.assertEqual(self.calls, [])

    def test_explicit_history_clear_invalidates_and_cancels_provider_context(self):
        self.turn()
        generation = self.scope["MODEL_WORK"].token().generation
        self.scope["invalidate_responses_history"]("clear_all")
        self.assertGreater(self.scope["MODEL_WORK"].token().generation, generation)
        with self.assertRaises(ResponsesReasoningError):
            self.turn()
        self.scope["reset_responses_session_command"]([], True)
        self.turn()
        self.assertNotIn("previous_response_id", self.calls[-1][0])

    def test_pending_request_blocks_transport_and_reset_before_io_starts(self):
        session = self.scope["RESPONSES_REASONING"]
        request = session.prepare(payload(), base_effort="low")
        with self.assertRaises(ResponsesReasoningError):
            self.scope["set_model_transport"]("chat_completions")
        with self.assertRaises(ResponsesReasoningError):
            self.scope["reset_responses_session_command"]([], True)
        session.invalidate("history cleared during request")
        self.assertTrue(session.snapshot()["completion_uncertain"])
        with self.assertRaises(ResponsesReasoningError):
            session.complete(request, completed())


class AssistantReasoningPolicyTests(unittest.TestCase):
    def setUp(self):
        self.harness = ingress.RuntimeIngressTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.scope = scope = self.harness.scope
        controller = runtime_scope()
        # Install the real controller functions in the same globals as admission.
        names = ["set_next_reasoning_effort_command", "reset_responses_session_command",
                 "set_next_inference_plan_from_pairs", "create_empty_next_inference_plan",
                 "normalize_reasoning_effort", "evaluate_assistant_command_policy", "evaluate_task_flow_permission", "get_command_name",
                 "get_next_inference_plan_snapshot", "execute_inference_plan_command"]
        scope.update({key: value for key, value in controller.items() if key not in scope})
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                     str(ingress.ROOT/'aurora2.py'), "exec"), scope)
        scope.update({"ASSISTANT_POLICY": "legacy", "infer_operating_context": lambda: {}, "build_semantic_command_identity": lambda *a, **k: {},
                      "assess_command_risk": lambda *a: ("runtime", "review", "runtime setting"),
                      "infer_expected_outcome": lambda *a, **k: "runtime setting", "get_pyag_action_name": lambda *a: ""})
        scope["command_dispatch"].update({name: scope[handler] for name, handler in {
            "SET_NEXT_REASONING_EFFORT": "set_next_reasoning_effort_command",
            "RESET_RESPONSES_SESSION": "reset_responses_session_command"}.items()})

    def test_policy_allows_only_valid_unlocked_one_turn_effort(self):
        policy = self.scope["evaluate_assistant_command_policy"]
        self.assertEqual(policy("SET_NEXT_REASONING_EFFORT(high,puzzle)")["decision"], "allow")
        self.assertEqual(policy("SET_NEXT_REASONING_EFFORT(ultra)")["decision"], "reject")
        self.assertEqual(policy("SET_NEXT_REASONING_EFFORT(high,note,extra)")["decision"], "reject")
        for command in ("SET_NEXT_INFERENCE(reasoning_effort=high)", "SET_MODEL_TRANSPORT(responses)",
                        "SET_SESSION_REASONING_EFFORT(high)"):
            self.assertEqual(policy(command)["decision"], "hold")
        self.scope["require_runtime_setting_unlocked"] = lambda *args: (_ for _ in ()).throw(RuntimeError("locked"))
        self.assertEqual(policy("SET_NEXT_REASONING_EFFORT(high)")["decision"], "reject")

    def test_invalid_reset_or_effort_rejects_whole_batch_and_lock_failure_stops_tail(self):
        for command in ("RESET_RESPONSES_SESSION(extra)", "SET_NEXT_REASONING_EFFORT(high,note,extra)",
                        "SET_NEXT_REASONING_EFFORT(ultra)"):
            result = self.scope["handle_commands"]("SET_TIME_LOGGING(on); " + command)
            self.assertFalse(result["success"], result)
            self.assertEqual(result["executed_commands"], [])
            self.assertEqual(self.harness.executed, [])
        self.scope["require_runtime_setting_unlocked"] = lambda *args: (_ for _ in ()).throw(RuntimeError("locked"))
        result = self.scope["handle_commands"]("SET_NEXT_REASONING_EFFORT(high); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"], result)
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(self.harness.executed, [])


if __name__ == "__main__":
    unittest.main()
