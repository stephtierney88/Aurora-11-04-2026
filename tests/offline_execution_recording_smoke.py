"""Production scheduler/worker boundary feed with fake provider and synthetic capture."""
import json
from unittest.mock import patch
import offline_task_progress_smoke as progress


SETUP = '''
    check("normal controller recording defaults off", not runtime.TASK_CONTINUATION.recording_status()["enabled"])
    runtime.TASK_CONTINUATION = TaskContinuation(clock=lambda: clock[0], recording_capacity=16)
'''
CHECKS = '''
    recording = runtime.TASK_CONTINUATION.peek_recording(limit=16)
    points = recording["records"]
    kinds = [point["kind"] for point in points]
    check("production boundaries include preparation final accounting receipt and exact frame", {"task_started", "request_prepared", "request_finalized", "command_receipt", "frame_observed", "task_stopped"} <= set(kinds))
    check("one controller session owns strict sequence order", len({point["session_id"] for point in points}) == 1 and [point["sequence"] for point in points] == sorted({point["sequence"] for point in points}))
    prepared = next(point for point in points if point["kind"] == "request_prepared")
    finalized = next(point for point in points if point["kind"] == "request_finalized" and point["identity"] == prepared["identity"])
    before_row = next(row for row in prepared["inspection"]["collections"]["requests"] if row["inference_request_id"] == prepared["identity"])
    final_row = next(row for row in finalized["inspection"]["collections"]["requests"] if row["inference_request_id"] == finalized["identity"])
    check("prepared snapshot does not gain later response fields", before_row["phase"] == "prepared" and "reported_usage" not in before_row)
    check("final accounting retains actual provider model and explicit unknown usage", final_row["provider_model"] == "fixture-provider" and final_row["reported_usage"]["total_tokens"] is None)
    observed = next(point for point in points if point["kind"] == "frame_observed")
    check("frame boundary captures exact accepted synthetic frame", observed["identity"] == stamp.frame_id and any(row.get("frame_id") == stamp.frame_id for row in observed["inspection"]["collections"]["commands"]))
    check("recording contains metadata not prompts paths or pixels", "PROGRESS_PRIVATE_NOTE" not in json.dumps(points) and '"path"' not in json.dumps(points) and "base64" not in json.dumps(points))
    check("recording is not silently added to model prompts", "aurora_execution_boundary_v1" not in runtime.build_base_system_prompt())
    check("small buffer exposes pressure without evicting first point", recording["status"]["dropped"] > 0 and recording["status"]["gaps"] and points[0]["sequence"] == 1)
    close = runtime.TASK_CONTINUATION.close_recording()
    before = runtime.TASK_CONTINUATION.snapshot(include_progress=True)
    ack = runtime.TASK_CONTINUATION.acknowledge_recording(close["session_id"], [point["sequence"] for point in points])
    check("closed feed remains drainable without changing task state", ack["status"] == "acknowledged" and not runtime.TASK_CONTINUATION.peek_recording()["records"] and runtime.TASK_CONTINUATION.snapshot(include_progress=True) == before)
    check("in memory acknowledgement never claims durability", not runtime.TASK_CONTINUATION.recording_status()["durable"])
    recording_proof = dict(status=runtime.TASK_CONTINUATION.recording_status(),
        boundaries=[{key: point[key] for key in ("session_id", "sequence", "kind", "identity", "task_id", "task_event_sequence")} for point in points])
'''


def run_smoke():
    scenarios = SETUP + progress.SCENARIOS + CHECKS
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    base = progress.continuation.SCENARIOS
    assert base.count(marker) == 1
    fixture = base.replace(marker, scenarios + '\n' + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "recording": recording_proof,')
    harness = progress.continuation.harness
    with patch.object(harness, 'FIXTURE', progress.continuation.CONTRACT_IMPORT_GUARD +
                      progress.continuation.CONTRACT_FIXTURE.rsplit('runtime.main()', 1)[0] + fixture):
        return harness.run_smoke()


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
