"""Real turn/worker/registry paths with a fake provider and no native I/O."""
import json

import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE


SCENARIOS = r'''
import json
import queue
import shutil
import threading
from types import SimpleNamespace
from aurora_task_continuation import TaskContinuation

shutil.copytree(Path.cwd().parent / "aurora_reference_maps" / "commands", runtime.AURORA_REFERENCE_ROOT / "commands")
runtime.display_message = lambda *a, **k: None
runtime.write_control_panel_state_snapshot = lambda *a, **k: None
runtime.maybe_build_episodic_planning_context = lambda *a, **k: {"used": False}
runtime.maybe_run_game_focus_recovery = lambda *a, **k: None
runtime.pyautogui.position = lambda: SimpleNamespace(x=0, y=0)
runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
runtime.REVIEW_TURN_INTERVAL = runtime.CRITIQUE_TURN_INTERVAL = 0
runtime.MODEL_TRANSPORT = "chat_completions"
runtime.READBACK_SCOPE = "discovery"
runtime.ACTIVE_TEXT_MODEL = runtime.ACTIVE_VISION_MODEL = runtime.ACTIVE_REASONING_MODEL = "gpt-6.1-sol"
runtime.ASSISTANT_POLICY = "task_flow"
runtime.EXECUTION_MODE = "auto"
runtime.CAPTURE_MODE = "request_only"
runtime.TURN_SCHEDULER_MODE = "event"
runtime.TURN_SCHEDULER_HEARTBEAT_SECONDS = runtime.TURN_SCHEDULER_MIN_GAP_SECONDS = 0
runtime.active_command_queue = queue.Queue()
results, errors, recent = queue.Queue(), queue.Queue(), []
context = SimpleNamespace(command_result_queue=results, shared_recent_executed_actions=recent,
                          drawing_output_queue=queue.Queue(), shared_image_history=[], image_history_queue=queue.Queue())
runtime.active_runtime_context = context
runtime.set_agent_running(True)
worker = threading.Thread(target=runtime.command_handler,
    args=(runtime.active_command_queue, results, recent, errors), name="aurora-continuation-commands")
worker.start()
checks, calls = [], []
clock = [100.0]
runtime.TASK_CONTINUATION = TaskContinuation(clock=lambda: clock[0])
reply = ["Ready."]
provider_mode = ["normal"]
unique_init = "INIT_SENTINEL_37: Keep evidence and use explicit command results."

def check(name, condition):
    assert condition, name
    checks.append(name)

def drain():
    deadline = time.monotonic() + 3
    while runtime.active_command_queue.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(.005)
    assert not runtime.active_command_queue.unfinished_tasks, "Command worker timed out"
    runtime.drain_runtime_command_results(context)
    assert errors.empty(), "Command worker failed"

def operator(command):
    runtime.enqueue_or_execute_command(command, is_user=True, source="continuation_fixture")
    drain()
    return recent[-1]

def input_turn(text):
    runtime.get_input_queue_store().put(text)
    result = runtime.maybe_run_due_inference_turn()
    drain()
    return result

def provider(packet, token):
    token.check()
    body = packet["payload"]
    text = json.dumps(body["messages"])
    calls.append({"model": body["model"], "init_occurrences": text.count("INIT_SENTINEL_37"),
                  "correlation": dict(packet.get("correlation") or {}),
                  "worker_delivery_context_present": runtime.current_delivery() is not None,
                  "message_count": len(body["messages"]), "serialized_message_chars": len(text),
                  "wake": runtime.runtime_state.get("last_turn_wake_reason"),
                  "readback_in_context": "Command discovery result" in text,
                  "image_attached": any(isinstance(m.get("content"), list) for m in body["messages"])})
    if provider_mode[0] == "late":
        clock[0] += 200
    if provider_mode[0] == "error":
        return SimpleNamespace(status_code=503, text="fixture unavailable"), "api_key", "guarded fake provider"
    return SimpleNamespace(status_code=200, json=lambda: {
        "model": "fixture-provider", "choices": [{"message": {"content": reply[0]}}]
    }), "api_key", "guarded fake provider"
runtime.perform_model_http_request = provider

proof = {}
try:
    runtime.init_prompt = unique_init
    runtime.initiate_and_handoff()
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    check("legacy turn dispatched", input_turn("Read the fixture Init."))
    check("legacy Init duplicate reproduced", calls[-1]["init_occurrences"] >= 2)
    check("shared registry enables optional path", operator(
        "SET_INIT_DELIVERY(system_once); SET_TASK_MAX_MODEL_TURNS(2); SET_TASK_MAX_SECONDS(120); "
        "SET_TASK_CONTINUATION(bounded); SET_READBACK_WAKE(on)")["success"])
    saved_prompt_modes = (runtime.INIT_PROMPT_PROFILE, runtime.ASSISTANT_POLICY, runtime.DEMAND_CAPTURE_ENABLED)
    try:
        runtime.INIT_PROMPT_PROFILE, runtime.ASSISTANT_POLICY, runtime.DEMAND_CAPTURE_ENABLED = 'current', 'task_flow', True
        check('dynamic prompt explains automatic post-action capture', 'Dynamic observation flow:' in runtime.build_base_system_prompt())
        runtime.DEMAND_CAPTURE_ENABLED = False
        check('disabled demand never promises automatic capture', 'Dynamic observation flow:' not in runtime.build_base_system_prompt())
        runtime.DEMAND_CAPTURE_ENABLED = True
        runtime.ASSISTANT_POLICY = 'legacy'
        check('legacy admission keeps prior prompt path', 'Dynamic observation flow:' not in runtime.build_base_system_prompt())
        runtime.ASSISTANT_POLICY = 'task_flow'
        runtime.INIT_PROMPT_PROFILE = 'legacy'
        check('legacy Init keeps prior prompt path', 'Dynamic observation flow:' not in runtime.build_base_system_prompt())
    finally:
        runtime.INIT_PROMPT_PROFILE, runtime.ASSISTANT_POLICY, runtime.DEMAND_CAPTURE_ENABLED = saved_prompt_modes
    before_generation = runtime.TASK_CONTINUATION.readback()["generation"]
    runtime.enable_unimportant_messages = False
    runtime.publish_command_discovery(False, "REJECTED_READBACK_SENTINEL")
    runtime.enable_unimportant_messages = True
    check("disabled history cannot create an empty readback loop", runtime.TASK_CONTINUATION.readback()["generation"] == before_generation)
    reply[0] = "Executed Commands:\nLOOKUP_COMMAND(REQUEST_SCREENSHOT_CAPTURE,low)"
    check("bounded first turn dispatched", input_turn("Look up the capture command before proceeding."))
    check('network worker receives exact frozen turn and task IDs without ContextVar propagation',
          calls[-1]['correlation']['task_id'] == runtime.TASK_CONTINUATION.snapshot()['task_id']
          and bool(calls[-1]['correlation']['inference_request_id']) and not calls[-1]['worker_delivery_context_present'])
    check("request contains Init exactly once", calls[-1]["init_occurrences"] == 1)
    check("original Init still retained", any(row.get("Exemption") == "Init" for row in runtime.get_chat_history_store()))
    check("readback wake pending", "command_readback" in runtime.evaluate_turn_scheduler()["reasons"])
    check("direct readback follow-up dispatched", runtime.maybe_run_due_inference_turn())
    drain()
    check("follow-up contains readback without an image", calls[-1]["readback_in_context"] and not calls[-1]["image_attached"])
    check("model turn limit stops repeated lookup loop", not runtime.maybe_run_due_inference_turn())
    check("stop reason exported", runtime.build_control_panel_state_snapshot()["continuation"]["active_task"]["stop_reason"] == "turn_limit")
    before = len(calls)
    check("automatic wake does not reset task", not runtime.maybe_run_due_inference_turn() and len(calls) == before)
    reply[0] = "Ready for a new task."
    check("new operator input starts next task", input_turn("New task: wait for my next instruction."))
    check("new task starts at one turn", runtime.TASK_CONTINUATION.snapshot()["turns"] == 1)
    blocked = runtime.execute_registered_setting_command("SET_TASK_MAX_MODEL_TURNS", ["100"], is_user=False)
    check("model cannot enlarge task limits", not blocked["success"] and blocked["effect_status"] == "not_started")
    operator("CANCEL_ACTIVE_WORK()")
    check("cancel stops automatic continuation", not runtime.maybe_run_due_inference_turn())
    check("cancel reason remains visible", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "operator_cancelled")
    provider_mode[0] = "late"
    reply[0] = "Executed Commands:\nUPDATE_CONTEXT(MUST_NOT_APPLY_LATE)"
    input_turn("Test the late-response boundary.")
    check("late response cannot enqueue commands", not any("MUST_NOT_APPLY_LATE" in str(row.get("action", "")) for row in recent))
    check("late response stops task", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "time_limit")
    provider_mode[0] = "error"
    input_turn("Test provider failure.")
    check("provider error stops task without automatic retry", runtime.TASK_CONTINUATION.snapshot()["status"] == "stopped" and not runtime.maybe_run_due_inference_turn())
    provider_mode[0] = "normal"
    reply[0] = "Ready."
    input_turn("Test pause.")
    runtime.RUNTIME_SETTING_LOCKS["live"] = False
    operator("SET_LIVE_MODE(off)")
    runtime.get_input_queue_store().put("Retain queued input while paused")
    check("pause preserves queued input", not runtime.maybe_run_due_inference_turn() and runtime.get_input_queue_store().qsize() == 1)
    check("pause stops bounded task", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "inference_paused")
    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())
    proof = {"status": "passed", "checks": checks, "requests": calls,
             "real_api_calls": 0, "native_input_calls": 0, "real_capture_calls": 0,
             "limits": "Synthetic provider; no gameplay, native frame or DPI qualification. Time limit is an admission boundary."}
finally:
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    worker.join(2)
    assert not worker.is_alive(), "Owned command worker did not stop"
    assert not runtime.MODEL_IO.busy, "Owned model transport did not stop"
Path("proof.json").write_text(json.dumps(dict(proof, owned_threads_stopped=True), indent=2), encoding="utf-8")
'''


if __name__ == "__main__":
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
