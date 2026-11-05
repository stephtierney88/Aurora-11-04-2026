"""Production capture/draw/publication workers, with guarded synthetic I/O."""
import json

import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_FIXTURE, CONTRACT_IMPORT_GUARD


SCENARIOS = r'''
import json
import queue
import threading
from types import SimpleNamespace
from PIL import Image
from contextlib import contextmanager
from aurora_capture_geometry import CaptureTarget

runtime.screenshot_capture, runtime.drawing_worker = production_capture, production_drawing
runtime.set_agent_running(True)
runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
runtime.CAPTURE_MODE = "request_only"
runtime.CAPTURE_PROVENANCE_POLICY = "verified"
runtime.CAPTURE_REQUEST_TIMEOUT_SECONDS = 0.0
runtime.CAPTURE_REQUEST_MAX_ATTEMPTS = 0
runtime.CAPTURE_GEOMETRY_POLICY = "verified"
runtime.CAPTURE_TARGET = "legacy_options"
@contextmanager
def synthetic_dpi_scope():
    yield "per_monitor_v2"
runtime.capture_geometry.physical_pixel_scope = synthetic_dpi_scope
runtime.capture_geometry.query_cursor_position = lambda: (0, 0)
runtime.capture_geometry.query_capture_target = lambda kind: CaptureTarget(
    kind, (-320, -120, 0, 120), (-1920, -120, 1920, 1080),
    (-320, -120, 0, 120) if kind == "foreground" else (),
    12 if kind == "foreground" else 0, 34 if kind == "foreground" else 0, 144 if kind == "foreground" else 0)

runtime.DEMAND_CAPTURE_ENABLED = True
runtime.runtime_state["demand_capture_enabled"] = True
runtime.SHOW_STATUS_TEXT_OVERLAY = False
runtime.target_width, runtime.target_height = 160, 120
runtime.scaling_factor_x = runtime.scaling_factor_y = 1
runtime.overlay = Image.new("RGBA", (160, 120), (0, 0, 0, 0))
runtime.initialize_overlay = lambda: None
runtime.get_cursor = lambda: (None, None, (0, 0))
runtime.pyautogui.position = lambda: SimpleNamespace(x=0, y=0)
runtime.write_control_panel_state_snapshot = lambda *a, **k: None
runtime.display_message = lambda *a, **k: None
runtime.screenshot_options = {"native_cursor_screenshot": True, "current_window": False, "entire_screen": False}
checks, workers, captures = [], [], []
errors, drawing_input, drawing_output = queue.Queue(), queue.Queue(), queue.Queue()
context = SimpleNamespace(drawing_output_queue=drawing_output, shared_image_history=[], image_history_queue=queue.Queue())
fail_grab = False
fail_grab_count = 0
block_grab = False
entered, release = threading.Event(), threading.Event()

def check(name, condition):
    assert condition, name
    checks.append(name)

def until(predicate, label, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.005)
    check(label, predicate())

def grab(*args, **kwargs):
    global fail_grab, fail_grab_count, block_grab
    captures.append(time.monotonic())
    if fail_grab or fail_grab_count:
        fail_grab = False
        fail_grab_count = max(0, fail_grab_count - 1)
        raise OSError("synthetic acquisition failure")
    if block_grab:
        block_grab = False
        entered.set()
        assert release.wait(3), "bounded fixture acquisition wait"
    bounds = kwargs.get("bbox")
    size = (bounds[2] - bounds[0], bounds[3] - bounds[1]) if bounds else (160, 120)
    return Image.new("RGB", size, "navy")

runtime.ImageGrab.grab = grab

def start(target, *args):
    thread = threading.Thread(target=target, args=args, name="owned-cf1a-" + target.__name__)
    thread.start()
    workers.append(thread)
    return thread

def drain():
    until(lambda: not drawing_output.empty(), "processed frame arrived")
    runtime.drain_runtime_processed_capture(context)

def pending():
    return runtime.CAPTURE_SERVICE.snapshot()["pending"]

try:
    check("runtime import acquired no pixels", not import_capture_calls)
    runtime.request_demand_capture("old", 0)
    old = runtime.acquire_runtime_frame("synthetic_direct")
    check("acquisition does not acknowledge", pending()["generation"] == 1)
    check("reason-only completion cannot acknowledge", not runtime.complete_demand_capture("old"))
    runtime.request_demand_capture("new", 0)
    drawing = start(runtime.drawing_worker, drawing_input, drawing_output, errors)
    drawing_input.put(old)
    drain()
    check("old publication preserves newer demand", pending()["generation"] == 2)
    drawing_input.put(runtime.acquire_runtime_frame("synthetic_direct"))
    drain()
    check("matching publication completes request", not pending())
    published = runtime.runtime_state["last_capture_frame"]
    metadata = json.loads(Path(runtime.get_image_context_sidecar_path(published["path"])).read_text())
    check("sidecar carries exact frame identity", metadata["capture"]["provenance"] == published["provenance"])
    check("sidecar counter matches published counter", metadata["capture"]["scheduler_capture_counter"] == published["counter"])
    check("acquisition precedes persistence", metadata["created_at_epoch"] + .001 >= published["provenance"]["acquired_end_epoch"])
    check("pixels unchanged but requested frame persisted", published["counter"] == 2)
    geometry = published["geometry"]
    check("sidecar carries exact frame geometry", metadata["capture"]["geometry"] == geometry)
    check("capture service carries exact frame geometry", runtime.CAPTURE_SERVICE.snapshot()["latest"]["geometry"] == geometry)
    check("acquired and resized dimensions remain distinct", geometry["acquired_size"] == [320, 240] and geometry["image_size"] == [160, 120])
    check("negative origin and physical transform are recorded", geometry["image_to_desktop"] == {"offset_x": -320, "offset_y": -120, "scale_x": 2.0, "scale_y": 2.0})
    counter = published["counter"]
    drawing_input.put(old)
    time.sleep(.06)
    check("late older frame rejected before drawing", drawing_output.empty() and runtime.runtime_state["turn_scheduler_capture_counter"] == counter)

    # Verified current-window uses the acquired target once; settings changed
    # before drawing cannot replace that frame or relabel its geometry.
    runtime.screenshot_options.update(native_cursor_screenshot=False, current_window=True)
    runtime.request_demand_capture("verified foreground", 0)
    original = runtime.acquire_runtime_frame("synthetic_foreground")
    count = len(captures)
    runtime.CAPTURE_GEOMETRY_POLICY = "legacy"
    runtime.CAPTURE_TARGET = "virtual"
    drawing_input.put(original)
    drain()
    foreground = runtime.runtime_state["last_capture_frame"]
    check("verified current-window has no redundant recapture", len(captures) == count and foreground["provenance"]["frame_id"] == original.stamp.frame_id)
    check("frame target survives a settings change before drawing", foreground["geometry"]["target"]["kind"] == "foreground" and foreground["geometry"]["target"]["hwnd"] == 12)
    runtime.CAPTURE_TARGET = "legacy_options"

    # Explicitly label the legacy current_window branch's replacement capture.
    runtime.screenshot_options.update(native_cursor_screenshot=False, current_window=True)
    runtime.request_demand_capture("replacement", 0)
    original = runtime.acquire_runtime_frame("synthetic_direct")
    drawing_input.put(original)
    drain()
    replacement = runtime.runtime_state["last_capture_frame"]["provenance"]
    check("drawing recapture gets a new identity", replacement["frame_id"] != original.stamp.frame_id)
    check("replacement provenance links earlier frame", replacement["replaces_frame_id"] == original.stamp.frame_id)
    check("replacement source remains honest", replacement["source"] == "drawing_current_window_recapture")
    check("legacy geometry stays explicitly unknown", runtime.runtime_state["last_capture_frame"]["geometry"]["status"] == "unknown")
    runtime.screenshot_options.update(native_cursor_screenshot=True, current_window=False)
    runtime.CAPTURE_GEOMETRY_POLICY = "verified"

    # Production request-only worker: no periodic pixels, then bounded failure retry.
    capture = start(runtime.screenshot_capture, drawing_input, errors)
    count = len(captures)
    time.sleep(.08)
    check("request-only idle takes no screenshots", len(captures) == count)
    fail_grab = True
    runtime.request_demand_capture("fail and recover", 0)
    until(lambda: runtime.CAPTURE_SERVICE.snapshot()["failure_count"] == 1, "acquisition failure recorded")
    check("failed acquisition remains pending", bool(pending()))
    drain()
    check("capture retry published and completed", not pending())
    check("failure retry is bounded", captures[-1] - captures[-2] >= .45)

    # Actual drawing exception, no false completion; restart only owned worker.
    real_scale = runtime.scale_resolution
    runtime.scale_resolution = lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic drawing failure"))
    runtime.request_demand_capture("draw retry", 0)
    until(lambda: not drawing.is_alive(), "failed drawing worker stopped")
    check("drawing failure remains pending", bool(pending()))
    check("drawing failure reported", errors.get(timeout=1)[0] == "drawing_worker")
    runtime.scale_resolution = real_scale
    drawing.join(1)
    drawing = start(runtime.drawing_worker, drawing_input, drawing_output, errors)
    drain()
    check("drawing recovery completes request", not pending())

    # Pixel and sidecar failures do not advance a request or its visible counter.
    for stage in ("pixels", "metadata", "metadata_exception"):
        runtime.request_demand_capture("persist " + stage, 0)
        until(lambda: not drawing_output.empty(), "frame ready before " + stage + " failure")
        before = runtime.runtime_state["turn_scheduler_capture_counter"]
        original_save, original_sidecar = runtime.save_capture, runtime.write_image_context_sidecar
        before_pngs = set(Path(runtime.logging_folder).glob("*.png"))
        if stage == "pixels":
            runtime.save_capture = lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic disk failure"))
        elif stage == "metadata_exception":
            runtime.write_image_context_sidecar = lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic metadata directory failure"))
        else:
            runtime.write_image_context_sidecar = lambda *a, **k: ""
        try:
            runtime.drain_runtime_processed_capture(context)
        finally:
            runtime.save_capture, runtime.write_image_context_sidecar = original_save, original_sidecar
        check(stage + " failure retains pending request", bool(pending()))
        check(stage + " failure does not publish counter", runtime.runtime_state["turn_scheduler_capture_counter"] == before)
        check(stage + " failure leaves no new orphan pixels", set(Path(runtime.logging_folder).glob("*.png")) == before_pngs)
        drain()
        check(stage + " recovery completes request", not pending())

    # Cancel while acquisition is physically in flight. Its late pixels must
    # not reach publication; a new request can still recover afterward.
    block_grab = True
    runtime.request_demand_capture("cancel inflight", 0)
    check("capture entered controlled in-flight wait", entered.wait(2))
    before = runtime.runtime_state["turn_scheduler_capture_counter"]
    result = runtime.cancel_active_work_command([], True)
    check("operator cancellation succeeds", result["success"])
    release.set()
    time.sleep(.08)
    runtime.drain_runtime_processed_capture(context)
    check("cancelled acquisition cannot publish", runtime.runtime_state["turn_scheduler_capture_counter"] == before)
    check("cancel clears demand explicitly", not pending())
    runtime.request_demand_capture("after cancellation", 0)
    drain()
    check("new request recovers after cancellation", not pending())
    check("no unexpected worker errors", errors.empty())
    check("no native input or network used", not Path("forbidden-native-input.txt").exists())
finally:
    release.set()
    runtime.set_agent_running(False)
    for worker in workers:
        worker.join(2)
    assert all(not worker.is_alive() for worker in workers), "owned capture/drawing thread leak"

proof = {"status": "passed", "checks": checks, "check_count": len(checks),
         "synthetic_acquisitions": len(captures), "owned_workers_joined": len(workers),
         "real_native_captures": 0, "real_api_calls": 0,
         "capture_service": runtime.CAPTURE_SERVICE.snapshot(),
         "limits": "Synthetic pixels/Win32 geometry/cursor only; native mixed-DPI, occlusion, backend input calibration and interruption acceptance remain unqualified."}
# Never retain fixture absolute paths or PNGs in the repository evidence.
proof["capture_service"]["latest"].pop("path", None)
Path("proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
'''


def run_smoke(additional_scenarios=""):
    original = harness.FIXTURE
    try:
        fixture = CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0]
        fixture = fixture.replace("runtime.screenshot_capture = idle_worker",
                                  "production_capture, production_drawing = runtime.screenshot_capture, runtime.drawing_worker\nruntime.screenshot_capture = idle_worker")
        scenarios = SCENARIOS.replace('    check("no unexpected worker errors", errors.empty())',
                                      additional_scenarios + '\n    check("no unexpected worker errors", errors.empty())')
        harness.FIXTURE = CONTRACT_IMPORT_GUARD + fixture + scenarios
        return harness.run_smoke()
    finally:
        harness.FIXTURE = original


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
