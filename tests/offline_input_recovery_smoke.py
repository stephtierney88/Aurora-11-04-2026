"""Durable inbox/queue/turn contracts with the production runtime and fake I/O."""
import json
import offline_delivery_smoke as delivery
import offline_responses_smoke as harness

SCENARIOS = r'''
import queue
from unittest.mock import patch
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
def run(command, success=True, user=True):
    result = runtime.execute_command_entry(dict(command=command, is_user=user, source='user' if user else 'assistant_response'))
    check(command[:80], result['success'] is success)
    return result
def rows():
    return run('SHOW_INPUT_RECOVERY()')['memory_command_results'][0]['readback']['entries']
def act(name, row, suffix=''):
    return name + '(' + row['entry_id'] + ',' + row['version'] + suffix + ')'
def restart_evidence():
    runtime.INPUT_RECOVERY.close()
    runtime.INPUT_RECOVERY = None
    # A fresh runtime starts with an empty volatile queue.
    runtime.agent_state.queued_user_input = queue.Queue()
    return runtime.get_input_recovery()

try:
    run('SET_INPUT_RECOVERY(durable)')
    check('shared readback exposes effective mode', runtime.build_registered_settings_runtime_state()['modes']['input_recovery'] == 'durable')
    first = send('Persist this first input')
    old = rows()[0]
    check('admitted durably before use', old['phase'] == 'queued')
    restart_evidence()
    recovered = rows()[0]
    check('restart holds and does not replay', recovered['phase'] == 'held' and runtime.get_input_queue_store().empty() and not calls)
    run(act('RETRY_INPUT', old), False)
    run(act('RETRY_INPUT', recovered), user=False, success=False)
    run(act('RETRY_INPUT', recovered))
    fresh = rows()[0]
    check('retry uses fresh correlation identity', fresh['identity'] != old['identity'] and fresh['attempt'] == 2)
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    runtime.handle_queued_input('', '')
    check('fresh retry reaches actual turn and terminal durable receipt', rows()[0]['phase'] == 'responded' and len(calls) == 1)
    check('duplicate original never redispatches', not runtime.queue_recoverable_input(old['text'], old['original_identity']) and runtime.get_input_queue_store().empty())
    runtime.SEND_TO_MODEL = False
    record = send('Cancel this queued input')
    cancelled = rows()[-1]
    run(act('CANCEL_QUEUED_INPUT', cancelled))
    check('cancel removes queued copy but keeps durable evidence', runtime.get_input_queue_store().empty() and rows()[-1]['phase'] == 'cancelled')
    run(act('RETRY_INPUT', rows()[-1]))
    run('SET_INPUT_RECOVERY(legacy)', False)
    runtime.SEND_TO_MODEL = True
    def interruption(): raise RuntimeError('fixture before dispatch')
    try: runtime.handle_queued_input('', '', before_dispatch=interruption)
    except RuntimeError: pass
    check('interruption after dequeue retains not-sent payload', rows()[-1]['phase'] == 'not_sent' and len(calls) == 1)
    run(act('RETRY_INPUT', rows()[-1]))
    recovery = runtime.get_input_recovery()
    original_publish = recovery._publish
    def fail_submit(state):
        if any(row['phase'] == 'submitted' for row in state.values()):
            raise OSError('fixture disk failure before submit')
        return original_publish(state)
    recovery._publish = fail_submit
    try: runtime.handle_queued_input('', '')
    finally: recovery._publish = original_publish
    check('durability failure prevents fake provider call', len(calls) == 1 and not rows()[-1]['request_started'])
    run(act('RETRY_INPUT', rows()[-1]))
    mode = 'http'
    runtime.handle_queued_input('', '')
    failed = rows()[-1]
    check('request failure retains started evidence', failed['phase'] == 'failed' and failed['request_started'])
    run(act('RETRY_INPUT', failed), False)
    run(act('RETRY_INPUT', failed, ',allow_uncertain'))
    mode = 'success'
    runtime.handle_queued_input('', '')
    check('explicit uncertain retry completes fresh attempt', rows()[-1]['phase'] == 'responded' and len(calls) == 3)
    # Failed admission must not advance inbox cursor or claim receipt of input.
    runtime.SEND_TO_MODEL = False
    record = runtime.append_external_message_record('Disk failure at admission', source='panel_conversation', client_id='delivery_smoke')
    before_cursor = runtime.external_bridge_state['inbox_offset']
    with patch('aurora_input_recovery.os.replace', side_effect=OSError('fixture disk full')):
        try: runtime.poll_external_inbox_messages()
        except OSError: pass
    check('admission failure preserves unread cursor and empty queue', runtime.external_bridge_state['inbox_offset'] == before_cursor and runtime.get_input_queue_store().empty())
    runtime.poll_external_inbox_messages()
    row = rows()[-1]
    run(act('CANCEL_QUEUED_INPUT', row))
    previous = len(rows())
    oversized = runtime.append_external_message_record('x'*64000, source='panel_conversation', client_id='delivery_smoke')
    runtime.poll_external_inbox_messages()
    check('oversized admission is explicitly rejected without poisoning later input', len(rows()) == previous and runtime.get_input_queue_store().empty())
    following = send('Valid input after rejected oversized record')
    run(act('CANCEL_QUEUED_INPUT', rows()[-1]))
    mode = 'cancel'
    send('Cancel while provider is outstanding')
    runtime.SEND_TO_MODEL = True
    def cancel_during_wait():
        if entered.is_set(): runtime.MODEL_WORK.cancel('fixture cancel')
    runtime.service_runtime_control_during_model_wait = cancel_during_wait
    runtime.handle_queued_input('', '')
    pending = rows()[-1]
    check('active cancellation retains started uncertainty', pending['phase'] == 'cancelled' and pending['request_started'] and runtime.MODEL_IO.busy)
    run(act('RETRY_INPUT', pending, ',allow_uncertain'), False)
    release.set()
    deadline = time.monotonic()+3
    while runtime.MODEL_IO.busy and time.monotonic() < deadline: time.sleep(.01)
    check('late provider result cannot overwrite cancellation', not runtime.MODEL_IO.busy and rows()[-1]['phase'] == 'cancelled')
    check('panel export includes recovery summary without message text',
          'phases' in runtime.build_control_panel_state_snapshot()['conversation_io']['input_recovery'])
    runtime.service_runtime_control_during_model_wait = lambda: None
    runtime.SEND_TO_MODEL = False
    done = next(row for row in rows() if row['phase'] == 'responded')
    before_disk = recovery.path.read_bytes()
    preview = run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)', user=False)['memory_command_results'][0]['readback']
    check('compaction preview leaves disk unchanged', recovery.path.read_bytes() == before_disk and preview['selected_count'] > 0)
    run(preview['apply_command'], user=False, success=False)
    record = send('New admission invalidates whole-store compaction preview')
    run(preview['apply_command'], success=False)
    run(act('CANCEL_QUEUED_INPUT', rows()[-1]))
    preview = run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)')['memory_command_results'][0]['readback']
    before_disk = recovery.path.read_bytes()
    run('LOCK_SETTING(execution)')
    run(preview['apply_command'], success=False)
    run('UNLOCK_SETTING(execution)')
    with runtime.COMMAND_WORK.scope():
        runtime.COMMAND_WORK.cancel('fixture cancelled compaction')
        cancelled = runtime.execute_input_recovery_command('COMPACT_INPUT_RECOVERY', ['0','100',preview['version'],'discard_text'], True)
    check('cancelled command cannot discard recovery text', cancelled.get('cancelled') is True and recovery.path.read_bytes() == before_disk)
    with patch('aurora_input_recovery.os.replace', side_effect=OSError('fixture compaction disk failure')):
        run(preview['apply_command'], success=False)
    check('compaction write failure preserves exact file', recovery.path.read_bytes() == before_disk)
    compacted = run(preview['apply_command'])['memory_command_results'][0]['after']
    check('compaction frees terminal payloads and retains hashes', compacted['compacted_count'] == preview['selected_count'] and recovery.summary()['compacted'] > 0)
    check('compacted original input stays deduplicated', not runtime.queue_recoverable_input(done['text'],done['original_identity']) and runtime.get_input_queue_store().empty())
    check('cancelled started input remains inspectable', any(row['phase'] == 'cancelled' and row['request_started'] for row in rows()))
    empty_preview = run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)')['memory_command_results'][0]['readback']
    no_op = run(empty_preview['apply_command'])['memory_command_results'][0]
    check('empty compaction reports unchanged', no_op['effect_status'] == 'unchanged' and not no_op['changed'])
    run('SET_INPUT_RECOVERY(legacy)')
    check('legacy can be restored after queued cancellation', runtime.INPUT_RECOVERY is None and runtime.INPUT_RECOVERY_MODE == 'legacy')
    run('SHOW_INPUT_RECOVERY()', False)
    check('no native guard touched', not Path('forbidden-native-input.txt').exists())
    proof = dict(status='passed', check_count=len(checks), checks=checks, fake_requests=len(calls),
                 real_api_calls=0, native_calls=0, restart_scope='fresh durable-store instance and volatile queue in guarded runtime; process-death lease test is separate')
finally:
    release.set()
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    if runtime.INPUT_RECOVERY is not None: runtime.INPUT_RECOVERY.close()
    assert not runtime.MODEL_IO.busy
Path('proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
'''


def run_smoke():
    harness.FIXTURE = delivery.FIXTURE.split('proof = {}', 1)[0] + SCENARIOS
    return harness.run_smoke()


if __name__ == '__main__': print(json.dumps(run_smoke(), indent=2))
