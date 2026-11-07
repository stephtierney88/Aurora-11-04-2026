"""Hidden Tk artifact checks using synthetic local files, never native capture/input."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
import aurora_execution_inspector as inspector
from aurora_capture_artifacts import ArtifactCheck, capture_reference
from aurora_capture_store import save_capture
from test_aurora_execution_inspector import fixture_state


def run_smoke():
    checks, children = [], []
    def check(label, condition):
        assert condition, label
        checks.append(label)
    app = tk.Tk()
    app.withdraw()
    app.state_cache = fixture_state()
    window = None
    with tempfile.TemporaryDirectory(prefix='aurora-inspector-test-') as temporary:
        root = Path(temporary)
        path = save_capture(Image.new('RGB', (12, 8), 'purple'), root)
        ref = capture_reference(path, 'a'*32, root)
        app.state_cache['continuation']['active_task']['progress']['requests'][0]['frame_artifact'] = ref
        def checker(caller_root, reference):
            check('UI supplies installation root rather than export path', caller_root == Path(inspector.__file__).resolve().parent / 'screenshots')
            job = ArtifactCheck(root, reference)
            children.append(job)
            return job
        try:
            with patch.object(inspector.ExecutionInspector, 'deiconify', lambda self: None), patch.object(inspector, 'ArtifactCheck', checker):
                window = inspector.ExecutionInspector.open(app)
                window.collection.set('requests'); window.render()
                check('request-local transport and provider IDs visible without private fields',
                      'req_fixture' in window.details.get('1.0','end') and 'PRIVATE' not in window.details.get('1.0','end'))
                frozen = copy.deepcopy(window.snapshot)
                window.artifact_button.invoke()
                deadline = time.monotonic() + 10
                while window.artifact_check is not None and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                check('real owned checker returns available in selected detail', window.artifact_results['r1']['status'] == 'available' and 'local_artifact_check_now' in window.details.get('1.0', 'end'))
                check('file verification leaves frozen task unchanged', window.snapshot == frozen)
                check('completed checker and Tk job are cleared', window.artifact_check is None and window.artifact_job is None and children[-1].process.poll() is not None)
                Path(path).unlink()
                window.artifact_button.invoke()
                deadline = time.monotonic() + 10
                while window.artifact_check is not None and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                check('recheck exposes deletion without repairing historical record', window.artifact_results['r1']['status'] == 'missing' and window.snapshot == frozen)
            class Pending:
                cancelled = False
                def __init__(self, *_args): pass
                def poll(self): return None
                def cancel(self):
                    self.cancelled = True
                    return {'status': 'cancelled'}
            with patch.object(inspector, 'ArtifactCheck', Pending):
                window.artifact_button.invoke()
                pending, callback = window.artifact_check, window.artifact_job
                window.destroy()
                window = None
                check('close cancels pending checker and removes callback', pending.cancelled and callback not in app.tk.splitlist(app.tk.call('after', 'info')))
            check('no live artifact checker children', all(child.process.poll() is not None for child in children))
        finally:
            if window is not None and window.winfo_exists(): window.destroy()
            for child in children: child.cancel()
            app.destroy()
    return dict(status='passed', checks=checks, check_count=len(checks), fixture_removed=not root.exists(),
                owned_children=[dict(pid=c.process.pid, started_at_epoch=c.started_at_epoch, alive=c.process.poll() is None) for c in children],
                native_input_calls=0, real_capture_calls=0, real_api_calls=0, displayed_layout_qualified=False)


if __name__ == '__main__':
    print(json.dumps(run_smoke(), indent=2))
