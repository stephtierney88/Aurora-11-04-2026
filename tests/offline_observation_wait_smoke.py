"""Bounded observation through real commands, receipts and frame publication."""
import json
import offline_turn_flow_smoke as flow

SCENARIOS = r'''
    runtime.cancel_capture_requests('observation fixture start')
    runtime.CAPTURE_PROVENANCE_POLICY=runtime.CAPTURE_GEOMETRY_POLICY='verified'
    runtime.CAPTURE_MODE='request_only'
    runtime.request_demand_capture('baseline',0)
    synthetic_capture()
    def baseline_id(): return runtime.CAPTURE_SERVICE.latest['provenance']['frame_id']
    def pump_observation(hashes=None, cancel=False, supersede=False, lock_capture=False):
        global capture_count
        hashes=list(hashes or [])
        deadline=time.monotonic()+4
        owned_seen=False
        while runtime.active_command_queue.unfinished_tasks and time.monotonic()<deadline:
            pending=runtime.CAPTURE_SERVICE.snapshot()['pending']
            if pending and pending['reason']=='bounded_screen_change':
                owned_seen=True
                if cancel:
                    runtime.cancel_active_work_command([],True)
                    cancel=False
                elif lock_capture:
                    runtime.RUNTIME_SETTING_LOCKS['screenshot_interval']=True
                    lock_capture=False
                elif supersede:
                    runtime.request_demand_capture('operator_newer',2)
                    supersede=False
                elif hashes:
                    stamp=runtime.CAPTURE_SERVICE.finish(runtime.CAPTURE_SERVICE.begin('synthetic_observation'))
                    # Reuse the baseline's exact verified target/transform.
                    geometry=FrameGeometry((320,240),(160,120),
                        CaptureTarget('foreground',(-320,-120,0,120),(-1920,-120,1920,1080),(-320,-120,0,120),12,34,144),
                        'per_monitor_v2','verified','resize_and_later_overlays')
                    context.drawing_output_queue.put(runtime.CapturedFrame(Image.new('RGB',(160,120),'navy'),stamp,hashes.pop(0),geometry))
                    runtime.drain_runtime_processed_capture(context)
                    capture_count+=1
            time.sleep(.005)
        check('observation worker returns within its bound',not runtime.active_command_queue.unfinished_tasks)
        return wait_results(),owned_seen

    check('task-flow admits bounded observation without granting input',runtime.evaluate_task_flow_permission(
        'OBSERVE_SCREEN_CHANGE('+baseline_id()+')','game','transition','',[])[0]=='allow')
    previous_mode=runtime.TASK_CONTINUATION_MODE
    runtime.TASK_CONTINUATION_MODE='bounded'
    check('dynamic prompt documents observation and semantic limit','OBSERVE_SCREEN_CHANGE' in runtime.build_base_system_prompt())
    runtime.TASK_CONTINUATION_MODE=previous_mode
    before_events=len(events)
    generation=runtime.CAPTURE_SERVICE.generation
    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.5,0.1)',is_user=True)
    result,seen=pump_observation(['same-fixture-pixels','changed-observation'])
    observation=result['observation_results'][0]
    check('actual worker returns exact changed frame receipt',seen and result['success'] and observation['status']=='changed'
          and observation['samples']==2 and observation['frame_id']==baseline_id())
    check('terminal receipt does not request an extra capture',runtime.CAPTURE_SERVICE.generation==generation+2
          and not runtime.CAPTURE_SERVICE.pending)
    check('fresh observation makes ordinary scheduler ready',runtime.evaluate_turn_scheduler()['should_run'])
    check('observation sends no input',len(events)==before_events)
    runtime.clear_turn_scheduler_command_result_pending()

    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.35,0.1)',is_user=True)
    result,_=pump_observation(['changed-observation']*4)
    check('unchanged frames return explicit bounded timeout',result['success'] and result['observation_results'][0]['status']=='timeout'
          and result['observation_results'][0]['condition_met'] is False)
    check('timeout with fresh samples still permits observation continuation',runtime.evaluate_turn_scheduler()['should_run'])
    runtime.clear_turn_scheduler_command_result_pending()

    old_generation=runtime.CAPTURE_SERVICE.generation
    result=operator('OBSERVE_SCREEN_CHANGE('+('0'*32)+',0.25,0.1)')
    check('stale exact frame rejected without new capture',not result['success'] and runtime.CAPTURE_SERVICE.generation==old_generation)
    for invalid in ('OBSERVE_SCREEN_CHANGE('+baseline_id()+',nan)',
                    'PYAG:press(a); OBSERVE_SCREEN_CHANGE('+baseline_id()+')',
                    'OBSERVE_SCREEN_CHANGE('+baseline_id()+'); PYAG:press(a)',
                    'QUEUE_PENDING(OBSERVE_SCREEN_CHANGE('+baseline_id()+'))'):
        try: runtime.prepare_command_batch(invalid)
        except ValueError: pass
        else: raise AssertionError('Invalid observation batch admitted')
    check('invalid and dependent batches rejected before input',len(events)==before_events)

    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.5,0.1)',is_user=True)
    result,_=pump_observation(cancel=True)
    check('cancel interrupts actual observation and clears owned request',result['cancelled']
          and result['observation_results'][0]['status']=='cancelled' and not runtime.CAPTURE_SERVICE.pending)
    runtime.cancel_capture_requests('post cancel fixture reset')
    runtime.request_demand_capture('new baseline',0)
    synthetic_capture()

    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.5,0.1)',is_user=True)
    result,_=pump_observation(supersede=True)
    check('supersession preserves operator newer capture',not result['success'] and result['observation_results'][0]['status']=='superseded'
          and runtime.CAPTURE_SERVICE.pending['reason']=='operator_newer')
    runtime.cancel_capture_requests('post supersession reset')
    runtime.request_demand_capture('new baseline',0)
    synthetic_capture()

    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.25,0.1)',is_user=True)
    result,_=pump_observation()
    check('missing publication becomes explicit capture failure',not result['success'] and result['observation_results'][0]['status']=='capture_failed')
    check('capture failure does not loop model or pretend old pixels are fresh',runtime.evaluate_turn_scheduler()['state']=='capture_failed')
    runtime.cancel_capture_requests('post failure reset')
    runtime.CAPTURE_MODE='heartbeat'
    result=operator('OBSERVE_SCREEN_CHANGE('+baseline_id()+')')
    check('unsupported capture mode remains unchanged',not result['success'] and runtime.CAPTURE_MODE=='heartbeat')
    runtime.CAPTURE_MODE='request_only'
    runtime.RUNTIME_SETTING_LOCKS['screenshot_interval']=True
    result=operator('OBSERVE_SCREEN_CHANGE('+baseline_id()+')')
    check('capture setting lock enforced for operator too',not result['success'])
    runtime.RUNTIME_SETTING_LOCKS['screenshot_interval']=False
    check('observation fixture leaves no pending capture',not runtime.CAPTURE_SERVICE.pending)

    runtime.cancel_capture_requests('capture-lock interruption baseline')
    runtime.request_demand_capture('new baseline',0)
    synthetic_capture()
    runtime.enqueue_or_execute_command('OBSERVE_SCREEN_CHANGE('+baseline_id()+',0.5,0.1)',is_user=True)
    result,_=pump_observation(lock_capture=True)
    check('new capture lock cancels in-flight wait with partial evidence',result['cancelled']
          and result['observation_results'][0]['requested_samples']==1)
    check('cancelled wait leaves no orphan scheduler boundary',not runtime.CAPTURE_SERVICE.pending
          and not runtime.runtime_state['turn_scheduler_pending_command_result'])
    runtime.RUNTIME_SETTING_LOCKS['screenshot_interval']=False

    # Model-origin command and the next request's exact typed readback, with fake transport.
    runtime.cancel_capture_requests('model observation setup')
    runtime.request_demand_capture('model baseline',0)
    synthetic_capture()
    operator('SET_TASK_CONTINUATION(bounded); SET_TASK_MAX_MODEL_TURNS(3); SET_TASK_MAX_SECONDS(30); SET_READBACK_SCOPE(reviewed); SET_READBACK_WAKE(on)')
    observation_calls=[]
    def observation_provider(packet,token):
        token.check()
        observation_calls.append(packet)
        assert len(observation_calls)<=2
        if len(observation_calls)==1:
            content='Scene: transition\nObservation: A synthetic transition is visible.\nExecuted Commands:\nOBSERVE_SCREEN_CHANGE('+baseline_id()+',0.5,0.1)'
        else:
            readbacks=[json.loads(m['content'].split('\n',1)[1]) for m in packet['payload']['messages']
                       if isinstance(m.get('content'),str) and m['content'].startswith('Command execution readbacks')]
            observed=[r['results']['observation_results'][0] for manifest in readbacks for r in manifest['records']
                      if 'observation_results' in r.get('results',{})]
            check('next model request receives exact typed observation receipt',len(observed)==1 and observed[0]['status']=='changed'
                  and observed[0]['frame_id']==baseline_id() and observed[0]['condition_met'] is True)
            check('receipt follow-up includes the same newly published frame',runtime.runtime_state['last_prompt_diagnostics']['capture_frame']['provenance']['frame_id']==observed[0]['frame_id'])
            content='Observation: I inspected the changed frame; semantic completion remains unknown.'
        return SimpleNamespace(status_code=200,json=lambda:{'model':'fixture-provider','choices':[{'message':{'content':content}}]}),'api_key','guarded observation provider'
    runtime.perform_model_http_request=observation_provider
    runtime.get_input_queue_store().put('Observe a change in the fixture, then describe the evidence without sending input.')
    check('bounded fake-model request starts',runtime.maybe_run_due_inference_turn())
    result,_=pump_observation(['same-fixture-pixels','model-changed'])
    check('assistant command reaches actual worker and receipt',result['success'] and result['is_user'] is False
          and result['observation_results'][0]['status']=='changed')
    check('observation continues model without heartbeat wait',runtime.maybe_run_due_inference_turn())
    check('no idle model loop after observation readback',not runtime.maybe_run_due_inference_turn() and len(observation_calls)==2)
    check('model-directed observation still sends no input',len(events)==before_events)
    runtime.perform_model_http_request=provider
'''

if __name__=='__main__':
    marker='    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False\n    check("pause prevents continuation"'
    assert flow.SCENARIOS.count(marker)==1
    scenario=flow.SCENARIOS.replace(marker,SCENARIOS+'\n'+marker)
    scenario=scenario.replace('"requests":calls,', '"requests":calls, "observation_model_requests":len(observation_calls),')
    flow.harness.COPY_FILES=(*flow.harness.COPY_FILES,'aurora2_init.txt')
    flow.harness.FIXTURE=flow.CONTRACT_IMPORT_GUARD+flow.CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0]+scenario
    print(json.dumps(flow.harness.run_smoke(),indent=2))
