"""Shared provider-free admission for episodic queries and snapshot commands.

Legacy coercion remains the default; strict argument policy is opt-in. Execution
supplies current runtime defaults, while static admission validates supplied fields.
"""
from __future__ import annotations
import json
import math
import re
from aurora_episodic_retrieval import RETRIEVAL_OPTION_DEFAULTS, normalize_retrieval_options
from aurora_search_query import SEARCH_DEFAULTS, SEARCH_CHOICES, parse_search_options, normalize_search_options, search_has_filter
from aurora_retrieval_results import RETRIEVAL_RESULT_SCHEMA, result_integer

RETRIEVAL_QUERY_COMMANDS = {"RETRIEVAL_PULL", "RECALL", "MEM"}
SNAPSHOT_COMMANDS = {"WRITE_EPISODIC_SNAPSHOT", "LIST_EPISODIC_SNAPSHOTS", "SEARCH_EPISODIC_SNAPSHOTS"}
EPISODIC_COMMANDS = RETRIEVAL_QUERY_COMMANDS | SNAPSHOT_COMMANDS
ALLOWED_RETRIEVAL_DISTRIBUTION_SHAPES = {"balanced", "gaussian", "geometric", "exponential"}
ALLOWED_EPISODIC_EMBEDDING_MODES = {"off", "auto", "force"}


def validate_legacy_fields(pairs):
    """Opt-in strict checks run before legacy clamp/default conversions."""
    policy = str(pairs.get("argument_policy", "legacy")).strip().lower()
    if policy not in {"legacy", "strict"}:
        raise ValueError("argument_policy must be legacy or strict.")
    if policy == "legacy":
        return
    if "k" in pairs:
        result_integer(pairs["k"], "k", 1, 24)
    ranges = {key: (0, 1) for key in ("time_weight", "semantic_weight", "tag_weight", "semantic_tag_weight", "variance_bias")}
    ranges.update(time_scale=(0.1, 5), distribution_center=(0, 100), distribution_spread=(0.05, 100))
    for key, (minimum, maximum) in ranges.items():
        if key not in pairs:
            continue
        try:
            value = float(pairs[key])
        except (TypeError, ValueError, OverflowError):
            value = float("nan")
        if (not math.isfinite(value) or not minimum <= value <= maximum
                or (key == "distribution_spread" and 1 < value < 5)):
            raise ValueError(f"Strict {key} requires a finite value in {minimum}–{maximum}; spread uses .05–1 or 5–100 percent.")
    for key, allowed in (("semantic_backend", ALLOWED_EPISODIC_EMBEDDING_MODES),
                         ("distribution_shape", ALLOWED_RETRIEVAL_DISTRIBUTION_SHAPES)):
        if key in pairs and str(pairs[key]).strip().lower() not in allowed:
            raise ValueError(f"Strict {key} must be one of {', '.join(sorted(allowed))}.")
    anchor = str(pairs.get("time_anchor", "")).strip().lower()
    if anchor and anchor not in {"oldest", "early", "mid", "middle", "late", "latest", "recent", "now"}:
        try:
            value = float(anchor)
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Strict time_anchor requires a known ordinal alias or a finite value from 0 to 100.")
    if "embedding_model" in pairs and not str(pairs["embedding_model"]).strip():
        raise ValueError("Strict embedding_model cannot be blank.")


def parse_episodic_command(name, args, *, list_limit=8, **defaults):
    name = name.upper()
    args = list(args or [])
    if any(not isinstance(arg, str) for arg in args):
        raise ValueError("Episodic command arguments must be text.")
    if name in RETRIEVAL_QUERY_COMMANDS:
        parser = build_retrieval_request if name == "RETRIEVAL_PULL" else build_retrieval_shorthand_request
        return parser(args, **defaults)
    if name not in SNAPSHOT_COMMANDS:
        raise ValueError(f"Unsupported episodic command: {name}.")
    if name == "WRITE_EPISODIC_SNAPSHOT":
        if len(args) > 2:
            raise ValueError("WRITE_EPISODIC_SNAPSHOT accepts optional reason and tags only.")
        return {"reason": args[0].strip() if args else "manual snapshot", "tags": args[1] if len(args) > 1 else ""}
    search = name == "SEARCH_EPISODIC_SNAPSHOTS"
    if (search and (not args or not args[0].strip())) or len(args) > (2 if search else 1):
        raise ValueError("SEARCH_EPISODIC_SNAPSHOTS requires query[, limit]." if search else "LIST_EPISODIC_SNAPSHOTS accepts optional limit only.")
    index = 1 if search else 0
    limit = list_limit
    if len(args) > index:
        try:
            number = float(args[index])
            if not math.isfinite(number):
                raise ValueError
            # Preserve legacy finite limit rounding/clamping.
            limit = max(1, min(24, int(number)))
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{name} limit must be a finite number.") from None
    return {"limit": limit, **({"query": args[0].strip()} if search else {})}


def episodic_receipt(operation, *, success=True, effect_status="read_only", reason="", **evidence):
    return {"schema_version": RETRIEVAL_RESULT_SCHEMA, "operation": operation, "success": success,
            "effect_status": effect_status, "reason": reason, **evidence}


def retrieval_receipt(result, requested):
    context = result.get("embedding_context") or {}
    return episodic_receipt("retrieve", success=bool(result.get("ok")),
        effect_status="published" if result.get("ok") else "not_published",
        reason=result.get("error", ""), requested=requested, effective=result.get("request", requested),
        retrieval_id=(result.get("request") or requested).get("_retrieval_id"),
        search=result.get("search", {}), summary=result.get("summary", ""),
        backend={key: context.get(key) for key in ("backend_requested", "backend_used", "embedding_model", "complete",
                    "required_vectors", "available_vectors", "request_batches", "error", "cache_error")})


def describe_episodic_contract(name):
    name = name.upper()
    query = name in RETRIEVAL_QUERY_COMMANDS
    if query:
        parameters = [{"name": "query_or_named_options", "type": "string", "variadic": True, "required": True}]
        semantics = ("Validate the complete query before batch execution, then recheck with runtime defaults. "
                     "argument_policy=legacy preserves old clamps/fallbacks; strict rejects invalid legacy numeric/enum fields. "
                     "Hard filters, option names, Boolean/date syntax and new options always validate. "
                     "May call embeddings and update cache/feedback/results; no automatic memory promotion.")
    else:
        parameters = ([{"name": "reason", "type": "string", "default": "manual snapshot"}, {"name": "tags", "type": "string", "default": ""}]
                      if name == "WRITE_EPISODIC_SNAPSHOT" else
                      ([{"name": "query", "type": "string", "required": True}] if name.startswith("SEARCH_") else [])
                      + [{"name": "limit", "type": "number", "required": False, "default_source": "runtime configured list limit", "coercion": "finite values truncate/clamp to 1–24"}])
        semantics = "Existing episodic snapshot write/list/lexical-search behavior with complete argument admission and correlated receipts; no inferred persistence or rollback guarantee."
    named_options = {}
    if query:
        choices = {**SEARCH_CHOICES, "semantic_backend": ("off", "auto", "force"),
                   "distribution_shape": ("balanced", "gaussian", "geometric", "exponential"),
                   "score_mode": ("legacy", "weighted"), "time_mode": ("ordinal", "age"),
                   "embedding_fallback": ("lexical", "partial")}
        for key, value in retrieval_query_defaults().items():
            named_options[key] = {"default": value}
            if key in choices:
                named_options[key]["choices"] = list(choices[key])
            if key in {"semantic_backend", "embedding_model"}:
                named_options[key]["default_source"] = "runtime configuration; built-in fallback shown"
    return {"parameter_validation": "pre_dispatch", "parameters": parameters, "named_options": named_options, "semantics": semantics,
            "effects": "query_provider_cache_and_result_state" if query else "snapshot_append" if name.startswith("WRITE_") else "snapshot_read",
            "result": {"protocol": RETRIEVAL_RESULT_SCHEMA, "receipt_field": "retrieval_results",
                       "failure_policy": "Failure stops batch tail; prior effects are not rolled back. Unexpected execution exceptions report uncertainty."}}

def normalize_text_content(content):
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text", ""))
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ""
    return str(content)

def normalize_memory_item(text):
    cleaned = normalize_text_content(text).strip()
    cleaned = cleaned.strip("`").strip()
    cleaned = re.sub(r'^\s*[-*+]\s*', '', cleaned)
    cleaned = re.sub(r'^\s*\d+[.)]\s*', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def strip_wrapping_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

def split_option_segments(raw_text):
    text = normalize_text_content(raw_text).strip()
    if not text:
        return []
    segments = []
    current = []
    quote_char = None
    escape_next = False
    nesting_depth = 0

    for char in text:
        if escape_next:
            current.append(char)
            escape_next = False
            continue
        if quote_char:
            current.append(char)
            if char == "\\":
                escape_next = True
            elif char == quote_char:
                quote_char = None
            continue
        if char in {"'", '"'}:
            quote_char = char
            current.append(char)
            continue
        if char in "([{":
            nesting_depth += 1
            current.append(char)
            continue
        if char in ")]}":
            nesting_depth = max(0, nesting_depth - 1)
            current.append(char)
            continue
        if nesting_depth == 0 and char in {";", "\n"}:
            candidate = "".join(current).strip()
            if candidate:
                segments.append(candidate)
            current = []
            continue
        current.append(char)

    trailing = "".join(current).strip()
    if trailing:
        segments.append(trailing)
    return segments

def _parse_snapshot_tags_arg(raw_value, max_tags=16):
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        items = list(raw_value)
    else:
        text = normalize_text_content(raw_value).replace(";", ",")
        items = text.split(",")
    tags = []
    seen = set()
    for item in items:
        cleaned = normalize_memory_item(item).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(cleaned)
        if len(tags) >= max_tags:
            break
    return tags

def _normalize_retrieval_weight(value, default):
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return max(0.0, min(1.0, numeric))

def _normalize_retrieval_positive_float(value, default, minimum=0.0, maximum=None):
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    numeric = max(minimum, numeric)
    if maximum is not None:
        numeric = min(maximum, numeric)
    return float(numeric)

def _normalize_retrieval_int(value, default, minimum=1, maximum=24):
    try:
        numeric = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return int(default)
    return max(minimum, min(maximum, numeric))

def _normalize_distribution_shape(value):
    normalized = normalize_text_content(value).strip().lower() or "balanced"
    if normalized not in ALLOWED_RETRIEVAL_DISTRIBUTION_SHAPES:
        return "balanced"
    return normalized

def _normalize_distribution_center(value, default=0.0):
    if value is None or value == "":
        return float(default)
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.0, min(1.0, numeric))

def _normalize_distribution_spread(value, default=0.22):
    if value is None or value == "":
        return float(default)
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.05, min(1.0, numeric))

def _normalize_episodic_embedding_mode(value, default="auto"):
    normalized = normalize_text_content(value).strip().lower() or normalize_text_content(default).strip().lower() or "auto"
    return normalized if normalized in ALLOWED_EPISODIC_EMBEDDING_MODES else "auto"

def retrieval_query_defaults(embedding_mode="auto", embedding_model="text-embedding-3-small"):
    return {
        "query": "",
        "k": 4,
        "time_weight": 0.5,
        "semantic_weight": 0.5,
        "tag_weight": 0.0,
        "semantic_tag_weight": 0.5,
        "semantic_backend": embedding_mode,
        "embedding_model": embedding_model,
        "time_anchor": "",
        "time_scale": 1.0,
        **RETRIEVAL_OPTION_DEFAULTS,
        **SEARCH_DEFAULTS,
        "distribution_shape": "balanced",
        "distribution_center": 0.0,
        "distribution_spread": 0.22,
        "variance_bias": 0.0,
        "tags_required": [],
        "tags_preferred": [],
        "source_buckets": [],
    }


def build_retrieval_request(args, *, embedding_mode="auto", embedding_model="text-embedding-3-small", max_tags=16):
    args = list(args or [])
    if any(not isinstance(arg, str) for arg in args):
        raise ValueError("Retrieval arguments must be text.")
    defaults = retrieval_query_defaults(embedding_mode, embedding_model)

    positional_query = ""
    named_segments = []
    for index, arg in enumerate(args):
        cleaned = normalize_text_content(arg).strip()
        if not cleaned:
            continue
        if index == 0 and not re.match(r"^[A-Za-z_][A-Za-z0-9_ ]*\s*[:=]", cleaned):
            positional_query = strip_wrapping_quotes(cleaned)
            continue
        named_segments.append(cleaned)

    segments = split_option_segments("; ".join(named_segments))
    pairs = parse_search_options(segments, set(defaults))
    if positional_query and "query" in pairs:
        raise ValueError("Supply either a positional query or query=, not both.")
    validate_legacy_fields(pairs)
    request = dict(defaults)
    request["query"] = normalize_text_content(positional_query or pairs.get("query", "")).strip()
    request["k"] = _normalize_retrieval_int(pairs.get("k", request["k"]), request["k"])
    request["time_weight"] = _normalize_retrieval_weight(pairs.get("time_weight", request["time_weight"]), request["time_weight"])
    request["semantic_weight"] = _normalize_retrieval_weight(pairs.get("semantic_weight", request["semantic_weight"]), request["semantic_weight"])
    request["tag_weight"] = _normalize_retrieval_weight(pairs.get("tag_weight", request["tag_weight"]), request["tag_weight"])
    request["semantic_tag_weight"] = _normalize_retrieval_weight(pairs.get("semantic_tag_weight", request["semantic_tag_weight"]), request["semantic_tag_weight"])
    request["semantic_backend"] = _normalize_episodic_embedding_mode(pairs.get("semantic_backend", request["semantic_backend"]), request["semantic_backend"])
    request["embedding_model"] = normalize_text_content(pairs.get("embedding_model", request["embedding_model"])).strip() or embedding_model
    request["time_anchor"] = normalize_text_content(pairs.get("time_anchor", "")).strip()
    request["time_scale"] = _normalize_retrieval_positive_float(pairs.get("time_scale", request["time_scale"]), request["time_scale"], minimum=0.1, maximum=5.0)
    request["distribution_shape"] = _normalize_distribution_shape(pairs.get("distribution_shape", request["distribution_shape"]))
    request["distribution_center"] = _normalize_distribution_center(pairs.get("distribution_center", request["distribution_center"]), request["distribution_center"])
    request["distribution_spread"] = _normalize_distribution_spread(pairs.get("distribution_spread", request["distribution_spread"]), request["distribution_spread"])
    request["variance_bias"] = _normalize_retrieval_weight(pairs.get("variance_bias", request["variance_bias"]), request["variance_bias"])
    request["tags_required"] = _parse_snapshot_tags_arg(pairs.get("tags_required", ""), max_tags)
    request["tags_preferred"] = _parse_snapshot_tags_arg(pairs.get("tags_preferred", ""), max_tags)
    request["source_buckets"] = [value.lower() for value in _parse_snapshot_tags_arg(pairs.get("source_buckets", ""), max_tags)]
    request.update(normalize_retrieval_options({**request, **{key: pairs[key] for key in RETRIEVAL_OPTION_DEFAULTS if key in pairs}}))
    request.update(normalize_search_options({**request, **{key: pairs[key] for key in SEARCH_DEFAULTS if key in pairs}}))
    if not request["query"] and not search_has_filter(request):
        raise ValueError("Supply semantic query text or at least one hard text/date/tag/source filter.")
    if not request["query"] and request["min_relevance"] > 0:
        raise ValueError("min_relevance requires semantic query text; use zero for filter-only searches.")
    return request

def build_retrieval_shorthand_request(args, **defaults):
    normalized_args = list(args or [])
    if len(normalized_args) > 1:
        first = normalize_text_content(normalized_args[0]).strip()
        second = normalize_text_content(normalized_args[1]).strip()
        first_is_named = bool(re.match(r"^[A-Za-z_][A-Za-z0-9_ ]*\s*[:=]", first))
        second_is_named = bool(re.match(r"^[A-Za-z_][A-Za-z0-9_ ]*\s*[:=]", second))
        if first and second and not first_is_named and not second_is_named and re.fullmatch(r"\d+(?:\.\d+)?", second):
            normalized_args = [first, f"k={second}"] + normalized_args[2:]
    return build_retrieval_request(normalized_args, **defaults)
