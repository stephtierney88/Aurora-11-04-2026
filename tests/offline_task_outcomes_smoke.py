"""Opt-in outcomes through real parsing/admission/receipts, with guarded fake I/O."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    import copy
    runtime.get_input_queue_store().get_nowait()
    operator("SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(12); SET_TASK_MAX_SECONDS(120); SET_READBACK_SCOPE(reviewed)")
    captured_receipts = []
    base_ingest = runtime.ingest_command_result
    def collect_receipt(row, *args, **kwargs):
        captured_receipts.append(copy.deepcopy(row))
        return base_ingest(row, *args, **kwargs)
    runtime.ingest_command_result = collect_receipt

    def direct(command):
        submission = runtime.enqueue_or_execute_command(command, is_user=True, source="task_outcome_fixture")
        drain()
        return submission

    inspected = direct("SHOW_TASK_STATUS()")
    check("task inspection executes in controller despite active worker queue", inspected["submission_status"] == "completed")
    check("inspection has typed observed state", inspected["execution_result"]["task_control_results"][0]["effect_status"] == "observed")
    reply[0] = "Ready."
    check("start disabled-outcome bounded task", input_turn("Start without outcome reporting."))
    disabled_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    denied = direct(f"REPORT_TASK_OUTCOME({disabled_id}, done, not enabled)")
    check("legacy default rejects outcome without stopping task", denied["submission_status"] == "failed" and runtime.TASK_CONTINUATION.snapshot()["status"] == "running")
    check("model cannot enable reporting itself", not runtime.execute_registered_setting_command("SET_TASK_OUTCOME_REPORTING", ["on"], is_user=False)["success"])
    operator("SET_TASK_OUTCOME_REPORTING(on)")
    check("setting is next-task only", runtime.TASK_OUTCOME_REPORTING and not runtime.TASK_CONTINUATION.snapshot()["outcome_reporting"])
    operator("CANCEL_ACTIVE_WORK()")

    outcome_mode = ["done"]
    base_provider = provider
    initial_goals = None
    pending_before = None
    focus_calls = []
    runtime.maybe_run_game_focus_recovery = lambda *args: focus_calls.append(True)
    runtime.EXECUTION_MODE = "assist"
    def outcome_provider(packet, token):
        global initial_goals, pending_before
        text = json.dumps(packet["payload"]["messages"])
        task_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
        check("prompt advertises exact task ID and standalone semantics " + outcome_mode[0], task_id in text and "REPORT_TASK_OUTCOME" in text and "does not prove success" in text)
        if outcome_mode[0] == "done":
            check("queue next-turn effort while current response is in flight", runtime.handle_commands("SET_NEXT_REASONING_EFFORT(high, retained after outcome)", True)["success"])
            check("create real goal for non-completion check", runtime.handle_commands("ADD_GOAL(OUTCOME_FIXTURE_GOAL,2,3)", True)["success"])
            runtime.hierarchical_tasks[:] = [[{"command": "UPDATE_CONTEXT(OUTCOME_MUST_NOT_RUN_IMMEDIATE)"}]]
            runtime.queue_pending_model_command("UPDATE_NOTES(OUTCOME_MUST_NOT_APPROVE)", source="outcome_fixture")
            pending_before = copy.deepcopy(runtime.get_pending_command_snapshot())
            initial_goals = runtime.encode_goals(runtime.agent_state.tasks_list)
        reply[0] = f'Executed Commands:\nREPORT_TASK_OUTCOME({task_id}, {outcome_mode[0]}, "Fixture observation, declared only")'
        return base_provider(packet, token)
    def checked_provider(packet, token):
        try:
            return outcome_provider(packet, token)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    runtime.perform_model_http_request = checked_provider
    outcome_records = []
    for value in ("done", "wait", "approval", "error"):
        runtime.EXECUTION_MODE = "auto" if value in {"done", "approval"} else "assist"
        outcome_mode[0] = value
        check("model reports " + value, input_turn("Start a bounded fixture task and report " + value))
        task = runtime.TASK_CONTINUATION.snapshot()
        report = task.get("reported_outcome") or {}
        check("reported stop is not a cancelled provider turn " + value, task["stop_reason"] == "reported_" + value and runtime.runtime_state["last_model_turn_status"] == "success")
        check("trusted model and originating request retained " + value, report.get("actor") == "model:gpt-6.1-sol" and bool(report.get("origin_inference_request_id")) and report.get("verification") == "reported_not_verified")
        receipt = next(row for row in reversed(captured_receipts) if row.get("task_control_results") and row["task_control_results"][0]["command"] == "REPORT_TASK_OUTCOME")
        check("controller receipt correlation agrees " + value, receipt["task_id"] == task["task_id"] and receipt["inference_request_id"] == report["origin_inference_request_id"] and receipt["success"])
        count = len(calls)
        runtime.TASK_CONTINUATION.publish_readback("still pending after outcome")
        check("readbacks cannot restart reported task " + value, not runtime.maybe_run_due_inference_turn() and len(calls) == count)
        check("automatic pending execution stays stopped " + value, runtime.auto_execute_pending_commands() == [])
        check("reported response does not run focus recovery " + value, not focus_calls)
        outcome_records.append(report)
        if value == "done":
            check("outcome preserves next-turn plan", runtime.agent_state.next_inference_plan["reasoning_effort"] == "high")
            check("outcome does not complete goals or approve pending work", runtime.encode_goals(runtime.agent_state.tasks_list) == initial_goals and runtime.get_pending_command_snapshot() == pending_before)
            check("immediate actions are retained but not executed", runtime.hierarchical_tasks[0][0]["command"] == "UPDATE_CONTEXT(OUTCOME_MUST_NOT_RUN_IMMEDIATE)" and not any("OUTCOME_MUST_NOT_RUN_IMMEDIATE" in row.get("action", "") for row in captured_receipts))
            direct("CLEAR_NEXT_INFERENCE()")
            runtime.hierarchical_tasks[0] = []
            direct("CLEAR_PENDING()")
        rejected = runtime.enqueue_or_execute_command("UPDATE_CONTEXT(OUTCOME_MUST_NOT_ADMIT)", is_user=False)
        check("new automatic admission blocked " + value, rejected["submission_status"] == "failed" and not rejected["execution_result"]["executed_commands"])
        late_route = runtime.route_assistant_commands("UPDATE_NOTES(OUTCOME_MUST_NOT_HOLD)")
        check("stopped task cannot add automatic pending proposals " + value, late_route["rejected_count"] == 1 and not late_route["held_commands"])

    runtime.perform_model_http_request = base_provider
    runtime.maybe_run_game_focus_recovery = lambda *args: None
    reply[0] = "Ready for validation."
    input_turn("Start a new task for rejected reports.")
    live_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    before = len(captured_receipts)
    mixed = f'UPDATE_CONTEXT(OUTCOME_MUST_NOT_MIX); REPORT_TASK_OUTCOME({live_id}, done, "mixed")'
    mixed_result = runtime.route_assistant_commands(mixed)
    check("mixed model batch rejected before effects", mixed_result["rejected_count"] == 1 and len(captured_receipts) == before and runtime.TASK_CONTINUATION.snapshot()["status"] == "running")
    for wrapper in (f'PENDING(REPORT_TASK_OUTCOME({live_id}, done, "wrapped"))',
                    f'PENDING(PENDING(SHOW_TASK_STATUS()))',
                    f'UPDATE_NOTES(OUTCOME_MUST_NOT_PRECEDE_WRAPPER); PENDING(REPORT_TASK_OUTCOME({live_id}, done, "wrapped mixed"))'):
        pending = copy.deepcopy(runtime.get_pending_command_snapshot())
        routed = runtime.route_assistant_commands(wrapper)
        check("assistant router rejects delayed control before effects " + wrapper.split("(", 1)[0],
              routed["rejected_count"] == 1 and len(captured_receipts) == before and runtime.get_pending_command_snapshot() == pending)
    for command in (mixed, f'PENDING(REPORT_TASK_OUTCOME({live_id}, done, "wrapped"))', f'REPORT_TASK_OUTCOME({live_id}, success, "bad enum")'):
        try:
            runtime.prepare_command_batch(command)
        except (ValueError, runtime.CommandSyntaxError):
            pass
        else:
            raise AssertionError("Invalid task control passed admission: " + command)
    check("mixed/wrapped/malformed controls fail admission", True)
    stale = direct(f'REPORT_TASK_OUTCOME({outcome_records[-1]["task_id"]}, done, stale)')
    check("old task cannot stop current task", stale["submission_status"] == "failed" and runtime.TASK_CONTINUATION.snapshot()["status"] == "running")
    detached = runtime.handle_commands(f"REPORT_TASK_OUTCOME({live_id}, done, no origin)", False)
    check("unattributed model report is rejected", not detached["success"])
    admitted_command = "WAIT(0.05); UPDATE_NOTES(OUTCOME_ADMITTED_WORK_CAN_FINISH)"
    admitted = runtime.enqueue_or_execute_command(admitted_command, is_user=False, source="pre_outcome_fixture")
    check("earlier work admitted before report", admitted["submission_status"] == "queued")
    accepted = direct(f'REPORT_TASK_OUTCOME({live_id}, wait, "Operator waits for evidence")')
    check("report does not falsely cancel admitted work", any(row.get("action") == admitted_command and row.get("success") for row in captured_receipts))
    duplicate = direct(f'REPORT_TASK_OUTCOME({live_id}, wait, "Operator waits for evidence")')
    conflict = direct(f'REPORT_TASK_OUTCOME({live_id}, done, "conflicting report")')
    check("operator reports are idempotent and immutable", accepted["submission_status"] == duplicate["submission_status"] == "completed" and duplicate["execution_result"]["task_control_results"][0]["effect_status"] == "unchanged" and conflict["submission_status"] == "failed")
    input_turn("Start and cancel another task.")
    cancelled_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    direct("CANCEL_ACTIVE_WORK()")
    cancelled = direct(f"REPORT_TASK_OUTCOME({cancelled_id}, done, too late)")
    check("cancel cannot be relabelled as done", cancelled["submission_status"] == "failed" and runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "operator_cancelled")
    operator("SET_TASK_CONTINUATION(legacy)")
    check("legacy mode retains normal model dispatch", input_turn("Legacy mode is still usable."))
    legacy = direct(f"REPORT_TASK_OUTCOME({cancelled_id}, done, legacy)")
    check("legacy mode never accepts outcome mutation", legacy["submission_status"] == "failed")
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + "\n" + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "outcome_reports": outcome_records,')
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
