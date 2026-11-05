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
from collections import OrderedDict


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
    FAMILIES = ("setting_results", "lock_results", "settings_transaction_receipts", "inference_plan_results",
                "default_profile_results", "pending_command_results", "history_command_results",
                "retrieval_results", "goal_file_results", "memory_command_results")

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


class TaskContinuation:
    """One bounded task spans all model slots and scheduler wake reasons.

    Configuration is latched at task start. Only new operator input may start a
    replacement after a terminal stop; automatic wakes cannot reset the budget.
    Readback generations are acknowledged before inference, never after it.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._task = {}
        self._readback_generation = 0
        self._readback_ack = 0
        self._readback_reason = ""
        self._reset_accounting()

    def _reset_accounting(self):
        self._seen_batches, self._seen_requests = set(), set()
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
            self._accounting["command_batches"] += 1
            for name in ("executed_commands", "failed_commands", "blocked_commands", "cancelled_commands"):
                self._accounting[name] += len(receipt.get(name) or [])
            self._accounting["last_command"] = {key: receipt.get(key) for key in
                ("command_batch_id", "receipt_id", "inference_request_id", "status", "command_generation")}
            return True

    def record_request(self, task_id, request_id, *, started, phase, model="", provider_model="", usage=None,
                       frame_id="", readback_ids=()):
        with self._lock:
            if not task_id or task_id != self._task.get("task_id") or request_id in self._seen_requests:
                return False
            if len(self._seen_requests) >= 4096:
                self._accounting["capacity_exceeded"] = True
                return False
            self._seen_requests.add(request_id)
            counts = reported_token_usage(usage)
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
                reported_usage=counts, frame_id=frame_id, readback_ids=list(readback_ids))
            return True

    def _expire(self):
        if self._task.get("status") == "running" and self._clock() >= self._task["deadline"]:
            self._stop("time_limit")

    def _stop(self, reason):
        if not self._task:
            now = self._clock()
            self._task = dict(task_id="", status="stopped", stop_reason=reason, turns=0,
                              max_turns=0, max_seconds=0, started=now, deadline=now, stopped=now,
                              trigger="stopped_before_start")
        if self._task and self._task.get("status") == "running":
            self._task.update(status="stopped", stop_reason=reason, stopped=self._clock())

    def stop(self, reason):
        with self._lock:
            self._stop(reason)

    def can_dispatch(self, *, operator_input=False):
        with self._lock:
            self._expire()
            if self._task.get("status") == "running" and self._task["turns"] >= self._task["max_turns"]:
                self._stop("turn_limit")
            return not self._task or self._task.get("status") == "running" or operator_input

    def reserve(self, *, max_turns, max_seconds, operator_input=False, trigger="manual"):
        with self._lock:
            if not self.can_dispatch(operator_input=operator_input):
                return False
            if not self._task or self._task.get("status") != "running":
                now = self._clock()
                self._task = dict(task_id="task-" + uuid.uuid4().hex, status="running", stop_reason="",
                                  turns=0, max_turns=int(max_turns), max_seconds=float(max_seconds),
                                  started=now, deadline=now + float(max_seconds), trigger=trigger)
                self._reset_accounting()
            self._task["turns"] += 1
            return True

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

    def snapshot(self):
        with self._lock:
            self._expire()
            result = {key: value for key, value in self._task.items() if key not in {"started", "deadline", "stopped"}}
            result.setdefault("status", "idle")
            if self._task:
                elapsed = max(0, self._task.get("stopped", self._clock()) - self._task["started"])
                result.update(elapsed_seconds=round(elapsed, 3),
                              remaining_seconds=round(max(0, self._task["max_seconds"] - elapsed), 3))
            result["readback"] = self.readback()
            result["accounting"] = copy.deepcopy(self._accounting)
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
