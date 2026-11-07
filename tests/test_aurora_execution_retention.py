"""Explicit retention contracts against owned synthetic checkpoint stores only."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import aurora_execution_history as history
from aurora_execution_history_job import HistoryJob
from aurora_execution_projection import inspection_snapshot
from test_aurora_execution_inspector import fixture_state


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aurora-retention-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'execution_history'
        self.store = history.ExecutionHistory(self.root)
        self.snapshot = inspection_snapshot(fixture_state())

    def save(self, digit):
        handle = digit*32
        self.store.save(self.snapshot, handle=handle)
        return handle

    def apply(self, preview, **changes):
        request = dict(operation='remove', checkpoint_ids=preview['checkpoint_ids'],
                       expected_version=preview['expected_version'], confirm=True)
        request.update(changes)
        return history.history_action(self.root, request)

    def job(self, request, **kwargs):
        job = HistoryJob(self.root, request, **kwargs)
        self.addCleanup(job.cancel)
        return job

    def finish(self, job):
        deadline = time.monotonic()+12
        result = job.poll()
        while result is None and time.monotonic() < deadline:
            time.sleep(.01); result=job.poll()
        self.assertIsNotNone(result)
        self.assertTrue(result['owned_resources_closed'])
        self.assertIsNotNone(job.process.poll())
        self.assertFalse(any(thread.is_alive() for thread in job.threads))
        return result

    def test_preview_preserves_bytes_and_exact_selection_then_frees_capacity(self):
        self.store=history.ExecutionHistory(self.root,capacity=2)
        a,b=self.save('a'),self.save('b')
        with self.assertRaisesRegex(history.HistoryError,'capacity_reached'):self.save('c')
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        preview=self.store.preview_remove([a])
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)
        self.assertEqual(preview['selected'][0]['task_id'],self.snapshot['task']['task_id'])
        self.assertEqual(preview['checkpoint_ids'],[a])
        self.assertEqual(preview['total_bytes'],len(before[a+'.json']))
        self.assertEqual(self.apply(preview)['removed'],[a])
        self.assertEqual(self.store.load(b)['status'],'loaded')
        self.save('c')
        self.assertEqual(len(self.store.list()['records']),2)

    def test_confirmation_and_selection_bound_version_required(self):
        a,b=self.save('a'),self.save('b')
        preview=self.store.preview_remove([a])
        for confirm in (False,None,1,'true'):
            self.assertEqual(self.apply(preview,confirm=confirm)['status'],'confirmation_required')
        self.assertEqual(self.apply(preview,expected_version='bad')['status'],'invalid_version')
        self.assertEqual(self.apply(preview,checkpoint_ids=[b])['status'],'version_conflict')
        self.assertEqual(self.apply(preview,checkpoint_ids=[a,b])['status'],'version_conflict')
        self.assertEqual(len(self.store.list()['records']),2)

    def test_new_save_invalidates_preview_before_any_removal(self):
        a=self.save('a');preview=self.store.preview_remove([a]);self.save('b')
        self.assertEqual(self.apply(preview)['status'],'version_conflict')
        self.assertEqual(self.store.load(a)['status'],'loaded')

    def test_same_size_content_change_with_restored_mtime_invalidates_preview(self):
        a,b=self.save('a'),self.save('b');preview=self.store.preview_remove([a])
        path=self.root/(b+'.json');before=path.stat();raw=path.read_bytes()
        # A valid JSON byte alteration with no file-size or mtime change.
        path.write_bytes(raw.replace(b'checkpoint_id',b'checkpoint_ix',1))
        os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertEqual(path.stat().st_size,len(raw))
        self.assertEqual(self.apply(preview)['status'],'version_conflict')
        self.assertTrue((self.root/(a+'.json')).exists())

    def test_corrupt_and_unknown_records_are_preserved(self):
        a,b=self.save('a'),self.save('b')
        corrupt=self.root/(b+'.json');corrupt.write_text('{broken')
        unrelated=self.root/'keep.txt';unrelated.write_text('unrelated')
        partial=self.root/('.'+'f'*32+'.'+'e'*32+'.tmp');partial.write_text('unfinished')
        shots=Path(self.temporary.name)/'screenshots';shots.mkdir();(shots/'keep.txt').write_text('separate')
        denied=history.history_action(self.root,dict(operation='preview_remove',checkpoint_ids=[b]))
        self.assertEqual(denied['status'],'corrupt')
        self.assertEqual(self.apply(self.store.preview_remove([a]))['status'],'removed')
        self.assertEqual(corrupt.read_text(),'{broken')
        self.assertEqual(unrelated.read_text(),'unrelated')
        self.assertEqual(partial.read_text(),'unfinished')
        self.assertTrue((shots/'keep.txt').exists())

    def test_selection_validation_never_creates_or_traverses_storage(self):
        for selected in ([],None,['../private'],['a'*32,'a'*32],['a'*32]*17,('a'*32,)):
            result=history.history_action(self.root,dict(operation='preview_remove',checkpoint_ids=selected))
            self.assertNotEqual(result['status'],'removal_preview')
        self.assertEqual(history.history_action(self.root,dict(operation='preview_remove',checkpoint_ids=['a'*32]))['status'],'missing')
        self.assertFalse(self.root.exists())

    def test_changed_inventory_during_preview_is_rejected(self):
        a=self.save('a');original=self.store._retention_state;calls=[]
        def changed():
            result=original();calls.append(1)
            if len(calls)==2:return ('f'*64,result[1])
            return result
        with patch.object(self.store,'_retention_state',side_effect=changed):
            with self.assertRaisesRegex(history.HistoryError,'version_conflict'):self.store.preview_remove([a])
        self.assertEqual(self.store.load(a)['status'],'loaded')

    def test_partial_removal_reports_prefix_uncertain_item_and_unattempted_tail(self):
        a,b,c=[self.save(d) for d in ('a','b','c')]
        preview=self.store.preview_remove([c,a,b]);unlink=Path.unlink
        def fail(path,*args,**kwargs):
            if path.name==b+'.json':raise OSError('fixture failure')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):result=self.apply(preview)
        self.assertEqual(result['status'],'removal_partial')
        self.assertEqual(result['removed'],[a]);self.assertEqual(result['uncertain'],[b])
        self.assertEqual(result['not_attempted'],[c])
        self.assertTrue((self.root/(b+'.json')).exists() and (self.root/(c+'.json')).exists())
        self.assertEqual(self.apply(preview)['status'],'version_conflict')

    def test_unlink_ack_failure_does_not_falsely_report_file_preserved(self):
        a=self.save('a');preview=self.store.preview_remove([a]);unlink=Path.unlink
        def fail_after(path,*args,**kwargs):
            unlink(path,*args,**kwargs)
            raise OSError('fixture lost acknowledgement')
        with patch.object(Path,'unlink',fail_after):result=self.apply(preview)
        self.assertEqual(result['status'],'removal_uncertain')
        self.assertEqual(result['uncertain'],[a]);self.assertFalse((self.root/(a+'.json')).exists())
        self.assertEqual(self.store.list()['records'],[])

    def test_real_worker_preview_remove_and_repeated_apply_conflict(self):
        a=self.save('a')
        preview=self.finish(self.job(dict(operation='preview_remove',checkpoint_ids=[a])))
        request=dict(operation='remove',checkpoint_ids=[a],expected_version=preview['expected_version'],confirm=True)
        self.assertEqual(self.finish(self.job(request))['status'],'removed')
        self.assertEqual(self.finish(self.job(request))['status'],'version_conflict')

    def test_two_competing_removers_cannot_both_report_removal(self):
        a=self.save('a');preview=self.store.preview_remove([a])
        request=dict(operation='remove',checkpoint_ids=[a],expected_version=preview['expected_version'],confirm=True)
        jobs=[self.job(request) for _ in range(2)]
        states=[self.finish(job)['status'] for job in jobs]
        self.assertEqual(states.count('removed'),1)
        self.assertTrue(set(states)<={'removed','writer_busy','version_conflict'})

    def test_cancelled_or_unacknowledged_remove_is_uncertain_and_not_retried(self):
        a=self.save('a');preview=self.store.preview_remove([a])
        request=dict(operation='remove',checkpoint_ids=[a],expected_version=preview['expected_version'],confirm=True)
        job=self.job(request,timeout=0);result=job.poll()
        self.assertEqual(result['status'],'removal_uncertain');self.assertEqual(result['checkpoint_ids'],[a])
        self.assertTrue(result['owned_resources_closed'])
        # A second scoped operation reaches publication but its reply is deliberately not consumed.
        if not (self.root/(a+'.json')).exists():self.save('a')
        preview=self.store.preview_remove([a]);request['expected_version']=preview['expected_version']
        job=self.job(request);deadline=time.monotonic()+5
        while (self.root/(a+'.json')).exists() and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(job.cancel()['status'],'removal_uncertain')
        self.assertEqual(self.store.list()['records'],[])
        self.assertFalse(any(t.is_alive() for t in job.threads))

    def test_cli_uses_same_preview_and_explicit_confirmation(self):
        a=self.save('a');work=Path(self.temporary.name)
        def call(*args):
            output=io.StringIO()
            with patch.object(history,'__file__',str(work/'history.py')),patch('sys.argv',['history.py',*args]),redirect_stdout(output):
                history.main()
            return json.loads(output.getvalue())
        preview=call('preview-remove',a)
        self.assertEqual(call('remove',a,'--expected-version',preview['expected_version'])['status'],'confirmation_required')
        self.assertEqual(call('remove',a,'--expected-version',preview['expected_version'],'--confirm')['status'],'removed')


if __name__=='__main__':unittest.main()
