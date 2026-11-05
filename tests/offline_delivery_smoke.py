"""Exact inbox-to-inference receipts with fake I/O; no native input or provider calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from offline_panel_smoke import COPY_FILES
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + '''
import json
import threading
from types import SimpleNamespace
from aurora_conversation_delivery import SessionOutbox
from aurora_control_plane import read_jsonl_from

runtime.pyautogui.position = lambda: SimpleNamespace(x=0, y=0)
runtime.display_message = lambda *args, **kwargs: None
runtime.process_assistant_response = lambda *args, **kwargs: None
runtime.maybe_build_episodic_planning_context = lambda *args, **kwargs: {"used": False}
runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
runtime.REVIEW_TURN_INTERVAL = runtime.CRITIQUE_TURN_INTERVAL = 0
runtime.MODEL_TRANSPORT = "chat_completions"
runtime.ACTIVE_TEXT_MODEL = runtime.ACTIVE_VISION_MODEL = runtime.ACTIVE_REASONING_MODEL = "gpt-6.1-sol"
runtime.set_agent_running(True)
box = SessionOutbox(Path.cwd())
mode, calls = "success", []
entered, release = threading.Event(), threading.Event()

def fake_provider(packet, token):
    token.check()
    calls.append(packet["payload"])
    if mode == "cancel":
        entered.set()
        assert release.wait(5), "Bounded cancellation fixture timed out"
    if mode == "auth":
        raise ValueError("fixture auth failure")
    if mode == "http":
        return SimpleNamespace(status_code=429, text="fixture rate limit"), "api_key", "fixture"
    data = {} if mode == "malformed" else {"model": "provider-fixture", "choices": [{"message": {"content": "Fixture reply."}}]}
    return SimpleNamespace(status_code=200, json=lambda: data), "api_key", "fixture"

runtime.perform_model_http_request = fake_provider
def send(text):
    record = runtime.append_external_message_record(text, source="panel_conversation", client_id="delivery_smoke")
    box.track(record)
    runtime.poll_external_inbox_messages()
    box.poll()
    assert box.rows[record["request_id"]]["phase"] == "received"
    return record

def observed(record):
    box.poll()
    return box.rows[record["request_id"]]

def finish(record, phase):
    row = observed(record)
    assert row["phase"] == phase, row
    return row

proof = {}
try:
    first = send("Identical fixture input")
    assert not runtime.handle_queued_input("", "")
    assert runtime.get_input_queue_store().qsize() == 1
    assert not calls
    second = send("Identical fixture input")
    runtime.get_input_queue_store().put("Legacy shell string")
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    assert runtime.handle_queued_input("", "")
    a, b = finish(first, "responded"), finish(second, "responded")
    assert a["inference_request_id"] == b["inference_request_id"]
    assert a["provider_model"] == "provider-fixture"
    assert len(calls) == 1 and "Legacy shell string" in str(calls[-1]["messages"])
    rows = read_jsonl_from(Path("aurora_external_bridge_log.jsonl"))[0]
    phases = [row["phase"] for row in rows if row.get("event") == "message_model_delivery" and row["request_id"] == first["request_id"]]
    assert phases == ["preparing", "prepared", "submitted", "responded"], phases
    proof["coalesced_distinct_messages"] = phases

    bad_image = send("Invalid screenshot fixture")
    count = len(calls)
    assert runtime.handle_queued_input("missing-fixture-image.png", "fixture-time")
    assert not finish(bad_image, "failed")["request_started"] and len(calls) == count
    proof["invalid_image_not_submitted"] = True

    for next_mode in ("auth", "http", "malformed"):
        mode = next_mode
        record = send("Failure fixture " + mode)
        try:
            runtime.handle_queued_input("", "")
        except KeyError:
            assert mode == "malformed"
        finish(record, "failed")
        assert runtime.get_input_queue_store().empty()
    proof["auth_http_malformed_failures"] = True

    mode = "cancel"
    record = send("Cancellation fixture")
    def cancel_during_wait():
        if entered.is_set():
            runtime.MODEL_WORK.cancel("fixture cancel")
    runtime.service_runtime_control_during_model_wait = cancel_during_wait
    previous_history = sum(entry.get("role") == "assistant" for entry in runtime.get_chat_history_store())
    runtime.handle_queued_input("", "")
    row = finish(record, "cancelled")
    assert row["request_started"] and runtime.MODEL_IO.busy
    release.set()
    deadline = time.monotonic() + 3
    while runtime.MODEL_IO.busy and time.monotonic() < deadline:
        time.sleep(.01)
    assert not runtime.MODEL_IO.busy
    assert sum(entry.get("role") == "assistant" for entry in runtime.get_chat_history_store()) == previous_history
    assert finish(record, "cancelled")["phase"] == "cancelled"
    proof["late_response_discarded_after_cancel"] = True

    mode = "success"
    runtime.service_runtime_control_during_model_wait = lambda: None
    record = send("After cancellation")
    runtime.handle_queued_input("", "")
    finish(record, "responded")
    proof["next_turn_recovers"] = True
    runtime.SEND_TO_MODEL = False
    record = send("Pause race fixture")
    tracked = runtime.get_input_queue_store().get_nowait()
    runtime.send_prompt_to_chatgpt(str(tracked), delivery_refs=tracked.delivery_refs)
    assert not finish(record, "not_sent")["request_started"]
    assert not Path("forbidden-native-input.txt").exists()
    proof.update(status="passed", fake_requests=len(calls), real_api_calls=0, input_receipts=len(box.rows),
                 pause_race_explicit=True, native_network_guards_unused=True)
finally:
    release.set()
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    assert not runtime.MODEL_IO.busy
Path("proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
'''


def run_smoke():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=".aurora-delivery-smoke-", dir=ROOT) as directory:
        work = Path(directory).resolve()
        assert work.parent == ROOT.resolve()
        for name in COPY_FILES:
            shutil.copy2(ROOT/name, work/name)
        (work/"fixture.py").write_text(FIXTURE, encoding="utf-8")
        flags = ["--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
                 "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none"]
        env = dict(os.environ, AURORA_ENABLE_TEXT_INPUT_PROCESS="0", AURORA_AUTH_MODE="api_key", PYTHONUNBUFFERED="1")
        with (work/"process.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(work/"fixture.py"), *flags], cwd=work, env=env,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ownership = {"pid": process.pid, "started_at_epoch": time.time(), "fixture_path": str(work)}
            try:
                code = process.wait(timeout=60)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
        if code != 0:
            raise AssertionError((work/"process.log").read_text(errors="replace")[-7000:])
        proof = json.loads((work/"proof.json").read_text(encoding="utf-8"))
        proof.update(runtime_exit_code=code, elapsed_seconds=round(time.monotonic()-started, 3), ownership=ownership)
    proof["fixture_removed"] = not work.exists()
    return proof


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
