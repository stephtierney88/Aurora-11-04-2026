"""Shared controls and durable worker with synthetic production boundaries only."""
import json
from unittest.mock import patch
import offline_task_progress_smoke as progress


SETUP = '''
    from aurora_recording_store import RecordingStore
    from aurora_settings_transactions import build_settings_transaction_request
    from aurora_settings_registry import build_settings_version
    recording_root = Path.cwd() / "execution_recordings"
    check("writer defaults off without storage", runtime.build_execution_recording_snapshot()["mode"] == "off" and not recording_root.exists())
    blocked = runtime.execute_registered_setting_command("SET_EXECUTION_RECORDING", ["boundaries"], is_user=False)
    check("model cannot enable recording", not blocked["success"] and runtime.EXECUTION_RECORDING_MODE == "off")
    runtime.RUNTIME_SETTING_LOCKS["execution"] = True
    blocked = runtime.execute_registered_setting_command("SET_EXECUTION_RECORDING", ["boundaries"], is_user=True)
    check("execution lock rejects recording setting", not blocked["success"] and runtime.EXECUTION_RECORDING_MODE == "off")
    runtime.RUNTIME_SETTING_LOCKS["execution"] = False
    version = build_settings_version(runtime.build_registered_settings_runtime_state())
    request = build_settings_transaction_request("preview", changes={"execution.recording":"boundaries"}, expected_version=version)
    ok, receipt = runtime.execute_settings_transaction_request(request)
    check("preview does not start writer", ok and runtime.EXECUTION_RECORDING_SERVICE is None)
    request = build_settings_transaction_request("apply", changes={"execution.recording":"boundaries"}, expected_version=version)
    ok, applied = runtime.execute_settings_transaction_request(request)
    check("apply records desired mode without immediate disk effects", ok and runtime.EXECUTION_RECORDING_MODE == "boundaries" and not recording_root.exists())
    before_task = runtime.TASK_CONTINUATION.snapshot(include_progress=True)
    runtime.tick_execution_recording()
    check("writer attaches without resetting task", before_task == runtime.TASK_CONTINUATION.snapshot(include_progress=True))
'''

CHECKS = '''
    check("details expose effective mode but compact prompt excludes recording", runtime.build_task_continuation_snapshot()["recording"]["effective_mode"] == "boundaries" and "recording" not in runtime.build_task_continuation_snapshot(include_progress=False))
    try:
        runtime.retry_execution_recording_command([], False)
        raise AssertionError("model retry must be rejected")
    except ValueError:
        checks.append("retry is operator-only")
    check("raw off goes through shared receipt authority", operator("SET_EXECUTION_RECORDING(off)")["success"])
    end = time.monotonic() + 8
    while runtime.build_execution_recording_snapshot()["state"] != "closed" and time.monotonic() < end:
        runtime.tick_execution_recording(); time.sleep(.01)
    recorded = runtime.build_execution_recording_snapshot()
    check("disabled recording closes after durable drain", recorded["state"] == "closed" and recorded["writer_pid"] is None and recorded["feed"]["queued"] == 0)
    entry = RecordingStore(recording_root).sessions()["sessions"][0]
    check("disk manifest includes exact commit count and gaps", entry["closure"] == "closed" and entry["committed_count"] == recorded["committed_records"] and entry["manifest"]["dropped"] == recorded["feed"]["dropped"])
    record = RecordingStore(recording_root).record(entry["manifest"]["session_id"], 1)["record"]
    check("restart inspection reads frozen boundary metadata", record["kind"] in {"task_started", "turn_reserved", "task_stopped"} and "PROGRESS_PRIVATE_NOTE" not in json.dumps(record))
    check("retry command normal no-op remains available", operator("RETRY_EXECUTION_RECORDING()")["success"])
    # A fresh settings transaction can undo the requested mode without deleting history.
    request = build_settings_transaction_request("apply", changes={"execution.recording":"boundaries"}, expected_version=build_settings_version(runtime.build_registered_settings_runtime_state()))
    ok, applied = runtime.execute_settings_transaction_request(request)
    request = build_settings_transaction_request("rollback", rollback_handle=applied["rollback_handle"]["handle_id"], expected_version=applied["after_version"])
    ok, rolled = runtime.execute_settings_transaction_request(request)
    check("rollback restores requested off without removing committed data", ok and runtime.EXECUTION_RECORDING_MODE == "off" and RecordingStore(recording_root).sessions()["sessions"][0]["committed_count"] == entry["committed_count"])
    recording_proof = dict(state=recorded,manifest=entry)
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    base=progress.continuation.SCENARIOS
    assert base.count(marker)==1
    fixture=base.replace(marker, SETUP+progress.SCENARIOS+CHECKS+'\n'+marker)
    fixture=fixture.replace('"requests": calls,','"requests": calls, "recording": recording_proof,')
    fixture=fixture.replace('finally:\n    runtime.SEND_TO_MODEL', 'finally:\n    if runtime.EXECUTION_RECORDING_SERVICE:\n        runtime.EXECUTION_RECORDING_SERVICE.close()\n    runtime.SEND_TO_MODEL')
    harness=progress.continuation.harness
    with patch.object(harness,'FIXTURE',progress.continuation.CONTRACT_IMPORT_GUARD+
                      progress.continuation.CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0]+fixture):
        return harness.run_smoke()


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
