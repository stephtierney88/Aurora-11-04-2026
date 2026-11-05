"""Real worker/model preparation paths, with guarded fake inference and no input."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    import copy
    from aurora_history_controls import history_actor_scope
    from aurora_task_continuation import command_task_scope, scoped_task_id
    runtime.get_input_queue_store().get_nowait()
    operator("SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(30); SET_TASK_MAX_SECONDS(120); SET_READBACK_SCOPE(reviewed)")
    operator("SET_TASK_PLAN_CARRY_POLICY(carry); SET_TASK_PENDING_CARRY_POLICY(carry)")

    def seed(text):
        reply[0] = "Executed Commands:\nSET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium)\nQUEUE_PENDING(WAIT(0))"
        check(text + " dispatched", input_turn(text))
        plan = runtime.get_next_inference_plan_snapshot()
        pending = runtime.get_pending_command_snapshot()["entries"]
        task = runtime.TASK_CONTINUATION.snapshot()
        check(text + " actual worker stamped both artifacts", scoped_task_id(plan) == task["task_id"] and any(scoped_task_id(row) == task["task_id"] for row in pending))
        check(text + " origin retains request identity", bool(plan["task_origin"]["inference_request_id"]))
        return task["task_id"], plan, pending

    old, plan, rows = seed("Queue one-turn reasoning and a harmless pending proposal.")
    operator("CANCEL_ACTIVE_WORK()")
    reply[0] = "New operator task; apply the configured carry policy."
    check("new task starts normally under compatibility defaults", input_turn("Start the next fixture task."))
    current = runtime.TASK_CONTINUATION.snapshot(include_progress=True)
    check("default carry still sends queued model once", calls[-1]["model"] == "gpt-6-astra" and current["task_id"] != old)
    check("default pending carry retains original task attribution", any(scoped_task_id(row) == old for row in runtime.get_pending_command_snapshot()["entries"]))
    check("transition preserves plan hash before consumption", current["artifact_transition"]["before_plan_version"] == current["artifact_transition"]["after_plan_version"])
    check("normal next turn restores primary", input_turn("Continue with the primary model.") and calls[-1]["model"] == "gpt-6.1-sol")
    operator("CLEAR_PENDING(all); CLEAR_NEXT_INFERENCE()")

    old, plan, rows = seed("Prepare artifacts for an explicit strict task boundary.")
    operator("SET_TASK_PLAN_CARRY_POLICY(discard_previous); SET_TASK_PENDING_CARRY_POLICY(hold_previous)")
    check("policy edit does not alter the running task", runtime.TASK_CONTINUATION.snapshot()["plan_carry_policy"] == "carry" and runtime.get_next_inference_plan_snapshot() == plan)
    operator("CANCEL_ACTIVE_WORK()")
    reply[0] = "Start without the old task's queued model."
    check("strict task starts", input_turn("A separate task using strict carry policies."))
    task = runtime.TASK_CONTINUATION.snapshot(include_progress=True)
    held = next(row for row in runtime.get_pending_command_snapshot()["entries"] if scoped_task_id(row) == old)
    check("prior model plan discarded before provider preparation", calls[-1]["model"] == "gpt-6.1-sol" and task["artifact_transition"]["plan_disposition"] == "discarded")
    check("prior proposal now has explicit operator hold", held["pending_state"] == "task_held" and held["manual_approval_required"])
    check("held proposal cannot auto approve", not runtime.is_pending_entry_auto_approvable(held)[0])
    check("transition receipt has before/after versions", all(task["artifact_transition"].get(key) for key in ("before_pending_version", "after_pending_version", "before_plan_version", "after_plan_version")))
    check("compact prompt omits per-item transition details", "pending_items" not in runtime.build_task_continuation_snapshot(include_progress=False)["active_task"]["artifact_transition"])
    check("transition logs committed status", task["artifact_transition"]["journal_status"] == "written")

    reply[0] = "Executed Commands:\nAPPROVE_PENDING(id:" + held["pending_id"] + ")"
    input_turn("Try model approval of an operator-held proposal.")
    check("model cannot release an old task hold", any(row.get("pending_id") == held["pending_id"] and row["pending_state"] == "task_held" for row in runtime.get_pending_command_snapshot()["entries"]))
    operator("APPROVE_PENDING(id:" + held["pending_id"] + ")")
    check("explicit operator approval succeeds through normal worker", not any(row.get("pending_id") == held["pending_id"] for row in runtime.get_pending_command_snapshot()["entries"]))
    check("approved child command has actual execution receipt", any(row.get("pending_id") == held["pending_id"] and row.get("success") for row in recent))

    operator("SET_NEXT_INFERENCE(note=operator-owned; target_turn=999)")
    operator_plan = runtime.get_next_inference_plan_snapshot()
    rejected = []
    with history_actor_scope("model:late-fixture"), command_task_scope(dict(task_id=old, inference_request_id="late-request")):
        for callback in (lambda: runtime.set_next_inference_plan_from_pairs({"note": "late"}),
                         lambda: runtime.queue_pending_model_command("WAIT(2)")):
            try:
                callback()
            except RuntimeError:
                rejected.append(True)
    check("late prior-task plan and proposal both reject", len(rejected) == 2)
    check("late publication cannot overwrite operator plan", runtime.get_next_inference_plan_snapshot() == operator_plan)
    operator("CLEAR_PENDING(all); CLEAR_NEXT_INFERENCE()")

    old, plan, rows = seed("Prepare a discard-policy boundary.")
    operator("QUEUE_PENDING(WAIT(1)); SET_TASK_PENDING_CARRY_POLICY(discard_previous)")
    manual = next(row for row in runtime.get_pending_command_snapshot()["entries"] if row.get("task_origin", {}).get("kind") == "operator")
    operator("CANCEL_ACTIVE_WORK()")
    reply[0] = "Discard old model proposals while retaining manual ones."
    input_turn("New task with explicit discard policy.")
    pending = runtime.get_pending_command_snapshot()["entries"]
    check("discard removes old model proposal", not any(scoped_task_id(row) == old for row in pending))
    check("discard retains operator proposal", any(row["pending_id"] == manual["pending_id"] for row in pending))
    ownership_proof = copy.deepcopy(runtime.TASK_CONTINUATION.snapshot(include_progress=True)["artifact_transition"])

    operator("CANCEL_ACTIVE_WORK()")
    before_calls = len(calls)
    before_rows = runtime.get_pending_command_snapshot()
    before_plan = runtime.get_next_inference_plan_snapshot()
    original_reconcile = runtime.reconcile_task_artifacts
    runtime.reconcile_task_artifacts = lambda *a: (_ for _ in ()).throw(ValueError("injected transition failure"))
    try:
        try:
            input_turn("Exercise a transition preparation failure.")
        except ValueError:
            pass
        check("failed transition sends no provider request", len(calls) == before_calls)
        check("failed transition retains both artifact stores", runtime.get_pending_command_snapshot() == before_rows and runtime.get_next_inference_plan_snapshot() == before_plan)
        check("specific transition stop survives outer wrapper", runtime.TASK_CONTINUATION.snapshot()["stop_reason"] == "artifact_transition_failed")
    finally:
        runtime.reconcile_task_artifacts = original_reconcile
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + "\n" + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "ownership_transition": ownership_proof,')
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
