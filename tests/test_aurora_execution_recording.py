"""Controller boundary order, loss visibility, privacy and unchanged execution."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from aurora_execution_recording import BoundaryBuffer
from aurora_task_continuation import TaskContinuation


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = TaskContinuation(clock=lambda:self.now, recording_capacity=16)
        self.task.reserve(max_turns=100,max_seconds=120)
        self.identity = self.task.snapshot()['task_id']

    def receipt(self, identity='b1'):
        return dict(task_id=self.identity,command_batch_id=identity,inference_request_id='r1',
                    receipt_id='receipt-'+identity,status='processed',executed_commands=['PRIVATE_ARGUMENT'])

    def delivery(self, identity='r1'):
        return NS(task_id=self.identity,inference_request_id=identity,model='fixture-model',frame_id='',
                  command_readbacks={'records':[]},private_prompt='PRIVATE_PROMPT')

    def records(self):return self.task.peek_recording(limit=16)['records']

    def test_default_is_off_without_extra_projection_or_export(self):
        task=TaskContinuation(clock=lambda:self.now)
        self.assertEqual(task.recording_status()['state'],'off')
        with patch.object(task,'_snapshot_locked',side_effect=AssertionError('must not record')):
            task.reserve(max_turns=10,max_seconds=10);task.stop('operator_cancelled')
        self.assertEqual(task.peek_recording()['records'],[])
        self.assertNotIn('recording',task.snapshot())
        self.assertEqual(task.close_recording()['state'],'off')

    def test_prepared_view_is_frozen_before_final_usage_and_receipts(self):
        delivery=self.delivery()
        self.task.record_request_progress(delivery,'prepared')
        self.task.record_request_progress(delivery,'responded')
        self.task.record_request(self.identity,'r1',started=True,phase='responded',provider_model='provider-fixture',
                                 usage={'prompt_tokens':3,'completion_tokens':4,'total_tokens':7})
        self.task.record_command(self.receipt())
        records=self.records()
        self.assertEqual([r['kind'] for r in records],['task_started','request_prepared','request_finalized','command_receipt'])
        prepared,final=records[1:3]
        self.assertEqual(prepared['inspection']['collections']['requests'][0]['phase'],'prepared')
        self.assertNotIn('reported_usage',prepared['inspection']['collections']['requests'][0])
        row=final['inspection']['collections']['requests'][0]
        self.assertEqual(row['reported_usage']['total_tokens'],7)
        self.assertEqual(row['provider_model'],'provider-fixture')
        self.assertEqual(final['identity'],'r1')
        self.assertEqual(final['inspection']['collections']['commands'],[])
        self.assertEqual(records[-1]['identity'],'b1')
        self.assertNotIn('PRIVATE_',json.dumps(records))
        self.assertIsNone(prepared['inspection']['source_export']['timestamp'])

    def test_final_usage_boundary_precedes_its_budget_stop(self):
        task=TaskContinuation(clock=lambda:self.now,recording_capacity=8)
        task.reserve(max_turns=10,max_seconds=20,max_reported_tokens=1)
        identity=task.snapshot()['task_id'];delivery=NS(task_id=identity,inference_request_id='r',model='fixture')
        task.record_request_progress(delivery,'prepared');task.record_request_progress(delivery,'responded')
        task.record_request(identity,'r',started=True,phase='responded',usage={'total_tokens':2})
        records=task.peek_recording()['records']
        self.assertEqual([r['kind'] for r in records][-2:],['request_finalized','task_stopped'])
        self.assertEqual(records[-2]['inspection']['task']['status'],'running')
        self.assertEqual(records[-1]['inspection']['task']['stop_reason'],'reported_token_limit')

    def test_recording_does_not_expire_task_as_a_side_effect(self):
        self.now+=130
        self.assertTrue(self.task.record_command(self.receipt()))
        self.assertEqual(self.records()[-1]['inspection']['task']['status'],'running')
        self.assertEqual(self.task.snapshot()['stop_reason'],'time_limit')
        self.assertEqual(self.records()[-1]['kind'],'task_stopped')

    def test_duplicates_and_stale_task_updates_do_not_create_boundaries(self):
        self.task.record_command(self.receipt())
        before=self.task.recording_status()['sequence']
        self.assertFalse(self.task.record_command(self.receipt()))
        self.assertEqual(self.task.recording_status()['sequence'],before)
        old=self.identity;self.task.stop('cancelled');self.task.reserve(max_turns=10,max_seconds=20,operator_input=True)
        before=self.task.recording_status()['sequence']
        self.assertFalse(self.task.record_request(old,'late',started=True,phase='responded'))
        self.assertFalse(self.task.record_request_progress(self.delivery('late'),'prepared'))
        self.assertEqual(self.task.recording_status()['sequence'],before)

    def test_task_replacement_preserves_session_order_and_old_records(self):
        session=self.task.recording_status()['session_id']
        self.task.stop('cancelled');self.task.stop('cancelled_again')
        self.task.reserve(max_turns=10,max_seconds=20,operator_input=True)
        records=self.records()
        self.assertEqual([r['sequence'] for r in records],[1,2,3])
        self.assertEqual(records[0]['task_id'],records[1]['task_id'])
        self.assertNotEqual(records[1]['task_id'],records[2]['task_id'])
        self.assertTrue(all(r['session_id']==session for r in records))
        self.assertEqual([r['task_event_sequence'] for r in records],[0,0,0])

    def test_pressure_preserves_oldest_records_and_exposes_gaps(self):
        task=TaskContinuation(clock=lambda:self.now,recording_capacity=1)
        task.reserve(max_turns=20,max_seconds=20)
        for _ in range(3):task.reserve(max_turns=20,max_seconds=20)
        status=task.recording_status()
        self.assertEqual(status['dropped'],3)
        self.assertEqual(status['gaps'],[dict(first=2,last=4,reason='capacity')])
        self.assertEqual(task.peek_recording()['records'][0]['sequence'],1)
        task.acknowledge_recording(status['session_id'],[1])
        task.reserve(max_turns=20,max_seconds=20)
        row=task.peek_recording()['records'][0]
        self.assertEqual(row['sequence'],5);self.assertEqual(row['dropped_total_before'],3)
        self.assertEqual(row['gaps_before'],status['gaps'])

    def test_ack_requires_exact_session_and_queue_prefix(self):
        self.task.record_command(self.receipt());session=self.task.recording_status()['session_id']
        for identity,sequences in [('wrong',[1]),(session,[2]),(session,[2,1]),(session,[]),(session,[True])]:
            self.assertEqual(self.task.acknowledge_recording(identity,sequences)['status'],'ack_conflict')
        view=self.records();view[0]['inspection']['task']['status']='mutated'
        self.assertEqual(self.records()[0]['inspection']['task']['status'],'running')
        self.assertEqual(self.task.acknowledge_recording(session,[1,2])['status'],'acknowledged')
        self.assertEqual(self.task.acknowledge_recording(session,[1,2])['status'],'ack_conflict')
        self.assertEqual(self.task.recording_status()['buffered_bytes'],0)

    def test_close_keeps_drainable_records_and_does_not_stop_execution(self):
        status=self.task.close_recording()
        self.assertEqual(status['state'],'closed');self.assertEqual(status['queued'],1)
        self.assertTrue(self.task.reserve(max_turns=100,max_seconds=120))
        self.assertTrue(self.task.record_command(self.receipt()))
        self.assertEqual(self.task.snapshot()['status'],'running')
        self.assertEqual(self.task.recording_status()['sequence'],1)
        self.assertEqual(self.task.recording_status()['after_close_ignored'],2)
        self.assertEqual(self.task.acknowledge_recording(status['session_id'],[1])['status'],'acknowledged')
        self.assertFalse(self.task.recording_status()['durable'])

    def test_sessions_and_sequence_do_not_claim_wall_clock_order(self):
        other=TaskContinuation(recording_capacity=1)
        self.assertNotEqual(other.recording_status()['session_id'],self.task.recording_status()['session_id'])
        self.task._recording.epoch_clock=lambda:1
        self.task.record_command(self.receipt())
        records=self.records()
        self.assertLess(records[-1]['observed_at_epoch'],records[0]['observed_at_epoch'])
        self.assertGreater(records[-1]['sequence'],records[0]['sequence'])

    def test_projection_failure_is_visible_without_breaking_commands(self):
        with patch.object(self.task,'_snapshot_locked',side_effect=RuntimeError('PRIVATE_ERROR')):
            self.assertTrue(self.task.record_command(self.receipt()))
        status=self.task.recording_status()
        self.assertEqual(status['gaps'][-1]['reason'],'projection_error')
        self.assertNotIn('PRIVATE',json.dumps(status))
        self.assertEqual(self.task.snapshot()['accounting']['command_batches'],1)

    def test_record_and_buffer_byte_limits_are_independent(self):
        with patch('aurora_execution_recording.MAX_RECORD_BYTES',1):
            self.task.record_command(self.receipt('b1'))
        with patch('aurora_execution_recording.MAX_BUFFER_BYTES',1):
            self.task.record_command(self.receipt('b2'))
        self.assertEqual([g['reason'] for g in self.task.recording_status()['gaps']],['record_bytes','buffer_bytes'])
        self.assertEqual(len(self.records()),1)

    def test_concurrent_receipts_are_serialized_without_losing_accounting(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda n:self.task.record_command(self.receipt('b'+str(n))),range(100)))
        self.assertTrue(all(results))
        status=self.task.recording_status()
        self.assertEqual(status['sequence'],101);self.assertEqual(status['queued'],16)
        self.assertEqual(status['dropped'],85)
        self.assertEqual([r['sequence'] for r in self.records()],list(range(1,17)))
        self.assertEqual(self.task.snapshot()['accounting']['command_batches'],100)

    def test_invalid_configuration_and_bounded_gap_diagnostics(self):
        for capacity in (-1,True,'8',17):
            with self.assertRaises(ValueError):TaskContinuation(recording_capacity=capacity)
        buffer=BoundaryBuffer(1)
        for n in range(40):
            buffer.offer('wrong' if n%2 else 'command_receipt',lambda:None,identity='bad identity')
        self.assertEqual(len(buffer.status()['gaps']),16)
        self.assertEqual(buffer.status()['gap_ranges_omitted'],24)
        self.assertEqual(buffer.status()['dropped'],40)


if __name__=='__main__':unittest.main()
