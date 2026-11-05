"""Real parser, command worker, scheduler and model turns with synthetic I/O only."""
import json

import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE


SCENARIOS = r'''
import json
import queue
import threading
from types import SimpleNamespace
from PIL import Image
from aurora_capture_geometry import CaptureTarget, FrameGeometry

runtime.display_message = lambda *a, **k: None
runtime.write_control_panel_state_snapshot = lambda *a, **k: None
runtime.maybe_build_episodic_planning_context = lambda *a, **k: {"used": False}
runtime.maybe_run_game_focus_recovery = lambda *a, **k: None
runtime.pyautogui.position = lambda: SimpleNamespace(x=0, y=0)
runtime.pyautogui.PAUSE = 0
runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
runtime.REVIEW_TURN_INTERVAL = runtime.CRITIQUE_TURN_INTERVAL = 0
runtime.MODEL_TRANSPORT = "chat_completions"
runtime.ACTIVE_TEXT_MODEL = runtime.ACTIVE_VISION_MODEL = runtime.ACTIVE_REASONING_MODEL = "gpt-6.1-sol"
runtime.ASSISTANT_POLICY = "task_flow"
runtime.EXECUTION_MODE = "auto"
runtime.CAPTURE_MODE = "request_only"
runtime.CAPTURE_GEOMETRY_POLICY = "verified"
runtime.TURN_SCHEDULER_MODE = "event"
runtime.TURN_SCHEDULER_HEARTBEAT_SECONDS = 0
runtime.TURN_SCHEDULER_MIN_GAP_SECONDS = 0
runtime.TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS = .02
runtime.DEMAND_CAPTURE_ENABLED = True
runtime.runtime_state["demand_capture_enabled"] = True
runtime.active_command_queue = queue.Queue()
results, errors, recent = queue.Queue(), queue.Queue(), []
context = SimpleNamespace(command_result_queue=results, shared_recent_executed_actions=recent,
                          drawing_output_queue=queue.Queue(), shared_image_history=[], image_history_queue=queue.Queue())
runtime.active_runtime_context = context
runtime.set_agent_running(True)
worker = threading.Thread(target=runtime.command_handler,
    args=(runtime.active_command_queue, results, recent, errors), name="aurora-turn-flow-commands")
worker.start()
events, checks, calls = [], [], []
fail_click = False
hold_entered = threading.Event()

def check(name, condition):
    assert condition, name
    checks.append(name)

def record(name):
    def action(*args, **kwargs):
        events.append([name, list(args), {k: v for k, v in kwargs.items() if k != "_pause"}])
        if name == "click" and fail_click:
            raise RuntimeError("simulated partial click failure")
        if name == "keyDown":
            hold_entered.set()
    return action
for name in ("press", "keyDown", "keyUp", "click", "doubleClick", "mouseDown", "mouseUp", "moveTo"):
    setattr(runtime.pyautogui, name, record(name))
runtime.focus_game_input_target = lambda title: {"success": True, "reason": "synthetic game focus"}
runtime.send_scancode_key_event = record("scancode")

def wait_results():
    deadline = time.monotonic() + 5
    while runtime.active_command_queue.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(.005)
    assert not runtime.active_command_queue.unfinished_tasks, "Command worker timed out"
    assert not results.empty(), "Expected a command receipt"
    check("undrained receipts block inference", not runtime.evaluate_turn_scheduler()["should_run"])
    runtime.drain_runtime_command_results(context)
    assert errors.empty(), "Command worker reported an error"
    return recent[-1]

def operator(command):
    runtime.enqueue_or_execute_command(command, is_user=True, source="flow_fixture")
    return wait_results()

capture_count = 0
def synthetic_capture():
    global capture_count
    deadline = time.monotonic() + 3
    reason = runtime.get_due_demand_capture_reason()
    while not reason and time.monotonic() < deadline:
        time.sleep(.005)
        reason = runtime.get_due_demand_capture_reason()
    assert reason, ("Expected a demand capture", runtime.CAPTURE_SERVICE.snapshot())
    # Exercise production persistence/history/scheduler, with unchanged synthetic pixels.
    stamp = runtime.CAPTURE_SERVICE.finish(runtime.CAPTURE_SERVICE.begin("synthetic_turn_flow"))
    geometry = FrameGeometry((320, 240), (160, 120),
        CaptureTarget("foreground", (-320, -120, 0, 120), (-1920, -120, 1920, 1080), (-320, -120, 0, 120), 12, 34, 144),
        "per_monitor_v2", "verified", "resize_and_later_overlays")
    context.drawing_output_queue.put(runtime.CapturedFrame(Image.new("RGB", (160, 120), "navy"), stamp, "same-fixture-pixels", geometry))
    runtime.drain_runtime_processed_capture(context)
    capture_count += 1
    return runtime.runtime_state["last_screenshot_path"]

replies = [
    "Scene: overworld\nObservation: A clear path in a synthetic room is visible.\nExecuted Commands:\n"
    "GB:hold(right,0.05)\nGB:hold(up,0.05)\nUPDATE_CONTEXT(Advanced along the fixture path)\nREQUEST_SCREENSHOT_CAPTURE(after_batch,0)",
    "Scene: overworld\nObservation: The synthetic path is unchanged.\nExecuted Commands:\nREQUEST_SCREENSHOT_CAPTURE(recheck,0)",
    "Scene: overworld\nObservation: The fixture task is complete.\nExecuted Commands:\nUPDATE_CONTEXT(Fixture task complete; await the operator)",
]
def provider(packet, token):
    token.check()
    body = packet["payload"]
    selected = runtime.runtime_state["last_prompt_diagnostics"]["capture_frame"]
    check("provider diagnostics identify the selected acquisition", selected["provenance"]["frame_id"] == runtime.runtime_state["last_capture_frame"]["provenance"]["frame_id"])
    check("dispatch acknowledges the exact selected counter", selected["counter"] == runtime.runtime_state["turn_scheduler_last_submitted_capture_counter"])
    text = json.dumps(body["messages"])
    check("provider diagnostics carry exact selected geometry", selected["geometry"] == runtime.runtime_state["last_capture_frame"]["geometry"])
    check("provider image text carries frame-specific coordinates", "x=-320+image_x*2" in text and selected["provenance"]["frame_id"] in text)
    check("provider prompt includes init and batch guidance", "Purpose and authority" in text and "2-4 actions" in text)
    check("provider prompt reports gate and cadence", "power-word gate: off" in text and "heartbeat=0s" in text)
    check("provider screenshot prompt avoids old one-action ceiling", "suggest at most one reversible next action" not in text)
    calls.append({"model": body["model"], "message_count": len(body["messages"]),
                  "serialized_message_chars": len(text), "init_occurrences": text.count("Purpose and authority"),
                  "capture_counter_at_start": runtime.runtime_state["turn_scheduler_capture_counter"]})
    assert len(calls) <= len(replies), "Unexpected extra inference"
    return SimpleNamespace(status_code=200, json=lambda: {
        "model": "fixture-provider", "choices": [{"message": {"content": replies[len(calls)-1]}}]
    }), "api_key", "guarded fake provider"
runtime.perform_model_http_request = provider

proof = {}
try:
    check("overlay inspection labels startup geometry as a preset", "startup_desktop=" in runtime.get_keypoint_grid_summary() and "preset" in runtime.get_keypoint_grid_summary())
    check("power word is off by default", runtime.REQUIRE_POWER_WORD is False)
    runtime.init_prompt = Path("aurora2_init.txt").read_text(encoding="utf-8")
    runtime.initiate_and_handoff()  # paused: pin/load without a model call
    check("loaded init is retained as Init exempt", any(row.get("Exemption") == "Init" for row in runtime.get_chat_history_store()))
    check("init survives normal recent-context selection", any(row.get("Exemption") == "Init" for row in runtime.get_recent_prompt_history()))
    check("loaded init is included in every base system prompt", runtime.init_prompt in runtime.build_base_system_prompt())
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True

    command = ('PYAG:click(10,20,left); PYAG:click(30,40,left); PYAG:press(tab,3,0.001); '
               'PYAG:multi_press(down,enter); PYAG:hotkey(ctrl,a); PYAG:type("x,y;z"); '
               'REQUEST_SCREENSHOT_CAPTURE(operator_batch,0)')
    result = operator(command)
    check("multiple mouse and keyboard commands succeed in order", result["success"] and len(result["executed_commands"]) == 7)
    check("mouse coordinates preserve command order", [row[2].get("x") for row in events if row[0] == "click"] == [10,30])
    check("repeat, sequence and quoted typing preserve order", [row[1][0] for row in events if row[0] == "press"] == list(["tab"]*3+["down","enter"])+list("x,y;z"))
    chord = [(row[0], row[1][0]) for row in events if row[0] in {"keyDown", "keyUp"}]
    check("hotkey is a chord with reverse release", chord == [("keyDown","ctrl"),("keyDown","a"),("keyUp","a"),("keyUp","ctrl")])
    check("capture wait blocks inference without a fresh image", not runtime.evaluate_turn_scheduler()["should_run"])
    first_image = synthetic_capture()
    check("requested capture triggers event inference with heartbeat off", runtime.maybe_run_due_inference_turn())
    action_receipt = wait_results()
    check("model emits and executes a multi-action batch", action_receipt["success"] and len(action_receipt["desktop_results"]) == 2)
    check("model batch did not need held proposals", not runtime.get_pending_command_store())
    second_image = synthetic_capture()
    check("unchanged requested image still has a distinct identity", first_image != second_image)
    check("action result immediately continues the task", runtime.maybe_run_due_inference_turn())
    wait_results()
    check("capture-only response retains its new wake request", runtime.runtime_state["turn_scheduler_pending_command_result"])
    synthetic_capture()
    check("capture-only continuation runs without heartbeat", runtime.maybe_run_due_inference_turn())
    wait_results()
    check("memory-only completion does not repeat old input wake", not runtime.evaluate_turn_scheduler()["should_run"] and len(calls) == 3)

    before = len(events)
    try:
        runtime.enqueue_or_execute_command("PYAG:click(1,2,left); PYAG:multi_press(tab,NOT_A_REAL_KEY)", is_user=True)
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed batch unexpectedly accepted")
    check("invalid key rejects complete raw batch before first click", len(events) == before)
    result = operator("PYAG:multi_hold(ctrl,shift); PYAG:multi_release(ctrl,shift); PYAG:doubleclick(12,24,left)")
    check("explicit held-key release and double-click remain supported", result["success"] and len(result["desktop_results"]) == 3)

    before = len(events)
    fail_click = True
    result = operator("PYAG:click(50,60,left); PYAG:press(enter); REQUEST_SCREENSHOT_CAPTURE(must_not_run,0)")
    fail_click = False
    check("failed first action blocks remaining commands", not result["success"] and len(result["blocked_commands"]) == 2)
    check("failed input is not blindly replayed", not any(row[0] == "press" for row in events[before:]))
    check("partial failure requests observation", runtime.runtime_state["turn_scheduler_pending_command_result"])
    runtime.clear_turn_scheduler_command_result_pending()

    before = len(events)
    hold_entered.clear()
    runtime.enqueue_or_execute_command("PYAG:hold(a,5); PYAG:click(70,80,left)", is_user=True, source="flow_cancel")
    assert hold_entered.wait(2), "Hold never started"
    check("running input blocks another inference", not runtime.evaluate_turn_scheduler()["should_run"])
    runtime.cancel_active_work_command([], True)
    result = wait_results()
    check("cancelled batch stops its tail", result["cancelled"] and not any(row[0] == "click" for row in events[before:]))
    check("cancel releases the held key", any(row[0] == "keyUp" and row[1] == ["a"] for row in events[before:]))
    check("cancelled partial input retains an observation request", runtime.runtime_state["turn_scheduler_pending_command_result"])
    result = operator("PYAG:press(tab)")
    check("a fresh batch works after cancellation without replay", result["success"] and len(result["executed_commands"]) == 1)
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    check("pause prevents continuation", not runtime.maybe_run_due_inference_turn())
    # Memory/scancode/key/mouse effects are all fixture records, never native calls.
    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())
    proof = {"status":"passed", "checks":checks, "requests":calls, "synthetic_captures":capture_count,
             "simulated_input_events":len(events), "real_api_calls":0, "native_input_calls":0,
             "real_capture_calls":0, "limits":"Synthetic frames through production persistence; native capture timing/DPI not qualified."}
finally:
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    worker.join(2)
    assert not worker.is_alive(), "Owned command worker did not stop"
    assert not runtime.MODEL_IO.busy, "Owned model transport did not stop"
Path("proof.json").write_text(json.dumps(dict(proof, owned_threads_stopped=True),indent=2),encoding="utf-8")
'''


if __name__ == "__main__":
    harness.COPY_FILES = (*harness.COPY_FILES, "aurora2_init.txt")
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
