"""Task-correlated readbacks through real admission, workers and fake requests."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    # The base continuation fixture ends paused with one intentional queued input.
    runtime.get_input_queue_store().get_nowait()
    check("reviewed scope enabled through shared commands", operator(
        "SET_LIVE_MODE(on); SET_TASK_MAX_MODEL_TURNS(12); SET_TASK_MAX_SECONDS(120); SET_READBACK_SCOPE(reviewed); SET_READBACK_WAKE(on)")["success"])
    check("task-flow permanent setting writes still require review", runtime.evaluate_assistant_command_policy("SET_CAPTURE_REQUEST_TIMEOUT(5)")["decision"] == "hold")
    runtime.ASSISTANT_POLICY = "legacy"
    check("legacy assistant policy retains setting-query review", runtime.evaluate_assistant_command_policy("SET_CAPTURE_REQUEST_TIMEOUT()")["decision"] == "hold")
    runtime.ASSISTANT_POLICY = "task_flow"
    runtime.COMMAND_DISCOVERY_CONTEXT = False
    runtime.enable_unimportant_messages = False
    handle = runtime.RETRIEVAL_RESULTS.publish(runtime.RETRIEVAL_RESULTS.prepare(
        [{"record": {"id": "readback-fixture", "summary": "RETRIEVAL_SENTINEL_44"}}], {}, {}, "fixture"))["handle"]
    recorded_manifests = []
    base_provider = provider
    usage_mode = ["known"]
    def reviewed_provider(packet, token):
        for message in packet["payload"]["messages"]:
            content = message.get("content")
            if isinstance(content, str) and content.startswith("Command execution readbacks"):
                recorded_manifests.append(json.loads(content.split("\n", 1)[1]))
        response, mode, source = base_provider(packet, token)
        if response.status_code == 200:
            body = response.json()
            if usage_mode[0] == "known":
                body["usage"] = {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}
            response = SimpleNamespace(status_code=200, json=lambda: body)
        return response, mode, source
    runtime.perform_model_http_request = reviewed_provider
    reply[0] = ("Executed Commands:\nSET_CAPTURE_REQUEST_TIMEOUT()\n"
                "ADD_GOAL(READBACK_GOAL_SENTINEL_44,2,3)\nSHOW_RETRIEVAL_RESULT(" + handle + ")")
    check("model-origin mixed reviewed commands dispatch", input_turn("Read settings, store the fixture goal, inspect the retained result."))
    task_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    rows = runtime.COMMAND_READBACKS.snapshot()["records"]
    current = [row for row in rows if row["task_id"] == task_id]
    families = {family for row in current for family in row["families"]}
    check("setting goal and retrieval receipts are retained", {"setting_results", "memory_command_results", "retrieval_results"} <= families)
    check("receipts carry origin request and batch identities", all(row["origin_inference_request_id"] and row["command_batch_id"] and row["receipt_id"] for row in current))
    check("readback wakes without history or discovery insertion", "command_readback" in runtime.evaluate_turn_scheduler()["reasons"])
    reply[0] = "I inspected the actual command receipts."
    usage_mode[0] = "unknown"
    check("receipt follow-up dispatched", runtime.maybe_run_due_inference_turn())
    drain()
    selected = recorded_manifests[-1]
    serialized = json.dumps(selected)
    check("actual request includes settings goal and retrieval evidence", all(term in serialized for term in ("setting_results", "READBACK_GOAL_SENTINEL_44", "RETRIEVAL_SENTINEL_44")))
    check("request manifest matches prepared diagnostics", selected == runtime.runtime_state["last_prompt_diagnostics"]["command_readbacks"])
    check("readback is text-only and consumed after response", not calls[-1]["image_attached"] and not runtime.COMMAND_READBACKS.pending(task_id))
    check("readback does not create an idle loop", not runtime.maybe_run_due_inference_turn())
    after = runtime.TASK_CONTINUATION.snapshot()["accounting"]
    check("per-task operation accounting records actual commands", after["command_batches"] >= 1 and after["executed_commands"] == 3 and after["failed_commands"] == 0)
    check("known usage and missing usage have separate coverage", after["usage"]["total_tokens"] == {"known_total": 25, "known_requests": 1, "unknown_requests": 1})
    check("request correlation retains selected readback identities", set(after["last_request"]["readback_ids"]) == {row["record_id"] for row in selected["records"]})
    repeated = recent[-1]
    before = runtime.TASK_CONTINUATION.snapshot()["accounting"]["command_batches"]
    runtime.ingest_command_result(repeated)
    check("duplicate ingestion does not recount or republish", runtime.TASK_CONTINUATION.snapshot()["accounting"]["command_batches"] == before and not runtime.COMMAND_READBACKS.pending(task_id))

    reply[0] = "Executed Commands:\nCOMPLETE_GOAL(99999999)"
    check("failed reviewed command runs", input_turn("Exercise a nonexistent goal failure."))
    check("failure receipt is pending for inspection", runtime.COMMAND_READBACKS.pending(task_id) > 0)
    provider_mode[0] = "error"
    runtime.maybe_run_due_inference_turn()
    drain()
    failed_rows = [row for row in runtime.COMMAND_READBACKS.snapshot()["records"] if row["task_id"] == task_id]
    check("submitted failure is uncertain and not automatically replayed", any(row["phase"] == "uncertain" and row["status"] == "failed" for row in failed_rows) and not runtime.maybe_run_due_inference_turn())
    check("failed command accounting is distinct from a reply", runtime.TASK_CONTINUATION.snapshot()["accounting"]["failed_commands"] == 1)
    provider_mode[0] = "normal"
    reply[0] = "A new task can begin."
    previous_manifest_count = len(recorded_manifests)
    check("new operator task recovers after failure", input_turn("Begin a separate task after inspecting the failure."))
    check("prior task evidence does not leak into the new task", runtime.TASK_CONTINUATION.snapshot()["task_id"] != task_id and len(recorded_manifests) == previous_manifest_count)

    reply[0] = "Executed Commands:\nSET_CAPTURE_REQUEST_TIMEOUT()"
    input_turn("Queue a setting readback for the scope test.")
    current_id = runtime.TASK_CONTINUATION.snapshot()["task_id"]
    check("receipt is available for the next turn", runtime.COMMAND_READBACKS.pending(current_id) > 0)
    operator("SET_READBACK_SCOPE(discovery)")
    check("legacy scope does not wake for reviewed-only receipts", not runtime.maybe_run_due_inference_turn())
    operator("SET_READBACK_SCOPE(reviewed)")
    check("returning to reviewed scope exposes existing pending data", "command_readback" in runtime.evaluate_turn_scheduler()["reasons"])
    operator("CANCEL_ACTIVE_WORK()")
    check("cancel blocks pending readback continuation", not runtime.maybe_run_due_inference_turn())
    runtime.enable_unimportant_messages = True
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + "\n" + marker)
    fixture = fixture.replace('"requests": calls,', '"requests": calls, "reviewed_receipts": selected, "accounting_after_readback": after, "retained_readbacks": runtime.COMMAND_READBACKS.snapshot(include_results=False),')
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
