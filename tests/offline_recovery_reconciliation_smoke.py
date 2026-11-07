"""Production command/queue/delivery paths with synthetic provider and disk faults."""
import json
import offline_delivery_smoke as delivery
import offline_responses_smoke as harness

SCENARIOS = r'''
import queue
from unittest.mock import patch
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def run(command,success=True,user=True):
    result=runtime.execute_command_entry(dict(command=command,is_user=user,source='user' if user else 'assistant_response'))
    check(command.split('(')[0]+' expected '+str(success),result['success'] is success)
    return result
def row():return run('SHOW_INPUT_RECOVERY()')['memory_command_results'][0]['readback']['entries'][-1]
def preview():
    current=row()
    return run('PREVIEW_INPUT_RECONCILIATION('+current['entry_id']+','+current['version']+')',user=False)['memory_command_results'][0]['readback']
def lost_terminal(text):
    runtime.SEND_TO_MODEL=False
    send(text)
    recovery=runtime.get_input_recovery();publish=recovery._publish
    def fail_terminal(rows,**kwargs):
        if list(rows.values())[-1]['phase']=='responded':raise OSError('fixture terminal write failure')
        return publish(rows,**kwargs)
    runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=True
    with patch.object(recovery,'_publish',fail_terminal):runtime.handle_queued_input('','')
    runtime.SEND_TO_MODEL=False
    return recovery
try:
    check('legacy recovery remains default',runtime.INPUT_RECOVERY_MODE=='legacy')
    run('SET_INPUT_RECOVERY(durable)')
    recovery=lost_terminal('RECONCILIATION_PRIVATE_FIXTURE_TEXT')
    check('terminal disk failure does not discard actual response or resend',row()['phase']=='submitted' and len(calls)==1)
    check('failed terminal durability is visible',bool(runtime.runtime_state.get('input_recovery_error')))
    before=recovery.path.read_bytes();p=preview()
    check('preview observes terminal evidence without writing',p['after']['phase']=='responded' and recovery.path.read_bytes()==before)
    check('preview excludes message text and local paths','RECONCILIATION_PRIVATE_FIXTURE_TEXT' not in json.dumps(p) and str(Path.cwd()) not in json.dumps(p))
    apply=p['apply_command']
    run(apply,success=False,user=False)
    runtime.SEND_TO_MODEL=True;run(apply,success=False);runtime.SEND_TO_MODEL=False
    with runtime.MODEL_WORK.scope():run(apply,success=False)
    run('LOCK_SETTING(execution)');run(apply,success=False);run('UNLOCK_SETTING(execution)')
    args=[p['entry_id'],p['version'],p['evidence_version']]
    with runtime.COMMAND_WORK.scope():
        runtime.COMMAND_WORK.cancel('fixture cancelled reconciliation')
        cancelled=runtime.execute_input_recovery_command('RECONCILE_INPUT_DELIVERY',args,True)
    check('cancelled scope cannot write',cancelled.get('cancelled') is True and recovery.path.read_bytes()==before)
    with patch('aurora_input_recovery.os.replace',side_effect=OSError('fixture reconcile disk failure')):
        failed=run(apply,success=False)['memory_command_results'][0]
    check('write failure reports uncertainty and preserves file',failed['effect_status']=='failed_uncertain' and recovery.path.read_bytes()==before)
    done=run(apply)['memory_command_results'][0]
    check('exact reconciliation changes bookkeeping only',done['before']['phase']=='submitted' and done['after']['phase']=='responded' and done['changed'] and len(calls)==1 and runtime.get_input_queue_store().empty())
    run(apply,success=False)
    current=row()
    run('RETRY_INPUT('+current['entry_id']+','+current['version']+',allow_uncertain)',success=False)
    check('responded input cannot be manually resent as recovery',len(calls)==1)

    recovery=lost_terminal('Restart reconciliation fixture')
    old=preview();recovery.close();runtime.INPUT_RECOVERY=None;runtime.agent_state.queued_user_input=queue.Queue()
    recovery=runtime.get_input_recovery()
    check('restart holds uncertain attempt without auto replay',row()['phase']=='uncertain' and not runtime.get_input_queue_store().qsize() and len(calls)==2)
    run(old['apply_command'],success=False)
    p=preview();run(p['apply_command'])
    check('new epoch preview reconciles the same original turn',row()['phase']=='responded' and len(calls)==2)

    recovery=lost_terminal('Lost local reconciliation acknowledgement')
    p=preview();publish=recovery._publish
    def commit_then_lose_ack(rows,**kwargs):
        publish(rows,**kwargs)
        raise OSError('fixture after atomic publication')
    with patch.object(recovery,'_publish',commit_then_lose_ack):
        uncertain=run(p['apply_command'],success=False)['memory_command_results'][0]
    check('post-commit lost acknowledgement stays uncertain until reread',uncertain['effect_status']=='failed_uncertain' and row()['phase']=='responded' and len(calls)==3)
    run(p['apply_command'],success=False)
    check('stale retry cannot repeat model work',len(calls)==3 and runtime.get_input_queue_store().empty())

    recovery=lost_terminal('Conflicting receipt fixture')
    p=preview();events=read_jsonl_from(Path(runtime.external_bridge_log_path))[0]
    terminal=next(event for event in reversed(events) if event.get('event')=='message_model_delivery' and event.get('inference_request_id')==p['turn_id'])
    terminal=dict(terminal,phase='cancelled');event=terminal.pop('event');runtime.write_external_bridge_log(event,**terminal)
    before=recovery.path.read_bytes();run(p['apply_command'],success=False)
    check('conflicting terminal receipts stay unresolved',row()['phase']=='submitted' and recovery.path.read_bytes()==before and len(calls)==4)
    # The fixture ends by reopening evidence, then preserving it cancelled; no provider retry.
    recovery.close();runtime.INPUT_RECOVERY=None;recovery=runtime.get_input_recovery();current=row()
    run('CANCEL_QUEUED_INPUT('+current['entry_id']+','+current['version']+')')
    run('SET_INPUT_RECOVERY(legacy)')
    check('legacy mode and all prior controls remain available',runtime.INPUT_RECOVERY is None and runtime.INPUT_RECOVERY_MODE=='legacy')
    check('native input/capture guard untouched',not Path('forbidden-native-input.txt').exists())
    proof=dict(status='passed',check_count=len(checks),checks=checks,fake_requests=len(calls),real_api_calls=0,native_input_calls=0,real_capture_calls=0)
finally:
    release.set();runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=False;runtime.set_agent_running(False)
    if runtime.INPUT_RECOVERY is not None:runtime.INPUT_RECOVERY.close()
    assert not runtime.MODEL_IO.busy
Path('proof.json').write_text(json.dumps(dict(proof,owned_threads_stopped=True),indent=2),encoding='utf-8')
'''


def run_smoke():
    harness.FIXTURE=delivery.FIXTURE.split('proof = {}',1)[0]+SCENARIOS
    return harness.run_smoke()


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
