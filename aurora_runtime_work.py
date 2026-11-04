"""Cancellation and bounded I/O for Aurora's synchronous runtime interfaces.

Only the transport callable runs in a background thread. Callers retain ownership
of state/history and may service the control plane while waiting. Cancelling is
local: a remote provider may continue work, so late results are discarded and the
single transport slot stays occupied until its bounded network call returns.
"""
from __future__ import annotations

import copy
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


class WorkCancelled(RuntimeError):
    pass


@dataclass
class WorkToken:
    generation: int
    event: threading.Event = field(default_factory=threading.Event)
    reason: str = ""

    def check(self):
        if self.event.is_set():
            raise WorkCancelled(self.reason or "Work cancelled")

    def wait(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Duration must be finite and non-negative.")
        self.check()
        # Large finite durations remain supported without overflowing OS waits.
        while seconds > 0:
            chunk = min(seconds, 60.0)
            if self.event.wait(chunk):
                self.check()
            seconds -= chunk


class CancellationDomain:
    def __init__(self):
        self._lock = threading.RLock()
        self._token = WorkToken(0)
        self._local = threading.local()
        self._active = 0
        self._last_reason = ""

    def token(self, generation=None):
        with self._lock:
            if generation is not None and generation != self._token.generation:
                raise WorkCancelled(self._last_reason or "Queued work cancelled")
            return self._token

    def current(self):
        return getattr(self._local, "token", None) or self.token()

    def cancel(self, reason):
        with self._lock:
            old = self._token
            old.reason = self._last_reason = str(reason)
            old.event.set()
            self._token = WorkToken(old.generation + 1)
            return old.generation

    @contextmanager
    def scope(self, generation=None):
        token = self.token(generation)
        previous = getattr(self._local, "token", None)
        self._local.token = token
        with self._lock:
            self._active += 1
        try:
            token.check()
            yield token
        finally:
            self._local.token = previous
            with self._lock:
                self._active -= 1

    def snapshot(self):
        with self._lock:
            return {"generation": self._token.generation, "active_scopes": self._active,
                    "last_cancel_reason": self._last_reason}


class BoundedModelIO:
    """One network worker; cancellation never creates an unbounded worker pool."""
    def __init__(self):
        self._slot = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_token = None
        self._started = 0.0
        self._discarded = 0

    @property
    def busy(self):
        return self._slot.locked()

    def call(self, transport, packet, token, service_control=None):
        def service():
            token.check()
            if service_control:
                service_control()
            token.check()

        while not self._slot.acquire(timeout=0.02):
            service()
        done = threading.Event()
        result = {}
        try:
            token.check()
            frozen_packet = copy.deepcopy(packet)
        except BaseException:
            self._slot.release()
            raise
        with self._state_lock:
            self._active_token = token
            self._started = time.monotonic()

        def worker():
            try:
                token.check()
                result["value"] = transport(frozen_packet)
            except Exception as error:
                result["error"] = error
            finally:
                with self._state_lock:
                    if token.event.is_set():
                        result.clear()
                        self._discarded += 1
                    self._active_token = None
                done.set()
                self._slot.release()

        try:
            threading.Thread(target=worker, name="aurora-model-io", daemon=True).start()
        except BaseException:
            with self._state_lock:
                self._active_token = None
            self._slot.release()
            raise
        while not done.wait(0.02):
            service()
        token.check()
        if "error" in result:
            raise result["error"]
        return result["value"]

    def snapshot(self):
        with self._state_lock:
            token = self._active_token
            return {
                "state": "draining" if token and token.event.is_set() else "running" if token else "idle",
                "active_network_calls": int(token is not None),
                "elapsed_seconds": round(time.monotonic() - self._started, 3) if token else 0.0,
                "discarded_results": self._discarded,
                "remote_cancellation_confirmed": False,
            }
