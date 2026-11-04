"""Bounded process-local retrieval evidence. No provider, disk or live-state restore.

Canonical JSON owns each retained payload; readers receive detached copies. Handles
identify one returned K-set, not the whole corpus or a historical knowledge view.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from collections import OrderedDict
from decimal import Decimal, InvalidOperation


RETRIEVAL_RESULT_SCHEMA = "aurora_retrieval_result_v1"
RETRIEVAL_RESULT_COMMANDS = {"SHOW_RETRIEVAL_RESULT", "PROMOTE_EPISODIC_MEMORY"}
PROMOTION_TARGET_ALIASES = {
    "note": "notes", "notes": "notes", "journal": "journal",
    "context": "recent_context", "recent_context": "recent_context", "recent": "recent_context",
    "pinned_immediate": "pinned_immediate", "immediate": "pinned_immediate",
    "pinned_short_term": "pinned_short_term", "short_term": "pinned_short_term", "short": "pinned_short_term",
    "goal": "apriority_goal", "apriority_goal": "apriority_goal", "open_goal": "apriority_goal",
    "overarching_goal": "overarching_goal", "mission": "overarching_goal",
}


def result_integer(value, name, minimum, maximum):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value() or not minimum <= number <= maximum:
            raise ValueError
        return int(number)
    except (ValueError, InvalidOperation):
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}.") from None


def validate_result_handle(value):
    value = str(value).strip()
    if not re.fullmatch(r"rr_[0-9a-f]{32}", value):
        raise ValueError("Expected a retained result handle rr_<32 hex digits>; run a search with result_mode=retained.")
    return value


def parse_retrieval_result_arguments(name, args):
    args = list(args)
    if any(not isinstance(value, str) for value in args):
        raise ValueError("Retrieval result arguments must be text.")
    if name.upper() == "SHOW_RETRIEVAL_RESULT":
        if not 1 <= len(args) <= 3:
            raise ValueError("SHOW_RETRIEVAL_RESULT(handle[, offset, limit]) requires 1–3 arguments.")
        return {"handle": validate_result_handle(args[0]),
                "offset": result_integer(args[1] if len(args) > 1 else 0, "offset", 0, 24),
                "limit": result_integer(args[2] if len(args) > 2 else 8, "limit", 1, 24)}
    if name.upper() != "PROMOTE_EPISODIC_MEMORY" or not 2 <= len(args) <= 4:
        raise ValueError("PROMOTE_EPISODIC_MEMORY(index, target[, prefix, result_handle]) requires 2–4 arguments.")
    target = PROMOTION_TARGET_ALIASES.get(args[1].strip().lower().replace(" ", "_"))
    if not target:
        raise ValueError("Unsupported promotion target. Use: " + ", ".join(dict.fromkeys(PROMOTION_TARGET_ALIASES.values())))
    return {"item_index": result_integer(args[0], "item_index", 1, 24), "target": target,
            "prefix": args[2] if len(args) > 2 else "",
            "result_handle": validate_result_handle(args[3]) if len(args) > 3 else ""}


def describe_retrieval_result_contract(name):
    inspect = name.upper() == "SHOW_RETRIEVAL_RESULT"
    parameters = ([{"name": "handle", "type": "string", "required": True},
                   {"name": "offset", "type": "integer", "default": 0, "minimum": 0, "maximum": 24},
                   {"name": "limit", "type": "integer", "default": 8, "minimum": 1, "maximum": 24}]
                  if inspect else [
                      {"name": "item_index", "type": "integer", "required": True, "minimum": 1, "maximum": 24},
                      {"name": "target", "type": "string", "required": True, "choices": list(PROMOTION_TARGET_ALIASES)},
                      {"name": "prefix", "type": "string", "default": ""},
                      {"name": "result_handle", "type": "string", "required": False}])
    return {"parameter_validation": "pre_dispatch", "parameters": parameters,
            "effects": "read_only" if inspect else "working_memory_mutation",
            "semantics": ("Inspect an immutable retained K-set without rescoring or a provider call." if inspect else
                          "Copy a legacy preview item, or exact full retained summary when a handle is supplied, into live memory; no state rewind."),
            "result": {"protocol": RETRIEVAL_RESULT_SCHEMA, "receipt_field": "retrieval_results",
                       "explicit_failure": "success=false", "none": "not_used"}}


class RetrievalResultStore:
    """FIFO/TTL capacity with copy isolation and monotonic expiry; reads do not extend life."""

    def __init__(self, *, max_batches=32, max_bytes=8 * 1024 * 1024,
                 max_batch_bytes=1024 * 1024, ttl_seconds=1800, clock=time.monotonic):
        if min(max_batches, max_bytes, max_batch_bytes, ttl_seconds) <= 0:
            raise ValueError("Result store limits must be positive.")
        self.max_batches, self.max_bytes = max_batches, max_bytes
        self.max_batch_bytes, self.ttl_seconds = min(max_batch_bytes, max_bytes), ttl_seconds
        self.clock = clock
        self.lock = threading.RLock()
        self.entries = OrderedDict()
        self.bytes_used = 0

    def prepare(self, selected, request, search, purpose):
        if len(selected) > 24:
            raise ValueError("A retained result set supports at most 24 returned items.")
        rows = []
        for index, candidate in enumerate(selected, 1):
            raw = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            record_raw = json.dumps(candidate["record"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            rows.append({"item_index": index, "item_id": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                         "record_sha256": hashlib.sha256(record_raw.encode("utf-8")).hexdigest(),
                         "candidate": json.loads(raw)})
        payload = {"schema_version": "aurora_retained_retrieval_v1", "purpose": purpose,
                   "request": request, "search": search, "items": rows, "returned_count": len(rows)}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > self.max_batch_bytes:
            raise ValueError(f"Retained result exceeds {self.max_batch_bytes} bytes; reduce K or use result_mode=legacy.")
        return raw

    def _expire(self):
        now = self.clock()
        for handle, entry in list(self.entries.items()):
            if now >= entry[0]:
                self.bytes_used -= len(entry[1])
                del self.entries[handle]

    def publish(self, prepared):
        # Only publish() mutates the cache. Validate detached data before eviction.
        if not isinstance(prepared, bytes) or len(prepared) > self.max_batch_bytes:
            raise ValueError("Invalid or oversized prepared retrieval result.")
        payload = json.loads(prepared)
        if (not isinstance(payload, dict) or payload.get("schema_version") != "aurora_retained_retrieval_v1"
                or not isinstance(payload.get("items"), list)
                or payload.get("returned_count") != len(payload["items"]) or len(payload["items"]) > 24):
            raise ValueError("Invalid prepared retrieval result schema.")
        with self.lock:
            self._expire()
            while self.entries and (len(self.entries) >= self.max_batches or self.bytes_used + len(prepared) > self.max_bytes):
                _, (_, old) = self.entries.popitem(last=False)
                self.bytes_used -= len(old)
            handle = "rr_" + uuid.uuid4().hex
            self.entries[handle] = (self.clock() + self.ttl_seconds, prepared)
            self.bytes_used += len(prepared)
        return {"handle": handle, "content_sha256": hashlib.sha256(prepared).hexdigest(),
                "returned_count": payload["returned_count"], "ttl_seconds": self.ttl_seconds,
                "scope": "runtime_memory", "max_batches": self.max_batches, "max_bytes": self.max_bytes,
                "max_batch_bytes": self.max_batch_bytes, "coverage": "returned_k_set"}

    def read(self, handle, offset=0, limit=8):
        handle = validate_result_handle(handle)
        offset, limit = result_integer(offset, "offset", 0, 24), result_integer(limit, "limit", 1, 24)
        with self.lock:
            self._expire()
            if handle not in self.entries:
                raise ValueError("Retained result unavailable: expired, evicted, unknown, or from another runtime. Rerun explicitly; no fallback to latest.")
            expires, raw = self.entries[handle]
            remaining = max(0, expires - self.clock())
        payload = json.loads(raw)
        total = payload["returned_count"]
        if offset > total:
            raise ValueError(f"offset exceeds retained result count {total}.")
        payload["items"] = payload["items"][offset:offset + limit]
        return {**payload, "handle": handle, "content_sha256": hashlib.sha256(raw).hexdigest(),
                "offset": offset, "next_offset": offset + limit if offset + limit < total else None,
                "expires_in_seconds": remaining, "scope": "runtime_memory"}

    def item(self, handle, index):
        index = result_integer(index, "item_index", 1, 24)
        page = self.read(handle, index - 1, 1)
        if not page["items"]:
            raise ValueError(f"item_index exceeds retained result count {page['returned_count']}.")
        return page["items"][0], page["content_sha256"]
