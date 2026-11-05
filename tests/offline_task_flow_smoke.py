"""Actual parser/admission/settings proof without native input or provider access."""
import json
import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

SCENARIOS = r'''
import json
runtime.display_message = lambda *a, **k: None
runtime.maybe_run_game_focus_recovery = lambda *a, **k: None
runtime.active_command_queue = None
runtime.EXECUTION_MODE = "auto"
runtime.agent_state.inference_counter = 10
checks=[]
def check(name, condition):
    assert condition, name
    checks.append(name)
for commands in (["REQUEST_SCREENSHOT_CAPTURE(before,0)", "GB:press(right)"],
                 ["GB:press(right)", "REQUEST_SCREENSHOT_CAPTURE(after,0)"]):
    check('mixed receipt requests post-action observation: ' + ';'.join(commands), runtime.should_request_turn_after_command_result({"executed_commands": commands}))
check('capture-only receipt does not recursively capture', not runtime.should_request_turn_after_command_result({"executed_commands": ["REQUEST_SCREENSHOT_CAPTURE(next,0)"]}))
def decision(command):
    return runtime.evaluate_assistant_command_policy(command)["decision"]
def operator(command):
    result=runtime.handle_commands(command, True)
    assert result["success"], result
    return result
runtime.process_assistant_response("Scene: overworld\nObservation: The bedroom and stairs are visible.")
for command in ("GB:hold(right,0.8)", "REQUEST_SCREENSHOT_CAPTURE(next,0)", "SET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium)"):
    check("legacy holds " + command, decision(command)=="hold")
operator("SET_ASSISTANT_POLICY(task_flow)")
runtime.set_demand_capture_enabled(True)
for command in ("GB:hold(right,0.8)", "GB:press(up)", "REQUEST_SCREENSHOT_CAPTURE(next,0)", "SET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium)", "LOOKUP_COMMAND(GB:hold,high)"):
    check("flow admits " + command, decision(command)=="allow")
for command in ("GB:hold(right,2)", "GB:hold(right)", "GB:press(right,100)", "PYAG:hold(right,0.8)", "SET_EXECUTION_MODE(auto)", "SAVE_TASKS(test.json)"):
    check("flow retains review " + command, decision(command)!="allow")
runtime.set_demand_capture_enabled(False)
check("disabled capture stays held", decision("REQUEST_SCREENSHOT_CAPTURE(next,0)")=="hold")
runtime.set_demand_capture_enabled(True)
original_lock=runtime.require_runtime_setting_unlocked
runtime.require_runtime_setting_unlocked=lambda *a: (_ for _ in ()).throw(RuntimeError("test locked"))
for command in ("GB:hold(right,0.8)", "REQUEST_SCREENSHOT_CAPTURE(next,0)", "SET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium)"):
    check("lock rejects " + command, decision(command)=="reject")
runtime.require_runtime_setting_unlocked=original_lock
runtime.process_assistant_response("Scene: battle\nObservation: A wild battle and Fight menu are visible.")
check("battle movement remains rejected", decision("GB:hold(right,0.8)")=="reject")
for command in ("GB:press(a)", "GB:press(down)", "GB:hold(b,0.2)"):
    check("flow admits bounded battle menu " + command, decision(command)=="allow")
check("battle repeat counts remain held", decision("GB:press(a,100)")=="hold")
operator("SET_ASSISTANT_POLICY(legacy)")
check("legacy battle still held", decision("GB:press(a)")=="hold")
operator("SET_ASSISTANT_POLICY(task_flow)")
runtime.process_assistant_response("Scene: unknown\nObservation: The scene is unclear.")
check("unknown movement remains held", decision("GB:hold(right,0.8)")=="hold")
runtime.get_pending_command_store().clear()
runtime.EXECUTION_MODE="assist"
runtime.process_assistant_response("Executed Commands:\nREQUEST_SCREENSHOT_CAPTURE(next,0)")
check("Assist still holds capture", len(runtime.get_pending_command_store())==1)
runtime.get_pending_command_store().clear()
runtime.EXECUTION_MODE="auto"
runtime.process_assistant_response("Executed Commands:\nSET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium)\nREQUEST_SCREENSHOT_CAPTURE(next,0)")
check("Auto captures without operator approval", runtime.runtime_state.get("demand_capture_pending") and not runtime.get_pending_command_store())
check("Auto queues one-turn model without operator approval", runtime.agent_state.next_inference_plan.get("model")=="gpt-6-astra")
check("shared readback", runtime.build_registered_settings_runtime_state()["modes"]["assistant_policy"]=="task_flow")
from aurora_settings_transactions import build_settings_transaction_request, build_settings_transaction_command
version=runtime.build_settings_transaction_runtime_snapshot()["version"]
request=build_settings_transaction_request("apply",changes={"runtime.assistant_policy":"legacy"},expected_version=version)
receipt=operator(build_settings_transaction_command(request))["settings_transaction_receipts"][0]
request=build_settings_transaction_request("rollback",expected_version=receipt["after_version"],rollback_handle=receipt["rollback_handle"]["handle_id"])
operator(build_settings_transaction_command(request))
check("shared rollback restores task flow", runtime.ASSISTANT_POLICY=="task_flow")
check("current prompt explains bounded progress", "2-4 actions" in runtime.build_base_system_prompt())
response = "Executed Commands:\nUPDATE_PINNED_SHORT_TERM(Complete rival battle, then leave Oak's lab.)"
runtime.process_assistant_response(response)
check('model short horizon preserves apostrophe and comma', runtime.agent_state.pinned_short_term_actions == ["Complete rival battle, then leave Oak's lab."])
for name, field in [('UPDATE_PINNED_IMMEDIATE', 'pinned_immediate_actions'), ('UPDATE_MID_TERM_CONTEXT', 'mid_term_context'), ('UPDATE_LONG_TERM_CONTEXT', 'long_term_context')]:
    operator(name + "(Observe, then act.)")
    check('task flow preserves complete horizon ' + name, getattr(runtime.agent_state, field) == ['Observe, then act.'])
operator('SET_ASSISTANT_POLICY(legacy)')
operator('UPDATE_PINNED_SHORT_TERM(First, second)')
check('legacy horizon argument behavior remains available', runtime.agent_state.pinned_short_term_actions == ['First'])
operator('SET_ASSISTANT_POLICY(task_flow)')
check('documented executed heading is recognized', runtime.split_response_sections('Executed Commands:\nNOT_A_REAL_COMMAND()')[0] == 'NOT_A_REAL_COMMAND()')
operator('ADD_GOAL("Flow verification goal",High,Significant)')
before_goals=runtime.build_pinned_tasks_snapshot()
for command in ('COMPLETE_GOAL(Flow verification goal)', 'COMPLETE_GOAL(999999999)', 'COMPLETE_GOAL()'):
    result=runtime.handle_commands(command+'; ADD_GOAL("must not run")', True)
    check("goal failure is truthful and stops batch " + command, not result['success'] and runtime.build_pinned_tasks_snapshot()==before_goals)
goal=runtime.tasks_list[-1]
operator('COMPLETE_GOAL('+str(goal.id)+')')
check("integer goal completion works", goal.status=='Complete')
before_past=list(runtime.significant_past_tasks)
operator('COMPLETE_GOAL('+str(goal.id)+')')
check("goal completion retry is idempotent", list(runtime.significant_past_tasks)==before_past)
assert not Path("forbidden-native-input.txt").exists()
Path("proof.json").write_text(json.dumps({"status":"passed","checks":checks,"native_input_calls":0,"provider_calls":0},indent=2))
'''

if __name__ == "__main__":
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
