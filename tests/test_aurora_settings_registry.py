import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from aurora_cli import main as aurora_cli_main
from aurora_settings_registry import (
    InvalidSettingKeyError,
    InvalidSettingValueError,
    UnknownSettingKeyError,
    build_setting_readback,
    build_settings_snapshot,
    build_settings_version,
    coerce_setting_value,
    describe_setting_definition,
    list_setting_definitions,
    registry_summary,
    resolve_setting_definition,
)


def sample_state():
    return {
        "timestamp": "2026-08-08 12:00:00",
        "modes": {
            "auth": "api_key",
            "live": False,
            "execution": "assist",
            "action": "gb",
            "game_profile": "firered",
            "game_profile_source": "env",
            "screenshot_interval": 0.12,
            "load_live_init_prompt": False,
        },
        "models": {
            "text": "gpt-5.4",
            "vision": "gpt-5.4",
            "reasoning": "gpt-5.4",
            "reasoning_effort": "none",
            "verbosity": "medium",
            "temperature": 0.0,
        },
        "scheduler": {
            "profile": "balanced",
            "mode": "hybrid",
            "heartbeat_seconds": 2.25,
            "min_gap_seconds": 0.55,
            "capture_wake_enabled": True,
            "capture_wake_debounce_seconds": 0.9,
            "post_action_settle_seconds": 0.55,
            "demand_capture_enabled": True,
        },
        "advanced": {"image_detail": "low"},
        "locks": {
            "auth": False,
            "live": True,
            "execution": False,
            "action": False,
            "models": False,
            "reasoning": False,
            "temperature": False,
            "screenshot_interval": False,
            "live_init": False,
        },
        "defaults": {
            "system_profile": {
                "auth_mode": "api_key",
                "execution_mode": "assist",
                "action_mode": "gb",
                "game_profile": "firered",
                "text_model": "gpt-5.4",
                "vision_model": "gpt-5.4",
                "reasoning_model": "gpt-5.4",
                "reasoning_effort": "none",
                "verbosity": "medium",
                "temperature": 0.0,
                "turn_scheduler_profile": "balanced",
                "turn_scheduler_mode": "hybrid",
                "turn_heartbeat_seconds": 2.25,
                "turn_min_gap_seconds": 0.55,
                "turn_capture_wake_enabled": True,
                "turn_capture_wake_debounce_seconds": 0.9,
                "turn_post_action_settle_seconds": 0.55,
                "screenshot_interval": 0.12,
                "demand_capture_enabled": True,
                "load_live_init_prompt": False,
                "advanced": {"image_detail": "low"},
            }
        },
    }


class AuroraSettingsRegistryTests(unittest.TestCase):
    def test_registry_is_bounded_and_transactional(self):
        summary = registry_summary()
        definitions = list_setting_definitions()

        self.assertEqual(summary["schema_version"], "aurora_settings_registry_v1")
        self.assertEqual(summary["setting_count"], 23)
        self.assertEqual(len(definitions), 23)
        self.assertTrue(summary["write_enabled"])
        self.assertEqual(summary["mutation_status"], "atomic_runtime_transactions")
        self.assertEqual(len({definition.key for definition in definitions}), 23)

    def test_alias_resolution_and_strict_key_errors(self):
        self.assertEqual(resolve_setting_definition("live").key, "runtime.live")
        self.assertEqual(resolve_setting_definition("TEXT_MODEL").key, "model.text")
        with self.assertRaises(InvalidSettingKeyError):
            resolve_setting_definition("runtime live")
        with self.assertRaises(UnknownSettingKeyError) as context:
            resolve_setting_definition("runtime.lvie")
        self.assertIn("runtime.live", str(context.exception))

    def test_typed_value_validation(self):
        self.assertTrue(coerce_setting_value("runtime.live", "on"))
        self.assertFalse(coerce_setting_value("runtime.live", "false"))
        self.assertEqual(coerce_setting_value("inference.temperature", "1.25"), 1.25)
        self.assertEqual(coerce_setting_value("inference.reasoning_effort", "xhigh"), "xhigh")
        self.assertFalse(coerce_setting_value("capture_wake_enabled", "off"))
        self.assertEqual(coerce_setting_value("capture_wake_debounce", "0.35"), 0.35)
        self.assertEqual(coerce_setting_value("post_action_settle", "0.25"), 0.25)
        with self.assertRaises(InvalidSettingValueError):
            coerce_setting_value("inference.temperature", 2.1)
        with self.assertRaises(InvalidSettingValueError):
            coerce_setting_value("capture.screenshot_interval", 0.019)
        with self.assertRaises(InvalidSettingValueError):
            coerce_setting_value("inference.reasoning_effort", "ultra")

    def test_scheduler_custom_is_readback_only(self):
        with self.assertRaises(InvalidSettingValueError):
            coerce_setting_value("scheduler.profile", "custom")
        self.assertEqual(
            coerce_setting_value("scheduler.profile", "custom", for_readback=True),
            "custom",
        )

    def test_effective_readback_includes_lock_and_default_source(self):
        row = build_setting_readback(
            "runtime.live",
            sample_state(),
            runtime_active=True,
            state_age_seconds=0.5,
        )

        self.assertEqual(row["value"], False)
        self.assertEqual(row["value_status"], "effective")
        self.assertTrue(row["effective"])
        self.assertTrue(row["locked"])
        self.assertEqual(row["source"]["kind"], "runtime_state_export")
        self.assertEqual(row["compatibility_default_status"], "literal")
        self.assertTrue(row["write_enabled"])

    def test_stopped_runtime_is_last_observed_not_effective(self):
        row = build_setting_readback(
            "game.profile",
            sample_state(),
            runtime_active=False,
            state_age_seconds=100.0,
        )

        self.assertEqual(row["value"], "firered")
        self.assertEqual(row["value_status"], "last_observed")
        self.assertFalse(row["effective"])
        self.assertEqual(row["source"]["origin"], "env")
        self.assertEqual(row["compatibility_default_source"], "defaults.system_profile.game_profile")

    def test_active_runtime_with_old_state_is_stale(self):
        row = build_setting_readback(
            "runtime.execution",
            sample_state(),
            runtime_active=True,
            state_age_seconds=30.0,
        )
        self.assertEqual(row["value_status"], "stale")
        self.assertFalse(row["effective"])

    def test_missing_dynamic_default_and_lock_are_unavailable(self):
        definition = describe_setting_definition("model.text", state={})
        row = build_setting_readback(
            "runtime.live",
            {},
            runtime_active=False,
        )

        self.assertIsNone(definition["compatibility_default"])
        self.assertEqual(definition["compatibility_default_status"], "unavailable")
        self.assertEqual(row["value_status"], "unavailable")
        self.assertEqual(row["lock_status"], "unavailable")

    def test_snapshot_filters_by_category(self):
        snapshot = build_settings_snapshot(
            sample_state(),
            runtime_active=True,
            state_age_seconds=0.1,
            category="capture",
        )
        self.assertEqual(snapshot["count"], 2)
        self.assertEqual(
            {row["key"] for row in snapshot["settings"]},
            {"capture.screenshot_interval", "capture.demand_enabled"},
        )
        self.assertTrue(snapshot["version"].startswith("sv1:"))

    def test_settings_version_tracks_values_locks_and_scheduler_bundle_fields(self):
        baseline = sample_state()
        baseline_version = build_settings_version(baseline)

        value_change = copy.deepcopy(baseline)
        value_change["models"]["temperature"] = 0.5
        lock_change = copy.deepcopy(baseline)
        lock_change["locks"]["models"] = True
        scheduler_aux_change = copy.deepcopy(baseline)
        scheduler_aux_change["scheduler"]["capture_wake_debounce_seconds"] = 0.35
        unrelated_change = copy.deepcopy(baseline)
        unrelated_change["unrelated"] = {"counter": 99}

        self.assertNotEqual(build_settings_version(value_change), baseline_version)
        self.assertNotEqual(build_settings_version(lock_change), baseline_version)
        self.assertNotEqual(build_settings_version(scheduler_aux_change), baseline_version)
        self.assertEqual(build_settings_version(unrelated_change), baseline_version)

    def test_cli_settings_get_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aurora_control_panel_state.json").write_text(
                json.dumps(sample_state()),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = aurora_cli_main(
                    ["--root", str(root), "settings", "get", "live", "--json"]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["key"], "runtime.live")
            self.assertEqual(payload["value_status"], "last_observed")

    def test_cli_unknown_setting_returns_two(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir, contextlib.redirect_stderr(stderr):
            exit_code = aurora_cli_main(
                ["--root", temp_dir, "settings", "get", "runtime.lvie"]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("runtime.live", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
