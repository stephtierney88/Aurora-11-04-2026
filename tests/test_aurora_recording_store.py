"""Durable metadata, transaction failures and exact worker acknowledgement."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from aurora_task_continuation import TaskContinuation
from aurora_recording_store import RecordingStore, store_action, normalize_record
from aurora_recording_service import RecordingService, RecordingJob
from aurora_command_contracts import validate_command_arguments, describe_command_contract


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aurora-recording-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'recordings'
        self.task=TaskContinuation(recording_capacity=16)
        self.task.reserve(max_turns=100,max_seconds=120)
        self.store=RecordingStore(self.root)

    def request(self):
        batch=self.task.peek_recording(limit=4)
        return dict(operation='publish',manifest=batch['status'],records=batch['records'])

    def test_atomic_idempotent_restart_and_checksum(self):
        request=self.request();first=store_action(self.root,request)
        self.assertEqual(first['status'],'committed')
        self.assertEqual(store_action(self.root,request),first)
        listing=RecordingStore(self.root).sessions()['sessions'][0]
        self.assertEqual(listing['committed_count'],1)
        self.assertIn('unknown',listing['closure'])
        loaded=self.store.record(first['session_id'],1)
        self.assertEqual(loaded['record'],normalize_record(request['records'][0])[0])
        self.assertEqual(loaded['digest'],first['digests'][0])

    def test_changed_content_cannot_replace_record(self):
        request=self.request();self.store.publish(request['manifest'],request['records'])
        request['records'][0]['observed_at_epoch']+=1
        self.assertEqual(store_action(self.root,request)['status'],'record_conflict')
        self.assertEqual(self.store.sessions()['sessions'][0]['committed_count'],1)

    def test_capacity_failure_rolls_back_whole_batch_and_manifest(self):
        request=self.request();self.store.publish(request['manifest'],request['records'])
        self.task.acknowledge_recording(request['manifest']['session_id'],[1])
        self.task.reserve(max_turns=100,max_seconds=120)
        self.task.reserve(max_turns=100,max_seconds=120)
        with patch('aurora_recording_store.MAX_SESSION_RECORDS',2):
            self.assertEqual(store_action(self.root,self.request())['status'],'record_capacity')
        state=self.store.sessions()['sessions'][0]
        self.assertEqual(state['manifest']['sequence'],1)
        self.assertEqual(state['committed_count'],1)

    def test_first_capacity_failure_keeps_usable_empty_store(self):
        with patch('aurora_recording_store.MAX_RECORDS',0):
            self.assertEqual(store_action(self.root,self.request())['status'],'record_capacity')
        self.assertEqual(self.store.sessions()['sessions'],[])
        self.assertEqual(store_action(self.root,self.request())['status'],'committed')

    def test_gaps_survive_restart_and_close_requires_all_accepted_records(self):
        for _ in range(20):self.task.reserve(max_turns=100,max_seconds=120)
        self.task.close_recording();request=self.request()
        self.assertEqual(store_action(self.root,request)['status'],'incomplete_close')
        self.assertEqual(self.store.sessions()['sessions'],[])
        while self.task.recording_status()['queued']:
            request=self.request()
            if request['manifest']['queued']>len(request['records']):request['manifest']['state']='buffering'
            result=store_action(self.root,request);self.assertEqual(result['status'],'committed')
            self.task.acknowledge_recording(result['session_id'],result['sequences'])
        entry=self.store.sessions()['sessions'][0]
        self.assertEqual(entry['closure'],'closed')
        self.assertEqual(entry['committed_count'],16)
        self.assertEqual(entry['manifest']['dropped'],5)
        self.assertEqual(entry['manifest']['gaps'],[dict(first=17,last=21,reason='capacity')])

    def test_schema_privacy_and_invalid_identity_rejected_before_disk(self):
        for mutate in (lambda r:r.update(secret='must-not-write'),
                       lambda r:r.update(identity='../arbitrary'),
                       lambda r:r['inspection']['task'].update(prompt='must-not-write'),
                       lambda r:r.update(schema='future'),
                       lambda r:r.update(sequence=True)):
            request=self.request();mutate(request['records'][0])
            self.assertNotEqual(store_action(self.root,request)['status'],'committed')
            self.assertFalse(self.root.exists())

    def test_corrupt_payload_is_not_loaded(self):
        result=store_action(self.root,self.request())
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("UPDATE records SET payload=?",(b'{}',));con.commit()
        self.assertEqual(store_action(self.root,dict(operation='record',session_id=result['session_id'],sequence=1))['status'],'corrupt')

    def test_locked_database_reports_uncertainty_without_consuming_feed(self):
        store_action(self.root,self.request())
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('BEGIN EXCLUSIVE')
            self.assertEqual(store_action(self.root,self.request())['status'],'publication_uncertain')
        self.assertEqual(self.task.recording_status()['queued'],1)

    def test_unsupported_store_preserved_and_oversize_rejected(self):
        self.root.mkdir()
        with closing(sqlite3.connect(self.store.path)) as con:con.execute('PRAGMA user_version=99')
        self.assertEqual(store_action(self.root,self.request())['status'],'unsupported_store')
        with patch('aurora_recording_store.MAX_DB_BYTES',1):
            self.assertEqual(store_action(self.root,self.request())['status'],'database_too_large')

    def test_session_limit_and_manifest_regression(self):
        first=self.request();store_action(self.root,first)
        self.task.reserve(max_turns=100,max_seconds=120)
        store_action(self.root,self.request())
        self.assertEqual(store_action(self.root,first)['status'],'manifest_regression')
        other=TaskContinuation(recording_capacity=16);other.reserve(max_turns=8,max_seconds=30)
        batch=other.peek_recording()
        with patch('aurora_recording_store.MAX_SESSIONS',1):
            self.assertEqual(store_action(self.root,dict(operation='publish',manifest=batch['status'],records=batch['records']))['status'],'session_capacity')

    def test_initialization_crash_empty_file_can_retry_without_erasing_unknown_schema(self):
        self.root.mkdir();self.store.path.touch()
        self.assertEqual(store_action(self.root,self.request())['status'],'committed')
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('PRAGMA user_version=0');con.commit()
        self.assertEqual(store_action(self.root,self.request())['status'],'unsupported_store')
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM records').fetchone()[0],1)

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'tools/build_public_snapshot.py').is_file(), 'Private export tooling is not shipped')
    def test_public_export_omits_recordings(self):
        from tools.build_public_snapshot import selected,audit
        self.assertFalse(selected('execution_recordings/history.sqlite3'))
        root=Path(self.tmp.name)/'export';(root/'execution_recordings').mkdir(parents=True)
        (root/'execution_recordings'/'history.sqlite3').write_text('fixture')
        self.assertTrue(audit(root)['findings'] if isinstance(audit(root),dict) else audit(root)[0])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aurora-recording-service-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'recordings'
        self.task=TaskContinuation()
        self.service=RecordingService(self.task,self.root)
        self.addCleanup(self.service.close)

    def wait(self,predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.service.tick()
            if predicate():return
            time.sleep(.01)
        self.fail(str(self.service.snapshot()))

    def test_off_no_resources_attach_keeps_existing_budget(self):
        self.service.tick();self.assertFalse(self.root.exists());self.assertIsNone(self.service.job)
        self.task.reserve(max_turns=8,max_seconds=120)
        before=self.task.snapshot(include_progress=True)
        self.service.set_mode('boundaries')
        self.assertEqual(before,self.task.snapshot(include_progress=True))
        self.task.reserve(max_turns=8,max_seconds=120)
        self.wait(lambda:self.service.committed==1)
        self.assertEqual(self.task.recording_status()['queued'],0)
        final=self.service.shutdown()
        self.assertEqual(final['state'],'closed')
        self.assertIsNone(final['writer_pid'])
        self.assertTrue(final['last_receipt']['owned_resources_closed'])
        old=final['feed']['session_id'];self.service.set_mode('boundaries')
        self.assertNotEqual(old,self.task.recording_status()['session_id'])

    def test_disable_drains_full_queue_and_persists_trailing_loss(self):
        self.service.set_mode('boundaries')
        for _ in range(21):self.task.reserve(max_turns=100,max_seconds=120)
        self.service.set_mode('off')
        with self.assertRaises(ValueError):self.service.set_mode('boundaries')
        self.wait(lambda:self.service.state=='closed')
        entry=RecordingStore(self.root).sessions()['sessions'][0]
        self.assertEqual(entry['closure'],'closed');self.assertEqual(entry['committed_count'],16)
        self.assertEqual(entry['manifest']['dropped'],5)

    def test_lost_commit_ack_retries_exact_batch_without_duplicates(self):
        self.service.set_mode('boundaries');self.task.reserve(max_turns=8,max_seconds=120)
        self.service.tick();job=self.service.job
        # Let the real child commit, then lose its receipt before the parent polls it.
        job.process.wait(timeout=8)
        job.cancel('simulated_lost_ack')
        self.service.tick()
        self.assertEqual(self.service.state,'error');self.assertEqual(self.task.recording_status()['queued'],1)
        self.assertEqual(RecordingStore(self.root).sessions()['sessions'][0]['committed_count'],1)
        exact=copy.deepcopy(self.service.pending)
        self.service.retry();self.service.tick()
        self.assertEqual(self.service.pending,exact)
        self.wait(lambda:self.service.committed==1)
        self.assertEqual(RecordingStore(self.root).sessions()['sessions'][0]['committed_count'],1)

    def test_writer_failure_does_not_stop_task_or_lose_queue(self):
        self.service.job_factory=lambda *a:(_ for _ in ()).throw(OSError('private path'))
        self.service.set_mode('boundaries');self.task.reserve(max_turns=8,max_seconds=120)
        before=self.task.snapshot(include_progress=True);self.service.tick()
        self.assertEqual(self.service.state,'error');self.assertEqual(self.task.recording_status()['queued'],1)
        self.assertEqual(before,self.task.snapshot(include_progress=True))
        self.assertNotIn('private path',json.dumps(self.service.snapshot()))
        self.service.job_factory=RecordingJob;self.service.retry()
        self.wait(lambda:self.service.committed==1)

    def test_wrong_ack_never_consumes_prefix(self):
        class BadJob:
            process=None;started_at_epoch=0
            def __init__(self,*args):pass
            def poll(self):return dict(status='committed',session_id='wrong',sequences=[1],digests=['wrong'])
        self.service.job_factory=BadJob
        self.service.set_mode('boundaries');self.task.reserve(max_turns=8,max_seconds=120)
        self.service.tick();self.service.tick()
        self.assertEqual(self.service.state,'error');self.assertEqual(self.task.recording_status()['queued'],1)

    def test_shutdown_deadline_cleans_owned_worker_preserves_uncertainty(self):
        self.service.set_mode('boundaries');self.task.reserve(max_turns=8,max_seconds=120)
        self.service.tick();job=self.service.job
        final=self.service.shutdown(timeout=0)
        self.assertEqual(final['error'],'publication_uncertain')
        self.assertIsNotNone(job.process.poll())
        self.assertFalse(any(thread.is_alive() for thread in job.threads))
        self.assertEqual(self.task.recording_status()['queued'],1)
        self.service.retry();self.wait(lambda:self.service.state=='closed')

    def test_retry_contract_is_explicit_and_zero_arguments(self):
        validate_command_arguments('RETRY_EXECUTION_RECORDING',[])
        with self.assertRaises(ValueError):validate_command_arguments('RETRY_EXECUTION_RECORDING',['all'])
        contract=describe_command_contract('RETRY_EXECUTION_RECORDING')
        self.assertEqual(contract['parameter_validation'],'pre_dispatch')
        self.assertIn('asynchronous',contract['result']['success'])

    def test_cleanup_failure_is_reported_without_aborting_runtime_shutdown(self):
        class BrokenCleanup:
            process=None;started_at_epoch=0
            def poll(self):raise OSError('private failure')
            def cancel(self,*args):raise OSError('private cleanup failure')
        self.service.set_mode('boundaries');self.service.job=BrokenCleanup()
        try:
            self.service.tick()
            result=self.service.shutdown(timeout=0)
            self.assertEqual(result['error'],'cleanup_incomplete')
            self.assertIs(result['last_receipt']['owned_resources_closed'],False)
            self.assertNotIn('private',json.dumps(result))
        finally:
            # Synthetic object owns no process/thread; remove the fixture reference.
            self.service.job=None


if __name__=='__main__':unittest.main()
