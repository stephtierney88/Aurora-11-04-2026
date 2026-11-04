"""Local history command contracts, pure selection and collision-safe text export.

Provider continuation and runtime locks remain runtime-owned. Exports are readable
text with image previews, preserving the existing SAVECH format, not restorable
conversation checkpoints.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
import os
import random
import re
from decimal import Decimal
from pathlib import Path


HISTORY_RESULT_SCHEMA = "aurora_history_command_result_v1"
HISTORY_COMMANDS = {
    "INIT": "replace_init", "PIN": "pin", "CLEAR%": "clear_percentage",
    "CLEAR_NOPIN%": "clear_unprotected_percentage", "CLEAR": "clear_unprotected",
    "CLEAR_NONPIN": "clear_unprotected", "CLEAR_INIT": "clear_init", "CLEAR_PIN": "clear_pin",
    "CLEAR_HANDOFF": "clear_handoff", "EDIT_MSGS": "edit", "DELETE_MSG": "delete",
    "SAVECH": "save", "DHISTORY": "show",
}
PROTECTED_EXEMPTIONS = {"Pinned", "Init", "Handoff"}
_LEGACY_PREFIXES = (("Pinned Init summary", "Init"), ("Pinned Handoff context", "Handoff"), ("Exemption", "Pinned"))


def history_text(entry):
    content = entry.get("content", {})
    return str(content.get("text", "")) if isinstance(content, dict) else str(content or "")


def history_exemption(entry):
    explicit = entry.get("Exemption", "None")
    if explicit not in {None, "", "None"}:
        return explicit
    text = re.sub(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*", "", history_text(entry))
    return next((kind for prefix, kind in _LEGACY_PREFIXES if text.startswith(prefix)), "None")


def parse_history_arguments(name, args):
    name = name.upper()
    operation = HISTORY_COMMANDS[name]
    args = list(args)
    if any(not isinstance(arg, str) for arg in args):
        raise ValueError(f"{name} arguments must be strings.")
    if operation in {"replace_init", "pin"}:
        text = " ".join(args).strip()
        if not text:
            raise ValueError(f"{name} requires non-empty text.")
        return {"operation": operation, "text": text}
    if operation in {"clear_percentage", "clear_unprotected_percentage"}:
        maximum = 2 if operation == "clear_unprotected_percentage" else 1
        if not 1 <= len(args) <= maximum:
            raise ValueError(f"{name} requires a percentage" + (" and optional random|oldest|newest selection." if maximum == 2 else "."))
        try:
            percentage = float(args[0])
        except ValueError:
            raise ValueError(f"{name} percentage must be finite and between 0 and 100.") from None
        if not math.isfinite(percentage) or not 0 <= percentage <= 100:
            raise ValueError(f"{name} percentage must be finite and between 0 and 100.")
        selection = args[1].strip().lower() if len(args) > 1 else "random"
        if selection not in {"random", "oldest", "newest"}:
            raise ValueError("Selection must be random, oldest or newest.")
        return {"operation": operation, "percentage": percentage, "selection": selection}
    if operation == "edit":
        if not args or len(args) % 2 or any(not value.strip() for value in args[::2]):
            raise ValueError("EDIT_MSGS requires complete timestamp, text pairs; text may be empty.")
        return {"operation": operation, "edits": list(zip(args[::2], args[1::2]))}
    if operation == "delete":
        if len(args) != 1 or not args[0].strip():
            raise ValueError("DELETE_MSG requires exactly one timestamp.")
        return {"operation": operation, "timestamp": args[0]}
    if operation == "save":
        if len(args) > 1 or (args and (not args[0].strip() or "\x00" in args[0])):
            raise ValueError("SAVECH takes one optional non-empty filename prefix.")
        return {"operation": operation, "path_prefix": args[0] if args else "chat_history"}
    if args:
        raise ValueError(f"{name} takes no arguments.")
    return {"operation": operation}


def history_version(entries):
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def history_summary(entries):
    images = sum(isinstance(row.get("content"), dict) and row["content"].get("type") == "image" for row in entries)
    return {"version": history_version(entries), "count": len(entries), "image_count": images,
            "protected_count": sum(history_exemption(row) in PROTECTED_EXEMPTIONS for row in entries)}


def plan_history_change(entries, options, *, new_entry=None, sample=random.sample):
    """Plan against positions, preserving equal-valued duplicates and stable order."""
    result = copy.deepcopy(entries)
    operation = options["operation"]
    remove, edited = set(), []
    protected = [index for index, row in enumerate(entries) if history_exemption(row) in PROTECTED_EXEMPTIONS]
    protected_set = set(protected)
    other = [index for index in range(len(entries)) if index not in protected_set]
    if operation == "clear_unprotected":
        remove.update(other)
    elif operation == "clear_unprotected_percentage":
        count = int(Decimal(len(other)) * Decimal(str(options["percentage"])) / 100)
        selection = options.get("selection", "random")
        selected = sample(other, count) if selection == "random" else other[:count] if selection == "oldest" else (other[-count:] if count else [])
        remove.update(selected)
    elif operation == "clear_percentage":
        keep_count = int(Decimal(len(entries)) * (1 - Decimal(str(options["percentage"])) / 100))
        if keep_count < len(protected):
            keep = set(protected[-keep_count:] if keep_count else [])
        else:
            other_count = keep_count - len(protected)
            keep = protected_set | set(other[-other_count:] if other_count else [])
        remove = set(range(len(entries))) - keep
    elif operation in {"clear_init", "clear_pin", "clear_handoff", "replace_init"}:
        kind = {"clear_init": "Init", "replace_init": "Init", "clear_pin": "Pinned", "clear_handoff": "Handoff"}[operation]
        remove = {index for index, row in enumerate(entries) if history_exemption(row) == kind}
    elif operation == "delete":
        remove = {index for index, row in enumerate(entries) if row.get("timestamp") == options["timestamp"]}
        if not remove:
            raise ValueError("No history message has the requested timestamp.")
    elif operation == "edit":
        for timestamp, text in options["edits"]:
            index = next((i for i, row in enumerate(result) if row.get("timestamp") == timestamp), None)
            if index is None:
                raise ValueError(f"No history message has timestamp {timestamp!r}; no edits applied.")
            result[index]["content"] = {"type": "text", "text": text}
            edited.append(index)
    if operation in {"pin", "replace_init"}:
        if new_entry is None:
            raise ValueError("A prepared history entry is required.")
        result.append(copy.deepcopy(new_entry))
    return [row for i, row in enumerate(result) if i not in remove], {
        "removed_count": len(remove), "edited_count": len(set(edited)),
        "added_count": int(operation in {"pin", "replace_init"}), "selection": options.get("selection", ""),
    }


def render_history_export(entries):
    lines = []
    for entry in entries:
        content = entry.get("content", {})
        content = content if isinstance(content, dict) else {"type": "text", "text": str(content or "")}
        kind = content.get("type", "No type")
        lines.append(f"Timestamp: {entry.get('timestamp', 'No timestamp')}\nRole: {entry.get('role', 'No role')}\nType: {kind}\n")
        if kind == "text":
            lines.append(f"Message: {content.get('text', 'No text content')}\n\n")
        elif kind == "image":
            lines.append(f"Image Data: {str(content.get('data', 'No image data'))[50:80]}... [truncated]\n\n")
        else:
            lines.append(f"Other Content: {content}\n\n")
    return "".join(lines)


def save_history_export(entries, prefix, *, now=None):
    """Exclusive destination creation; never overwrite an export from the same second.

    A file can be visible while it is written. On write/flush failure only this
    call's new file is removed; incomplete cleanup is reported explicitly.
    """
    stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    body = render_history_export(entries).encode("utf-8")
    for suffix in range(1000):
        path = Path(f"{prefix}_{stamp}" + (f"_{suffix}" if suffix else "") + ".txt").resolve()
        try:
            handle = path.open("xb")
        except FileExistsError:
            continue
        try:
            with handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            if path.read_bytes() != body:
                return {"success": False, "effect_status": "uncertain", "path": str(path), "reason": "Export readback did not match; inspect the file before retrying."}
            return {"success": True, "effect_status": "observed", "path": str(path), "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(), "format": "text_with_image_previews"}
        except Exception as error:
            try:
                path.unlink()
                return {"success": False, "effect_status": "not_started", "path": str(path), "reason": str(error), "partial_file_removed": True}
            except OSError as cleanup_error:
                return {"success": False, "effect_status": "uncertain", "path": str(path), "reason": str(error), "cleanup_error": str(cleanup_error)}
    raise FileExistsError("Too many history exports with the same prefix and timestamp.")


def describe_history_contract(name):
    operation = HISTORY_COMMANDS[name.upper()]
    parameters = ([{"name": "text", "type": "string", "variadic": True, "required": True}] if operation in {"pin", "replace_init"}
                  else [{"name": "percentage", "type": "number", "minimum": 0, "maximum": 100, "required": True}]
                  + ([{"name": "selection", "type": "string", "enum": ["random", "oldest", "newest"], "default": "random", "required": False}] if operation == "clear_unprotected_percentage" else []) if "percentage" in operation
                  else [{"name": "timestamp_text_pairs", "type": "string", "variadic": True, "required": True}] if operation == "edit"
                  else [{"name": "timestamp", "type": "string", "required": True}] if operation == "delete"
                  else [{"name": "path_prefix", "type": "string", "default": "chat_history", "required": False}] if operation == "save" else [])
    return {"parameter_validation": "pre_dispatch", "parameters": parameters,
            "effects": "Local history only; preserve protected typed/legacy entries, actual retention gates, and existing command names. SAVECH exports text/image previews without overwriting earlier files.",
            "semantics": "CLEAR/CLEAR_NONPIN retain Init/Pinned/Handoff; CLEAR_NOPIN% removes a percentage of unprotected positions (random default, optional oldest/newest). CLEAR% keeps a total recency budget with protected priority and may remove protected rows. EDIT_MSGS changes first timestamp match per pair; DELETE_MSG removes all matches.",
            "result": {"protocol": HISTORY_RESULT_SCHEMA, "receipt_field": "history_command_results",
                       "failure_policy": "Validate before effects; failed controls stop the remaining raw batch. Explicit changed history cancels stale model work and invalidates any active Responses continuation. No automatic session reset/replay or remote deletion.",
                       "verification": "Before/after versions and counts prove local state; saved path/hash proves the text export. Retention and prompt-inclusion settings remain separately controlled."}}
