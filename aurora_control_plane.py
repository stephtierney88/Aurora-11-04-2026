from __future__ import annotations

import ctypes
import datetime
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from ctypes import wintypes
from pathlib import Path
from typing import Any


BRIDGE_REQUEST_SCHEMA_VERSION = "aurora_bridge_request_v1"
COMMAND_RECEIPT_SCHEMA_VERSION = "aurora_command_receipt_v1"
MUTATION_ADMISSION_SCHEMA_VERSION = "aurora_mutation_admission_v1"
OPERATOR_DASHBOARD_SCHEMA_VERSION = "aurora_operator_dashboard_v1"
OPERATOR_DASHBOARD_EVENT_SCHEMA_VERSION = "aurora_operator_dashboard_event_v1"
DEFAULT_CLIENT_ID = "aurora_operator"
IDENTIFIER_MAX_CHARS = 160


def control_plane_paths(root: str | os.PathLike[str]) -> dict[str, Path]:
    root_path = Path(root).expanduser().resolve()
    return {
        "root": root_path,
        "state": root_path / "aurora_control_panel_state.json",
        "inbox": root_path / "aurora_external_inbox.jsonl",
        "bridge_log": root_path / "aurora_external_bridge_log.jsonl",
        "command_log": root_path / "aurora_command_execution_log.jsonl",
        "mutation_log": root_path / "aurora_mutation_admission_log.jsonl",
        "cli_history": root_path / "aurora_cli_history.jsonl",
        "command_index": root_path / "aurora_reference_maps" / "commands" / "commands-index.tsv",
        "runtime_pid": root_path / "aurora_runtime.pid",
        "control_panel_pid": root_path / "aurora_control_panel.pid",
    }


def normalize_identifier(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[^A-Za-z0-9._:-]+", "-", text)
    return text.strip("-")[:IDENTIFIER_MAX_CHARS]


def _new_identifier(prefix: str) -> str:
    clean_prefix = normalize_identifier(prefix, "aurora") or "aurora"
    return f"{clean_prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:10]}"


def extract_request_identity(record: dict[str, Any] | None) -> dict[str, str]:
    record = record if isinstance(record, dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    message_id = normalize_identifier(record.get("message_id") or metadata.get("message_id"))
    request_id = normalize_identifier(
        record.get("request_id") or metadata.get("request_id") or message_id
    )
    client_id = normalize_identifier(
        record.get("client_id")
        or metadata.get("client_id")
        or record.get("source")
        or DEFAULT_CLIENT_ID
    )
    return {
        "request_id": request_id,
        "message_id": message_id,
        "client_id": client_id,
    }


def build_bridge_request(
    text: str,
    *,
    raw: bool = False,
    source: str = "external",
    author: str = "operator",
    subject: str = "[AURORA OPERATOR]",
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    message_id: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("Aurora bridge requests require non-empty text.")

    normalized_source = normalize_identifier(source, "external") or "external"
    normalized_client_id = normalize_identifier(
        client_id,
        normalized_source or DEFAULT_CLIENT_ID,
    )
    normalized_request_id = normalize_identifier(
        request_id,
        _new_identifier(f"{normalized_client_id}-request"),
    )
    normalized_message_id = normalize_identifier(
        message_id,
        _new_identifier(f"{normalized_client_id}-message"),
    )
    payload_metadata = dict(metadata or {})
    payload_metadata["ingest_mode"] = "raw" if raw else str(
        payload_metadata.get("ingest_mode") or "normal"
    ).strip().lower()
    payload_metadata["request_id"] = normalized_request_id
    payload_metadata["message_id"] = normalized_message_id
    payload_metadata["client_id"] = normalized_client_id
    now = time.time()
    return {
        "schema_version": BRIDGE_REQUEST_SCHEMA_VERSION,
        "request_id": normalized_request_id,
        "message_id": normalized_message_id,
        "client_id": normalized_client_id,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "created_at_epoch": round(now, 6),
        "author": str(author or "operator").strip() or "operator",
        "source": normalized_source,
        "subject": str(subject or "").strip(),
        "text": normalized_text,
        "metadata": payload_metadata,
    }


def append_jsonl_record(path: str | os.PathLike[str], record: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def append_durable_jsonl_record(
    path: str | os.PathLike[str],
    record: dict[str, Any],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def mutation_command_digest(command_text: Any) -> str:
    normalized = str(command_text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mutation_admission_id(client_id: Any, request_id: Any) -> str:
    normalized_client_id = normalize_identifier(client_id)
    normalized_request_id = normalize_identifier(request_id)
    if not normalized_client_id or not normalized_request_id:
        return ""
    identity_digest = hashlib.sha256(
        f"{normalized_client_id}\0{normalized_request_id}".encode("utf-8")
    ).hexdigest()
    return f"mutation-{identity_digest[:24]}"


def _mutation_identity(client_id: Any, request_id: Any) -> tuple[str, str]:
    normalized_client_id = normalize_identifier(client_id)
    normalized_request_id = normalize_identifier(request_id)
    if not normalized_client_id or not normalized_request_id:
        raise ValueError("Mutation admission requires both client_id and request_id.")
    return normalized_client_id, normalized_request_id


def _mutation_journal_timestamp() -> tuple[str, float]:
    now = time.time()
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(now, 6)


class MutationAdmissionJournal:
    """Durably reserve mutating request identities before runtime dispatch."""

    def __init__(self, root: str | os.PathLike[str], *, session_id: str = "") -> None:
        self.root = Path(root).expanduser().resolve()
        self.paths = control_plane_paths(self.root)
        self.session_id = normalize_identifier(session_id)
        self._lock = threading.RLock()
        self._entries: dict[tuple[str, str], dict[str, Any]] = {}
        self.reload()

    def reload(self) -> dict[str, Any]:
        with self._lock:
            entries: dict[tuple[str, str], dict[str, Any]] = {}
            rows, _ = read_jsonl_from(self.paths["mutation_log"], 0)
            for row in rows:
                if row.get("schema_version") != MUTATION_ADMISSION_SCHEMA_VERSION:
                    continue
                client_id = normalize_identifier(row.get("client_id"))
                request_id = normalize_identifier(row.get("request_id"))
                if not client_id or not request_id:
                    continue
                key = (client_id, request_id)
                event = str(row.get("event") or "").strip()
                if event in {"mutation_admitted", "mutation_rejected"}:
                    entries.setdefault(
                        key,
                        {
                            "admission": dict(row),
                            "terminal_receipt": None,
                        },
                    )
                elif event == "mutation_terminal" and key in entries:
                    receipt = row.get("receipt")
                    if isinstance(receipt, dict) and bool(receipt.get("terminal", True)):
                        entries[key]["terminal_receipt"] = dict(receipt)

            # A terminal command row may have reached disk just before a crash that
            # prevented the matching mutation_terminal journal row.
            command_rows, _ = read_jsonl_from(self.paths["command_log"], 0)
            for row in command_rows:
                if row.get("event") != "command_result" or not bool(row.get("terminal", True)):
                    continue
                if bool(row.get("duplicate_suppressed", False)):
                    continue
                client_id = normalize_identifier(row.get("client_id"))
                request_id = normalize_identifier(row.get("request_id"))
                key = (client_id, request_id)
                entry = entries.get(key)
                if entry is None:
                    continue
                admission = entry["admission"]
                if row.get("mutation_admission_id") != admission.get("admission_id"):
                    continue
                if str(row.get("command_digest") or "").strip() != admission.get(
                    "command_digest"
                ):
                    continue
                if entry.get("terminal_receipt") is None:
                    entry["terminal_receipt"] = dict(row)

            self._entries = entries
            return self.summary()

    def reserve(
        self,
        command_text: Any,
        *,
        client_id: Any,
        request_id: Any,
        message_id: Any = "",
        command_name: Any = "",
        admitted: bool = True,
        reason: str = "",
    ) -> dict[str, Any]:
        normalized_client_id, normalized_request_id = _mutation_identity(client_id, request_id)
        normalized_message_id = normalize_identifier(message_id)
        digest = mutation_command_digest(command_text)
        admission_id = mutation_admission_id(normalized_client_id, normalized_request_id)
        key = (normalized_client_id, normalized_request_id)

        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                admission = existing["admission"]
                result = {
                    "schema_version": MUTATION_ADMISSION_SCHEMA_VERSION,
                    "admission_id": admission_id,
                    "client_id": normalized_client_id,
                    "request_id": normalized_request_id,
                    "message_id": normalized_message_id,
                    "command_digest": digest,
                    "original_message_id": admission.get("message_id", ""),
                    "original_disposition": admission.get("disposition", "admitted"),
                    "duplicate_suppressed": True,
                    "replay_attempted": False,
                }
                if digest != admission.get("command_digest"):
                    result.update(
                        {
                            "decision": "request_conflict",
                            "terminal": True,
                            "reason": (
                                "The client_id + request_id pair is already reserved for a "
                                "different mutating command payload."
                            ),
                        }
                    )
                    return result
                terminal_receipt = existing.get("terminal_receipt")
                if isinstance(terminal_receipt, dict):
                    result.update(
                        {
                            "decision": "duplicate_terminal",
                            "terminal": True,
                            "terminal_receipt": dict(terminal_receipt),
                            "reason": (
                                "Duplicate mutating request suppressed; returning the prior "
                                "terminal result without replaying the command."
                            ),
                        }
                    )
                    return result
                result.update(
                    {
                        "decision": "duplicate_uncertain",
                        "terminal": False,
                        "reason": (
                            "Duplicate mutating request suppressed because the original request "
                            "was observed without a known terminal result. Aurora will not replay "
                            "an uncertain write automatically."
                        ),
                    }
                )
                return result

            timestamp, created_at_epoch = _mutation_journal_timestamp()
            disposition = "admitted" if admitted else "rejected"
            event = "mutation_admitted" if admitted else "mutation_rejected"
            record = {
                "schema_version": MUTATION_ADMISSION_SCHEMA_VERSION,
                "event": event,
                "timestamp": timestamp,
                "created_at_epoch": created_at_epoch,
                "session_id": self.session_id,
                "admission_id": admission_id,
                "client_id": normalized_client_id,
                "request_id": normalized_request_id,
                "message_id": normalized_message_id,
                "command_name": normalize_identifier(command_name),
                "command_digest": digest,
                "disposition": disposition,
                "reason": str(reason or "").strip(),
                "replay_attempted": False,
            }
            append_durable_jsonl_record(self.paths["mutation_log"], record)
            self._entries[key] = {
                "admission": dict(record),
                "terminal_receipt": None,
            }
            return {
                **record,
                "decision": disposition,
                "terminal": not admitted,
                "duplicate_suppressed": False,
            }

    def record_terminal(self, receipt: dict[str, Any]) -> bool:
        if not isinstance(receipt, dict) or not bool(receipt.get("terminal", True)):
            return False
        client_id = normalize_identifier(receipt.get("client_id"))
        request_id = normalize_identifier(receipt.get("request_id"))
        if not client_id or not request_id:
            return False
        key = (client_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.get("terminal_receipt") is not None:
                return False
            admission = entry["admission"]
            if receipt.get("mutation_admission_id") != admission.get("admission_id"):
                return False
            receipt_digest = str(receipt.get("command_digest") or "").strip()
            if receipt_digest != admission.get("command_digest"):
                return False
            timestamp, created_at_epoch = _mutation_journal_timestamp()
            record = {
                "schema_version": MUTATION_ADMISSION_SCHEMA_VERSION,
                "event": "mutation_terminal",
                "timestamp": timestamp,
                "created_at_epoch": created_at_epoch,
                "session_id": self.session_id,
                "admission_id": admission.get("admission_id", ""),
                "client_id": client_id,
                "request_id": request_id,
                "message_id": normalize_identifier(receipt.get("message_id")),
                "command_digest": admission.get("command_digest", ""),
                "status": str(receipt.get("status") or "").strip(),
                "receipt": dict(receipt),
                "replay_attempted": False,
            }
            append_durable_jsonl_record(self.paths["mutation_log"], record)
            entry["terminal_receipt"] = dict(receipt)
            return True

    def summary(self) -> dict[str, Any]:
        with self._lock:
            admitted = 0
            rejected = 0
            terminal = 0
            uncertain = 0
            for entry in self._entries.values():
                disposition = entry["admission"].get("disposition", "admitted")
                if disposition == "rejected":
                    rejected += 1
                else:
                    admitted += 1
                if isinstance(entry.get("terminal_receipt"), dict):
                    terminal += 1
                else:
                    uncertain += 1
            return {
                "schema_version": MUTATION_ADMISSION_SCHEMA_VERSION,
                "path": str(self.paths["mutation_log"]),
                "reserved_count": len(self._entries),
                "admitted_count": admitted,
                "rejected_count": rejected,
                "terminal_count": terminal,
                "uncertain_count": uncertain,
                "no_automatic_replay": True,
            }


def build_mutation_decision_receipt(
    decision: dict[str, Any],
    *,
    command: Any,
    source: str,
    message_id: Any,
) -> dict[str, Any]:
    decision_name = str(decision.get("decision") or "").strip()
    request_id = normalize_identifier(decision.get("request_id"))
    client_id = normalize_identifier(decision.get("client_id"))
    current_message_id = normalize_identifier(message_id)
    common = {
        "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
        "receipt_id": f"receipt-{request_id}" if request_id else "",
        "request_id": request_id,
        "message_id": current_message_id,
        "client_id": client_id,
        "command": str(command or "").strip(),
        "source": str(source or "external_operator").strip() or "external_operator",
        "mutation_admission_schema_version": MUTATION_ADMISSION_SCHEMA_VERSION,
        "mutation_admission_id": decision.get("admission_id", ""),
        "command_digest": decision.get("command_digest", ""),
        "admission_status": decision_name,
        "duplicate_suppressed": bool(decision.get("duplicate_suppressed", False)),
        "replay_attempted": False,
        "replayed": False,
        "original_message_id": decision.get("original_message_id", ""),
        "reason": str(decision.get("reason") or "").strip(),
        "is_user": True,
    }
    if decision_name == "duplicate_terminal":
        prior = decision.get("terminal_receipt")
        prior = prior if isinstance(prior, dict) else {}
        for key in (
            "associated_goal",
            "expected_outcome",
            "expanded_commands",
            "executed_commands",
            "failed_commands",
            "command_timings",
            "settings_transaction_receipts",
            "setting_results",
            "lock_results",
            "inference_plan_results",
            "default_profile_results",
            "pending_command_results",
            "history_command_results", "retrieval_results", "goal_file_results", "memory_command_results",
            "pending_id",
            "pending_attempt_id",
            "desktop_results",
            "input_cleanup_results",
            "held_input_results",
            "blocked_commands",
            "cancelled_commands",
            "cancellation_reason",
            "command_generation",
            "total_command_duration_ms",
        ):
            if key in prior:
                common[key] = prior[key]
        common.update(
            {
                "status": str(prior.get("status") or "processed"),
                "outcome_status": str(
                    prior.get("outcome_status") or prior.get("status") or "processed"
                ),
                "delivery_status": "duplicate_suppressed",
                "terminal": True,
                "original_receipt_id": prior.get("receipt_id", ""),
                "original_delivery_status": prior.get("delivery_status", "completed"),
            }
        )
        return common
    if decision_name == "duplicate_uncertain":
        common.update(
            {
                "status": "uncertain",
                "outcome_status": "uncertain",
                "delivery_status": "duplicate_suppressed",
                "terminal": False,
            }
        )
        return common
    if decision_name == "request_conflict":
        common.update(
            {
                "status": "request_conflict",
                "outcome_status": "rejected",
                "delivery_status": "rejected",
                "terminal": True,
                "request_conflict": True,
            }
        )
        return common
    raise ValueError(f"Unsupported mutation admission decision: {decision_name or 'missing'}")


def append_bridge_request(
    root: str | os.PathLike[str],
    text: str,
    **kwargs: Any,
) -> dict[str, Any]:
    record = build_bridge_request(text, **kwargs)
    append_jsonl_record(control_plane_paths(root)["inbox"], record)
    return record


def journal_offsets(root: str | os.PathLike[str]) -> dict[str, int]:
    paths = control_plane_paths(root)
    offsets = {}
    for key in ("bridge_log", "command_log"):
        try:
            offsets[key] = paths[key].stat().st_size
        except OSError:
            offsets[key] = 0
    return offsets


def validate_bridge_request(record: dict[str, Any]) -> str:
    """Return an actionable envelope error; legacy envelopes remain supported."""
    if not isinstance(record.get("text"), str) or not record["text"].strip():
        return "text must be a non-empty string"
    metadata = record.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return "metadata must be an object or null"
    metadata = metadata or {}
    for container in (record, metadata):
        for field in ("request_id", "message_id", "client_id"):
            if field in container and not isinstance(container[field], str):
                return f"{field} must be a string"
    mode = metadata.get("ingest_mode", "normal")
    if not isinstance(mode, str) or mode.strip().lower() not in {"", "normal", "raw"}:
        return "metadata.ingest_mode must be normal or raw"
    return ""


def read_jsonl_batch(
    path: str | os.PathLike[str],
    offset: int = 0,
    *,
    file_identity: str = "",
    discarding_record: bool = False,
    max_records: int = 128,
    max_bytes: int = 4 * 1024 * 1024,
    max_record_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    """Read bounded, newline-committed JSON objects using byte offsets.

    Incomplete tails stay unread, including syntactically valid JSON without its
    newline. Oversized records are discarded in bounded chunks until the next
    newline; persist both the cursor and discarding_record between calls. File
    identity detects replacement, and a shorter file resets a truncated cursor.
    Errors contain offsets/reasons only, never raw request contents.
    """
    if min(max_records, max_record_bytes) < 1 or max_bytes <= max_record_bytes:
        raise ValueError("JSONL limits require positive records and max_bytes > max_record_bytes.")
    start = max(0, int(offset or 0))
    result: dict[str, Any] = {
        "entries": [], "next_offset": start, "file_identity": file_identity,
        "discarding_record": bool(discarding_record), "reset": False,
        "bytes_read": 0, "file_size": start,
    }
    try:
        handle = Path(path).open("rb")
    except FileNotFoundError:
        return result
    with handle:
        stat = os.fstat(handle.fileno())
        identity = f"{stat.st_dev}:{stat.st_ino}"
        if start > stat.st_size or (file_identity and file_identity != identity):
            start = 0
            discarding_record = False
            result["reset"] = True
        result.update(next_offset=start, file_identity=identity, file_size=stat.st_size)
        handle.seek(start)
        while len(result["entries"]) < max_records and result["bytes_read"] < max_bytes:
            line_offset = handle.tell()
            remaining = max_bytes - result["bytes_read"]
            raw = handle.readline(min(max_record_bytes + 1, remaining))
            result["bytes_read"] += len(raw)
            if not raw:
                break
            end = handle.tell()
            if discarding_record:
                discarding_record = not raw.endswith(b"\n")
                result["next_offset"] = end
                continue
            if len(raw) > max_record_bytes:
                result["entries"].append({
                    "record": None, "error": f"record exceeds {max_record_bytes} bytes",
                    "offset": line_offset, "next_offset": end,
                })
                discarding_record = not raw.endswith(b"\n")
                result["next_offset"] = end
                continue
            if not raw.endswith(b"\n"):
                break  # A producer may still be writing this record.
            result["next_offset"] = end
            try:
                line = raw.decode("utf-8-sig" if line_offset == 0 else "utf-8").strip()
                if not line:
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("JSONL record must be an object")
                error = ""
            except (ValueError, UnicodeError) as exc:
                record = None
                error = "invalid UTF-8 or JSON object" if isinstance(exc, (UnicodeError, json.JSONDecodeError)) else str(exc)
            result["entries"].append({
                "record": record, "error": error, "offset": line_offset, "next_offset": end,
            })
        result["discarding_record"] = discarding_record
    return result


def read_jsonl_from(
    path: str | os.PathLike[str],
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Read committed journal rows; large historical receipts remain supported.

    Runtime ingestion uses read_jsonl_batch for explicit work/record limits. This
    compatibility reader has no record-size cap because existing receipt and
    mutation-journal callers require the complete history.
    """
    rows: list[dict[str, Any]] = []
    cursor = max(0, int(offset or 0))
    try:
        handle = Path(path).open("rb")
    except FileNotFoundError:
        return rows, 0
    with handle:
        size = os.fstat(handle.fileno()).st_size
        if cursor > size:
            cursor = 0
        handle.seek(cursor)
        while handle.tell() < size:
            start = handle.tell()
            raw = handle.readline()
            if not raw.endswith(b"\n"):
                break
            cursor = handle.tell()
            try:
                row = json.loads(raw.decode("utf-8-sig" if start == 0 else "utf-8"))
            except (ValueError, UnicodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows, cursor


def read_jsonl_tail(
    path: str | os.PathLike[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists() or limit <= 0:
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, int(limit)))
    with target.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return list(rows)


def receipt_matches_request(
    record: dict[str, Any], request_id: str, *, client_id: str = "",
) -> bool:
    identity = extract_request_identity(record)
    return bool(
        request_id
        and identity["request_id"] == normalize_identifier(request_id)
        and (not client_id or identity["client_id"] == normalize_identifier(client_id))
    )


def wait_for_command_receipt(
    root: str | os.PathLike[str],
    request_id: str,
    *,
    client_id: str = "",
    offsets: dict[str, int] | None = None,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.10,
) -> dict[str, Any]:
    paths = control_plane_paths(root)
    positions = dict(offsets or {})
    command_offset = int(positions.get("command_log", 0) or 0)
    bridge_offset = int(positions.get("bridge_log", 0) or 0)
    normalized_request_id = normalize_identifier(request_id)
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    admitted_record: dict[str, Any] | None = None

    while True:
        command_rows, command_offset = read_jsonl_from(paths["command_log"], command_offset)
        for row in command_rows:
            if row.get("event") != "command_result":
                continue
            if receipt_matches_request(row, normalized_request_id, client_id=client_id):
                result = dict(row)
                result.setdefault("receipt_schema_version", COMMAND_RECEIPT_SCHEMA_VERSION)
                result.setdefault("request_id", normalized_request_id)
                result.setdefault("terminal", True)
                result.setdefault("delivery_status", "completed")
                result.setdefault("outcome_status", result.get("status", "processed"))
                return result

        bridge_rows, bridge_offset = read_jsonl_from(paths["bridge_log"], bridge_offset)
        for row in bridge_rows:
            if not receipt_matches_request(row, normalized_request_id, client_id=client_id):
                continue
            event = str(row.get("event") or "").strip()
            if event == "message_rejected":
                return {
                    **row,
                    "event": "command_result",
                    "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
                    "request_id": normalized_request_id,
                    "status": "rejected",
                    "outcome_status": "rejected",
                    "delivery_status": "rejected",
                    "terminal": True,
                }
            if event == "message_ingested":
                admitted_record = row
                if not bool(row.get("dispatched_as_command", False)):
                    return {
                        **row,
                        "event": "command_result",
                        "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
                        "request_id": normalized_request_id,
                        "status": "routed_as_input",
                        "outcome_status": "not_dispatched",
                        "delivery_status": "delivered",
                        "terminal": True,
                    }

        if time.monotonic() >= deadline:
            if admitted_record is not None:
                return {
                    **admitted_record,
                    "event": "command_result",
                    "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
                    "request_id": normalized_request_id,
                    "status": "uncertain",
                    "outcome_status": "uncertain",
                    "delivery_status": "delivered",
                    "terminal": False,
                    "reason": "Command was admitted by the bridge but no correlated terminal result arrived before timeout.",
                }
            return {
                "event": "command_result",
                "receipt_schema_version": COMMAND_RECEIPT_SCHEMA_VERSION,
                "request_id": normalized_request_id,
                "status": "queued",
                "client_id": normalize_identifier(client_id),
                "outcome_status": "not_observed",
                "delivery_status": "queued",
                "terminal": False,
                "reason": "No bridge admission or terminal result was observed before timeout.",
            }
        time.sleep(max(0.02, float(poll_interval_seconds)))


def collect_command_receipts(
    root: str | os.PathLike[str],
    *,
    limit: int = 20,
    request_id: str = "",
    client_id: str = "",
) -> list[dict[str, Any]]:
    command_log_path = control_plane_paths(root)["command_log"]
    if request_id or client_id:
        rows, _ = read_jsonl_from(command_log_path, 0)
    else:
        rows = read_jsonl_tail(command_log_path, max(200, limit * 10))
    receipts = []
    for row in rows:
        if row.get("event") != "command_result":
            continue
        if request_id and not receipt_matches_request(row, request_id, client_id=client_id):
            continue
        if client_id and extract_request_identity(row)["client_id"] != normalize_identifier(client_id):
            continue
        receipts.append(row)
    return receipts[-max(1, int(limit)) :]


def read_json_file(path: str | os.PathLike[str], default: Any = None) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def read_pid(path: str | os.PathLike[str]) -> int:
    try:
        return max(0, int(Path(path).read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            int(pid),
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return int(exit_code.value) == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_operator_status(
    root: str | os.PathLike[str],
    *,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = control_plane_paths(root)
    state = state_snapshot if isinstance(state_snapshot, dict) else read_json_file(paths["state"], {})
    if not isinstance(state, dict):
        state = {}
    runtime_pid = read_pid(paths["runtime_pid"])
    panel_pid = read_pid(paths["control_panel_pid"])
    try:
        state_age_seconds = max(0.0, time.time() - paths["state"].stat().st_mtime)
    except OSError:
        state_age_seconds = None
    return {
        "schema_version": "aurora_operator_status_v1",
        "root": str(paths["root"]),
        "observed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "runtime": {
            "pid": runtime_pid,
            "running": process_is_running(runtime_pid),
        },
        "control_panel": {
            "pid": panel_pid,
            "running": process_is_running(panel_pid),
        },
        "state": {
            "exists": paths["state"].exists(),
            "age_seconds": round(state_age_seconds, 2) if state_age_seconds is not None else None,
            "timestamp": state.get("timestamp", ""),
            "session_id": state.get("session_id", ""),
        },
        "modes": state.get("modes", {}) if isinstance(state.get("modes"), dict) else {},
        "work": state.get("work", {}) if isinstance(state.get("work"), dict) else {},
        "scheduler": state.get("scheduler", {}) if isinstance(state.get("scheduler"), dict) else {},
        "monitors": state.get("monitors", {}) if isinstance(state.get("monitors"), dict) else {},
        "queue_bridge": state.get("queue_bridge", {}) if isinstance(state.get("queue_bridge"), dict) else {},
        "mutation_admission": (
            state.get("mutation_admission", {})
            if isinstance(state.get("mutation_admission"), dict)
            else {}
        ),
        "runtime_summary": str(state.get("runtime_summary") or ""),
    }


def _dashboard_command_name(command: Any) -> str:
    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)", str(command or ""))
    return match.group(1).upper() if match else "UNKNOWN"


def _dashboard_receipt_event(record: dict[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or record.get("outcome_status") or "unknown").strip().lower()
    detail_by_status = {
        "uncertain": "Outcome uncertain; automatic replay is disabled.",
        "request_conflict": "Request identity was reused with a different payload.",
        "rejected": "Request was rejected.",
        "routed_as_input": "Input was not dispatched as a command.",
        "timeout": "No terminal result was observed before timeout.",
        "cancelled": "Batch cancelled; the full receipt records any completed steps.",
    }
    identity = extract_request_identity(record)
    return {
        "schema_version": OPERATOR_DASHBOARD_EVENT_SCHEMA_VERSION,
        "kind": "command_receipt",
        "timestamp": str(record.get("timestamp") or ""),
        "request_id": identity["request_id"],
        "client_id": identity["client_id"],
        "command_name": _dashboard_command_name(record.get("command")),
        "status": status or "unknown",
        "delivery_status": str(record.get("delivery_status") or "unknown").strip().lower(),
        "terminal": bool(record.get("terminal", True)),
        "duplicate_suppressed": bool(record.get("duplicate_suppressed", False)),
        "detail": detail_by_status.get(status, ""),
    }


def build_operator_dashboard(
    root: str | os.PathLike[str],
    *,
    event_limit: int = 8,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from aurora_settings_registry import build_settings_snapshot

    paths = control_plane_paths(root)
    state = state_snapshot if isinstance(state_snapshot, dict) else read_json_file(paths["state"], {})
    if not isinstance(state, dict):
        state = {}
    status = build_operator_status(root, state_snapshot=state)
    runtime_active = bool((status.get("runtime", {}) or {}).get("running", False))
    state_status = status.get("state", {}) or {}
    settings_snapshot = build_settings_snapshot(
        state,
        runtime_active=runtime_active,
        state_age_seconds=state_status.get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )
    setting_rows = [
        {
            "key": str(row.get("key") or ""),
            "value": row.get("value"),
            "value_status": str(row.get("value_status") or "unknown"),
            "effective": bool(row.get("effective", False)),
            "locked": bool(row.get("locked", False)),
            "scope": str(row.get("scope") or "runtime_session"),
            "maturity": str(row.get("maturity") or ""),
        }
        for row in settings_snapshot.get("settings", []) or []
        if isinstance(row, dict)
    ]

    normalized_event_limit = max(0, min(50, int(event_limit or 0)))
    receipt_rows = (
        collect_command_receipts(root, limit=normalized_event_limit)
        if normalized_event_limit
        else []
    )
    events = [_dashboard_receipt_event(row) for row in receipt_rows]

    queue_bridge = status.get("queue_bridge", {}) or {}
    scheduler = status.get("scheduler", {}) or {}
    monitors = status.get("monitors", {}) or {}
    state_age = state_status.get("age_seconds")
    if not state_status.get("exists", False):
        freshness = "missing"
    elif state_age is not None and float(state_age) <= 10.0:
        freshness = "fresh"
    else:
        freshness = "stale"

    return {
        "schema_version": OPERATOR_DASHBOARD_SCHEMA_VERSION,
        "observed_at": status.get("observed_at", ""),
        "root": status.get("root", str(paths["root"])),
        "summary": {
            "runtime_status": "running" if runtime_active else "stopped",
            "control_panel_status": (
                "running"
                if bool((status.get("control_panel", {}) or {}).get("running", False))
                else "stopped"
            ),
            "state_freshness": freshness,
            "monitor_status": str(monitors.get("overall_status") or "unknown"),
            "automatic_replay": False,
            "settings_scope": "runtime_session",
            "persistent_settings_enabled": False,
        },
        "runtime": dict(status.get("runtime", {}) or {}),
        "control_panel": dict(status.get("control_panel", {}) or {}),
        "state": dict(state_status),
        "modes": dict(status.get("modes", {}) or {}),
        "models": dict(state.get("models", {}) or {}),
        "scheduler": {
            key: scheduler.get(key)
            for key in (
                "profile",
                "mode",
                "heartbeat_seconds",
                "min_gap_seconds",
                "capture_wake_enabled",
                "capture_wake_debounce_seconds",
                "post_action_settle_seconds",
                "last_wake_reason",
                "pending_reasons",
                "demand_capture_enabled",
                "demand_capture_pending",
                "demand_capture_reason",
            )
        },
        "monitor": {
            "overall_status": str(monitors.get("overall_status") or "unknown"),
            "summary": str(monitors.get("summary") or ""),
            "status_counts": dict(monitors.get("status_counts", {}) or {}),
        },
        "queue_bridge": {
            key: queue_bridge.get(key)
            for key in (
                "pending_count",
                "due_pending_count",
                "oldest_pending_age_seconds",
                "stale_pending_count",
                "pending_queue_mode",
                "bridge_caught_up",
                "command_result_caught_up",
                "latest_bridge_event",
                "latest_bridge_request_id",
                "latest_external_command_result_status",
                "latest_external_command_result_request_id",
                "inbox_size_bytes",
                "bridge_log_size_bytes",
                "command_log_size_bytes",
            )
        },
        "mutation_admission": dict(status.get("mutation_admission", {}) or {}),
        "settings": {
            "schema_version": settings_snapshot.get("schema_version", ""),
            "version_schema_version": settings_snapshot.get("version_schema_version", ""),
            "version": settings_snapshot.get("version", ""),
            "runtime_active": runtime_active,
            "state_age_seconds": settings_snapshot.get("state_age_seconds"),
            "count": len(setting_rows),
            "status_counts": dict(settings_snapshot.get("status_counts", {}) or {}),
            "locked_count": sum(1 for row in setting_rows if row["locked"]),
            "effective_count": sum(1 for row in setting_rows if row["effective"]),
            "writable_count": sum(
                1 for row in setting_rows if not row["locked"] and row["effective"]
            ),
            "scope": "runtime_session",
            "persistent_scopes_enabled": False,
            "rows": setting_rows,
        },
        "events": {
            "schema_version": OPERATOR_DASHBOARD_EVENT_SCHEMA_VERSION,
            "limit": normalized_event_limit,
            "count": len(events),
            "rows": events,
        },
        "runtime_summary": str(status.get("runtime_summary") or ""),
    }


def _dashboard_short(value: Any, limit: int = 48) -> str:
    text = str(value or "-").replace("\r", " ").replace("\n", " ").strip() or "-"
    return text if len(text) <= limit else text[: max(1, limit - 3)] + "..."


def _dashboard_age(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        seconds = max(0.0, float(value))
    except (TypeError, ValueError):
        return "unknown"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_operator_dashboard(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary", {}) or {}
    runtime = snapshot.get("runtime", {}) or {}
    panel = snapshot.get("control_panel", {}) or {}
    state = snapshot.get("state", {}) or {}
    modes = snapshot.get("modes", {}) or {}
    models = snapshot.get("models", {}) or {}
    scheduler = snapshot.get("scheduler", {}) or {}
    monitor = snapshot.get("monitor", {}) or {}
    queue_bridge = snapshot.get("queue_bridge", {}) or {}
    mutation = snapshot.get("mutation_admission", {}) or {}
    settings = snapshot.get("settings", {}) or {}
    events = (snapshot.get("events", {}) or {}).get("rows", []) or []

    pending_reasons = ",".join(str(item) for item in scheduler.get("pending_reasons", []) or [])
    setting_counts = ", ".join(
        f"{key}={value}" for key, value in sorted((settings.get("status_counts", {}) or {}).items())
    ) or "none"
    lines = [
        f"Aurora Operator Dashboard | {snapshot.get('observed_at') or '-'}",
        (
            f"Runtime {str(summary.get('runtime_status') or 'unknown').upper()} "
            f"(pid {runtime.get('pid') or '-'}) | Control Panel "
            f"{str(summary.get('control_panel_status') or 'unknown').upper()} "
            f"(pid {panel.get('pid') or '-'})"
        ),
        (
            f"State {str(summary.get('state_freshness') or 'unknown').upper()} | "
            f"timestamp {state.get('timestamp') or '-'} | age {_dashboard_age(state.get('age_seconds'))} | "
            f"session {state.get('session_id') or '-'}"
        ),
        (
            f"Monitor {monitor.get('overall_status') or 'unknown'} | "
            f"{_dashboard_short(monitor.get('summary'), 96)}"
        ),
        "",
        "Runtime posture",
        (
            f"  live={'on' if modes.get('live') else 'off'} | execution={modes.get('execution') or '-'} | "
            f"action={modes.get('action') or '-'} | auth={modes.get('auth') or '-'} | "
            f"game={modes.get('game_profile') or '-'}"
        ),
        (
            f"  models={models.get('text') or '-'}/{models.get('vision') or '-'}/{models.get('reasoning') or '-'} | "
            f"effort={models.get('reasoning_effort') or '-'} | verbosity={models.get('verbosity') or '-'}"
        ),
        (
            f"  scheduler={scheduler.get('profile') or '-'} ({scheduler.get('mode') or '-'}) | "
            f"heartbeat={scheduler.get('heartbeat_seconds') or '-'}s | "
            f"pending={pending_reasons or 'none'} | wake={scheduler.get('last_wake_reason') or '-'}"
        ),
        "",
        "Control plane",
        (
            f"  queue pending={queue_bridge.get('pending_count') or 0} | due={queue_bridge.get('due_pending_count') or 0} | "
            f"bridge_caught_up={bool(queue_bridge.get('bridge_caught_up', True))} | "
            f"results_caught_up={bool(queue_bridge.get('command_result_caught_up', True))}"
        ),
        (
            f"  mutations reserved={mutation.get('reserved_count') or 0} | "
            f"terminal={mutation.get('terminal_count') or 0} | uncertain={mutation.get('uncertain_count') or 0} | "
            "automatic_replay=off"
        ),
        (
            f"  settings version={_dashboard_short(settings.get('version'), 30)} | count={settings.get('count') or 0} | "
            f"effective={settings.get('effective_count') or 0} | locked={settings.get('locked_count') or 0} | "
            f"statuses {setting_counts} | scope=runtime_session"
        ),
        "",
        f"Recent receipts ({len(events)})",
    ]
    if not events:
        lines.append("  none observed")
    for event in events:
        lifecycle = "terminal" if event.get("terminal", False) else "nonterminal"
        duplicate = " | duplicate_suppressed" if event.get("duplicate_suppressed", False) else ""
        lines.append(
            f"  {event.get('timestamp') or '-'} | {event.get('command_name') or 'UNKNOWN'} | "
            f"{event.get('status') or 'unknown'}/{event.get('delivery_status') or 'unknown'} | "
            f"{lifecycle}{duplicate} | request {_dashboard_short(event.get('request_id'), 42)}"
        )
        if event.get("detail"):
            lines.append(f"    {event['detail']}")
    return "\n".join(lines)
