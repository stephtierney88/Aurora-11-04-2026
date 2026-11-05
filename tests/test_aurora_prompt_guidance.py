import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PromptGuidanceTests(unittest.TestCase):
    def test_current_and_legacy_selection_and_explicit_override(self):
        source = (ROOT / "aurora2.py").read_text(encoding="utf-8-sig")
        block = source[source.index('INIT_PROMPT_PROFILE ='):source.index('# Input and Output Settings')]
        for profile in ("current", "legacy"):
            with self.subTest(profile=profile), patch.dict(os.environ, {"AURORA_INIT_PROMPT_PROFILE": profile}, clear=True):
                scope = {"os": os}
                exec(block, scope)
                self.assertEqual(scope["COMMAND_DISCOVERY_CONTEXT"], profile == "current")
                if profile == "legacy":
                    self.assertEqual(scope["test_init_prompt"], scope["legacy_test_init_prompt"])
                    self.assertEqual(scope["LIVE_INIT_FILENAME"], "aurora2_init_legacy.txt")
                else:
                    self.assertIn("LOOKUP_COMMAND", scope["test_init_prompt"])
                    self.assertNotEqual(scope["test_init_prompt"], scope["legacy_test_init_prompt"])
        with patch.dict(os.environ, {"AURORA_LIVE_INIT_FILENAME": "custom.txt", "AURORA_COMMAND_DISCOVERY_CONTEXT": "off"}, clear=True):
            scope = {"os": os}
            exec(block, scope)
            self.assertEqual(scope["LIVE_INIT_FILENAME"], "custom.txt")
            self.assertFalse(scope["COMMAND_DISCOVERY_CONTEXT"])

    def test_discovery_reaches_model_context_only_when_enabled_and_model_requested(self):
        tree = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "publish_command_discovery")
        displayed, history = [], []
        scope = {"display_message": lambda *args: displayed.append(args),
                 "update_chat_history": lambda *args: history.append(args), "COMMAND_DISCOVERY_CONTEXT": True,
                 "READBACK_WAKE_ENABLED": False, "TASK_CONTINUATION_MODE": "legacy"}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "discovery", "exec"), scope)
        scope["publish_command_discovery"](False, "Signature: LOOKUP_COMMAND(name, high)")
        self.assertIn("Signature: LOOKUP_COMMAND", history[0][1])
        scope["publish_command_discovery"](True, "operator-only")
        scope["COMMAND_DISCOVERY_CONTEXT"] = False
        scope["publish_command_discovery"](False, "legacy-terminal-only")
        self.assertEqual(len(history), 1)
        self.assertEqual(len(displayed), 3)

    def test_current_extended_profile_fits_default_cap_and_legacy_is_preserved(self):
        current = (ROOT / "aurora2_init.txt").read_text(encoding="utf-8-sig")
        legacy = (ROOT / "aurora2_init_legacy.txt").read_text(encoding="utf-8-sig")
        self.assertLess(len(current), 12000)
        self.assertGreater(len(legacy), 12000)
        for name in ("SEARCH_COMMANDS", "LOOKUP_COMMAND", "SET_NEXT_INFERENCE", "REQUEST_SCREENSHOT_CAPTURE"):
            self.assertIn(name, current)

    def test_screenshot_turn_guidance_matches_profile_without_single_step_conflict(self):
        tree = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
        names = {"LEGACY_SCREENSHOT_REVIEW_PROMPT", "DEFAULT_SCREENSHOT_REVIEW_PROMPT"}
        nodes = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
        for profile in ("current", "legacy"):
            scope = {"INIT_PROMPT_PROFILE": profile}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "screenshot-prompt", "exec"), scope)
            prompt = scope["DEFAULT_SCREENSHOT_REVIEW_PROMPT"]
            if profile == "legacy":
                self.assertIn("at most one", prompt)
            else:
                self.assertIn("2-4 actions", prompt)
                self.assertNotIn("at most one", prompt)
                self.assertIn("REQUEST_SCREENSHOT_CAPTURE", prompt)

    def test_main_enable_preserves_settings_and_start_is_paused(self):
        tree = ast.parse((ROOT / "aurora2_control_panel.py").read_text(encoding="utf-8-sig"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AuroraControlPanel")
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "start_or_enable_runtime")
        launched, commands = [], []
        scope = {"decorate_state_processes": lambda state: state,
                 "launch_runtime_process": lambda **kwargs: launched.append(kwargs)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "panel-start", "exec"), scope)
        app = SimpleNamespace(state_cache={"processes": {"runtime": {"active": False}}},
            conversation_delivery_var=SimpleNamespace(set=lambda text: None), send_raw=commands.append,
            after=lambda *args: None, refresh_now=lambda: None)
        scope["start_or_enable_runtime"](app)
        self.assertEqual(launched, [{"with_ui": False, "paused": True}])
        self.assertEqual(commands, [])
        app.state_cache["processes"]["runtime"]["active"] = True
        scope["start_or_enable_runtime"](app)
        self.assertEqual(commands, ["SET_LIVE_MODE(on)"])


if __name__ == "__main__":
    unittest.main()
