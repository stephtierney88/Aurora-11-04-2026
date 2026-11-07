"""Hidden Tk retention workflow; no runtime, native input, capture or provider calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aurora_execution_inspector as inspector
from aurora_execution_history import ExecutionHistory
from aurora_execution_history_job import HistoryJob
from test_aurora_execution_inspector import fixture_state


def run_smoke():
    checks,jobs=[],[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    app=tk.Tk();app.withdraw();app.state_cache=fixture_state()
    live=copy.deepcopy(app.state_cache);window=None
    callback_errors=[]
    app.report_callback_exception=lambda *error:callback_errors.append(str(error[1]))
    with tempfile.TemporaryDirectory(prefix='aurora-retention-ui-') as temporary:
        root=Path(temporary)/'execution_history';store=ExecutionHistory(root)
        snapshot=inspector.inspection_snapshot(live)
        a,b,c=[d*32 for d in ('a','b','c')]
        store.save(snapshot,handle=a);store.save(snapshot,handle=b)
        def factory(caller_root,request):
            assert caller_root==Path(inspector.__file__).resolve().parent/'execution_history'
            job=HistoryJob(root,request);jobs.append(job);return job
        def finish():
            deadline=time.monotonic()+12
            while window.history_job is not None and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            assert window.history_job is None and window.history_callback is None,'operation did not finish'
        def select(handle):
            window.history_selector.current(next(i for i,row in enumerate(window.history_rows) if row['checkpoint_id']==handle))
            window.history_selector.event_generate('<<ComboboxSelected>>');app.update()
        def refresh():
            window.history_refresh.invoke();finish()
        def preview(handle):
            select(handle);window.history_preview_remove.invoke();finish()
        try:
            with patch.object(inspector.ExecutionInspector,'deiconify',lambda self:None),patch.object(inspector,'HistoryJob',factory):
                window=inspector.ExecutionInspector.open(app)
                check('delete disabled without preview',str(window.history_remove['state'])=='disabled')
                window.toggle_history();finish()
                preview(a)
                check('preview names exact ID and permanent effect',a in window.removal_text.get() and 'permanently delete' in window.removal_text.get() and 'No undo' in window.removal_text.get())
                check('preview preserves archive and live runtime',len(store.list()['records'])==2 and app.state_cache==live)
                check('explicit preview enables delete',str(window.history_remove['state'])=='normal')
                window.refresh_button.invoke()
                check('loading latest export clears removal preview',window.removal_preview is None and str(window.history_remove['state'])=='disabled')
                preview(a)
                select(b)
                check('selection change invalidates preview',window.removal_preview is None and str(window.history_remove['state'])=='disabled' and not window.removal_text.get())
                preview(a);store.save(snapshot,handle=c)
                window.history_remove.invoke();finish()
                check('archive change refuses stale preview without deletion','changed since preview' in window.history_status.get() and len(store.list()['records'])==3)
                check('failed removal requires fresh list and preview',not window.history_rows and window.removal_preview is None and str(window.history_remove['state'])=='disabled')
                refresh();select(a);window.history_load.invoke();finish()
                historical=copy.deepcopy(window.snapshot)
                preview(a);window.history_remove.invoke();finish()
                check('delete removes only previewed file',not (root/(a+'.json')).exists() and (root/(b+'.json')).exists() and (root/(c+'.json')).exists())
                check('loaded historical view remains inspectable after deletion',window.snapshot==historical and window.snapshot_origin=='history' and window.history_context['saved_file_now']=='removed')
                check('removal reports exact ID and requires refreshed selection',a in window.history_status.get() and not window.history_rows)
                check('runtime remains unchanged after removal',app.state_cache==live)
                refresh();preview(b)
                class Pending:
                    def __init__(self,_root,request):self.request=request;self.cancelled=False
                    def poll(self):return None
                    def cancel(self):
                        self.cancelled=True
                        return dict(status='removal_uncertain',checkpoint_ids=self.request['checkpoint_ids'],owned_resources_closed=True)
                with patch.object(inspector,'HistoryJob',Pending):
                    window.history_remove.invoke();pending=window.history_job;window.history_cancel.invoke()
                    check('cancel gives exact uncertain IDs without automatic retry',pending.cancelled and b in window.history_status.get() and 'uncertain' in window.history_status.get() and window.history_job is None)
                    check('cancel clears callback and stale preview',window.history_callback is None and window.removal_preview is None and not window.history_rows)
                check('cancelled fixture preserves unattempted files',(root/(b+'.json')).exists() and (root/(c+'.json')).exists())
                (root/(c+'.json')).write_text('{corrupt fixture')
                refresh();select(c)
                check('corrupt saved files cannot be armed for removal',str(window.history_preview_remove['state'])=='disabled' and str(window.history_remove['state'])=='disabled')
                preview(b)
                with patch.object(inspector,'HistoryJob',Pending):
                    window.history_remove.invoke();pending=window.history_job;callback=window.history_callback
                    window.destroy();window=None
                    check('close cancels owned operation and callback',pending.cancelled and callback not in app.tk.splitlist(app.tk.call('after','info')))
                check('all real helpers and pipe threads stopped',all(j.process.poll() is not None and not any(t.is_alive() for t in j.threads) for j in jobs))
                check('no Tk callback errors',not callback_errors)
        finally:
            if window is not None and window.winfo_exists():window.destroy()
            for job in jobs:job.cancel()
            app.destroy()
    return dict(status='passed',checks=checks,check_count=len(checks),fixture_removed=not root.exists(),
        owned_children=[dict(pid=j.process.pid,started_at_epoch=j.started_at_epoch,alive=j.process.poll() is None) for j in jobs],
        native_input_calls=0,real_capture_calls=0,real_provider_calls=0,displayed_layout_qualified=False)


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
