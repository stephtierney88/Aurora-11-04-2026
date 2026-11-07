import copy
import json
import threading
import unittest
from types import SimpleNamespace as NS

import aurora_execution_evidence as evidence
from aurora_task_continuation import TaskContinuation, CommandReadbacks
from aurora_execution_inspector import inspection_snapshot, inspection_detail


class EvidenceTests(unittest.TestCase):
    def test_actual_route_and_wire_settings_are_distinct_from_selection(self):
        item = evidence.TransportEvidence({'reasoning': {'effort': 'low'}},
            {'effective_effort': 'high', 'configuration_update_sent': True})
        with evidence.observe_transport(item):
            evidence.instrumented()
            evidence.attempt({'model': 'gpt-fixture', 'reasoning': {'effort': 'low'}}, 'responses', 'api_key')
            evidence.response(status=200, headers={'x-request-id':'req_fixture','Authorization':'PRIVATE'},
                body={'id':'resp_fixture','model':'gpt-fixture','reasoning':{'effort':'low'},'service_tier':'default','output':'PRIVATE'})
        row = item.snapshot(close=True)
        self.assertEqual(row['controller_selected_effort'], 'high')
        self.assertTrue(row['configuration_update_sent'])
        self.assertEqual(row['attempts'][0]['wire_reasoning_effort'], 'low')
        self.assertEqual(row['attempts'][0]['provider_reported_effort'], 'low')
        self.assertIsNone(row['attempts'][0]['wire_service_tier'])
        self.assertEqual(row['attempts'][0]['provider_request_id'], 'req_fixture')
        self.assertNotIn('PRIVATE', json.dumps(row))

    def test_preflight_failure_and_uninstrumented_adapter_stay_distinct(self):
        unknown = evidence.TransportEvidence({})
        with evidence.observe_transport(unknown): pass
        self.assertFalse(unknown.snapshot()['instrumented'])
        blocked = evidence.TransportEvidence({})
        with self.assertRaises(ValueError), evidence.observe_transport(blocked):
            evidence.instrumented()
            raise ValueError('PRIVATE credential error')
        result = blocked.snapshot(close=True)
        self.assertTrue(result['instrumented'] and result['worker_failed'])
        self.assertEqual(result['attempts'], [])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_oauth_refresh_attempts_do_not_overwrite_first_failure(self):
        item = evidence.TransportEvidence({})
        with evidence.observe_transport(item):
            evidence.instrumented()
            evidence.attempt({'model':'fixture'}, 'chat_completions', 'codex_oauth')
            evidence.response(status=401, headers={'x-request-id':'req_denied'})
            evidence.attempt({'model':'fixture'}, 'chat_completions', 'api_key')
            evidence.response(status=200, body={'id':'chatcmpl_fixture','model':'fixture'})
        rows = item.snapshot()['attempts']
        self.assertEqual([(r['ordinal'],r['auth_mode'],r['http_status']) for r in rows], [(1,'codex_oauth',401),(2,'api_key',200)])
        self.assertEqual(rows[0]['provider_request_id'], 'req_denied')
        self.assertIsNone(rows[0]['provider_response_id'])

    def test_cancellation_freezes_evidence_before_late_response(self):
        item = evidence.TransportEvidence({})
        started, release = threading.Event(), threading.Event()
        def worker():
            with evidence.observe_transport(item):
                evidence.instrumented()
                evidence.attempt({'model':'fixture'}, 'chat_completions', 'api_key')
                started.set()
                release.wait(2)
                evidence.response(status=200, body={'id':'chatcmpl_late'})
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(started.wait(1))
            frozen = item.snapshot(close=True)
        finally:
            release.set(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(item.snapshot(), frozen)
        self.assertFalse(frozen['attempts'][0]['http_response_observed'])

    def test_nested_context_and_attempt_bounds(self):
        first, second = evidence.TransportEvidence({}), evidence.TransportEvidence({})
        with evidence.observe_transport(first):
            with evidence.observe_transport(second): evidence.instrumented()
            for _ in range(6): evidence.attempt({'model':'fixture'}, 'responses','api_key')
            evidence.response(status=200, body={'id':'resp_overflow'})
        self.assertEqual(len(first.snapshot()['attempts']),4)
        self.assertEqual(first.snapshot()['attempts_omitted'],2)
        self.assertTrue(second.snapshot()['instrumented'])
        self.assertFalse(any(r['http_response_observed'] for r in first.snapshot()['attempts']))

    def test_private_and_malformed_export_values_are_dropped(self):
        item = evidence.TransportEvidence({})
        item.attempt({'model':'sk-'+'x'*60},'responses','api_key')
        row=item.snapshot();row.update(path='PRIVATE', instrumented='yes')
        row['attempts'][0].update(provider_response_id='C:/PRIVATE/file', body='PRIVATE')
        clean=evidence.transport_snapshot(row)
        self.assertNotIn('PRIVATE',json.dumps(clean));self.assertNotIn('sk-',json.dumps(clean))
        self.assertIsNone(clean['instrumented'])
        self.assertEqual(evidence.transport_snapshot({}),{})
        self.assertEqual(evidence.receipt_snapshot({'schema':'aurora_receipt_evidence_v1','families':'bad'})['families'],[])

    def test_local_receipt_results_are_bounded_and_do_not_expose_values(self):
        receipt={'setting_results':[{'status':'applied','success':True,'before':'PRIVATE','after':'PRIVATE'}]*66,
                 'observation_results':[{'status':'timeout','success':True}, {'status':['bad']}],
                 'unknown_family':[{'api_key':'PRIVATE'}]}
        result=evidence.receipt_snapshot(evidence.receipt_summary(receipt))
        rows={r['family']:r for r in result['families']}
        self.assertEqual(rows['setting_results']['omitted'],2)
        self.assertEqual(rows['observation_results']['statuses'],{'timeout':1,'unknown':1})
        self.assertEqual(rows['observation_results']['success_unknown'],1)
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertEqual(CommandReadbacks.FAMILIES,evidence.RECEIPT_FAMILIES)

    def test_exact_task_projection_frozen_and_excluded_from_prompt(self):
        controller=TaskContinuation(clock=lambda:100.)
        controller.reserve(max_turns=3,max_seconds=30)
        task_id=controller.snapshot()['task_id']
        item=evidence.TransportEvidence({'reasoning_effort':'low'})
        item.attempt({'model':'fixture'},'responses','api_key')
        item.response(status=200,body={'id':'resp_fixture','reasoning':{'effort':'low'}})
        delivery=NS(task_id=task_id,inference_request_id='r1',model='fixture',frame_id='',transport_evidence=item.snapshot(close=True))
        controller.record_request_progress(delivery,'prepared');controller.record_request_progress(delivery,'responded')
        controller.record_command({'task_id':task_id,'command_batch_id':'b1','receipt_id':'c1','setting_results':[{'success':False}]})
        state={'continuation':{'mode':'bounded','active_task':controller.snapshot(include_progress=True)}}
        frozen=inspection_snapshot(state)
        delivery.transport_evidence['attempts'][0]['provider_response_id']='resp_mutated'
        detail=inspection_detail(frozen,'requests','r1')
        self.assertEqual(detail['latest_request_in_snapshot']['transport_evidence']['attempts'][0]['provider_response_id'],'resp_fixture')
        self.assertIn('receipt_evidence',inspection_detail(frozen,'commands','b1')['latest_command_in_snapshot'])
        compact=controller.snapshot()['progress']
        self.assertNotIn('transport_evidence',compact['latest_request'])
        self.assertNotIn('receipt_evidence',compact['latest_command'])

    def test_diagnostic_json_failure_does_not_change_response(self):
        item=evidence.TransportEvidence({})
        def invalid(): raise ValueError('PRIVATE')
        with evidence.observe_transport(item):
            evidence.attempt({'model':'fixture'},'chat_completions','api_key')
            evidence.http_response(NS(status_code=200,headers={},json=invalid))
        self.assertEqual(item.snapshot()['attempts'][0]['http_status'],200)
        self.assertIsNone(item.snapshot()['attempts'][0]['provider_response_id'])


if __name__=='__main__': unittest.main()
