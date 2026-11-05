"""Extend the guarded production-worker fixture with request/worker deadlines."""
import json
import offline_capture_provenance_smoke as capture


SCENARIOS = r'''
    # Fail exactly the permitted acquisitions; no new worker or implicit retry.
    runtime.set_capture_request_timeout(5)
    runtime.set_capture_request_attempts(2)
    fail_grab_count = 10
    attempts_before = len(captures)
    runtime.request_screenshot_capture_command(["attempt budget", "0"], True)
    until(lambda: runtime.CAPTURE_SERVICE.snapshot()["current_failure"], "attempt budget reached a terminal outcome")
    failure = runtime.mirror_capture_service_state()["current_failure"]
    check("attempt exhaustion names the failed request", failure["code"] == "attempts_exhausted" and failure["attempts"] == 2)
    time.sleep(.65)
    check("request-only capture stops retrying after exhaustion", len(captures) == attempts_before + 2)
    check("queue readback exposes capture failure", "capture request failed" in runtime.build_queue_next_action_runtime_cue())
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    decision = runtime.evaluate_turn_scheduler()
    check("failed observation cannot trigger a model turn", not decision["should_run"] and "attempts_exhausted" in decision["detail"])
    interruption = runtime.evaluate_turn_scheduler(input_pending=True)
    check("operator text can interrupt without attaching stale pixels", interruption["should_run"] and interruption["omit_capture"])
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    fail_grab_count = 0
    runtime.set_capture_request_timeout(0)
    runtime.set_capture_request_attempts(0)
    runtime.request_screenshot_capture_command(["explicit budget retry", "0"], True)
    drain()
    check("explicit retry completes and clears active failure", not pending() and not runtime.mirror_capture_service_state()["current_failure"])

    # Main-thread observation expires a request even while its native substitute
    # is blocked. It cannot kill that call and must not create a duplicate worker.
    entered.clear()
    release.clear()
    block_grab = True
    runtime.set_capture_request_timeout(.15)
    runtime.request_screenshot_capture_command(["deadline during acquisition", "0"], True)
    check("deadline fixture reached native substitute", entered.wait(2))
    runtime.set_capture_request_timeout(0)
    before = runtime.runtime_state["turn_scheduler_capture_counter"]
    time.sleep(.2)
    status = runtime.mirror_capture_service_state()
    check("deadline is latched despite settings change", status["current_failure"]["code"] == "deadline_exceeded" and status["current_failure"]["timeout_seconds"] == .15)
    check("stuck call remains visible and is not claimed cancelled", len(status["acquisitions_inflight"]) == 1 and status["acquisitions_inflight"][0]["status"] == "discard_on_return" and not status["current_failure"]["native_call_cancelled"])
    monitor_context = SimpleNamespace(restart_counts={}, error_queue=queue.Queue())
    observed_worker = SimpleNamespace(pid=None, is_alive=capture.is_alive)
    processes = {"screenshot": observed_worker}
    runtime.monitor_and_restart_processes(processes, monitor_context)
    check("monitor does not duplicate a live blocked capture worker", processes["screenshot"] is observed_worker and not monitor_context.restart_counts)
    release.set()
    until(lambda: not runtime.CAPTURE_SERVICE.snapshot()["acquisitions_inflight"], "late native substitute returned")
    time.sleep(.05)
    runtime.drain_runtime_processed_capture(context)
    check("late acquired pixels cannot publish after timeout", runtime.runtime_state["turn_scheduler_capture_counter"] == before)
    runtime.request_screenshot_capture_command(["after timeout", "0"], True)
    drain()
    check("new request recovers after the old call returns", not pending())

    # Expiry during sidecar I/O must not publish a counter or orphan image.
    runtime.set_capture_request_timeout(.5)
    runtime.request_screenshot_capture_command(["deadline during publication", "0"], True)
    until(lambda: not drawing_output.empty(), "frame ready for slow publication")
    original_sidecar = runtime.write_image_context_sidecar
    def slow_sidecar(*args, **kwargs):
        time.sleep(.6)
        return original_sidecar(*args, **kwargs)
    before = runtime.runtime_state["turn_scheduler_capture_counter"]
    before_pngs = set(Path(runtime.logging_folder).glob("*.png"))
    before_sidecars = set(Path(runtime.logging_folder).glob("*.json"))
    runtime.write_image_context_sidecar = slow_sidecar
    try:
        runtime.drain_runtime_processed_capture(context)
    finally:
        runtime.write_image_context_sidecar = original_sidecar
    check("publication deadline leaves scheduler counter unchanged", runtime.runtime_state["turn_scheduler_capture_counter"] == before)
    check("expired publication removes its own pixel and sidecar files", set(Path(runtime.logging_folder).glob("*.png")) == before_pngs and set(Path(runtime.logging_folder).glob("*.json")) == before_sidecars)
    check("publication timeout is explicit", runtime.mirror_capture_service_state()["current_failure"]["code"] == "deadline_exceeded")
    runtime.set_capture_request_timeout(0)
    runtime.request_screenshot_capture_command(["after publication timeout", "0"], True)
    drain()
    check("publication timeout retry recovers", not pending())

    # A worker that returns after a controller reinitialization belongs to the
    # old service. It must exit rather than start capturing for the new runtime.
    entered.clear()
    release.clear()
    block_grab = True
    runtime.request_demand_capture("old controller", 0)
    check("old-controller capture entered substitute", entered.wait(2))
    old_service = runtime.CAPTURE_SERVICE
    runtime.CAPTURE_SERVICE = runtime.CaptureService()
    release.set()
    capture.join(2)
    drawing.join(2)
    check("old capture and drawing workers exit after service replacement", not capture.is_alive() and not drawing.is_alive())
    check("old workers did not acquire or publish into new controller", runtime.CAPTURE_SERVICE.sequence == 0 and not runtime.CAPTURE_SERVICE.snapshot()["latest"])
    check("old controller retains no active acquisition", not old_service.snapshot()["acquisitions_inflight"])
    runtime.CAPTURE_SERVICE = old_service  # retain this fixture's evidence for proof/cleanup
'''


def run_smoke():
    return capture.run_smoke(SCENARIOS)


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
