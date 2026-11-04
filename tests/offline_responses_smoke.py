"""Full Aurora model-turn path with a fake provider and all native/network I/O guarded."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from offline_panel_smoke import COPY_FILES
from offline_runtime_smoke import CONTRACT_FIXTURE

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + '''
import json
import queue
import threading
from types import SimpleNamespace

startup = {"live": bool(runtime.SEND_TO_MODEL), "model_responses": bool(runtime.ENABLE_MODEL_RESPONSES),
           "transport": runtime.MODEL_TRANSPORT}
runtime.display_message = lambda *args, **kwargs: None
runtime.maybe_build_episodic_planning_context = lambda *args, **kwargs: {"used": False, "reason": "fake-provider proof"}
runtime.maybe_run_game_focus_recovery = lambda *args, **kwargs: None
runtime.active_command_queue = queue.Queue()
results, errors, recent = queue.Queue(), queue.Queue(), []
worker = threading.Thread(target=runtime.command_handler,
    args=(runtime.active_command_queue, results, recent, errors), name="aurora-responses-proof-commands")
runtime.set_agent_running(True)
worker.start()
requests_seen = []

def fake_provider(packet, token):
    token.check()
    assert packet["url"] == "https://api.openai.com/v1/responses"
    body = packet["payload"]
    assert body["model"] == "gpt-6-astra"
    assert body["reasoning"] == {"effort": "low"}
    assert body["truncation"] == "disabled" and body["store"] is True
    updates = [item["reasoning"]["effort"] for item in body["input"] if item.get("type") == "configuration_update"]
    number = len(requests_seen) + 1
    text = "Executed Commands:\\nSET_NEXT_REASONING_EFFORT(high, puzzle)" if number == 1 else "No executable commands."
    requests_seen.append({"model": body["model"], "request_level_effort": body["reasoning"]["effort"],
                          "updates": updates, "previous_response_id": body.get("previous_response_id"),
                          "message_count": len(body["input"]), "max_output_tokens": body["max_output_tokens"]})
    data = {"id": "resp_fixture_" + str(number), "model": body["model"], "status": "completed",
            "reasoning": {"effort": "low"}, "usage": {"input_tokens": 1200 + number, "input_tokens_details": {"cached_tokens": 256}},
            "output": [{"type": "message", "role": "assistant", "status": "completed", "phase": "final_answer",
                        "content": [{"type": "output_text", "text": text}]}]}
    return SimpleNamespace(status_code=200, json=lambda: data), "api_key", "fake provider; no credentials used"

runtime.perform_model_http_request = fake_provider
runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
runtime.EXECUTION_MODE = "assist"
runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
runtime.REVIEW_TURN_INTERVAL = runtime.CRITIQUE_TURN_INTERVAL = 0
runtime.DEFAULT_REASONING_EFFORT = runtime.BATTLE_REASONING_EFFORT = "low"
runtime.ACTIVE_TEXT_MODEL = runtime.ACTIVE_VISION_MODEL = runtime.ACTIVE_REASONING_MODEL = "gpt-6-astra"
runtime.MODEL_TRANSPORT = "responses"
try:
    first = runtime.send_prompt_to_chatgpt("Routine local fake-provider check.")
    assert first, runtime.runtime_state.get("last_response_summary")
    deadline = time.monotonic() + 3
    while runtime.agent_state.next_inference_plan.get("reasoning_effort") != "high" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runtime.agent_state.next_inference_plan.get("reasoning_effort") == "high", {"plan": runtime.agent_state.next_inference_plan, "recent": recent, "parsed": runtime.split_response_sections(first), "policy": runtime.evaluate_assistant_command_policy("SET_NEXT_REASONING_EFFORT(high, puzzle)")}
    second = runtime.send_prompt_to_chatgpt("Solve the local fixture puzzle.")
    assert second, runtime.runtime_state.get("last_response_summary")
    third = runtime.send_prompt_to_chatgpt("Puzzle solved; return to routine decisions.")
    assert third, runtime.runtime_state.get("last_response_summary")
    assert [row["updates"] for row in requests_seen] == [[], ["high"], ["low"]], requests_seen
    assert [row["previous_response_id"] for row in requests_seen] == [None, "resp_fixture_1", "resp_fixture_2"]
    assert runtime.RESPONSES_REASONING.snapshot()["effective_effort"] == "low"
    assert errors.empty()
    assert not Path("forbidden-native-input.txt").exists()
    proof = {"status": "passed", "startup": startup, "requests": requests_seen,
             "model_requested_escalation": True, "command_result_count": len(recent),
             "reasoning_state": runtime.RESPONSES_REASONING.snapshot(),
             "native_capture_network_guards_unused": True, "real_api_calls": 0}
finally:
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    worker.join(2)
    assert not worker.is_alive(), "Owned command worker did not stop"
    assert not runtime.MODEL_IO.busy, "Owned model I/O worker did not stop"
Path("proof.json").write_text(json.dumps(dict(proof, owned_threads_stopped=True), indent=2), encoding="utf-8")
'''


def run_smoke():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=".aurora-responses-smoke-", dir=ROOT) as directory:
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
                code = process.wait(timeout=45)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
        if code != 0:
            raise AssertionError((work/"process.log").read_text(errors="replace")[-6000:])
        proof = json.loads((work/"proof.json").read_text(encoding="utf-8"))
        proof.update(runtime_exit_code=code, elapsed_seconds=round(time.monotonic()-started, 3), ownership=ownership)
    proof["fixture_removed"] = not work.exists()
    return proof


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
