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
from aurora_capture_artifacts import safe_reference


def dynamic_observation_guidance(policy):
    """Describe selected batching semantics without changing execution authority."""
    beginning = "Dynamic observation flow: after a submitted desktop/game input batch, Aurora requests a post-action screenshot automatically. "
    if policy in {"batch_end", "batch_end_explicit"}:
        timing = (f"Command-batch capture policy={policy}. Explicit capture commands in the batch share one "
                  "fresh acquisition after its terminal receipt with automatic post-action capture. "
                  "A capture command is not a visual feedback barrier inside the batch; split actions that depend on seeing a new image. ")
        if policy == "batch_end_explicit":
            timing += ("Successful capture-only batches use their explicit requested delay (zero if omitted); "
                       "input, mixed or uncertain batches retain the post-action delay. Longer pending waits are preserved. ")
        else:
            timing += "The longest explicit/default post-action delay applies, including to capture-only batches. "
        timing += "A settle delay does not verify visual stability or completion of an animation. "
    else:
        timing = ("Normally end the batch after its actions and let that observation continue the task; an additional REQUEST_SCREENSHOT_CAPTURE "
                  "in the same batch is optional and can produce an extra capture. ")
    return beginning + timing + (
        "Use explicit capture when observing without input, when the last image is insufficient/stale, or after inspecting a capture failure. "
        "Optional OBSERVE_SCREEN_CHANGE(frame_id,3,0.25) waits within one standalone command for a sampled fingerprint change "
        "from the exact latest frame (request-only capture and verified geometry/provenance required). It sends no input, "
        "takes at most 12 samples and returns changed/timeout/failure evidence; changed does not mean an animation finished. "
        "Rejected/held commands do not prove an action or fresh observation occurred. Readbacks can continue without an image; "
        "never assume the screen changed. This guidance changes no permissions, capture settings, batching rules or observation freshness checks.")


def is_capture_only_receipt(row):
    """Require complete successful receipt evidence before omitting the input delay."""
    commands = row.get("executed_commands")
    count = (row.get("capture_batch") or {}).get("requests")
    if (row.get("success") is not True or not isinstance(commands, list) or not commands
            or type(count) is not int or count != len(commands)):
        return False
    for field in ("desktop_results", "failed_commands", "blocked_commands", "cancelled_commands"):
        if not isinstance(row.get(field), list) or row[field]:
            return False
    return all(isinstance(command, str) and command.split("(", 1)[0].strip().upper()
               in {"REQUEST_SCREENSHOT_CAPTURE", "REQUEST_DEMAND_CAPTURE"} for command in commands)


def plan_batch_observation(entries, *, session_id, lifecycle, command_generation, default_settle):
    """Select terminal receipts, never pixels. A later acquisition is still required.

    Legacy receipts keep their existing path. Opted-in requests are discarded
    after cancellation/lifecycle replacement, and share the longest settle delay.
    batch_end_explicit omits the default floor only with capture-only proof.
    """
    selected, rejected, deferred = [], [], 0
    settle = 0.0
    explicit_only = default_floor = 0
    for row in entries:
        batch = row.get("capture_batch") or {}
        row_settle = float(default_settle)
        if batch.get("policy") in {"batch_end", "batch_end_explicit"}:
            if (row.get("cancelled") or batch.get("session_id") != session_id
                    or batch.get("lifecycle") != lifecycle or row.get("command_generation") != command_generation):
                rejected.append(row.get("command_batch_id", ""))
                continue
            delay = batch.get("settle_seconds", 0.0)
            if not isinstance(delay, (int, float)) or not math.isfinite(delay) or delay < 0:
                rejected.append(row.get("command_batch_id", ""))
                continue
            if batch.get("policy") == "batch_end_explicit" and is_capture_only_receipt(row):
                row_settle = 0.0
                explicit_only += 1
            else:
                default_floor += 1
            row_settle = max(row_settle, delay)
            deferred += batch.get("requests", 0)
        else:
            default_floor += 1
        settle = max(settle, row_settle)
        selected.append(row)
    return selected, dict(settle_seconds=settle if selected else float(default_settle), deferred_requests=deferred,
                          explicit_only_batches=explicit_only, default_settle_batches=default_floor,
                          selected_batches=len(selected), rejected_batch_ids=rejected,
                          boundary="receipt drain followed by fresh acquisition; no frame reuse")


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

    def publish(self, stamp, *, path, timestamp, capture_hash, counter, geometry=None, artifact=None):
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
                           "geometry": geometry.to_dict() if geometry else {"status": "unknown"},
                           "artifact": safe_reference(artifact)}
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

    def cancel_request(self, generation, reason):
        """Cancel only an owned pending request; never consume a newer request."""
        with self.lock:
            if not self.pending or self.pending['generation'] != generation:
                return False
            self.rejected_generation = max(self.rejected_generation, generation)
            self.cancelled_count += 1
            self.pending = None
            self.attempt_due_at = self.retry_at = 0.0
            self.last_cancel_reason = str(reason)
            return True

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
