"""Correlate an input's first model turn without changing its text or retry policy.

Receipts describe local preparation/request attempts and accepted responses, not
remote cancellation or successful tool execution. Historical re-inclusion is not
tracked here. No prompt text, credentials, or provider error bodies are logged.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import uuid


DELIVERY_SCHEMA = 1
IDENTITY_FIELDS = ("request_id", "message_id", "client_id")
TURN_PHASES = ("preparing", "prepared", "submitted", "responded", "failed", "cancelled", "not_sent")
TERMINAL_PHASES = frozenset({"responded", "failed", "cancelled", "not_sent"})
_current = ContextVar("aurora_input_delivery", default=None)


def input_identities(values):
    """Copy complete identities only; repeated text is never an identity."""
    result, seen = [], set()
    for value in values or ():
        if not isinstance(value, dict):
            continue
        identity = {key: value.get(key) for key in IDENTITY_FIELDS}
        if not all(isinstance(item, str) and item and len(item) <= 512 for item in identity.values()):
            continue
        key = tuple(identity.values())
        if key not in seen:
            seen.add(key)
            result.append(identity)
    return tuple(result)


class TrackedInput(str):
    """A legacy-compatible string carrying inbox identity through queue pickling."""
    def __new__(cls, text, identity=None):
        value = super().__new__(cls, text)
        value.delivery_refs = input_identities([identity] if identity else ())
        return value


def queued_input_identities(values):
    return input_identities(ref for value in values for ref in getattr(value, "delivery_refs", ()))


class TurnDelivery:
    def __init__(self, writer, references, *, observer=None, guard=None):
        self.writer, self.references = writer, input_identities(references)
        self.inference_request_id = "turn-" + uuid.uuid4().hex
        self.phase, self.sequence, self.model = "", 0, ""
        self.request_started = False
        self.receipt_errors = 0
        self.observer, self.observer_errors = observer, 0
        self.guard = guard

    def observe(self, phase):
        if self.observer is not None:
            try:
                self.observer(self, phase)
            except Exception:
                # Diagnostics must not lose input or trigger a retry.
                self.observer_errors += 1

    def emit(self, phase, *, reason="", model="", provider_model=""):
        if phase not in TURN_PHASES or self.phase in TERMINAL_PHASES:
            return
        if self.guard is not None:
            self.guard(self, phase)
        self.phase, self.sequence = phase, self.sequence + 1
        if model:
            self.model = str(model)
        if phase == "submitted":
            self.request_started = True
        self.observe(phase)
        for identity in self.references:
            try:
                self.writer("message_model_delivery", **identity,
                    delivery_schema=DELIVERY_SCHEMA, inference_request_id=self.inference_request_id,
                    sequence=self.sequence, phase=phase, requested_model=self.model,
                    provider_model=str(provider_model), request_started=self.request_started,
                    remote_cancellation_confirmed=False, reason=str(reason)[:500])
            except Exception:
                # Observability must not lose input, retry a request, or mask an
                # original error. The panel retains its last observed evidence.
                self.receipt_errors += 1


def current_delivery():
    return _current.get()


@contextmanager
def delivery_turn(writer, references, *, observer=None, guard=None):
    delivery = TurnDelivery(writer, references, observer=observer, guard=guard)
    token = _current.set(delivery)
    try:
        delivery.emit("preparing", reason="Selected from input queue; waiting for turn preparation.")
        yield delivery
    finally:
        try:
            delivery.emit("failed", reason="Turn ended without a confirmed response. Inspect runtime details; no automatic resend.")
        finally:
            _current.reset(token)
