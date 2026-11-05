"""Everyday operator/assistant commands against a disposable, guarded full runtime.

No GUI, native input/capture, credentials, model or embedding request is used.
The fixture executes real parsing, handlers, memory structures and receipt ingestion.
"""
import json
import offline_responses_smoke as harness
from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

SCENARIOS = r'''
import copy
import json
from aurora_history_controls import build_update_message_command, message_revision, history_text
from aurora_control_plane import read_jsonl_from
runtime.display_message = lambda *a, **k: None
runtime.maybe_run_game_focus_recovery = lambda *a, **k: None
runtime.active_command_queue = None
runtime.EXECUTION_MODE = 'assist'
checks, commands_seen = [], set()
def check(name, condition, evidence=None):
    assert condition, (name, evidence)
    checks.append(name)
def run(command, success=True, ingest=False):
    identity = 'basic-' + str(len(checks))
    result = runtime.execute_command_entry(dict(command=command, is_user=True, request_id=identity,
        client_id='basic-fixture', message_id=identity, source='user'))
    check(command[:110], result['success'] is success, result)
    commands_seen.update(row[1] for row in runtime.prepare_command_batch(command)) if result['expanded_commands'] else None
    if ingest:
        runtime.ingest_command_result(result)
        rows, _ = read_jsonl_from(Path('aurora_command_execution_log.jsonl'))
        receipt = next(row for row in reversed(rows) if row.get('request_id') == identity)
        check('memory result survives persisted receipt and request identity',
              receipt.get('memory_command_results') == result['memory_command_results'], receipt)
    return result
def model(command):
    with runtime.history_actor_scope('model:fixture-assistant'):
        runtime.process_assistant_response('Executed Commands:\n' + command)
    for _ in range(10):
        if not runtime.get_pending_command_store():
            break
        result = runtime.approve_pending_command(['1'], True)
        check('model pending approval ' + command[:70], result['success'], result)
    check('model pending queue drains', not runtime.get_pending_command_store())

# Explicit retention settings keep synthetic timestamps from incidental decay.
for cmd, attribute in [('SET_IMPORTANT_MESSAGES', 'enable_important_messages'),
                       ('SET_UNIMPORTANT_MESSAGES', 'enable_unimportant_messages'),
                       ('SET_ADD_IMSGS_TO_HISTORY', 'ADD_IMSGS_TO_HISTORY'),
                       ('SET_ADD_UMSGS_TO_HISTORY', 'ADD_UMSGS_TO_HISTORY'),
                       ('SET_IMSGS_DECAY_CHECK', 'CHECK_IMSGS_DECAY'),
                       ('SET_UMSGS_DECAY_CHECK', 'CHECK_UMSGS_DECAY')]:
    for enabled in (False, True):
        run(cmd + '(' + ('on' if enabled else 'off') + ')')
        check(cmd + ' actual state', getattr(runtime, attribute) is enabled)
    run(cmd + '()')
    check(cmd + ' query leaves current state alone', getattr(runtime, attribute) is True)
run('SET_IMSGS_DECAY_CHECK(off); SET_UMSGS_DECAY_CHECK(off)')
for cmd, attribute in [('TOGGLE_IMSGS', 'enable_important_messages'), ('TOGGLE_UMSGS', 'enable_unimportant_messages'),
                       ('TOGGLE_ADD_IMSGS_TO_HISTORY', 'ADD_IMSGS_TO_HISTORY'), ('TOGGLE_ADD_UMSGS_TO_HISTORY', 'ADD_UMSGS_TO_HISTORY'),
                       ('TOGGLE_IMSGS_DECAY_CHECK', 'CHECK_IMSGS_DECAY'), ('TOGGLE_UMSGS_DECAY_CHECK', 'CHECK_UMSGS_DECAY')]:
    original = getattr(runtime, attribute)
    run(cmd + '()')
    check(cmd + ' flips actual state', getattr(runtime, attribute) is not original)
    run(cmd + '()')
    check(cmd + ' restores actual state', getattr(runtime, attribute) is original)
run('SET_TIME_LOGGING(off)')
for bad in ['ADD_GOAL()', 'ADD_GOAL(" ")', 'ADD_GOAL(x,High,Critical,ignored)',
            'ADD_GOAL("x;High;Critical;ignored")', 'ADD_APRIORITY_GOAL()', 'UPDATE_NOTES()',
            'UPDATE_NOTES(x,ignored)', 'UPDATE_PINNED_IMMEDIATE()', 'COMPLETE_GOAL(nope)',
            'SET_SHOW_AI_TEXT(off,ignored)', 'SET_UMSGS_DECAY_CHECK(typo)']:
    before = runtime.build_pinned_tasks_snapshot()
    result = run('SET_TIME_LOGGING(on); ' + bad, False)
    check('bad tail rejects whole batch without effects: ' + bad,
          not result['executed_commands'] and not runtime.TIME_LOGGING_ENABLED and runtime.build_pinned_tasks_snapshot() == before)

first = run('ADD_GOAL("Reach town, then heal",High,Critical)', ingest=True)['memory_command_results'][0]
markup = run('ADD_GOAL("-"); UPDATE_NOTES("must not run")', False)
check('formatting-only goal is rejected before mutation and stops tail', markup['memory_command_results'][0]['effect_status'] == 'not_started' and markup['blocked_commands'])
check('goal ID and priority/importance labels in receipt',
      first['goal_id'] > 0 and first['priority'] == 'High' and first['significance'] == 'Critical' and first['changed'])
duplicate = run('ADD_GOAL("Reach town, then heal",Low,Minor)')['memory_command_results'][0]
check('duplicate is unchanged and does not silently relabel', duplicate['effect_status'] == 'unchanged' and duplicate['goal_id'] == first['goal_id'] and duplicate['priority'] == 'High')
run('ADD_GOAL("Find a map;0.7;custom importance")')
model('ADD_GOAL("Model goal",Medium,Significant)')
check('assistant creates actual goal', any(goal.text == 'Model goal' for goal in runtime.tasks_list))
for command in ['ADD_APRIORITY_GOAL("Explore later")', 'ADD_OVERARCHING_GOAL("Finish the journey")',
                'ADD_UNKNOWN_PRIORITY("Investigate the cave")', 'UPDATE_NOTES("alpha;beta;ALPHA")',
                'ADD_JOURNAL("Met the guide, received advice")']:
    run(command)
check('notes replace and deduplicate in order', runtime.notes == ['alpha', 'beta'])
for policy, expected in [('legacy', 'first'), ('task_flow', 'first, second')]:
    run('SET_ASSISTANT_POLICY(' + policy + ')')
    for command, field in [('UPDATE_PINNED_IMMEDIATE', 'pinned_immediate_actions'),
                           ('UPDATE_PINNED_SHORT_TERM', 'pinned_short_term_actions'),
                           ('UPDATE_MID_TERM_CONTEXT', 'mid_term_context'),
                           ('UPDATE_LONG_TERM_CONTEXT', 'long_term_context')]:
        receipt = run(command + '(first,second)')['memory_command_results'][0]
        check(policy + ' horizon behavior and disclosure', getattr(runtime.agent_state, field) == [expected]
              and receipt['ignored_argument_count'] == (1 if policy == 'legacy' else 0))
run('UPDATE_NOTES("")')
check('explicit empty notes clears list', runtime.notes == [])
run('UPDATE_NOTES("Keep the map;Do not infer a numeric priority scheduler")')

hierarchy = '**Level 1**\n**Action 1**: Look around\n**Priority**: High\n**Significance**: Critical\n**Associated Goal**: Reach town\n**Level 2**\n**Action 1**: `PIN("remember")`\n**Priority**: Medium\n**Significance**: Useful\n**Associated Goal**: Find map\n'
runtime.parse_hierarchical_tasks(hierarchy)
before = copy.deepcopy(runtime.hierarchical_tasks)
runtime.parse_hierarchical_tasks(runtime.construct_hierarchical_tasks_text())
check('command and descriptive hierarchy roundtrip preserves labels/goals', runtime.hierarchical_tasks == before)
manual = list(runtime.pinned_immediate_actions)
runtime.sync_action_horizons_from_hierarchical_tasks()
check('legacy hierarchy synchronization still replaces manual horizon', runtime.pinned_immediate_actions != manual)
runtime.parse_hierarchical_tasks('')
run('SET_HIERARCHY_DISPATCH(advisory); SET_HORIZON_SYNC(preserve)')
run('UPDATE_PINNED_IMMEDIATE("Keep explicit manual plan")')
runtime.parse_hierarchical_tasks(hierarchy)
runtime.sync_action_horizons_from_hierarchical_tasks()
check('preserve keeps explicit horizons separate from hierarchy', runtime.pinned_immediate_actions == ['Keep explicit manual plan'])
captured, real_route = [], runtime.route_assistant_commands
runtime.route_assistant_commands = lambda *a, **k: captured.append((a, k))
try:
    runtime.execute_immediate_actions([{'command':'GB:press(a)'}])
    check('advisory blocks hierarchy routing without erasing it', not captured and bool(runtime.hierarchical_tasks))
    run('SET_HIERARCHY_DISPATCH(legacy)')
    runtime.execute_immediate_actions([{'command':'GB:press(a)'}])
    check('reenabling legacy does not rearm retained hierarchy', not captured and not runtime.HIERARCHY_DISPATCH_ARMED)
finally:
    runtime.route_assistant_commands = real_route
runtime.parse_hierarchical_tasks('')
run('SET_HORIZON_SYNC(legacy)')
check('registered policy readback is effective', runtime.build_registered_settings_runtime_state()['modes']['horizon_sync'] == 'legacy')
parent = runtime.tasks_list[0]
runtime.add_sub_goal(parent.id, 'Child', 'Low', 'Optional')
child = parent.sub_goals[0]
run('COMPLETE_GOAL(' + str(child.id) + ')')
complete = run('COMPLETE_GOAL(' + str(child.id) + ')')['memory_command_results'][0]
check('recursive completion idempotent', complete['effect_status'] == 'unchanged' and child.status == 'Complete')
run('COMPLETE_GOAL(999999999); UPDATE_NOTES("must not run")', False)
check('missing goal stops batch tail', runtime.notes[0] == 'Keep the map')
run('TASKS(); UPDATE_NOTES("must not run")', False)
check('TASKS cannot falsely report scheduling', runtime.runtime_state['last_memory_command_result']['effect_status'] == 'not_started')
for format in ('legacy', 'versioned'):
    run('SET_GOAL_SAVE_FORMAT(' + format + ')')
    before = runtime.build_pinned_tasks_snapshot()
    run('SAVE_TASKS(' + format + '.json)')
    runtime.tasks_list.clear()
    runtime.notes[:] = ['different']
    run('LOAD_TASKS(' + format + '.json)')
    check(format + ' recursive goals/labels/notes/horizons restore', runtime.build_pinned_tasks_snapshot() == before)

# Inject a post-write failure: do not claim rollback or allow the batch tail.
original_update = runtime.update_notes
def fail_after_write(text):
    original_update(text)
    raise RuntimeError('fixture after-write failure')
runtime.update_notes = fail_after_write
failed = run('UPDATE_NOTES("written before failure"); ADD_GOAL("must not run")', False)
runtime.update_notes = original_update
check('partial effect is uncertain with evidence and blocked tail', failed['memory_command_results'][0]['effect_status'] == 'failed_uncertain'
      and failed['memory_command_results'][0]['changed'] and failed['blocked_commands'])

original_update = runtime.update_notes
def cancel_after_write(text):
    original_update(text)
    raise runtime.WorkCancelled('fixture cancellation after write')
runtime.update_notes = cancel_after_write
cancelled = run('UPDATE_NOTES("written before cancellation"); ADD_GOAL("must not run")', False)
runtime.update_notes = original_update
check('cancellation retains partial-effect receipt and cancels tail', cancelled['cancelled']
      and cancelled['memory_command_results'][0]['effect_status'] == 'failed_uncertain' and cancelled['cancelled_commands'])

store = runtime.get_chat_history_store()
store[:] = []
for index in range(4):
    store.append(dict(timestamp='2026-11-05 12:00:0' + str(index), role='assistant', model='original-model',
                      Exemption='None', content=dict(type='text', text='message ' + str(index))))
runtime.ensure_message_ids(store)
run('DHISTORY()')
run('PIN("new pinned note")')
check('PIN appends protected text', any(row.get('Exemption') == 'Pinned' and 'new pinned note' in history_text(row) for row in store))
target = next(row for row in store if history_text(row) == 'message 0')
command = build_update_message_command(dict(message_id=target['message_id'], revision=message_revision(target)), 'literal CLEAR(); text, café', 'on')
run(command)
target = next(row for row in store if row.get('message_id') == target['message_id'])
check('existing message pin preserves sender and literal command text', target['Exemption'] == 'Pinned'
      and target['model'] == 'original-model' and target.get('edited_by') == 'operator' and history_text(target) == 'literal CLEAR(); text, café')
run(command, False)
run(build_update_message_command(dict(message_id=target['message_id'], revision=message_revision(target)), history_text(target), 'off'))
check('unpin explicitly succeeds', next(row for row in store if row.get('message_id') == target['message_id'])['Exemption'] == 'None')
run('EDIT_MSGS("2026-11-05 12:00:00","corrected zero","2026-11-05 12:00:01","corrected one")')
model('EDIT_MSGS("2026-11-05 12:00:02","model corrected")')
edited = next(row for row in store if row.get('timestamp') == '2026-11-05 12:00:02')
check('assistant edit records separate editor and sender', edited.get('edited_by') == 'model:fixture-assistant' and edited['model'] == 'original-model')
run('DELETE_MSG("2026-11-05 12:00:00")')
model('DELETE_MSG("2026-11-05 12:00:03")')
check('operator/assistant delete exact targets', not any(row.get('timestamp') in {'2026-11-05 12:00:00', '2026-11-05 12:00:03'} for row in store))
before = copy.deepcopy(store)
run('DELETE_MSG("2026-11-05 12:00:01","2026-11-05 12:00:02")', False)
check('unsupported delete range is rejected without effects', store == before)
run('SAVECH(basic-chat)')
run('SAVECH(basic-chat)')
check('chat exports do not overwrite', len(list(Path('.').glob('basic-chat*.txt'))) == 2)
run('CLEAR_NONPIN()')
check('clear nonpinned retains pin', any(row.get('Exemption') == 'Pinned' for row in store)
      and not any(row.get('timestamp') == '2026-11-05 12:00:01' for row in store))

# Nonsemantic filtering is currently wired to episodic records, not chat logs.
records = [dict(snapshot_id=name, summary_text=text, timestamp=stamp, source_bucket='manual', tags=['route'])
           for name, text, stamp in [('a', 'red key', '2026-11-04T08:00:00Z'),
                                    ('b', 'blue key', '2026-11-05T08:00:00Z'),
                                    ('c', 'red key failed', '2026-11-05T09:00:00Z')]]
Path(runtime.episodic_memory_path).parent.mkdir(parents=True, exist_ok=True)
Path(runtime.episodic_memory_path).write_text('\n'.join(json.dumps(row) for row in records) + '\n', encoding='utf-8')
receipt = run('RETRIEVAL_PULL(date_start=2026-11-05,date_end=2026-11-05,timezone=UTC,text_filter="key AND NOT failed",text_mode=boolean,sort=oldest,semantic_backend=off)')['retrieval_results'][0]
check('date plus boolean filter uses no semantic scoring', receipt['backend']['backend_used'] == 'filter_only'
      and receipt['search']['returned_records'] == 1, receipt)
for unsupported in ['SEARCH_MESSAGES("key")', 'RETRIEVAL_PULL(person=alice,date_end=2026-11-05)']:
    run(unsupported, False)
check('no message range-search binding is advertised', not any(name in runtime.command_dispatch for name in ('SEARCH_MESSAGES','DELETE_MSG_RANGE')))
check('no native or network guard was touched', not Path('forbidden-native-input.txt').exists())
check('inference stays offline', not runtime.SEND_TO_MODEL and not runtime.ENABLE_MODEL_RESPONSES)
Path('proof.json').write_text(json.dumps(dict(status='passed', checks=checks, check_count=len(checks),
    command_bindings_exercised=sorted(commands_seen), native_input_calls=0, provider_calls=0,
    embedding_calls=0, ui_launched=False, scope='real parser/handlers/memory/receipt ingestion; simulated assistant, no inference',
    known_limits=['chat message range search absent', 'range deletion absent', 'manual horizons replaced by legacy sync',
                  'priority/significance labels are not one numeric scheduler', 'TASKS remains explicitly unsupported']), indent=2), encoding='utf-8')
'''

if __name__ == '__main__':
    harness.FIXTURE = CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE.rsplit('runtime.main()', 1)[0] + SCENARIOS
    print(json.dumps(harness.run_smoke(), indent=2))
