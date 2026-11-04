"""Owned native inputs with frozen release callbacks and observable cleanup.

No worker threads or OS hooks are created here. A successful callback means the
backend accepted the operation, not that an application observed it. Human-held
inputs cannot be distinguished by ordinary desktop injection APIs.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class InputOwnershipError(RuntimeError):
    def __init__(self, message, effect_status="uncertain"):
        super().__init__(message)
        self.effect_status = effect_status


@dataclass
class _HeldInput:
    identity: str
    generation: int
    route: dict
    owner: dict
    release: object
    persistent: bool
    started: float = field(default_factory=time.monotonic)
    operation: object = field(default_factory=threading.Lock)
    state: str = "pressing"
    release_attempts: int = 0
    error: str = ""


class HeldInputLedger:
    """A lease survives failed release; stale lease IDs cannot release new holds."""
    def __init__(self):
        self._lock = threading.RLock()
        self._held = OrderedDict()
        self._released = OrderedDict()
        self._closed_generation = -1
        self._owner = ContextVar("aurora_input_owner", default=None)
        self._last_cleanup = None

    @contextmanager
    def owner_scope(self, metadata=None, command=None):
        owner = dict(self._owner.get() or {"batch_id": uuid.uuid4().hex})
        owner.update({key: value for key, value in (metadata or {}).items()
                      if key in {"request_id", "message_id", "client_id", "source", "is_user"}})
        if command:
            owner["command"] = command  # Never retain raw arguments or typed text.
        marker = self._owner.set(owner)
        try:
            yield
        finally:
            self._owner.reset(marker)

    @staticmethod
    def _logical(route):
        return route["namespace"], route["kind"], route["requested"]

    @staticmethod
    def _conflicts(first, second):
        if first["kind"] != second["kind"]:
            return False
        def canonical(key):
            return {"ctrlleft": "ctrl", "ctrlright": "ctrl", "shiftleft": "shift", "shiftright": "shift",
                    "altleft": "alt", "altright": "alt", " ": "space"}.get(key.lower(), key.lower())
        first_key, second_key = canonical(first["effective"]), canonical(second["effective"])
        if first_key in second.get("implicit_modifiers", []) or second_key in first.get("implicit_modifiers", []):
            return True
        if first_key == second_key:
            return True
        a, b = first.get("native"), second.get("native")
        return bool(a and b and a == b)

    @staticmethod
    def _view(record):
        return {"lease_id": record.identity, "generation": record.generation,
                "owner": dict(record.owner), "route": dict(record.route),
                "persistent": record.persistent, "state": record.state,
                "age_seconds": round(time.monotonic() - record.started, 3),
                "release_attempts": record.release_attempts, "error": record.error}

    def check_ready(self):
        """Unconfirmed modifiers/buttons can change the meaning of other input."""
        with self._lock:
            if any(record.state in {"release_uncertain", "releasing"}
                   or record.generation <= self._closed_generation for record in self._held.values()):
                raise InputOwnershipError("Owned input cleanup is unresolved; inspect SHOW_HELD_INPUTS() and release it before new input.", "not_started")

    def acquire(self, token, route, down, release, *, persistent=False, atomic=False):
        """Track before down. atomic callbacks perform their own down/up pair."""
        token.check()
        record = _HeldInput(uuid.uuid4().hex, token.generation, dict(route),
                            dict(self._owner.get() or {"batch_id": uuid.uuid4().hex}), release, persistent)
        record.operation.acquire()
        with self._lock:
            try:
                self.check_ready()
            except BaseException:
                record.operation.release()
                raise
            if token.generation <= self._closed_generation:
                record.operation.release()
                raise InputOwnershipError("Input generation was cancelled before submission.", "not_started")
            if any(self._conflicts(held.route, route) for held in self._held.values()):
                record.operation.release()
                raise InputOwnershipError("Input is already owned; release the existing hold first.", "not_started")
            if len(self._held) >= 256:
                record.operation.release()
                raise InputOwnershipError("Owned-input limit reached; inspect and release existing holds.", "not_started")
            self._held[record.identity] = record
            self._released.pop(self._logical(route), None)
        try:
            token.check()
            down()
            with self._lock:
                record.state = "held"
                if atomic:
                    self._held.pop(record.identity, None)
            token.check()
        except BaseException:
            record.operation.release()
            self.release(record.identity)
            raise
        record.operation.release()
        # A stop can arrive between the post-down check and unlocking. Check once
        # more so the acquiring worker completes any deferred cancellation cleanup.
        try:
            token.check()
        except BaseException:
            self.release(record.identity)
            raise
        return record.identity

    def release(self, identity):
        with self._lock:
            record = self._held.get(identity)
        if record is None:
            return {"lease_id": identity, "success": True, "status": "already_released"}
        if not record.operation.acquire(blocking=False):
            return {"lease_id": identity, "success": False, "status": "pending_operation",
                    "reason": "Native operation is in flight; its owner must finish cleanup."}
        try:
            with self._lock:
                if identity not in self._held:
                    return {"lease_id": identity, "success": True, "status": "already_released"}
                record.state = "releasing"
                record.release_attempts += 1
            try:
                record.release()
            except Exception as error:
                with self._lock:
                    record.state = "release_uncertain"
                    record.error = str(error)
                return dict(self._view(record), success=False, status="release_uncertain")
            with self._lock:
                self._held.pop(identity, None)
                if record.persistent:
                    logical = self._logical(record.route)
                    self._released[logical] = dict(record.route)
                    self._released.move_to_end(logical)
                    while len(self._released) > 256:
                        self._released.popitem(last=False)
            return dict(self._view(record), success=True, status="released", state="released")
        finally:
            record.operation.release()

    def release_many(self, identities):
        results = [self.release(identity) for identity in identities]
        return {"success": all(row["success"] for row in results), "results": results}

    def release_requested(self, namespace, kind, requested):
        logical = namespace, kind, requested
        with self._lock:
            records = [record for record in reversed(list(self._held.values()))
                       if self._logical(record.route) == logical]
            prior = self._released.get(logical)
        if records:
            result = self.release_many(record.identity for record in records)
            for row, record in zip(result["results"], records):
                row.setdefault("route", dict(record.route))
            return result
        if prior is not None:
            return {"success": True, "results": [{"success": True, "status": "already_released", "route": dict(prior)}]}
        return None  # Preserve explicit legacy key-up for inputs not owned here.

    def owned_route(self, namespace, kind, requested):
        """Read-only admission hint; execution still resolves the live lease ID."""
        logical = namespace, kind, requested
        with self._lock:
            for record in reversed(list(self._held.values())):
                if self._logical(record.route) == logical:
                    return dict(record.route)
            prior = self._released.get(logical)
            return dict(prior) if prior is not None else None

    def cancel_through(self, generation, reason):
        with self._lock:
            self._closed_generation = max(self._closed_generation, generation)
            ids = [record.identity for record in reversed(list(self._held.values()))
                   if record.generation <= generation]
        result = dict(self.release_many(ids), schema_version="aurora_input_cleanup_v1",
                      reason=reason, cancelled_through_generation=generation)
        with self._lock:
            self._last_cleanup = result
        return result

    def snapshot(self):
        with self._lock:
            held = [self._view(record) for record in self._held.values()]
            return {"schema_version": "aurora_held_inputs_v1", "held_count": len(held),
                    "uncertain_count": sum(row["state"] == "release_uncertain" for row in held),
                    "held": held, "last_cleanup": self._last_cleanup,
                    "verification": "backend_submission_only"}


def cooperative_move(move, position, token, x, y, duration, *, interval=0.02):
    """Interpolate using immediate native calls; never hand a long wait to the OS."""
    token.check()
    if duration <= 0:
        move(x=x, y=y, duration=0, _pause=False)
        token.check()
        return
    start_x, start_y = position()
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        fraction = min(1.0, elapsed / duration)
        token.check()
        move(x=round(start_x + (x - start_x) * fraction),
             y=round(start_y + (y - start_y) * fraction), duration=0, _pause=False)
        token.check()
        if fraction >= 1:
            return
        token.wait(min(interval, duration - elapsed))
