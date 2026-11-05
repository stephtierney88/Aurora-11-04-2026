"""Optional budgets through real routing/workers with fake providers and native guards."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    import copy
    import os
    from aurora_task_continuation import command_task_scope
    from aurora_pending_commands import PENDING_COMMANDS
    runtime.get_input_queue_store().get_nowait()
    operator("SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(30); SET_TASK_MAX_SECONDS(120); SET_READBACK_SCOPE(reviewed)")
    captured_receipts, budget_snapshots = [], []
    base_ingest = runtime.ingest_command_result
    def collect_receipt(row, *args, **kwargs):
        captured_receipts.append(copy.deepcopy(row))
        return base_ingest(row, *args, **kwargs)
    runtime.ingest_command_result = collect_receipt
    def direct(command, is_user=True):
        result = runtime.enqueue_or_execute_command(command, is_user=is_user, source="task_budget_fixture")
        drain()
        return result
    def start(command_limit=0, token_limit=0, unknown="continue", response="Ready for this bounded task."):
        direct("CANCEL_ACTIVE_WORK()")
        direct(f"SET_TASK_MAX_COMMANDS({command_limit}); SET_TASK_MAX_REPORTED_TOKENS({token_limit}); SET_TASK_UNKNOWN_USAGE_POLICY({unknown})")
        reply[0] = response
        check("new operator task starts", input_turn("Start a separate budget test."))
        return runtime.TASK_CONTINUATION.snapshot()["task_id"]
    def executed(sentinel):
        return any(sentinel in str(command) and runtime.get_command_name(str(command)).upper() not in PENDING_COMMANDS
                   for row in captured_receipts for command in row.get("executed_commands", []))

    start(command_limit=3)
    reply[0] = "Executed Commands:\nUPDATE_NOTES(BUDGET_FIRST_NOTES)\nADD_GOAL(BUDGET_FIRST_GOAL,2,3)"
    check("model multiple commands dispatch together", input_turn("Store two fixture facts."))
    check("both commands execute against one allowance", executed("BUDGET_FIRST_NOTES") and executed("BUDGET_FIRST_GOAL") and runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 2)
    reply[0] = "Executed Commands:\nUPDATE_NOTES(BUDGET_NO_PREFIX)\nADD_GOAL(BUDGET_NO_TAIL,2,3)"
    check("oversized response remains a usable reply", input_turn("Attempt a two-command batch with one reservation left."))
    check("entire oversized batch denied without a prefix", not executed("BUDGET_NO_PREFIX") and not executed("BUDGET_NO_TAIL") and runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 2)
    check("command stop prevents automatic requests", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "command_limit" and not runtime.maybe_run_due_inference_turn())
    rejected = next(row for row in reversed(captured_receipts) if row.get("task_budget_results"))
    check("budget denial has typed before and after receipt", rejected["task_budget_results"][0]["code"] == "command_limit" and rejected["task_budget_results"][0]["before"]["remaining_commands"] == 1)
    check("operator status remains available", direct("SHOW_TASK_STATUS()")["submission_status"] == "completed")
    direct("UPDATE_NOTES(BUDGET_OPERATOR_OVERRIDE)")
    check("direct operator commands remain available without charging", executed("BUDGET_OPERATOR_OVERRIDE") and runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 2)
    for name, value in (("SET_TASK_MAX_COMMANDS", "500"), ("SET_TASK_MAX_REPORTED_TOKENS", "99999"), ("SET_TASK_UNKNOWN_USAGE_POLICY", "continue")):
        check("model cannot enlarge operator limits " + name, not runtime.execute_registered_setting_command(name, [value], is_user=False)["success"])
    budget_snapshots.append(runtime.TASK_CONTINUATION.snapshot())

    start(command_limit=1)
    try:
        direct("UPDATE_NOTES(BUDGET_INVALID_PREFIX); NO_SUCH_BUDGET_COMMAND()", False)
    except (ValueError, runtime.CommandSyntaxError):
        pass
    else:
        raise AssertionError("Invalid command unexpectedly admitted")
    check("invalid batch consumes no reservation", runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 0 and not executed("BUDGET_INVALID_PREFIX"))
    reply[0] = "Executed Commands:\nCOMPLETE_GOAL(99999999)"
    input_turn("Exercise an admitted command failure.")
    check("failed command does not refund reservation", runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 1 and runtime.TASK_CONTINUATION.snapshot()["accounting"]["failed_commands"] == 1)
    check("exact quota prevents next inference", not runtime.maybe_run_due_inference_turn() and runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "command_limit")

    start(command_limit=1)
    saved_queue = runtime.active_command_queue
    class BrokenSubmission:
        def put(self, entry):
            raise OSError("fixture submission uncertainty")
    try:
        runtime.active_command_queue = BrokenSubmission()
        try:
            runtime.enqueue_or_execute_command("UPDATE_NOTES(BUDGET_QUEUE_FAILURE)", is_user=False)
        except OSError:
            pass
        else:
            raise AssertionError("Submission failure did not propagate")
    finally:
        runtime.active_command_queue = saved_queue
    check("uncertain submission cannot refund or automatically replay", runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 1 and not runtime.maybe_run_due_inference_turn() and not executed("BUDGET_QUEUE_FAILURE"))

    start(command_limit=1)
    direct('QUEUE_PENDING("UPDATE_NOTES(BUDGET_PENDING_PREFIX); ADD_GOAL(BUDGET_PENDING_TAIL,2,3)")')
    pending_id = runtime.get_pending_command_store()[-1]["pending_id"]
    direct("APPROVE_PENDING(all)")
    held = runtime.get_pending_command_store()
    check("unstarted oversized pending batch remains held", len(held) == 1 and held[0]["pending_id"] == pending_id and held[0]["pending_state"] == "held")
    check("manual pending approval uses automatic child budget", runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 0 and not executed("BUDGET_PENDING_PREFIX") and not executed("BUDGET_PENDING_TAIL"))
    direct("CLEAR_PENDING()")

    nested_id = start(command_limit=1)
    direct('QUEUE_PENDING("UPDATE_NOTES(BUDGET_NESTED_CHILD)")')
    direct("APPROVE_PENDING(all)", False)
    nested = next(row for row in reversed(captured_receipts) if row.get("task_budget_results", [{}])[0].get("code") == "command_limit")
    check("worker nested admission shares parent identity and allowance", nested["task_id"] == nested_id and runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 1 and not executed("BUDGET_NESTED_CHILD"))
    check("nested rejection retains pending proposal", runtime.get_pending_command_store()[-1]["pending_state"] == "held")
    direct("CLEAR_PENDING()")
    old_parent = dict(task_id=nested_id, inference_request_id="old-budget-request", task_budget_results=[dict(controller_pid=os.getpid())])
    current_id = start(command_limit=4)
    with command_task_scope(old_parent):
        stale = direct("UPDATE_NOTES(BUDGET_STALE_CHILD)", False)
    check("old nested work cannot spend newer task budget", stale["execution_result"]["task_budget_results"][0]["code"] == "stale_task" and runtime.TASK_CONTINUATION.budget_snapshot()["admitted_commands"] == 0 and runtime.TASK_CONTINUATION.snapshot()["task_id"] == current_id)
    with command_task_scope(dict(old_parent, task_id=current_id, task_budget_results=[dict(controller_pid=os.getpid()+100000)])):
        foreign = direct("UPDATE_NOTES(BUDGET_FOREIGN_CHILD)", False)
    check("foreign worker cannot spend child-local allowance", foreign["execution_result"]["task_budget_results"][0]["code"] == "controller_required" and not executed("BUDGET_FOREIGN_CHILD"))

    # Reported usage is injected only at the provider boundary; no real requests.
    usage = [None]
    base_provider = provider
    def metered_provider(packet, token):
        response, mode, source = base_provider(packet, token)
        if response.status_code == 200:
            body = response.json()
            if usage[0] is not None:
                body["usage"] = copy.deepcopy(usage[0])
            response = SimpleNamespace(status_code=200, json=lambda: body)
        return response, mode, source
    runtime.perform_model_http_request = metered_provider
    usage[0] = {"total_tokens": 20}
    metered_id = start(token_limit=50)
    direct("SET_TASK_MAX_REPORTED_TOKENS(1000); SET_TEXT_MODEL(gpt-6-astra)")
    check("future setting does not rewrite active allowance", runtime.TASK_MAX_REPORTED_TOKENS == 1000 and runtime.TASK_CONTINUATION.budget_snapshot()["max_reported_tokens"] == 50)
    usage[0] = {"total_tokens": 30}
    reply[0] = "TOKEN_LIMIT_VISIBLE_REPLY\nExecuted Commands:\nUPDATE_NOTES(BUDGET_TOKEN_ACTION_MUST_NOT_RUN)"
    check("final metered response still returns normally", input_turn("Finish the metered fixture."))
    metered = runtime.TASK_CONTINUATION.snapshot()
    check("all slots share usage and terminal wrapper does not double charge", metered["task_id"] == metered_id and metered["accounting"]["usage"]["total_tokens"] == dict(known_total=50, known_requests=2, unknown_requests=0) and calls[-1]["model"] == "gpt-6-astra")
    check("usable final response is visible while its actions are withheld", "TOKEN_LIMIT_VISIBLE_REPLY" in json.dumps(runtime.get_chat_history_store()) and not executed("BUDGET_TOKEN_ACTION_MUST_NOT_RUN") and runtime.runtime_state["last_model_turn_status"] == "task_budget_stopped")
    check("reported token threshold stops automatic continuation", metered["stop_reason"] == "reported_token_limit" and not runtime.maybe_run_due_inference_turn())
    budget_snapshots.append(metered)
    direct("SET_TEXT_MODEL(gpt-6.1-sol)")

    usage[0] = None
    start(token_limit=50, unknown="continue")
    check("missing usage stays unknown under continue policy", runtime.TASK_CONTINUATION.snapshot()["status"] == "running" and runtime.TASK_CONTINUATION.budget_snapshot()["unknown_usage_requests"] == 1 and runtime.TASK_CONTINUATION.budget_snapshot()["known_usage_requests"] == 0)
    start(token_limit=50, unknown="stop", response="Executed Commands:\nUPDATE_NOTES(BUDGET_UNKNOWN_ACTION_MUST_NOT_RUN)")
    check("missing usage stop policy stops first unmetered response", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "usage_unknown" and runtime.runtime_state["last_model_turn_status"] == "task_budget_stopped" and not executed("BUDGET_UNKNOWN_ACTION_MUST_NOT_RUN"))
    start(unknown="stop")
    reply[0] = "Executed Commands:\nUPDATE_NOTES(BUDGET_ZERO_LEGACY_WORKS)"
    input_turn("Zero limits preserve the existing path.")
    check("zero token limit ignores missing usage policy", executed("BUDGET_ZERO_LEGACY_WORKS") and runtime.TASK_CONTINUATION.snapshot()["status"] == "running" and not runtime.TASK_CONTINUATION.budget_snapshot()["enabled"])

    usage[0] = {"total_tokens": 75}
    start(token_limit=50)
    check("last response can overshoot and is not clamped", runtime.TASK_CONTINUATION.budget_snapshot()["known_total_tokens"] == 75 and runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "reported_token_limit")
    budget_snapshots.append(runtime.TASK_CONTINUATION.snapshot())
    usage[0] = {"total_tokens": 1}
    start(token_limit=50, unknown="stop")
    provider_mode[0] = "error"
    input_turn("Exercise provider failure with missing usage stop enabled.")
    check("provider failure reason is not relabelled by usage policy", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "api_error_503" and not runtime.maybe_run_due_inference_turn())
    provider_mode[0] = "normal"
    runtime.perform_model_http_request = base_provider
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + "\n" + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "budget_snapshots": budget_snapshots,')
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
