"""Read-only paging, exact handles, unavailable records and concurrent append."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aurora_task_continuation import TaskContinuation
from aurora_recording_store import RecordingStore, store_action, unavailable_ranges
from aurora_execution_history import canonical


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aurora-timeline-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'records';self.store=RecordingStore(self.root)
        self.task=TaskContinuation(recording_capacity=16)
        self.identity=self.task.recording_status()['session_id']

    def publish(self,count=1,close=False):
        for _ in range(count):self.task.reserve(max_turns=1000,max_seconds=120)
        if close:self.task.close_recording()
        while True:
            batch=self.task.peek_recording(limit=4);manifest=batch['status']
            if manifest['queued']>len(batch['records']):manifest['state']='buffering'
            result=self.store.publish(manifest,batch['records'])
            if batch['records']:self.task.acknowledge_recording(self.identity,result['sequences'])
            if not self.task.recording_status()['queued']:break

    def request(self,**extra):
        return dict(operation='timeline',session_id=self.identity,**extra)

    def test_bounded_pages_order_and_exact_load_after_restart(self):
        self.publish(12,close=True)
        first=self.store.timeline(self.identity,limit=5)
        self.assertEqual([r['sequence'] for r in first['records']],[1,2,3,4,5])
        second=RecordingStore(self.root).timeline(self.identity,after_sequence=first['next_after'],limit=5,expected_version=first['version'])
        self.assertEqual([r['sequence'] for r in second['records']],[6,7,8,9,10])
        last=self.store.timeline(self.identity,after_sequence=second['next_after'],expected_version=first['version'])
        self.assertEqual([r['sequence'] for r in last['records']],[11,12]);self.assertIsNone(last['next_after'])
        selected=second['records'][1]
        loaded=RecordingStore(self.root).record(self.identity,selected['sequence'],selected['digest'])
        self.assertEqual(loaded['record']['sequence'],7)
        self.assertNotIn('inspection',selected)

    def test_empty_reader_creates_no_storage(self):
        self.assertEqual(self.store.sessions()['sessions'],[])
        self.assertEqual(store_action(self.root,self.request())['status'],'missing')
        self.assertFalse(self.root.exists())

    def test_empty_session_and_unknown_open_closure(self):
        self.publish(0)
        page=self.store.timeline(self.identity)
        self.assertEqual(page['records'],[]);self.assertIsNone(page['next_after'])
        self.assertIn('unknown',page['closure'])
        self.assertEqual(page['coverage']['unavailable_total'],0)

    def test_appending_invalidates_page_version_but_not_exact_immutable_handle(self):
        self.publish(4);page=self.store.timeline(self.identity,limit=2)
        self.publish(1)
        self.assertEqual(store_action(self.root,self.request(after_sequence=2,expected_version=page['version']))['status'],'session_changed')
        selected=page['records'][0]
        self.assertEqual(self.store.record(self.identity,1,selected['digest'])['status'],'loaded')

    def test_read_connection_freezes_manifest_and_index_together(self):
        self.publish(1)
        with self.store.connection() as con:
            first,_=self.store._session_state(con,self.identity)
            # A competing writer cannot publish through the active rollback-journal read transaction.
            self.task.reserve(max_turns=1000,max_seconds=120)
            batch=self.task.peek_recording()
            result=store_action(self.root,dict(operation='publish',manifest=batch['status'],records=batch['records']))
            self.assertEqual(result['status'],'publication_uncertain')
            second,_=self.store._session_state(con,self.identity)
            self.assertEqual(first,second)
        self.assertEqual(self.store.sessions()['sessions'][0]['committed_count'],1)

    def test_corrupt_one_record_does_not_hide_other_rows(self):
        self.publish(3,close=True)
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('UPDATE records SET payload=? WHERE sequence=2',(b'{}',));con.commit()
        page=self.store.timeline(self.identity)
        self.assertEqual([r['status'] for r in page['records']],['available','corrupt_or_unsupported','available'])
        self.assertEqual(set(page['records'][1]),{'sequence','status'})

    def test_changed_selected_content_requires_fresh_handle(self):
        self.publish(1)
        selected=self.store.timeline(self.identity)['records'][0]
        record=self.store.record(self.identity,1)['record'];record['observed_at_epoch']+=1
        payload=canonical(record);digest=hashlib.sha256(payload).hexdigest()
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('UPDATE records SET payload=?,digest=? WHERE sequence=1',(payload,digest));con.commit()
        result=store_action(self.root,dict(operation='record',session_id=self.identity,sequence=1,expected_digest=selected['digest']))
        self.assertEqual(result['status'],'record_changed')

    def test_unknown_holes_are_distinct_from_recorded_drops(self):
        for _ in range(20):self.task.reserve(max_turns=1000,max_seconds=120)
        batch=self.task.peek_recording(limit=4)
        self.store.publish(batch['status'],batch['records'])
        page=self.store.timeline(self.identity)
        self.assertEqual(page['coverage']['uncommitted_accepted'],12)
        self.assertEqual(page['coverage']['ranges'],[
            dict(first=5,last=16,status='unavailable_unknown'),
            dict(first=17,last=20,status='recorded_drop',reason='capacity')])
        self.assertEqual(page['coverage']['unavailable_total'],16)

    def test_huge_unknown_gap_uses_interval_arithmetic_and_truncation(self):
        manifest=dict(sequence=1000000000,accepted=70,dropped=1000000000-70,gaps=[])
        result=unavailable_ranges(manifest,list(range(2,142,2)))
        self.assertEqual(len(result['ranges']),64);self.assertEqual(result['omitted_ranges'],7)
        self.assertTrue(all(r['status']=='unavailable_unknown' for r in result['ranges']))

    def test_one_bad_manifest_isolated_from_other_sessions(self):
        self.publish(1)
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('INSERT INTO sessions VALUES(?,?,?)',('a'*32,'{}',1));con.commit()
        rows=self.store.sessions()['sessions']
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(r['status']=='available' for r in rows),1)
        self.assertEqual(sum(r['status']=='invalid_session_metadata' for r in rows),1)

    def test_read_only_listing_and_paging_do_not_change_database_bytes(self):
        self.publish(4,close=True)
        before=self.store.path.read_bytes()
        self.store.sessions();self.store.timeline(self.identity);self.store.record(self.identity,1)
        self.assertEqual(before,self.store.path.read_bytes())

    def test_checksum_projection_does_not_hold_database_read_lock(self):
        from aurora_recording_store import decode_stored_record
        self.publish(1)
        def check_after_append(*args,**kwargs):
            self.publish(1)
            return decode_stored_record(*args,**kwargs)
        with patch('aurora_recording_store.decode_stored_record',side_effect=check_after_append):
            page=self.store.timeline(self.identity)
        self.assertEqual(page['committed_count'],1)
        self.assertEqual(self.store.sessions()['sessions'][0]['committed_count'],2)

    def test_page_byte_budget_returns_a_usable_cursor(self):
        self.publish(4)
        with patch('aurora_recording_store.MAX_PAGE_BYTES',1):
            page=self.store.timeline(self.identity)
        self.assertEqual(len(page['records']),1);self.assertEqual(page['next_after'],1)

    def test_invalid_options_and_closed_manifest_missing_record_fail_explicitly(self):
        self.publish(1,close=True)
        for changes in ({'limit':0},{'limit':33},{'after_sequence':-1},{'limit':True}):
            self.assertIn(store_action(self.root,self.request(**changes))['status'],('invalid_counter','invalid_page_size'))
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute('DELETE FROM records');con.commit()
        self.assertEqual(store_action(self.root,self.request())['status'],'incomplete_manifest')

    def test_cli_rejects_ignored_paging_options(self):
        command=[sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'aurora_recording_store.py')]
        result=subprocess.run(command+['record',self.identity,'1','--expected-version','abc'],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,2)
        self.assertIn('require timeline',result.stderr)

    def test_backward_timestamps_do_not_reorder_sequences(self):
        for _ in range(2):self.task.reserve(max_turns=1000,max_seconds=120)
        batch=self.task.peek_recording()
        batch['records'][0]['observed_at_epoch']=2000
        batch['records'][1]['observed_at_epoch']=1000
        self.store.publish(batch['status'],batch['records'])
        rows=self.store.timeline(self.identity)['records']
        self.assertEqual([r['sequence'] for r in rows],[1,2])
        self.assertEqual([r['observed_at_epoch'] for r in rows],[2000,1000])


if __name__=='__main__':unittest.main()
