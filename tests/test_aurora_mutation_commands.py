"""Transaction/lock/setting-shortcut behavior through real AST runtime handlers; no native I/O."""
import ast
import base64
import json
import threading
import unittest
import uuid

import test_aurora_command_ingress as ingress
import test_aurora_setting_commands as settings
from aurora_command_catalog import build_command_catalog, parse_dispatch
from aurora_command_contracts import LOCK_COMMANDS, SETTING_SHORTCUT_COMMANDS, TRANSACTION_COMMANDS, describe_command_contract
from aurora_runtime_work import WorkCancelled
from aurora_settings_registry import SETTINGS_REGISTRY_SCHEMA_VERSION, RUNTIME_LOCK_KEYS, RUNTIME_LOCK_ALIASES, normalize_runtime_lock_key
from aurora_settings_transactions import (
    MAX_TRANSACTION_TOKEN_BYTES, SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION, SETTINGS_ROLLBACK_HANDLE_SCHEMA_VERSION,
    build_settings_transaction_request, build_settings_transaction_command, parse_settings_transaction_command,
    plan_settings_transaction,
)


class MutationCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = settings.SettingCommandTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scope = s = self.fixture.scope
        self.harness = self.fixture.harness
        self.fixture.locks.update(dict.fromkeys(RUNTIME_LOCK_KEYS, False))
        bindings = parse_dispatch(ingress.TREE, "command_dispatch")
        commands = set(LOCK_COMMANDS) | set(SETTING_SHORTCUT_COMMANDS) | set(TRANSACTION_COMMANDS)
        names = {bindings[name] for name in commands} | {
            "normalize_runtime_lock_name", "get_runtime_lock_summary", "get_runtime_lock_snapshot", "set_runtime_setting_lock",
            "_settings_transaction_receipt_base", "_settings_transaction_command", "_remember_settings_transaction_receipt",
            "_execute_settings_preview_or_apply", "_execute_settings_rollback", "_capture_settings_transaction_auxiliary",
            "_restore_settings_transaction_rows", "_restore_scheduler_transaction_auxiliary", "_build_settings_transaction_change_receipts",
            "_store_settings_rollback_handle",
        }
        exec(compile(ast.Module(body=[ingress.FUNCTIONS[name] for name in sorted(names)], type_ignores=[]),
                     str(ingress.ROOT / "aurora2.py"), "exec"), s)
        s.update({"uuid": uuid, "RUNTIME_SETTING_LOCKS": self.fixture.locks, "normalize_runtime_lock_key": normalize_runtime_lock_key,
                  "SETTINGS_REGISTRY_SCHEMA_VERSION": SETTINGS_REGISTRY_SCHEMA_VERSION,
                  "SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION": SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION,
                  "SETTINGS_ROLLBACK_HANDLE_SCHEMA_VERSION": SETTINGS_ROLLBACK_HANDLE_SCHEMA_VERSION,
                  "SETTINGS_ROLLBACK_STORE": {}, "SETTINGS_ROLLBACK_STORE_LIMIT": 24,
                  "parse_settings_transaction_command": parse_settings_transaction_command,
                  "plan_settings_transaction": plan_settings_transaction})
        s["command_dispatch"].update({name: s[bindings[name]] for name in commands})

    def request(self, operation="apply", **kwargs):
        return build_settings_transaction_request(operation, expected_version=kwargs.pop("expected_version", self.fixture.version()),
                                                  **({"changes": {"temperature": 0.5}} if operation != "rollback" and "changes" not in kwargs else {}), **kwargs)

    def run_batch(self, text):
        return self.scope["handle_commands"](text)

    def transaction(self, request, tail=""):
        return self.run_batch(build_settings_transaction_command(request) + tail)

    def test_model_cannot_expand_task_limits_by_transaction_or_rollback(self):
        before = self.fixture.version()
        request = self.request(changes={"task.max_model_turns": 100, "inference.temperature": .5})
        success, receipt = self.scope["execute_settings_transaction_request"](request, is_user=False)
        self.assertFalse(success)
        self.assertEqual(receipt["status"], "rejected")
        self.assertEqual(self.fixture.version(), before)
        success, applied = self.scope["execute_settings_transaction_request"](request, is_user=True)
        self.assertTrue(success, applied)
        rollback = self.request(operation="rollback", rollback_handle=applied["rollback_handle"]["handle_id"])
        after = self.fixture.version()
        success, rejected = self.scope["execute_settings_transaction_request"](rollback, is_user=False)
        self.assertFalse(success)
        self.assertEqual(self.fixture.version(), after)
        success, restored = self.scope["execute_settings_transaction_request"](rollback, is_user=True)
        self.assertTrue(success, restored)
        self.assertEqual(self.fixture.version(), before)

    def test_invalid_transaction_tails_reject_before_an_earlier_mutation(self):
        good = self.request()
        variants = [{**good, field: value} for field, value in (
            ("schema_version", "unknown"), ("operation", "rollback"), ("scope", "saved_defaults"),
            ("expected_version", ""), ("expected_version", []), ("transaction_id", {}),
            ("changes", []), ("changes", {}), ("changes", [{"key": "temperature"}]),
            ("changes", [{"key": "unknown", "value": 1}]),
            ("changes", [{"key": "temperature", "value": "nan"}]),
            ("changes", [{"key": "temperature", "value": 0.2}, {"key": "inference.temperature", "value": 0.3}]),
            ("changes", [{"key": "scheduler.profile", "value": "responsive"}, {"key": "scheduler.mode", "value": "event"}]),
            ("rollback_handle", "unexpected"))]
        tokens = ["bad_token", "%%", "", "a" * (MAX_TRANSACTION_TOKEN_BYTES * 2 + 1)]
        tokens += [base64.urlsafe_b64encode(json.dumps(row).encode()).decode() for row in variants]
        # Duplicate fields and JavaScript-style numeric constants must not be silently accepted.
        raw = json.dumps(good)
        tokens += [base64.urlsafe_b64encode(text.encode()).decode() for text in (
            raw.replace('"operation": "apply"', '"operation": "preview", "operation": "apply"'),
            raw.replace('0.5', 'NaN'), raw.replace('0.5', 'Infinity'), raw.replace('0.5', '1e999'))]
        baseline = self.fixture.version()
        for token in tokens:
            with self.subTest(token=token[:40]):
                result = self.run_batch("SET_TIME_LOGGING(on); " + settings.command("APPLY_SETTINGS_TRANSACTION", token))
                self.assertFalse(result["success"], result)
                self.assertEqual(result["executed_commands"], [])
                self.assertEqual(self.harness.executed, [])
                self.assertEqual(self.fixture.version(), baseline)

    def test_transaction_command_arity_and_operation_are_admitted_for_all_three_names(self):
        for name in TRANSACTION_COMMANDS:
            for args in ((), ("token", "extra")):
                result = self.run_batch("SET_TIME_LOGGING(on); " + settings.command(name, *args))
                self.assertFalse(result["success"])
                self.assertEqual(self.harness.executed, [])
        for name in ("PREVIEW_SETTINGS_TRANSACTION", "ROLLBACK_SETTINGS_TRANSACTION"):
            token = build_settings_transaction_command(self.request()).split("(", 1)[1][:-1]
            self.assertFalse(self.run_batch(settings.command(name, token))["success"])

    def test_version_conflict_blocks_tail_but_does_not_undo_a_prior_raw_setting(self):
        request = self.request()
        result = self.run_batch("SET_TEMPERATURE(0.2); " + build_settings_transaction_command(request) + "; SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"], result)
        self.assertEqual(result["settings_transaction_receipts"][0]["status"], "rejected")
        self.assertIn("version_conflict", {r["code"] for r in result["settings_transaction_receipts"][0]["rejections"]})
        self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.2)
        self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])
        self.assertEqual(self.harness.executed, [])

    def test_preview_apply_and_rollback_preserve_existing_atomic_service(self):
        baseline = self.fixture.version()
        preview = self.transaction(self.request("preview"))["settings_transaction_receipts"][0]
        self.assertEqual(preview["status"], "previewed")
        self.assertEqual(self.fixture.version(), baseline)
        applied = self.transaction(self.request())["settings_transaction_receipts"][0]
        self.assertEqual(applied["status"], "applied")
        rollback = self.request("rollback", rollback_handle=applied["rollback_handle"]["handle_id"])
        result = self.transaction(rollback)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["settings_transaction_receipts"][0]["status"], "rolled_back")
        self.assertEqual(self.fixture.version(), baseline)
        again = self.transaction({**rollback, "expected_version": baseline}, "; SET_TIME_LOGGING(on)")
        self.assertFalse(again["success"])
        self.assertEqual(again["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_apply_failure_verifies_restoration_and_blocks_tail(self):
        original = self.scope["command_dispatch"]["SET_TEMPERATURE"]
        calls = []
        def partial(args, is_user):
            calls.append(args[0])
            original(args, is_user)
            if float(args[0]) == 0.5:
                raise RuntimeError("fixture partial setter")
            return True
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = partial
        baseline = self.fixture.version()
        result = self.transaction(self.request(), "; SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(result["settings_transaction_receipts"][0]["status"], "failed_rolled_back")
        self.assertEqual(self.fixture.version(), baseline)
        self.assertEqual(calls, ["0.5", "0.0"])
        self.assertEqual(self.harness.executed, [])

    def test_unexpected_error_after_apply_reports_uncertain_observed_versions(self):
        def fail_handle(*args):
            raise RuntimeError("fixture handle publication error")
        self.scope["_store_settings_rollback_handle"] = fail_handle
        baseline = self.fixture.version()
        result = self.transaction(self.request(), "; SET_TIME_LOGGING(on)")
        receipt = result["settings_transaction_receipts"][0]
        self.assertFalse(result["success"], result)
        self.assertEqual(receipt["status"], "failed_uncertain")
        self.assertEqual(receipt["before_version"], baseline)
        self.assertEqual(receipt["after_version"], self.fixture.version())
        self.assertEqual(self.scope["DEFAULT_MODEL_TEMPERATURE"], 0.5)
        self.assertEqual(self.harness.executed, [])

    def test_failed_readback_and_receipt_publication_remain_uncertain(self):
        def fail_after_apply(*args, **kwargs):
            self.scope["DEFAULT_MODEL_TEMPERATURE"] = 0.5
            self.scope["build_registered_settings_runtime_state"] = lambda: (_ for _ in ()).throw(RuntimeError("readback gone"))
            raise RuntimeError("fixture execution error")
        self.scope["_execute_settings_preview_or_apply"] = fail_after_apply
        self.scope["_remember_settings_transaction_receipt"] = lambda *args: (_ for _ in ()).throw(RuntimeError("receipt gone"))
        result = self.transaction(self.request())
        receipt = result["settings_transaction_receipts"][0]
        self.assertEqual(receipt["status"], "failed_uncertain")
        self.assertEqual(receipt["after_version"], "")
        self.assertEqual({r["code"] for r in receipt["rejections"]}, {"execution_uncertain", "readback_failed", "receipt_publication_failed"})

    def test_transaction_cancellation_keeps_receipt_and_cancels_tail(self):
        def cancel(*args, **kwargs):
            raise WorkCancelled("fixture transaction cancellation")
        self.scope["_execute_settings_preview_or_apply"] = cancel
        result = self.transaction(self.request(), "; SET_TIME_LOGGING(on)")
        self.assertTrue(result["cancelled"], result)
        self.assertEqual(result["settings_transaction_receipts"][0]["status"], "failed_uncertain")
        self.assertTrue(result["cancelled_commands"][-1].startswith("SET_TIME_LOGGING"))

    def test_cancellation_inside_apply_restores_settings_and_retains_cancelled_receipt(self):
        original = self.scope["command_dispatch"]["SET_TEMPERATURE"]
        def cancel_after_write(args, is_user):
            original(args, is_user)
            if float(args[0]) == 0.5:
                raise WorkCancelled("cancel after setting write")
            return True
        self.scope["command_dispatch"]["SET_TEMPERATURE"] = cancel_after_write
        baseline = self.fixture.version()
        result = self.transaction(self.request(), "; SET_TIME_LOGGING(on)")
        self.assertTrue(result["cancelled"], result)
        self.assertEqual(result["settings_transaction_receipts"][0]["status"], "failed_rolled_back")
        self.assertEqual(self.fixture.version(), baseline)
        self.assertEqual(self.harness.executed, [])

    def test_rollback_wire_shape_rejects_before_prior_commands(self):
        good = self.request("rollback", rollback_handle="fixture")
        for changes in ({"rollback_handle": ""}, {"changes": [{"key": "temperature", "value": 0.5}]}, {"changes": {}}):
            result = self.run_batch("SET_TIME_LOGGING(on); " + build_settings_transaction_command({**good, **changes}))
            self.assertFalse(result["success"])
            self.assertEqual(self.harness.executed, [])

    def test_transaction_locks_are_checked_at_execution_not_at_admission(self):
        request = self.request()
        prepared = self.scope["prepare_command_batch"](build_settings_transaction_command(request) + "; SET_TIME_LOGGING(on)")
        self.fixture.locks["temperature"] = True
        result = self.scope["handle_commands"]("prepared fixture", prepared_commands=prepared)
        self.assertFalse(result["success"])
        self.assertIn("setting_locked", {r["code"] for r in result["settings_transaction_receipts"][0]["rejections"]})
        self.assertEqual(self.harness.executed, [])

    def test_invalid_lock_and_shortcut_arguments_reject_before_prior_mutation(self):
        tails = [settings.command(name, "ignored") for name in SETTING_SHORTCUT_COMMANDS]
        tails += [settings.command(name, *args) for name in LOCK_COMMANDS for args in (("unknown",), ("",), ("live", "ignored"))]
        for tail in tails:
            with self.subTest(tail=tail):
                result = self.run_batch("SET_TIME_LOGGING(on); " + tail)
                self.assertFalse(result["success"])
                self.assertEqual(self.harness.executed, [])

    def test_all_lock_aliases_queries_and_explicit_unlock_keep_values_intact(self):
        for alias, key in RUNTIME_LOCK_ALIASES.items():
            with self.subTest(alias=alias):
                result = self.run_batch(settings.command("LOCK_SETTING", alias))
                outcome = result["lock_results"][0]
                self.assertTrue(result["success"], result)
                self.assertTrue(outcome["locks"][key])
                self.assertEqual(outcome["effect_status"], "observed")
                for name in LOCK_COMMANDS:
                    self.assertEqual(self.run_batch(settings.command(name))["lock_results"][0]["operation"], "read")
                self.assertTrue(self.run_batch(settings.command("UNLOCK_SETTING", alias))["success"])
        result = self.run_batch("LOCK_SETTING(temp); SET_TEMPERATURE(0.5); SET_TIME_LOGGING(on)")
        self.assertFalse(result["success"])
        self.assertEqual(result["setting_results"][0]["effect_status"], "not_started")
        result = self.run_batch("UNLOCK_SETTING(temp); SET_TEMPERATURE(0.5)")
        self.assertTrue(result["success"], result)
        self.assertFalse(result["lock_results"][0]["locks"]["temperature"])
        self.assertEqual(result["setting_results"][0]["value"], 0.5)

    def test_shortcuts_produce_typed_readback_and_obey_locks(self):
        for name, expected in (("GB_MODE", "gb"), ("PYAG_MODE", "pyag"), ("NO_ACTION_MODE", "none"),
                               ("TOGGLE_IMAGE_DETAIL", "high"), ("TOGGLE_IMAGE_DETAIL", "low"),
                               ("TOGGLE_LIVE_MODE", True), ("TOGGLE_LIVE_MODE", False)):
            result = self.run_batch(name + "()")
            self.assertTrue(result["success"], result)
            self.assertEqual(result["setting_results"][0]["value"], expected)
            self.assertEqual(result["setting_results"][0]["requested_value"], expected)
        self.scope["image_detail"] = "original"
        self.assertEqual(self.run_batch("TOGGLE_IMAGE_DETAIL()")["setting_results"][0]["value"], "low")
        for lock, name in (("action", "PYAG_MODE"), ("live", "TOGGLE_LIVE_MODE")):
            self.fixture.locks[lock] = True
            result = self.run_batch(name + "(); SET_TIME_LOGGING(on)")
            self.assertFalse(result["success"])
            self.assertEqual(result["setting_results"][0]["effect_status"], "not_started")
            self.assertEqual(result["blocked_commands"], ["SET_TIME_LOGGING(on)"])

    def test_lock_failure_mismatch_and_cancellation_keep_evidence(self):
        for failure in (False, True, "cancel"):
            def handler(*args):
                if failure == "cancel":
                    self.fixture.locks["temperature"] = True
                    raise WorkCancelled("fixture lock cancellation")
                return failure
            self.scope["command_dispatch"]["LOCK_SETTING"] = handler
            result = self.run_batch("LOCK_SETTING(temp); SET_TIME_LOGGING(on)")
            self.assertFalse(result["success"])
            self.assertEqual(result["lock_results"][0]["effect_status"], "uncertain")
            self.assertEqual(self.harness.executed, [])
            if failure == "cancel":
                self.assertTrue(result["cancelled"])
                self.assertTrue(result["lock_results"][0]["locks"]["temperature"])

    def test_locks_and_shortcuts_serialize_with_transaction_service(self):
        for text in ("LOCK_SETTING(temp)", "TOGGLE_IMAGE_DETAIL()"):
            entered, release, done = threading.Event(), threading.Event(), threading.Event()
            results = []
            def hold_transaction():
                with self.scope["SETTINGS_TRANSACTION_LOCK"]:
                    entered.set()
                    release.wait(2)
            holder = threading.Thread(target=hold_transaction)
            worker = threading.Thread(target=lambda: (results.append(self.run_batch(text)), done.set()))
            try:
                holder.start()
                self.assertTrue(entered.wait(1))
                worker.start()
                self.assertFalse(done.wait(0.05))
            finally:
                release.set()
                holder.join(3)
                worker.join(3)
            self.assertFalse(holder.is_alive() or worker.is_alive())
            self.assertTrue(results[0]["success"], results)

    def test_duplicate_transaction_and_lock_receipts_do_not_redispatch(self):
        self.harness.authorize()
        for identity, text, field in (("transaction", build_settings_transaction_command(self.request()), "settings_transaction_receipts"),
                                       ("locks", "LOCK_SETTING(temp)", "lock_results")):
            for _ in range(2):
                self.harness.send(text, identity)
                self.harness.poll()
            receipts = [row for row in self.harness.events if row.get("event") == "command_result"]
            self.assertTrue(receipts[-1]["duplicate_suppressed"])
            self.assertEqual(receipts[-1][field], receipts[-2][field])
            self.assertEqual(receipts[-1]["status"], "processed")

    def test_discovery_describes_reviewed_controls_without_false_aliases(self):
        catalog = build_command_catalog(ingress.ROOT)
        rows = {row["command"]: row for row in catalog["commands"]}
        for name in (*SETTING_SHORTCUT_COMMANDS, *LOCK_COMMANDS, *TRANSACTION_COMMANDS):
            contract = rows[name]["contract"]
            self.assertEqual(contract["parameter_validation"], "pre_dispatch")
            self.assertIn("receipt_field", contract["result"])
        for name in SETTING_SHORTCUT_COMMANDS:
            self.assertEqual(rows[name]["aliases"], [])
            self.assertEqual(describe_command_contract(name)["max_arguments"], 0)


if __name__ == "__main__":
    unittest.main()
