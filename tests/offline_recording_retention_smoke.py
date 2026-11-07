"""Hidden Tk retention controls with synthetic recordings and real owned workers."""
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
import aurora_recording_browser as browser
from aurora_recording_gate import RecordingGate
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
    with tempfile.TemporaryDirectory(prefix='aurora-recording-retention-ui-') as temporary:
        root=Path(temporary)/'records';store=RecordingStore(root)
        def publish(closed=True):
            task=TaskContinuation(recording_capacity=16);task.reserve(max_turns=10,max_seconds=120)
            if closed:task.close_recording()
            batch=task.peek_recording(limit=4);store.publish(batch['status'],batch['records'])
            return batch['status']['session_id']
        first=publish();second=publish();incomplete=publish(False)
        def factory(caller_root,request):
            job=RecordingJob(root,request);jobs.append(job);return job
        def finish():
            deadline=time.monotonic()+12
            while view.job is not None and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            app.update()
            check('operation completes and clears callback',view.job is None and view.callback is None)
            check('no Tk callback errors',not errors)
        def select(identity):
            view.session_tree.selection_set(identity);view.session_changed()
        try:
            with patch.object(inspector.ExecutionInspector,'deiconify',lambda self:None),patch.object(browser.RecordingBrowser,'deiconify',lambda self:None),patch.object(browser,'RecordingJob',factory):
                window=inspector.ExecutionInspector.open(app);live=copy.deepcopy(app.state_cache)
                view=window.open_recordings();view.refresh_sessions();finish();select(first)
                check('delete requires a preview',str(view.remove_button['state'])=='disabled' and not view.include_incomplete.get())
                view.browse_session();finish();view.load_selected();finish()
                frozen=copy.deepcopy(window.snapshot)
                view.preview_button.invoke();finish()
                check('preview shows exact identity count and bytes',first in view.status.get() and '1 boundaries' in view.status.get() and 'payload bytes' in view.status.get())
                check('preview enables explicit permanent removal',str(view.remove_button['state'])=='normal' and len(store.sessions()['sessions'])==3)
                select(second)
                check('selection change invalidates preview',view.removal_preview is None and str(view.remove_button['state'])=='disabled')
                select(first);view.preview_removal();finish()
                view.include_incomplete.set(True);view.retention_option_changed()
                check('option change invalidates preview',view.removal_preview is None)
                view.include_incomplete.set(False);view.retention_option_changed();view.preview_removal();finish()
                publish();view.remove_button.invoke();finish()
                check('stale whole archive refuses delete: '+view.status.get()+' / '+str(len(store.sessions()['sessions']))+' / '+str(jobs[-1].result),'archive changed' in view.status.get() and len(store.sessions()['sessions'])==4)
                view.refresh_sessions();finish();select(first)
                with RecordingGate(root):
                    view.preview_removal();finish()
                    check('active writer blocks preview','recording active' in view.status.get() and view.removal_preview is None)
                select(incomplete);view.preview_removal();finish()
                check('incomplete protected by default','incomplete protected' in view.status.get() and view.removal_preview is None)
                view.include_incomplete.set(True);view.retention_option_changed();view.preview_removal();finish()
                check('explicit incomplete preview warns about loss','Incomplete history cannot be recovered' in view.status.get())
                view.remove_previewed();finish()
                check('explicit incomplete discard removes only selected',incomplete not in view.sessions and len(store.sessions()['sessions'])==3)
                select(first);view.include_incomplete.set(False);view.retention_option_changed();view.preview_removal();finish()
                view.remove_previewed();finish()
                check('removal leaves loaded historical view and live task intact',window.snapshot==frozen and app.state_cache==live and window.snapshot_origin=='recording')
                check('loaded boundary marks removed backing session','removed' in window.recording_context['stored_session_now'])
                check('delete clears stale selection and preview',view.removal_preview is None and view.selected_session is None and first not in view.sessions)
                # A real child commits, but cancellation discards its acknowledgement.
                view.refresh_sessions();finish();select(second);view.preview_removal();finish();view.remove_previewed()
                job=view.job;job.process.wait(timeout=8);view.cancel()
                check('lost acknowledgement exposes uncertainty and exact IDs',view.uncertain_removal==[second] and 'uncertain' in view.status.get())
                view.reconcile_button.invoke();finish()
                check('read-only reconciliation finds retirement','retired' in view.status.get() and second not in view.sessions)
                check('reconciliation preserves details','evidence_hash' in view.details.get('1.0','end'))
                check('manual snapshot and capture directories untouched',not (Path(temporary)/'execution_history').exists() and not (Path(temporary)/'capture_artifacts').exists())
                window.destroy();window=view=None
                check('all real workers and pipe threads stopped',all(j.process.poll() is not None and not any(t.is_alive() for t in j.threads) for j in jobs))
        finally:
            if window is not None and window.winfo_exists():window.destroy()
            for job in jobs:job.cancel()
            app.destroy()
    return dict(status='passed',checks=checks,check_count=len(checks),callback_errors=errors,fixture_removed=not root.exists(),
        owned_children=[dict(pid=j.process.pid,started_at_epoch=j.started_at_epoch,alive=j.process.poll() is None) for j in jobs],
        real_provider_calls=0,native_input_calls=0,real_capture_calls=0,displayed_layout_qualified=False)


if __name__=='__main__':print(json.dumps(run_smoke(),indent=2))
