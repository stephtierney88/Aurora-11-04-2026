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


def conversation_text(view):
    return "\n\n".join(f"{row['role'].title()}  {row.get('timestamp', '')}\n{row['text']}"
                       for row in view.get("rows", []))
