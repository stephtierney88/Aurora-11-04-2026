"""Recursive goal codec and bounded atomic task documents, independent of the runtime."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

GOAL_LOCK = threading.RLock()
MAX_BYTES = 8 * 1024 * 1024
MAX_GOALS = 10000
MAX_DEPTH = 32
SCHEMA = "aurora_tasks_v1"
GOAL_FILE_COMMANDS = {"SAVE_TASKS", "LOAD_TASKS"}
MEMORY_RESULT_SCHEMA = "aurora_memory_command_result_v1"
MEMORY_COMMANDS = {
    "ADD_GOAL": "goals_list", "COMPLETE_GOAL": "goals_list",
    "ADD_APRIORITY_GOAL": "apriority_tasks", "ADD_OVERARCHING_GOAL": "overarching_goals",
    "ADD_UNKNOWN_PRIORITY": "unknown_priority_candidates", "UPDATE_NOTES": "notes",
    "ADD_JOURNAL": "journal_entries", "UPDATE_PINNED_IMMEDIATE": "pinned_immediate_actions",
    "UPDATE_PINNED_SHORT_TERM": "pinned_short_term_actions", "UPDATE_MID_TERM_CONTEXT": "mid_term_context",
    "UPDATE_LONG_TERM_CONTEXT": "long_term_context", "TASKS": "unsupported",
}
HORIZON_COMMANDS = frozenset({"UPDATE_PINNED_IMMEDIATE", "UPDATE_PINNED_SHORT_TERM",
                              "UPDATE_MID_TERM_CONTEXT", "UPDATE_LONG_TERM_CONTEXT"})


def parse_memory_command_arguments(name, args, *, assistant_policy="legacy"):
    """Validate the everyday memory commands without silently dropping arguments."""
    name, args = name.upper(), list(args)
    if name not in MEMORY_COMMANDS or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
        raise ValueError("Memory command arguments must be text without NUL characters.")
    if name == "TASKS":
        if args:
            raise ValueError("TASKS accepts no arguments and is an unimplemented legacy placeholder.")
        return {}
    if name == "COMPLETE_GOAL":
        if len(args) != 1:
            raise ValueError("COMPLETE_GOAL requires exactly one positive integer goal_id from the current goal list.")
        try:
            goal_id = int(args[0])
            if goal_id < 1:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Invalid goal ID. Use the positive integer ID from the current goal list, not its text.") from None
        return {"goal_id": goal_id}
    if name == "ADD_GOAL":
        # Retain the documented single semicolon argument and comma forms.
        fields = [part.strip() for part in args[0].split(";")] if len(args) == 1 and ";" in args[0] else args
        if not 1 <= len(fields) <= 3 or not fields[0].strip():
            raise ValueError("ADD_GOAL requires non-empty goal text and optional priority, significance (at most three fields).")
        return {"text": fields[0], "priority": fields[1] if len(fields) > 1 else "No Priority",
                "significance": fields[2] if len(fields) > 2 else "No Significance"}
    if name in HORIZON_COMMANDS:
        if not args:
            raise ValueError(f"{name} requires text; use an explicit empty string to clear its list.")
        # Intentional compatibility: task_flow joins prose, legacy uses arg 1.
        return {"text": ", ".join(args) if assistant_policy == "task_flow" else args[0],
                "argument_policy": assistant_policy, "ignored_argument_count": 0 if assistant_policy == "task_flow" else len(args) - 1}
    if len(args) != 1 or (name != "UPDATE_NOTES" and not args[0].strip()):
        raise ValueError(f"{name} requires exactly one {'text' if name == 'UPDATE_NOTES' else 'non-empty text'} argument; quote commas inside it.")
    return {"text": args[0]}


def describe_memory_command_contract(name):
    name = name.upper()
    parameters = ([{"name": "goal_id", "type": "integer", "minimum": 1, "required": True}] if name == "COMPLETE_GOAL" else
                  [] if name == "TASKS" else
                  [{"name": "text", "type": "string", "required": True, "variadic": name in HORIZON_COMMANDS}])
    if name == "ADD_GOAL":
        parameters += [{"name": "priority", "type": "string", "required": False, "default": "No Priority"},
                       {"name": "significance", "type": "string", "required": False, "default": "No Significance"}]
    semantics = ("Unimplemented legacy placeholder: reports failure and stops the batch tail; does not start inference." if name == "TASKS" else
                 "Add a goal with opaque priority/significance labels; duplicates are unchanged, not relabeled. Accepts comma fields or one semicolon-delimited argument." if name == "ADD_GOAL" else
                 "Complete the exact recursive goal ID; a missing ID fails, repeated completion is unchanged." if name == "COMPLETE_GOAL" else
                 "Replace this horizon's semicolon-delimited items. task_flow joins comma prose; legacy uses the first argument and discloses ignored arguments. Explicit empty text clears it." if name in HORIZON_COMMANDS else
                 "Replace the semicolon-delimited notes list; explicit empty text clears it." if name == "UPDATE_NOTES" else
                 "Add non-empty text to the named memory list, retaining its existing deduplication/retention policy.")
    return {"parameter_validation": "pre_dispatch", "parameters": parameters,
            "min_arguments": 0 if name == "TASKS" else 1,
            "max_arguments": None if name in HORIZON_COMMANDS else 3 if name == "ADD_GOAL" else 0 if name == "TASKS" else 1,
            "argument_style": "positional", "effects": MEMORY_COMMANDS[name], "semantics": semantics,
            "result": {"protocol": MEMORY_RESULT_SCHEMA, "receipt_field": "memory_command_results",
                       "failure_policy": "Validate syntax before batch effects; runtime failures stop the tail. Applied effects are not automatically rolled back or replayed.",
                       "verification": "Scoped before/after fingerprints, bounded readback and explicit changed/unchanged/uncertain result; not a full-memory concurrency guarantee."}}


def parse_task_file_arguments(name, args):
    if name.upper() not in GOAL_FILE_COMMANDS or len(args) > 1:
        raise ValueError("SAVE_TASKS/LOAD_TASKS accept at most one file path")
    path = str(args[0]).strip() if args else "pinned_tasks.json"
    if not path or "\x00" in path:
        raise ValueError("Task file path must be nonempty and contain no NUL")
    return path


def describe_goal_file_contract(name):
    return {"parameter_validation": "pre_dispatch", "argument_style": "positional",
            "min_arguments": 0, "max_arguments": 1,
            "parameters": [{"name": "path", "type": "string", "required": False, "default": "pinned_tasks.json"}],
            "effects": "Save a validated recursive task snapshot atomically, or validate and restore a complete snapshot. Does not undo live actions.",
            "result": {"protocol": "aurora_goal_file_result_v1", "receipt_field": "goal_file_results",
                       "failure_policy": "Stop the batch tail on failure; malformed input does not mutate memory or overwrite an existing file."}}
LIST_FIELDS = {
    "apriority_goals": "apriority_tasks", "overarching_goals": "overarching_goals",
    "unknown_priority_candidates": "unknown_priority_candidates", "notable_inventory": "notable_inventory",
    "party_status": "party_status", "recent_context_events": "recent_context_events", "route_intent": "route_intent",
    "local_path_plan": "local_path_plan", "route_blockers": "route_blockers", "recent_movement_results": "recent_movement_results",
    "notes": "notes", "journal_entries": "journal_entries", "pinned_immediate_actions": "pinned_immediate_actions",
    "pinned_short_term_actions": "pinned_short_term_actions", "mid_term_context": "mid_term_context",
    "long_term_context": "long_term_context", "recent_action_intents": "recent_action_intents",
    "recent_command_proposals": "recent_command_proposals", "command_drip_history": "command_drip_history",
    "hierarchical_tasks": "hierarchical_tasks", "significant_past_goals": "significant_past_tasks",
    "recent_executed_actions": "recent_executed_actions",
}


class Goal:
    _next_id = 1

    def __init__(self, text, priority="No Priority", significance="No Significance", status="Incomplete", sub_goals=None, id=None):
        with GOAL_LOCK:
            if id is None:
                id = Goal._next_id
            if type(id) is not int or id < 1:
                raise ValueError("Goal IDs must be positive integers")
            Goal._next_id = max(Goal._next_id, id + 1)
            self.id, self.text, self.priority = id, text, priority
            self.significance, self.status = significance, status
            self.sub_goals = list(sub_goals or [])

    def add_sub_goal(self, sub_goal):
        with GOAL_LOCK:
            self.sub_goals.append(sub_goal)


def encode_goals(goals):
    seen, active = set(), set()
    def encode(goal, depth):
        if depth > MAX_DEPTH or len(seen) >= MAX_GOALS or id(goal) in active:
            raise ValueError("Goal tree exceeds limits or contains a cycle")
        if type(goal.id) is not int or goal.id < 1 or goal.id in seen:
            raise ValueError("Goal IDs must be positive and unique across the tree")
        seen.add(goal.id)
        active.add(id(goal))
        row = {name: getattr(goal, name) for name in ("id", "text", "priority", "significance", "status")}
        if any(not isinstance(row[key], str) for key in ("text", "priority", "significance", "status")):
            raise ValueError("Goal text and labels must be strings")
        row["sub_goals"] = [encode(child, depth + 1) for child in goal.sub_goals]
        active.remove(id(goal))
        return row
    return [encode(goal, 0) for goal in goals]


def validate_document(document):
    if not isinstance(document, dict):
        raise ValueError("Task document must be an object")
    if "schema_version" in document:
        if document["schema_version"] != SCHEMA:
            raise ValueError("Unsupported task schema version")
        if set(document) - {"schema_version", "state"}:
            raise ValueError("Unsupported task envelope fields")
        document = document.get("state")
    if not isinstance(document, dict) or "goals_list" not in document:
        raise ValueError("Task document requires goals_list")
    unknown = set(document) - {"goals_list", "route_state", *LIST_FIELDS}
    if unknown:
        raise ValueError("Unsupported task state fields: " + ", ".join(sorted(unknown)))
    state = copy.deepcopy(document)
    seen = set()
    def validate(rows, depth=0):
        if not isinstance(rows, list) or depth > MAX_DEPTH:
            raise ValueError("Invalid goal tree or depth")
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"id", "text", "priority", "significance", "status", "sub_goals"}:
                raise ValueError("Invalid or unknown goal fields")
            goal_id = row.get("id")
            if type(goal_id) is not int or goal_id < 1 or goal_id in seen or len(seen) >= MAX_GOALS:
                raise ValueError("Goal IDs must be positive and unique; original file was not changed")
            seen.add(goal_id)
            for field, default in (("text", None), ("priority", "No Priority"), ("significance", "No Significance"), ("status", "Incomplete")):
                row.setdefault(field, default)
                if not isinstance(row[field], str):
                    raise ValueError(f"Goal {field} must be a string")
            row.setdefault("sub_goals", [])
            validate(row["sub_goals"], depth + 1)
    validate(state["goals_list"])
    for name in LIST_FIELDS:
        state.setdefault(name, [])
        if not isinstance(state[name], list):
            raise ValueError(f"{name} must be a list")
    route = state.setdefault("route_state", {})
    if not isinstance(route, dict):
        raise ValueError("route_state must be an object")
    for name in ("current_area", "target_area", "travel_heading", "last_landmark", "status", "last_updated"):
        route.setdefault(name, "unknown" if name == "status" else "")
        if not isinstance(route[name], str):
            raise ValueError(f"route_state.{name} must be text")
    route.setdefault("stale_reasons", [])
    route.setdefault("field_meta", {})
    if not isinstance(route["stale_reasons"], list) or not isinstance(route["field_meta"], dict):
        raise ValueError("Invalid route metadata")
    # Reject nonfinite and non-JSON payloads before any caller mutates state.
    json.dumps(state, allow_nan=False)
    return state


def decode_goals(rows):
    return [Goal(**dict(row, sub_goals=decode_goals(row["sub_goals"]))) for row in rows]


def read_document(path):
    with Path(path).open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Task document exceeds size limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate task document field: " + key)
            result[key] = value
        return result
    document = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs)
    return validate_document(document), hashlib.sha256(data).hexdigest(), "versioned" if "schema_version" in document else "legacy"


def write_document(path, state, *, format="versioned", check_cancel=lambda: None):
    if format not in {"legacy", "versioned"}:
        raise ValueError("Unknown task save format")
    state = validate_document(state)
    document = state if format == "legacy" else {"schema_version": SCHEMA, "state": state}
    data = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("Task document exceeds size limit")
    path = Path(path)
    temporary = None
    with GOAL_LOCK:
        check_cancel()
        # Preserve malformed existing files for diagnosis rather than overwrite them.
        before_hash = read_document(path)[1] if path.exists() else None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".aurora-goals-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            check_cancel()
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if current_hash != before_hash:
                raise ValueError("Task destination changed during save; retry after inspection")
            os.replace(temporary, path)
            return {"before_hash": before_hash, "after_hash": hashlib.sha256(data).hexdigest(), "format": format, "bytes": len(data)}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
