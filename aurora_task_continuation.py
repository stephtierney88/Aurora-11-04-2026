"""Optional inference-task limits and lossless Init request deduplication.

No provider, GUI or input adapters live here. Limits are admission boundaries,
not a promise to cancel a remote request or undo an already executing action.
"""
from __future__ import annotations

import threading
import time
import uuid
import copy
import hashlib
import json
import os
import re
import math
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from collections import OrderedDict
from aurora_task_objective import TaskObjective, TaskObjectiveCapacity, decode_steering_text


TASK_CONTROL_RESULT_SCHEMA = "aurora_task_control_result_v1"
TASK_CONTROL_COMMANDS = {
    "SHOW_TASK_STATUS": "Inspect the controller's current bounded task, limits and declared outcome.",
    "SHOW_TASK_CONTEXT": "Operator-only: inspect the exact current task's retained operator messages and context version. Not the exact last request or full chat history.",
    "STEER_TASK": "Operator-only: append literal operator context to an exact running task using its current context version. Applies at next normal preparation; no wake, new task, budget reset or interruption of in-flight requests.",
    "CANCEL_ACTIVE_WORK_IF_TASK": "Operator-only: cancel active work only if the exact bounded task is still current. Same global work scope as Cancel work, including unscoped work; not task-isolated cancellation.",
    "REPORT_TASK_OUTCOME": "Declare done, wait, approval or error for the current opted-in task and stop automatic continuation. This is not verified success, approval, cancellation or rollback.",
}
TASK_OUTCOMES = ("done", "wait", "approval", "error")
TASK_BUDGET_RESULT_SCHEMA = "aurora_task_budget_result_v1"
TASK_TRANSITION_SCHEMA = "aurora_task_transition_v1"
TASK_ORIGIN_SCHEMA = "aurora_task_origin_v1"
USAGE_BUDGET_STOP_REASONS = {"reported_token_limit", "usage_unknown", "usage_accounting_capacity"}
_command_task = ContextVar("aurora_command_task", default=None)


@contextmanager
def command_task_scope(entry):
    """Carry controller identity through nested submissions, including workers."""
    marker = _command_task.set(copy.deepcopy({key: entry.get(key) for key in
        ("task_id", "inference_request_id", "command_batch_id", "task_budget_results")}))
    try:
        yield
    finally:
        _command_task.reset(marker)


def current_command_task():
    return copy.deepcopy(_command_task.get() or {})


def scoped_task_id(artifact):
    """Old/unattributed data is not silently assigned a destructive policy."""
    origin = (artifact or {}).get("task_origin") or {}
    if not isinstance(origin, dict):
        return ""
    identity = origin.get("task_id", "")
    return identity if (origin.get("schema") == TASK_ORIGIN_SCHEMA and origin.get("kind") in ("model", "runtime")
                        and isinstance(identity, str) and re.fullmatch(r"task-[0-9a-f]{32}", identity)) else ""


def reconcile_task_artifacts(plan, pending, task_id, plan_policy="carry", pending_policy="carry"):
    """Prepare detached replacements; caller commits under settings then queue lock.

    No submitted/uncertain work is discarded. A task-held row is explicit manual
    work; changing back to carry does not grant approval or release that hold.
    """
    if plan_policy not in {"carry", "discard_previous"} or pending_policy not in {"carry", "hold_previous", "discard_previous"}:
        raise ValueError("Unsupported task artifact policy")
    if not re.fullmatch(r"task-[0-9a-f]{32}", str(task_id)):
        raise ValueError("A current bounded task ID is required")
    updated_plan, updated_pending = copy.deepcopy(plan), copy.deepcopy(pending)
    prior_plan = scoped_task_id(plan)
    plan_action = "unscoped_preserved" if not prior_plan else "same_task" if prior_plan == task_id else "carried"
    if prior_plan and prior_plan != task_id and plan_policy == "discard_previous":
        updated_plan, plan_action = None, "discarded"
    retained, changes, counts = [], [], {}
    for entry in updated_pending:
        origin = scoped_task_id(entry)
        action = "unscoped_preserved" if not origin else "same_task" if origin == task_id else "carried"
        state = entry.get("pending_state", "held")
        if origin and origin != task_id:
            if state not in {"held", "task_held"}:
                action = "in_flight_or_uncertain_preserved"
            elif pending_policy == "discard_previous":
                action = "discarded"
            elif pending_policy == "hold_previous":
                action = "held_for_operator"
                entry.update(pending_state="task_held", manual_approval_required=True,
                             task_hold={"from_task_id": origin, "for_task_id": task_id, "policy": pending_policy})
        counts[action] = counts.get(action, 0) + 1
        if len(changes) < 64:
            changes.append(dict(pending_id=entry.get("pending_id", ""), origin_task_id=origin,
                                disposition=action, before_state=state,
                                after_state="removed" if action == "discarded" else entry.get("pending_state", "held")))
        if action != "discarded":
            retained.append(entry)
    return updated_plan, retained, dict(schema=TASK_TRANSITION_SCHEMA, success=True, task_id=task_id,
        plan_policy=plan_policy, pending_policy=pending_policy, plan_disposition=plan_action,
        before_plan_id=plan.get("plan_id", ""), after_plan_id=(updated_plan or {}).get("plan_id", ""),
        plan_origin_task_id=prior_plan, pending_before_count=len(pending), pending_after_count=len(retained),
        pending_dispositions=counts, pending_items=changes, pending_items_omitted=max(0, len(pending)-len(changes)),
        rollback_supported=False, scope="queued task-scoped artifacts only; no cancellation, approval or goal deletion")


def task_budget_summary(task):
    budget = (task or {}).get("budgets") or {}
    if not budget.get("enabled"):
        return "Command/token budgets off"
    commands = (f"Commands reserved {budget.get('admitted_commands', 0)}/{budget['max_commands']}"
                if budget.get("max_commands") else "Command limit off")
    tokens = (f"Reported tokens {budget.get('known_total_tokens', 0)}/{budget['max_reported_tokens']}"
              if budget.get("max_reported_tokens") else "Token limit off")
    return f"{commands} · {tokens} · unknown usage {budget.get('unknown_usage_requests', 0)} ({budget.get('unknown_usage_policy', 'continue')})"


def parse_task_control_arguments(name, args):
    name = name.upper()
    values = [str(value).strip() for value in args]
    # The command framer preserves wrapping quotes. Do not reinterpret escapes or
    # treat the reason as executable text.
    values = [value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
              for value in values]
    if name == "SHOW_TASK_STATUS":
        if values:
            raise ValueError("SHOW_TASK_STATUS takes no arguments.")
        return {}
    if name == "CANCEL_ACTIVE_WORK_IF_TASK":
        if len(values) != 1:
            raise ValueError("CANCEL_ACTIVE_WORK_IF_TASK(task_id) requires one exact task ID.")
        return dict(task_id=validate_task_id(values[0]))
    if name == "SHOW_TASK_CONTEXT":
        if len(values) != 1:
            raise ValueError('SHOW_TASK_CONTEXT(task_id) requires one exact task ID.')
        return dict(task_id=validate_task_id(values[0]))
    if name == "STEER_TASK":
        if len(values) != 3:
            raise ValueError('STEER_TASK(task_id, context_version, text_json_base64url) requires three arguments.')
        validate_task_id(values[0])
        if not re.fullmatch(r'ctx1:[0-9a-f]{64}', values[1]):
            raise ValueError('Use the exact context version from SHOW_TASK_CONTEXT.')
        return dict(task_id=values[0], context_version=values[1], text=decode_steering_text(values[2]))
    if name != "REPORT_TASK_OUTCOME" or len(values) != 3:
        raise ValueError("REPORT_TASK_OUTCOME(task_id, done|wait|approval|error, reason) requires three arguments; quote a reason containing commas.")
    return validate_task_outcome(*values)


def validate_task_id(task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"task-[0-9a-f]{32}", task_id):
        raise ValueError("Use the exact current task ID from SHOW_TASK_STATUS or the bounded-task prompt.")
    return task_id


def validate_task_outcome(task_id, outcome, reason):
    """Validate decoded values without stripping literal quotes from evidence."""
    validate_task_id(task_id)
    if outcome not in TASK_OUTCOMES:
        raise ValueError("Outcome must be done, wait, approval or error.")
    if not reason.strip() or len(reason) > 2000:
        raise ValueError("Outcome reason must contain 1–2000 characters.")
    return dict(task_id=task_id, outcome=outcome, reason=reason)


def task_outcome_summary(task):
    """Compact UI feedback; full evidence remains in SHOW_TASK_STATUS/receipts."""
    report = (task or {}).get("reported_outcome") or {}
    if not report:
        return ""
    reason = " ".join(str(report.get("reason", "")).split())
    if len(reason) > 160:
        reason = reason[:157] + "..."
    return f"Reported {report.get('outcome', 'unknown')} by {report.get('actor', 'unknown')} (unverified): {reason}"


def describe_task_control_contract(name):
    if name.upper() in {"SHOW_TASK_CONTEXT", "STEER_TASK"}:
        steer = name.upper() == "STEER_TASK"
        parameters = [dict(name='task_id', type='string', required=True, pattern=r'^task-[0-9a-f]{32}$')]
        if steer:
            parameters += [dict(name='context_version', type='string', required=True, pattern=r'^ctx1:[0-9a-f]{64}$'),
                           dict(name='text_json_base64url', type='string', required=True, max_length=270000)]
        return dict(parameter_validation='pre_dispatch', min_arguments=len(parameters), max_arguments=len(parameters),
            parameters=parameters, effects=TASK_CONTROL_COMMANDS[name.upper()], actor='operator_only', mode='bounded',
            batch_policy='Standalone controller command only; no pending wrappers or mixed batches.',
            result=dict(protocol=TASK_CONTROL_RESULT_SCHEMA, receipt_field='task_control_results',
                failure_policy='Reject stale task/version, stopped/expired task, model actor, disabled retention or capacity overflow without partial append. Never automatically retry.',
                verification='Context readback is current retained text, not provider delivery. Steering requires execution unlocked and active latched operator objective mode; creates no inference wake. Full text is explicit operator readback only.'))
    if name.upper() == "CANCEL_ACTIVE_WORK_IF_TASK":
        return dict(parameter_validation="pre_dispatch", min_arguments=1, max_arguments=1,
            parameters=[dict(name="task_id", type="string", required=True, pattern=r"^task-[0-9a-f]{32}$")],
            effects=TASK_CONTROL_COMMANDS[name.upper()], actor="operator_only", mode="bounded",
            batch_policy="Standalone controller command only; no pending wrappers or mixed batches.",
            result=dict(protocol=TASK_CONTROL_RESULT_SCHEMA, receipt_field="task_control_results",
                failure_policy="Stale IDs, legacy mode and model actors have no cancellation effects. Already stopped is idempotent. Partial cleanup is uncertain; inspect owned inputs before explicit release.",
                verification="Local cancellation only; remote cancellation and rollback are unconfirmed. Captured generation cleanup cannot release newer holds. Live mode, settings, plans and goals are preserved."))
    report = name.upper() == "REPORT_TASK_OUTCOME"
    return dict(parameter_validation="pre_dispatch", min_arguments=3 if report else 0,
                max_arguments=3 if report else 0, parameters=[
                    dict(name="task_id", type="string", required=True, pattern=r"^task-[0-9a-f]{32}$"),
                    dict(name="outcome", type="string", required=True, enum=list(TASK_OUTCOMES)),
                    dict(name="reason", type="string", required=True, min_length=1, max_length=2000),
                ] if report else [], effects=TASK_CONTROL_COMMANDS[name.upper()],
                batch_policy="Standalone controller command only; no pending wrappers or mixed batches.",
                result=dict(protocol=TASK_CONTROL_RESULT_SCHEMA, receipt_field="task_control_results",
                            failure_policy="Reject stale/disabled/stopped/conflicting reports without changing the task; identical reports are idempotent.",
                            verification="Declared outcome, not independent success verification. Already admitted work can finish. Plans and goals are preserved."))


def reported_token_usage(usage):
    """Normalize reported counts only. Missing/invalid fields remain unknown."""
    usage = usage if isinstance(usage, dict) else {}
    result = {}
    for key, alias in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
                       ("total_tokens", "total_tokens")):
        value = usage.get(key, usage.get(alias))
        result[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return result


class CommandReadbacks:
    """Bounded, process-local copies of sanitized reviewed receipts.

    Selection is task-scoped and request-specific. Submitted/uncertain records
    are never automatically replayed; this store cannot execute commands.
    """
    from aurora_execution_evidence import RECEIPT_FAMILIES as FAMILIES

    def __init__(self, *, max_records=64, record_chars=6000, request_chars=24000):
        if max_records < 1 or record_chars < 1 or request_chars < record_chars + 2048:
            raise ValueError("Readback capacity must fit at least one bounded record and its metadata")
        self._lock = threading.RLock()
        self._records = OrderedDict()
        self.max_records, self.record_chars, self.request_chars = max_records, record_chars, request_chars
        self.evicted_pending = 0

    def publish(self, receipt):
        """Receipt must already be sanitized by the shared runtime log writer."""
        if not isinstance(receipt, dict):
            return False
        key = receipt.get("command_batch_id")
        task_id = receipt.get("task_id")
        families = {name: receipt[name] for name in self.FAMILIES if receipt.get(name)}
        if not key or not task_id or not receipt.get("inference_request_id") or receipt.get("is_user") or not families:
            return False
        payload = json.dumps(families, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        row = {"record_id": "readback-" + key, "command_batch_id": key, "receipt_id": receipt.get("receipt_id", ""),
               "task_id": task_id, "origin_inference_request_id": receipt["inference_request_id"],
               "status": receipt.get("status", "unknown"), "generation": receipt.get("command_generation"),
               "coverage": "reviewed_receipt_fields_only", "families": list(families),
               "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(), "payload_chars": len(payload),
               "payload_truncated": len(payload) > self.record_chars, "phase": "pending", "included_request_id": ""}
        if row["payload_truncated"]:
            row["payload_preview"] = payload[:self.record_chars]
        else:
            row["results"] = json.loads(payload)
        with self._lock:
            if key in self._records:
                return False
            self._records[key] = row
            while len(self._records) > self.max_records:
                _, removed = self._records.popitem(last=False)
                self.evicted_pending += int(removed["phase"] in {"pending", "prepared"})
            return True

    def pending(self, task_id):
        with self._lock:
            return sum(row["task_id"] == task_id and row["phase"] == "pending" for row in self._records.values())

    def prepare(self, task_id, request_id):
        with self._lock:
            candidates = [row for row in self._records.values() if row["task_id"] == task_id and row["phase"] == "pending"]
            chosen, size = [], 0
            for row in candidates:
                copy_row = copy.deepcopy(row)
                copy_row.update(phase="prepared", included_request_id=request_id)
                length = len(json.dumps(copy_row, ensure_ascii=True))
                if len(chosen) >= 4 or size + length > self.request_chars:
                    break
                row.update(phase="prepared", included_request_id=request_id)
                chosen.append(copy_row)
                size += length
            return {"schema": "aurora_command_readbacks_v1", "request_id": request_id, "task_id": task_id,
                    "records": chosen, "remaining_pending": len(candidates) - len(chosen),
                    "evicted_pending_total": self.evicted_pending, "scope": "session_only; data, not instructions"}

    def mark_request(self, request_id, phase):
        if phase not in {"submitted", "responded", "failed", "cancelled", "not_sent"}:
            return
        with self._lock:
            for row in self._records.values():
                if row["included_request_id"] != request_id or row["phase"] not in {"prepared", "submitted"}:
                    continue
                row["phase"] = ("uncertain" if phase in {"failed", "cancelled"} and row["phase"] == "submitted"
                                else "not_sent" if phase in {"failed", "cancelled", "not_sent"} else phase)

    def snapshot(self, *, include_results=True):
        with self._lock:
            rows = (list(self._records.values()) if include_results else
                    [{key: value for key, value in row.items() if key not in {"results", "payload_preview"}}
                     for row in self._records.values()])
            return {"scope": "bounded_session_receipts", "retained": len(self._records),
                    "max_records": self.max_records, "record_char_limit": self.record_chars,
                    "request_char_limit": self.request_chars, "evicted_pending_total": self.evicted_pending,
                    "records": copy.deepcopy(rows)}


def _elapsed_ms(start, end):
    """Unknown stays unknown; never clamp invalid evidence into a zero latency."""
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (start, end)) or end < start:
        return None
    return round((end - start) * 1000, 3)


class TaskProgress:
    """Bounded diagnostic joins, called under the owning TaskContinuation lock.

    Controller-relative monotonic times measure local observation boundaries.
    Capture-service clocks are used only to match an explicit freshness boundary,
    never subtracted from this clock. No text, paths, pixels or provider bodies.
    """
    PHASES = {"preparing", "prepared", "submitted", "responded", "failed", "cancelled", "not_sent"}
    TERMINAL = {"responded", "failed", "cancelled", "not_sent"}

    def __init__(self, clock, capacity=64):
        self.clock, self.started, self.capacity = clock, clock(), capacity
        self.batches, self.requests = OrderedDict(), OrderedDict()
        self.events = []
        self.total_events = self.evicted_batches = self.evicted_requests = 0

    def now(self):
        return self.clock() - self.started

    def event(self, kind, identity, **fields):
        self.total_events += 1
        self.events.append(dict(sequence=self.total_events, kind=kind, identity=str(identity)[:160],
                                observed_at_seconds=self.now(), **fields))
        self.events = self.events[-self.capacity:]

    def row(self, book, identity):
        if identity not in book:
            book[identity] = {}
            if len(book) > self.capacity:
                book.popitem(last=False)
                if book is self.batches:
                    self.evicted_batches += 1
                else:
                    self.evicted_requests += 1
        return book[identity]

    def admission(self, entry):
        identity = entry.get("command_batch_id")
        if not identity:
            return False
        row = self.row(self.batches, identity)
        if "admitted_at" in row:
            return False
        row.update(command_batch_id=identity, origin_request_id=entry.get("inference_request_id", ""),
                   admitted_at=self.now(), status="admitted", binding_count=len(entry.get("prepared_commands") or []))
        # Keep reviewed binding names, never command arguments or input text.
        names = [item[1] for item in (entry.get("prepared_commands") or [])
                 if isinstance(item, (tuple, list)) and len(item) >= 2
                 and isinstance(item[1], str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", item[1])]
        row.update(binding_names=names[:64], binding_names_omitted=max(0, row["binding_count"] - min(64, len(names))))
        self.event("command_admitted", identity)
        return True

    def receipt(self, receipt):
        from aurora_execution_evidence import receipt_summary
        identity = receipt.get("command_batch_id")
        row = self.row(self.batches, identity)
        if "receipt_at" in row:
            return False
        row.update(command_batch_id=identity, receipt_id=receipt.get("receipt_id", ""),
                   origin_request_id=receipt.get("inference_request_id", ""), receipt_at=self.now(),
                   status=str(receipt.get("status", "unknown"))[:80],
                   executed_count=len(receipt.get("executed_commands") or []),
                   failed_count=len(receipt.get("failed_commands") or []),
                   blocked_count=len(receipt.get("blocked_commands") or []),
                   cancelled_count=len(receipt.get("cancelled_commands") or []))
        row['receipt_evidence'] = receipt_summary(receipt)
        self.event("command_receipt", identity, status=row["status"])
        return True

    def await_frame(self, entry, boundary, observation_generation, request_generation):
        identity = entry.get("command_batch_id")
        if not identity or not boundary:
            return False
        row = self.row(self.batches, identity)
        if row.get("observation_generation", -1) >= observation_generation:
            return False
        # A later post-action boundary must not inherit an earlier capture from
        # the same batch (e.g. capture command followed by another desktop action).
        for key in ("frame_id", "frame_observed_at", "capture_request_generation", "frame_prepared_at", "frame_request_id"):
            row.pop(key, None)
        row.update(command_batch_id=identity, observation_generation=observation_generation,
                   required_request_generation=request_generation, observation_requested_at=self.now(),
                   boundary={key: boundary.get(key) for key in ("session_id", "lifecycle", "after_monotonic")})
        self.event("observation_requested", identity, observation_generation=observation_generation,
                   capture_request_generation=request_generation)
        return True

    def frame(self, frame):
        stamp = (frame or {}).get("provenance") or {}
        if stamp.get("status") != "acquired" or not stamp.get("frame_id") or not stamp.get("session_id"):
            return False
        matched = False
        for identity, row in self.batches.items():
            boundary = row.get("boundary") or {}
            if row.get("frame_id") or stamp.get("session_id") != boundary.get("session_id") or stamp.get("lifecycle") != boundary.get("lifecycle"):
                continue
            if _elapsed_ms(boundary.get("after_monotonic"), stamp.get("acquired_start_monotonic")) is None:
                continue
            generation = stamp.get("request_generation")
            required = row.get("required_request_generation", 0)
            if not isinstance(generation, int) or isinstance(generation, bool) or generation < required:
                continue
            row.update(frame_id=stamp["frame_id"], frame_observed_at=self.now(), capture_request_generation=generation)
            self.event("frame_observed", identity, frame_id=stamp["frame_id"], capture_request_generation=generation,
                       observation_generation=row["observation_generation"])
            matched = True
        return matched

    def request_phase(self, delivery, phase):
        if phase not in self.PHASES:
            return False
        identity = delivery.inference_request_id
        row = self.row(self.requests, identity)
        times = row.setdefault("phase_times", {})
        if phase in times or row.get("phase") in self.TERMINAL:
            return False
        order = {"preparing": 0, "prepared": 1, "submitted": 2}
        if phase in order and order.get(row.get("phase"), -1) >= order[phase]:
            return False
        times[phase] = self.now()
        row.update(inference_request_id=identity, phase=phase, model=str(delivery.model)[:160])
        if hasattr(delivery, 'transport_evidence'):
            from aurora_execution_evidence import transport_snapshot
            row['transport_evidence'] = transport_snapshot(delivery.transport_evidence)
        if phase == "prepared":
            row["frame_id"] = getattr(delivery, "frame_id", "")
            row["prepared_settings"] = self.safe_fields(getattr(delivery, "prepared_settings", {}),
                ("reasoning_effort", "service_tier", "configured_transport", "configured_auth", "review_turn", "critique_turn"))
            row["frame_provenance"] = self.safe_fields(getattr(delivery, "frame_provenance", {}),
                ("status", "frame_id", "session_id", "sequence", "lifecycle", "request_generation",
                 "acquired_start_epoch", "acquired_end_epoch", "acquired_start_monotonic", "acquired_end_monotonic"))
            from aurora_capture_artifacts import safe_reference
            row["frame_artifact"] = safe_reference(getattr(delivery, "frame_artifact", {}))
            manifest = getattr(delivery, "command_readbacks", {}) or {}
            included = {item.get("command_batch_id") for item in manifest.get("records", [])}
            readback_links, frame_links = [], []
            for batch_id, batch in self.batches.items():
                if batch_id in included:
                    readback_links.append(batch_id)
                    batch.setdefault("readback_prepared_at", times[phase])
                    batch.setdefault("readback_request_id", identity)
                if row["frame_id"] and batch.get("frame_id") == row["frame_id"]:
                    frame_links.append(batch_id)
                    batch.setdefault("frame_prepared_at", times[phase])
                    batch.setdefault("frame_request_id", identity)
            row.update(readback_batch_ids=readback_links, frame_batch_ids=frame_links)
        self.event("model_" + phase, identity, frame_id=row.get("frame_id", ""))
        return True

    @staticmethod
    def safe_fields(value, keys):
        """Small typed metadata only; prompts, paths and credential fields stay out."""
        value = value if isinstance(value, dict) else {}
        return {key: item[:160] if isinstance(item, str) else item
                for key in keys if key in value
                for item in (value[key],)
                if item is None or isinstance(item, (str, bool, int))
                or (isinstance(item, float) and math.isfinite(item))}

    def request_result(self, request_id, *, started, phase, provider_model, counts):
        # Do not recreate evicted request records or invent missing phase times.
        row = self.requests.get(request_id)
        if row is not None:
            row.update(request_started=bool(started), result_phase=phase,
                       provider_model=str(provider_model or "")[:160], reported_usage=copy.deepcopy(counts))

    @staticmethod
    def batch_view(row):
        result = copy.deepcopy({key: value for key, value in row.items() if key != "boundary"})
        result["latency_ms"] = {name: _elapsed_ms(row.get(start), row.get(end)) for name, start, end in (
            ("admission_to_receipt", "admitted_at", "receipt_at"),
            ("observation_wait", "observation_requested_at", "frame_observed_at"),
            ("receipt_to_frame_observed", "receipt_at", "frame_observed_at"),
            ("receipt_to_readback_prepared", "receipt_at", "readback_prepared_at"),
            ("frame_observed_to_request_prepared", "frame_observed_at", "frame_prepared_at"))}
        return result

    @staticmethod
    def request_view(row):
        result, times = copy.deepcopy(row), row.get("phase_times", {})
        terminal = times.get(row.get("phase")) if row.get("phase") in TaskProgress.TERMINAL else None
        result["latency_ms"] = dict(preparation=_elapsed_ms(times.get("preparing"), times.get("prepared")),
            prepared_to_submitted=_elapsed_ms(times.get("prepared"), times.get("submitted")),
            submitted_to_response=_elapsed_ms(times.get("submitted"), times.get("responded")),
            submitted_to_terminal=_elapsed_ms(times.get("submitted"), terminal))
        return result

    def snapshot(self, include_records=False):
        result = dict(schema="aurora_task_progress_v1", scope="controller_observations_only; not verified task completion",
            clock="task_relative_monotonic", capacity_per_collection=self.capacity, events_total=self.total_events,
            events_evicted=max(0, self.total_events - len(self.events)), batches_evicted=self.evicted_batches,
            requests_evicted=self.evicted_requests, retained_batches=len(self.batches), retained_requests=len(self.requests),
            latest_event=copy.deepcopy(self.events[-1]) if self.events else {},
            latest_command=self.batch_view(next(reversed(self.batches.values()))) if self.batches else {},
            latest_request=self.request_view(next(reversed(self.requests.values()))) if self.requests else {})
        if include_records:
            result.update(events=copy.deepcopy(self.events), commands=[self.batch_view(r) for r in self.batches.values()],
                          requests=[self.request_view(r) for r in self.requests.values()])
        else:
            # Detailed inspection is operator-only data, not extra per-turn prompt overhead.
            result['latest_command'].pop('binding_names', None)
            result['latest_command'].pop('receipt_evidence', None)
            for key in ('prepared_settings', 'frame_provenance', 'frame_artifact', 'transport_evidence'):
                result['latest_request'].pop(key, None)
        return result


class TaskContinuation:
    """One bounded task spans all model slots and scheduler wake reasons.

    Configuration is latched at task start. Only new operator input may start a
    replacement after a terminal stop; automatic wakes cannot reset the budget.
    Readback generations are acknowledged before inference, never after it.
    """

    def __init__(self, clock=time.monotonic, *, recording_capacity=0):
        self._clock = clock
        self.controller_pid = os.getpid()
        self._lock = threading.RLock()
        self._task = {}
        self._objective = TaskObjective()
        self._readback_generation = 0
        self._readback_ack = 0
        self._readback_reason = ""
        if type(recording_capacity) is not int or not 0 <= recording_capacity <= 16:
            raise ValueError('Recording capacity must be 0..16; zero preserves legacy behavior.')
        self._recording = None
        if recording_capacity:
            from aurora_execution_recording import BoundaryBuffer
            self._recording = BoundaryBuffer(recording_capacity)
        self._reset_accounting()

    def _record_boundary(self, kind, identity=None):
        if self._recording is not None and self._task.get('task_id'):
            self._recording.offer(kind, lambda: self._snapshot_locked(include_progress=True),
                                  identity=self._task['task_id'] if identity is None else identity)

    def recording_status(self):
        with self._lock:
            return self._recording.status() if self._recording else dict(enabled=False, durable=False, state='off')

    def start_recording(self, capacity=16):
        """Attach a new epoch without changing task state; never discard queued data."""
        with self._lock:
            if self._recording and (not self._recording.closed or self._recording.records):
                raise ValueError('Previous recording must be closed and drained.')
            from aurora_execution_recording import BoundaryBuffer
            self._recording = BoundaryBuffer(capacity)
            return self._recording.status()

    def peek_recording(self, limit=8):
        with self._lock:
            return self._recording.peek(limit) if self._recording else dict(status=self.recording_status(), records=[])

    def acknowledge_recording(self, session_id, sequences):
        with self._lock:
            return self._recording.acknowledge(session_id, sequences) if self._recording else dict(status='off', acknowledged=[])

    def close_recording(self):
        with self._lock:
            return self._recording.close() if self._recording else self.recording_status()

    def _reset_accounting(self):
        self._artifact_transition = {}
        self._progress = TaskProgress(self._clock)
        self._seen_batches, self._seen_requests = set(), set()
        self._admitted_batches = set()
        self._admitted_commands = 0
        self._last_admission = {}
        self._accounting = {"coverage": "observed_receipts_only", "capacity_exceeded": False,
                            "command_batches": 0, "executed_commands": 0, "failed_commands": 0,
                            "blocked_commands": 0, "cancelled_commands": 0, "requests_started": 0,
                            "responses_received": 0, "request_failures": 0,
                            "usage": {key: {"known_total": 0, "known_requests": 0, "unknown_requests": 0}
                                      for key in ("input_tokens", "output_tokens", "total_tokens")},
                            "last_command": {}, "last_request": {}}

    def record_command(self, receipt):
        if not isinstance(receipt, dict):
            return False
        with self._lock:
            key = receipt.get("command_batch_id")
            if not key or not receipt.get("task_id") or receipt["task_id"] != self._task.get("task_id") or key in self._seen_batches:
                return False
            if len(self._seen_batches) >= 4096:
                self._accounting["capacity_exceeded"] = True
                return False
            self._seen_batches.add(key)
            self._progress.receipt(receipt)
            self._accounting["command_batches"] += 1
            for name in ("executed_commands", "failed_commands", "blocked_commands", "cancelled_commands"):
                self._accounting[name] += len(receipt.get(name) or [])
            self._accounting["last_command"] = {key: receipt.get(key) for key in
                ("command_batch_id", "receipt_id", "inference_request_id", "status", "command_generation")}
            self._record_boundary('command_receipt', key)
            return True

    def record_request(self, task_id, request_id, *, started, phase, model="", provider_model="", usage=None,
                       frame_id="", readback_ids=(), progress_errors=0):
        with self._lock:
            if not task_id or task_id != self._task.get("task_id") or request_id in self._seen_requests:
                return False
            if len(self._seen_requests) >= 4096:
                self._accounting["capacity_exceeded"] = True
                if self._task.get("max_reported_tokens"):
                    self._stop("usage_accounting_capacity")
                return False
            self._seen_requests.add(request_id)
            counts = reported_token_usage(usage)
            self._progress.request_result(request_id, started=started, phase=phase,
                                          provider_model=provider_model, counts=counts)
            if started:
                self._accounting["requests_started"] += 1
                self._accounting["responses_received" if phase == "responded" else "request_failures"] += 1
                for name, value in counts.items():
                    counter = self._accounting["usage"][name]
                    counter["known_requests" if value is not None else "unknown_requests"] += 1
                    if value is not None:
                        counter["known_total"] += value
            self._accounting["last_request"] = dict(inference_request_id=request_id, phase=phase,
                request_started=bool(started), requested_model=model, provider_model=provider_model,
                reported_usage=counts, frame_id=frame_id, readback_ids=list(readback_ids), progress_errors=progress_errors)
            self._record_boundary('request_finalized', request_id)
            self._expire()
            limit = self._task.get("max_reported_tokens", 0)
            if limit:
                total = self._accounting["usage"]["total_tokens"]
                if total["known_total"] >= limit:
                    self._stop("reported_token_limit")
                elif total["unknown_requests"] and self._task.get("unknown_usage_policy") == "stop":
                    self._stop("usage_unknown")
            return True

    def record_command_admission(self, entry):
        with self._lock:
            return bool(entry.get("task_id") and entry["task_id"] == self._task.get("task_id")
                        and self._progress.admission(entry))

    def record_observation_wait(self, entries, boundary, observation_generation, request_generation):
        with self._lock:
            for entry in entries:
                if entry.get("task_id") and entry["task_id"] == self._task.get("task_id"):
                    self._progress.await_frame(entry, boundary, observation_generation, request_generation)

    def record_frame_observed(self, frame):
        with self._lock:
            changed = self._progress.frame(frame)
            if changed:
                self._record_boundary('frame_observed', frame['provenance']['frame_id'])
            return changed

    def record_request_progress(self, delivery, phase):
        with self._lock:
            changed = bool(getattr(delivery, "task_id", "") and delivery.task_id == self._task.get("task_id")
                           and self._progress.request_phase(delivery, phase))
            if changed and phase == 'prepared':
                self._record_boundary('request_prepared', delivery.inference_request_id)
            return changed

    def budget_snapshot(self):
        with self._lock:
            maximum = self._task.get("max_commands", 0)
            tokens = self._task.get("max_reported_tokens", 0)
            usage = self._accounting["usage"]["total_tokens"]
            return dict(enabled=bool(maximum or tokens), max_commands=maximum, max_reported_tokens=tokens,
                admitted_commands=self._admitted_commands, admitted_batches=len(self._admitted_batches),
                remaining_commands=max(0, maximum - self._admitted_commands) if maximum else None,
                known_total_tokens=usage["known_total"], known_usage_requests=usage["known_requests"],
                unknown_usage_requests=usage["unknown_requests"],
                unknown_usage_policy=self._task.get("unknown_usage_policy", "continue"),
                controller_pid=self.controller_pid,
                command_unit="expanded bindings reserved at automatic admission; one binding may perform multiple inputs; no refund",
                token_scope="reported total tokens at response boundaries, not a hard token/spend cap",
                last_admission=copy.deepcopy(self._last_admission))

    def admit_commands(self, task_id, batch_id, count):
        """Reserve the entire batch atomically. Never partially admit or refund it."""
        if not isinstance(count, int) or isinstance(count, bool) or count < 1 or not batch_id:
            raise ValueError("Command admission requires a batch ID and a positive binding count.")
        with self._lock:
            self._expire()
            before = self.budget_snapshot()
            reason, code = "", "admitted"
            if task_id != self._task.get("task_id"):
                reason, code = "Task identity changed; no commands reserved for the newer task.", "stale_task"
            elif self._task.get("status") != "running":
                reason, code = "Bounded task stopped; automatic work was not admitted.", "task_stopped"
            elif batch_id in self._admitted_batches:
                reason, code = "Batch already reserved; do not submit it again.", "duplicate_batch"
            elif before["max_commands"] and count > before["remaining_commands"]:
                self._stop("command_limit")
                reason, code = "Whole batch exceeds remaining command budget; no prefix was admitted.", "command_limit"
            elif before["max_commands"] and len(self._admitted_batches) >= 4096:
                self._stop("command_budget_capacity")
                reason, code = "Command admission identity capacity reached; no untracked reservation allowed.", "command_budget_capacity"
            elif before["max_commands"]:
                self._admitted_batches.add(batch_id)
                self._admitted_commands += count
            self._last_admission = dict(batch_id=batch_id, requested_commands=count, code=code, allowed=not reason)
            return dict(schema_version=TASK_BUDGET_RESULT_SCHEMA, success=not reason, allowed=not reason,
                effect_status="reserved" if not reason else "not_started", code=code, reason=reason,
                task_id=task_id, command_batch_id=batch_id, controller_pid=self.controller_pid,
                before=before, after=self.budget_snapshot())

    def _expire(self):
        if self._task.get("status") == "running" and self._clock() >= self._task["deadline"]:
            self._stop("time_limit")

    def _stop(self, reason):
        self._objective.clear()
        if not self._task:
            now = self._clock()
            self._task = dict(task_id="", status="stopped", stop_reason=reason, turns=0,
                              max_turns=0, max_seconds=0, started=now, deadline=now, stopped=now,
                              trigger="stopped_before_start")
        if self._task and self._task.get("status") == "running":
            self._task.update(status="stopped", stop_reason=reason, stopped=self._clock())
            self._record_boundary('task_stopped')

    def stop(self, reason):
        with self._lock:
            self._stop(reason)

    def stop_if_current(self, task_id, reason, *, on_stop=None):
        """Compare and stop atomically; rejection never expires an unrelated task.

        on_stop(effects) is trusted short controller bookkeeping under this lock,
        never native I/O. It may retain partial effects before raising. Callers
        must acquire any outer service locks first and release inputs afterward.
        """
        validate_task_id(task_id)
        with self._lock:
            before = self._snapshot_locked()
            result = dict(task_id=task_id, success=False, changed=False,
                          effect_status="not_started", before=before, effects={})
            if self._task.get("task_id") != task_id:
                result.update(code="stale_task", reason="Expected task is no longer current.")
            elif self._task.get("status") != "running":
                result.update(success=True, code="already_stopped", effect_status="unchanged",
                              reason="Task already stopped; no cancellation generations changed.")
            else:
                self._stop(reason)
                result.update(success=True, changed=True, code="stopped", effect_status="applied", reason="")
                if on_stop is not None:
                    try:
                        on_stop(result["effects"])
                    except Exception:
                        result.update(success=False, code="cancellation_uncertain", effect_status="failed_uncertain",
                                      reason="Task stopped; cancellation bookkeeping partly failed. Inspect current work before retrying.")
            result["after"] = self._snapshot_locked()
            return copy.deepcopy(result)

    def can_dispatch(self, *, operator_input=False):
        with self._lock:
            self._expire()
            if self._task.get("status") == "running" and self._task["turns"] >= self._task["max_turns"]:
                self._stop("turn_limit")
            if (self._task.get("status") == "running" and self._task.get("max_commands")
                    and self._admitted_commands >= self._task["max_commands"]):
                self._stop("command_limit")
            return not self._task or self._task.get("status") == "running" or operator_input

    def reserve(self, *, max_turns, max_seconds, operator_input=False, trigger="manual", outcome_reporting=False,
                max_commands=0, max_reported_tokens=0, unknown_usage_policy="continue",
                plan_carry_policy="carry", pending_carry_policy="carry", objective_mode="legacy", operator_messages=()):
        with self._lock:
            if not self.can_dispatch(operator_input=operator_input):
                return False
            new_task = not self._task or self._task.get('status') != 'running'
            if not self._task or self._task.get("status") != "running":
                if objective_mode not in {"legacy", "operator"}:
                    raise ValueError("Unknown task objective mode")
                self._objective.clear()
                now = self._clock()
                self._task = dict(task_id="task-" + uuid.uuid4().hex, status="running", stop_reason="",
                                  turns=0, max_turns=int(max_turns), max_seconds=float(max_seconds),
                                  outcome_reporting=bool(outcome_reporting),
                                  max_commands=int(max_commands), max_reported_tokens=int(max_reported_tokens),
                                  unknown_usage_policy=unknown_usage_policy,
                                  plan_carry_policy=plan_carry_policy, pending_carry_policy=pending_carry_policy,
                                  objective_mode=objective_mode,
                                  started=now, deadline=now + float(max_seconds), trigger=trigger)
                self._reset_accounting()
            if self._task.get("objective_mode") == "operator" and operator_input and operator_messages:
                try:
                    self._objective.append(operator_messages)
                except TaskObjectiveCapacity:
                    self._stop("objective_capacity")
                    raise
            self._task["turns"] += 1
            self._record_boundary('task_started' if new_task else 'turn_reserved')
            return True

    def objective_projection(self, task_id):
        return self.prepare_objective(task_id)['messages']

    def _context_metadata_locked(self):
        summary = self._objective.snapshot()
        identity = dict(task_id=self._task.get('task_id', ''), objective_mode=self._task.get('objective_mode', 'legacy'),
                        digest=summary['digest'], messages=summary['messages'])
        version = 'ctx1:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode('utf-8')).hexdigest()
        return dict(summary, task_id=identity['task_id'], objective_mode=identity['objective_mode'], context_version=version,
                    status=self._task.get('status', 'idle'),
                    expired=bool(self._task.get('status') == 'running' and self._clock() >= self._task['deadline']))

    def inspect_context(self, task_id):
        """Explicit readback; stale inspection neither expires nor reveals another task."""
        validate_task_id(task_id)
        with self._lock:
            if self._task.get('task_id') != task_id:
                return dict(success=False, code='stale_task', effect_status='not_started', task_id=task_id,
                            reason='Expected task is no longer current.')
            return dict(success=True, code='observed', effect_status='observed', task_id=task_id,
                        context=self._context_metadata_locked(),
                        messages=self._objective.records(),
                        scope='Current retained operator context only; not full chat, historical context or provider delivery.')

    def steer(self, task_id, context_version, text):
        """Atomic compare-and-append; no queue insertion, wake, budget change or replay."""
        validate_task_id(task_id)
        if not isinstance(context_version, str) or not re.fullmatch(r'ctx1:[0-9a-f]{64}', context_version):
            raise ValueError('Use the exact context version from SHOW_TASK_CONTEXT.')
        if not isinstance(text, str) or not text.strip() or len(text) > TaskObjective.MAX_CHARACTERS:
            raise ValueError('Steering requires nonempty text of at most 32768 characters.')
        text.encode('utf-8')
        with self._lock:
            result = dict(success=False, changed=False, effect_status='not_started', task_id=task_id,
                          provider_delivery_confirmed=False, wake_requested=False,
                          scope='Next normal request preparation only; no inference wake, task restart, budget reset or in-flight interruption.')
            if self._task.get('task_id') != task_id:
                return dict(result, code='stale_task', reason='Expected task is no longer current.')
            before = self._context_metadata_locked()
            result.update(before=before)
            if before['status'] != 'running' or before['expired']:
                result.update(code='task_stopped', reason='Task is stopped or expired; steering cannot restart it.')
            elif before['objective_mode'] != 'operator':
                result.update(code='retention_disabled', reason='This task did not start with operator context retention enabled.')
            elif context_version != before['context_version']:
                result.update(code='context_conflict', reason='Context version changed. Inspect the current context before deciding on another edit; no automatic retry.')
            else:
                try:
                    self._objective.append([text], source='operator_steering')
                except TaskObjectiveCapacity:
                    result.update(code='context_capacity', reason='Retained context is full (32 messages / 32768 characters); no text appended and the current task was preserved.')
                else:
                    result.update(success=True, changed=True, code='applied', effect_status='applied', reason='')
            result['after'] = self._context_metadata_locked()
            return result

    def prepare_objective(self, task_id):
        """Freeze text and metadata together; future steering cannot rewrite this view."""
        with self._lock:
            self._expire()
            if self._task.get("task_id") != task_id or self._task.get("status") != "running":
                return dict(messages=[], metadata={})
            return dict(messages=self._objective.projection(task_id), metadata=self._context_metadata_locked())

    def record_artifact_transition(self, receipt):
        with self._lock:
            if receipt.get("task_id") != self._task.get("task_id"):
                return False
            self._artifact_transition = copy.deepcopy(receipt)
            return True

    def report_outcome(self, task_id, outcome, reason, *, actor, origin_request_id=""):
        """Commit one immutable declaration. Neither approval nor success is inferred."""
        values = validate_task_outcome(task_id, outcome, reason)
        with self._lock:
            self._expire()
            before = self.snapshot()
            existing = self._task.get("reported_outcome") or {}
            error = ""
            changed = False
            if values["task_id"] != self._task.get("task_id"):
                error = "Task ID is stale or no bounded task has started."
            elif not self._task.get("outcome_reporting"):
                error = "Outcome reporting was not enabled when this task started."
            elif existing:
                if any(existing.get(key) != value for key, value in dict(values, actor=actor).items()):
                    error = "The task already has an immutable outcome; conflicting reports are rejected."
            elif self._task.get("status") != "running":
                error = "The task is already stopped; a report cannot replace cancellation, failure or a limit."
            else:
                self._task["reported_outcome"] = dict(values, actor=str(actor),
                    origin_inference_request_id=str(origin_request_id),
                    reported_at=datetime.now(timezone.utc).isoformat(), verification="reported_not_verified")
                self._stop("reported_" + outcome)
                changed = True
            return dict(schema_version=TASK_CONTROL_RESULT_SCHEMA, command="REPORT_TASK_OUTCOME",
                        success=not error, effect_status="not_started" if error else "applied" if changed else "unchanged",
                        reason=error, before=before, after=self.snapshot(),
                        scope="Automatic continuation stops; admitted work, pending proposals, goals and one-turn plans are not cancelled or cleared.")

    def check_deadline(self):
        """Do not discard the final allowed turn merely because its slot is used."""
        with self._lock:
            self._expire()
            return not self._task or self._task.get("status") == "running"

    def publish_readback(self, reason):
        with self._lock:
            self._readback_generation += 1
            self._readback_reason = str(reason)[:160]
            return self._readback_generation

    def readback(self):
        with self._lock:
            return dict(generation=self._readback_generation, acknowledged=self._readback_ack,
                        pending=self._readback_generation > self._readback_ack, reason=self._readback_reason)

    def acknowledge_readback(self, generation):
        with self._lock:
            self._readback_ack = max(self._readback_ack, min(int(generation), self._readback_generation))

    def snapshot(self, *, include_progress=False):
        with self._lock:
            self._expire()
            return self._snapshot_locked(include_progress=include_progress)

    def _snapshot_locked(self, *, include_progress=False):
        """Observation only under owner lock; boundary recording must not expire a task."""
        result = copy.deepcopy({key: value for key, value in self._task.items() if key not in {"started", "deadline", "stopped"}})
        result.setdefault("status", "idle")
        if self._task:
            elapsed = max(0, self._task.get("stopped", self._clock()) - self._task["started"])
            result.update(elapsed_seconds=round(elapsed, 3),
                          remaining_seconds=round(max(0, self._task["max_seconds"] - elapsed), 3))
        result["objective"] = self._objective.snapshot()
        result["readback"] = self.readback()
        result["accounting"] = copy.deepcopy(self._accounting)
        result["budgets"] = self.budget_snapshot()
        result["progress"] = self._progress.snapshot(include_records=include_progress)
        result["artifact_transition"] = copy.deepcopy(self._artifact_transition)
        if not include_progress:
            result["artifact_transition"].pop("pending_items", None)
        result["limits_scope"] = "model-turn admission; late responses cannot launch commands"
        return result


def prepare_init_delivery(history, init_text, system_text, *, mode="legacy", current_prompt="", exemption=""):
    """Remove only exact Init copies already present in full in the system text.

    History is never mutated. A truncated/edited/quoted Init is retained. The
    initialization trigger survives as a short current message, not a third copy.
    """
    init = str(init_text or "").strip()
    effective = mode == "system_once" and bool(init) and "Persistent init context:\n" + init in system_text
    removed = []
    retained = []
    for row in history:
        content = row.get("content") or {}
        text = str(content.get("text", "")).strip()
        # Runtime history prefixes its own recorded timestamp. Strip no arbitrary
        # bracketed prose: it must match this row's timestamp and the complete Init.
        timestamp = str(row.get("timestamp") or "")
        exact = text == init or (bool(timestamp) and text == f"[{timestamp}] {init}")
        duplicate = (effective and row.get("Exemption") == "Init" and content.get("type") == "text"
                     and exact)
        (removed if duplicate else retained).append(row)
    duplicate_current = effective and exemption == "Init" and str(current_prompt).strip() == init
    request_prompt = ("Initialization context is loaded in the system message. Acknowledge readiness and follow the operator's task."
                      if duplicate_current else current_prompt)
    return retained, request_prompt, {
        "mode": mode, "eligible": effective, "removed_history_copies": len(removed),
        "removed_history_chars": sum(len(row["content"]["text"]) for row in removed),
        "shortened_initialization_trigger": duplicate_current,
        "history_preserved": True,
    }
