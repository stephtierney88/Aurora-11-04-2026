"""Real response/hierarchy functions with no runtime import or native I/O."""
import ast
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from aurora_settings_registry import coerce_setting_value

TREE = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
FUNCTIONS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}


class HorizonControlsTests(unittest.TestCase):
    def setUp(self):
        self.routes = []
        self.fresh = False
        state = SimpleNamespace(pinned_immediate_actions=["manual now"], pinned_short_term_actions=["manual short"],
                                mid_term_context=["manual mid"], long_term_context=["manual long"])
        noop = lambda *a, **k: None
        self.scope = s = dict(
            split_response_sections=lambda text: ("", "fresh" if self.fresh else "", {}, text),
            write_chat_history_log=noop, summarize_runtime_text=lambda v, **k: v,
            normalize_action_command=str, normalize_memory_item=str, split_commands_preserving_parentheses=lambda text: [],
            GAMEPLAY_SCENE_POLICY="legacy", score_recent_action_outcomes=noop, TASK_CONTINUATION_MODE="legacy",
            maybe_run_game_focus_recovery=noop, route_assistant_commands=lambda *a, **k: self.routes.append((a, k)),
            promote_response_memory=noop, promote_associated_goals_from_tasks=noop, auto_execute_pending_commands=noop,
            update_pinned_information=noop, parse_hierarchical_tasks=noop, agent_state=state,
            hierarchical_tasks=[[{"command": "GB:press(a)"}]], MAX_ROUTE_ITEMS=8, MAX_MID_TERM_ITEMS=8, MAX_LONG_TERM_ITEMS=10,
            dedupe_preserve_order=lambda seq: list(dict.fromkeys(seq)), SETTINGS_TRANSACTION_LOCK=threading.RLock(),
            GOAL_LOCK=threading.RLock(), HIERARCHY_DISPATCH="legacy", HORIZON_SYNC="legacy", HIERARCHY_DISPATCH_ARMED=True,
            require_runtime_setting_unlocked=noop, coerce_setting_value=coerce_setting_value, display_message=noop)
        names = ("process_assistant_response", "execute_immediate_actions", "sync_action_horizons_from_hierarchical_tasks",
                 "summarize_hierarchical_action", "set_hierarchy_dispatch", "set_horizon_sync",
                 "set_hierarchy_dispatch_command", "set_horizon_sync_command")
        exec(compile(ast.Module(body=[FUNCTIONS[n] for n in names], type_ignores=[]), "aurora2.py", "exec"), s)

    def response(self):
        self.scope["process_assistant_response"]("ordinary response")

    def test_legacy_retained_hierarchy_behavior_remains(self):
        self.response(); self.response()
        self.assertEqual(len(self.routes), 2)

    def test_advisory_blocks_retained_and_fresh_hierarchy(self):
        self.scope["set_hierarchy_dispatch"]("advisory")
        self.response(); self.fresh = True; self.response()
        self.assertFalse(self.routes)
        self.assertTrue(self.scope["hierarchical_tasks"][0])

    def test_reenable_requires_fresh_hierarchy(self):
        self.scope["set_hierarchy_dispatch"]("advisory")
        self.scope["set_hierarchy_dispatch"]("legacy")
        self.response()
        self.assertFalse(self.routes)
        self.fresh = True; self.response()
        self.assertEqual(len(self.routes), 1)

    def test_preserve_keeps_all_manual_lists(self):
        self.scope["set_horizon_sync"]("preserve")
        self.fresh = True; self.response()
        self.assertEqual(vars(self.scope["agent_state"]), dict(pinned_immediate_actions=["manual now"],
            pinned_short_term_actions=["manual short"], mid_term_context=["manual mid"], long_term_context=["manual long"]))

    def test_legacy_sync_still_replaces_and_clears_missing_levels(self):
        self.scope["sync_action_horizons_from_hierarchical_tasks"]()
        self.assertEqual(self.scope["agent_state"].pinned_immediate_actions, ["GB:press(a)"])
        self.assertFalse(self.scope["agent_state"].long_term_context)

    def test_noop_does_not_rearm_after_toggle(self):
        self.scope["set_hierarchy_dispatch"]("advisory")
        self.scope["set_hierarchy_dispatch"]("legacy")
        self.scope["set_hierarchy_dispatch"]("legacy")
        self.assertFalse(self.scope["HIERARCHY_DISPATCH_ARMED"])

    def test_invalid_policy_and_model_write_do_not_mutate(self):
        for name in ("set_hierarchy_dispatch", "set_horizon_sync"):
            with self.assertRaises(ValueError): self.scope[name]("invalid")
        for name, value in (("set_hierarchy_dispatch_command", "advisory"), ("set_horizon_sync_command", "preserve")):
            with self.assertRaises(ValueError): self.scope[name]([value], False)
            self.assertTrue(self.scope[name]([], False))
        self.assertEqual(self.scope["HIERARCHY_DISPATCH"], "legacy")
        self.assertEqual(self.scope["HORIZON_SYNC"], "legacy")

    def test_explicit_commands_remain_independent_of_advisory(self):
        self.scope["set_hierarchy_dispatch"]("advisory")
        self.scope["split_response_sections"] = lambda text: ("UPDATE_CONTEXT(verified)", "", {}, text)
        self.response()
        self.assertEqual(len(self.routes), 1)
        self.assertEqual(self.routes[0][1]["source"], "assistant_response")

    def test_policy_change_between_actions_stops_unadmitted_tail(self):
        def route(*args, **kwargs):
            self.routes.append((args, kwargs))
            self.scope["set_hierarchy_dispatch"]("advisory")
        self.scope["route_assistant_commands"] = route
        self.scope["execute_immediate_actions"]([{"command": "GB:press(a)"}, {"command": "GB:press(b)"}])
        self.assertEqual([args[0] for args, _ in self.routes], ["GB:press(a)"])
        self.assertFalse(self.scope["HIERARCHY_DISPATCH_ARMED"])


if __name__ == "__main__":
    unittest.main()
