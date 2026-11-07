import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import io
from contextlib import redirect_stdout

from aurora_execution_projection import inspection_snapshot, normalize_inspection
from aurora_execution_history import ExecutionHistory, HistoryError, history_action, MAX_BYTES
from aurora_execution_history_job import HistoryJob
from test_aurora_execution_inspector import fixture_state


class HistoryTests(unittest.TestCase):
    def test_malformed_metadata_is_rejected_without_worker_crash(self):
        for field in ('task', 'retention', 'display_omitted'):
            for value in ([], 'invalid', None):
                with self.subTest(field=field, value=value):
                    snapshot=copy.deepcopy(self.snapshot); snapshot[field]=value
                    result=history_action(self.root, dict(operation='save', checkpoint_id=uuid.uuid4().hex, inspection=snapshot))
                    self.assertEqual(result['status'],'invalid_snapshot')
        self.assertFalse(self.root.exists())

    def test_unrenderable_historical_time_does_not_break_inspection(self):
        from aurora_execution_inspector import ExecutionInspector
        self.assertIn('not displayable',ExecutionInspector.history_time_label(1e300))
        self.assertEqual(ExecutionInspector.history_time_label(None),'time unknown')
        self.assertIn('1970',ExecutionInspector.history_time_label(100000))

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'tools/build_public_snapshot.py').is_file(), 'Private export tooling is not shipped')
    def test_public_snapshot_excludes_and_audits_local_history(self):
        from tools.build_public_snapshot import selected, audit
        relative='execution_history/'+('a'*32)+'.json'
        self.assertFalse(selected(relative))
        self.assertTrue(selected('aurora_execution_history.py'))
        fixture=Path(self.temp.name)/'public-fixture'
        record=fixture/relative; record.parent.mkdir(parents=True); record.write_text('{}')
        self.assertTrue(any(item['file']==relative and 'private/local' in item['kind'] for item in audit(fixture)['findings']))

    def test_offline_cli_save_list_load_use_the_same_projection(self):
        import aurora_execution_history as history
        work=Path(self.temp.name)
        (work/'aurora_control_panel_state.json').write_text(json.dumps(fixture_state()))
        def call(*args):
            output=io.StringIO()
            with patch.object(history,'__file__',str(work/'history.py')), patch('sys.argv',['history.py',*args]), redirect_stdout(output):
                history.main()
            return json.loads(output.getvalue())
        saved=call('save')
        self.assertEqual(saved['status'],'saved')
        self.assertEqual(call('list')['records'][0]['checkpoint_id'],saved['checkpoint_id'])
        self.assertEqual(call('load',saved['checkpoint_id'])['status'],'loaded')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aurora-history-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'history'
        self.store = ExecutionHistory(self.root)
        self.snapshot = inspection_snapshot(fixture_state())

    def job(self, request, **kwargs):
        job = HistoryJob(self.root, request, **kwargs)
        self.addCleanup(job.cancel)
        return job

    def finish(self, job):
        deadline = time.monotonic() + 12
        result = job.poll()
        while result is None and time.monotonic() < deadline:
            time.sleep(.01); result = job.poll()
        self.assertIsNotNone(result)
        self.assertTrue(result['owned_resources_closed'])
        self.assertIsNotNone(job.process.poll())
        self.assertFalse(any(t.is_alive() for t in job.threads))
        return result

    def test_listing_does_not_enable_storage_or_create_directory(self):
        self.assertEqual(self.store.list()['records'], [])
        self.assertFalse(self.root.exists())

    def test_restart_roundtrip_preserves_exact_metadata_and_source_time(self):
        result = self.store.save(self.snapshot, saved_at=1000)
        self.snapshot['task']['task_id'] = 'unrelated-current-task'
        loaded = ExecutionHistory(self.root).load(result['checkpoint_id'])
        self.assertNotEqual(loaded['inspection']['task']['task_id'], 'unrelated-current-task')
        self.assertEqual(loaded['saved_at_epoch'], 1000)
        self.assertEqual(loaded['inspection']['source_export']['timestamp'], '2000-01-01 00:00:00')
        self.assertEqual(loaded['inspection']['collections']['requests'][0]['transport_evidence']['attempts'][0]['provider_request_id'], 'req_fixture')
        self.assertIn('current outcome is unknown', loaded['notice'])

    def test_same_handle_idempotent_but_conflicting_save_never_replaces(self):
        handle = uuid.uuid4().hex
        self.store.save(self.snapshot, handle=handle, saved_at=1000)
        before = (self.root/(handle+'.json')).read_bytes()
        self.assertEqual(self.store.save(self.snapshot, handle=handle, saved_at=2000)['status'], 'already_saved')
        changed = copy.deepcopy(self.snapshot); changed['task']['status'] = 'stopped'
        with self.assertRaisesRegex(HistoryError, 'handle_conflict'): self.store.save(changed, handle=handle)
        self.assertEqual((self.root/(handle+'.json')).read_bytes(), before)

    def test_capacity_preserves_old_records_and_legacy_session_data(self):
        store = ExecutionHistory(self.root, capacity=1)
        handle = store.save(self.snapshot)['checkpoint_id']
        with self.assertRaisesRegex(HistoryError, 'capacity_reached'): store.save(self.snapshot)
        self.assertEqual(len(store.list()['records']),1)
        self.assertEqual(store.load(handle)['inspection'],normalize_inspection(self.snapshot))

    def test_atomic_publication_failure_removes_only_owned_temp(self):
        self.root.mkdir()
        unrelated = self.root/'keep.txt'; unrelated.write_text('fixture')
        partial = self.root/('.'+'a'*32+'.'+'b'*32+'.tmp'); partial.write_text('incomplete fixture')
        with patch('aurora_execution_history.os.link', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError): self.store.save(self.snapshot)
        listing=self.store.list()
        self.assertEqual(listing['records'],[])
        self.assertEqual(listing['partial_files'],1)
        self.assertTrue(partial.exists() and unrelated.exists())

    def test_checksum_and_schema_failures_are_visible_without_fallback(self):
        handle=self.store.save(self.snapshot)['checkpoint_id']; path=self.root/(handle+'.json')
        original=json.loads(path.read_text())
        changed=copy.deepcopy(original); changed['saved_at_epoch']+=1; path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(HistoryError,'checksum_mismatch'): self.store.load(handle)
        self.assertEqual(self.store.list()['records'][0]['status'],'checksum_mismatch')
        changed['schema']='future_v900';path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(HistoryError,'unsupported_schema'): self.store.load(handle)
        path.write_text('{partial')
        with self.assertRaisesRegex(HistoryError,'corrupt'): self.store.load(handle)

    def test_invalid_handles_never_open_other_files(self):
        for handle in ('../secrets','C:/anything', 'https://host', 'a'*32+'.json','B'*32,None):
            with self.subTest(handle=handle), self.assertRaisesRegex(HistoryError,'invalid_handle'): self.store.load(handle)
        self.assertFalse(self.root.exists())

    def test_missing_snapshot_does_not_resolve_nearby_task(self):
        self.store.save(self.snapshot)
        with self.assertRaisesRegex(HistoryError,'missing'): self.store.load('f'*32)

    def test_old_export_and_omission_counts_survive(self):
        old=copy.deepcopy(self.snapshot)
        old.pop('source_export')
        for row in old['collections']['requests']:
            row.pop('frame_artifact',None);row.pop('transport_evidence',None)
        old['display_omitted']['events']=500
        handle=self.store.save(old)['checkpoint_id']
        loaded=self.store.load(handle)['inspection']
        self.assertIsNone(loaded['source_export']['timestamp'])
        self.assertEqual(loaded['display_omitted']['events'],500)
        self.assertNotIn('transport_evidence',loaded['collections']['requests'][0])

    def test_no_raw_private_fields_or_unknown_metadata_persist(self):
        snapshot=copy.deepcopy(self.snapshot)
        snapshot['prompt']='PRIVATE_PROMPT'
        snapshot['collections']['requests'][0]['api_key']='PRIVATE_KEY'
        snapshot['source_export']['timestamp']='PRIVATE_PATH'
        handle=self.store.save(snapshot)['checkpoint_id']
        self.assertNotIn('PRIVATE',(self.root/(handle+'.json')).read_text())

    def test_ambiguous_empty_and_oversized_snapshots_refused(self):
        invalid=copy.deepcopy(self.snapshot)
        invalid['collections']['requests'].append(copy.deepcopy(invalid['collections']['requests'][0]))
        for snapshot in (invalid, {}, None):
            self.assertEqual(history_action(self.root,dict(operation='save',checkpoint_id=uuid.uuid4().hex,inspection=snapshot))['status'],'invalid_snapshot')
        with patch('aurora_execution_history.MAX_BYTES',1):
            with self.assertRaisesRegex(HistoryError,'snapshot_too_large'): self.store.save(self.snapshot)
        self.assertFalse(self.root.exists())

    def test_oversized_files_and_links_are_not_followed(self):
        handle=self.store.save(self.snapshot)['checkpoint_id'];path=self.root/(handle+'.json')
        with path.open('wb') as f: f.truncate(MAX_BYTES+1)
        with self.assertRaisesRegex(HistoryError,'record_too_large'): self.store.load(handle)
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(HistoryError,'unsafe_path'): self.store.load(handle)

    def test_real_worker_save_list_load_and_cleanup(self):
        handle=uuid.uuid4().hex
        result=self.finish(self.job(dict(operation='save',checkpoint_id=handle,inspection=self.snapshot)))
        self.assertEqual(result['status'],'saved')
        self.assertEqual(self.finish(self.job({'operation':'list'}))['records'][0]['checkpoint_id'],handle)
        loaded=self.finish(self.job({'operation':'load','checkpoint_id':handle}))
        self.assertEqual(loaded['inspection'],normalize_inspection(self.snapshot))

    def test_writer_lease_conflict_keeps_other_pending_files(self):
        with self.store._lease():
            pending=self.root/('.'+'a'*32+'.'+'b'*32+'.tmp');pending.write_text('another writer fixture')
            result=self.finish(self.job(dict(operation='save',checkpoint_id='a'*32,inspection=self.snapshot)))
            self.assertEqual(result['status'],'writer_busy')
            self.assertTrue(pending.exists())

    def test_concurrent_last_slot_cannot_exceed_capacity(self):
        for _ in range(63): self.store.save(self.snapshot)
        jobs=[self.job(dict(operation='save',checkpoint_id=uuid.uuid4().hex,inspection=self.snapshot)) for _ in range(2)]
        results=[self.finish(job)['status'] for job in jobs]
        self.assertEqual(results.count('saved'),1)
        self.assertTrue(set(results) <= {'saved','writer_busy','capacity_reached'})
        self.assertEqual(len(self.store.list()['records']),64)

    def test_cancelled_save_has_explicit_uncertain_outcome_and_exact_handle(self):
        handle=uuid.uuid4().hex
        job=self.job(dict(operation='save',checkpoint_id=handle,inspection=self.snapshot),timeout=0)
        result=job.poll()
        self.assertEqual(result['status'],'save_uncertain')
        self.assertEqual(result['checkpoint_id'],handle)
        self.assertTrue(result['owned_resources_closed'])
        self.assertFalse(any(t.is_alive() for t in job.threads))
        self.assertIsNotNone(job.process.poll())
        self.assertFalse(list(self.root.glob('.*.tmp')))

    def test_lost_save_ack_can_be_reconciled_without_auto_replay(self):
        handle=uuid.uuid4().hex
        job=self.job(dict(operation='save',checkpoint_id=handle,inspection=self.snapshot))
        deadline=time.monotonic()+5
        while not (self.root/(handle+'.json')).exists() and time.monotonic()<deadline: time.sleep(.01)
        result=job.cancel()
        self.assertEqual(result['status'],'save_uncertain')
        self.assertEqual(ExecutionHistory(self.root).load(handle)['checkpoint_id'],handle)
        self.assertEqual(len(self.store.list()['records']),1)


if __name__=='__main__': unittest.main()
