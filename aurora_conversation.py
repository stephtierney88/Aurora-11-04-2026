"""Detached, bounded conversation views. Never reads the historical chat log."""
from __future__ import annotations

import hashlib
import json

MAX_VIEW_CHARS = 256_000
MAX_MESSAGE_CHARS = 32_000
MAX_VIEW_ROWS = 2_000


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
                     "timestamp": str(entry.get("timestamp", "")), "kind": kind,
                     "timestamp_iso": str(entry.get("timestamp_iso", "")),
                     "model": str(entry.get("model", "")), "model_source": str(entry.get("model_source", "unknown")),
                     "edited_by": str(entry.get("edited_by", "")), "edited_at": str(entry.get("edited_at", "")),
                     "shortened": shortened})
    rows.reverse()
    result = {"source": source, "rows": rows, "total": len(entries),
              "omitted": len(entries) - len(rows), "shortened": clipped}
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def build_conversation_snapshot(history_read_state, current_entries=None):
    """Current means eligible history now, not the exact last provider payload."""
    current = (history_read_state.get("recent_prompt_history", [])
               if current_entries is None else current_entries)
    return {"schema_version": "aurora_conversation_v1",
            "current": build_conversation_view(current, source="current_context_window"),
            "retained": build_conversation_view(history_read_state.get("history_store", []),
                                                source="retained_runtime_history")}


def conversation_text(view, *, show_time=True, show_model=True, show_edits=True):
    blocks = []
    for row in view.get("rows", []):
        details = []
        if show_model and row.get("role") == "assistant":
            model = row.get("model") or "model unknown"
            if row.get("model_source") == "requested":
                model += " (requested)"
            details.append(model)
        if show_time:
            details.append(row.get("timestamp_iso") or row.get("timestamp") or "time unknown")
        if show_edits and row.get("edited_by"):
            details.append("last edited by " + row["edited_by"] + (" · " + row.get("edited_at", "") if show_time else ""))
        text = row["text"]
        legacy_prefix = "[" + str(row.get("timestamp", "")) + "] "
        if row.get("timestamp") and text.startswith(legacy_prefix):
            text = text[len(legacy_prefix):]
        blocks.append(f"{row['role'].title()}  {' · '.join(details)}\n{text}")
    return "\n\n".join(blocks)


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
