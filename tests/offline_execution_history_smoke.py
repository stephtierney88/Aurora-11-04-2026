"""Hidden inspector save/restart/load proof using only synthetic metadata and local files."""
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
    checks, jobs = [], []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    app=tk.Tk();app.withdraw();app.state_cache=fixture_state()
    window=None
    with tempfile.TemporaryDirectory(prefix='aurora-history-ui-') as temporary:
        root=Path(temporary)/'history'
        def factory(caller_root, request):
            check('history uses installation root rather than imported path',caller_root==Path(inspector.__file__).resolve().parent/'execution_history')
            job=HistoryJob(root,request);jobs.append(job);return job
        def finish():
            deadline=time.monotonic()+12
            while window.history_job is not None and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            check('history operation completes and clears Tk callback',window.history_job is None and window.history_callback is None)
        try:
            with patch.object(inspector.ExecutionInspector,'deiconify',lambda self:None), patch.object(inspector,'HistoryJob',factory):
                window=inspector.ExecutionInspector.open(app)
                original=copy.deepcopy(window.snapshot)
                check('history starts collapsed and creates no storage',not window.history_area.winfo_manager() and not root.exists())
                window.save_button.invoke()
                app.state_cache=fixture_state();live=copy.deepcopy(app.state_cache)
                finish()
                saved=ExecutionHistory(root).list()['records'][0]
                check('save uses frozen selection rather than newer live export',saved['task_id']==original['task']['task_id'] and window.snapshot==original)
                check('saving does not mutate runtime export',app.state_cache==live)
                window.destroy()
                window=inspector.ExecutionInspector.open(app)
                check('reopen still defaults to live export',window.snapshot['task']['task_id']==live['continuation']['active_task']['task_id'])
                window.toggle_history();finish()
                check('listing does not silently load historical task',window.snapshot_origin=='live' and len(window.history_rows)==1)
                window.history_load.invoke();finish()
                check('explicit historical load restores only inspection view',window.snapshot_origin=='history' and window.snapshot==original and app.state_cache==live)
                check('historical running status is clearly qualified', 'HISTORICAL' in window.summary.get() and 'current outcome unknown' in window.summary.get() and 'No runtime' in window.notice.get())
                check('historical view is not resaved as fresh runtime evidence',str(window.save_button['state'])=='disabled')
                window.collection.set('requests');window.render()
                check('checkpoint identity and exact provider evidence remain inspectable',saved['checkpoint_id'] in window.details.get('1.0','end') and 'req_fixture' in window.details.get('1.0','end'))
                frozen=copy.deepcopy(window.snapshot)
                (root/(saved['checkpoint_id']+'.json')).unlink()
                window.history_load.invoke();finish()
                check('missing saved file leaves existing view intact',window.snapshot==frozen and 'missing' in window.history_status.get())
                window.refresh_button.invoke()
                check('load latest returns to live view without restoring actions',window.snapshot_origin=='live' and window.snapshot['task']['task_id']==live['continuation']['active_task']['task_id'] and app.state_cache==live)
                class Pending:
                    cancelled=False
                    def __init__(self,_root,request): self.request=request
                    def poll(self): return None
                    def cancel(self):
                        self.cancelled=True
                        return dict(status='save_uncertain',checkpoint_id=self.request['checkpoint_id'],owned_resources_closed=True)
                with patch.object(inspector,'HistoryJob',Pending):
                    window.save_button.invoke();pending=window.history_job
                    window.history_cancel.invoke()
                    check('cancel exposes uncertain save handle and clears callback',pending.cancelled and pending.request['checkpoint_id'] in window.history_status.get() and 'uncertain' in window.history_status.get() and window.history_callback is None)
                    window.save_button.invoke();pending=window.history_job;callback=window.history_callback
                    window.destroy();window=None
                    check('close cancels owned pending history operation',pending.cancelled and callback not in app.tk.splitlist(app.tk.call('after','info')))
                check('all real helpers and pipe threads stopped',all(j.process.poll() is not None and not any(t.is_alive() for t in j.threads) for j in jobs))
        finally:
            if window is not None and window.winfo_exists():window.destroy()
            for job in jobs:job.cancel()
            app.destroy()
    return dict(status='passed',checks=checks,check_count=len(checks),fixture_removed=not root.exists(),
                owned_children=[dict(pid=j.process.pid,started_at_epoch=j.started_at_epoch,alive=j.process.poll() is None) for j in jobs],
                native_input_calls=0,real_capture_calls=0,real_provider_calls=0,displayed_layout_qualified=False)


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
