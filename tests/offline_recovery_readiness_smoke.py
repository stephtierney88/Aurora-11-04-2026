"""Guarded production readiness/ack admission, without native capture or network."""
import json
import offline_input_recovery_smoke as recovery
import offline_delivery_smoke as delivery
import offline_responses_smoke as harness

SCENARIOS = r'''
try:
    def state():
        return run('SHOW_INPUT_RECOVERY_STATUS()')['memory_command_results'][0]['readback']
    initial = state()
    check('legacy inspection does not open a store', initial['effective_mode']=='legacy' and runtime.INPUT_RECOVERY is None)
    path = Path('aurora_input_recovery.json')
    path.write_text('{broken fixture', encoding='utf-8')
    before = path.read_bytes()
    run('SET_INPUT_RECOVERY(durable)', False)
    failed = state()
    check('failed open preserves effective legacy and exact evidence', failed['effective_mode']=='legacy'
          and failed['store_state']=='not_open' and failed['diagnostic']['operation']=='open' and path.read_bytes()==before)
    version = failed['diagnostic']['version']
    command = 'ACK_INPUT_RECOVERY_DIAGNOSTIC(' + version + ')'
    run(command, False, user=False)
    run('LOCK_SETTING(execution)')
    run(command, False)
    run('UNLOCK_SETTING(execution)')
    with runtime.COMMAND_WORK.scope():
        runtime.COMMAND_WORK.cancel('cancel acknowledgement fixture')
        result = runtime.execute_input_recovery_command('ACK_INPUT_RECOVERY_DIAGNOSTIC', [version], True)
    check('cancelled acknowledgement changes nothing', result.get('cancelled') and not state()['diagnostic']['acknowledged'])
    run(command)
    check('acknowledgement never opens store or clears failure', state()['diagnostic']['acknowledged']
          and runtime.INPUT_RECOVERY is None and path.read_bytes()==before)
    check('duplicate acknowledgement is unchanged', not run(command)['memory_command_results'][0]['changed'])
    run('SET_INPUT_RECOVERY(durable)', False)
    run(command, False)
    check('new identical fault needs new acknowledgement', not state()['diagnostic']['acknowledged'])
    # Only the deliberately corrupt fixture file is replaced with a valid empty fixture.
    path.write_text(json.dumps(dict(schema_version='aurora_input_recovery_v1', rows={})), encoding='utf-8')
    run('SET_INPUT_RECOVERY(durable)')
    check('durable store ready and prior diagnostic preserved', state()['records_available'] and state()['diagnostic'] is not None)
    send('READINESS_PRIVATE_TEXT_82')
    row = rows()[0]
    runtime.INPUT_RECOVERY.claim([row['identity']])
    runtime.INPUT_RECOVERY.delivery([row['identity']], 'submitted', 'fixture-turn', 1, True)
    restart_evidence()
    check('restart uncertain status is explicit', state()['uncertain']==1 and runtime.get_input_queue_store().empty())
    before_disk = path.read_bytes()
    with patch('aurora_input_recovery.os.replace', side_effect=OSError('READINESS_PRIVATE_ERROR_82')):
        run(act('CANCEL_QUEUED_INPUT', rows()[0]), False)
    diagnostic = state()['diagnostic']
    check('publication diagnostic contains no text or exception message', diagnostic['operation']=='write'
          and 'READINESS_PRIVATE' not in json.dumps(state()) and path.read_bytes()==before_disk)
    run('ACK_INPUT_RECOVERY_DIAGNOSTIC(' + diagnostic['version'] + ')')
    check('ack preserves unresolved row and failed write', state()['uncertain']==1 and state()['last_write']=='failed'
          and path.read_bytes()==before_disk and runtime.get_input_queue_store().empty() and not calls)
    run(act('RETRY_INPUT', rows()[0]), False)
    check('diagnostic ack grants no uncertain retry permission', rows()[0]['phase']=='uncertain' and not calls)
    run(act('CANCEL_QUEUED_INPUT', rows()[0]))
    check('successful later write reports success without forgetting diagnostic', state()['last_write']=='succeeded'
          and state()['diagnostic']['version']==diagnostic['version'])
    exported = runtime.build_control_panel_state_snapshot()['conversation_io']['input_recovery_readiness']
    check('shared export matches command authority', exported==state())
    run('SET_INPUT_RECOVERY(legacy)')
    check('legacy restored without deleting evidence', not state()['records_available'] and path.exists())
    check('no native guard touched', not Path('forbidden-native-input.txt').exists())
    proof = dict(status='passed', check_count=len(checks), checks=checks, real_api_calls=0, native_calls=0)
finally:
    release.set()
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    if runtime.INPUT_RECOVERY is not None: runtime.INPUT_RECOVERY.close()
    assert not runtime.MODEL_IO.busy
Path('proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
'''

def run_smoke():
    harness.FIXTURE = delivery.FIXTURE.split('proof = {}', 1)[0] + recovery.SCENARIOS.split('try:\n    run', 1)[0] + SCENARIOS
    return harness.run_smoke()

if __name__ == '__main__': print(json.dumps(run_smoke(), indent=2))
