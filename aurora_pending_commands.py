"""Pending-command selection, ownership and receipts without runtime/native imports.

The runtime retains its planning/scoring policies. This module owns identities,
selector semantics and the reserve/submit transition used by manual and automatic
approval. A submission is not proof of an application effect.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from threading import RLock


PENDING_RESULT_SCHEMA = "aurora_pending_command_result_v1"
PENDING_WRAPPER_MODES = {"QUEUE_PENDING": "normal", "INSERT_PENDING": "insert",
                         "REPLACE_PENDING": "replace", "OVERRIDE_PENDING": "replace"}
PENDING_COMMANDS = {
    **{name: "queue" for name in PENDING_WRAPPER_MODES},
    "APPROVE_PENDING": "approve", "CLEAR_PENDING_COMMANDS": "clear", "CLEAR_PENDING": "clear",
    "SHOW_PENDING_COMMANDS": "show", "SHOW_PENDING": "show",
}
PENDING_SCOPES = {"low", "medium", "high", "memory", "desktop_action", "runtime", "persistence", "other"}
_VOLATILE_FIELDS = {"turns_until_due", "priority_score", "importance_score", "auto_policy_reason"}


def validate_pending_arguments(name, args):
    name = name.upper()
    operation = PENDING_COMMANDS[name]
    if operation == "queue":
        if len(args) != 1 or not isinstance(args[0], str) or not args[0].strip():
            raise ValueError(f"{name} requires exactly one non-empty command or quoted command batch.")
    elif operation == "show":
        if args:
            raise ValueError(f"{name} takes no arguments.")
    else:
        parse_pending_selectors(args)


def parse_pending_selectors(args):
    selectors, version = [], None
    for raw in args:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Pending selectors must be non-empty strings.")
        value = raw.strip()
        lower = value.lower()
        if lower.startswith("version:"):
            if version is not None or not re.fullmatch(r"[0-9a-f]{64}", lower[8:]):
                raise ValueError("Use one version:<64-character queue hash> guard.")
            version = lower[8:]
        elif lower.startswith("id:"):
            if not re.fullmatch(r"pending-[0-9a-f]{32}", lower[3:]):
                raise ValueError("Use id:pending-<32-character item identity> from SHOW_PENDING.")
            selectors.append(("id", lower[3:]))
        elif re.fullmatch(r"[+-]?\d+", lower):
            if len(lower) > 12 or int(lower) <= 0:
                raise ValueError(f"Pending indexes start at 1: {raw}")
            selectors.append(("index", int(lower) - 1))
        elif lower in {"all", "*"}:
            selectors.append(("all", "all"))
        else:
            selectors.append(("scope", value))
    return selectors, version


def pending_entry_available(entry):
    return entry.get("pending_state", "held") == "held"


def _public_entry(entry):
    result = copy.deepcopy({key: value for key, value in entry.items() if not key.startswith("_")})
    result["action_routes"] = [route.to_dict() for _, _, _, route in entry.get("_prepared_commands", ())
                               if route is not None]
    return result


def pending_queue_version(entries):
    stable = [{key: value for key, value in entry.items() if key not in _VOLATILE_FIELDS}
              for entry in entries]
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def pending_result(operation, before, after, *, success=True, effect_status="observed", reason="", **details):
    return {"schema_version": PENDING_RESULT_SCHEMA, "operation": operation,
            "success": bool(success), "effect_status": effect_status, "reason": str(reason),
            "before_version": pending_queue_version(before), "after_version": pending_queue_version(after),
            "before_count": len(before), "after_count": len(after), **details}


class PendingCommandLedger:
    def __init__(self):
        self.lock = RLock()

    def ensure_identities(self, store):
        """Call while locked; legacy in-memory rows gain additive identity/state."""
        seen = set()
        for entry in store:
            identity = entry.get("pending_id", "")
            if not re.fullmatch(r"pending-[0-9a-f]{32}", identity) or identity in seen:
                identity = "pending-" + uuid.uuid4().hex
                entry["pending_id"] = identity
            seen.add(identity)
            entry.setdefault("pending_state", "held")

    def snapshot(self, store):
        with self.lock:
            self.ensure_identities(store)
            return [_public_entry(entry) for entry in store]

    @contextmanager
    def mutation(self, store):
        """Restore queue state on local planning failure, retaining object identity.

        This does not undo emitted audit/feedback text. Never execute commands
        inside this context or hold this lock across a submission callback.
        """
        with self.lock:
            self.ensure_identities(store)
            originals = list(store)
            values = copy.deepcopy(originals)
            try:
                yield
                self.ensure_identities(store)
            except BaseException:
                for entry, value in zip(originals, values):
                    entry.clear()
                    entry.update(value)
                store[:] = originals
                raise

    def select(self, store, args, *, normalize, default_all=False):
        """Resolve every selector before effects; an empty match never means all."""
        with self.lock:
            rows = self.snapshot(store)
            selectors, expected = parse_pending_selectors(args)
            if expected is not None and expected != pending_queue_version(rows):
                raise ValueError("Pending queue version changed; inspect SHOW_PENDING before selecting again.")
            if not selectors:
                return list(range(len(rows))) if default_all else ([0] if rows else [])
            requested = set()
            for kind, value in selectors:
                if kind == "all":
                    matches = list(range(len(rows)))
                elif kind == "index":
                    if value >= len(rows):
                        raise ValueError(f"Pending command index out of range: {value + 1}")
                    matches = [value]
                elif kind == "id":
                    matches = [i for i, row in enumerate(rows) if row["pending_id"] == value]
                    if not matches:
                        raise ValueError(f"Pending item is absent or stale: id:{value}")
                else:
                    lower = value.lower()
                    if lower in PENDING_SCOPES:
                        field = "risk" if lower in {"low", "medium", "high"} else "category"
                        matches = [i for i, row in enumerate(rows) if str(row.get(field, "")).lower() == lower]
                    else:
                        matches = [i for i, row in enumerate(rows)
                                   if normalize(row.get("command", "")).strip().lower() == normalize(value).strip().lower()]
                        if not matches:
                            matches = [i for i, row in enumerate(rows) if lower in
                                       (str(row.get("family_key", "")).lower(), str(row.get("semantic_label", "")).lower())]
                        if not matches:
                            raise ValueError(f"Unknown or unmatched pending selector: {value}")
                requested.update(matches)
            return sorted(requested)

    def reserve(self, store, indexes, *, prepare, check, allow_task_held=False):
        """Caller holds lock; validate the whole selection before reserving any row."""
        self.ensure_identities(store)
        selected = [store[index] for index in indexes]
        for entry in selected:
            if not pending_entry_available(entry) and not (allow_task_held and entry.get("pending_state") == "task_held"):
                raise ValueError(f"{entry['pending_id']} is {entry['pending_state']}; inspect its prior submission, then clear/requeue explicitly if appropriate.")
        prepared = [prepare(entry) for entry in selected]
        check()
        for entry, commands in zip(selected, prepared):
            entry["pending_state"] = "reserved"
            entry["pending_attempt_id"] = "pending-attempt-" + uuid.uuid4().hex
            entry["_prepared_commands"] = commands
        return copy.deepcopy(selected)

    def finish(self, store, entry, outcome):
        """Acknowledge one reservation without ever automatically replaying it."""
        with self.lock:
            candidate = next((row for row in store if row.get("pending_id") == entry["pending_id"]), None)
            if candidate is None or candidate.get("pending_attempt_id") != entry["pending_attempt_id"]:
                return {**outcome, "pending_id": entry["pending_id"], "pending_attempt_id": entry["pending_attempt_id"],
                        "status": "uncertain", "reason": "Reservation identity changed before acknowledgement."}
            status = outcome.get("status", "uncertain")
            result = {**outcome, "pending_id": entry["pending_id"], "pending_attempt_id": entry["pending_attempt_id"]}
            if status in {"queued", "completed", "failed", "cancelled"}:
                store.remove(candidate)
            else:
                candidate["pending_state"] = ("task_held" if candidate.get("task_hold") else "held") if status == "not_started" else "uncertain"
                candidate["last_submission"] = copy.deepcopy(result)
                if status != "not_started":
                    candidate["manual_approval_required"] = True
            return result


def describe_pending_contract(name):
    operation = PENDING_COMMANDS[name.upper()]
    parameters = ([{"name": "command", "type": "string", "required": True}]
                  if operation == "queue" else [] if operation == "show" else
                  [{"name": "selectors", "type": "string", "variadic": True, "required": False}])
    return {"parameter_validation": "pre_dispatch", "parameters": parameters,
            "min_arguments": 1 if operation == "queue" else 0,
            "max_arguments": 1 if operation == "queue" else 0 if operation == "show" else None,
            "effects": "Preserves normal/insert/replace and manual/auto policy. Nested commands share full admission; queue selection and reserve/acknowledge use one lock. Optional cross-task holds require explicit operator approval or clearing; models and auto approval cannot release them.",
            "selectors": "Index, all/*, risk, category, exact command, family or semantic label; additive id:pending-<id> and version:<queue hash>. No matches is a no-op. Validate every selector, even after all.",
            "defaults": "APPROVE_PENDING() selects first; CLEAR_PENDING() selects all. Positional selectors use execution-time order; use IDs plus version for stale-read protection.",
            "result": {"protocol": PENDING_RESULT_SCHEMA, "receipt_field": "pending_command_results",
                       "failure_policy": "Stop the batch tail. Unstarted rows remain held; uncertain submission stays quarantined. Accepted submissions have separate correlated execution receipts; no automatic retry of a failed/uncertain execution.",
                       "verification": "Queue receipts prove local transitions/submission only. No rollback of executed effects or persistence across runtime restart."}}
