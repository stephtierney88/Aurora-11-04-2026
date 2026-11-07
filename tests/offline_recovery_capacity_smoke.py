"""Bounded pressure cycles through real recovery admission/receipts; fake I/O only."""
import json
import offline_input_recovery_smoke as recovery
import offline_delivery_smoke as delivery
import offline_responses_smoke as harness

SCENARIOS = r'''
try:
    run('SET_INPUT_RECOVERY(durable)')
    def capacity():
        return run('SHOW_INPUT_RECOVERY_STATUS()')['memory_command_results'][0]['readback']['summary']['capacity']
    check('normal production caps unchanged', capacity()['retained_limit']==1000 and capacity()['deduplication_limit']==10000)
    def fixture_bounds():
        runtime.INPUT_RECOVERY.max_rows = 4
        runtime.INPUT_RECOVERY.max_tombstones = 32
    fixture_bounds()
    originals = []
    cycles = 32
    restarts = 0
    transient_write_blocks = 0
    injected_write_blocks = 0
    def admit_fixture(text):
        global transient_write_blocks, injected_write_blocks
        # Append once. An explicitly inspected fixture retry must not append a new envelope.
        runtime.append_external_message_record(text, source='panel_conversation', client_id='capacity_fixture')
        path = runtime.INPUT_RECOVERY.path
        before = path.read_bytes() if path.exists() else None
        cursor = runtime.external_bridge_state['inbox_offset']
        for attempt in range(5):
            try:
                if not originals and attempt==0:
                    injected_write_blocks += 1
                    with patch('aurora_input_recovery.os.replace', side_effect=PermissionError('synthetic access-denied fixture')):
                        runtime.poll_external_inbox_messages()
                else:
                    runtime.poll_external_inbox_messages()
                return
            except PermissionError:
                transient_write_blocks += 1
                check('transient admission failure preserved file cursor and queue',
                      (path.read_bytes() if path.exists() else None)==before
                      and runtime.external_bridge_state['inbox_offset']==cursor
                      and runtime.get_input_queue_store().empty())
                if attempt==4: raise
                time.sleep(.1)  # Fixture-only explicit retry after evidence checks; no production retry change.
    for index in range(cycles):
        admit_fixture('CAPACITY_PRIVATE_FIXTURE_' + str(index))
        row = rows()[0]
        originals.append((row['text'], row['original_identity']))
        run(act('CANCEL_QUEUED_INPUT',row))
        preview = run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)')['memory_command_results'][0]['readback']
        receipt = run(preview['apply_command'])['memory_command_results'][0]
        check('cycle '+str(index)+': one identity preserved and payload removed', receipt['after']['compacted_count']==1
              and receipt['after']['summary']['capacity']['deduplication_used']==index+1
              and runtime.get_input_queue_store().empty())
        if (index+1)%8==0:
            restart_evidence(); fixture_bounds(); restarts+=1
            check('bounded restart '+str(restarts)+' preserves all duplicate fences',
                  all(not runtime.queue_recoverable_input(text,identity) for text,identity in originals)
                  and runtime.get_input_queue_store().empty())
    check('full index leaves retained slots usable', capacity()['deduplication_available']==0
          and capacity()['retained_available']==4 and capacity()['new_input_capacity']=='payload_dependent')
    for index in range(4):
        admit_fixture('RETAINED_CAPACITY_FIXTURE_' + str(index))
        row = rows()[-1]
        originals.append((row['text'],row['original_identity']))
        run(act('CANCEL_QUEUED_INPUT',row))
    before = runtime.INPUT_RECOVERY.path.read_bytes()
    preview = run('PREVIEW_INPUT_RECOVERY_COMPACTION(0,100)')['memory_command_results'][0]['readback']
    check('zero compaction explains full index', preview['selected_count']==0 and preview['capacity_blocked']
          and preview['selection_reason']=='deduplication_limit')
    result = run(preview['apply_command'])['memory_command_results'][0]
    check('blocked compaction is explicit unchanged receipt', not result['changed'] and result['effect_status']=='unchanged'
          and result['after']['capacity_blocked'] and result['after']['selection_reason']=='deduplication_limit'
          and runtime.INPUT_RECOVERY.path.read_bytes()==before)
    identity = dict(client_id='capacity-fixture',request_id='rejected',message_id='rejected')
    try: runtime.queue_recoverable_input('Must not evict anything',identity)
    except ValueError: pass
    else: raise AssertionError('Full retained store admitted new input')
    check('capacity rejection retains all evidence with empty queue', runtime.INPUT_RECOVERY.path.read_bytes()==before
          and runtime.get_input_queue_store().empty() and capacity()['new_input_capacity']=='retained_limit')
    restart_evidence(); fixture_bounds(); restarts+=1
    check('all 36 original envelopes remain suppressed after restart',
          all(not runtime.queue_recoverable_input(text,identity) for text,identity in originals))
    conflict_count = 0
    for text,identity in originals:
        try: runtime.queue_recoverable_input(text+' changed',identity)
        except ValueError: conflict_count+=1
    check('all retained and compacted changed-payload conflicts rejected',conflict_count==len(originals)
          and runtime.get_input_queue_store().empty())
    check('status contains no retained message text', 'CAPACITY_PRIVATE_FIXTURE_' not in json.dumps(capacity()))
    check('no extra turns or native calls', not calls and not Path('forbidden-native-input.txt').exists())
    proof = dict(status='passed',check_count=len(checks),checks=checks,pressure_cycles=cycles,
                 store_reopens=restarts,protected_original_identities=len(originals),real_api_calls=0,native_calls=0,
                 transient_write_blocks=transient_write_blocks,
                 injected_write_blocks=injected_write_blocks, observed_external_write_blocks=transient_write_blocks-injected_write_blocks,
                 scope='Production command/admission paths, reduced fixture ceilings, fresh store instances; not long-duration or full-process acceptance.')
finally:
    release.set()
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
    runtime.set_agent_running(False)
    if runtime.INPUT_RECOVERY is not None: runtime.INPUT_RECOVERY.close()
    assert not runtime.MODEL_IO.busy
Path('proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
'''

def run_smoke():
    harness.FIXTURE = delivery.FIXTURE.split('proof = {}',1)[0] + recovery.SCENARIOS.split('try:\n    run',1)[0] + SCENARIOS
    return harness.run_smoke()

if __name__ == '__main__': print(json.dumps(run_smoke(),indent=2))
