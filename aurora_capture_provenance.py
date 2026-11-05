"""Acquisition identity and demand publication; no screen, disk or provider I/O.

Wall clocks are for inspection. Monotonic times are comparable only in this
service session. A frame acknowledges a request only after its artifact has
been published, never merely because acquisition or drawing completed.
"""
from dataclasses import asdict, dataclass, replace
import math
import threading
import time
import uuid


@dataclass(frozen=True)
class FrameStamp:
    frame_id: str
    session_id: str
    sequence: int
    lifecycle: int
    source: str
    request_generation: int
    request_reason: str
    acquired_start_epoch: float
    acquired_start_monotonic: float
    acquired_end_epoch: float = 0.0
    acquired_end_monotonic: float = 0.0
    replaces_frame_id: str = ""
    request_attempt: int = 0

    def to_dict(self):
        return {"schema_version": 1, "status": "acquired", **asdict(self)}


@dataclass(frozen=True)
class CapturedFrame:
    image: object
    stamp: FrameStamp
    capture_hash: str = ""
    geometry: object = None


class CaptureService:
    """Latest request wins; stale completions cannot consume newer requests.

    Callers hold ``lock`` through publication and state mirroring. Pixel and
    file acquisition run outside it. No unbounded request/frame history is kept.
    """
    def __init__(self, *, epoch=time.time, monotonic=time.monotonic):
        self.lock = threading.RLock()
        self.epoch, self.monotonic = epoch, monotonic
        self.session_id = uuid.uuid4().hex
        self.lifecycle = self.generation = self.sequence = 0
        self.pending = None
        self.latest = {}
        self.completed_count = self.cancelled_count = self.failure_count = 0
        self.last_completion = {}
        self.last_error = ""
        self.last_cancel_reason = ""
        self.retry_at = 0.0
        self.attempt_due_at = 0.0
        self.failed_request_count = 0
        self.rejected_generation = self.blocked_generation = 0
        self.last_failure = {}
        self.acquisitions = {}

    def request(self, reason, settle=0.0, *, timeout_seconds=0.0, max_attempts=0):
        settle = float(settle)
        if not math.isfinite(settle) or settle < 0:
            raise ValueError("Capture settle must be finite and nonnegative")
        if isinstance(timeout_seconds, bool):
            raise ValueError("Capture timeout must be finite and nonnegative")
        timeout_seconds = float(timeout_seconds)
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("Capture timeout must be finite and nonnegative")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 0:
            raise ValueError("Capture attempts must be a nonnegative integer")
        with self.lock:
            self._expire()
            self.generation += 1
            now, mono = self.epoch(), self.monotonic()
            self.pending = {"generation": self.generation, "reason": str(reason),
                            "lifecycle": self.lifecycle,
                            "requested_at_epoch": now, "requested_at_monotonic": mono,
                            "due_at_epoch": now + settle, "due_at_monotonic": mono + settle,
                            "timeout_seconds": timeout_seconds, "max_attempts": max_attempts, "attempts": 0,
                            "deadline_at_epoch": now + timeout_seconds if timeout_seconds else 0.0,
                            "deadline_at_monotonic": mono + timeout_seconds if timeout_seconds else 0.0}
            self.attempt_due_at = mono + settle
            self.retry_at = 0.0
            self.blocked_generation = 0
            return self.generation

    def _fail_request(self, code):
        """Lock held. Terminal evidence is retained; pixels from it are fenced."""
        if not self.pending:
            return
        request = self.pending
        self.last_failure = {**request, "status": "failed", "code": code,
                             "detected_at_epoch": self.epoch(),
                             "elapsed_seconds": round(max(0.0, self.monotonic() - request["requested_at_monotonic"]), 3),
                             "last_error": self.last_error,
                             "native_call_cancelled": False}
        self.failed_request_count += 1
        self.rejected_generation = max(self.rejected_generation, request["generation"])
        self.blocked_generation = request["generation"]
        self.pending = None
        self.attempt_due_at = self.retry_at = 0.0

    def _expire(self):
        if not self.pending:
            return
        request, now = self.pending, self.monotonic()
        if request["timeout_seconds"] and now >= request["deadline_at_monotonic"]:
            self._fail_request("deadline_exceeded")
        elif (request["max_attempts"] and request["attempts"] >= request["max_attempts"]
              and now >= self.attempt_due_at):
            self._fail_request("attempts_exhausted")

    def demand_wait(self):
        with self.lock:
            self._expire()
            if not self.pending:
                return None
            now = self.monotonic()
            wait = max(0.0, self.pending["due_at_monotonic"] - now,
                       self.attempt_due_at - now, self.retry_at - now)
            return min(wait, max(0.0, self.pending["deadline_at_monotonic"] - now)) if self.pending["timeout_seconds"] else wait

    def retry_wait(self):
        with self.lock:
            self._expire()
            return max(0.0, self.retry_at - self.monotonic())

    def begin(self, source, *, replaces_frame_id="", allow_demand=True, require_demand=False, parent=None):
        with self.lock:
            self._expire()
            if parent is not None and (parent.session_id != self.session_id or parent.lifecycle != self.lifecycle
                                       or 0 < parent.request_generation <= self.rejected_generation):
                return None
            now, mono = self.epoch(), self.monotonic()
            request = self.pending if allow_demand and self.pending and mono >= self.pending["due_at_monotonic"] else None
            if require_demand and not request:
                return None
            replacement = bool(request and parent and parent.request_generation == request["generation"])
            if request and not replacement and request["max_attempts"] and request["attempts"] >= request["max_attempts"]:
                return None
            if request:
                # Lease bounds retries if a queued frame is dropped or drawing
                # stalls. Periodic frames may still carry the pending request.
                if not replacement:
                    request["attempts"] += 1
                    self.attempt_due_at = mono + 1.0
            self.sequence += 1
            stamp = FrameStamp(uuid.uuid4().hex, self.session_id, self.sequence, self.lifecycle,
                               str(source), request["generation"] if request else 0,
                               request["reason"] if request else "", now, mono,
                               replaces_frame_id=parent.frame_id if parent else replaces_frame_id,
                               request_attempt=parent.request_attempt if replacement else request["attempts"] if request else 0)
            self.acquisitions[stamp.frame_id] = stamp
            return stamp

    def finish(self, stamp):
        with self.lock:
            self.acquisitions.pop(stamp.frame_id, None)
            return replace(stamp, acquired_end_epoch=self.epoch(), acquired_end_monotonic=self.monotonic())

    def accepts(self, stamp):
        with self.lock:
            self._expire()
            return (isinstance(stamp, FrameStamp) and stamp.session_id == self.session_id
                    and stamp.lifecycle == self.lifecycle
                    and not 0 < stamp.request_generation <= self.rejected_generation
                    and stamp.acquired_end_monotonic >= stamp.acquired_start_monotonic
                    and stamp.acquired_end_epoch > 0
                    and stamp.sequence > self.latest.get("provenance", {}).get("sequence", 0))

    def matches_pending(self, stamp):
        with self.lock:
            return bool(self.accepts(stamp) and self.pending
                        and stamp.request_generation == self.pending["generation"]
                        and stamp.acquired_start_monotonic >= self.pending["due_at_monotonic"])

    def publish(self, stamp, *, path, timestamp, capture_hash, counter, geometry=None):
        with self.lock:
            if not self.accepts(stamp):
                return False
            matched = self.matches_pending(stamp)
            # Matching also checks expiry. A deadline crossed during that check
            # must not turn a failed request into a successfully published frame.
            if not self.accepts(stamp):
                return False
            now = self.epoch()
            self.latest = {"path": path, "timestamp": timestamp, "hash": capture_hash,
                           "counter": counter, "published_at_epoch": now, "provenance": stamp.to_dict(),
                           "geometry": geometry.to_dict() if geometry else {"status": "unknown"}}
            if matched:
                self.completed_count += 1
                self.last_completion = {"generation": self.pending["generation"], "reason": self.pending["reason"],
                                        "frame_id": stamp.frame_id, "published_at_epoch": now,
                                        "latency_ms": round(1000 * max(0.0, self.monotonic() - self.pending["requested_at_monotonic"]))}
                self.pending = None
                self.attempt_due_at = 0.0
            if matched or not self.pending:
                self.retry_at = 0.0
                self.last_error = ""
            return True

    def fail(self, stage, error, stamp=None):
        with self.lock:
            if stamp is not None:
                self.acquisitions.pop(stamp.frame_id, None)
            self._expire()
            if stamp is not None and (stamp.session_id != self.session_id or stamp.lifecycle != self.lifecycle
                                      or 0 < stamp.request_generation <= self.rejected_generation
                                      or self.pending and stamp.request_generation != self.pending["generation"]):
                return
            self.failure_count += 1
            # Bounded backoff also applies in fast heartbeat mode.
            self.retry_at = self.monotonic() + 0.5
            self.attempt_due_at = self.retry_at
            self.last_error = f"{stage}: {type(error).__name__}"  # no private paths/pixels
            if self.pending and self.pending["max_attempts"] and self.pending["attempts"] >= self.pending["max_attempts"]:
                self._fail_request("attempts_exhausted")

    def cancel(self, reason, *, invalidate_frames=True):
        with self.lock:
            self._expire()
            if invalidate_frames:
                self.lifecycle += 1
            self.cancelled_count += int(self.pending is not None)
            self.pending = None
            self.attempt_due_at = self.retry_at = 0.0
            self.blocked_generation = 0
            self.last_cancel_reason = str(reason)

    def boundary(self, settle=0.0):
        with self.lock:
            return {"session_id": self.session_id, "lifecycle": self.lifecycle,
                    "after_monotonic": self.monotonic() + float(settle)}

    def is_fresh(self, frame, boundary):
        with self.lock:
            self._expire()
            stamp = frame.get("provenance", {})
            return bool(boundary and stamp.get("status") == "acquired"
                        and not 0 < stamp.get("request_generation", 0) <= self.rejected_generation
                        and stamp.get("session_id") == boundary.get("session_id") == self.session_id
                        and stamp.get("lifecycle") == boundary.get("lifecycle") == self.lifecycle
                        and stamp.get("acquired_start_monotonic", -1) >= boundary["after_monotonic"])

    def snapshot(self):
        with self.lock:
            import copy
            self._expire()
            inflight = [{"frame_id": stamp.frame_id, "source": stamp.source,
                         "request_generation": stamp.request_generation,
                         "elapsed_seconds": round(max(0, self.monotonic() - stamp.acquired_start_monotonic), 3),
                         "status": "discard_on_return" if (stamp.lifecycle != self.lifecycle or
                                      0 < stamp.request_generation <= self.rejected_generation) else "running"}
                        for stamp in self.acquisitions.values()]
            return {"session_id": self.session_id, "lifecycle": self.lifecycle,
                    "request_generation": self.generation, "pending": dict(self.pending or {}),
                    "latest": copy.deepcopy(self.latest),
                    "completed_count": self.completed_count, "cancelled_count": self.cancelled_count,
                    "failure_count": self.failure_count, "last_error": self.last_error,
                    "failed_request_count": self.failed_request_count, "last_failure": dict(self.last_failure),
                    "current_failure": dict(self.last_failure) if self.blocked_generation else {},
                    "acquisitions_inflight": inflight,
                    "last_completion": dict(self.last_completion), "last_cancel_reason": self.last_cancel_reason}
