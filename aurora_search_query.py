"""Bounded, provider-free hard filters for episodic search.

The semantic query remains separate from this filter language. No eval, arbitrary
regex, implicit timezone, input hooks, workers or persistent settings live here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import threading
import uuid
from collections import OrderedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SEARCH_DEFAULTS = {
    "text_filter": "", "text_mode": "literal", "text_field": "any",
    "date_start": "", "date_end": "", "timezone": "UTC",
    "after": "", "before": "", "date_period": "none", "date_anchor": "",
    "sort": "legacy", "offset": 0, "result_mode": "legacy",
    "value_encoding": "legacy", "argument_policy": "legacy",
    "feedback_mode": "off", "feedback_factor": 0.25,
    "feedback_session": "manual", "feedback_action": "none", "feedback_token": "",
}
SEARCH_CHOICES = {
    "argument_policy": ("legacy", "strict"),
    "result_mode": ("legacy", "retained"),
    "date_period": ("none", "today", "yesterday", "last_24_hours", "last_7_days", "last_30_days",
                    "this_week", "last_week", "this_month", "last_month"),
    "text_mode": ("literal", "word", "phrase", "wildcard", "boolean"),
    "text_field": ("any", "summary", "tags"),
    "sort": ("legacy", "relevance", "newest", "oldest"),
    "value_encoding": ("legacy", "json"),
    "feedback_mode": ("off", "skip", "penalize"),
    "feedback_action": ("none", "reject_last", "reset"),
}


def decode_search_value(value):
    """Decode JSON-quoted command values once; retain legacy single quotes."""
    value = str(value).strip()
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid quoted search value; use JSON escaping (\\\\ for a literal backslash).") from error
        if not isinstance(decoded, str):
            raise ValueError("Quoted search values must be strings.")
        return decoded
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError("Unclosed single-quoted search value.")
        return value[1:-1].replace("\\'", "'").replace("\\\\", "\\")
    return value


def parse_search_options(segments, allowed_keys):
    """Strict named admission; the caller supplies framing and legacy key names."""
    pairs = {}
    for segment in segments:
        match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_ ]*)\s*[:=]\s*(.*)", str(segment), re.S)
        if not match:
            raise ValueError("Expected name=value after the optional first retrieval query.")
        key = match[1].strip().lower().replace(" ", "_")
        if key not in allowed_keys:
            hint = " Person/conversation filters require the future message index." if key in {
                "person", "author", "conversation", "person_id", "author_id", "conversation_id", "role"
            } else ""
            raise ValueError(f"Unsupported retrieval option: {key}.{hint}")
        if key in pairs:
            raise ValueError(f"Duplicate retrieval option: {key}.")
        pairs[key] = match[2].strip()
    encoding = decode_search_value(pairs.get("value_encoding", "legacy")).lower()
    if encoding not in SEARCH_CHOICES["value_encoding"]:
        raise ValueError("value_encoding must be legacy or json.")
    def decode(key, value):
        # Preserve the old handling of backslashes in existing named options.
        # New fields and explicit JSON mode decode one transport quoting layer.
        if encoding == "json" or key in SEARCH_DEFAULTS:
            return decode_search_value(value)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value
    return {key: decode(key, value) for key, value in pairs.items()}


def search_timezone(name):
    name = str(name).strip()
    if name.upper() in {"UTC", "Z"}:
        return dt.timezone.utc
    if re.fullmatch(r"[+-]\d{2}:\d{2}", name):
        hours, minutes = map(int, name[1:].split(":"))
        if hours > 23 or minutes > 59:
            raise ValueError("Invalid timezone offset; expected ±HH:MM.")
        return dt.timezone(dt.timedelta(minutes=(hours * 60 + minutes) * (-1 if name[0] == "-" else 1)))
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Unknown/unavailable timezone {name!r}; use UTC, ±HH:MM or an installed IANA zone.") from error


def _localize_strict(value, zone):
    if value.tzinfo is not None:
        return value
    first, second = value.replace(tzinfo=zone, fold=0), value.replace(tzinfo=zone, fold=1)
    valid = [candidate for candidate in (first, second)
             if candidate.astimezone(dt.timezone.utc).astimezone(zone).replace(tzinfo=None) == value]
    if not valid:
        raise ValueError("Date/time falls in a daylight-saving gap; supply an explicit UTC offset.")
    if len(valid) == 2 and first.utcoffset() != second.utcoffset():
        raise ValueError("Date/time is ambiguous at daylight-saving fallback; supply an explicit UTC offset.")
    return valid[0]


def date_boundary(value, zone, *, end=False):
    """[start, end): date-only end includes that entire calendar day."""
    if not value:
        return None
    value = str(value).strip()
    try:
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        if not date_only and not re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", value):
            raise ValueError("Use YYYY-MM-DD or an ISO date/time.")
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if end and date_only:
            parsed += dt.timedelta(days=1)
        return _localize_strict(parsed, zone).timestamp()
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError(f"Invalid {'end' if end else 'start'} date {value!r}: {error}") from error


def record_search_epoch(record, zone):
    try:
        epoch = float(record.get("created_at_epoch"))
        if math.isfinite(epoch) and not isinstance(record.get("created_at_epoch"), bool):
            dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
            return epoch
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    try:
        return _localize_strict(dt.datetime.fromisoformat(str(record.get("timestamp", "")).replace("Z", "+00:00")), zone).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def resolve_search_dates(options, *, evaluation_epoch=None):
    """Resolve one explicit window; relative calendar periods use the named zone.

    before excludes its instant/day; after excludes its instant or entire day.
    Existing date_start/date_end semantics are unchanged. Relative windows end
    exclusively; current periods run up to the anchor, completed periods are full.
    """
    zone = search_timezone(options["timezone"])
    start, end, inclusive = None, None, True
    period = options["date_period"]
    if period not in SEARCH_CHOICES["date_period"]:
        raise ValueError("Unsupported relative date period.")
    if options["after"] and options["date_start"]:
        raise ValueError("Use either after or date_start, not both.")
    if options["before"] and options["date_end"]:
        raise ValueError("Use either before or date_end, not both.")
    anchor = None
    try:
        if period == "none":
            if options["date_anchor"]:
                raise ValueError("date_anchor requires a relative date_period.")
            start = date_boundary(options["date_start"], zone)
            end = date_boundary(options["date_end"], zone, end=True)
            if options["after"]:
                date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", options["after"]))
                start = date_boundary(options["after"], zone, end=date_only)
                inclusive = date_only
            if options["before"]:
                end = date_boundary(options["before"], zone)
        else:
            if any(options[key] for key in ("date_start", "date_end", "after", "before")):
                raise ValueError("Relative date_period cannot be combined with explicit date bounds.")
            if options["date_anchor"]:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", options["date_anchor"]):
                    raise ValueError("date_anchor requires an ISO date/time, not a date alone.")
                anchor = date_boundary(options["date_anchor"], zone)
            else:
                if options["offset"] or options["feedback_mode"] != "off" or options["feedback_action"] != "none":
                    raise ValueError("Relative paging/feedback requires a fixed date_anchor; reuse the resolved anchor from the first search.")
                anchor = dt.datetime.now(dt.timezone.utc).timestamp() if evaluation_epoch is None else evaluation_epoch
            if isinstance(anchor, bool) or not isinstance(anchor, (float, int)) or not math.isfinite(anchor):
                raise ValueError("Invalid date evaluation time.")
            local = dt.datetime.fromtimestamp(anchor, zone)
            today = local.date()
            def midnight(day):
                return _localize_strict(dt.datetime.combine(day, dt.time()), zone).timestamp()
            elapsed = {"last_24_hours": 86400, "last_7_days": 7 * 86400, "last_30_days": 30 * 86400}
            if period in elapsed:
                start, end = anchor - elapsed[period], anchor
            elif period == "today":
                start, end = midnight(today), anchor
            elif period == "yesterday":
                start, end = midnight(today - dt.timedelta(days=1)), midnight(today)
            elif period in ("this_week", "last_week"):
                monday = today - dt.timedelta(days=today.weekday())
                start, end = (midnight(monday), anchor) if period == "this_week" else (
                    midnight(monday - dt.timedelta(days=7)), midnight(monday))
            else:
                first = today.replace(day=1)
                start, end = (midnight(first), anchor) if period == "this_month" else (
                    midnight((first - dt.timedelta(days=1)).replace(day=1)), midnight(first))
        for epoch in (start, end):
            if epoch is not None:
                dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
        if start is not None and end is not None and (start > end or (start == end and period == "none")):
            raise ValueError("Start must precede the exclusive end boundary.")
        iso = lambda epoch: None if epoch is None else dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat()
        return {"start_epoch": start, "end_epoch": end, "start_inclusive": inclusive,
                "end_exclusive": True, "start_utc": iso(start), "end_utc": iso(end),
                "anchor_epoch": anchor, "anchor_utc": iso(anchor), "period": period,
                "timezone": options["timezone"]}
    except (OverflowError, OSError) as error:
        raise ValueError("Date period exceeds the supported calendar range.") from error


def _glob_parts(pattern):
    parts, escaped = [], False
    for char in pattern.casefold():
        if escaped:
            parts.append(("literal", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in "*?":
            if char != "*" or not parts or parts[-1][0] != "*":
                parts.append((char, ""))
        else:
            parts.append(("literal", char))
    if escaped:
        raise ValueError("Wildcard/term cannot end in an unpaired backslash.")
    return parts


def _glob_matches(parts, text):
    """Full token glob, greedy bounded backtracking; no regex expansion."""
    p = t = 0
    star, retry = -1, 0
    while t < len(text):
        if p < len(parts) and (parts[p][0] == "?" or parts[p] == ("literal", text[t])):
            p += 1
            t += 1
        elif p < len(parts) and parts[p][0] == "*":
            star, retry = p, t
            p += 1
        elif star >= 0:
            retry += 1
            p, t = star + 1, retry
        else:
            return False
    return all(kind == "*" for kind, _ in parts[p:])


def _leaf(mode, value):
    if not value:
        raise ValueError("Empty search term/phrase is not supported.")
    if mode == "wildcard":
        if any(char.isspace() for char in value):
            raise ValueError("Wildcard mode matches one whitespace-delimited token; use Boolean AND for multiple patterns.")
        return (mode, _glob_parts(value), value)
    if mode == "word":
        parts = _glob_parts(value)
        if any(kind in {"*", "?"} for kind, _ in parts):
            return ("wildcard", parts, value)
        value = "".join(char for _, char in parts)
    return (mode, value.casefold(), value)


def _boolean_tokens(text):
    tokens, index = [], 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
        elif char == '"':
            index += 1
            chars = []
            while index < len(text) and text[index] != '"':
                if text[index] == "\\":
                    index += 1
                    if index == len(text):
                        raise ValueError("Unclosed phrase escape.")
                chars.append(text[index])
                index += 1
            if index == len(text):
                raise ValueError("Unclosed exact phrase.")
            index += 1
            tokens.append(_leaf("phrase", "".join(chars)))
        else:
            chars = []
            while index < len(text) and not text[index].isspace() and text[index] not in '()"':
                char = text[index]
                chars.append(char)
                index += 1
                if char == "\\":
                    if index == len(text):
                        raise ValueError("Unpaired term escape.")
                    chars.append(text[index])
                    index += 1
            value = "".join(chars)
            tokens.append(value.upper() if value.upper() in {"AND", "OR", "NOT"} else _leaf("word", value))
        if len(tokens) > 128:
            raise ValueError("Boolean filter exceeds 128 tokens.")
    return tokens


def compile_text_filter(text, mode):
    if not text:
        return None
    if len(text) > 2048:
        raise ValueError("text_filter exceeds 2048 characters.")
    if mode != "boolean":
        # Plain word mode treats stars literally; only explicit wildcard/Boolean
        # modes interpret patterns.
        return (mode, text.casefold(), text) if mode == "word" else _leaf(mode, text)
    tokens, position = _boolean_tokens(text), 0

    def expression(minimum=0, depth=0):
        nonlocal position
        if depth > 16:
            raise ValueError("Boolean filter nesting exceeds 16 levels.")
        if position >= len(tokens):
            raise ValueError("Missing Boolean operand.")
        token = tokens[position]
        position += 1
        if token == "NOT":
            node = ("NOT", expression(3, depth + 1))
        elif token == "(":
            node = expression(0, depth + 1)
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("Unclosed Boolean group.")
            position += 1
        elif isinstance(token, tuple):
            node = token
        else:
            raise ValueError("Expected a Boolean term, phrase, NOT or group.")
        while position < len(tokens) and isinstance(tokens[position], str):
            operator = tokens[position]
            precedence = {"OR": 1, "AND": 2}.get(operator, -1)
            if precedence < minimum:
                break
            position += 1
            node = (operator, node, expression(precedence + 1, depth + 1))
        return node

    result = expression()
    if position != len(tokens):
        raise ValueError("Unexpected Boolean token; use explicit AND/OR between terms.")
    return result


def _match_tree(node, fields):
    if node is None:
        return True
    kind = node[0]
    if kind == "AND":
        return _match_tree(node[1], fields) and _match_tree(node[2], fields)
    if kind == "OR":
        return _match_tree(node[1], fields) or _match_tree(node[2], fields)
    if kind == "NOT":
        return not _match_tree(node[1], fields)
    if kind == "wildcard":
        return any(_glob_matches(node[1], word) for field in fields for word in field.split())
    if kind in {"word", "phrase"}:
        value = node[1]
        pattern = (r"(?<!\w)" if value[0].isalnum() or value[0] == "_" else "") + re.escape(value)
        pattern += r"(?!\w)" if value[-1].isalnum() or value[-1] == "_" else ""
        return any(re.search(pattern, field) is not None for field in fields)
    return any(node[1] in field for field in fields)


def normalize_search_options(values):
    result = {key: values.get(key, default) for key, default in SEARCH_DEFAULTS.items()}
    for key, choices in SEARCH_CHOICES.items():
        result[key] = str(result[key]).strip().lower()
        if result[key] not in choices:
            raise ValueError(f"{key} must be one of {', '.join(choices)}.")
    for key in ("text_filter", "date_start", "date_end", "timezone", "after", "before", "date_anchor"):
        result[key] = str(result[key]).strip()
    if not re.fullmatch(r"\d{1,7}", str(result["offset"])) or int(result["offset"]) > 1000000:
        raise ValueError("offset must be an integer from 0 to 1000000.")
    result["offset"] = int(result["offset"])
    try:
        result["feedback_factor"] = float(result["feedback_factor"])
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("feedback_factor must be a number from zero to one.") from error
    if not math.isfinite(result["feedback_factor"]) or not 0 <= result["feedback_factor"] <= 1:
        raise ValueError("feedback_factor must be finite and from zero to one.")
    for key in ("feedback_session", "feedback_token"):
        result[key] = str(result[key]).strip()
        if len(result[key]) > 128:
            raise ValueError(f"{key} exceeds 128 characters.")
    if not result["feedback_session"]:
        raise ValueError("feedback_session must not be empty.")
    if result["feedback_action"] == "reject_last" and (result["feedback_mode"] == "off" or not result["feedback_token"]):
        raise ValueError("reject_last requires skip/penalize mode and the last result's feedback_token.")
    if result["feedback_mode"] != "off" and result["offset"]:
        raise ValueError("Feedback changes the candidate pool; use offset=0 with feedback enabled.")
    if result["feedback_mode"] == "penalize" and result["sort"] in {"newest", "oldest"}:
        raise ValueError("Penalties require legacy/relevance sorting; use skip for date sorting.")
    if result["offset"] and result["sort"] == "legacy":
        raise ValueError("Pagination requires sort=relevance, newest or oldest; legacy curve/jitter ranking remains available without offset.")
    # Validation does not read the clock or freeze an implicit relative anchor.
    resolve_search_dates(result, evaluation_epoch=946728000.0)
    compile_text_filter(result["text_filter"], result["text_mode"])
    return result


def search_has_filter(request):
    return (request.get("date_period", "none") != "none" or
            any(request.get(key) for key in ("text_filter", "date_start", "date_end", "after", "before", "tags_required", "source_buckets")))


def compile_search_filter(request, *, evaluation_epoch=None):
    options = normalize_search_options(request)
    zone = search_timezone(options["timezone"])
    dates = resolve_search_dates(options, evaluation_epoch=evaluation_epoch)
    return {"options": options, "zone": zone, "dates": dates,
            "start": dates["start_epoch"], "end": dates["end_epoch"],
            "tree": compile_text_filter(options["text_filter"], options["text_mode"])}


def match_search_filter(record, compiled):
    """Return explainable hard-filter evidence, or None for excluded records."""
    options, reasons = compiled["options"], []
    epoch = record_search_epoch(record, compiled["zone"])
    if compiled["start"] is not None or compiled["end"] is not None:
        if epoch is None:
            return None
        if compiled["start"] is not None and epoch < compiled["start"]:
            return None
        if not compiled["dates"]["start_inclusive"] and epoch == compiled["start"]:
            return None
        if compiled["end"] is not None and epoch >= compiled["end"]:
            return None
        bracket = "[" if compiled["dates"]["start_inclusive"] else "("
        reasons.append(f"timestamp within requested {bracket}start, end) boundaries")
    if compiled["tree"] is not None:
        groups = {"summary": [str(record.get("summary_text", "")).casefold()],
                  "tags": [str(tag).casefold() for tag in record.get("tags", [])]}
        selected = groups[options["text_field"]] if options["text_field"] != "any" else groups["summary"] + groups["tags"]
        if not _match_tree(compiled["tree"], selected):
            return None
        matched_fields = [name for name, fields in groups.items()
                          if options["text_field"] in {"any", name} and _match_tree(compiled["tree"], fields)]
        reasons.append(f"{options['text_mode']} filter passed in " + (", ".join(matched_fields) or "combined summary/tags"))
    return {"epoch": epoch, "reasons": reasons}


def order_search_candidates(candidates, request):
    """Explicit deterministic sorts bypass legacy curve/jitter; missing dates last."""
    mode = request.get("sort", "legacy")
    def key(item):
        epoch = item.get("search_epoch")
        identity = (str(item.get("record", {}).get("snapshot_id", "")), item.get("source_ordinal", 0))
        if mode == "relevance":
            return (-item.get("weighted_total", 0), *identity)
        return (epoch is None, 0 if epoch is None else epoch * (-1 if mode == "newest" else 1), *identity)
    ordered = sorted(candidates, key=key)
    offset = request.get("offset", 0)
    return [{**item, "adjusted_score": item["weighted_total"], "rank_weight": 1.0,
             "random_multiplier": 1.0, "sort_used": mode} for item in ordered[offset:offset + request.get("k", 4)]]


def feedback_record_key(record):
    """A changed record is new evidence, even if its snapshot ID is reused."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


class SearchFeedbackLedger:
    """Bounded process-local feedback; mutations commit only with successful results.

    Each session + effective query has a result token. Optimistic publication
    prevents stale/concurrent requests from rejecting a different batch. There
    are no workers, disk writes, implicit judgments or global settings here.
    """
    def __init__(self, max_queries=32, max_rejected=2048):
        self._entries = OrderedDict()
        self._lock = threading.RLock()
        self.max_queries = max_queries
        self.max_rejected = max_rejected

    def prepare(self, request):
        if request["feedback_mode"] == "off" and request["feedback_action"] == "none":
            return None
        identity_keys = ("query", "text_filter", "text_mode", "text_field", "date_start", "date_end", "timezone",
                         "after", "before", "date_period", "date_anchor",
                         "tags_required", "source_buckets", "feedback_session")
        identity = {key: request.get(key) for key in identity_keys}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        with self._lock:
            previous = self._entries.get(key)
            expected = previous["token"] if previous else None
            rejected = dict(previous["rejected"]) if previous else {}
            if request["feedback_action"] == "reject_last":
                if not previous or request["feedback_token"] != expected:
                    raise ValueError("Feedback token is stale, expired, or belongs to another query/session. Search again before marking results.")
                for record_key in previous["last"]:
                    rejected[record_key] = rejected.get(record_key, 0) + 1
                if len(rejected) > self.max_rejected:
                    raise ValueError("Feedback limit reached; reset this query's feedback or use a new session.")
            elif request["feedback_action"] == "reset":
                rejected = {}
            return {"key": key, "expected": expected, "rejected": rejected,
                    "mode": request["feedback_mode"], "factor": request["feedback_factor"],
                    "session": request["feedback_session"]}

    def factor(self, plan, record):
        if not plan or plan["mode"] == "off":
            return 1.0
        count = plan["rejected"].get(feedback_record_key(record), 0)
        if not count:
            return 1.0
        return 0.0 if plan["mode"] == "skip" else plan["factor"] ** count

    def publish(self, plan, selected):
        if plan is None:
            return {"mode": "off", "token": "", "scope": "runtime_session"}
        with self._lock:
            previous = self._entries.get(plan["key"])
            if (previous["token"] if previous else None) != plan["expected"]:
                raise ValueError("Feedback changed during retrieval; retry with the current result token.")
            token = uuid.uuid4().hex
            self._entries[plan["key"]] = {"token": token, "rejected": plan["rejected"],
                                          "last": [feedback_record_key(item["record"]) for item in selected]}
            self._entries.move_to_end(plan["key"])
            while len(self._entries) > self.max_queries:
                self._entries.popitem(last=False)
            return {"mode": plan["mode"], "factor": plan["factor"], "token": token,
                    "session": plan["session"], "query_key": plan["key"],
                    "rejected_records": len(plan["rejected"]), "scope": "runtime_session",
                    "max_queries": self.max_queries, "max_rejected": self.max_rejected}
