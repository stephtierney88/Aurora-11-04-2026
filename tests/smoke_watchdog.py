"""Cooperative smoke diagnostics; the supervising process owns the hard timeout.

The native faulthandler timer reproducibly crashes this host's CPython 3.12.8
while inspecting other threads. This helper calls dump_traceback from an ordinary
Python thread instead. It cannot run while another thread permanently holds the
interpreter lock; keep the independent parent-process deadline in every fixture.
"""
from __future__ import annotations

import faulthandler
import math
import sys
import threading


class SmokeWatchdog:
    def __init__(self, interval=25.0, *, stream=None, dump=None):
        self.interval = float(interval)
        if not math.isfinite(self.interval) or self.interval <= 0:
            raise ValueError('Diagnostic interval must be finite and positive.')
        self.stream = sys.stderr if stream is None else stream
        self.dump = faulthandler.dump_traceback if dump is None else dump
        self._stop = threading.Event()
        self._thread = None
        self.dumps = 0
        self.error = ''

    def __enter__(self):
        if self._thread is not None:
            raise RuntimeError('A smoke watchdog cannot be started twice.')
        self._thread = threading.Thread(target=self._run, name='aurora-smoke-diagnostics', daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.stream.write(f'Cooperative smoke watchdog ({self.interval:g}s):\n')
                self.stream.flush()
                self.dump(file=self.stream, all_threads=True)
                self.dumps += 1
            except Exception as error:
                self.error = type(error).__name__
                self._stop.set()

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError('Smoke diagnostic thread did not stop; parent deadline remains required.')

    def snapshot(self):
        return {'mode': 'cooperative_python_thread', 'interval_seconds': self.interval,
                'dumps': self.dumps, 'error': self.error,
                'thread_stopped': self._thread is None or not self._thread.is_alive(),
                'limitation': 'Requires Python thread execution; parent process owns the hard deadline.'}

    def __exit__(self, *_exc):
        self.close()
