"""Real queue/preparation/provider-boundary proof with guarded native/network I/O."""
import json
import offline_continuation_smoke as continuation

SCENARIOS = r'''
    runtime.get_input_queue_store().get_nowait()
    observed_objectives = []
    base_provider = runtime.perform_model_http_request
    def objective_provider(packet, token):
        observed_objectives.append([m for m in packet['payload']['messages'] if isinstance(m.get('content'), str)
            and m['content'].startswith('Retained operator context for active task ')])
        return base_provider(packet, token)
    runtime.perform_model_http_request = objective_provider
    check('operator context enabled via shared setting receipt', operator(
        'SET_TASK_OBJECTIVE_MODE(operator); SET_TASK_MAX_MODEL_TURNS(20); SET_TASK_MAX_SECONDS(120); SET_LIVE_MODE(on)')['success'])
    reply[0] = 'Ready.'
    input_turn('OBJECTIVE_66: deliver parcel, then continue to Pewter until stopped.')
    task_id = runtime.TASK_CONTINUATION.snapshot()['task_id']
    check('queue text projected in original user role', observed_objectives[-1][0]['role']=='user'
          and 'OBJECTIVE_66' in observed_objectives[-1][0]['content'])
    runtime.get_chat_history_store()[:] = []
    runtime.MAX_TEXT_CONTEXT_MESSAGES = 1
    runtime.send_prompt_to_chatgpt('Synthetic receipt, not a new objective.', role='user', wake_reason='command_readback')
    drain()
    check('objective survives history loss without promoting readbacks', 'OBJECTIVE_66' in observed_objectives[-1][0]['content']
          and 'Synthetic receipt' not in observed_objectives[-1][0]['content'])
    input_turn('CLARIFICATION_66: heal before travelling further if health is low.')
    check('clarification preserves task and initial objective', runtime.TASK_CONTINUATION.snapshot()['task_id']==task_id
          and all(word in observed_objectives[-1][0]['content'] for word in ['OBJECTIVE_66','CLARIFICATION_66']))
    check('next-task setting does not remove active objective', operator('SET_TASK_OBJECTIVE_MODE(legacy)')['success']
          and runtime.TASK_CONTINUATION.snapshot()['objective_mode']=='operator')
    check('cancel removes objective projection', operator('CANCEL_ACTIVE_WORK()')['success']
          and not runtime.TASK_CONTINUATION.objective_projection(task_id))
    input_turn('Legacy replacement task.')
    check('legacy replacement receives no retained projection', observed_objectives[-1]==[])
    operator('CANCEL_ACTIVE_WORK()')
    operator('SET_TASK_OBJECTIVE_MODE(operator)')
    input_turn('REPLACEMENT_66: a distinct task.')
    check('replacement does not inherit prior operator instructions', 'REPLACEMENT_66' in observed_objectives[-1][0]['content']
          and 'OBJECTIVE_66' not in observed_objectives[-1][0]['content'])
    before = len(observed_objectives)
    input_turn('x' * 32769)
    check('capacity stops before provider without partial instruction', len(observed_objectives)==before
          and runtime.TASK_CONTINUATION.snapshot()['stop_reason']=='objective_capacity'
          and runtime.runtime_state['last_model_turn_status']=='objective_capacity')
    operator('SET_TASK_OBJECTIVE_MODE(legacy); SET_LIVE_MODE(off)')
'''


def run_smoke():
    marker = '    check("native/network guards never fired", not Path("forbidden-native-input.txt").exists())'
    assert continuation.SCENARIOS.count(marker) == 1
    fixture = continuation.SCENARIOS.replace(marker, SCENARIOS + '\n' + marker)
    continuation.harness.FIXTURE = (continuation.CONTRACT_IMPORT_GUARD +
        continuation.CONTRACT_FIXTURE.rsplit('runtime.main()', 1)[0] + fixture)
    return continuation.harness.run_smoke()


if __name__ == '__main__':
    print(json.dumps(run_smoke(), indent=2))
