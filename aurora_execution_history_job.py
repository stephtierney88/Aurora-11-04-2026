"""One owned hidden history operation. File I/O and pipes never run on Tk's thread."""
import copy
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from aurora_execution_history import MAX_BYTES, HANDLE, ordinary


class HistoryJob:
    WORKER_NAME = 'aurora_execution_history.py'
    REQUEST_LIMIT = MAX_BYTES + 8192

    def __init__(self, root, request, *, timeout=10):
        self.root, self.request = Path(root).absolute(), copy.deepcopy(request)
        self.request['write_id'] = uuid.uuid4().hex
        self.started_at_epoch, self.deadline = time.time(), time.monotonic() + timeout
        self.process, self.result, self.threads = None, None, []
        self.output = queue.Queue(maxsize=1)
        payload = json.dumps(self.request, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        if len(payload) > self.REQUEST_LIMIT:
            self.result = {'status': 'snapshot_too_large'}
            return
        try:
            self.process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name(self.WORKER_NAME)),
                '--worker', str(self.root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def write():
                try:
                    self.process.stdin.write(payload)
                    self.process.stdin.close()
                except (OSError, ValueError):
                    pass
            def read():
                try:
                    raw = self.process.stdout.read(MAX_BYTES + 8193)
                    value = json.loads(raw) if len(raw) <= MAX_BYTES + 8192 else None
                    self.output.put_nowait(value if isinstance(value, dict) else {'status':'invalid_worker_result'})
                except (OSError, ValueError, queue.Full):
                    try: self.output.put_nowait({'status':'invalid_worker_result'})
                    except queue.Full: pass
            for target, suffix in ((write, 'write'), (read, 'read')):
                thread = threading.Thread(target=target, name='aurora-history-'+suffix, daemon=True)
                self.threads.append(thread)
                thread.start()
        except (OSError, RuntimeError):
            self.cancel('unavailable')

    def _cleanup(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=1)
            for thread in self.threads:
                if thread.ident is not None: thread.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None: stream.close()
        # Only this operation's unpublished temporary name, after its child exits.
        handle = self.request.get('checkpoint_id')
        if self.request.get('operation') == 'save' and isinstance(handle, str) and HANDLE.fullmatch(handle) and self.root.exists():
            try:
                ordinary(self.root, directory=True)
                temporary = self.root / ('.'+handle+'.'+self.request['write_id']+'.tmp')
                if temporary.exists():
                    ordinary(temporary)
                    temporary.unlink()
            except OSError:
                return False
            except ValueError:
                return False
        return not any(thread.is_alive() for thread in self.threads)

    def poll(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        if time.monotonic() >= self.deadline:
            return self.cancel('timed_out')
        if self.process.poll() is None:
            return None
        try:
            result = self.output.get_nowait()
        except queue.Empty:
            if any(thread.is_alive() for thread in self.threads):
                return None
            result = {'status': 'invalid_worker_result'}
        if self.process.returncode != 0:
            return self.cancel('worker_failed')
        if result.get('status') == 'invalid_worker_result':
            return self.cancel('invalid_worker_result')
        self.result = result
        self.result['owned_resources_closed'] = self._cleanup()
        return copy.deepcopy(self.result)

    def cancel(self, reason='cancelled'):
        clean = self._cleanup()
        operation = self.request.get('operation')
        status = 'save_uncertain' if operation == 'save' else 'removal_uncertain' if operation == 'remove' else reason
        self.result = dict(status=status, reason=reason, checkpoint_id=self.request.get('checkpoint_id'),
            checkpoint_ids=self.request.get('checkpoint_ids', []), owned_resources_closed=clean)
        return copy.deepcopy(self.result)
