import unittest

from aurora_settings_registry import build_settings_version
from aurora_settings_transactions import (
    SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION,
    build_setting_command_invocation,
    build_settings_transaction_command,
    build_settings_transaction_request,
    decode_settings_transaction_request,
    encode_settings_transaction_request,
    extract_settings_transaction_receipt,
    plan_settings_transaction,
)


def sample_state():
    return {
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
            "capture_wake_debounce_seconds": 0.8,
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
        "defaults": {"system_profile": {}},
    }


class AuroraSettingsTransactionTests(unittest.TestCase):
    def test_request_token_round_trip_and_wire_command(self):
        state = sample_state()
        request = build_settings_transaction_request(
            "preview",
            changes={"temperature": "0.5", "action": "none"},
            expected_version=build_settings_version(state),
            transaction_id="settings-tx-test",
        )

        token = encode_settings_transaction_request(request)
        decoded = decode_settings_transaction_request(token)

        self.assertEqual(decoded, request)
        self.assertEqual(decoded["schema_version"], SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION)
        self.assertTrue(build_settings_transaction_command(request).startswith("PREVIEW_SETTINGS_TRANSACTION("))

    def test_complete_batch_validation_reports_all_rejections(self):
        state = sample_state()
        request = build_settings_transaction_request(
            "apply",
            changes=[
                {"key": "runtime.live", "value": "on"},
                {"key": "live", "value": "off"},
                {"key": "runtime.lvie", "value": "off"},
                {"key": "inference.temperature", "value": "9"},
            ],
            expected_version=build_settings_version(state),
        )

        plan = plan_settings_transaction(request, state)
        codes = {row["code"] for row in plan["rejections"]}

        self.assertFalse(plan["valid"])
        self.assertTrue({"setting_locked", "duplicate_key", "unknown_key", "invalid_value"}.issubset(codes))

    def test_expected_version_conflict_rejects_before_apply(self):
        state = sample_state()
        request = build_settings_transaction_request(
            "apply",
            changes={"runtime.action": "none"},
            expected_version="sv1:stale",
        )

        plan = plan_settings_transaction(request, state)

        self.assertFalse(plan["valid"])
        self.assertIn("version_conflict", {row["code"] for row in plan["rejections"]})

    def test_valid_plan_coerces_values_and_marks_noops(self):
        state = sample_state()
        request = build_settings_transaction_request(
            "apply",
            changes={
                "inference.temperature": "0.5",
                "runtime.execution": "assist",
            },
            expected_version=build_settings_version(state),
        )

        plan = plan_settings_transaction(request, state)
        changes = {row["key"]: row for row in plan["changes"]}

        self.assertTrue(plan["valid"])
        self.assertEqual(changes["inference.temperature"]["value"], 0.5)
        self.assertTrue(changes["inference.temperature"]["changed"])
        self.assertFalse(changes["runtime.execution"]["changed"])

    def test_scheduler_profile_and_leaf_changes_conflict(self):
        state = sample_state()
        request = build_settings_transaction_request(
            "preview",
            changes={
                "scheduler.profile": "responsive",
                "scheduler.capture_wake_enabled": "off",
            },
            expected_version=build_settings_version(state),
        )

        plan = plan_settings_transaction(request, state)

        self.assertFalse(plan["valid"])
        self.assertIn("conflicting_changes", {row["code"] for row in plan["rejections"]})

    def test_command_invocation_uses_direct_boolean_argument(self):
        name, args, display = build_setting_command_invocation("runtime.live", False)

        self.assertEqual(name, "SET_LIVE_MODE")
        self.assertEqual(args, ["off"])
        self.assertEqual(display, "SET_LIVE_MODE(off)")

    def test_extracts_nested_transaction_receipt(self):
        receipt = extract_settings_transaction_receipt(
            {
                "settings_transaction_receipts": [
                    {"schema_version": "aurora_settings_transaction_receipt_v1", "status": "applied"}
                ]
            }
        )

        self.assertEqual(receipt["status"], "applied")


if __name__ == "__main__":
    unittest.main()
