import copy
import json
import unittest
from types import SimpleNamespace as NS

from aurora_task_continuation import TaskContinuation
from aurora_execution_inspector import inspection_snapshot, inspection_detail


def fixture_state():
    controller = TaskContinuation(clock=lambda: 100.0)
    controller.reserve(max_turns=20, max_seconds=120)
    task_id = controller.snapshot()['task_id']
    delivery = NS(task_id=task_id, inference_request_id='r1', model='fixture-requested', frame_id='f1',
        command_readbacks={}, prepared_settings=dict(reasoning_effort='low', service_tier='regular',
            configured_transport='chat_completions', configured_auth='api_key', api_key='FAKE_PRIVATE_SECRET'),
        frame_provenance=dict(status='acquired', frame_id='f1', session_id='capture1', request_generation=2,
                              acquired_start_epoch=1000, path='PRIVATE_PATH'),
        frame_artifact=dict(schema='aurora_capture_artifact_v1', status='bound', frame_id='f1',
            artifact_name='100-'+'a'*32+'.png', byte_count=123, sha256='b'*64, path='PRIVATE_PATH'))
    controller.record_request_progress(delivery, 'prepared')
    delivery.transport_evidence = dict(schema='aurora_transport_evidence_v1', scope='inference_transport_only',
        instrumented=True, worker_entered=True, observation_closed=True, controller_selected_effort='low',
        configuration_update_sent=False, attempts_omitted=0,
        attempts=[dict(ordinal=1, transport='chat_completions', auth_mode='api_key', wire_reasoning_effort='low',
            http_status=200, http_response_observed=True, provider_request_id='req_fixture',
            provider_response_id='chatcmpl_fixture', provider_reported_effort=None, api_key='FAKE_PRIVATE_SECRET')])
    controller.record_request_progress(delivery, 'submitted')
    controller.record_request_progress(delivery, 'responded')
    controller.record_request(task_id, 'r1', started=True, phase='responded', provider_model='fixture-returned', usage={'total_tokens': 9})
    entry = dict(task_id=task_id, command_batch_id='b1', inference_request_id='r1',
                 prepared_commands=[('UPDATE_NOTES(PRIVATE_TEXT)', 'UPDATE_NOTES', ['PRIVATE_TEXT'])])
    controller.record_command_admission(entry)
    controller.record_command(dict(entry, receipt_id='receipt1', status='processed', executed_commands=['PRIVATE_TEXT']))
    return {'timestamp': '2000-01-01 00:00:00', 'continuation': {'mode': 'bounded', 'active_task': controller.snapshot(include_progress=True)}}


class InspectionTests(unittest.TestCase):
    def test_safe_metadata_retained_without_text_paths_or_secrets(self):
        state = fixture_state()
        progress = state['continuation']['active_task']['progress']
        request = progress['requests'][0]
        self.assertEqual(request['prepared_settings']['reasoning_effort'], 'low')
        self.assertEqual(request['frame_artifact']['status'], 'bound')
        self.assertEqual((request['model'], request['provider_model']), ('fixture-requested', 'fixture-returned'))
        self.assertEqual(request['reported_usage'], dict(input_tokens=None, output_tokens=None, total_tokens=9))
        self.assertEqual(progress['commands'][0]['binding_names'], ['UPDATE_NOTES'])
        self.assertNotIn('PRIVATE', json.dumps(progress))
        state['last_prompt_diagnostics'] = dict(frame_id='unrelated', secret='PRIVATE_SECRET')
        snapshot = inspection_snapshot(state)
        self.assertNotIn('PRIVATE', json.dumps(snapshot))
        self.assertEqual(snapshot['collections']['requests'][0]['transport_evidence']['attempts'][0]['provider_request_id'], 'req_fixture')
        self.assertNotIn('unrelated', json.dumps(snapshot))

    def test_event_stage_not_rewritten_by_later_receipt(self):
        snapshot = inspection_snapshot(fixture_state())
        event = next(e for e in snapshot['collections']['events'] if e['kind'] == 'command_admitted')
        detail = inspection_detail(snapshot, 'events', event['sequence'])
        self.assertEqual(detail['selected_event_or_record']['kind'], 'command_admitted')
        self.assertEqual(detail['latest_command_in_snapshot']['status'], 'processed')
        self.assertEqual(detail['linked_records']['origin_request_id']['provider_model'], 'fixture-returned')
        self.assertIn('unknown', detail['evidence']['verification'])
        self.assertIn('not provider confirmation', detail['evidence']['provider_effort'])

    def test_snapshot_frozen_across_task_replacement_and_selection(self):
        state = fixture_state()
        snapshot = inspection_snapshot(state)
        original = snapshot['task']['task_id']
        state['continuation']['active_task']['task_id'] = 'another-task'
        state['continuation']['active_task']['progress']['commands'][0]['receipt_id'] = 'changed'
        detail = inspection_detail(snapshot, 'commands', 'b1')
        self.assertEqual(detail['task_id'], original)
        self.assertEqual(detail['latest_command_in_snapshot']['receipt_id'], 'receipt1')
        detail['latest_command_in_snapshot']['receipt_id'] = 'changed-again'
        self.assertEqual(inspection_detail(snapshot, 'commands', 'b1')['latest_command_in_snapshot']['receipt_id'], 'receipt1')

    def test_missing_request_and_receipt_stay_unknown(self):
        state = fixture_state()
        progress = state['continuation']['active_task']['progress']
        progress['requests'] = []
        progress['commands'][0].pop('receipt_id')
        snapshot = inspection_snapshot(state)
        detail = inspection_detail(snapshot, 'commands', 'b1')
        self.assertIn('unknown', detail['linked_records']['origin_request_id'])
        self.assertNotIn('receipt_id', detail['latest_command_in_snapshot'])
        self.assertIn('unknown', inspection_detail(snapshot, 'commands', 'absent'))

    def test_evicted_event_link_does_not_use_nearest_record(self):
        state = fixture_state()
        progress = state['continuation']['active_task']['progress']
        progress['commands'][0]['command_batch_id'] = 'unrelated'
        snapshot = inspection_snapshot(state)
        event = next(e for e in snapshot['collections']['events'] if e['kind'] == 'command_receipt')
        detail = inspection_detail(snapshot, 'events', event['sequence'])
        self.assertIsNone(detail['latest_command_in_snapshot'])
        self.assertFalse(detail['linked_records'])

    def test_missing_or_legacy_export_has_explanation(self):
        for state in ({}, {'continuation': {'active_task': {}}}, {'continuation': 'invalid'},
                      {'continuation': {'active_task': 'invalid'}}, None):
            snapshot = inspection_snapshot(state)
            self.assertFalse(snapshot['available'])
            self.assertIn('Legacy', snapshot['unavailable_reason'])
        state = fixture_state()
        del state['continuation']['active_task']['progress']['events']
        self.assertFalse(inspection_snapshot(state)['available'])

    def test_duplicate_identities_refuse_ambiguous_join(self):
        state = fixture_state()
        commands = state['continuation']['active_task']['progress']['commands']
        commands.append(copy.deepcopy(commands[0]))
        snapshot = inspection_snapshot(state)
        self.assertFalse(snapshot['available'])
        self.assertIn('ambiguous', snapshot['unavailable_reason'])

    def test_display_bounds_do_not_hide_omissions(self):
        state = fixture_state()
        progress = state['continuation']['active_task']['progress']
        progress['events'] = [dict(sequence=n+1, kind='model_prepared', identity='r1', secret='PRIVATE') for n in range(80)]
        progress['events_evicted'] = 200
        snapshot = inspection_snapshot(state)
        self.assertEqual(len(snapshot['collections']['events']), 64)
        self.assertEqual(snapshot['display_omitted']['events'], 16)
        self.assertEqual(snapshot['retention']['events_evicted'], 200)
        self.assertNotIn('PRIVATE', json.dumps(snapshot))

    def test_old_record_without_new_fields_remains_inspectable(self):
        state = fixture_state()
        for key in ('prepared_settings', 'frame_provenance', 'provider_model', 'reported_usage'):
            state['continuation']['active_task']['progress']['requests'][0].pop(key)
        snapshot = inspection_snapshot(state)
        self.assertTrue(snapshot['available'])
        detail = inspection_detail(snapshot, 'requests', 'r1')
        self.assertNotIn('provider_model', detail['latest_request_in_snapshot'])

    def test_request_outcome_does_not_recreate_evicted_row(self):
        controller = TaskContinuation()
        controller.reserve(max_turns=20, max_seconds=120)
        task_id = controller.snapshot()['task_id']
        controller.record_request(task_id, 'unretained', started=True, phase='failed')
        self.assertEqual(controller.snapshot(include_progress=True)['progress']['requests'], [])

    def test_inspection_metadata_does_not_expand_compact_prompt(self):
        controller = TaskContinuation()
        controller.reserve(max_turns=20, max_seconds=120)
        task_id = controller.snapshot()['task_id']
        delivery = NS(task_id=task_id, inference_request_id='r1', model='fixture', frame_id='f1',
                      prepared_settings={'reasoning_effort': 'high'}, frame_provenance={'frame_id': 'f1'})
        controller.record_request_progress(delivery, 'prepared')
        controller.record_command_admission(dict(task_id=task_id, command_batch_id='b1',
            prepared_commands=[('', 'UPDATE_NOTES', [])]*100))
        full = controller.snapshot(include_progress=True)['progress']
        self.assertEqual(len(full['commands'][0]['binding_names']), 64)
        self.assertEqual(full['commands'][0]['binding_names_omitted'], 36)
        compact = controller.snapshot()['progress']
        self.assertNotIn('binding_names', compact['latest_command'])
        self.assertNotIn('prepared_settings', compact['latest_request'])
        self.assertNotIn('frame_provenance', compact['latest_request'])
        self.assertNotIn('frame_artifact', compact['latest_request'])

    def test_artifact_stays_frozen_and_old_export_does_not_guess_reference(self):
        state = fixture_state()
        snapshot = inspection_snapshot(state)
        ref = snapshot['collections']['requests'][0]['frame_artifact']
        state['continuation']['active_task']['progress']['requests'][0]['frame_artifact']['sha256'] = 'changed'
        self.assertEqual(ref['sha256'], 'b'*64)
        state['continuation']['active_task']['progress']['requests'][0].pop('frame_artifact')
        self.assertNotIn('frame_artifact', inspection_snapshot(state)['collections']['requests'][0])


if __name__ == '__main__':
    unittest.main()
