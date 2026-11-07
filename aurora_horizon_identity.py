"""Explicit horizon/goal links; string lists remain the compatibility authority.

Callers serialize access with GOAL_LOCK. Bulk list changes invalidate that list's
links rather than guessing identity from text or position. Loading retains IDs,
but creates a new edit epoch so a pre-load command cannot silently apply.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid

HORIZON_FIELDS = {
    "immediate": "pinned_immediate_actions", "short": "pinned_short_term_actions",
    "medium": "mid_term_context", "long": "long_term_context",
}
IDENTITY_COMMANDS = frozenset({"SHOW_HORIZON_ENTRIES", "LINK_HORIZON_GOAL"})
IDENTITY_SCHEMA = "aurora_horizon_identity_v1"


def valid_uid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def parse_identity_arguments(name, args):
    name, args = name.upper(), list(args)
    if any(not isinstance(value, str) or "\x00" in value for value in args):
        raise ValueError("Identity arguments must be text without NUL.")
    if name == "SHOW_HORIZON_ENTRIES":
        if len(args) > 3:
            raise ValueError("Use SHOW_HORIZON_ENTRIES([all|goals|immediate|short|medium|long[, offset, limit]]).")
        view = args[0].lower() if args else "all"
        offset, limit = int(args[1]) if len(args) > 1 else 0, int(args[2]) if len(args) > 2 else 50
        if view not in {"all", "goals", *HORIZON_FIELDS} or offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Unknown view or page bounds; offset >= 0, limit 1..200.")
        return {"view": view, "offset": offset, "limit": limit}
    if name == "LINK_HORIZON_GOAL":
        if len(args) != 3 or not valid_uid(args[0]) or re.fullmatch(r"[0-9a-f]{64}", args[1]) is None:
            raise ValueError("Use LINK_HORIZON_GOAL(entry_id, entry_version, goal_uid|none) from fresh SHOW_HORIZON_ENTRIES readbacks.")
        target = None if args[2].lower() == "none" else args[2]
        if target is not None and not valid_uid(target):
            raise ValueError("Use the stable goal_uid from SHOW_HORIZON_ENTRIES(goals), not a numeric goal ID.")
        return {"entry_id": args[0], "expected_version": args[1], "goal_uid": target}
    raise ValueError("Unknown identity command.")


def describe_identity_contract(name):
    read = name.upper() == "SHOW_HORIZON_ENTRIES"
    return {"parameter_validation": "pre_dispatch", "argument_style": "positional",
            "min_arguments": 0 if read else 3, "max_arguments": 3,
            "parameters": ([{"name": "view", "type": "string", "required": False, "default": "all"},
                            {"name": "offset", "type": "integer", "required": False, "default": 0},
                            {"name": "limit", "type": "integer", "required": False, "default": 50}] if read else
                           [{"name": key, "type": "string", "required": True} for key in ("entry_id", "entry_version", "goal_uid_or_none")]),
            "effects": "Inspect memory identity" if read else "Link or unlink an existing horizon entry; never execute or complete a goal",
            "semantics": ("Inspect bounded entries or goals with stable IDs. Lazily creates metadata; does not change list text. Views: all, goals, immediate, short, medium, long; limit 1..200." if read else
                          "Use fresh entry/version and goal_uid readbacks. Reject stale tokens/missing targets. Bulk list replacement invalidates affected links; versioned saves retain links, legacy saves omit them."),
            "result": {"protocol": "aurora_memory_command_result_v1", "receipt_field": "memory_command_results",
                       "failure_policy": "Syntax validated before batch effects; stale identity fails without mutation and stops the tail. No automatic retry."}}


class HorizonIdentityLedger:
    def __init__(self, stores, saved=None):
        self.epoch = uuid.uuid4().hex
        self.rows = {field: [] for field in HORIZON_FIELDS.values()}
        if saved is not None:
            self.rows = self.validate_saved(saved, stores)
        self.sync(stores)

    @staticmethod
    def validate_saved(saved, stores):
        if not isinstance(saved, dict) or set(saved) != {"schema_version", "rows"} or saved["schema_version"] != IDENTITY_SCHEMA:
            raise ValueError("Invalid horizon identity metadata.")
        rows = saved["rows"]
        if not isinstance(rows, dict) or set(rows) != set(HORIZON_FIELDS.values()):
            raise ValueError("Horizon identity fields do not match stores.")
        seen = set()
        for field, entries in rows.items():
            if not isinstance(entries, list) or len(entries) != len(stores[field]):
                raise ValueError("Horizon identity list length mismatch.")
            for entry, text in zip(entries, stores[field]):
                if not isinstance(entry, dict) or set(entry) != {"entry_id", "text", "revision", "goal_uid"}:
                    raise ValueError("Invalid horizon identity entry fields.")
                if not valid_uid(entry["entry_id"]) or entry["entry_id"] in seen:
                    raise ValueError("Horizon entry IDs must be unique.")
                seen.add(entry["entry_id"])
                if entry["text"] != text or type(entry["revision"]) is not int or entry["revision"] < 1:
                    raise ValueError("Horizon entry text/revision mismatch.")
                if entry["goal_uid"] is not None and not valid_uid(entry["goal_uid"]):
                    raise ValueError("Invalid linked goal UID.")
        return copy.deepcopy(rows)

    def sync(self, stores):
        invalidated = []
        for field in HORIZON_FIELDS.values():
            values = stores[field]
            if [row["text"] for row in self.rows[field]] != values:
                invalidated.append(field)
                self.rows[field] = [{"entry_id": uuid.uuid4().hex, "text": copy.deepcopy(text),
                                     "revision": 1, "goal_uid": None} for text in values]
        return invalidated

    def export(self):
        return {"schema_version": IDENTITY_SCHEMA, "rows": copy.deepcopy(self.rows)}

    def version(self, row):
        return hashlib.sha256(json.dumps([self.epoch, row], sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def inspect(self, goals, view="all", offset=0, limit=50):
        by_uid = {goal["uid"]: goal for goal in goals}
        if view == "goals":
            rows = [dict(goal, goal_uid=goal["uid"]) for goal in goals]
        else:
            rows = []
            for horizon, field in HORIZON_FIELDS.items():
                if view not in {"all", horizon}:
                    continue
                for row in self.rows[field]:
                    target = by_uid.get(row["goal_uid"])
                    rows.append(dict(copy.deepcopy(row), horizon=horizon, version=self.version(row),
                                     link_state="unlinked" if row["goal_uid"] is None else "resolved" if target else "missing",
                                     goal=copy.deepcopy(target)))
        return {"view": view, "total": len(rows), "offset": offset, "limit": limit,
                "omitted_before": min(offset, len(rows)), "omitted_after": max(0, len(rows)-offset-limit),
                "entries": rows[offset:offset+limit]}

    def link(self, entry_id, expected_version, goal_uid, goals):
        row = next((row for entries in self.rows.values() for row in entries if row["entry_id"] == entry_id), None)
        if row is None or self.version(row) != expected_version:
            raise ValueError("Horizon entry changed or was reloaded; inspect again before linking.")
        if goal_uid is not None and not any(goal["uid"] == goal_uid for goal in goals):
            raise ValueError("Linked goal no longer exists; inspect goals again.")
        before = dict(copy.deepcopy(row), version=self.version(row))
        changed = row["goal_uid"] != goal_uid
        if changed:
            row["goal_uid"] = goal_uid
            row["revision"] += 1
        return {"changed": changed, "before": before, "after": dict(copy.deepcopy(row), version=self.version(row))}

    def project(self, field, goals):
        horizon = next(key for key, value in HORIZON_FIELDS.items() if value == field)
        rows = self.inspect(goals, horizon, limit=len(self.rows[field]))["entries"]
        result = []
        for row in rows:
            target = row["goal"]
            label = ("unlinked" if row["link_state"] == "unlinked" else "linked goal missing; review retained plan" if target is None else
                     f"goal ID {target['id']}: {target['status']}; declared status, not outcome verification")
            result.append(f"{row['text']} [entry {row['entry_id']}; {label}]")
        return result
