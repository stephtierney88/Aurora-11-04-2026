"""Exact selection, writer exclusion, transactional retirement and lost-ack proofs."""
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from aurora_recording_gate import RecordingGate
from aurora_recording_service import RecordingJob, RecordingService
from aurora_recording_store import RecordingStore, store_action
from aurora_task_continuation import TaskContinuation


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aurora-recording-retention-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'records';self.store=RecordingStore(self.root)
        self.first=self.publish();self.second=self.publish()

    def publish(self,closed=True):
        task=TaskContinuation(recording_capacity=16);task.reserve(max_turns=10,max_seconds=120)
        if closed:task.close_recording()
        batch=task.peek_recording(limit=4)
        request=dict(operation='publish',manifest=batch['status'],records=batch['records'])
        self.assertEqual(store_action(self.root,request)['status'],'committed')
        return request

    def ids(self,*requests):return [r['manifest']['session_id'] for r in requests or (self.first,)]
    def preview(self,ids=None,**options):
        return store_action(self.root,dict(operation='preview_remove',session_ids=ids or self.ids(),**options))
    def remove(self,preview=None,**options):
        preview=preview or self.preview()
        return store_action(self.root,dict(operation='remove',session_ids=preview['session_ids'],
            expected_version=preview['version'],include_incomplete=preview['include_incomplete'],confirm=True,**options))
    def sql(self,statement,*args):
        with closing(sqlite3.connect(self.store.path)) as con:
            result=con.execute(statement,*args).fetchall();con.commit();return result

    def test_preview_is_exact_and_does_not_migrate_or_delete(self):
        before=self.store.path.read_bytes();result=self.preview()
        self.assertEqual(result['status'],'removal_preview');self.assertEqual(result['record_count'],1)
        self.assertGreater(result['payload_bytes'],0);self.assertEqual(result['session_ids'],self.ids())
        self.assertEqual(self.store.path.read_bytes(),before);self.assertEqual(self.sql('PRAGMA user_version'),[(1,)])

    def test_remove_reclaims_slots_preserves_others_and_rejects_delayed_retry(self):
        other=self.store.record(self.ids(self.second)[0],1);preview=self.preview()
        result=self.remove(preview)
        self.assertEqual(result['status'],'removed');self.assertEqual(result['version'],preview['version'])
        self.assertEqual(self.sql('PRAGMA user_version'),[(2,)])
        self.assertEqual(self.store.record(self.ids(self.second)[0],1),other)
        self.assertEqual(store_action(self.root,self.first)['status'],'session_retired')
        self.publish();self.assertEqual(len(self.store.sessions()['sessions']),2)

    def test_multi_selection_atomic(self):
        result=self.remove(self.preview(self.ids(self.first,self.second)))
        self.assertEqual(result['record_count'],2);self.assertEqual(self.store.sessions()['sessions'],[])

    def test_changed_unselected_session_invalidates_archive_preview(self):
        preview=self.preview();self.publish()
        self.assertEqual(self.remove(preview)['status'],'archive_changed')
        self.assertEqual(len(self.store.sessions()['sessions']),3)

    def test_confirm_and_selection_bound_version(self):
        preview=self.preview()
        self.assertEqual(store_action(self.root,dict(operation='remove',session_ids=self.ids(),expected_version=preview['version']))['status'],'confirmation_required')
        changed=copy.deepcopy(preview);changed['session_ids']=self.ids(self.second)
        self.assertEqual(self.remove(changed)['status'],'archive_changed')

    def test_incomplete_requires_explicit_discard_and_option_bound_version(self):
        incomplete=self.publish(False);ids=self.ids(incomplete)
        self.assertEqual(self.preview(ids)['status'],'incomplete_protected')
        preview=self.preview(ids,include_incomplete=True)
        self.assertEqual(preview['sessions'][0]['manifest']['state'],'buffering')
        changed=copy.deepcopy(preview);changed['include_incomplete']=False
        self.assertEqual(self.remove(changed)['status'],'incomplete_protected')
        self.assertEqual(self.remove(preview)['status'],'removed')
        self.assertEqual(store_action(self.root,incomplete)['status'],'session_retired')

    def test_active_epoch_blocks_preview_even_between_children_and_after_error(self):
        service=RecordingService(TaskContinuation(),self.root);self.addCleanup(service.close)
        service.set_mode('boundaries')
        self.assertEqual(self.preview()['status'],'recording_active_or_retention_busy')
        service.state='error';service.error='publication_uncertain';service.set_mode('off')
        self.assertEqual(self.preview(include_incomplete=True)['status'],'recording_active_or_retention_busy')
        service.close(timeout=0)
        self.assertEqual(self.preview()['status'],'removal_preview')
        with self.assertRaises(ValueError):service.retry()

    def test_shared_gate_allows_publish_but_excludes_retention_and_exclusive_blocks_activation(self):
        with RecordingGate(self.root):
            self.publish()
            self.assertEqual(self.preview()['status'],'recording_active_or_retention_busy')
        service=RecordingService(TaskContinuation(),self.root);self.addCleanup(service.close)
        with RecordingGate(self.root,exclusive=True):
            with self.assertRaises(ValueError):service.set_mode('boundaries')
            self.assertIsNone(service.gate)
            self.assertEqual(service.snapshot()['feed']['enabled'],False)

    def test_guard_acquired_after_preview_blocks_apply(self):
        preview=self.preview()
        with RecordingGate(self.root):self.assertEqual(self.remove(preview)['status'],'recording_active_or_retention_busy')
        self.assertEqual(self.remove(preview)['status'],'removed')

    def test_corrupt_selected_refused_unselected_preserved(self):
        self.sql('UPDATE records SET payload=? WHERE session=?',(b'corrupt',self.ids()[0]))
        self.assertEqual(self.preview()['status'],'corrupt')
        self.assertEqual(self.remove(self.preview(self.ids(self.second)))['status'],'removed')
        self.assertEqual(self.sql('SELECT payload FROM records'),[(b'corrupt',)])

    def test_unknown_schema_and_invalid_manifest_preserved(self):
        self.sql('PRAGMA user_version=99');before=self.store.path.read_bytes()
        self.assertEqual(self.preview()['status'],'unsupported_store');self.assertEqual(self.store.path.read_bytes(),before)
        self.sql('PRAGMA user_version=1');self.sql('UPDATE sessions SET manifest=? WHERE id=?',('{}',self.ids()[0]))
        self.assertNotEqual(self.preview()['status'],'removal_preview')
        self.assertEqual(len(self.store.sessions()['sessions']),2)

    def test_transaction_failure_rolls_back_migration_and_all_deletes(self):
        preview=self.preview(self.ids(self.first,self.second))
        # Fault after retirement insertion and first DELETE, before commit.
        self.sql("CREATE TRIGGER fail_removal BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.assertEqual(self.remove(preview)['status'],'removal_uncertain')
        self.assertEqual(len(self.store.sessions()['sessions']),2);self.assertEqual(self.sql('PRAGMA user_version'),[(1,)])
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE name='retired_sessions'"),[])

    def test_lost_ack_resolves_retired_without_replay_and_cleans_child(self):
        preview=self.preview()
        job=RecordingJob(self.root,dict(operation='remove',session_ids=self.ids(),expected_version=preview['version'],confirm=True))
        self.addCleanup(job.cancel)
        job.process.wait(timeout=8)
        result=job.cancel('fixture_lost_ack')
        self.assertEqual(result['status'],'removal_uncertain');self.assertEqual(result['session_ids'],self.ids())
        self.assertTrue(result['owned_resources_closed']);self.assertFalse(any(t.is_alive() for t in job.threads))
        result=store_action(self.root,dict(operation='removal_status',session_ids=self.ids()+self.ids(self.second)+['f'*32]))
        rows={row['session_id']:row for row in result['sessions']}
        self.assertEqual([rows[identity]['status'] for identity in self.ids()+self.ids(self.second)+['f'*32]],['retired','present','missing_unknown'])
        self.assertEqual(rows[self.ids()[0]]['evidence_hash'],preview['version'])
        self.assertEqual(self.remove(preview)['status'],'missing_session')

    def test_invalid_selection_and_bounded_retirement(self):
        for ids in ([],self.ids()*2,['bad'],self.ids()*17):
            self.assertEqual(store_action(self.root,dict(operation='preview_remove',session_ids=ids))['status'],'invalid_selection' if ids!=['bad'] else 'invalid_session')
        with patch('aurora_recording_retention.MAX_RETIRED',0):self.assertEqual(self.preview()['status'],'retirement_capacity')
        self.assertEqual(len(self.store.sessions()['sessions']),2)

    def test_no_recording_store_created_by_invalid_or_missing_preview(self):
        root=Path(self.tmp.name)/'absent'
        self.assertEqual(store_action(root,dict(operation='preview_remove',session_ids=self.ids()))['status'],'missing')
        self.assertFalse(root.exists())

    def test_worker_preserves_typed_conflict_receipt(self):
        preview=self.preview();self.publish()
        job=RecordingJob(self.root,dict(operation='remove',session_ids=self.ids(),expected_version=preview['version'],confirm=True))
        self.addCleanup(job.cancel)
        deadline=time.monotonic()+8;result=None
        while result is None and time.monotonic()<deadline:
            result=job.poll();time.sleep(.01)
        self.assertEqual(result['status'],'archive_changed')
        self.assertTrue(result['owned_resources_closed'])

    def test_timeout_keeps_outcome_unknown_until_readback(self):
        preview=self.preview()
        job=RecordingJob(self.root,dict(operation='remove',session_ids=self.ids(),expected_version=preview['version'],confirm=True),timeout=0)
        self.addCleanup(job.cancel)
        result=job.poll()
        self.assertEqual(result['status'],'removal_uncertain');self.assertTrue(result['owned_resources_closed'])
        state=store_action(self.root,dict(operation='removal_status',session_ids=self.ids()))
        self.assertIn(state['sessions'][0]['status'],('present','retired'))
        self.assertIsNotNone(job.process.poll())

    def test_failed_cleanup_keeps_writer_and_retention_lease(self):
        class IncompleteCleanup:
            process=None;started_at_epoch=0
            def poll(self):raise OSError('fixture')
            def cancel(self,*_):return dict(owned_resources_closed=False)
        service=RecordingService(TaskContinuation(),self.root);self.addCleanup(service.close)
        service.set_mode('boundaries');job=IncompleteCleanup();service.job=job
        try:
            service.tick();self.assertIs(service.job,job)
            result=service.close(timeout=0)
            self.assertFalse(result['disposed']);self.assertTrue(result['retention_protected'])
            self.assertEqual(self.preview()['status'],'recording_active_or_retention_busy')
        finally:service.job=None  # Synthetic fixture has no real owned resources.


if __name__=='__main__':unittest.main()
