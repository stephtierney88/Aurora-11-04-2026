"""Disposable operator/model-path characterization; records known gaps, never uses native I/O."""
import json
import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

SCENARIOS = r'''
import copy
import json
runtime.display_message = lambda *a, **k: None
runtime.maybe_run_game_focus_recovery = lambda *a, **k: None
runtime.EXECUTION_MODE = "assist"
runtime.active_command_queue = None
checks = []
def check(name, passed, **details):
    checks.append(dict(name=name, status="passed" if passed else "confirmed_defect", **details))
def operator(command):
    result = runtime.handle_commands(command, True)
    assert result["success"], result
    return result
def model(command):
    with runtime.history_actor_scope("model:fixture-assistant"):
        runtime.process_assistant_response("Executed Commands:\n" + command)
    while runtime.get_pending_command_store():
        result = runtime.approve_pending_command(["1"], True)
        assert result["success"], result
    return command

# Assistant admission must preserve the original GB/PYAG namespace even when
# the current mode differs, including nested pending wrappers. No input runs.
runtime.EXECUTION_MODE = "safe"
runtime.ACTIVE_ACTION_MODE = "pyag"
for proposal, namespace in [('GB:hold(right,0.2)', 'gb'),
                            ('QUEUE_PENDING("GB:hold(left,0.2)")', 'gb'),
                            ('INSERT_PENDING("GB:press(a)")', 'gb'),
                            ('REPLACE_PENDING("GB:press(b)")', 'gb'),
                            ('PYAG:press(a)', 'pyag')]:
    runtime.get_pending_command_store().clear()
    runtime.process_assistant_response("Executed Commands:\n" + proposal)
    pending = runtime.get_pending_command_store()
    assert len(pending) == 1, (proposal, pending)
    routes = [item[3] for item in pending[0]['_prepared_commands'] if item[3] is not None]
    assert len(routes) == 1 and routes[0].namespace == namespace, (proposal, routes)
check("assistant and wrapper admission preserves game/desktop namespace", True)
runtime.get_pending_command_store().clear()
runtime.EXECUTION_MODE = "assist"
runtime.ACTIVE_ACTION_MODE = "gb"

operator('ADD_GOAL("Reach the next town",High,Critical)')
check("operator goal labels", runtime.tasks_list[0].priority == "High" and runtime.tasks_list[0].significance == "Critical")
model('ADD_GOAL("Inspect the map",Medium,Significant)')
check("assistant parser and pending approval create goal", any(g.text == "Inspect the map" for g in runtime.tasks_list))
operator('UPDATE_PINNED_IMMEDIATE("Observe the screen")')
operator('UPDATE_PINNED_SHORT_TERM("Leave the room")')
operator('UPDATE_MID_TERM_CONTEXT("Reach the next town")')
operator('UPDATE_LONG_TERM_CONTEXT("Complete the journey")')
check("four supported horizon updates", all((runtime.agent_state.pinned_immediate_actions, runtime.agent_state.pinned_short_term_actions, runtime.agent_state.mid_term_context, runtime.agent_state.long_term_context)))
runtime.parse_hierarchical_tasks("""**Level 1**
**Action 1**: Inspect the door
**Priority**: High
**Significance**: Critical
**Associated Goal**: Reach the next town
**Level 2**
**Action 1**: Exit the room
**Priority**: Medium
**Significance**: Significant
**Level 3**
**Action 1**: Reach the town
**Level 4**
**Action 1**: Finish the route
""")
runtime.sync_action_horizons_from_hierarchical_tasks()
check("hierarchical priority/significance parse", runtime.hierarchical_tasks[0][0]["priority"] == "High" and runtime.hierarchical_tasks[0][0]["significance"] == "Critical")
checks.append(dict(name="manual horizons after hierarchy sync", status="legacy_behavior", replaces_manual=True,
                   observed=runtime.agent_state.pinned_immediate_actions))
runtime.parse_hierarchical_tasks("")
operator('COMPLETE_GOAL(1)')
check("complete existing goal", runtime.tasks_list[0].status == "Complete")

store = runtime.get_chat_history_store()
fixtures = [{"timestamp": f"2026-11-04 12:00:0{i}", "timestamp_iso": f"2026-11-04T12:00:0{i}-08:00", "role": "assistant", "model": "original", "Exemption": "None", "content": {"type":"text","text":f"message {i}"}} for i in range(4)]
store.extend(copy.deepcopy(fixtures))
operator('DHISTORY()')
check("operator message review", True)
operator('EDIT_MSGS("2026-11-04 12:00:00","operator corrected")')
model('EDIT_MSGS("2026-11-04 12:00:01","model corrected")')
edited = next(row for row in store if row.get("timestamp") == fixtures[1]["timestamp"])
check("model edits previous message and preserves author", edited.get("edited_by") == "model:fixture-assistant" and edited.get("model") == "original")
from aurora_history_controls import message_revision, build_update_message_command, history_text
runtime.ensure_message_ids(store)
target = next(row for row in store if row.get('timestamp') == fixtures[0]['timestamp'])
command = build_update_message_command(dict(message_id=target['message_id'], revision=message_revision(target)), 'operator pinned edit', 'on')
operator(command)
target = next(row for row in store if row.get('message_id') == target['message_id'])
check('revision-checked message edit and pin', target['Exemption']=='Pinned' and history_text(target)=='operator pinned edit' and target['model']=='original')
check('stale editor rejected', not runtime.handle_commands(command, True)['success'])
operator('PIN("legacy new pin remains available")')
check('legacy PIN creates new entry', any('legacy new pin remains available' in history_text(row) for row in store))
operator('DELETE_MSG("2026-11-04 12:00:02")')
model('DELETE_MSG("2026-11-04 12:00:03")')
check("operator and model exact timestamp deletion", not any(row.get("timestamp") in {fixtures[2]["timestamp"],fixtures[3]["timestamp"]} for row in store))
before = copy.deepcopy(store)
result = runtime.handle_commands('DELETE_MSG("2026-11-04 12:00:00","2026-11-04 12:00:01")', True)
check("unsupported range fails without deletion", not result["success"] and store == before)
checks.append(dict(name="range delete and near/extra-long horizons", status="not_implemented", detail="No such binding or optional horizon mode in current implementation"))
for signal in ('The bedroom stairs are at upper right.', 'The bedroom has no battle interface.'):
    scene = runtime.infer_gameplay_scene({'context': 'game', 'signal_parts': [signal]})
    check('scene classifier avoids false battle: ' + signal, scene['scene'] != 'battle', observed=scene)

runtime.tasks_list[:] = [runtime.Goal("Parent", "High", "Critical")]
try:
    runtime.save_pinned_tasks("flat-goals.json")
    runtime.load_pinned_tasks("flat-goals.json")
    check("goal persistence roundtrip", True)
except Exception as error:
    check("goal persistence roundtrip", False, error=type(error).__name__ + ": " + str(error))
runtime.add_sub_goal(runtime.tasks_list[0].id, "Child one")
runtime.add_sub_goal(runtime.tasks_list[0].id, "Child two")
ids = [goal.id for goal in runtime.iter_all_goals()]
check("nested goal IDs unique", len(ids) == len(set(ids)), observed_ids=ids)
try:
    runtime.save_pinned_tasks("nested-goals.json")
    check("nested goal save", True)
except Exception as error:
    check("nested goal save", False, error=type(error).__name__ + ": " + str(error))
assert not Path("forbidden-native-input.txt").exists()
proof = dict(status="characterized", checks=checks, native_or_network_calls=0, owned_threads_stopped=True)
Path("proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
'''

if __name__ == '__main__':
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit('runtime.main()', 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
