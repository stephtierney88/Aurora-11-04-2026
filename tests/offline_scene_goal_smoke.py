"""Real command/parser/state proof with synthetic import capture and no native/network I/O."""
import json
import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

SCENARIOS = r'''
import copy
import json
runtime.display_message = lambda *args, **kwargs: None
runtime.maybe_run_game_focus_recovery = lambda *args, **kwargs: None
runtime.active_command_queue = None
runtime.EXECUTION_MODE = "safe"
runtime.ACTIVE_ACTION_MODE = "gb"
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
def operator(command):
    result = runtime.handle_commands(command, True)
    assert result["success"], result
    return result

runtime.agent_state.inference_counter = 10
runtime.agent_state.recent_context_events[:] = ["Pokemon battle was rejected; old battle plans and HP/PP"]
runtime.set_runtime_value("last_command_status", "Rejected: battle scenes reject movement")
runtime.process_assistant_response("Scene: overworld\nObservation: The bedroom stairs are at upper right. No battle interface.\n\nExecuted Commands:\nGB:hold(right,0.2)")
info = runtime.infer_operating_context()
check("fresh model observation precedes command admission", info["gameplay_scene"] == "overworld")
check("receipt and planning text cannot reintroduce false battle", runtime.infer_gameplay_scene(info)["scene"] == "overworld")
runtime.agent_state.recent_context_events[:] = ["Python source module editor line numbers traceback stderr powershell prompt"]
check("fresh scene outranks historical desktop context", runtime.infer_operating_context()["context"] == "game")
check("current evidence is exported", runtime.build_control_panel_state_snapshot()["planning"]["gameplay_scene_evidence"]["policy"] == "evidence")
runtime.get_pending_command_store().clear()
transitions = []
original_invalidate = runtime.invalidate_pending_entries_for_scene_change
def track_transition(previous, current):
    transitions.append((previous, current))
    return original_invalidate(previous, current)
runtime.invalidate_pending_entries_for_scene_change = track_transition
runtime.process_assistant_response("Scene: battle\nObservation: Wild battle, Fight and a text box are visible.")
check("battle remains a reviewed/rejected input scene", runtime.evaluate_assistant_command_policy("GB:move_key(right,3)")["decision"] == "reject")
check("scene transition reaches pending invalidation", ("overworld", "battle") in transitions)
runtime.invalidate_pending_entries_for_scene_change = original_invalidate
runtime.agent_state.inference_counter += 2
check("old scene report expires", runtime.infer_gameplay_scene({"context": "game"})["scene"] == "unknown")
operator("SET_GAMEPLAY_SCENE_POLICY(legacy)")
check("legacy substring heuristic remains selectable", runtime.infer_gameplay_scene({"context":"game", "signal_parts":["The bedroom stairs are at upper right."]})["scene"] == "battle")
operator("SET_GAMEPLAY_SCENE_POLICY(evidence)")
check("scene setting readback", runtime.build_registered_settings_runtime_state()["modes"]["gameplay_scene_policy"] == "evidence")

operator('ADD_GOAL("Reach Cerulean",High,Critical)')
parent = runtime.tasks_list[0]
runtime.add_sub_goal(parent.id, "Find the stairs", "Medium", "Significant")
runtime.add_sub_goal(parent.id, "Leave the room")
child = parent.sub_goals[0]
runtime.add_sub_goal(child.id, "Observe the doorway")
runtime.mark_goal_as_completed(child.id)
ids = [goal.id for goal in runtime.iter_all_goals()]
check("recursive unique IDs", len(ids) == len(set(ids)))
runtime.agent_state.notes[:] = ["Preserve notes"]
runtime.agent_state.route_state["field_meta"] = {"current_area": {"source":"fixture"}}
runtime.agent_state.pinned_immediate_actions[:] = ["Look"]
runtime.agent_state.pinned_short_term_actions[:] = ["Leave"]
runtime.agent_state.mid_term_context[:] = ["Town"]
runtime.agent_state.long_term_context[:] = ["Journey"]
before = runtime.build_pinned_tasks_snapshot()
for format in ("versioned", "legacy"):
    operator("SET_GOAL_SAVE_FORMAT(" + format + ")")
    saved = operator("SAVE_TASKS(" + format + ".json)")
    check(format + " save receipt", saved["goal_file_results"][0]["effect_status"] == "applied")
    runtime.tasks_list.clear()
    runtime.agent_state.notes[:] = ["mutated"]
    runtime.agent_state.route_state["field_meta"]["stale_extra"] = True
    loaded = operator("LOAD_TASKS(" + format + ".json)")
    check(format + " full goal/horizon/notes roundtrip", runtime.build_pinned_tasks_snapshot() == before)
    check(format + " load receipt", loaded["goal_file_results"][0]["format"] == format)
new_goal = runtime.Goal("New after restore")
check("restoration does not reuse IDs", new_goal.id > max(ids))
before = runtime.build_pinned_tasks_snapshot()
Path("invalid.json").write_text(json.dumps({"goals_list":[], "notes":"bad"}))
for command in ("LOAD_TASKS(missing.json)", "LOAD_TASKS(invalid.json)"):
    result = runtime.handle_commands(command + '; ADD_GOAL("must not execute")', True)
    check(command + " has failure receipt", not result["success"] and not result["goal_file_results"][0]["success"])
    check(command + " leaves memory and batch tail unchanged", runtime.build_pinned_tasks_snapshot() == before)
result = runtime.handle_commands('ADD_GOAL("must not execute"); SAVE_TASKS(a,b)', True)
check("invalid save arguments reject the entire batch", not result["success"] and runtime.build_pinned_tasks_snapshot() == before)
original = Path("invalid.json").read_bytes()
result = runtime.handle_commands("SAVE_TASKS(invalid.json)", True)
check("malformed existing file retained", not result["success"] and Path("invalid.json").read_bytes() == original)
runtime.set_goal_save_format("versioned")
runtime.set_gameplay_scene_policy("evidence")
profile = runtime.build_runtime_preferences_snapshot()
runtime.set_goal_save_format("legacy")
runtime.set_gameplay_scene_policy("legacy")
restored = runtime._apply_default_profile(profile, source="offline_scene_goal")
check("profiles restore both compatibility settings", restored["success"] and runtime.GOAL_SAVE_FORMAT == "versioned" and runtime.GAMEPLAY_SCENE_POLICY == "evidence")
from aurora_settings_transactions import build_settings_transaction_request, build_settings_transaction_command
version = runtime.build_settings_transaction_runtime_snapshot()["version"]
for operation in ("preview", "apply"):
    request = build_settings_transaction_request(operation, changes={"game.scene_policy":"legacy", "goals.save_format":"legacy"}, expected_version=version)
    receipt = operator(build_settings_transaction_command(request))["settings_transaction_receipts"][0]
    check(operation + " shared settings transaction", receipt["status"] == ("previewed" if operation == "preview" else "applied"))
rollback = build_settings_transaction_request("rollback", expected_version=receipt["after_version"], rollback_handle=receipt["rollback_handle"]["handle_id"])
receipt = operator(build_settings_transaction_command(rollback))["settings_transaction_receipts"][0]
check("shared rollback restores both policies", receipt["status"] == "rolled_back" and runtime.GAMEPLAY_SCENE_POLICY == "evidence" and runtime.GOAL_SAVE_FORMAT == "versioned")
original_snapshot = runtime.build_pinned_tasks_snapshot
snapshot_calls = []
def fail_final_observation():
    snapshot_calls.append(True)
    if len(snapshot_calls) == 2:
        raise RuntimeError("fixture final observation failure")
    return original_snapshot()
runtime.build_pinned_tasks_snapshot = fail_final_observation
uncertain = runtime.handle_commands('LOAD_TASKS(versioned.json); ADD_GOAL("must not execute")', True)
check("post-publication failure stays uncertain and stops tail", not uncertain["success"] and uncertain["goal_file_results"][0]["effect_status"] == "failed_uncertain" and not any(g.text == "must not execute" for g in runtime.tasks_list))
runtime.build_pinned_tasks_snapshot = original_snapshot
assert not Path("forbidden-native-input.txt").exists()
Path("proof.json").write_text(json.dumps({"status":"passed", "checks":checks,
    "native_input_calls":0, "provider_calls":0, "capture":"synthetic PIL image installed before runtime import",
    "settings":runtime.build_registered_settings_runtime_state()["modes"]}, indent=2), encoding="utf-8")
'''

if __name__ == "__main__":
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
