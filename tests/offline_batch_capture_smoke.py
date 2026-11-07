"""Real command worker and receipt/capture scheduler; synthetic native/provider I/O."""
import json
import offline_turn_flow_smoke as flow

SCENARIOS = r'''
    def bounded_prompt():
        previous=runtime.TASK_CONTINUATION_MODE
        try:
            runtime.TASK_CONTINUATION_MODE='bounded'
            return runtime.build_base_system_prompt()
        finally:
            runtime.TASK_CONTINUATION_MODE=previous

    runtime.cancel_capture_requests('start batch fixture')
    check('shared operator setting selects batch-end policy', operator('SET_CAPTURE_COMMAND_POLICY(batch_end)')['success'])
    old_stamp = runtime.CAPTURE_SERVICE.finish(runtime.CAPTURE_SERVICE.begin('pre_batch'))
    generation = runtime.CAPTURE_SERVICE.generation
    hold_entered.clear()
    runtime.enqueue_or_execute_command('REQUEST_SCREENSHOT_CAPTURE(first,0); PYAG:hold(a,0.2); REQUEST_DEMAND_CAPTURE(second,0.04)', is_user=True)
    assert hold_entered.wait(2)
    check('explicit capture does not start inside unfinished batch', runtime.CAPTURE_SERVICE.generation == generation)
    result = wait_results()
    check('two explicit requests and automatic input share one capture', runtime.CAPTURE_SERVICE.generation == generation+1
          and result['capture_batch']['requests']==2 and runtime.runtime_state['last_batch_capture']['deferred_requests']==2)
    boundary = runtime.runtime_state['turn_scheduler_post_action_boundary']
    check('pre-batch pixels never satisfy post-batch observation', not runtime.CAPTURE_SERVICE.is_fresh({'provenance':old_stamp.to_dict()}, boundary))
    check('post-batch delay preserves explicit settle', runtime.runtime_state['last_batch_capture']['settle_seconds'] >= .04)
    check('scheduler labels waiting capture', runtime.evaluate_turn_scheduler()['state']=='waiting_capture')
    synthetic_capture()
    check('published new acquisition satisfies exact boundary', runtime.CAPTURE_SERVICE.is_fresh(runtime.runtime_state['last_capture_frame'], boundary))
    check('fresh receipt capture makes scheduler ready', runtime.evaluate_turn_scheduler()['state']=='ready')
    runtime.cancel_capture_requests('reset capture case')

    generation=runtime.CAPTURE_SERVICE.generation
    result=operator('REQUEST_SCREENSHOT_CAPTURE(only,0); REQUEST_SCREENSHOT_CAPTURE(again,0)')
    check('capture-only batch wakes once without input', runtime.CAPTURE_SERVICE.generation==generation+1 and result['capture_batch']['requests']==2)
    runtime.cancel_capture_requests('reset capture case')
    runtime.request_demand_capture('independent-long-settle', .25)
    old_due=runtime.CAPTURE_SERVICE.snapshot()['pending']['due_at_monotonic']
    operator('REQUEST_SCREENSHOT_CAPTURE(short,0)')
    check('batch coalescing cannot shorten independent pending settle', runtime.CAPTURE_SERVICE.snapshot()['pending']['due_at_monotonic']>=old_due)
    runtime.cancel_capture_requests('reset capture case')

    fail_click=True
    generation=runtime.CAPTURE_SERVICE.generation
    result=operator('REQUEST_SCREENSHOT_CAPTURE(before_failure,0); PYAG:click(1,2,left); REQUEST_SCREENSHOT_CAPTURE(blocked,0)')
    fail_click=False
    check('partial failure observes once and blocked tail is not requested', not result['success'] and result['capture_batch']['requests']==1
          and len(result['blocked_commands'])==1 and runtime.CAPTURE_SERVICE.generation==generation+1)
    runtime.cancel_capture_requests('reset capture case')

    hold_entered.clear()
    runtime.enqueue_or_execute_command('REQUEST_SCREENSHOT_CAPTURE(before_cancel,0); PYAG:hold(a,5)',is_user=True)
    assert hold_entered.wait(2)
    generation=runtime.CAPTURE_SERVICE.generation
    runtime.cancel_active_work_command([],True)
    result=wait_results()
    check('cancelled deferred request cannot resurrect capture', result['cancelled'] and not runtime.CAPTURE_SERVICE.snapshot()['pending']
          and runtime.CAPTURE_SERVICE.generation==generation and runtime.runtime_state['last_batch_capture']['selected_batches']==0)
    check('cancel still releases owned input', runtime.HELD_INPUTS.snapshot()['held_count']==0)

    runtime.enqueue_or_execute_command('REQUEST_SCREENSHOT_CAPTURE(old_lifecycle,0)',is_user=True)
    deadline=time.monotonic()+2
    while runtime.active_command_queue.unfinished_tasks and time.monotonic()<deadline: time.sleep(.005)
    runtime.cancel_capture_requests('replace lifecycle before receipt')
    wait_results()
    check('old lifecycle receipt cannot start a capture', not runtime.CAPTURE_SERVICE.snapshot()['pending'])

    runtime.active_command_queue=None
    try:
        generation=runtime.CAPTURE_SERVICE.generation
        result=runtime.enqueue_or_execute_command('REQUEST_SCREENSHOT_CAPTURE(direct,0)',is_user=True)
        check('synchronous command path also publishes deferred capture', runtime.CAPTURE_SERVICE.generation==generation+1)
    finally:
        runtime.active_command_queue=worker_queue
    runtime.cancel_capture_requests('reset capture case')
    runtime.DEMAND_CAPTURE_ENABLED=runtime.runtime_state['demand_capture_enabled']=False
    generation=runtime.CAPTURE_SERVICE.generation
    result=operator('REQUEST_SCREENSHOT_CAPTURE(disabled,0)')
    check('disabled demand remains disabled in batch mode', runtime.CAPTURE_SERVICE.generation==generation and result['capture_batch']['requests']==0)
    runtime.DEMAND_CAPTURE_ENABLED=runtime.runtime_state['demand_capture_enabled']=True

    old_settle=runtime.TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS
    runtime.TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS=.12
    check('operator can select explicit-only settle variant', operator('SET_CAPTURE_COMMAND_POLICY(batch_end_explicit)')['success'])
    prompt=bounded_prompt()
    check('effective policy reaches actual model system prompt', 'policy=batch_end_explicit' in prompt
          and 'zero if omitted' in prompt and 'can produce an extra capture' not in prompt)
    generation=runtime.CAPTURE_SERVICE.generation
    result=operator('REQUEST_SCREENSHOT_CAPTURE(only,.01); REQUEST_DEMAND_CAPTURE(again,.03)')
    info=runtime.runtime_state['last_batch_capture']
    check('capture-only variant coalesces two requests once', runtime.CAPTURE_SERVICE.generation==generation+1)
    check('capture-only receipt proves explicit settle without input floor', info['settle_seconds']==.03
          and info['explicit_only_batches']==1 and info['default_settle_batches']==0)
    synthetic_capture()
    check('explicit-only acquisition satisfies scheduler boundary', runtime.evaluate_turn_scheduler()['should_run'])
    runtime.cancel_capture_requests('reset explicit variant')
    operator('REQUEST_SCREENSHOT_CAPTURE(zero,0)')
    check('zero explicit delay is preserved', runtime.runtime_state['last_batch_capture']['settle_seconds']==0)
    runtime.cancel_capture_requests('reset explicit variant')
    operator('UPDATE_CONTEXT(capture timing fixture); REQUEST_SCREENSHOT_CAPTURE(mixed,0)')
    check('mixed memory batch conservatively retains input floor', runtime.runtime_state['last_batch_capture']['settle_seconds']==.12)
    runtime.cancel_capture_requests('reset explicit variant')
    operator('PYAG:press(a); REQUEST_SCREENSHOT_CAPTURE(after_input,0)')
    check('input batch retains post-action floor', runtime.runtime_state['last_batch_capture']['settle_seconds']==.12
          and runtime.runtime_state['last_batch_capture']['default_settle_batches']==1)
    runtime.cancel_capture_requests('reset explicit variant')
    runtime.request_demand_capture('independent-delay',.25)
    old_due=runtime.CAPTURE_SERVICE.snapshot()['pending']['due_at_monotonic']
    operator('REQUEST_SCREENSHOT_CAPTURE(explicit_zero,0)')
    check('explicit-only variant cannot shorten existing pending delay', runtime.CAPTURE_SERVICE.snapshot()['pending']['due_at_monotonic']>=old_due)
    runtime.cancel_capture_requests('reset explicit variant')
    fail_click=True
    result=operator('REQUEST_SCREENSHOT_CAPTURE(before_failure,0); PYAG:click(1,2,left); REQUEST_SCREENSHOT_CAPTURE(blocked,0)')
    fail_click=False
    check('failed batch retains floor and observes partial effects once', not result['success']
          and runtime.runtime_state['last_batch_capture']['settle_seconds']==.12 and result['capture_batch']['requests']==1)
    runtime.cancel_capture_requests('reset explicit variant')
    hold_entered.clear()
    runtime.enqueue_or_execute_command('REQUEST_SCREENSHOT_CAPTURE(before_cancel,0); PYAG:hold(a,5)',is_user=True)
    assert hold_entered.wait(2)
    runtime.cancel_active_work_command([],True)
    wait_results()
    check('explicit-only variant cancellation discards pending capture', not runtime.CAPTURE_SERVICE.snapshot()['pending']
          and runtime.HELD_INPUTS.snapshot()['held_count']==0)
    result=operator('SET_CAPTURE_COMMAND_POLICY(batch_end); REQUEST_SCREENSHOT_CAPTURE(latched,0)')
    check('capture policy is latched before an in-batch change', result['capture_batch']['policy']=='batch_end_explicit')
    runtime.cancel_capture_requests('reset latched variant')
    result=operator('REQUEST_SCREENSHOT_CAPTURE(next_batch,0)')
    check('following batch uses original batch-end floor', result['capture_batch']['policy']=='batch_end'
          and runtime.runtime_state['last_batch_capture']['settle_seconds']==.12)
    check('original batch-end prompt retains floor guidance', 'including to capture-only batches' in bounded_prompt())
    runtime.cancel_capture_requests('reset original batch-end')
    runtime.TURN_SCHEDULER_POST_ACTION_SETTLE_SECONDS=old_settle

    operator('SET_CAPTURE_COMMAND_POLICY(legacy)')
    generation=runtime.CAPTURE_SERVICE.generation
    operator('PYAG:press(a); REQUEST_SCREENSHOT_CAPTURE(legacy,0)')
    check('legacy immediate plus automatic request behavior remains', runtime.CAPTURE_SERVICE.generation==generation+2)
    runtime.cancel_capture_requests('diagnostic reset')
    runtime.runtime_state['last_turn_completed_at_epoch']=time.time()
    runtime.runtime_state['turn_scheduler_last_submitted_capture_counter']=runtime.runtime_state['turn_scheduler_capture_counter']
    check('request-only idle explicitly reports no scheduled wake', runtime.evaluate_turn_scheduler()['state']=='quiescent')
    runtime.TURN_SCHEDULER_HEARTBEAT_SECONDS=30
    check('configured future heartbeat reports timer wait', runtime.evaluate_turn_scheduler()['state']=='waiting_timer')
    runtime.TURN_SCHEDULER_HEARTBEAT_SECONDS=0
    check('new operator input can still wake quiescent scheduler', runtime.evaluate_turn_scheduler(input_pending=True)['should_run'])
'''


if __name__ == '__main__':
    marker='    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False\n    check("pause prevents continuation"'
    assert flow.SCENARIOS.count(marker)==1
    scenario=flow.SCENARIOS.replace(marker, '    worker_queue=runtime.active_command_queue\n'+SCENARIOS+'\n'+marker)
    flow.harness.COPY_FILES=(*flow.harness.COPY_FILES,'aurora2_init.txt')
    flow.harness.FIXTURE=flow.CONTRACT_IMPORT_GUARD+flow.CONTRACT_FIXTURE.rsplit('runtime.main()',1)[0]+scenario
    print(json.dumps(flow.harness.run_smoke(),indent=2))
