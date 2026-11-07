"""Real command/turn/transport preparation with synthetic provider and I/O guards."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    from aurora_task_objective import encode_steering_text
    def operator(command):
        submitted = runtime.enqueue_or_execute_command(command, is_user=True, source='steering_fixture')
        drain()
        return submitted.get('execution_result') or recent[-1]
    runtime.get_input_queue_store().get_nowait()
    check('context retention enabled through existing settings', operator(
        'SET_TASK_OBJECTIVE_MODE(operator); SET_TASK_MAX_MODEL_TURNS(20); SET_TASK_MAX_SECONDS(120); SET_LIVE_MODE(on)')['success'])
    input_turn('ORIGINAL_81: deliver parcel, then heal; do not leave the fixture.')
    identity = runtime.TASK_CONTINUATION.snapshot()['task_id']
    def read_context():
        receipt = operator('SHOW_TASK_CONTEXT(' + identity + ')')
        check('inspection returns typed controller receipt', receipt['success'] and bool(receipt['task_control_results']))
        return receipt['task_control_results'][0]
    def steer(text, version=None, target=None):
        version = version or read_context()['context']['context_version']
        return operator('STEER_TASK(' + (target or identity) + ',' + version + ',' + encode_steering_text(text) + ')')
    initial = read_context()
    check('exact original context retained with source and user role', initial['messages'][0]['role']=='user'
          and initial['messages'][0]['source']=='queued_operator_text' and 'ORIGINAL_81' in initial['messages'][0]['text'])
    before = runtime.TASK_CONTINUATION.snapshot()
    before_calls = len(calls)
    text = 'STEERING_81: café first.\nLiteral syntax: "); CANCEL_ACTIVE_WORK(); UPDATE_NOTES(MUST_NOT_EXECUTE_81)"'
    applied = steer(text, initial['context']['context_version'])
    result = applied['task_control_results'][0]
    check('steering applies once with typed version evidence', applied['success'] and result['changed']
          and result['before']['context_version']!=result['after']['context_version'])
    after = runtime.TASK_CONTINUATION.snapshot()
    check('steering preserves task limits turns and wake generation', all(before[key]==after[key] for key in ('task_id','turns','budgets','readback','max_seconds','max_turns')))
    check('steering creates no inference wake or queue entry', len(calls)==before_calls and runtime.get_input_queue_store().empty()
          and not runtime.maybe_run_due_inference_turn() and result['wake_requested'] is False)
    view = read_context()
    check('literal text remains one operator message and did not execute', view['messages'][-1]['text']==text
          and view['messages'][-1]['source']=='operator_steering' and runtime.TASK_CONTINUATION.snapshot()['status']=='running')
    duplicate = steer(text, initial['context']['context_version'])
    check('same edit retry cannot append twice', not duplicate['success']
          and duplicate['task_control_results'][0]['code']=='context_conflict' and read_context()['context']['messages']==2)
    check('ordinary snapshots contain no retained private text', 'STEERING_81' not in json.dumps(runtime.TASK_CONTINUATION.snapshot(include_progress=True)))

    original_provider = runtime.perform_model_http_request
    prepared_contexts = []
    entered, release = threading.Event(), threading.Event()
    blocking = [False]
    def observe_provider(packet, token):
        prepared_contexts.append([dict(m) for m in packet['payload']['messages'] if isinstance(m.get('content'),str)
            and m['content'].startswith('Retained operator context for active task ')])
        if blocking[0]:
            entered.set()
            assert release.wait(4), 'Synthetic steering provider did not release'
        return original_provider(packet, token)
    runtime.perform_model_http_request = observe_provider
    runtime.get_chat_history_store()[:] = []
    runtime.send_prompt_to_chatgpt('Normal continued fixture request.', wake_reason='command_readback')
    drain()
    check('next normal request receives full retained text in user role', prepared_contexts[-1][0]['role']=='user'
          and all(value in prepared_contexts[-1][0]['content'] for value in ('ORIGINAL_81','STEERING_81')))
    check('preparation metadata joins request ID and exact selected version', runtime.runtime_state['last_prompt_diagnostics']['inference_request_id']
          and runtime.runtime_state['last_prompt_diagnostics']['task_context']['context_version']==view['context']['context_version'])
    check('inspecting context did not inject it into ordinary chat', not any('STEERING_81' in str(row.get('content')) for row in runtime.get_chat_history_store()))

    blocking[0] = True
    thread_errors = []
    def in_flight():
        try:
            runtime.send_prompt_to_chatgpt('In-flight preparation fixture.', wake_reason='command_readback')
        except Exception as error:
            thread_errors.append(type(error).__name__)
    thread = threading.Thread(target=in_flight, name='aurora-steering-inflight-fixture')
    thread.start()
    try:
        check('real model I/O boundary reached before steering', entered.wait(2))
        old_preparation = runtime.runtime_state['last_prompt_diagnostics']['task_context']['context_version']
        changed = steer('LATE_STEERING_81: wait for the blue sign.')
        check('in-flight steering applies without interrupting provider', changed['success'] and runtime.MODEL_IO.busy)
        check('already prepared payload and version stay frozen', 'LATE_STEERING_81' not in json.dumps(prepared_contexts[-1])
              and runtime.runtime_state['last_prompt_diagnostics']['task_context']['context_version']==old_preparation)
    finally:
        release.set()
        thread.join(4)
        blocking[0] = False
        assert not thread.is_alive(), 'Owned steering thread did not exit'
        deadline = time.monotonic()+3
        while runtime.MODEL_IO.busy and time.monotonic()<deadline:
            time.sleep(.005)
        assert not runtime.MODEL_IO.busy, 'Owned synthetic provider did not exit'
    check('in-flight request finishes without automatic replay', not thread_errors and not runtime.maybe_run_due_inference_turn())
    runtime.send_prompt_to_chatgpt('Next normal request after steering.', wake_reason='command_readback')
    drain()
    check('later preparation uses updated steering version', 'LATE_STEERING_81' in json.dumps(prepared_contexts[-1])
          and runtime.runtime_state['last_prompt_diagnostics']['task_context']['context_version']==read_context()['context']['context_version'])
    runtime.perform_model_http_request = original_provider

    current = read_context()
    for command in ('SHOW_TASK_CONTEXT(' + identity + ')', 'STEER_TASK(' + identity + ',' + current['context']['context_version'] + ',' + encode_steering_text('MODEL_FORGED_81') + ')'):
        denied = runtime.handle_commands(command, is_user=False)
        check('model actor denied retained context control', not denied['success'])
    check('model actor cannot promote its plan into operator authority', not any('MODEL_FORGED_81' in row['text'] for row in read_context()['messages']))
    runtime.RUNTIME_SETTING_LOCKS['execution'] = True
    try:
        locked = steer('LOCKED_81', current['context']['context_version'])
        check('locked execution rejects steering with typed receipt', not locked['success'] and locked['task_control_results'][0]['code']=='execution_locked')
        check('inspection remains available while execution locked', read_context()['context']['context_version']==current['context']['context_version'])
    finally:
        runtime.RUNTIME_SETTING_LOCKS['execution'] = False
    overflow = steer('x'*32768)
    check('capacity overflow preserves original task and text', not overflow['success']
          and overflow['task_control_results'][0]['code']=='context_capacity'
          and runtime.TASK_CONTINUATION.snapshot()['status']=='running' and read_context()['context']['context_version']==current['context']['context_version'])
    operator('SET_TASK_OBJECTIVE_MODE(legacy)')
    check('latched operator mode still permits active task steering', steer('LATCHED_81')['success'])
    operator('CANCEL_ACTIVE_WORK()')
    stopped = steer('DO_NOT_RESTART_81', current['context']['context_version'])
    check('stopped task cannot be revived by steering', not stopped['success'] and stopped['task_control_results'][0]['code']=='task_stopped')
    input_turn('Replacement using legacy retention.')
    old_identity = identity
    identity = runtime.TASK_CONTINUATION.snapshot()['task_id']
    stale = steer('DO_NOT_LEAK_81', current['context']['context_version'], old_identity)
    check('stale edit cannot target replacement or expose its text', not stale['success']
          and stale['task_control_results'][0]['code']=='stale_task' and 'Replacement using' not in json.dumps(stale['task_control_results']))
    check('legacy replacement retains no text', read_context()['messages']==[])
    disabled = steer('DO_NOT_ENABLE_RETENTION_81')
    check('steering cannot enable retention on legacy task', not disabled['success'] and disabled['task_control_results'][0]['code']=='retention_disabled')
    operator('SET_LIVE_MODE(off)')
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
