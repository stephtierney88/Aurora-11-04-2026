"""Conditional Cancel work through real dispatch/turns; native/network guarded."""
import json
import offline_continuation_smoke as continuation


SCENARIOS = r'''
    def operator(command):
        submitted = runtime.enqueue_or_execute_command(command, is_user=True, source='continuation_fixture')
        drain()
        return submitted.get('execution_result') or recent[-1]
    runtime.get_input_queue_store().get_nowait()
    check('task cancellation settings enabled through existing authority', operator(
        'SET_TASK_MAX_MODEL_TURNS(20); SET_TASK_MAX_SECONDS(120); SET_LIVE_MODE(on)')['success'])
    input_turn('Conditional cancellation fixture task.')
    expected = runtime.TASK_CONTINUATION.snapshot()['task_id']

    def generations():
        return (runtime.MODEL_WORK.token().generation, runtime.COMMAND_WORK.token().generation,
                runtime.CAPTURE_SERVICE.lifecycle)

    old = generations()
    for label, command in (
        ('malformed task ID', 'CANCEL_ACTIVE_WORK_IF_TASK(invalid)'),
        ('mixed action batch', 'CANCEL_ACTIVE_WORK_IF_TASK(' + expected + '); UPDATE_NOTES(MUST_NOT_APPLY_80)'),
        ('pending wrapper', 'NEXT_TURN: CANCEL_ACTIVE_WORK_IF_TASK(' + expected + ')')):
        rejected = False
        try:
            runtime.enqueue_or_execute_command(command, is_user=True, source='continuation_fixture')
        except ValueError:
            rejected = True
        check(label + ' rejected before effects', rejected and generations()==old)
    denied = runtime.handle_commands('CANCEL_ACTIVE_WORK_IF_TASK(' + expected + ')', is_user=False)
    check('model actor cannot cancel operator task', not denied['success'] and generations()==old)
    stale = operator('CANCEL_ACTIVE_WORK_IF_TASK(task-' + '0'*32 + ')')
    check('stale task rejection has typed receipt', not stale['success']
          and stale['task_control_results'][0]['code']=='stale_task' and generations()==old)

    request = operator('REQUEST_SCREENSHOT_CAPTURE(conditional_cancel_fixture,0)')
    check('normal capture request pending without native acquisition', request['success'] and runtime.CAPTURE_SERVICE.snapshot()['pending'])
    released = []
    runtime.HELD_INPUTS.acquire(runtime.COMMAND_WORK.token(),
        dict(namespace='fixture', kind='key', requested='a', effective='a', backend='fixture'),
        lambda: None, lambda: released.append('a'), persistent=True)
    runtime.enqueue_or_execute_command('WAIT(5)', is_user=True, source='conditional_active_fixture')
    deadline = time.monotonic() + 2
    while not runtime.COMMAND_WORK.snapshot()['active_scopes'] and time.monotonic() < deadline:
        time.sleep(.005)
    check('real command worker has active cancellable wait', runtime.COMMAND_WORK.snapshot()['active_scopes'] > 0)
    runtime.enqueue_or_execute_command('UPDATE_NOTES(MUST_NOT_APPLY_80)', is_user=True, source='conditional_queued_fixture')
    cancelled = operator('CANCEL_ACTIVE_WORK_IF_TASK(' + expected + ')')
    receipt = cancelled['task_control_results'][0]
    check('matching conditional cancel executes through urgent controller', cancelled['success'] and receipt['changed'])
    check('receipt retains before after and generation evidence', receipt['before']['task_id']==expected
          and receipt['before']['status']=='running' and receipt['after']['status']=='stopped'
          and receipt['effects']['model_cancelled_through_generation']==old[0]
          and receipt['effects']['command_cancelled_through_generation']==old[1])
    check('input receipt releases original fake route exactly once', released==['a'] and cancelled['input_cleanup_results'][0]['success'])
    cancelled_batches = [row for row in recent if row.get('source') in ('conditional_active_fixture', 'conditional_queued_fixture')]
    check('conditional cancellation stops active and queued command generations', len(cancelled_batches)==2
          and all(row['cancelled'] and not row['executed_commands'] for row in cancelled_batches))
    check('cancel invalidates capture lifecycle and pending observation', not runtime.CAPTURE_SERVICE.snapshot()['pending']
          and runtime.CAPTURE_SERVICE.lifecycle==old[2]+1 and not runtime.runtime_state.get('turn_scheduler_pending_command_result'))
    check('cancel preserves live settings with unconfirmed remote outcome', runtime.SEND_TO_MODEL
          and runtime.ENABLE_MODEL_RESPONSES and receipt['remote_cancellation_confirmed'] is False)
    after = generations()
    again = operator('CANCEL_ACTIVE_WORK_IF_TASK(' + expected + ')')
    check('idempotent receipt does not rotate generations again', again['success']
          and again['task_control_results'][0]['code']=='already_stopped' and generations()==after and released==['a'])
    check('cancelled task cannot automatically continue', not runtime.maybe_run_due_inference_turn())
    input_turn('Replacement task remains active after a late cancellation command.')
    replacement = runtime.TASK_CONTINUATION.snapshot()['task_id']
    late = operator('CANCEL_ACTIVE_WORK_IF_TASK(' + expected + ')')
    check('late command cannot stop replacement task', not late['success'] and replacement!=expected
          and runtime.TASK_CONTINUATION.snapshot()['status']=='running' and generations()==after)

    for failure in ('none', 'cancelled', 'exception'):
        runtime.TASK_CONTINUATION.stop('fixture_boundary')
        replaced = []
        @runtime.serialized_model_turn
        def late_turn(**kwargs):
            replaced.append(runtime.current_delivery().task_id)
            runtime.TASK_CONTINUATION.stop('fixture_replacement')
            runtime.TASK_CONTINUATION.reserve(max_turns=20, max_seconds=120, operator_input=True)
            replaced.append(runtime.TASK_CONTINUATION.snapshot()['task_id'])
            if failure == 'cancelled':
                raise runtime.WorkCancelled('fixture late cancellation')
            if failure == 'exception':
                raise RuntimeError('fixture late exception')
            return None
        try:
            late_turn(wake_reason='user_input')
        except RuntimeError as error:
            check('fixture exception remains visible', failure=='exception' and str(error)=='fixture late exception')
        state = runtime.TASK_CONTINUATION.snapshot()
        check('actual model wrapper preserves replacement after ' + failure,
              replaced[0]!=replaced[1] and state['task_id']==replaced[1] and state['status']=='running')

    # A cancelled waiter has no reserved task. It must not stop the current one.
    entered = threading.Event()
    waiter_errors = []
    current_token = runtime.MODEL_WORK.current
    def observed_token():
        token = current_token()
        entered.set()
        return token
    runtime.MODEL_WORK.current = observed_token
    @runtime.serialized_model_turn
    def must_not_run(**kwargs):
        raise AssertionError('Cancelled waiter unexpectedly ran')
    def waiting_turn():
        try:
            must_not_run(wake_reason='command_readback')
        except Exception as error:
            waiter_errors.append(type(error).__name__)
    runtime.MODEL_TURN_LOCK.acquire()
    waiter = threading.Thread(target=waiting_turn, name='aurora-cancel-fixture-waiter')
    waiter.start()
    try:
        check('waiter captured old generation before cancellation', entered.wait(2))
        runtime.MODEL_WORK.cancel('fixture waiter only')
        waiter.join(2)
        check('cancelled waiter exits without stopping current task', not waiter.is_alive()
              and not waiter_errors and runtime.TASK_CONTINUATION.snapshot()['status']=='running')
    finally:
        runtime.MODEL_TURN_LOCK.release()
        waiter.join(2)
        runtime.MODEL_WORK.current = current_token
        assert not waiter.is_alive(), 'Owned cancellation waiter did not stop'

    provider_entered, release_provider = threading.Event(), threading.Event()
    original_provider = runtime.perform_model_http_request
    live_turn_errors = []
    def slow_provider(packet, token):
        provider_entered.set()
        assert release_provider.wait(3), 'Owned synthetic provider timed out'
        return original_provider(packet, token)
    runtime.perform_model_http_request = slow_provider
    def provider_turn():
        try:
            runtime.send_prompt_to_chatgpt('Synthetic in-flight cancellation.', wake_reason='user_input')
        except Exception as error:
            live_turn_errors.append(type(error).__name__)
    turn_thread = threading.Thread(target=provider_turn, name='aurora-conditional-provider-turn')
    turn_thread.start()
    try:
        check('synthetic provider reaches real I/O boundary', provider_entered.wait(2))
        in_flight_task = runtime.TASK_CONTINUATION.snapshot()['task_id']
        result = operator('CANCEL_ACTIVE_WORK_IF_TASK(' + in_flight_task + ')')
        turn_thread.join(1)
        check('conditional cancellation returns local turn while provider drains', result['success']
              and not turn_thread.is_alive() and not live_turn_errors and runtime.MODEL_IO.busy)
        check('draining provider cannot restart stopped task', runtime.TASK_CONTINUATION.snapshot()['status']=='stopped'
              and not runtime.maybe_run_due_inference_turn())
    finally:
        release_provider.set()
        turn_thread.join(3)
        deadline = time.monotonic() + 3
        while runtime.MODEL_IO.busy and time.monotonic() < deadline:
            time.sleep(.005)
        runtime.perform_model_http_request = original_provider
        assert not turn_thread.is_alive() and not runtime.MODEL_IO.busy, 'Owned synthetic provider did not drain'

    operator('CANCEL_ACTIVE_WORK()')
    check('legacy unconditional cancel still stops current task', runtime.TASK_CONTINUATION.snapshot()['status']=='stopped')
    operator('SET_TASK_CONTINUATION(legacy)')
    before = generations()
    disabled = operator('CANCEL_ACTIVE_WORK_IF_TASK(' + replacement + ')')
    check('legacy path rejects conditional control without effects', not disabled['success']
          and disabled['task_control_results'][0]['code']=='bounded_required' and generations()==before)
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
