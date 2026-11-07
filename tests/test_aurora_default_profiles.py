"""Defaults compatibility, durable saves and real runtime transitions without native I/O."""
import ast
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aurora_default_profiles as profiles
import test_aurora_command_ingress as ingress
import test_aurora_setting_commands as settings
from aurora_command_catalog import build_command_catalog, parse_dispatch
from aurora_command_contracts import describe_command_contract


class ProfileFileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="aurora-defaults-test-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "personal.json"

    def test_missing_invalid_unreadable_and_empty_are_distinct(self):
        self.assertEqual(profiles.read_profile_document(self.path)["status"], "missing")
        for text in ('{bad', '{"temperature":0,"temperature":1}', '{"future":NaN}', '{"future":1e9999}',
                     '{"overlay":false}', '{"advanced":[]}', '[]'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(profiles.read_profile_document(self.path)["status"], "invalid")
        with patch.object(Path, "open", side_effect=PermissionError("fixture sharing error")):
            self.assertEqual(profiles.read_profile_document(self.path)["status"], "unreadable")
        self.path.write_text("{}", encoding="utf-8")
        self.assertEqual(profiles.read_profile_document(self.path)["status"], "available")

    def test_save_preserves_unknown_fields_and_off_states(self):
        old = {"future": {"mode": "kept"}, "advanced": {"future_knob": 8, "show_ai_text": True}, "temperature": 1}
        self.path.write_text(json.dumps(old), encoding="utf-8")
        result = profiles.save_profile_document(self.path, {"temperature": 0, "advanced": {"show_ai_text": False}})
        self.assertTrue(result["success"], result)
        self.assertEqual(profiles.read_profile_document(self.path)["profile"],
                         {"future": old["future"], "temperature": 0, "advanced": {"future_knob": 8, "show_ai_text": False}})
        self.assertNotEqual(result["before_file_version"], result["file_version"])
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_disk_failures_preserve_original_bytes_and_clean_temp(self):
        self.path.write_text('{"temperature":0.5}', encoding="utf-8")
        before = self.path.read_bytes()
        for function in ("replace", "fsync"):
            with self.subTest(function=function), patch.object(profiles.os, function, side_effect=OSError("fixture disk failure")):
                result = profiles.save_profile_document(self.path, {"temperature": 0.7})
            self.assertFalse(result["success"])
            self.assertEqual(result["effect_status"], "not_started")
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_or_oversized_file_is_preserved(self):
        self.path.write_text("broken", encoding="utf-8")
        self.assertFalse(profiles.save_profile_document(self.path, {})["success"])
        self.assertEqual(self.path.read_text(), "broken")
        self.path.write_text('{"future":"' + 'x' * 64 + '"}', encoding="utf-8")
        before = self.path.read_bytes()
        with patch.object(profiles, "MAX_PROFILE_BYTES", 32):
            self.assertEqual(profiles.read_profile_document(self.path)["status"], "invalid")
            self.assertFalse(profiles.save_profile_document(self.path, {})["success"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_external_writer_before_publication_is_preserved(self):
        self.path.write_text('{"temperature":0}', encoding="utf-8")
        original = profiles.os.fsync
        def fsync_and_change(fd):
            original(fd)
            self.path.write_text('{"temperature":1}', encoding="utf-8")
        with patch.object(profiles.os, "fsync", side_effect=fsync_and_change):
            result = profiles.save_profile_document(self.path, {"temperature": 2})
        self.assertFalse(result["success"])
        self.assertEqual(profiles.read_profile_document(self.path)["profile"]["temperature"], 1)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failure_after_publication_is_uncertain_without_replay(self):
        original = profiles.read_profile_document
        calls = []
        def reader(path):
            calls.append(path)
            return ({"status": "unreadable", "version": "", "profile": None, "reason": "fixture sharing error"}
                    if len(calls) >= 3 else original(path))
        with patch.object(profiles, "read_profile_document", side_effect=reader):
            result = profiles.save_profile_document(self.path, {"temperature": 0})
        self.assertFalse(result["success"])
        self.assertEqual(result["effect_status"], "uncertain")
        self.assertEqual(json.loads(self.path.read_text()), {"temperature": 0})
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


class ProfileContractTests(unittest.TestCase):
    def test_snapshot_fields_and_bindings_remain_available(self):
        def fields(node, prefix=""):
            result = []
            for key, child in zip(node.keys, node.values):
                name = prefix + ast.literal_eval(key)
                result.extend(fields(child, name + ".") if isinstance(child, ast.Dict) else [name])
            return result
        node = ingress.FUNCTIONS["_build_runtime_preferences_snapshot"]
        raw = next(n.value for n in node.body if isinstance(n, ast.Return))
        self.assertEqual(set(fields(raw)), set(profiles.PROFILE_FIELDS))
        self.assertEqual(len(fields(raw)), 72)
        rows = {row["command"]: row for row in build_command_catalog(ingress.ROOT)["commands"]}
        self.assertEqual(len(rows), 410)
        for name in profiles.DEFAULT_PROFILE_COMMANDS:
            self.assertEqual(rows[name]["contract"], describe_command_contract(name))
            self.assertEqual(rows[name]["contract"]["result"]["receipt_field"], "default_profile_results")

    def test_aliases_blanks_off_values_and_unknown_fields(self):
        value = {"execution_mode": "guided", "temperature": 0, "text_model": "", "overlay": None,
                 "advanced": {"always_on": "off", "hide_input": "false", "high_detail": -2, "future": True}, "future": {"action": "ignored"}}
        before = copy.deepcopy(value)
        clean, ignored = profiles.normalize_profile_snapshot(value)
        self.assertEqual(value, before)
        self.assertEqual(clean["execution_mode"], "assist")
        self.assertEqual(clean["advanced"], {"always_on": False, "hide_input": False, "high_detail": -2})
        self.assertEqual(ignored, ["advanced.future", "future"])

    def test_invalid_values_reject_without_fallback_or_rounding(self):
        for value in ({"time_logging": "nope"}, {"review_turn_interval": "2.5"}, {"review_turn_interval": -1},
                      {"command_drip_retention_turns": 0}, {"critique_turn_interval": "1e999999"},
                      {"temperature": float("nan")}, {"battle_verbosity": "verbose"},
                      {"unchanged_screenshot_persist_interval": 0.1}, {"advanced": {"max_images_in_history": 0.5}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                profiles.normalize_profile_snapshot(value)


class ProfileRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = settings.SettingCommandTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope = s = self.fixture.scope
        directory = tempfile.TemporaryDirectory(prefix="aurora-default-runtime-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "personal.json"
        names = {row[0] for row in profiles.PROFILE_FIELDS.values() if row[0]} | set("""
            _build_runtime_preferences_snapshot build_runtime_preferences_snapshot _write_default_profile_field
            _default_profile_result _apply_default_profile apply_runtime_preferences_snapshot load_personal_defaults_profile
            save_personal_defaults_profile apply_personal_defaults_profile apply_system_defaults_profile get_default_profiles_status
            execute_default_profile_command save_personal_defaults_command apply_personal_defaults_command apply_system_defaults_command
            show_default_profiles_command normalize_reasoning_effort normalize_reasoning_summary_mode normalize_pending_queue_mode
            normalize_nonnegative_int normalize_image_detail get_unchanged_screenshot_persist_interval get_command_drip_store trim_command_drip_history
        """.split())
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in names], type_ignores=[]), str(ingress.ROOT / "aurora2.py"), "exec"), s)
        for node in ingress.TREE.body:
            if isinstance(node, ast.Assign):
                try: value = ast.literal_eval(node.value)
                except (ValueError, TypeError): continue
                for target in node.targets:
                    if isinstance(target, ast.Name): s.setdefault(target.id, copy.deepcopy(value))
        s.update({name:getattr(profiles, name) for name in """DEFAULT_PROFILE_RESULT_SCHEMA PROFILE_FIELDS SCHEDULER_PROFILE_FIELDS DefaultProfileError
            profile_value coerce_profile_value normalize_profile_snapshot supplied_profile_fields profile_lock_keys
            project_profile_snapshot profile_version read_profile_document save_profile_document validate_default_profile_arguments""".split()})
        s.update({"copy": copy, "personal_defaults_path": str(self.path), "_last_auth_resolution": {"mode": "api_key", "source": "fixture", "error": ""},
                  "GAME_PROFILE_SOURCE": "fixture", "BATTLE_REASONING_EFFORT": "low", "REVIEW_REASONING_EFFORT": "medium", "CRITIQUE_REASONING_EFFORT": "high",
                  "BATTLE_MODEL_VERBOSITY": "low", "REVIEW_MODEL_VERBOSITY": "medium", "CRITIQUE_MODEL_VERBOSITY": "high", "DEFAULT_REASONING_SUMMARY_MODE": "auto",
                  "AUTO_DYNAMIC_INFERENCE_ENABLED": True, "REVIEW_TURN_INTERVAL": 10, "CRITIQUE_TURN_INTERVAL": 20,
                  "DEFAULT_PENDING_QUEUE_MODE": "normal", "COMMAND_DRIP_RETENTION_TURNS": 8, "COMMAND_DRIP_LOOKAHEAD_TURNS": 2,
                  "COMMAND_DRIP_SHOW_VARIANTS": True, "COMMAND_DRIP_SHOW_LIKELY_DROPPED": True,
                  "ENABLE_SOUND_EFFECTS": False, "TIME_LOGGING_ENABLED": False, "CHAT_LOG_ECHO_ENABLED": False,
                  "unchanged_screenshot_persist_interval": 2.5, "refresh_static_overlay": lambda:True,
                  "agent_state": SimpleNamespace(inference_counter=20, command_drip_history=[{"turn":14, "note":"keep on rollback"}])})
        s["SYSTEM_DEFAULT_PROFILE"] = s["build_runtime_preferences_snapshot"]()
        bindings = parse_dispatch(ingress.TREE, "command_dispatch")
        s["command_dispatch"].update({name:s[bindings[name]] for name in profiles.DEFAULT_PROFILE_COMMANDS})

    def apply(self, value, apply_mode="reapply"):
        return self.scope["apply_runtime_preferences_snapshot"](value, return_receipt=True, apply_mode=apply_mode)

    def snapshot(self):
        return self.scope["build_runtime_preferences_snapshot"]()

    def command(self, text):
        return self.scope["handle_commands"](text)

    def test_all_fields_round_trip_with_custom_scheduler_and_explicit_off_states(self):
        target = self.snapshot()
        target.update(turn_scheduler_profile="custom", turn_heartbeat_seconds=3.75, turn_capture_wake_enabled=False,
                      demand_capture_enabled=False, unchanged_screenshot_persist_interval=7.5, review_turn_interval=0,
                      critique_turn_interval=0, auto_dynamic_inference=False, command_drip_show_variants=False,
                      command_drip_show_likely_dropped=False, temperature=0, pending_queue_mode="insert",
                      capture_command_policy="batch_end")
        for section in ("advanced", "overlay"):
            for key, value in target[section].items():
                if isinstance(value, bool): target[section][key] = False
        target["advanced"].update(high_detail=-2, max_images_in_history=0, image_detail="original", latest_image_detail="auto")
        result = self.apply(target)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["profile"], target)
        self.assertEqual(self.scope["MODEL_TRANSPORT"], "chat_completions")
        self.assertEqual(self.scope["save_personal_defaults_profile"](), target)
        self.assertTrue(self.apply({"turn_heartbeat_seconds":1, "unchanged_screenshot_persist_interval":1,
                                    "capture_command_policy":"legacy"})["success"])
        self.assertEqual(self.scope["apply_personal_defaults_profile"](), target)

    def test_legacy_partial_profile_preserves_capture_policy_and_invalid_policy_rejects(self):
        self.assertTrue(self.apply({"capture_command_policy":"batch_end"})["success"])
        self.assertTrue(self.apply({"time_logging":True})["success"])
        self.assertEqual(self.snapshot()["capture_command_policy"], "batch_end")
        before = self.snapshot()
        result = self.apply({"capture_command_policy":"typo", "time_logging":False})
        self.assertFalse(result["success"])
        self.assertEqual(self.snapshot(), before)

    def test_partial_profile_changes_only_present_fields_and_keeps_system_baseline(self):
        before = self.snapshot()
        result = self.apply({"time_logging":True, "advanced":{"hide_input":True}, "future":{"action":"ignored"}})
        expected = copy.deepcopy(before); expected["time_logging"] = True; expected["advanced"]["hide_input"] = True
        self.assertTrue(result["success"], result)
        self.assertEqual(result["profile"], expected)
        self.assertEqual(result["ignored_fields"], ["future"])
        self.assertEqual(self.scope["SYSTEM_DEFAULT_PROFILE"], before)

    def test_named_preset_precedes_manual_overrides(self):
        result = self.apply({"turn_scheduler_profile":"responsive", "turn_heartbeat_seconds":8})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["profile"]["turn_heartbeat_seconds"], 8)
        self.assertEqual(result["profile"]["turn_min_gap_seconds"], self.scope["TURN_SCHEDULER_PROFILES"]["responsive"]["min_gap_seconds"])
        self.assertEqual(result["profile"]["turn_scheduler_profile"], "custom")
        rejected = self.apply({"turn_scheduler_profile":"custom"})
        self.assertFalse(rejected["success"]); self.assertEqual(rejected["attempted_fields"], [])

    def test_cadence_and_drip_integers_keep_precision_and_zero(self):
        large = 9007199254740993
        result = self.apply({"review_turn_interval":large, "critique_turn_interval":0,
                             "command_drip_retention_turns":large, "command_drip_lookahead_turns":large})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["profile"]["review_turn_interval"], large)
        self.assertEqual(result["profile"]["command_drip_lookahead_turns"], large)
        self.assertEqual(self.scope["model_interval"], large)

    def test_empty_personal_profile_is_a_valid_noop_and_system_restore_works(self):
        self.path.write_text("{}", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.scope["apply_personal_defaults_profile"](), before)
        self.assertTrue(self.apply({"time_logging":True})["success"])
        restored = self.command("APPLY_SYSTEM_DEFAULTS()")["default_profile_results"][0]
        self.assertTrue(restored["success"], restored)
        self.assertEqual(restored["profile"], before)

    def test_current_state_survives_final_readback_failure_with_uncertain_receipt(self):
        original = self.scope["build_runtime_preferences_snapshot"]
        calls = []
        def fail_last_read():
            calls.append(True)
            if len(calls) == 3: raise RuntimeError("fixture readback unavailable")
            return original()
        self.scope["build_runtime_preferences_snapshot"] = fail_last_read
        result = self.apply({"time_logging":True})
        self.assertFalse(result["success"])
        self.assertEqual(result["effect_status"], "uncertain")
        self.assertTrue(original()["time_logging"])

    def test_full_validation_and_every_lock_precede_setters(self):
        before = self.snapshot()
        bad = self.apply({"temperature":1, "advanced":{"image_detail":"bad"}})
        self.assertFalse(bad["success"]); self.assertEqual(bad["attempted_fields"], [])
        for lock in profiles.profile_lock_keys(before):
            self.fixture.locks[lock] = True
            with self.subTest(lock=lock):
                result = self.apply(dict(before, temperature=1))
                self.assertFalse(result["success"], result); self.assertEqual(result["attempted_fields"], [])
                self.assertEqual(self.snapshot(), before)
            self.fixture.locks[lock] = False

    def test_bad_arguments_block_prior_batch_effects(self):
        for name in profiles.DEFAULT_PROFILE_COMMANDS:
            result = self.command("SET_TIME_LOGGING(on); " + name + "(extra)")
            self.assertFalse(result["success"]); self.assertEqual(result["executed_commands"], [])

    def test_late_failure_restores_settings_origin_and_history_and_blocks_tail(self):
        before = self.snapshot(); history = copy.deepcopy(self.scope["agent_state"].command_drip_history)
        original = self.scope["set_max_images_in_history"]
        def fail(value):
            result = original(value)
            if value == 1: raise RuntimeError("fixture failure after mutation")
            return result
        self.scope["set_max_images_in_history"] = fail
        self.path.write_text(json.dumps({"game_profile":"blue", "command_drip_retention_turns":1, "advanced":{"max_images_in_history":1}}), encoding="utf-8")
        batch = self.command("APPLY_PERSONAL_DEFAULTS(); SET_TIME_LOGGING(on)")
        result = batch["default_profile_results"][0]
        self.assertFalse(batch["success"]); self.assertEqual(result["effect_status"], "restored", result)
        self.assertEqual(result["restoration"], {"attempted":True, "state_restored":True, "errors":[]})
        self.assertEqual(self.snapshot(), before); self.assertEqual(self.scope["GAME_PROFILE_SOURCE"], "fixture")
        self.assertEqual(self.scope["agent_state"].command_drip_history, history)
        self.assertEqual(batch["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_unrestorable_value_remains_uncertain(self):
        original = self.scope["set_time_logging_enabled"]
        def fail(value):
            original(True)
            raise RuntimeError("fixture cannot restore")
        self.scope["set_time_logging_enabled"] = fail
        result = self.apply({"time_logging":True})
        self.assertFalse(result["success"]); self.assertEqual(result["effect_status"], "uncertain")
        self.assertFalse(result["restoration"]["state_restored"]); self.assertTrue(result["restoration"]["errors"])

    def test_ignored_setter_is_detected_by_readback(self):
        self.scope["set_time_logging_enabled"] = lambda value:value
        result = self.apply({"time_logging":True})
        self.assertFalse(result["success"]); self.assertIn("readback mismatch", result["reason"])
        self.assertEqual(result["effect_status"], "restored")

    def test_noop_skips_overlay_rebuild_and_history_trim(self):
        before = self.snapshot()
        self.scope["refresh_static_overlay"] = lambda:self.fail("unnecessary overlay rebuild")
        self.scope["trim_command_drip_history"] = lambda:self.fail("unnecessary trim")
        result = self.apply(before, apply_mode="CHANGED_ONLY")
        self.assertTrue(result["success"], result); self.assertEqual(result["attempted_fields"], [])

    def test_default_reapply_retains_refresh_and_pruning_and_explicit_mode_is_discoverable(self):
        calls = []
        self.scope["refresh_static_overlay"] = lambda:calls.append("overlay") or True
        self.scope["trim_command_drip_history"] = lambda:calls.append("trim")
        self.path.write_text(json.dumps(self.snapshot()), encoding="utf-8")
        same = self.command("APPLY_PERSONAL_DEFAULTS(changed_only)")["default_profile_results"][0]
        self.assertTrue(same["success"], same)
        self.assertEqual(same["apply_mode"], "changed_only")
        self.assertEqual(calls, [])
        reapply = self.command("APPLY_PERSONAL_DEFAULTS()")["default_profile_results"][0]
        self.assertTrue(reapply["success"], reapply)
        self.assertEqual(reapply["apply_mode"], "reapply")
        self.assertEqual(calls.count("overlay"), 2)
        self.assertEqual(calls.count("trim"), 1)
        self.assertEqual(set(profiles.describe_default_profile_contract("APPLY_PERSONAL_DEFAULTS")["parameters"][0]["enum"]),
                         {"reapply", "changed_only"})

    def test_read_and_save_ignore_locks_but_return_detached_state(self):
        self.fixture.locks.update({key:True for key in self.fixture.locks})
        batch = self.command("SHOW_DEFAULT_PROFILES(); SAVE_PERSONAL_DEFAULTS()")
        self.assertTrue(batch["success"], batch)
        read, saved = batch["default_profile_results"]
        self.assertEqual(read["defaults_status"]["personal_status"], "missing")
        self.assertEqual(saved["file_status"], "available")
        read["profile"]["advanced"]["image_detail"] = "tampered"
        self.assertNotEqual(self.snapshot()["advanced"]["image_detail"], "tampered")
        status = self.scope["get_default_profiles_status"](); status["system_profile"]["advanced"]["image_detail"] = "tampered"
        self.assertNotEqual(self.scope["SYSTEM_DEFAULT_PROFILE"]["advanced"]["image_detail"], "tampered")

    def test_corrupt_file_is_visible_and_apply_stops_tail(self):
        self.path.write_text("not json", encoding="utf-8"); before = self.snapshot()
        read = self.command("SHOW_DEFAULT_PROFILES()")["default_profile_results"][0]
        self.assertEqual(read["defaults_status"]["personal_status"], "invalid")
        batch = self.command("APPLY_PERSONAL_DEFAULTS(); SET_TIME_LOGGING(on)")
        self.assertFalse(batch["success"]); self.assertEqual(batch["default_profile_results"][0]["effect_status"], "not_started")
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError): self.scope["load_personal_defaults_profile"]()

    def test_snapshot_reader_waits_for_complete_apply(self):
        entered, release, observed = threading.Event(), threading.Event(), threading.Event()
        original = self.scope["set_time_logging_enabled"]; results, snapshots = [], []
        def blocked(value):
            result = original(value); entered.set()
            if not release.wait(3): raise RuntimeError("fixture timeout")
            return result
        self.scope["set_time_logging_enabled"] = blocked
        writer = threading.Thread(target=lambda:results.append(self.apply({"time_logging":True, "chat_log_echo":True})))
        reader = threading.Thread(target=lambda:(snapshots.append(self.snapshot()), observed.set()))
        try:
            writer.start(); self.assertTrue(entered.wait(2)); reader.start(); self.assertFalse(observed.wait(0.03))
        finally:
            release.set(); writer.join(3)
            if reader.ident is not None: reader.join(3)
        self.assertFalse(writer.is_alive()); self.assertFalse(reader.is_alive())
        self.assertTrue(results[0]["success"], results)
        self.assertTrue(snapshots[0]["time_logging"] and snapshots[0]["chat_log_echo"])


if __name__ == "__main__":
    unittest.main()
