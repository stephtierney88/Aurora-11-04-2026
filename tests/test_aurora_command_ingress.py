"""Exercise real runtime ingress/dispatch with harmless handlers and temporary journals."""
import ast
import datetime
import json
import os
import queue
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from aurora_runtime_work import CancellationDomain, WorkCancelled
from aurora_input_ownership import HeldInputLedger, InputOwnershipError, cooperative_move
from aurora_pending_commands import PENDING_WRAPPER_MODES

from aurora_command_protocol import CommandSyntaxError, split_command_batch
from aurora_command_contracts import (
    DesktopCommandError, command_result_failed, desktop_result, parse_desktop_arguments,
    setting_command_definition, LOCK_COMMANDS, command_failure_stops_batch, parse_lock_command_arguments,
    DesktopActionContext, current_desktop_action_context, desktop_action_scope, projected_action_mode,
    validate_command_arguments, validate_desktop_keys, wait_duration,
)
from aurora_control_plane import (
    COMMAND_RECEIPT_SCHEMA_VERSION, MUTATION_ADMISSION_SCHEMA_VERSION,
    MutationAdmissionJournal, append_bridge_request, append_jsonl_record,
    build_mutation_decision_receipt, control_plane_paths, extract_request_identity,
    read_jsonl_batch, read_jsonl_from, validate_bridge_request,
)
from aurora_settings_registry import coerce_setting_value
from aurora_history_controls import current_history_actor, history_actor_scope


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
FUNCTIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}
RUNTIME_FUNCTIONS = """
normalize_text_content normalize_memory_item normalize_action_mode strip_wrapping_quotes
extract_command_arguments parse_command_signature_raw get_command_name_key
is_privileged_operator_command can_dispatch_external_single_command
can_dispatch_external_raw_command is_external_mutation_command prepare_command_batch
normalize_action_command parse_command_signature expand_structured_memory_command
format_command_text handle_commands enqueue_or_execute_command poll_external_inbox_messages
is_urgent_control_command execute_command_entry
desktop_command_arguments
input_key_callbacks acquire_key_input release_input_leases release_owned_key acquire_mouse_input cancel_command_inputs
resolve_desktop_action_context translate_game_backend_key
execute_runtime_lock_command
save_external_bridge_state write_mutation_decision_command_receipt record_mutation_terminal_result
canonicalize_gameboy_command canonicalize_pyag_command format_action_command format_action_argument
is_unprefixed_gameboy_command is_unprefixed_pyag_command is_gameboy_control_token
normalize_gameboy_control_token
split_commands_preserving_parentheses is_known_command extract_command_candidate clean_response_line
""".split()


def runtime_constants():
    wanted = {"READONLY_OPERATOR_COMMANDS", "PYAG_ACTION_NAMES", "GAMEBOY_ACTION_ALIASES",
              "GAMEBOY_CONTROL_TOKENS", "GAME_INPUT_SCANCODES"}
    # Hardware key bindings come from environment variables in production.
    scope = {"GAME_CONTROL_KEY_TRANSLATIONS": {"a": "x", "b": "z", "start": "enter", "select": "backspace"},
             "GAME_DIRECTION_KEY_TRANSLATIONS": {key: key for key in ("up", "down", "left", "right")}}
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    scope[target.id] = ast.literal_eval(node.value)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "update"
                    and isinstance(call.func.value, ast.Name) and call.func.value.id in wanted):
                scope[call.func.value.id].update(ast.literal_eval(call.args[0]))
    return scope


class RuntimeIngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-ingress-test-")
        self.addCleanup(self.temp.cleanup)
        self.paths = control_plane_paths(self.temp.name)
        self.paths["inbox"].touch()
        self.events, self.executed = [], []
        self.inputs = queue.Queue()
        self.journal = MutationAdmissionJournal(self.temp.name, session_id="test")
        self.scope = {
            "current_history_actor": current_history_actor, "history_actor_scope": history_actor_scope,
            **runtime_constants(), "json": json, "re": re, "time": time, "os": os,
            "datetime": datetime, "CommandSyntaxError": CommandSyntaxError,
            "command_result_failed": command_result_failed,
            "setting_command_definition": setting_command_definition,
            "LOCK_COMMANDS": LOCK_COMMANDS, "command_failure_stops_batch": command_failure_stops_batch,
            "parse_lock_command_arguments": parse_lock_command_arguments,
            "DesktopActionContext": DesktopActionContext, "current_desktop_action_context": current_desktop_action_context,
            "desktop_action_scope": desktop_action_scope, "projected_action_mode": projected_action_mode,
            "coerce_setting_value": coerce_setting_value,
            "DesktopCommandError": DesktopCommandError, "desktop_result": desktop_result,
            "parse_desktop_arguments": parse_desktop_arguments, "validate_desktop_keys": validate_desktop_keys,
            "validate_command_arguments": validate_command_arguments,
            "PENDING_WRAPPER_MODES": PENDING_WRAPPER_MODES,
            "wait_duration": wait_duration,
            "COMMAND_WORK": CancellationDomain(), "MODEL_WORK": CancellationDomain(),
            "HELD_INPUTS": HeldInputLedger(), "InputOwnershipError": InputOwnershipError,
            "cooperative_move": cooperative_move,
            "GAME_INPUT_EXTENDED_SCANCODE_KEYS": {"up", "down", "left", "right"},
            "WorkCancelled": WorkCancelled,
            "is_agent_running": lambda: True,
            "split_command_batch": split_command_batch, "read_jsonl_batch": read_jsonl_batch,
            "validate_bridge_request": validate_bridge_request,
            "extract_request_identity": extract_request_identity,
            "build_mutation_decision_receipt": build_mutation_decision_receipt,
            "COMMAND_RECEIPT_SCHEMA_VERSION": COMMAND_RECEIPT_SCHEMA_VERSION,
            "MUTATION_ADMISSION_SCHEMA_VERSION": MUTATION_ADMISSION_SCHEMA_VERSION,
            "has_operator_passcode": lambda: True, "is_operator_authorized": lambda: False,
            "is_operator_passcode_required": lambda: True,
            "ACTIVE_ACTION_MODE": "none", "GAME_INPUT_BACKEND": "scancode",
            "set_last_command_value": lambda value: None,
            "get_last_command_value": lambda: "", "get_last_key_value": lambda: "",
            "runtime_state": {}, "agent_state": SimpleNamespace(inference_counter=0),
            "display_message": lambda *args: None, "append_runtime_feedback": lambda *args: None,
            "touch_last_interaction": lambda: None, "ensure_external_bridge_files": lambda: None,
            "summarize_runtime_text": lambda text, **kw: str(text)[:kw.get("max_chars", 1000)],
            "sanitize_sensitive_command_text": lambda text: text,
            "external_bridge_state": {"inbox_offset": 0},
            "external_inbox_path": str(self.paths["inbox"]),
            "external_bridge_state_path": str(Path(self.temp.name) / "bridge-state.json"),
            "active_command_queue": None, "get_input_queue_store": lambda: self.inputs,
            "get_mutation_admission_journal": lambda: self.journal,
            "write_external_bridge_log": self.bridge_event,
            "write_command_execution_log": self.command_event,
            "ingest_command_result": self.ingest_result,
            "execute_desktop_command": lambda name, args: self.executed.append((name, args)) or desktop_result(name),
            "pyautogui": SimpleNamespace(KEYBOARD_KEYS=[chr(code) for code in range(32, 127)] + ["enter", "ctrl", "shift", "space", "up", "down", "left", "right", "\n", "\r", "\t"]),
            "is_valid_keyboard_key_token": lambda key: key in {"a", "b", "x", "z", "start", "select", "enter", "up", "down", "left", "right", "ctrl", "shift", "space"},
            "should_use_game_input_backend": lambda key: False,
            "pyautogui_dispatch": {"press": object(), "type": object()},
            "command_dispatch": {
                name: (lambda args, user, n=name: self.executed.append((n, args)))
                for name in ("SHOW_RUNTIME", "SHOW_AUTH", "SET_TIME_LOGGING", "UPDATE_NOTES",
                             "UPDATE_CONTEXT", "UPDATE_PINNED_IMMEDIATE", "AUTHORIZE_OPERATOR")
            },
        }
        exec(compile(ast.Module(body=[FUNCTIONS[n] for n in RUNTIME_FUNCTIONS], type_ignores=[]),
                     str(ROOT / "aurora2.py"), "exec"), self.scope)

    def bridge_event(self, event, **fields):
        row = {"event": event, **fields}
        self.events.append(row)
        append_jsonl_record(self.paths["bridge_log"], row)
        return row

    def test_invalid_wait_rejects_entire_batch_before_a_mutation(self):
        self.scope["command_dispatch"]["WAIT"] = lambda args, user: self.executed.append(("WAIT", args))
        for text in ("WAIT()", "WAIT(nan)", "WAIT(inf)", "WAIT(-1)", "WAIT(nope)", "WAIT(1,2)", "WAIT(,1)", "WAIT(1,,2)"):
            with self.subTest(text=text):
                result = self.scope["handle_commands"]("SET_TIME_LOGGING(on); " + text)
                self.assertFalse(result["success"])
                self.assertEqual(result["executed_commands"], [])
                self.assertEqual(self.executed, [])
        result = self.scope["handle_commands"]("SET_TIME_LOGGING(on); WAIT(0)")
        self.assertTrue(result["success"])
        self.assertEqual(len(self.executed), 2)

    def test_quoted_empty_arguments_and_trailing_comma_stay_supported(self):
        self.assertEqual(self.scope["extract_command_arguments"]('UPDATE_NOTES("", "a,b",)'), ["", "a,b"])

    def test_nontransaction_structured_failure_is_not_success(self):
        self.scope["command_dispatch"]["SHOW_RUNTIME"] = lambda args, user: {"success": False, "error": "fixture failure"}
        result = self.scope["handle_commands"]("SHOW_RUNTIME()")
        self.assertFalse(result["success"])
        self.assertEqual(result["executed_commands"], [])
        self.assertEqual(result["command_timings"][0]["status"], "failed")

    def test_desktop_handler_explicit_failures_are_preserved(self):
        scope = dict(self.scope)
        exec(compile(ast.Module(body=[FUNCTIONS["execute_desktop_command"], FUNCTIONS["handle_pyautogui_command"]], type_ignores=[]),
                     str(ROOT / "aurora2.py"), "exec"), scope)
        for returned in (False, {"success": False}, None, True):
            scope["pyautogui_dispatch"] = {"press": lambda args, value=returned: value}
            self.assertEqual(scope["handle_pyautogui_command"]("press", ["a"]),
                             returned is None or returned is True)

    def command_event(self, event, **fields):
        row = {"event": event, **fields}
        self.events.append(row)
        append_jsonl_record(self.paths["command_log"], row)
        return row

    def ingest_result(self, result):
        receipt = self.command_event("command_result", **result)
        self.journal.record_terminal(receipt)

    def send(self, text, request_id="request", raw=True):
        return append_bridge_request(self.temp.name, text, raw=raw, client_id="test", request_id=request_id)

    def poll(self):
        return self.scope["poll_external_inbox_messages"]()

    def authorize(self):
        self.scope["is_operator_authorized"] = lambda: True

    def test_locked_read_then_mutation_executes_nothing_and_is_journaled(self):
        self.send("SHOW_RUNTIME(); SET_TIME_LOGGING(on)")
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.executed, [])
        admissions, _ = read_jsonl_from(self.paths["mutation_log"])
        self.assertEqual(admissions[0]["event"], "mutation_rejected")
        receipt = next(row for row in self.events if row["event"] == "command_result")
        self.assertEqual(receipt["status"], "rejected")

    def test_all_readonly_batch_remains_available_while_locked(self):
        self.send("SHOW_RUNTIME(); SHOW_AUTH()")
        self.poll()
        self.assertEqual([item[0] for item in self.executed], ["SHOW_RUNTIME", "SHOW_AUTH"])
        self.assertFalse(self.paths["mutation_log"].exists())

    def test_invalid_tail_rejects_whole_batch_before_any_handler(self):
        self.authorize()
        for i, suffix in enumerate(("UNKNOWN()", "SET_TIME_LOGGING(on", "SHOW_AUTH() junk", "SHOW_AUTH(])")):
            with self.subTest(suffix=suffix):
                self.send("SHOW_RUNTIME(); " + suffix, request_id=f"bad-{i}")
                self.poll()
                self.assertEqual(self.executed, [])
                self.assertTrue(self.inputs.empty())

    def test_authorization_in_same_batch_cannot_unlock_later_mutation(self):
        self.send("AUTHORIZE_OPERATOR(example); SET_TIME_LOGGING(on)")
        self.poll()
        self.assertEqual(self.executed, [])

    def test_quoted_delimiters_hashes_whitespace_and_nested_arguments_survive(self):
        self.authorize()
        text = 'UPDATE_NOTES("keep  two spaces; ) # and \\"quote\\""); SHOW_RUNTIME() # comment\nSHOW_AUTH()'
        self.send(text)
        self.poll()
        self.assertEqual([name for name, _ in self.executed], ["UPDATE_NOTES", "SHOW_RUNTIME", "SHOW_AUTH"])
        self.assertIn('two spaces; ) #', self.executed[0][1][0])
        self.assertIn('keep  two', self.executed[0][1][0])
        self.assertEqual(split_command_batch('UPDATE_NOTES({"a": [1, ";"]})'),
                         ('UPDATE_NOTES({"a": [1, ";"]})',))

    def test_structured_expansion_is_checked_before_execution(self):
        self.send('SHOW_RUNTIME(); UPDATE_CONTEXT(immediate="plan")')
        self.poll()
        self.assertEqual(self.executed, [])
        self.authorize()
        self.send('UPDATE_CONTEXT(immediate="plan")', request_id="allowed")
        self.poll()
        self.assertEqual(self.executed, [("UPDATE_PINNED_IMMEDIATE", ["plan"])])

    def test_model_candidate_keeps_quoted_hash_and_bad_proposals_do_not_raise(self):
        candidate = 'UPDATE_NOTES("a # literal marker")'
        self.assertEqual(self.scope["extract_command_candidate"](candidate), candidate)
        self.assertFalse(self.scope["is_known_command"]("SHOW_RUNTIME_SOMETHING_ELSE()"))
        self.assertEqual(self.scope["split_commands_preserving_parentheses"]("SHOW_RUNTIME(); BAD("), [])

    def test_desktop_text_does_not_get_reescaped_by_action_normalization(self):
        command = r'pyag:type("two  spaces and \"quotes\"")'
        self.assertEqual(self.scope["normalize_action_command"](command), command)

    def test_queue_keeps_the_admitted_alias_when_action_mode_changes(self):
        self.authorize()
        self.scope["ACTIVE_ACTION_MODE"] = "gb"
        self.scope["active_command_queue"] = queue.Queue()
        self.send("press(a)")
        self.poll()
        entry = self.scope["active_command_queue"].get_nowait()
        self.scope["ACTIVE_ACTION_MODE"] = "none"
        self.assertTrue(entry["prepared_commands"][0][3])
        result = self.scope["handle_commands"](entry["command"], prepared_commands=entry["prepared_commands"])
        self.assertTrue(result["success"])
        self.assertEqual(self.executed, [("press", ["a"])])

    def test_duplicate_mutating_batch_is_not_replayed_after_restart_or_rotation(self):
        self.authorize()
        self.send("SHOW_RUNTIME(); SET_TIME_LOGGING(on)")
        self.poll()
        self.journal = MutationAdmissionJournal(self.temp.name, session_id="restarted")
        self.scope["external_bridge_state"] = json.loads(Path(self.scope["external_bridge_state_path"]).read_text())
        rotated = self.paths["inbox"].with_suffix(".old")
        self.paths["inbox"].replace(rotated)
        self.send("SHOW_RUNTIME(); SET_TIME_LOGGING(on)")
        self.poll()
        self.assertEqual(len(self.executed), 2)
        self.assertTrue(any(row["event"] == "mutation_duplicate_suppressed" for row in self.events))
        self.assertTrue(any(row["event"] == "inbox_cursor_reset" for row in self.events))

    def test_identical_envelope_retry_gets_a_receipt_instead_of_being_silently_skipped(self):
        self.authorize()
        record = self.send("SET_TIME_LOGGING(off)")
        self.poll()
        append_jsonl_record(self.paths["inbox"], record)
        self.poll()
        self.assertEqual(len(self.executed), 1)
        self.assertTrue(any(row["event"] == "mutation_duplicate_suppressed" for row in self.events))

    def test_temporary_cursor_save_failure_retries_without_reexecuting(self):
        self.authorize()
        original_save = self.scope["save_external_bridge_state"]
        def unavailable():
            raise PermissionError("temporary sharing violation")
        self.scope["save_external_bridge_state"] = unavailable
        self.send("SET_TIME_LOGGING(off)")
        self.poll()
        self.assertTrue(self.scope["external_bridge_state"]["inbox_cursor_save_pending"])
        self.scope["save_external_bridge_state"] = original_save
        self.poll()
        self.assertEqual(len(self.executed), 1)
        self.assertNotIn("inbox_cursor_save_pending", self.scope["external_bridge_state"])
        self.assertTrue(Path(self.scope["external_bridge_state_path"]).exists())

    def test_partial_record_and_partial_utf8_are_retried(self):
        encoded = (json.dumps({"text": "a \u2603 message", "message_id": "split"}, ensure_ascii=False) + "\n").encode()
        split = encoded.index("\u2603".encode()) + 1
        self.paths["inbox"].write_bytes(encoded[:split])
        self.assertEqual(self.poll(), 0)
        self.assertEqual(self.scope["external_bridge_state"]["inbox_offset"], 0)
        with self.paths["inbox"].open("ab") as handle:
            handle.write(encoded[split:])
        self.assertEqual(self.poll(), 1)
        self.assertIn("\u2603", self.inputs.get_nowait())

    def test_bad_envelopes_advance_durable_cursor_and_do_not_poison_following_record(self):
        bad = [[], None, {"text": "x", "metadata": "invalid"}, {"text": ["x"]},
               {"text": "x", "metadata": {"ingest_mode": "typo"}}]
        self.paths["inbox"].write_text("".join(json.dumps(row) + "\n" for row in bad), encoding="utf-8")
        self.assertEqual(self.poll(), 0)
        saved = json.loads(Path(self.scope["external_bridge_state_path"]).read_text())
        self.assertEqual(saved["inbox_offset"], self.paths["inbox"].stat().st_size)
        self.send("good", raw=False)
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.inputs.qsize(), 1)
        self.assertEqual(sum(row["event"] == "message_rejected" for row in self.events), len(bad))


class JSONLFramingTests(unittest.TestCase):
    def test_historical_receipt_reader_does_not_drop_large_valid_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "journal"
            row = {"text": "x" * (1024 * 1024 + 50)}
            append_jsonl_record(path, row)
            rows, cursor = read_jsonl_from(path)
            self.assertEqual(rows, [row])
            self.assertEqual(cursor, path.stat().st_size)

    def test_valid_json_waits_for_newline_including_split_crlf(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inbox"
            for tail in (b'{"text":"done"}', b'{"text":"done"}\r'):
                path.write_bytes(tail)
                self.assertEqual(read_jsonl_from(path), ([], 0))
                with path.open("ab") as handle:
                    handle.write(b"\n")
                self.assertEqual(read_jsonl_from(path)[0], [{"text": "done"}])

    def test_bounded_poll_resumes_and_skips_oversized_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inbox"
            path.write_bytes(b"x" * 1000 + b'\n{"text":"next"}\n')
            cursor, discarding, seen = 0, False, []
            for _ in range(30):
                batch = read_jsonl_batch(path, cursor, discarding_record=discarding,
                                        max_records=2, max_bytes=100, max_record_bytes=60)
                self.assertLessEqual(batch["bytes_read"], 100)
                seen.extend(batch["entries"])
                cursor, discarding = batch["next_offset"], batch["discarding_record"]
                if cursor == path.stat().st_size:
                    break
            self.assertEqual(sum(bool(entry["error"]) for entry in seen), 1)
            self.assertEqual([entry["record"] for entry in seen if entry["record"]], [{"text": "next"}])
            self.assertFalse(discarding)

    def test_record_limit_and_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inbox"
            path.write_bytes(b'{"n":1}\n' * 10)
            batch = read_jsonl_batch(path, max_records=2)
            self.assertEqual(len(batch["entries"]), 2)
            path.write_bytes(b'{"n":2}\n')
            reset = read_jsonl_batch(path, batch["next_offset"], file_identity=batch["file_identity"])
            self.assertTrue(reset["reset"])
            self.assertEqual(reset["entries"][0]["record"], {"n": 2})


if __name__ == "__main__":
    unittest.main()
