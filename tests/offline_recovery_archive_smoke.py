"""Real read-only archive command admission/receipts with guarded native/network I/O."""
import json
import offline_input_recovery_smoke as recovery
import offline_delivery_smoke as delivery
import offline_responses_smoke as harness

SCENARIOS=r'''
try:
    run('PREVIEW_INPUT_RECOVERY_ARCHIVE()',False)
    run('SET_INPUT_RECOVERY(durable)')
    empty=run('PREVIEW_INPUT_RECOVERY_ARCHIVE()')['memory_command_results'][0]
    check('empty candidate is read-only with no archive',empty['effect_status']=='observed' and not empty['changed']
          and empty['readback']['archive_state']=='not_created' and empty['readback']['selected_count']==0)
    send('ARCHIVE_PRIVATE_FIXTURE')
    row=rows()[0]
    run(act('CANCEL_QUEUED_INPUT',row))
    preview=run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)')['memory_command_results'][0]['readback']
    run(preview['apply_command'])
    send('Pending input must not be archived')
    before=runtime.INPUT_RECOVERY.path.read_bytes()
    before_queue=list(runtime.get_input_queue_store().queue)
    def inspect(user=True):
        return run('PREVIEW_INPUT_RECOVERY_ARCHIVE(1)',user=user)['memory_command_results'][0]
    result=inspect()
    manifest=result['readback']
    check('preview reports bounded manifest and hypothetical savings',manifest['selected_count']==1
          and manifest['segment_bytes']>0 and manifest['candidate_fits'] and manifest['actual_slots_freed']==0
          and manifest['hypothetical_slots_freed']==1 and not manifest['archive_activation_available'])
    check('preview creates no mutation and preserves queued input',not result['changed']
          and runtime.INPUT_RECOVERY.path.read_bytes()==before and list(runtime.get_input_queue_store().queue)==before_queue)
    check('readback contains no original private message', 'ARCHIVE_PRIVATE_FIXTURE' not in json.dumps(manifest))
    check('assistant can inspect through shared readonly contract',inspect(False)['readback']==manifest)
    run('LOCK_SETTING(execution)')
    check('read-only preview works with execution locked',inspect()['readback']==manifest)
    run('UNLOCK_SETTING(execution)')
    run('PREVIEW_INPUT_RECOVERY_ARCHIVE(0)',False)
    run('PREVIEW_INPUT_RECOVERY_ARCHIVE(1,extra)',False)
    with runtime.COMMAND_WORK.scope():
        runtime.COMMAND_WORK.cancel('cancel archive preview fixture')
        cancelled=runtime.execute_input_recovery_command('PREVIEW_INPUT_RECOVERY_ARCHIVE',['1'],True)
    check('cancelled preview has no candidate',cancelled.get('cancelled') and 'readback' not in cancelled)
    check('original compacted duplicate stays suppressed',not runtime.queue_recoverable_input(row['text'],row['original_identity']))
    pending=rows()[0]; run(act('CANCEL_QUEUED_INPUT',pending))
    restart_evidence()
    fresh=inspect()['readback']
    check('restart changes source handle and preserves segment digest',fresh['source_version']!=manifest['source_version']
          and fresh['segment_sha256']==manifest['segment_sha256'])
    check('restart duplicate protection intact',not runtime.queue_recoverable_input(row['text'],row['original_identity']))
    state=runtime.build_control_panel_state_snapshot()
    check('runtime exposes agreed release identity',state['build']['release_id']=='preview-2026.11.06-r84'
          and state['build']['recovery_archive']=='preview_only')
    check('no archive files or native/provider calls',not list(Path('.').glob('*segment*')) and not calls
          and not Path('forbidden-native-input.txt').exists())
    proof=dict(status='passed',checks=checks,check_count=len(checks),real_api_calls=0,native_calls=0)
finally:
    release.set()
    runtime.SEND_TO_MODEL=runtime.ENABLE_MODEL_RESPONSES=False
    runtime.set_agent_running(False)
    if runtime.INPUT_RECOVERY is not None: runtime.INPUT_RECOVERY.close()
    assert not runtime.MODEL_IO.busy
Path('proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
'''

def run_smoke():
    harness.FIXTURE=delivery.FIXTURE.split('proof = {}',1)[0]+recovery.SCENARIOS.split('try:\n    run',1)[0]+SCENARIOS
    return harness.run_smoke()

if __name__=='__main__': print(json.dumps(run_smoke(),indent=2))
