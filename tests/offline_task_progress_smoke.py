"""Real command/capture publication/request joins with synthetic pixels/provider."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    import copy
    from PIL import Image
    runtime.get_input_queue_store().get_nowait()
    operator("SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(20); SET_TASK_MAX_SECONDS(120); SET_READBACK_SCOPE(reviewed)")
    runtime.DEMAND_CAPTURE_ENABLED = True
    runtime.runtime_state["demand_capture_enabled"] = True
    runtime.CAPTURE_PROVENANCE_POLICY = "verified"
    reply[0] = "Executed Commands:\nUPDATE_NOTES(PROGRESS_PRIVATE_NOTE)\nREQUEST_SCREENSHOT_CAPTURE(progress_fixture,0)"
    check("assistant batch enters actual worker", input_turn("Store a fixture note then request fresh observation."))
    task_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    full = runtime.build_task_continuation_snapshot()["active_task"]["progress"]
    command = full["commands"][-1]
    check("admission receipt and request correlation are present", command["origin_request_id"] and command["receipt_id"] and command["binding_count"] == 2 and command["latency_ms"]["admission_to_receipt"] is not None)
    check("capture request binds exact batch without physical input", command["observation_generation"] > 0 and command["required_request_generation"] == runtime.CAPTURE_SERVICE.generation)
    check("pending visual boundary still blocks followup", not runtime.maybe_run_due_inference_turn())
    check("no guessed frame or observed effect", "frame_id" not in command and command["latency_ms"]["receipt_to_frame_observed"] is None)

    stamp = runtime.CAPTURE_SERVICE.begin("synthetic_progress", allow_demand=True, require_demand=True)
    check("synthetic acquisition belongs to pending generation", stamp is not None and stamp.request_generation == command["required_request_generation"])
    stamp = runtime.CAPTURE_SERVICE.finish(stamp)
    clock[0] += 2
    published = runtime.persist_runtime_capture(Image.new("RGB", (32, 24), (20, 40, 60)), "fixture-progress", "test", stamp=stamp)
    check("normal publication path accepts synthetic frame", bool(published))
    frame = copy.deepcopy(runtime.runtime_state["last_capture_frame"])
    command = runtime.TASK_CONTINUATION.snapshot(include_progress=True)["progress"]["commands"][-1]
    check("frame observed links exact generation and identity", command["frame_id"] == stamp.frame_id and command["capture_request_generation"] == stamp.request_generation and command["latency_ms"]["observation_wait"] == 2000)
    clock[0] += 1
    reply[0] = "The exact frame and receipt are available for this fixture."
    check("existing event continuation still dispatches", runtime.maybe_run_due_inference_turn())
    drain()
    progress = runtime.TASK_CONTINUATION.snapshot(include_progress=True)["progress"]
    command, request = progress["commands"][-1], progress["requests"][-1]
    check("selected frame and readback join same command", command["command_batch_id"] in request["frame_batch_ids"] and command["command_batch_id"] in request["readback_batch_ids"] and request["frame_id"] == stamp.frame_id)
    check("local observation timing uses controller clock", command["latency_ms"]["frame_observed_to_request_prepared"] == 1000 and command["latency_ms"]["receipt_to_readback_prepared"] == 3000)
    check("request phases report actual local submission and response", request["phase"] == "responded" and {"preparing", "prepared", "submitted", "responded"} <= set(request["phase_times"]) and request["latency_ms"]["submitted_to_response"] is not None)
    check("diagnostics are not task success or another wake", runtime.TASK_CONTINUATION.snapshot()["status"] == "running" and not runtime.maybe_run_due_inference_turn())
    check("task progress retains no private text paths or pixels", "PROGRESS_PRIVATE_NOTE" not in json.dumps(progress) and "path" not in json.dumps(progress) and "base64" not in json.dumps(progress))
    check("prompt uses compact progress only", '"events":' not in runtime.build_base_system_prompt() and '"commands":' not in json.dumps(runtime.build_task_continuation_snapshot(include_progress=False)["active_task"]["progress"]))
    progress_proof = copy.deepcopy(progress)

    bad_frame = dict(frame, path="different-fixture-file.png")
    check("mismatched metadata does not prevent normal model call", bool(runtime.send_prompt_to_chatgpt("Inspect a synthetic image with unknown identity.", image_path=published[0], image_timestamp=published[1], capture_frame=bad_frame)))
    mismatch = runtime.TASK_CONTINUATION.snapshot(include_progress=True)["progress"]["requests"][-1]
    check("mismatched image path cannot claim another frame identity", mismatch["frame_id"] == "" and mismatch["frame_batch_ids"] == [])

    provider_mode[0] = "error"
    input_turn("Exercise a failed request after observation.")
    failed = runtime.TASK_CONTINUATION.snapshot(include_progress=True)["progress"]["requests"][-1]
    check("failure timing is separate from response timing", failed["phase"] == "failed" and failed["latency_ms"]["submitted_to_terminal"] is not None and failed["latency_ms"]["submitted_to_response"] is None)
    provider_mode[0] = "normal"
    reply[0] = "Start the next task."
    input_turn("New operator task after inspecting the failure.")
    reset = runtime.TASK_CONTINUATION.snapshot(include_progress=True)
    check("new task cannot inherit old batch telemetry", reset["task_id"] != task_id and not reset["progress"]["commands"])
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + "\n" + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "progress": progress_proof,')
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
