import unittest

from aurora2_control_panel import (
    CONTROL_PANEL_SCHEDULER_LEAF_KEYS,
    build_control_panel_registered_changes,
    filter_changed_control_panel_settings,
    format_control_panel_settings_receipt,
    format_control_panel_settings_snapshot,
)


class AuroraControlPanelSettingsClientTests(unittest.TestCase):
    def test_named_scheduler_profile_excludes_scheduler_leaves(self):
        values = {
            "auth.mode": "api_key",
            "scheduler.profile": "balanced",
            "scheduler.mode": "heartbeat",
            "scheduler.heartbeat_seconds": "9.0",
            "scheduler.min_gap_seconds": "3.0",
            "scheduler.capture_wake_enabled": False,
            "scheduler.capture_wake_debounce_seconds": "4.0",
            "scheduler.post_action_settle_seconds": "5.0",
        }

        changes = build_control_panel_registered_changes(values)
        keys = {row["key"] for row in changes}

        self.assertIn("auth.mode", keys)
        self.assertIn("scheduler.profile", keys)
        self.assertTrue(keys.isdisjoint(CONTROL_PANEL_SCHEDULER_LEAF_KEYS))

    def test_custom_scheduler_profile_includes_all_scheduler_leaves(self):
        values = {
            "scheduler.profile": "custom",
            "scheduler.mode": "hybrid",
            "scheduler.heartbeat_seconds": "2.25",
            "scheduler.min_gap_seconds": "0.55",
            "scheduler.capture_wake_enabled": True,
            "scheduler.capture_wake_debounce_seconds": "0.90",
            "scheduler.post_action_settle_seconds": "0.55",
        }

        changes = build_control_panel_registered_changes(values)
        keys = {row["key"] for row in changes}

        self.assertNotIn("scheduler.profile", keys)
        self.assertTrue(set(CONTROL_PANEL_SCHEDULER_LEAF_KEYS).issubset(keys))

    def test_changed_filter_uses_typed_setting_equality(self):
        snapshot = {
            "settings": [
                {"key": "runtime.live", "value": True},
                {"key": "inference.temperature", "value": 0.2},
                {"key": "model.text", "value": "gpt-5.4"},
            ]
        }
        changes = [
            {"key": "runtime.live", "value": "on"},
            {"key": "inference.temperature", "value": "0.20"},
            {"key": "model.text", "value": "gpt-5.5"},
        ]

        filtered = filter_changed_control_panel_settings(changes, snapshot)

        self.assertEqual(filtered, [{"key": "model.text", "value": "gpt-5.5"}])

    def test_snapshot_details_include_provenance_and_policy(self):
        text = format_control_panel_settings_snapshot(
            {
                "version": "sv-test",
                "runtime_active": True,
                "state_timestamp": "2026-08-08 12:00:00",
                "count": 1,
                "settings": [
                    {
                        "key": "runtime.live",
                        "value": True,
                        "value_status": "effective",
                        "source": {"kind": "runtime_state", "path": "modes.live"},
                        "locked": False,
                        "maturity": "stable",
                        "gui_tier": "basic",
                        "risk_class": "basic",
                        "apply_timing": "next_model_turn",
                    }
                ],
            }
        )

        self.assertIn("Settings version: sv-test", text)
        self.assertIn("runtime.live: on", text)
        self.assertIn("source=runtime_state (modes.live)", text)
        self.assertIn("maturity=stable", text)
        self.assertIn("apply=next_model_turn", text)

    def test_receipt_details_include_rollback_rejection_and_version(self):
        text = format_control_panel_settings_receipt(
            {
                "transaction_id": "stx-test",
                "operation": "apply",
                "status": "rejected",
                "scope": "runtime_session",
                "before_version": "sv-before",
                "after_version": "sv-before",
                "no_automatic_replay": True,
                "rejections": [
                    {"key": "runtime.execution", "code": "setting_locked", "message": "locked"}
                ],
                "rollback_handle": {
                    "handle_id": "srb-test",
                    "baseline_version": "sv-before",
                    "target_version": "sv-after",
                },
            }
        )

        self.assertIn("Version sv-before -> sv-before", text)
        self.assertIn("automatic replay off", text)
        self.assertIn("runtime.execution [setting_locked]: locked", text)
        self.assertIn("Rollback handle: srb-test", text)


if __name__ == "__main__":
    unittest.main()
