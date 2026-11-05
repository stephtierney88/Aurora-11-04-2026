"""One-turn inference contracts and real runtime queue transitions; no native or model I/O."""
import ast
import copy
import json
import threading
import unittest
import uuid
from types import SimpleNamespace

import test_aurora_command_ingress as ingress
import test_aurora_setting_commands as settings
from aurora_command_catalog import build_command_catalog, parse_dispatch
from aurora_command_contracts import (
    INFERENCE_PLAN_COMMANDS, INFERENCE_PLAN_RESULT_SCHEMA, NEXT_INFERENCE_ALIASES,
    describe_command_contract, inference_plan_version, normalize_next_inference_pairs,
    parse_inference_plan_arguments,
)


class InferenceOptionTests(unittest.TestCase):
    def test_legacy_fields_aliases_and_zero_are_preserved(self):
        options = parse_inference_plan_arguments("SET_NEXT_INFERENCE", [
            'reasoning: MINIMAL; verbosity_level=high; summary=brief; detail=original; latest_detail=auto',
            'temperature=0; model="future custom model"; text_model=old-model; vision_model=vision; reasoning_model=reasoner',
            'note="inspect; then compare, with evidence"; target_turn=12.0',
        ])
        self.assertEqual(options, {
            "reasoning_effort": "minimal", "verbosity": "high", "summary_mode": "brief",
            "image_detail": "original", "latest_image_detail": "auto", "temperature": "0.00",
            "model": "future custom model", "text_model": "old-model", "vision_model": "vision",
            "reasoning_model": "reasoner", "note": "inspect; then compare, with evidence", "target_turn": 12,
        })

    def test_normalization_does_not_mutate_input_and_identical_aliases_agree(self):
        pairs = {"reasoning": "high", "reasoning_effort": "HIGH", "target_turn": 0}
        before = copy.deepcopy(pairs)
        result = normalize_next_inference_pairs(pairs)
        self.assertEqual(pairs, before)
        self.assertEqual(result, {"reasoning_effort": "high", "target_turn": 0})

    def test_invalid_values_are_rejected_instead_of_ignored_or_coerced(self):
        for value in ("temperature=nan", "temperature=inf", "temperature=-0.1", "temperature=2.1",
                      "verbosity=verbose", "summary=compact", "detail=ultra", "reasoning=ultra",
                      "target_turn=-1; note=x", "target_turn=2.5; note=x", "target_turn=1e999999999; note=x",
                      "reasoning=high; reasoning_effort=low", "note=x; unknown=y",
                      "note=x; not_an_option", "target_turn=5", 'note="unterminated'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_inference_plan_arguments("SET_NEXT_INFERENCE", [value])

    def test_direct_service_scalar_types_and_empty_effort_are_checked(self):
        for pairs in ({"note": []}, {"temperature": True}, {"target_turn": {}}, {"model": {}}, {"future": ""}):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                normalize_next_inference_pairs(pairs)
        with self.assertRaises(ValueError):
            parse_inference_plan_arguments("SET_NEXT_REASONING_EFFORT", ["", "note"])
        self.assertEqual(normalize_next_inference_pairs({"reasoning": "", "note": "keep"}), {"note": "keep"})

    def test_query_clear_arity_and_model_specific_efforts_remain_explicit(self):
        for name in INFERENCE_PLAN_COMMANDS:
            self.assertEqual(parse_inference_plan_arguments(name, []), {})
        for name in ("CLEAR_NEXT_INFERENCE", "SHOW_NEXT_INFERENCE"):
            with self.assertRaises(ValueError):
                parse_inference_plan_arguments(name, ["extra"])
        for value in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            self.assertEqual(parse_inference_plan_arguments("SET_NEXT_REASONING_EFFORT", [value])["reasoning_effort"], value)
        with self.assertRaises(ValueError):
            parse_inference_plan_arguments("SET_NEXT_REASONING_EFFORT", ["high", "note", "extra"])

    def test_descriptions_publish_contracts_without_removing_bindings(self):
        rows = {r["command"]: r for r in build_command_catalog(ingress.ROOT)["commands"]}
        self.assertEqual(len(rows), 376)
        for name in INFERENCE_PLAN_COMMANDS:
            self.assertEqual(rows[name]["contract"], describe_command_contract(name))
            self.assertEqual(rows[name]["contract"]["result"]["receipt_field"], "inference_plan_results")
            self.assertEqual(rows[name]["contract"]["parameter_validation"], "pre_dispatch")
        self.assertEqual(set(rows["SET_NEXT_INFERENCE"]["contract"]["parameters"][0]["accepted_aliases"]), set(NEXT_INFERENCE_ALIASES))


class InferencePlanRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = settings.SettingCommandTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope = s = self.fixture.scope
        self.state = s.setdefault("agent_state", SimpleNamespace())
        self.state.inference_counter = 7
        names = {
            "create_empty_next_inference_plan", "get_next_inference_plan_snapshot", "build_next_inference_plan_summary",
            "has_effective_next_inference_plan", "clear_next_inference_plan", "set_next_inference_plan_from_pairs",
            "resolve_next_inference_plan_for_turn", "execute_inference_plan_command", "set_next_inference_command",
            "set_next_reasoning_effort_command", "clear_next_inference_command", "show_next_inference_command",
        }
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), s)
        s.update({"uuid": uuid, "INFERENCE_PLAN_RESULT_SCHEMA": INFERENCE_PLAN_RESULT_SCHEMA,
                  "parse_inference_plan_arguments": parse_inference_plan_arguments,
                  "normalize_next_inference_pairs": normalize_next_inference_pairs,
                  "inference_plan_version": inference_plan_version})
        self.state.next_inference_plan = s["create_empty_next_inference_plan"]()
        s["next_inference_plan"] = self.state.next_inference_plan
        bindings = parse_dispatch(ingress.TREE, "command_dispatch")
        s["command_dispatch"].update({name: s[bindings[name]] for name in INFERENCE_PLAN_COMMANDS})

    def run_batch(self, command):
        return self.scope["handle_commands"](command)

    def replace(self, **pairs):
        return self.scope["set_next_inference_plan_from_pairs"](pairs)

    def test_malformed_batch_tail_prevents_all_earlier_effects(self):
        for command in ("SET_NEXT_INFERENCE(verbosity=bad; note=x)", "SET_NEXT_INFERENCE(temperature=nan)",
                        "SET_NEXT_INFERENCE(reasoning=high; typoo=low)", "SET_NEXT_INFERENCE(note=x; garbage)",
                        "CLEAR_NEXT_INFERENCE(extra)", "SHOW_NEXT_INFERENCE(extra)"):
            result = self.run_batch("SET_TIME_LOGGING(on); " + command)
            self.assertFalse(result["success"], result)
            self.assertEqual(result["executed_commands"], [])
            self.assertEqual(self.fixture.harness.executed, [])
            self.assertEqual(self.state.next_inference_plan["target_turn"], 0)

    def test_read_replace_and_clear_have_detached_before_after_receipts(self):
        before = copy.deepcopy(self.state.next_inference_plan)
        result = self.run_batch("SET_NEXT_INFERENCE(reasoning=high; note=puzzle; target_turn=12)")
        self.assertTrue(result["success"], result)
        outcome = result["inference_plan_results"][0]
        self.assertEqual(outcome["before_plan"], before)
        self.assertEqual(outcome["plan"]["target_turn"], 12)
        self.assertEqual(outcome["plan"]["queued_at_turn"], 7)
        self.assertTrue(outcome["plan"]["plan_id"])
        self.assertEqual(outcome["plan"]["source"], "operator")
        self.assertEqual(outcome["after_version"], inference_plan_version(self.state.next_inference_plan))
        self.assertEqual(outcome["effect_status"], "observed")
        json.dumps(outcome, allow_nan=False)
        for command in ("SET_NEXT_INFERENCE()", "SET_NEXT_REASONING_EFFORT()", "SHOW_NEXT_INFERENCE()"):
            read = self.run_batch(command)["inference_plan_results"][0]
            self.assertEqual(read["operation"], "read")
            self.assertEqual(read["before_version"], read["after_version"])
            self.assertEqual(read["plan"]["plan_id"], outcome["plan"]["plan_id"])
        outcome["plan"]["note"] = "mutated caller copy"
        self.assertEqual(self.state.next_inference_plan["note"], "puzzle")
        cleared = self.run_batch("CLEAR_NEXT_INFERENCE()")["inference_plan_results"][0]
        self.assertEqual(cleared["operation"], "clear")
        self.assertEqual(cleared["plan"]["target_turn"], 0)
        self.assertNotEqual(cleared["before_version"], cleared["after_version"])

    def test_each_setting_lock_blocks_atomic_replacement_and_batch_tail(self):
        initial = self.replace(note="keep old plan")
        for lock, options in (("models", "model=custom; note=x"), ("reasoning", "reasoning=high; note=x"),
                              ("reasoning", "verbosity=high; note=x"), ("reasoning", "summary=brief; note=x"),
                              ("temperature", "temperature=0; note=x"), ("reasoning", "service_tier=priority")):
            with self.subTest(lock=lock, options=options):
                self.fixture.locks[lock] = True
                result = self.run_batch("SET_NEXT_INFERENCE(" + options + "); SET_TIME_LOGGING(on)")
                self.fixture.locks[lock] = False
                self.assertFalse(result["success"], result)
                self.assertEqual(result["inference_plan_results"][0]["effect_status"], "not_started")
                self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
                self.assertEqual(self.state.next_inference_plan, initial)

    def test_queries_and_clear_work_while_setting_locks_are_enabled(self):
        self.replace(reasoning="high")
        self.fixture.locks.update({key: True for key in self.fixture.locks})
        for command in ("SHOW_NEXT_INFERENCE()", "SET_NEXT_INFERENCE()", "SET_NEXT_REASONING_EFFORT()", "CLEAR_NEXT_INFERENCE()"):
            result = self.run_batch(command)
            self.assertTrue(result["success"], result)

    def test_service_preserves_inputs_and_returns_detached_state(self):
        pairs = {"reasoning": "high", "note": "original"}
        before = copy.deepcopy(pairs)
        queued = self.scope["set_next_inference_plan_from_pairs"](pairs)
        self.assertEqual(pairs, before)
        queued["note"] = "caller edit"
        self.assertEqual(self.state.next_inference_plan["note"], "original")
        self.assertEqual(self.scope["build_next_inference_plan_summary"]({}), "")
        self.assertFalse(self.scope["has_effective_next_inference_plan"]({}))

    def test_future_zero_and_past_targets_retain_one_turn_semantics(self):
        resolve = self.scope["resolve_next_inference_plan_for_turn"]
        future = self.replace(note="future", target_turn=20)
        self.assertIsNone(resolve(19))
        self.assertEqual(resolve(20), future)
        self.assertIsNone(resolve(20))
        self.assertIsNone(resolve(21))
        automatic = self.replace(note="automatic", target_turn=0)
        self.assertEqual(automatic["target_turn"], 8)
        self.assertEqual(resolve(8)["plan_id"], automatic["plan_id"])
        past = self.replace(note="past target", target_turn=1)
        self.assertEqual(resolve(9)["plan_id"], past["plan_id"])

    def test_effort_shortcut_replaces_plan_without_changing_session_defaults(self):
        self.replace(model="future custom model", temperature=0.7)
        session_before = self.fixture.version()
        result = self.scope["execute_inference_plan_command"]("SET_NEXT_REASONING_EFFORT", ["max", "puzzle"], False)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["plan"]["reasoning_effort"], "max")
        self.assertEqual(result["plan"]["model"], "")
        self.assertEqual(result["plan"]["source"], "assistant")
        self.assertTrue(result["plan"]["auto_generated"])
        self.assertEqual(self.fixture.version(), session_before)

    def test_partial_service_failure_is_uncertain_and_blocks_tail(self):
        self.scope["append_runtime_feedback"] = lambda *args: (_ for _ in ()).throw(RuntimeError("feedback failed after assignment"))
        result = self.run_batch("SET_NEXT_INFERENCE(note=changed); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"], result)
        row = result["inference_plan_results"][0]
        self.assertEqual(row["effect_status"], "uncertain")
        self.assertEqual(row["plan"]["note"], "changed")
        self.assertNotEqual(row["before_version"], row["after_version"])
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_consuming_old_plan_cannot_clear_a_concurrent_replacement(self):
        old = self.replace(note="old")
        entered, release, attempted, replaced = (threading.Event() for _ in range(4))
        real_clear = self.scope["clear_next_inference_plan"]
        results, errors = [], []
        def delayed_clear():
            entered.set()
            if not release.wait(3):
                raise TimeoutError("fixture gate")
            return real_clear()
        self.scope["clear_next_inference_plan"] = delayed_clear
        def consume():
            try:
                results.append(self.scope["resolve_next_inference_plan_for_turn"](8))
            except Exception as error:
                errors.append(error)
        def replace():
            attempted.set()
            try:
                self.replace(note="new")
                replaced.set()
            except Exception as error:
                errors.append(error)
        a, b = threading.Thread(target=consume), threading.Thread(target=replace)
        a.start()
        try:
            self.assertTrue(entered.wait(2))
            b.start()
            self.assertTrue(attempted.wait(2))
            self.assertFalse(replaced.wait(0.08), "replacement must wait for the old plan's atomic consume")
        finally:
            release.set()
            a.join(3)
            if b.ident is not None:
                b.join(3)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [old])
        self.assertEqual(self.state.next_inference_plan["note"], "new")
        self.assertNotEqual(self.state.next_inference_plan["plan_id"], old["plan_id"])

    def test_unavailable_readback_reports_uncertainty_without_mutation(self):
        before = copy.deepcopy(self.state.next_inference_plan)
        self.scope["get_next_inference_plan_snapshot"] = lambda: (_ for _ in ()).throw(RuntimeError("readback unavailable"))
        result = self.run_batch("SET_NEXT_INFERENCE(note=never assigned); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"], result)
        self.assertEqual(result["inference_plan_results"][0]["effect_status"], "uncertain")
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(self.state.next_inference_plan, before)


if __name__ == "__main__":
    unittest.main()
