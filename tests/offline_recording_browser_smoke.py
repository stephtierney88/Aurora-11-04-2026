"""Hidden Tk exact-record browsing; synthetic metadata and owned file readers only."""
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aurora_execution_inspector as inspector
import aurora_recording_browser as browser
from aurora_recording_service import RecordingJob
from aurora_recording_store import RecordingStore
from aurora_task_continuation import TaskContinuation
from test_aurora_execution_inspector import fixture_state


def run_smoke():
    checks,jobs,errors=[],[],[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    app=tk.Tk();app.withdraw();app.state_cache=fixture_state()
    app.report_callback_exception=lambda kind,value,trace:errors.append(kind.__name__+': '+str(value))
    window=view=None
    with tempfile.TemporaryDirectory(prefix='aurora-recording-ui-') as temporary:
        root=Path(temporary)/'records';store=RecordingStore(root)
        task=TaskContinuation(recording_capacity=16);session=task.recording_status()['session_id']
        def publish(count,close=False):
            for _ in range(count):task.reserve(max_turns=1000,max_seconds=120)
            if close:task.close_recording()
            while True:
                batch=task.peek_recording(limit=4);manifest=batch['status']
                if manifest['queued']>len(batch['records']):manifest['state']='buffering'
                result=store.publish(manifest,batch['records'])
                if batch['records']:task.acknowledge_recording(session,result['sequences'])
                if not task.recording_status()['queued']:break
        def factory(caller_root,request):
            check('reader uses installation recording root',caller_root==Path(browser.__file__).resolve().parent/'execution_recordings')
            job=RecordingJob(root,request);jobs.append(job);return job
        def finish():
            deadline=time.monotonic()+12
            while view.job is not None and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            app.update()
            check('read completes and clears owned callback',view.job is None and view.callback is None)
            check('no Tk callback errors',not errors)
        try:
            with patch.object(inspector.ExecutionInspector,'deiconify',lambda self:None),patch.object(browser.RecordingBrowser,'deiconify',lambda self:None),patch.object(browser,'RecordingJob',factory):
                window=inspector.ExecutionInspector.open(app);live=copy.deepcopy(app.state_cache)
                view=window.open_recordings()
                check('opening browser does not enable recording or create storage',not root.exists() and view.job is None)
                check('one reusable browser belongs to inspector',window.open_recordings() is view)
                view.refresh_sessions();finish()
                check('empty store is an empty listing without storage creation',not view.sessions and not root.exists())
                publish(16);publish(6)
                view.refresh_sessions();finish()
                check('listing leaves live view unchanged',window.snapshot_origin=='live' and app.state_cache==live)
                view.browse_button.invoke();finish()
                check('first page is ordered and bounded',list(view.records)==[str(n) for n in range(1,17)] and view.page['next_after']==16)
                check('open session uncertainty visible', 'unknown' in view.summary.get() and 'unavailable sequences' in view.summary.get())
                view.next_button.invoke();finish()
                check('next page and previous cursor work',list(view.records)==[str(n) for n in range(17,23)] and view.previous==[0])
                view.previous_button.invoke();finish()
                check('previous page restores first sequence range',list(view.records)[0]=='1' and not view.previous)
                view.record_tree.selection_set('3');view.record_changed()
                view.load_button.invoke();finish()
                check('exact selected boundary loads only historical inspector',window.snapshot_origin=='recording' and window.recording_context['sequence']==3 and app.state_cache==live)
                check('historical status and identity are explicit',session in window.summary.get() and 'current outcome unknown' in window.summary.get() and 'recorded_boundary' in window.details.get('1.0','end'))
                check('recording cannot be resaved as new live evidence',str(window.save_button['state'])=='disabled')
                frozen=copy.deepcopy(window.snapshot)
                publish(1)
                view.next_button.invoke();finish()
                check('concurrent append invalidates paging without changing inspector',view.page is None and 'session changed' in view.status.get() and window.snapshot==frozen)
                view.browse_session();finish()
                with closing(sqlite3.connect(store.path)) as con:
                    con.execute('UPDATE records SET payload=? WHERE sequence=3',(b'{}',));con.commit()
                view.record_tree.selection_set('3');view.record_changed();view.load_selected();finish()
                check('corruption on selected load keeps prior view', 'corrupt' in view.status.get() and window.snapshot==frozen)
                view.browse_session();finish()
                view.record_tree.selection_set('3');view.record_changed()
                check('corrupt index row is visible and cannot load',view.records['3']['status']=='corrupt_or_unsupported' and str(view.load_button['state'])=='disabled')
                view.toggle_details()
                check('details include exact manifest and gaps',view.detail_area.winfo_manager() and 'coverage' in view.details.get('1.0','end'))
                view.toggle_details()
                window.refresh_button.invoke()
                check('latest export clears recorded context without restoring actions',window.snapshot_origin=='live' and window.recording_context is None and app.state_cache==live)
                class Pending:
                    cancelled=False
                    def __init__(self,_root,request):self.request=request
                    def poll(self):return None
                    def cancel(self):self.cancelled=True;return dict(status='cancelled',owned_resources_closed=True)
                with patch.object(browser,'RecordingJob',Pending):
                    view.browse_session();pending=view.job;callback=view.callback
                    view.cancel_button.invoke()
                    check('cancel stops reader and callback without replacing inspector',pending.cancelled and view.job is None and callback not in app.tk.splitlist(app.tk.call('after','info')) and window.snapshot_origin=='live')
                    view.browse_session();pending=view.job;view.destroy();view=None
                    check('closing browser cleans owned reader',pending.cancelled and window.recording_browser is None)
                view=window.open_recordings();view.refresh_sessions();finish();view.browse_session();finish()
                check('restart browsing reaches same durable session',view.page['session_id']==session)
                with closing(sqlite3.connect(store.path)) as con:
                    con.execute('INSERT INTO sessions VALUES(?,?,?)',('a'*32,'{}',0));con.commit()
                view.refresh_sessions();finish()
                check('invalid session explains why browsing is unavailable','Unavailable:' in view.session_tree.item('a'*32,'values')[1])
                view.session_tree.selection_set('a'*32);view.session_changed()
                check('invalid session cannot start a guessed read',str(view.browse_button['state'])=='disabled')
                view.session_tree.selection_set(session);view.session_changed();view.browse_session();finish()
                view.record_tree.selection_set('1');view.record_changed()
                class CleanupRetry(Pending):
                    attempts=0
                    def cancel(self):
                        self.attempts+=1
                        return dict(status='cancelled',owned_resources_closed=self.attempts>1)
                with patch.object(browser,'RecordingJob',CleanupRetry):
                    view.load_selected();pending=view.job
                    check('failed cleanup keeps owned job and browser available',view.destroy() is False and view.job is pending and view.winfo_exists())
                    view.cancel()
                    check('explicit cleanup retry releases job',view.job is None and pending.attempts==2)
                with patch.object(browser,'RecordingJob',Pending):
                    view.load_selected();pending=view.job
                    view.record_tree.selection_set('2');view.record_changed()
                    check('changing selected boundary cancels in-flight exact load',pending.cancelled and view.job is None and window.snapshot_origin=='live')
                    view.load_selected();pending=view.job
                    window.refresh_button.invoke()
                    check('return to live export cancels in-flight historical load',pending.cancelled and view.job is None and window.snapshot_origin=='live')
                    view.browse_session();pending=view.job;window.destroy();window=None;view=None
                    check('parent close owns browser and reader cleanup',pending.cancelled)
                check('all real reader processes and pipe threads stopped',all(j.process.poll() is not None and not any(t.is_alive() for t in j.threads) for j in jobs))
        finally:
            if window is not None and window.winfo_exists():window.destroy()
            for job in jobs:job.cancel()
            app.destroy()
    return dict(status='passed',checks=checks,check_count=len(checks),callback_errors=errors,fixture_removed=not root.exists(),
                owned_children=[dict(pid=j.process.pid,started_at_epoch=j.started_at_epoch,alive=j.process.poll() is None) for j in jobs],
                real_provider_calls=0,native_input_calls=0,real_capture_calls=0,displayed_layout_qualified=False)


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
