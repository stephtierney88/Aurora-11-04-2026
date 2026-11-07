"""Opt-in bounded smoke of the real launcher/runtime in a disposable workspace.

No model calls, keyboard commands, audio input, live init, or built-in action
smoke. Runtime capture workers operate normally inside this isolated copy.
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aurora_control_plane import append_bridge_request, build_bridge_request, read_jsonl_from
from aurora_settings_transactions import build_settings_transaction_command, build_settings_transaction_request


MODEL_FIXTURE = '''from pathlib import Path
import time
from types import SimpleNamespace
import aurora2 as runtime

def forbidden_network(*args, **kwargs):
    raise AssertionError("Network disabled in cancellation fixture")
runtime.requests.post = forbidden_network

def transport(packet, token):
    Path("model-entered").write_text("started")
    deadline = time.monotonic() + 60
    while not Path("model-release").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    return SimpleNamespace(status_code=200, json=lambda: {
        "choices": [{"message": {"content": "SET_TIME_LOGGING(on)"}}]
    }), "api_key", "test-only fake transport"

runtime.perform_model_http_request = transport
runtime.process_assistant_response = lambda response: Path("late-response-applied").write_text(response)
started = False
def model_turn():
    global started
    if started or not Path("model-trigger").exists():
        return False
    started = True
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    try:
        runtime.send_prompt_to_chatgpt("Local cancellation fixture", wake_reason="test_fixture")
    finally:
        runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
        Path("model-caller-returned").write_text("returned")
    return True
runtime.maybe_run_due_inference_turn = model_turn
runtime.apply_cli_args(runtime.build_cli_parser().parse_args())
runtime.main()
'''


CONTRACT_IMPORT_GUARD = '''
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from PIL import Image, ImageGrab

import_capture_calls = []
def synthetic_import_capture(*args, **kwargs):
    import_capture_calls.append(True)
    return Image.new("RGB", (1280, 720), "black")
ImageGrab.grab = synthetic_import_capture

# Guard import-time network activity too (cold token vocabulary / IPv6 probe).
socket.has_ipv6 = False
def offline_audit(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
        Path("forbidden-native-input.txt").write_text(event)
        raise AssertionError("Network disabled in contract fixture: " + event)
sys.addaudithook(offline_audit)
fixture_tokenizer = SimpleNamespace(encode=lambda text, **kw: list(str(text).encode("utf-8")),
                                   decode=lambda values: bytes(values).decode("utf-8", errors="replace"))
sys.modules["tiktoken"] = SimpleNamespace(get_encoding=lambda *a, **kw: fixture_tokenizer,
                                        encoding_for_model=lambda *a, **kw: fixture_tokenizer)
'''


CONTRACT_FIXTURE = '''import time
from pathlib import Path
import aurora2 as runtime
runtime.CAPTURE_GEOMETRY_POLICY = "legacy"  # Native queries disabled in generic synthetic fixtures.
runtime.get_foreground_window_title = lambda: "Aurora offline fixture"

def idle_worker(*args):
    while runtime.is_agent_running():
        time.sleep(0.01)

runtime.screenshot_capture = idle_worker
runtime.drawing_worker = idle_worker
runtime.initialize_overlay = lambda: None

def forbidden_input(name):
    def guard(*args, **kwargs):
        with Path("forbidden-native-input.txt").open("a") as handle:
            handle.write(name + "\\n")
        raise AssertionError("Native input is disabled in the contract fixture: " + name)
    return guard

for name in ("press", "keyDown", "keyUp", "hotkey", "write", "typewrite", "moveTo", "dragTo", "click",
             "doubleClick", "mouseDown", "mouseUp", "scroll", "screenshot"):
    setattr(runtime.pyautogui, name, forbidden_input(name))
runtime.keyboard.press = forbidden_input("keyboard.press")
runtime.keyboard.release = forbidden_input("keyboard.release")
runtime.send_scancode_key_event = forbidden_input("send_scancode_key_event")
runtime.requests.post = forbidden_input("requests.post")
runtime.perform_model_http_request = forbidden_input("perform_model_http_request")
runtime.focus_window_by_title = lambda title: {"success": False, "reason": "fixture target is absent"}
runtime.focus_game_input_target = lambda title: {"success": False, "reason": "fixture game target is absent"}
runtime.apply_cli_args(runtime.build_cli_parser().parse_args())
runtime.main()
'''


def run_smoke(simulate_model=False, contracts_only=False) -> dict:
    if simulate_model and contracts_only:
        raise ValueError("Choose the model/capture proof or the no-capture contract proof.")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".aurora-ingress-smoke-") as folder:
        work = Path(folder).resolve()
        assert ROOT.resolve() in work.parents
        for name in ("aurora_subscription_worker.py", "aurora_task_continuation.py", "aurora_task_objective.py", "aurora_delivery_receipts.py", "aurora_gameplay_scene.py", "aurora_goal_store.py", "aurora_conversation_navigator.py", "aurora2.py", "aurora2_control_panel.py", "aurora_preflight.py",
                     "aurora_runtime_work.py", "aurora_input_ownership.py", "aurora_responses_reasoning.py", "aurora_capture_store.py", "aurora_capture_artifacts.py", "aurora_execution_evidence.py", "aurora_execution_projection.py", "aurora_execution_history.py", "aurora_execution_history_job.py", "aurora_execution_recording.py", "aurora_recording_store.py", "aurora_recording_gate.py", "aurora_recording_retention.py", "aurora_recording_service.py", "aurora_recording_browser.py", "aurora_capture_provenance.py", "aurora_observation_wait.py", "aurora_capture_geometry.py", "aurora_panel_layout.py",
                     "aurora_command_protocol.py", "aurora_command_contracts.py", "aurora_default_profiles.py", "aurora_pending_commands.py", "aurora_history_controls.py", "aurora_episodic_retrieval.py", "aurora_search_query.py", "aurora_retrieval_results.py", "aurora_retrieval_commands.py", "aurora_conversation.py", "aurora_control_plane.py", "aurora_codex_oauth.py",
                     "aurora_settings_registry.py", "aurora_settings_transactions.py", "launch_aurora2.cmd"):
            shutil.copy2(ROOT / name, work / name)
        env = dict(os.environ, AURORA_PYTHON=sys.executable, AURORA_ENABLE_TEXT_INPUT_PROCESS="0",
                   AURORA_AUTH_MODE="api_key", PYTHONUNBUFFERED="1")
        flags = ["--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
                 "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none",
                 "--screenshot-interval", "0.35"]
        output = work / "process.log"
        if simulate_model or contracts_only:
            (work / "smoke_runtime.py").write_text(CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE if contracts_only else MODEL_FIXTURE, encoding="utf-8")
            launch = [sys.executable, str(work / "smoke_runtime.py"), *flags]
        else:
            launch = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(work / "launch_aurora2.cmd"), *flags]
        with output.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(launch,
                                       cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            receipts = []
            deadline = time.monotonic() + 55
            measurements = {}

            def wait_for(predicate, label):
                while time.monotonic() < deadline:
                    if predicate():
                        return
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)
                raise AssertionError("Timed out waiting for " + label + ": " + output.read_text(errors="replace")[-4500:])

            def state_now():
                try:
                    return json.loads((work / "aurora_control_panel_state.json").read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    return {}

            def wait_receipt(request_id):
                while time.monotonic() < deadline:
                    rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                    matching = [row for row in rows if row.get("event") == "command_result"
                                and row.get("request_id") == request_id and row.get("client_id") == "offline_smoke"]
                    if matching:
                        receipts.append(matching[-1])
                        return matching[-1]
                    if process.poll() is not None:
                        raise AssertionError(f"Runtime exited {process.returncode}: " + output.read_text(errors="replace")[-4500:])
                    time.sleep(0.01)
                raise AssertionError("Timed out waiting for " + request_id + ": " + output.read_text(errors="replace")[-4500:])

            def send(text, request_id):
                return append_bridge_request(work, text, raw=True, client_id="offline_smoke", request_id=request_id)

            try:
                send("SHOW_RUNTIME(); SHOW_AUTH()", "ready")
                assert wait_receipt("ready")["status"] == "processed"
                wait_for(lambda: state_now().get("locks", {}).get("live") is True
                         and state_now().get("modes", {}).get("live") is False,
                         "explicit offline/live-lock startup flags")
                inbox = work / "aurora_external_inbox.jsonl"
                record = build_bridge_request("SHOW_RUNTIME()", raw=True, client_id="offline_smoke", request_id="split")
                payload = (json.dumps(record) + "\n").encode()
                with inbox.open("ab") as handle:
                    handle.write(payload[:len(payload) // 2])
                time.sleep(0.7)
                with inbox.open("ab") as handle:
                    handle.write(payload[len(payload) // 2:])
                assert wait_receipt("split")["status"] == "processed"
                with inbox.open("ab") as handle:
                    handle.write(b'null\n{"text":"bad metadata","metadata":[]}\n')
                send("SHOW_RUNTIME(); UNKNOWN_SMOKE_COMMAND()", "reject")
                rejected = wait_receipt("reject")
                assert rejected["status"] == "rejected" and rejected["executed_commands"] == []
                send("SET_TIME_LOGGING(off)", "mutation")
                assert wait_receipt("mutation")["status"] == "processed"
                if contracts_only:
                    invalid_commands = ("WAIT(nan)", "WAIT(,1)", "pyag:hotkey(ctrl,not_a_real_key)",
                                        "pyag:press(a,1.5)", 'pyag:type("x🙂")',
                                        "pyag:move(1,2,inf)", "pyag:click(1,2,bogus)",
                                        "SET_TEMPERATURE(nan)", "SET_SCREENSHOT_INTERVAL(inf)",
                                        "SET_GAME_PROFILE(misspelled)", "SET_TURN_SCHEDULER_PROFILE(misspelled)",
                                        "SET_TURN_SCHEDULER_MODE(misspelled)", "SET_IMAGE_DETAIL(invalid)",
                                        "SET_TEMPERATURE(0.5,ignored)", "APPLY_SETTINGS_TRANSACTION(bad_token)",
                                        "ROLLBACK_SETTINGS_TRANSACTION()", "PREVIEW_SETTINGS_TRANSACTION(token,extra)",
                                        "LOCK_SETTING(unknown)", "UNLOCK_SETTING(temp,extra)", "TOGGLE_LIVE_MODE(ignored)",
                                        "GB_MODE(ignored)", "TOGGLE_IMAGE_DETAIL(ignored)",
                                        "SET_NEXT_INFERENCE(temperature=nan)", "SET_NEXT_INFERENCE(verbosity=bad; note=x)",
                                        "SET_NEXT_INFERENCE(reasoning=high; typo=low)", "CLEAR_NEXT_INFERENCE(extra)",
                                        "SAVE_PERSONAL_DEFAULTS(extra)", "APPLY_PERSONAL_DEFAULTS(extra)",
                                        "APPLY_SYSTEM_DEFAULTS(extra)", "SHOW_DEFAULT_PROFILES(extra)",
                                        "QUEUE_PENDING(WAIT(0),WAIT(1))", "INSERT_PENDING(WAIT(nan))",
                                        "REPLACE_PENDING(NO_SUCH_COMMAND())", "SHOW_PENDING(extra)", "CLEAR_PENDING(0)")
                    for index, invalid_command in enumerate(invalid_commands):
                        request = f"invalid-parameters-{index}"
                        send("SET_TIME_LOGGING(on); " + invalid_command, request)
                        rejected = wait_receipt(request)
                        assert rejected["status"] == "rejected" and rejected["executed_commands"] == [], rejected
                    send("TASKS()", "tasks-alias")
                    tasks = wait_receipt("tasks-alias")
                    assert tasks["status"] == "failed" and tasks["executed_commands"] == [], tasks
                    assert tasks["memory_command_results"][0]["effect_status"] == "not_started", tasks
                    assert "unimplemented legacy placeholder" in tasks["memory_command_results"][0]["reason"], tasks
                    send("SET_TIME_LOGGING(invalid)", "handler-failure")
                    invalid_boolean = wait_receipt("handler-failure")
                    assert invalid_boolean["status"] == "failed" and invalid_boolean["executed_commands"] == [], invalid_boolean
                    send("SET_SHOW_AI_TEXT(invalid); SET_TIME_LOGGING(on)", "reviewed-boolean-invalid")
                    invalid_reviewed = wait_receipt("reviewed-boolean-invalid")
                    assert invalid_reviewed["status"] == "rejected" and invalid_reviewed["executed_commands"] == [], invalid_reviewed
                    desktop_batch = 'pyag:focus_window("fixture missing"); pyag:type("never sent"); SET_TIME_LOGGING(on)'
                    send(desktop_batch, "desktop-failure")
                    failure = wait_receipt("desktop-failure")
                    assert failure["status"] == "failed" and failure["executed_commands"] == [], failure
                    assert len(failure["blocked_commands"]) == 2, failure
                    assert failure["desktop_results"][0]["effect_status"] == "uncertain", failure
                    send(desktop_batch, "desktop-failure")
                    def duplicate_desktop_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "desktop-failure" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_desktop_receipts, "desktop failure duplicate receipt")
                    duplicate_failure = duplicate_desktop_receipts()[-1]
                    assert duplicate_failure["desktop_results"] == failure["desktop_results"], duplicate_failure
                    assert duplicate_failure["blocked_commands"] == failure["blocked_commands"], duplicate_failure
                    receipts.append(duplicate_failure)
                    send("SET_TEMPERATURE(); SET_IMAGE_DETAIL()", "setting-query")
                    query = wait_receipt("setting-query")
                    assert query["status"] == "processed" and len(query["setting_results"]) == 2, query
                    baseline_temperature = query["setting_results"][0]["value"]
                    send("SET_TEMPERATURE(0.25)", "setting-write")
                    setting_write = wait_receipt("setting-write")
                    assert setting_write["status"] == "processed", setting_write
                    assert setting_write["setting_results"][0]["value"] == 0.25, setting_write
                    assert setting_write["setting_results"][0]["effect_status"] == "observed", setting_write
                    locked_batch = 'SET_LIVE_MODE(on); pyag:type("never sent after locked setting"); SET_TIME_LOGGING(on)'
                    send(locked_batch, "setting-locked")
                    locked = wait_receipt("setting-locked")
                    assert locked["status"] == "failed" and locked["executed_commands"] == [], locked
                    assert locked["setting_results"][0]["effect_status"] == "not_started", locked
                    assert len(locked["blocked_commands"]) == 2, locked
                    send(locked_batch, "setting-locked")
                    def duplicate_setting_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "setting-locked" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_setting_receipts, "locked setting duplicate receipt")
                    duplicate_setting = duplicate_setting_receipts()[-1]
                    assert duplicate_setting["setting_results"] == locked["setting_results"], duplicate_setting
                    assert duplicate_setting["blocked_commands"] == locked["blocked_commands"], duplicate_setting
                    receipts.append(duplicate_setting)
                    version = setting_write["setting_results"][0]["after_version"]
                    for operation in ("preview", "apply"):
                        request = build_settings_transaction_request(operation, changes={"temperature": 0.5}, expected_version=version)
                        send(build_settings_transaction_command(request), "settings-" + operation)
                        transaction = wait_receipt("settings-" + operation)
                        assert transaction["status"] == "processed", transaction
                        transaction_result = transaction["settings_transaction_receipts"][0]
                        assert transaction_result["status"] == ("previewed" if operation == "preview" else "applied"), transaction
                    rollback = build_settings_transaction_request("rollback", expected_version=transaction_result["after_version"],
                                                                  rollback_handle=transaction_result["rollback_handle"]["handle_id"])
                    send(build_settings_transaction_command(rollback), "settings-rollback")
                    rolled_back = wait_receipt("settings-rollback")
                    assert rolled_back["status"] == "processed", rolled_back
                    assert rolled_back["settings_transaction_receipts"][0]["status"] == "rolled_back", rolled_back
                    send(f"SET_TEMPERATURE({baseline_temperature}); SET_TEMPERATURE()", "setting-restore")
                    restored = wait_receipt("setting-restore")
                    assert restored["status"] == "processed", restored
                    assert restored["setting_results"][-1]["value"] == baseline_temperature, restored
                    # Exercise reviewed controls without enabling model I/O or sending native input.
                    send('TOGGLE_LIVE_MODE(); pyag:type("never sent after locked toggle")', "toggle-locked")
                    toggle_locked = wait_receipt("toggle-locked")
                    assert toggle_locked["status"] == "failed", toggle_locked
                    assert toggle_locked["setting_results"][0]["effect_status"] == "not_started", toggle_locked
                    assert len(toggle_locked["blocked_commands"]) == 1, toggle_locked
                    send("LOCK_SETTING(temp); SET_TEMPERATURE(0.75); SET_TIME_LOGGING(on)", "lock-blocks-setter")
                    lock_blocks = wait_receipt("lock-blocks-setter")
                    assert lock_blocks["status"] == "failed", lock_blocks
                    assert lock_blocks["lock_results"][0]["locks"]["temperature"] is True, lock_blocks
                    assert lock_blocks["setting_results"][0]["effect_status"] == "not_started", lock_blocks
                    send(f"UNLOCK_SETTING(temp); SET_TEMPERATURE({baseline_temperature}); LOCK_SETTING()", "unlock-and-query")
                    unlock_query = wait_receipt("unlock-and-query")
                    assert unlock_query["status"] == "processed", unlock_query
                    assert len(unlock_query["lock_results"]) == 2 and unlock_query["lock_results"][-1]["operation"] == "read", unlock_query
                    stale = build_settings_transaction_request("apply", changes={"temperature": 0.5}, expected_version="sv1:stale")
                    stale_batch = build_settings_transaction_command(stale) + '; pyag:type("never sent after stale transaction")'
                    send(stale_batch, "transaction-stale")
                    stale_result = wait_receipt("transaction-stale")
                    assert stale_result["status"] == "failed" and len(stale_result["blocked_commands"]) == 1, stale_result
                    assert stale_result["settings_transaction_receipts"][0]["status"] == "rejected", stale_result
                    send(stale_batch, "transaction-stale")
                    def duplicate_transaction_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "transaction-stale" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_transaction_receipts, "transaction duplicate receipt")
                    duplicate_transaction = duplicate_transaction_receipts()[-1]
                    assert duplicate_transaction["settings_transaction_receipts"] == stale_result["settings_transaction_receipts"], duplicate_transaction
                    assert duplicate_transaction["blocked_commands"] == stale_result["blocked_commands"], duplicate_transaction
                    receipts.append(duplicate_transaction)
                    send("SET_ACTION_MODE()", "action-mode-baseline")
                    action_baseline = wait_receipt("action-mode-baseline")
                    baseline_action = action_baseline["setting_results"][0]["value"]
                    send('PYAG_MODE(); type("")', "implicit-desktop-route")
                    implicit_desktop = wait_receipt("implicit-desktop-route")
                    assert implicit_desktop["status"] == "processed", implicit_desktop
                    assert implicit_desktop["desktop_results"][0]["action_route"]["namespace"] == "pyag", implicit_desktop
                    assert implicit_desktop["desktop_results"][0]["action_route"]["origin"] == "implicit", implicit_desktop
                    send('GB_MODE(); Start; PYAG:type("")', "implicit-game-route")
                    implicit_game = wait_receipt("implicit-game-route")
                    assert implicit_game["status"] == "failed", implicit_game
                    assert implicit_game["desktop_results"][0]["effect_status"] == "not_started", implicit_game
                    assert implicit_game["desktop_results"][0]["action_route"]["namespace"] == "gb", implicit_game
                    assert implicit_game["desktop_results"][0]["action_route"]["requested_key"] == "start", implicit_game
                    assert implicit_game["blocked_commands"] == ['PYAG:type("")'], implicit_game
                    send(f"SET_ACTION_MODE({baseline_action}); SET_ACTION_MODE()", "action-mode-restore")
                    action_restored = wait_receipt("action-mode-restore")
                    assert action_restored["setting_results"][-1]["value"] == baseline_action, action_restored
                    send("SET_TIME_LOGGING(on); NO_ACTION_MODE(); press(a)", "implicit-none-rejected")
                    none_rejected = wait_receipt("implicit-none-rejected")
                    assert none_rejected["status"] == "rejected" and none_rejected["executed_commands"] == [], none_rejected
                    action_request = build_settings_transaction_request("apply", changes={"action": "pyag"},
                                                                       expected_version=action_restored["setting_results"][-1]["after_version"])
                    send(build_settings_transaction_command(action_request) + '; type("")', "transaction-action-route")
                    action_applied = wait_receipt("transaction-action-route")
                    assert action_applied["status"] == "processed", action_applied
                    assert action_applied["desktop_results"][0]["action_route"]["namespace"] == "pyag", action_applied
                    action_transaction = action_applied["settings_transaction_receipts"][0]
                    action_rollback = build_settings_transaction_request("rollback", expected_version=action_transaction["after_version"],
                                                                         rollback_handle=action_transaction["rollback_handle"]["handle_id"])
                    send("SET_TIME_LOGGING(on); " + build_settings_transaction_command(action_rollback) + "; press(a)", "rollback-implicit-rejected")
                    ambiguous = wait_receipt("rollback-implicit-rejected")
                    assert ambiguous["status"] == "rejected" and ambiguous["executed_commands"] == [], ambiguous
                    send(build_settings_transaction_command(action_rollback), "action-transaction-restore")
                    action_rolled_back = wait_receipt("action-transaction-restore")
                    assert action_rolled_back["status"] == "processed", action_rolled_back
                    assert action_rolled_back["settings_transaction_receipts"][0]["status"] == "rolled_back", action_rolled_back
                send("SET_TIME_LOGGING(off)", "mutation")
                duplicate_deadline = min(deadline, time.monotonic() + 8)
                while time.monotonic() < duplicate_deadline:
                    rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                    duplicate = [row for row in rows if row.get("request_id") == "mutation"
                                 and row.get("duplicate_suppressed")]
                    if duplicate:
                        receipts.append(duplicate[-1])
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("No duplicate-suppression receipt")

                send("WAIT(60); SET_TIME_LOGGING(on)", "long-wait")
                wait_for(lambda: state_now().get("work", {}).get("commands", {}).get("active_scopes", 0) > 0, "active WAIT")
                send("SET_TIME_LOGGING(on)", "queued-after-wait")
                # Wait until both queued requests are admitted before cancelling.
                wait_for(lambda: 'queued-after-wait' in (work / "aurora_mutation_admission_log.jsonl").read_text(errors="replace"), "queued admission")
                stop_started = time.perf_counter()
                send("CANCEL_ACTIVE_WORK()", "cancel-wait")
                assert wait_receipt("cancel-wait")["status"] == "processed"
                measurements["wait_cancel_receipt_ms"] = round((time.perf_counter() - stop_started) * 1000, 2)
                assert measurements["wait_cancel_receipt_ms"] < 500, measurements
                for request in ("long-wait", "queued-after-wait"):
                    receipt = wait_receipt(request)
                    assert receipt["status"] == "cancelled" and receipt["executed_commands"] == [], receipt

                if simulate_model:
                    (work / "model-trigger").touch()
                    wait_for(lambda: (work / "model-entered").exists(), "fake model transport")
                    sidecars_before = len(list((work / "aurora_image_context_index").glob("*.json")))
                    send("REQUEST_SCREENSHOT_CAPTURE(during_model_wait, 0)", "capture-during-model")
                    assert wait_receipt("capture-during-model")["status"] == "processed"
                    wait_for(lambda: len(list((work / "aurora_image_context_index").glob("*.json"))) > sidecars_before,
                             "capture processing during blocked model request")
                    measurements["capture_processed_during_model_wait"] = True
                    stop_started = time.perf_counter()
                    send("CANCEL_ACTIVE_WORK()", "cancel-model")
                    assert wait_receipt("cancel-model")["status"] == "processed"
                    measurements["model_cancel_receipt_ms"] = round((time.perf_counter() - stop_started) * 1000, 2)
                    assert measurements["model_cancel_receipt_ms"] < 500, measurements
                    wait_for(lambda: (work / "model-caller-returned").exists(), "cancelled model caller")
                    wait_for(lambda: state_now().get("work", {}).get("model_io", {}).get("state") == "draining", "honest draining state")
                    (work / "model-release").touch()
                    wait_for(lambda: state_now().get("work", {}).get("model_io", {}).get("discarded_results") == 1, "late reply discarded")
                    assert not (work / "late-response-applied").exists()

                if not contracts_only:
                    send("REQUEST_SCREENSHOT_CAPTURE(identity_smoke, 0)", "capture")
                    assert wait_receipt("capture")["status"] == "processed"
                    wait_for(lambda: len(list((work / "aurora_image_context_index").glob("*.json"))) >= 2, "capture sidecars")
                checked_captures = []
                for sidecar in (work / "aurora_image_context_index").glob("*.json"):
                    record = json.loads(sidecar.read_text(encoding="utf-8"))
                    capture = Path(record["screenshot_path"])
                    assert capture.stem == record["image_id"] == sidecar.stem
                    assert hashlib.sha1(capture.read_bytes()[:16 * 1024 * 1024]).hexdigest()[:16] == record["hashes"]["file_sha1_prefix"]
                    checked_captures.append(capture.name)

                if contracts_only:
                    send("UNLOCK_SETTING(reasoning); UNLOCK_SETTING(models); UNLOCK_SETTING(temperature)", "plan-unlock")
                    assert wait_receipt("plan-unlock")["status"] == "processed"
                    plan_command = ('SET_NEXT_INFERENCE(reasoning:high; verbosity_level=low; summary=brief; '
                                    'detail=original; latest_detail=auto; temperature=0.35; model=fixture-custom; '
                                    'note="inspect; compare"; target_turn=2000000000)')
                    send(plan_command, "plan-write")
                    plan_write = wait_receipt("plan-write")
                    assert plan_write["status"] == "processed", plan_write
                    plan_row = plan_write["inference_plan_results"][0]
                    assert plan_row["plan"]["target_turn"] == 2000000000, plan_row
                    assert plan_row["plan"]["note"] == "inspect; compare", plan_row
                    assert plan_row["plan"]["temperature"] == "0.35" and plan_row["plan"]["model"] == "fixture-custom", plan_row
                    assert plan_row["plan"]["plan_id"] and plan_row["effect_status"] == "observed", plan_row
                    send(plan_command, "plan-write")
                    def duplicate_plan_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "plan-write" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_plan_receipts, "inference plan duplicate receipt")
                    duplicate_plan = duplicate_plan_receipts()[-1]
                    receipts.append(duplicate_plan)
                    assert duplicate_plan["inference_plan_results"] == plan_write["inference_plan_results"], duplicate_plan
                    send("SET_NEXT_INFERENCE(); SET_NEXT_REASONING_EFFORT(); SHOW_NEXT_INFERENCE()", "plan-read")
                    plan_read = wait_receipt("plan-read")
                    assert plan_read["status"] == "processed", plan_read
                    assert len(plan_read["inference_plan_results"]) == 3, plan_read
                    assert all(row["after_version"] == plan_row["after_version"] for row in plan_read["inference_plan_results"]), plan_read
                    send("LOCK_SETTING(reasoning)", "plan-lock")
                    assert wait_receipt("plan-lock")["status"] == "processed"
                    send("SET_NEXT_REASONING_EFFORT(max); SET_TIME_LOGGING(on)", "plan-locked")
                    plan_locked = wait_receipt("plan-locked")
                    assert plan_locked["status"] == "failed" and plan_locked["blocked_commands"] == ["SET_TIME_LOGGING(on)"], plan_locked
                    assert plan_locked["inference_plan_results"][0]["after_version"] == plan_row["after_version"], plan_locked
                    send("CLEAR_NEXT_INFERENCE()", "plan-clear")
                    plan_clear = wait_receipt("plan-clear")
                    assert plan_clear["status"] == "processed" and plan_clear["inference_plan_results"][0]["plan"]["target_turn"] == 0, plan_clear
                    send("UNLOCK_SETTING(reasoning); SET_NEXT_REASONING_EFFORT(max,puzzle)", "plan-effort")
                    plan_effort = wait_receipt("plan-effort")
                    assert plan_effort["status"] == "processed", plan_effort
                    assert plan_effort["inference_plan_results"][0]["plan"]["reasoning_effort"] == "max", plan_effort
                    send("CLEAR_NEXT_INFERENCE()", "plan-cleanup")
                    assert wait_receipt("plan-cleanup")["status"] == "processed"
                    measurements["inference_plan_checks"] = 9

                    send("SHOW_DEFAULT_PROFILES()", "defaults-read")
                    defaults_read = wait_receipt("defaults-read")["default_profile_results"][0]
                    assert defaults_read["defaults_status"]["personal_status"] == "missing", defaults_read
                    defaults_path = Path(defaults_read["defaults_status"]["personal_path"]).resolve()
                    assert defaults_path.parent == work, defaults_path
                    baseline_defaults = defaults_read["profile"]
                    send("SAVE_PERSONAL_DEFAULTS()", "defaults-save")
                    saved_defaults = wait_receipt("defaults-save")["default_profile_results"][0]
                    assert saved_defaults["success"] and saved_defaults["file_status"] == "available", saved_defaults
                    saved_bytes = defaults_path.read_bytes()
                    desired = dict(baseline_defaults, turn_scheduler_profile="custom",
                                   turn_heartbeat_seconds=4.123, turn_capture_wake_enabled=False,
                                   unchanged_screenshot_persist_interval=7.5, review_turn_interval=0,
                                   future_extension={"retained": True})
                    defaults_path.write_text(json.dumps(desired), encoding="utf-8")
                    send("APPLY_PERSONAL_DEFAULTS()", "defaults-apply")
                    applied_defaults_receipt = wait_receipt("defaults-apply")
                    applied_defaults = applied_defaults_receipt["default_profile_results"][0]
                    assert applied_defaults["success"] and applied_defaults["profile"]["turn_scheduler_profile"] == "custom", applied_defaults
                    assert applied_defaults["profile"]["unchanged_screenshot_persist_interval"] == 7.5, applied_defaults
                    assert applied_defaults["profile"]["turn_capture_wake_enabled"] is False, applied_defaults
                    assert applied_defaults["ignored_fields"] == ["future_extension"], applied_defaults
                    assert applied_defaults["apply_mode"] == "reapply", applied_defaults
                    send("APPLY_PERSONAL_DEFAULTS(changed_only)", "defaults-unchanged")
                    unchanged_defaults = wait_receipt("defaults-unchanged")["default_profile_results"][0]
                    assert unchanged_defaults["success"] and unchanged_defaults["attempted_fields"] == [], unchanged_defaults
                    assert unchanged_defaults["apply_mode"] == "changed_only", unchanged_defaults
                    send("SAVE_PERSONAL_DEFAULTS(); SET_TIME_LOGGING(on)", "defaults-resave")
                    assert wait_receipt("defaults-resave")["status"] == "processed"
                    assert json.loads(defaults_path.read_text())["future_extension"] == {"retained": True}
                    send("APPLY_PERSONAL_DEFAULTS()", "defaults-apply")
                    def duplicate_defaults_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "defaults-apply" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_defaults_receipts, "defaults duplicate receipt")
                    duplicate_defaults = duplicate_defaults_receipts()[-1]
                    receipts.append(duplicate_defaults)
                    assert duplicate_defaults["default_profile_results"] == applied_defaults_receipt["default_profile_results"], duplicate_defaults
                    send("SHOW_DEFAULT_PROFILES(); LOCK_SETTING(temperature)", "defaults-before-lock")
                    locked_before = wait_receipt("defaults-before-lock")["default_profile_results"][0]
                    assert locked_before["profile"]["time_logging"] is True, locked_before
                    send("APPLY_PERSONAL_DEFAULTS(); SET_TIME_LOGGING(off)", "defaults-locked")
                    defaults_locked = wait_receipt("defaults-locked")
                    assert defaults_locked["status"] == "failed" and defaults_locked["blocked_commands"] == ["SET_TIME_LOGGING(off)"], defaults_locked
                    assert defaults_locked["default_profile_results"][0]["attempted_fields"] == [], defaults_locked
                    assert defaults_locked["default_profile_results"][0]["after_version"] == locked_before["after_version"], defaults_locked
                    send("UNLOCK_SETTING(temperature); APPLY_SYSTEM_DEFAULTS()", "defaults-system")
                    system_restored = wait_receipt("defaults-system")
                    assert system_restored["status"] == "processed", system_restored
                    assert system_restored["default_profile_results"][0]["source"] == "system"
                    defaults_path.write_text("malformed fixture", encoding="utf-8")
                    send("APPLY_PERSONAL_DEFAULTS(); SET_TIME_LOGGING(on)", "defaults-invalid-file")
                    invalid_defaults = wait_receipt("defaults-invalid-file")
                    assert invalid_defaults["status"] == "failed", invalid_defaults
                    assert invalid_defaults["default_profile_results"][0]["file_status"] == "invalid", invalid_defaults
                    assert invalid_defaults["default_profile_results"][0]["effect_status"] == "not_started", invalid_defaults
                    defaults_path.write_bytes(saved_bytes)
                    send("APPLY_PERSONAL_DEFAULTS()", "defaults-restore")
                    defaults_restored = wait_receipt("defaults-restore")
                    assert defaults_restored["status"] == "processed", defaults_restored
                    assert defaults_restored["default_profile_results"][0]["profile"] == baseline_defaults, defaults_restored
                    assert not list(work.glob(".*.aurora-*.tmp")), "Owned profile save temporary file survived."
                    measurements["default_profile_checks"] = 11

                    send("QUEUE_PENDING(WAIT(0)); SHOW_PENDING()", "pending-first")
                    first_receipt = wait_receipt("pending-first")
                    first = first_receipt["pending_command_results"][-1]["entries"][0]
                    first_version = first_receipt["pending_command_results"][-1]["after_version"]
                    first_id = first["pending_id"]
                    send("CLEAR_PENDING(memory); SHOW_PENDING()", "pending-no-match")
                    no_match = wait_receipt("pending-no-match")["pending_command_results"]
                    assert no_match[0]["cleared_count"] == 0 and no_match[1]["entries"][0]["pending_id"] == first_id, no_match
                    send("INSERT_PENDING(WAIT(0.01)); SHOW_PENDING()", "pending-insert")
                    inserted = wait_receipt("pending-insert")["pending_command_results"][-1]["entries"]
                    assert len(inserted) == 2 and inserted[0]["execute_by_inference"] > inserted[1]["execute_by_inference"], inserted
                    send(f"CLEAR_PENDING(id:{first_id},version:{first_version}); SET_TIME_LOGGING(on)", "pending-stale-version")
                    stale = wait_receipt("pending-stale-version")
                    assert stale["status"] == "failed" and stale["blocked_commands"] == ["SET_TIME_LOGGING(on)"], stale
                    send("CLEAR_PENDING(all,misspelled); SET_TIME_LOGGING(on)", "pending-invalid-selector")
                    invalid = wait_receipt("pending-invalid-selector")
                    assert invalid["status"] == "failed" and invalid["pending_command_results"][0]["after_count"] == 2, invalid
                    send("OVERRIDE_PENDING(WAIT(0.02)); SHOW_PENDING()", "pending-replace")
                    replaced = wait_receipt("pending-replace")["pending_command_results"]
                    assert replaced[0]["removed_ids"] == [inserted[1]["pending_id"]], replaced
                    assert len(replaced[-1]["entries"]) == 2, replaced
                    selected_version = replaced[-1]["after_version"]
                    approve_text = f"APPROVE_PENDING(id:{first_id},version:{selected_version})"
                    send(approve_text, "pending-approve")
                    approved = wait_receipt("pending-approve")
                    approved_result = approved["pending_command_results"][0]
                    assert approved_result["success"] and approved_result["submissions"][0]["status"] == "queued", approved
                    attempt_id = approved_result["submissions"][0]["pending_attempt_id"]
                    def pending_execution_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("event") == "command_result"
                                and row.get("pending_attempt_id") == attempt_id]
                    wait_for(pending_execution_receipts, "correlated pending execution receipt")
                    execution = pending_execution_receipts()[-1]
                    assert execution["pending_id"] == first_id and execution["status"] == "processed", execution
                    receipts.append(execution)
                    send(approve_text, "pending-approve")
                    def duplicate_pending_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "pending-approve" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_pending_receipts, "pending duplicate receipt")
                    duplicate_pending = duplicate_pending_receipts()[-1]
                    receipts.append(duplicate_pending)
                    assert duplicate_pending["pending_command_results"] == approved["pending_command_results"], duplicate_pending
                    assert len(pending_execution_receipts()) == 1, "Duplicate pending execution"
                    send(f"APPROVE_PENDING(id:{first_id})", "pending-stale-id")
                    assert wait_receipt("pending-stale-id")["status"] == "failed"
                    send("CLEAR_PENDING(); SHOW_PENDING_COMMANDS()", "pending-clear-rest")
                    cleared = wait_receipt("pending-clear-rest")["pending_command_results"]
                    assert cleared[0]["cleared_count"] == 1 and cleared[1]["entries"] == [], cleared
                    measurements["pending_command_checks"] = 10

                    send("SET_IMPORTANT_MESSAGES(on); SET_ADD_IMSGS_TO_HISTORY(on); CLEAR%(100); PIN(history fixture)", "history-pin")
                    pinned = wait_receipt("history-pin")["history_command_results"]
                    assert pinned[0]["after"]["count"] == 0, pinned
                    assert pinned[1]["added_count"] == 1 and pinned[1]["success"], pinned
                    timestamp = pinned[1]["added_timestamps"][0]
                    send(f'EDIT_MSGS("{timestamp}",history edited); SAVECH(history-proof)', "history-edit-save")
                    edited_receipt = wait_receipt("history-edit-save")
                    edited, saved = edited_receipt["history_command_results"]
                    assert edited["edited_count"] == 1 and edited["model_work_cancelled"], edited
                    export = Path(saved["path"]).resolve()
                    assert export.parent == work and saved["success"], saved
                    assert "history edited" in export.read_text(encoding="utf-8"), saved
                    assert hashlib.sha256(export.read_bytes()).hexdigest() == saved["sha256"], saved
                    assert not saved["model_work_cancelled"], saved
                    send(f'EDIT_MSGS("{timestamp}",history edited); SAVECH(history-proof)', "history-edit-save")
                    def duplicate_history_receipts():
                        rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in rows if row.get("request_id") == "history-edit-save" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_history_receipts, "history duplicate receipt")
                    duplicate_history = duplicate_history_receipts()[-1]
                    receipts.append(duplicate_history)
                    assert duplicate_history["history_command_results"] == edited_receipt["history_command_results"], duplicate_history
                    send("SAVECH(history-proof); CLEAR_NOPIN%(0); DHISTORY()", "history-read")
                    history_read = wait_receipt("history-read")["history_command_results"]
                    assert history_read[0]["path"] != saved["path"] and export.exists(), history_read
                    assert history_read[1]["removed_count"] == 0 and not history_read[1]["model_work_cancelled"], history_read
                    assert history_read[2]["before_version"] == history_read[2]["after_version"], history_read
                    send("SET_ADD_IMSGS_TO_HISTORY(off); INIT(blocked); SET_TIME_LOGGING(on)", "history-retention")
                    blocked_history = wait_receipt("history-retention")
                    assert blocked_history["status"] == "failed" and blocked_history["blocked_commands"] == ["SET_TIME_LOGGING(on)"], blocked_history
                    retained = blocked_history["history_command_results"][0]
                    assert retained["before_version"] == retained["after_version"] and not retained["model_work_cancelled"], retained
                    send("SET_ADD_IMSGS_TO_HISTORY(on); INIT(first); INIT(second); CLEAR_NOPIN%(100,oldest); CLEAR_NOPIN%(100,newest)", "history-init")
                    initialized = wait_receipt("history-init")["history_command_results"]
                    assert initialized[1]["removed_count"] == 1 and initialized[1]["added_count"] == 1, initialized
                    assert initialized[2]["after"]["protected_count"] >= 2, initialized
                    send("PIN(must not apply); CLEAR%(nan)", "history-invalid")
                    invalid_history = wait_receipt("history-invalid")
                    assert invalid_history["status"] == "rejected" and not invalid_history["executed_commands"], invalid_history
                    send("DELETE_MSG(missing-fixture); SET_TIME_LOGGING(on)", "history-missing")
                    missing_history = wait_receipt("history-missing")
                    assert missing_history["status"] == "failed" and missing_history["blocked_commands"] == ["SET_TIME_LOGGING(on)"], missing_history
                    send("SAVECH(missing-directory/export); SET_TIME_LOGGING(on)", "history-export-failure")
                    export_failure = wait_receipt("history-export-failure")
                    assert export_failure["status"] == "failed" and export_failure["blocked_commands"] == ["SET_TIME_LOGGING(on)"], export_failure
                    send("CLEAR_PIN(); CLEAR_INIT(); CLEAR_HANDOFF(); CLEAR_NONPIN(); CLEAR(); DHISTORY()", "history-clear")
                    cleared_history = wait_receipt("history-clear")["history_command_results"]
                    assert all(row["success"] for row in cleared_history), cleared_history
                    assert cleared_history[-1]["after"]["protected_count"] == 0, cleared_history
                    measurements["history_command_checks"] = 10

                    # Retrieval remains local: use real ingress/scorer/state with embeddings off.
                    memory_path = work / "aurora_memory" / "episodic_snapshots.jsonl"
                    memory_path.parent.mkdir(exist_ok=True)
                    memory_path.write_text("\n".join(json.dumps(row) for row in [
                        {"snapshot_id": "retrieval-hit", "summary_text": "rocket clue", "tags": ["fixture"],
                         "timestamp": "2026-10-16 00:00:00", "created_at_epoch": 1, "source_bucket": "manual"},
                        {"snapshot_id": "retrieval-unrelated", "summary_text": "unrelated newest memory", "tags": [],
                         "timestamp": "2026-10-16 01:00:00", "source_bucket": "manual"}, None,
                    ]) + "\n", encoding="utf-8")
                    send("RETRIEVAL_PULL(rocket,semantic_backend=off,time_weight=0,semantic_weight=1,semantic_tag_weight=0,min_relevance=.1)", "retrieval-zero")
                    assert wait_receipt("retrieval-zero")["status"] == "processed"
                    wait_for(lambda: (state_now().get("episodic_memory", {}).get("last_retrieval_items", []) or [{}])[0].get("snapshot_id") == "retrieval-hit", "retrieval zero weights")
                    item = state_now()["episodic_memory"]["last_retrieval_items"][0]
                    assert item["semantic_score"] == 1 and item["time_mode"] == "ordinal", item
                    send("RECALL(rocket,3,semantic_backend=off,semantic_tag_weight=0,time_mode=age,age_half_life_hours=24,min_relevance=.1)", "retrieval-recall")
                    assert wait_receipt("retrieval-recall")["status"] == "processed"
                    wait_for(lambda: (state_now().get("episodic_memory", {}).get("last_retrieval_items", []) or [{}])[0].get("time_mode") == "age", "retrieval age mode")
                    item = state_now()["episodic_memory"]["last_retrieval_items"][0]
                    assert item["semantic_score"] == 1 and item["time_score"] == 0 and item["age_hours"] > 24, item
                    send("MEM(rocket,semantic_backend=off,min_relevance=nan)", "retrieval-invalid")
                    assert wait_receipt("retrieval-invalid")["status"] == "rejected"
                    send("RETRIEVAL_PULL(rocket,semantic_backend=off,min_relevance=0)", "retrieval-legacy")
                    assert wait_receipt("retrieval-legacy")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_count") == 2, "retrieval legacy permissive ranking")
                    assert not (memory_path.parent / "episodic_embedding_cache.json").exists(), "Offline retrieval wrote an embedding cache."
                    send("RECALL(rocket,semantic_backend=off,score_mode=weighted,description_weight=1,keyword_weight=0,recency_weight=0,rating_weight=0)", "retrieval-visual-description")
                    assert wait_receipt("retrieval-visual-description")["status"] == "processed"
                    wait_for(lambda: (state_now().get("episodic_memory", {}).get("last_retrieval_items", []) or [{}])[0].get("score_mode") == "weighted", "retrieval weighted scorer")
                    item = state_now()["episodic_memory"]["last_retrieval_items"][0]
                    assert item["weighted_total"] == 1 and item["score_contributions"]["rating"] == 0, item
                    send("MEM(rocket,semantic_backend=off,score_mode=weighted,description_weight=0,keyword_weight=0,recency_weight=1,rating_weight=0)", "retrieval-visual-time")
                    assert wait_receipt("retrieval-visual-time")["status"] == "processed"
                    wait_for(lambda: (state_now().get("episodic_memory", {}).get("last_retrieval_items", []) or [{}])[0].get("snapshot_id") == "retrieval-unrelated", "retrieval pure time scorer")
                    item = state_now()["episodic_memory"]["last_retrieval_items"][0]
                    assert item["weighted_total"] == 1 and item["score_contributions"]["description"] == 0, item
                    expression = '("rocket clue" OR badge) AND NOT failed'
                    send("RECALL(text_filter=" + json.dumps(expression) + ",text_mode=boolean,tags_required=fixture,source_buckets=manual,date_start=1970-01-01,date_end=1970-01-01,sort=newest,semantic_backend=force)", "search-filter-only")
                    assert wait_receipt("search-filter-only")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("filter_only") is True, "filter-only search state")
                    search_state = state_now()["episodic_memory"]
                    assert search_state["last_retrieval_backend"] == "filter_only", search_state
                    assert search_state["last_retrieval_search"]["eligible_records"] == 1, search_state
                    assert len(search_state["last_retrieval_items"][0]["search_matches"]) == 4, search_state
                    send("MEM(source_buckets=manual,sort=newest,k=1,offset=1,semantic_backend=force)", "search-page")
                    assert wait_receipt("search-page")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("offset") == 1, "search page state")
                    search_state = state_now()["episodic_memory"]
                    assert search_state["last_retrieval_items"][0]["snapshot_id"] == "retrieval-hit", search_state
                    assert search_state["last_retrieval_search"]["matched_records"] == 2, search_state
                    send("RETRIEVAL_PULL(text_filter=rock*,text_mode=wildcard,semantic_backend=off)", "search-wildcard")
                    assert wait_receipt("search-wildcard")["status"] == "processed"
                    send("RECALL(rocket,author=someone,semantic_backend=off)", "search-unsupported")
                    assert wait_receipt("search-unsupported")["status"] == "rejected"
                    send("MEM(date_start=2026-10-18,date_end=2026-10-16,semantic_backend=off)", "search-reversed")
                    assert wait_receipt("search-reversed")["status"] == "rejected"
                    send("RECALL(date_period=yesterday,date_anchor=1970-01-02T12:00:00Z,semantic_backend=force)", "search-relative")
                    assert wait_receipt("search-relative")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("date_window", {}).get("period") == "yesterday", "anchored relative window")
                    relative = state_now()["episodic_memory"]["last_retrieval_search"]
                    assert relative["date_window"]["start_epoch"] == 0 and relative["date_window"]["end_epoch"] == 86400, relative
                    assert relative["matched_records"] == 1, relative
                    send("MEM(after=1970-01-01T00:00:01Z,before=1970-01-02,semantic_backend=force)", "search-strict-after")
                    assert wait_receipt("search-strict-after")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("start_epoch_exclusive") == 1, "strict after readback")
                    assert state_now()["episodic_memory"]["last_retrieval_search"]["matched_records"] == 0
                    send("RECALL(date_period=today,date_start=1970-01-01,semantic_backend=force)", "search-conflicting-window")
                    assert wait_receipt("search-conflicting-window")["status"] == "rejected"
                    send("RECALL(date_period=last_7_days,feedback_mode=skip,semantic_backend=force)", "search-moving-feedback")
                    assert wait_receipt("search-moving-feedback")["status"] == "rejected"
                    assert not (memory_path.parent / "episodic_embedding_cache.json").exists(), "Filter-only search called embeddings."
                    send("RECALL(rocket,semantic_backend=off,feedback_mode=skip,feedback_session=smoke,k=1,sort=relevance)", "feedback-first")
                    assert wait_receipt("feedback-first")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("feedback", {}).get("session") == "smoke", "feedback first token")
                    first_state = state_now()["episodic_memory"]
                    token = first_state["last_retrieval_search"]["feedback"]["token"]
                    first_id = first_state["last_retrieval_items"][0]["snapshot_id"]
                    repeat = "RECALL(rocket,semantic_backend=off,feedback_mode=skip,feedback_session=smoke,k=1,sort=relevance,feedback_action=reject_last,feedback_token=" + token + ")"
                    send(repeat, "feedback-reject")
                    assert wait_receipt("feedback-reject")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("feedback", {}).get("rejected_records") == 1, "feedback rejection")
                    assert state_now()["episodic_memory"]["last_retrieval_items"][0]["snapshot_id"] != first_id
                    send(repeat, "feedback-stale")
                    assert wait_receipt("feedback-stale")["status"] == "failed"
                    send("RECALL(rocket,semantic_backend=off,feedback_mode=skip,feedback_session=smoke,feedback_action=reset,k=1,sort=relevance)", "feedback-reset")
                    assert wait_receipt("feedback-reset")["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("feedback", {}).get("rejected_records") == 0, "feedback reset")
                    # Retained K-sets remain exact after a different query/corpus replaces the preview.
                    retained_records = [{"snapshot_id": "duplicate-legacy-id", "summary_text": f"rocket item {index}: " + "complete evidence " * 20,
                                         "tags": ["retained"], "created_at_epoch": index, "source_bucket": "manual"} for index in range(12)]
                    memory_path.write_text("\n".join(json.dumps(row) for row in retained_records) + "\n", encoding="utf-8")
                    send("RECALL(rocket,k=12,sort=oldest,semantic_backend=off,result_mode=retained)", "retained-search")
                    retained_search_receipt = wait_receipt("retained-search")
                    assert retained_search_receipt["status"] == "processed"
                    wait_for(lambda: state_now().get("episodic_memory", {}).get("last_retrieval_search", {}).get("retained_result"), "retained handle")
                    retained_state = state_now()["episodic_memory"]
                    retained_handle = retained_state["last_retrieval_search"]["retained_result"]["handle"]
                    assert len(retained_state["last_retrieval_items"]) == 8 and retained_state["last_retrieval_count"] == 12
                    send(f"SHOW_RETRIEVAL_RESULT({retained_handle},8,4)", "retained-inspect")
                    page = wait_receipt("retained-inspect")["retrieval_results"][0]["page"]
                    assert len(page["items"]) == 4 and page["items"][0]["item_index"] == 9, page
                    assert page["items"][0]["candidate"]["record"]["summary_text"] == retained_records[8]["summary_text"]
                    memory_path.write_text(json.dumps({"snapshot_id": "replacement", "summary_text": "different query"}) + "\n", encoding="utf-8")
                    send("RECALL(different,semantic_backend=off)", "retained-replace-preview")
                    assert wait_receipt("retained-replace-preview")["status"] == "processed"
                    promote = f'PROMOTE_EPISODIC_MEMORY(9,notes,"",{retained_handle})'
                    send(promote, "retained-promote")
                    promoted_receipt = wait_receipt("retained-promote")
                    promoted = promoted_receipt["retrieval_results"][0]
                    assert promoted["success"] and promoted["selection_mode"] == "retained", promoted
                    assert promoted["summary"] == retained_records[8]["summary_text"].strip(), promoted
                    assert promoted["before"] != promoted["after"], promoted
                    send(promote, "retained-promote")
                    def duplicate_retained_receipts():
                        log_rows, _ = read_jsonl_from(work / "aurora_command_execution_log.jsonl")
                        return [row for row in log_rows if row.get("request_id") == "retained-promote" and row.get("duplicate_suppressed")]
                    wait_for(duplicate_retained_receipts, "retained duplicate receipt")
                    duplicate = duplicate_retained_receipts()[-1]
                    receipts.append(duplicate)
                    assert duplicate["duplicate_suppressed"] and duplicate["retrieval_results"] == promoted_receipt["retrieval_results"], duplicate
                    send('PROMOTE_EPISODIC_MEMORY(1,notes);SHOW_RETRIEVAL_RESULT(bad)', "retained-admission-reject")
                    assert wait_receipt("retained-admission-reject")["status"] == "rejected"
                    unknown_handle = "rr_" + "0" * 32
                    send(f'PROMOTE_EPISODIC_MEMORY(1,notes,"",{unknown_handle});PROMOTE_EPISODIC_MEMORY(1,notes)', "retained-missing")
                    missing = wait_receipt("retained-missing")
                    assert missing["status"] == "failed" and len(missing["blocked_commands"]) == 1, missing
                    assert missing["retrieval_results"][0]["effect_status"] == "not_applied", missing
                    query_receipt = retained_search_receipt["retrieval_results"][0]
                    assert query_receipt["operation"] == "retrieve" and query_receipt["effect_status"] == "published", query_receipt
                    assert query_receipt["search"]["retained_result"]["handle"] == retained_handle
                    assert query_receipt["retrieval_id"] == query_receipt["search"]["retrieval_id"]
                    assert query_receipt["search"]["returned_records"] == 12 and len(query_receipt["preview"]) == 8
                    # A statically invalid query at the tail must prevent the preceding file write.
                    before_file = memory_path.read_bytes()
                    send('WRITE_EPISODIC_SNAPSHOT(must not write);RECALL(rocket,argument_policy=strict,k=nan)', "retrieval-admission-tail")
                    assert wait_receipt("retrieval-admission-tail")["status"] == "rejected"
                    assert memory_path.read_bytes() == before_file
                    send('RECALL(different,semantic_backend=off,k=nan,time_weight=2,argument_policy=legacy)', "retrieval-coercion")
                    legacy_receipt = wait_receipt("retrieval-coercion")["retrieval_results"][0]
                    assert legacy_receipt["success"] and legacy_receipt["effective"]["k"] == 4 and legacy_receipt["effective"]["time_weight"] == 1
                    send('MEM(different,semantic_backend=off,argument_policy=strict,time_weight=0)', "retrieval-strict")
                    strict_receipt = wait_receipt("retrieval-strict")["retrieval_results"][0]
                    assert strict_receipt["success"] and strict_receipt["effective"]["time_weight"] == 0
                    send('WRITE_EPISODIC_SNAPSHOT(receipt proof,contracttag)', "snapshot-receipt-write")
                    written = wait_receipt("snapshot-receipt-write")["retrieval_results"][0]
                    assert written["success"] and written["effect_status"] == "appended", written
                    actual_records = [json.loads(line) for line in memory_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    actual = next(row for row in actual_records if row.get("snapshot_id") == written["snapshot"]["snapshot_id"])
                    assert hashlib.sha256(json.dumps(actual, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest() == written["snapshot"]["record_sha256"]
                    assert written["snapshot_count_after"] == written["snapshot_count_before"] + 1
                    send('LIST_EPISODIC_SNAPSHOTS(2);SEARCH_EPISODIC_SNAPSHOTS(contracttag,2)', "snapshot-receipt-read")
                    listed, searched = wait_receipt("snapshot-receipt-read")["retrieval_results"]
                    assert listed["returned_count"] == 2 and searched["returned_count"] == 1, (listed, searched)
                    assert searched["preview"][0]["snapshot_id"] == written["snapshot"]["snapshot_id"]
                    assert searched["preview"][0]["lexical_score"] > 0
                    # A now-unavailable feedback token is an execution failure, not static rejection.
                    send('RECALL(different,semantic_backend=off,feedback_mode=skip,feedback_action=reject_last,feedback_token=unknown);WRITE_EPISODIC_SNAPSHOT(must not write)', "retrieval-runtime-tail")
                    before_tail = memory_path.read_bytes()
                    failed_query = wait_receipt("retrieval-runtime-tail")
                    assert failed_query["status"] == "failed" and len(failed_query["blocked_commands"]) == 1, failed_query
                    assert not failed_query["retrieval_results"][0]["success"]
                    assert memory_path.read_bytes() == before_tail
                    measurements["episodic_retrieval_checks"] = 33

                send("WAIT(60)", "shutdown-wait")
                wait_for(lambda: state_now().get("work", {}).get("commands", {}).get("active_scopes", 0) > 0, "shutdown WAIT")
                stop_started = time.perf_counter()
                send("SHUTDOWN_RUNTIME()", "shutdown")
                shutdown = wait_receipt("shutdown")
                assert shutdown["status"] == "processed", shutdown
                measurements["shutdown_receipt_ms"] = round((time.perf_counter() - stop_started) * 1000, 2)
                assert measurements["shutdown_receipt_ms"] < 500, measurements
                assert wait_receipt("shutdown-wait")["status"] == "cancelled"
                process.wait(timeout=12)
                assert process.returncode == 0
                state = json.loads((work / "aurora_control_panel_state.json").read_text(encoding="utf-8-sig"))
                assert state["modes"]["live"] is False
                if contracts_only:
                    assert not (work / "forbidden-native-input.txt").exists(), "A blocked action attempted native input."
                return {
                    "status": "passed", "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "launcher_exit": process.returncode, "live_mode": state["modes"]["live"],
                    "measurements": measurements, "captures_verified": len(checked_captures),
                    "fake_model_transport": simulate_model,
                    "desktop_capture_disabled": contracts_only,
                    "native_input_guard_passed": contracts_only,
                    "model_transport_guard_passed": contracts_only,
                    "startup_flags_verified": True,
                    "request_statuses": [{key: row.get(key) for key in (
                        "request_id", "status", "delivery_status", "duplicate_suppressed", "desktop_results", "setting_results", "lock_results", "inference_plan_results", "default_profile_results", "pending_command_results", "history_command_results", "retrieval_results", "pending_id", "pending_attempt_id", "settings_transaction_receipts", "blocked_commands")}
                        for row in receipts],
                    "isolation": "Disposable source copy; real runtime, workers, ingress and receipts.",
                    "owned_runtime_pid": process.pid,
                    "fixture_directory": str(work),
                }
            finally:
                if process.poll() is None:
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, timeout=10)
                    process.wait(timeout=10)


if __name__ == "__main__":
    print(json.dumps(run_smoke(simulate_model="--fake-model" in sys.argv,
                               contracts_only="--contracts-only" in sys.argv), indent=2))
