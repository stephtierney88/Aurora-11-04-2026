"""Detached, bounded conversation views. Never reads the historical chat log."""
from __future__ import annotations

import hashlib
import json
import copy
import math
import os
import re
import threading
import uuid
from aurora_history_controls import message_revision
from collections import OrderedDict

MAX_VIEW_CHARS = 256_000
MAX_MESSAGE_CHARS = 32_000
MAX_VIEW_ROWS = 2_000


def ensure_message_ids(entries):
    """Call under the history lock before copying/mutating runtime history."""
    for entry in entries:
        if isinstance(entry, dict) and not entry.get("message_id"):
            entry["message_id"] = uuid.uuid4().hex


def message_key(entry):
    if entry.get("message_id"):
        return str(entry["message_id"])
    # Read-only compatibility identity for older exports; collisions are disclosed.
    content = entry.get("content", {})
    text = content.get("text", "") if isinstance(content, dict) else str(content or "")
    return "legacy:" + hashlib.sha256(json.dumps([entry.get("timestamp"), entry.get("role"), text], sort_keys=True).encode()).hexdigest()[:24]


def build_conversation_view(entries, *, source, max_chars=MAX_VIEW_CHARS,
                            max_message_chars=MAX_MESSAGE_CHARS, max_rows=MAX_VIEW_ROWS):
    """Export newest retained rows without image bytes or silent truncation."""
    entries = [entry for entry in entries if isinstance(entry, dict)]
    rows, used, clipped = [], 0, 0
    for entry in reversed(entries[-max_rows:]):
        content = entry.get("content", {})
        kind = content.get("type", "text") if isinstance(content, dict) else "text"
        if kind == "image":
            text = "[Screenshot in current context — open Screenshots to inspect]"
        elif isinstance(content, dict):
            text = str(content.get("text", ""))
        else:
            text = str(content or "")
        available = min(max_message_chars, max_chars - used)
        if available <= 0:
            break
        shortened = len(text) > available
        if shortened:
            text = text[:available] + "\n[Message shortened in this view]"
            clipped += 1
        used += len(text)
        rows.append({"role": str(entry.get("role", "unknown")), "text": text,
                     "message_id": message_key(entry), "revision": message_revision(entry), "exemption": str(entry.get("Exemption", "")),
                     "pinned": entry.get("Exemption") in {"Pinned", "PinnedInfo", "Init", "Handoff"},
                     "token_count": entry.get("token_count") if isinstance(entry.get("token_count"), (int, float)) and math.isfinite(entry["token_count"]) else None,
                     "original_chars": len(str(content.get("text", ""))) if isinstance(content, dict) and kind != "image" else len(text),
                     "timestamp": str(entry.get("timestamp", "")), "kind": kind,
                     "timestamp_iso": str(entry.get("timestamp_iso", "")),
                     "model": str(entry.get("model", "")), "model_source": str(entry.get("model_source", "unknown")),
                     "edited_by": str(entry.get("edited_by", "")), "edited_at": str(entry.get("edited_at", "")),
                     "created_by": str(entry.get("created_by", "")),
                     "shortened": shortened})
    rows.reverse()
    result = {"source": source, "rows": rows, "total": len(entries),
              "omitted": len(entries) - len(rows), "shortened": clipped}
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def build_conversation_snapshot(history_read_state, current_entries=None, *, archive=None, decay=None, models=None):
    """Current means eligible history now, not the exact last provider payload."""
    current = (history_read_state.get("recent_prompt_history", [])
               if current_entries is None else current_entries)
    result = {"schema_version": "aurora_conversation_v1",
            "current": build_conversation_view(current, source="current_context_window"),
            "retained": build_conversation_view(history_read_state.get("history_store", []),
                                                source="retained_runtime_history"),
            "decay": dict(decay or {}), "models": dict(models or {})}
    current_ids = {message_key(row) for row in current if isinstance(row, dict)}
    for view in (result["current"], result["retained"]):
        for row in view["rows"]:
            row["in_current"] = row["message_id"] in current_ids
            row["retained"] = True
    if archive is not None:
        result["archive"] = archive.snapshot(current_ids)
    return result


def conversation_text(view, *, show_time=True, show_model=True, show_edits=True, show_metadata=False, decay=None):
    blocks = []
    for row in view.get("rows", []):
        details = []
        if show_model:
            model = row.get("model") or row.get("created_by") or ("model unknown" if row.get("role") == "assistant" else row.get("role", "unknown"))
            if row.get("model_source") == "requested":
                model += " (requested)"
            details.append("sent from " + model)
        if show_time:
            details.append(row.get("timestamp_iso") or row.get("timestamp") or "time unknown")
        if show_edits and row.get("edited_by"):
            details.append("last edited by " + row["edited_by"] + (" · " + row["edited_at"] if show_time and row.get("edited_at") else ""))
        if show_metadata:
            details.extend(message_metadata(row, decay or {}))
        text = row["text"]
        legacy_prefix = "[" + str(row.get("timestamp", "")) + "] "
        if row.get("timestamp") and text.startswith(legacy_prefix):
            text = text[len(legacy_prefix):]
        blocks.append(f"{row['role'].title()}  {' · '.join(details)}\n{text}")
    return "\n\n".join(blocks)


def message_metadata(row, decay):
    from aurora_history_controls import history_entry_age_seconds
    details = []
    if row.get("pinned"):
        details.append("Pinned" + (" / " + row["exemption"] if row.get("exemption") != "Pinned" else ""))
    elif row.get("exemption") and row["exemption"].lower() != "none":
        details.append(row["exemption"])
    important = row.get("exemption") in {"Pinned", "Init", "Special", "Handoff"}
    prefix = "important" if important else "ordinary"
    if row.get("kind") == "image":
        details.append("decay: image retention policy")
    elif prefix + "_enabled" not in decay:
        details.append("decay: unknown")
    elif not decay[prefix + "_enabled"]:
        details.append("decay: off")
    else:
        details.append(f"decay: {decay.get(prefix + '_minutes', '?')} min age threshold")
        if row.get("retained") is False or row.get("historical_revision"):
            details.append("archived view; no active expiry timer")
        else:
            age = history_entry_age_seconds(row, decay.get("observed_at"))
            if age is None:
                details.append("age unknown; invalid/missing timestamp is retained")
            else:
                details.append(f"age at snapshot {age / 60:.1f} min" if decay.get("observed_at") else f"estimated age {age / 60:.1f} min")
                try:
                    remaining = float(decay[prefix + "_minutes"]) - age / 60
                    if remaining < 0:
                        details.append("past threshold; checked on next history append")
                    else:
                        details.append(f"{remaining:.1f} min to threshold")
                except (ValueError, TypeError, KeyError):
                    pass
    if row.get("retained") is False:
        details.append(row.get("removal_reason") or "no longer retained")
    elif row.get("in_current") is False:
        details.append("outside current context selection")
    if row.get("event"):
        details.append(row["event"])
    if row.get("moved"):
        details.append("position changed since first observation")
    if row.get("historical_revision"):
        details.append("historical text revision")
    return details


class ConversationArchive:
    """Bounded, in-memory observation archive. Never a provider transcript or image store."""
    def __init__(self, *, enabled=True, max_chars=512_000, max_rows=2000):
        self.enabled, self.max_chars, self.max_rows = enabled, max_chars, max_rows
        self.records, self.events = OrderedDict(), []
        self.lock = threading.RLock()
        self.sequence = self.evicted = 0
        self.last_order = []

    def _event(self, row, event):
        self.sequence += 1
        self.events.append(dict(copy.deepcopy(row), event=event, sequence=self.sequence,
                                message_id=f"event:{self.sequence}", target_id=row["message_id"]))

    def observe(self, entries, *, reason="no longer retained"):
        if not self.enabled:
            return
        view = build_conversation_view(entries, source="session_observation", max_chars=self.max_chars, max_rows=self.max_rows)
        with self.lock:
            live = {message_key(entry) for entry in entries if isinstance(entry, dict)}
            order = [row["message_id"] for row in view["rows"]]
            common = set(order).intersection(self.last_order)
            previous = [key for key in self.last_order if key in common]
            current = [key for key in order if key in common]
            moved = {a for a, b in zip(current, previous) if a != b}
            for position, row in enumerate(view["rows"]):
                key = row["message_id"]
                record = self.records.get(key)
                if record is None:
                    self._event(row, "first observed")
                    record = {"original": copy.deepcopy(row), "sequence": self.sequence, "original_position": position, "moved": False}
                    self.records[key] = record
                elif record["latest"] != row or key in moved:
                    self._event(row, "changed" if record["latest"] != row else "position changed")
                record.update(latest=row, retained=True, removal_reason="", position=position)
                record["moved"] = record["moved"] or key in moved
            for key, record in self.records.items():
                if key not in live and record.get("retained"):
                    record.update(retained=False, removal_reason=reason)
                    self._event(record["latest"], reason)
            self.last_order = order
            self._bound()

    def record_event(self, record):
        if not self.enabled or record.get("event") == "history_append":
            return
        # Already sanitized by runtime; allow only text summaries and lifecycle facts.
        fields = {key: record[key] for key in ("event", "timestamp", "executed_commands", "narrative_summary", "content_summary", "command", "success", "reason") if key in record}
        if len(fields) <= 2:
            return
        row = {"message_id": "runtime-event", "role": "command" if fields.get("executed_commands") or fields.get("command") else "system",
               "timestamp": str(record.get("timestamp", "")), "text": json.dumps(fields, ensure_ascii=False)[:8000], "kind": "event"}
        with self.lock:
            self._event(row, "runtime summary")
            self._bound()

    def record_prepared(self, material):
        """Keep bounded system/memory/current text evidence, explicitly before transport."""
        if not self.enabled:
            return
        parts = []
        for name, section in material.get("sections", {}).items():
            text = str(section.get("text", ""))
            parts.append(name.title() + ":\n" + text + ("\n[Prepared section clipped]" if section.get("truncated") else ""))
        row = {"message_id": "prepared-text", "role": "system", "kind": "preparation",
               "timestamp": str(material.get("prepared_at", "")), "model": str(material.get("model", "")),
               "model_source": "requested", "text": "[Prepared text; delivery is not established. Images/history/session transformations are separate.]\n" + "\n\n".join(parts)}
        if len(row["text"]) > MAX_MESSAGE_CHARS:
            row["text"] = row["text"][:MAX_MESSAGE_CHARS] + "\n[Prepared text shortened in archive]"
        with self.lock:
            self._event(row, "request preparation")
            self._bound()

    def _bound(self):
        def size(record):
            return len(record["original"]["text"]) + len(record["latest"]["text"])
        total = sum(size(record) for record in self.records.values())
        while self.records and (len(self.records) > self.max_rows or total > self.max_chars):
            _, record = self.records.popitem(last=False)
            total -= size(record)
            self.evicted += 1
        total = sum(len(row["text"]) for row in self.events)
        while self.events and (len(self.events) > self.max_rows or total > self.max_chars):
            total -= len(self.events.pop(0)["text"])
            self.evicted += 1

    def snapshot(self, current_ids):
        with self.lock:
            latest, original = [], []
            for key, record in self.records.items():
                metadata = {"retained": record["retained"], "removal_reason": record["removal_reason"],
                            "in_current": key in current_ids, "sequence": record["sequence"],
                            "position": record["position"], "moved": record["moved"]}
                latest.append(dict(record["latest"], **metadata))
                original_metadata = dict(metadata, historical_revision=record["original"] != record["latest"])
                original_metadata["in_current"] = metadata["in_current"] and not original_metadata["historical_revision"]
                original.append(dict(record["original"], **original_metadata))
            latest.sort(key=lambda row: (row["position"], row["sequence"]))
            events = []
            for event in self.events:
                record = self.records.get(event.get("target_id"))
                current = event.get("target_id") in current_ids and event.get("text") == record["latest"]["text"] if record else None
                events.append(dict(event, in_current=current))
            return copy.deepcopy({"enabled": self.enabled, "latest": latest, "original": original,
                                  "events": events, "evicted": self.evicted,
                                  "coverage": "This runtime session, from first observation; bounded text only. Earlier deleted text and intermediate unobserved changes are unavailable. Runtime events may be summaries. Not an exact provider transcript."})


CONVERSATION_ARCHIVE = ConversationArchive(enabled=os.getenv("AURORA_CONVERSATION_ARCHIVE", "on").lower() not in {"off", "0", "false"})


VIEW_MODES = ("Current context", "Retained messages", "SHOW_ALL", "SHOW_ALL_IN_ORDER", "SHOW_ALL_FULL_TRANSCRIPT")


def select_conversation_rows(snapshot, mode, *, include_system=False, include_commands=False):
    archive = snapshot.get("archive", {})
    if mode in VIEW_MODES[2:]:
        key = {"SHOW_ALL": "latest", "SHOW_ALL_IN_ORDER": "original", "SHOW_ALL_FULL_TRANSCRIPT": "events"}[mode]
        rows = copy.deepcopy(archive.get(key, []))
        note = archive.get("coverage", "Session archive unavailable; old deleted text cannot be reconstructed.")
        note += f" Evicted archive records/events: {archive.get('evicted', 0)}."
    else:
        view = snapshot.get("retained" if mode == "Retained messages" else "current", {})
        rows = copy.deepcopy(view.get("rows", []))
        note = ("Eligible conversation now, not the exact last request." if mode == "Current context" else "Retained runtime messages; some are outside current context.")
        note += f" Display: {view.get('omitted', 0)} omitted, {view.get('shortened', 0)} shortened."
    shown = []
    for row in rows:
        if row.get("role") == "system" and not include_system or row.get("role") == "command" and not include_commands:
            continue
        if not include_commands:
            row["text"] = re.sub(r"(?ims)^\s*(?:executed )?commands?\s*:.*?(?=^\s*(?:observation|scene|tasks|goals|thoughts|response|narrative|summary)\s*:|\Z)", "[Commands hidden — view options]\n", row.get("text", ""))
        shown.append(row)
    return shown, note


def estimate_model_windows(rows, models, budgets=None):
    """Text-only recency fit against operator budgets, never provider inclusion proof."""
    budgets = budgets or {}
    result = []
    for slot, model in models.items():
        budget = budgets.get(model)
        budget = int(budget) if isinstance(budget, (int, float)) and math.isfinite(budget) and budget > 0 else None
        costs, used = {}, 0
        for row in reversed(rows):
            if row.get("kind", "text") != "text":
                continue
            token_count = row.get("token_count")
            cost = int(token_count) if isinstance(token_count, (int, float)) and math.isfinite(token_count) and token_count > 0 else max(1, math.ceil(row.get("original_chars", len(row.get("text", ""))) / 4))
            used += cost + 4
            costs[row["message_id"]] = None if budget is None else used <= budget
        result.append({"slot": slot, "model": model, "budget": budget, "fits": costs,
                       "estimated_text_tokens": used, "source": "operator text budget" if budget else "capacity unknown",
                       "note": "Approximate text-only recency fit; excludes images, system/init, tools, output reserve and provider session state. Does not change runtime selection."})
    return result


def build_init_context(text, *, source, profile, configured_file, configured_mode, prompt_limit):
    """Bounded observation of loaded init, not a disk read or complete provider prompt."""
    text = str(text or "").strip()
    limit = min(64000, max(0, int(prompt_limit)))
    return {"schema_version": "aurora_init_context_v1", "source": str(source or "unknown"),
            "profile": str(profile), "configured_file": str(configured_file), "configured_mode": str(configured_mode),
            "text": text[:limit], "total_chars": len(text), "displayed_chars": min(len(text), limit),
            "truncated": len(text) > limit, "prompt_char_limit": int(prompt_limit),
            "note": "Loaded init in runtime memory. Other system guidance, working memory and conversation are separate. This is not the complete last provider request."}


def build_prompt_materials(*, system, memory, current, retrieval, prepared_at, model):
    """Bounded text evidence at request preparation; never includes image bytes."""
    sections = {}
    for name, value in (("system", system), ("memory", memory), ("current", current), ("retrieval", retrieval)):
        text = str(value or "")
        sections[name] = {"text": text[:24000], "total_chars": len(text),
                          "displayed_chars": min(len(text), 24000), "truncated": len(text) > 24000}
    return {"schema_version": "aurora_prompt_materials_v1", "prepared_at": str(prepared_at),
            "model": str(model), "sections": sections,
            "note": "Last prepared text components, before provider transport. Preparation does not prove delivery or completion. Current context may since have changed; history, image bytes and provider session transformations are not reproduced here."}
