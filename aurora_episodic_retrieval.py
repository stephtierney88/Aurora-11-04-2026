"""Offline-testable episodic retrieval policy, vector validation and cache writes.

Request-scoped options deliberately retain ordinal time and permissive ranking.
This module owns no provider, native input, worker or persistent settings service.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path


RETRIEVAL_OPTION_DEFAULTS = {
    "time_mode": "ordinal", "age_half_life_hours": 168.0,
    "min_relevance": 0.0, "embedding_fallback": "lexical",
    "score_mode": "legacy", "description_weight": 0.3, "keyword_weight": 0.3,
    "recency_weight": 0.3, "rating_weight": 0.1,
}
RETRIEVAL_WEIGHT_KEYS = ("description_weight", "keyword_weight", "recency_weight", "rating_weight")


def normalize_score_weights(values):
    weights = {key: finite_number(values.get(key, RETRIEVAL_OPTION_DEFAULTS[key]), float("nan")) for key in RETRIEVAL_WEIGHT_KEYS}
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in weights.values()):
        raise ValueError("Retrieval weights must be finite numbers from zero to one.")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one retrieval weight must be positive.")
    return {key: value / total for key, value in weights.items()}


def rebalance_score_weights(values, changed_key, changed_value):
    """Move one dial while redistributing the remainder proportionally (or equally)."""
    current = normalize_score_weights(values)
    if changed_key not in RETRIEVAL_WEIGHT_KEYS:
        raise ValueError("Unknown retrieval weight.")
    value = max(0.0, min(1.0, finite_number(changed_value)))
    others = [key for key in RETRIEVAL_WEIGHT_KEYS if key != changed_key]
    other_total = sum(current[key] for key in others)
    result = {key: (1.0 - value) * (current[key] / other_total if other_total > 0 else 1.0 / len(others)) for key in others}
    result[changed_key] = value
    return result


def weighted_score_components(request, description, keywords, recency, ratings):
    weights = normalize_score_weights(request)
    scores = (description, keywords, recency, ratings)
    return {key.removesuffix("_weight"): weights[key] * max(0.0, min(1.0, finite_number(score)))
            for key, score in zip(RETRIEVAL_WEIGHT_KEYS, scores)}


def distribution_rank_weight(shape, position, center, spread):
    position = max(0.0, min(1.0, finite_number(position)))
    center = max(0.0, min(1.0, finite_number(center)))
    spread = max(0.05, min(1.0, finite_number(spread, .22)))
    if shape == "gaussian":
        sigma = max(0.05, spread / 2.0)
        return math.exp(-((position - center) ** 2) / (2.0 * sigma * sigma))
    if shape == "geometric":
        decay = max(0.12, min(0.95, 1.0 - spread))
        return max(0.01, (1.0 - decay) ** (abs(position - center) * 10.0))
    if shape == "exponential":
        return math.exp(-(abs(position - center) / max(0.05, spread)))
    return max(0.05, 1.0 - abs(position - center) / max(0.2, spread + 0.2))


def distribution_preview(shape, center, spread, variance, samples=65):
    variance = max(0.0, min(1.0, finite_number(variance)))
    samples = max(2, min(257, int(samples)))
    rows = []
    for index in range(samples):
        position = index / (samples - 1)
        weight = distribution_rank_weight(shape, position, center, spread)
        rows.append({"position": position, "weight": weight,
                     "low": weight * (1 - variance), "high": weight * (1 + variance)})
    return rows


def finite_number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def normalize_retrieval_options(values):
    """Validate additive query options without changing legacy weight coercion."""
    result = dict(RETRIEVAL_OPTION_DEFAULTS)
    for key, allowed in (("score_mode", {"legacy", "weighted"}), ("time_mode", {"ordinal", "age"}),
                         ("embedding_fallback", {"lexical", "partial"})):
        value = str(values.get(key, result[key])).strip().lower()
        if value not in allowed:
            raise ValueError(f"{key} must be one of {', '.join(sorted(allowed))}.")
        result[key] = value
    for key, low, high in (("min_relevance", 0.0, 1.0),
                           ("age_half_life_hours", 0.001, 876000.0)):
        number = finite_number(values.get(key, result[key]), float("nan"))
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"{key} must be finite and between {low} and {high}.")
        result[key] = number
    if result["time_mode"] == "age" and str(values.get("time_anchor", "")).strip():
        raise ValueError("time_anchor uses ordinal percent; use time_mode=ordinal with an anchor.")
    result.update(normalize_score_weights(values))
    return result


def normalize_snapshot_record(record):
    """Ignore non-record JSON rows; keep legacy metadata and sanitize score inputs."""
    if not isinstance(record, dict):
        return None
    result = dict(record)
    tags = result.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    result["tags"] = [str(tag) for tag in tags if isinstance(tag, (str, int, float))] if isinstance(tags, list) else []
    for key in ("summary_text", "timestamp", "snapshot_id", "source_bucket"):
        result[key] = str(result.get(key) or "")
    for key in ("importance_score", "confidence_score", "outcome_score"):
        result[key] = finite_number(result.get(key))
    return result


def record_matches_filters(record, request):
    tags = {str(tag).strip().lower() for tag in record.get("tags", [])}
    required = {str(tag).strip().lower() for tag in request.get("tags_required", [])}
    buckets = {str(value).strip().lower() for value in request.get("source_buckets", [])}
    return required.issubset(tags) and (not buckets or str(record.get("source_bucket", "")).strip().lower() in buckets)


def embedding_record_key(record):
    """Content identity prevents same-second/duplicate snapshot IDs sharing vectors."""
    content = [record.get(key) for key in ("snapshot_id", "timestamp", "summary_text", "tags")]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def age_time_score(record, now_epoch, half_life_hours):
    """Prefer the writer's epoch; legacy naive timestamps use host local time."""
    stamp = finite_number(record.get("created_at_epoch"), float("nan"))
    source = "created_at_epoch"
    if not math.isfinite(stamp):
        source = "timestamp"
        try:
            stamp = datetime.datetime.fromisoformat(str(record.get("timestamp", "")).replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError, OverflowError, OSError):
            return {"time_score": 0.0, "age_hours": None, "time_source": "missing_or_invalid"}
    if not math.isfinite(stamp):
        return {"time_score": 0.0, "age_hours": None, "time_source": "missing_or_invalid"}
    age = max(0.0, (now_epoch - stamp) / 3600.0)
    return {"time_score": 2.0 ** (-age / half_life_hours), "age_hours": age,
            "time_source": source + (":future_clamped" if stamp > now_epoch else "")}


def validated_vector(value, dimension=None):
    if not isinstance(value, list) or not value or any(isinstance(x, bool) for x in value):
        raise ValueError("Embedding must be a nonempty numeric vector.")
    vector = [finite_number(x, float("nan")) for x in value]
    norm = math.hypot(*vector)
    if not all(math.isfinite(x) for x in vector) or not math.isfinite(norm) or norm <= 0:
        raise ValueError("Embedding must be finite and have a nonzero finite norm.")
    if dimension is not None and len(vector) != dimension:
        raise ValueError("Embedding dimensions do not match the query.")
    return vector


def parse_embedding_vectors(body, expected_count):
    """Honor response indices, rejecting duplicates, missing rows and mixed sizes."""
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError("Embedding response count does not match the request.")
    vectors = [None] * expected_count
    dimension = None
    for row in rows:
        index = row.get("index") if isinstance(row, dict) else None
        if type(index) is not int or not 0 <= index < expected_count or vectors[index] is not None:
            raise ValueError("Embedding response contains invalid or duplicate indices.")
        vector = validated_vector(row.get("embedding"), dimension)
        dimension = len(vector)
        vectors[index] = vector
    return vectors


def atomic_write_cache(path, payload):
    """Replace only after complete serialization/fsync; preserve old file on failure."""
    path = Path(path)
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_embedding_context(query, request, records, *, model, backend, auth_mode,
                            truncate, get_cached, request_vectors, save_entries,
                            check_cancel, batch_size=64):
    """Deduplicate text, bound provider batches and expose complete/partial coverage."""
    context = {"backend_requested": backend, "backend_used": "lexical", "embedding_model": model,
               "query_vector": None, "summary_vectors": {}, "tag_vectors": {}, "error": "",
               "cache_error": "", "auth_mode": auth_mode, "complete": False,
               "required_vectors": 0, "available_vectors": 0, "request_batches": 0}
    if not str(query).strip():
        context.update(backend_used="filter_only", complete=True)
        return context
    if backend == "off" or not records:
        context["complete"] = not records
        return context
    # Deduplicate transport by text, while retaining existing model/kind cache keys.
    slots = [("query", "", truncate(query))]
    for record in records:
        check_cancel()
        key = embedding_record_key(record)
        slots.extend([("summary", key, truncate(record.get("summary_text", ""))),
                      ("tags", key, truncate(" | ".join(record.get("tags", []))))])
    slots = list(dict.fromkeys(slot for slot in slots if slot[2]))
    context["required_vectors"] = len(slots)
    vectors = {}
    missing = {}
    for kind, key, text in slots:
        check_cancel()
        cached = get_cached(model, text, kind=kind)
        try:
            vectors[(kind, key)] = validated_vector(cached)
        except ValueError:
            missing.setdefault(text, []).append((kind, key))
    cache_entries = []
    texts = list(missing)
    for offset in range(0, len(texts), batch_size):
        check_cancel()
        batch = texts[offset:offset + batch_size]
        response = request_vectors(batch, model)
        check_cancel()
        context["request_batches"] += 1
        context["auth_mode"] = response.get("auth_mode", context["auth_mode"])
        if not response.get("ok"):
            context["error"] = response.get("error") or "Embedding request failed."
            break
        received = response.get("vectors", [])
        try:
            if len(received) != len(batch):
                raise ValueError("Embedding count mismatch.")
            received = [validated_vector(vector) for vector in received]
        except ValueError as error:
            context["error"] = str(error)
            break
        for text, vector in zip(batch, received):
            for kind, key in missing[text]:
                vectors[(kind, key)] = vector
                cache_entries.append({"text": text, "kind": kind, "vector": vector})
    query_vector = vectors.get(("query", ""))
    dimension = len(query_vector) if query_vector else None
    valid = {}
    if dimension is not None:
        for slot, vector in vectors.items():
            try:
                valid[slot] = validated_vector(vector, dimension)
            except ValueError as error:
                context["error"] = context["error"] or str(error)
    context["available_vectors"] = len(valid)
    context["complete"] = bool(query_vector) and len(valid) == len(slots)
    if not context["complete"]:
        context["error"] = context["error"] or "Embedding coverage is incomplete."
    check_cancel()
    # Only persist vectors matching this query, once for the whole retrieval.
    cache_entries = [row for row in cache_entries if dimension and len(row["vector"]) == dimension]
    if cache_entries:
        try:
            save_entries(model, cache_entries)
        except (OSError, ValueError, TypeError) as error:
            context["cache_error"] = f"Embedding cache was not saved ({type(error).__name__})."
    check_cancel()
    use_vectors = context["complete"] or (backend == "auto" and request.get("embedding_fallback") == "partial" and query_vector)
    if use_vectors:
        context["query_vector"] = query_vector
        for (kind, key), vector in valid.items():
            if kind != "query":
                context["summary_vectors" if kind == "summary" else "tag_vectors"][key] = vector
        context["backend_used"] = "embedding" if context["complete"] else "embedding_partial"
    elif backend == "force":
        context["backend_used"] = "embedding_failed"
    return context
