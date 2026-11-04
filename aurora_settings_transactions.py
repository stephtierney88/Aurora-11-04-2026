from __future__ import annotations

import base64
import datetime
import json
import math
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from aurora_settings_registry import (
    InvalidSettingKeyError,
    InvalidSettingValueError,
    SettingRegistryError,
    UnknownSettingKeyError,
    build_setting_readback,
    build_settings_version,
    coerce_setting_value,
    resolve_setting_definition,
)


SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION = "aurora_settings_transaction_request_v1"
SETTINGS_TRANSACTION_PLAN_SCHEMA_VERSION = "aurora_settings_transaction_plan_v1"
SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION = "aurora_settings_transaction_receipt_v1"
SETTINGS_ROLLBACK_HANDLE_SCHEMA_VERSION = "aurora_settings_rollback_handle_v1"
SETTINGS_TRANSACTION_WIRE_COMMANDS = {
    "preview": "PREVIEW_SETTINGS_TRANSACTION",
    "apply": "APPLY_SETTINGS_TRANSACTION",
    "rollback": "ROLLBACK_SETTINGS_TRANSACTION",
}
MAX_TRANSACTION_TOKEN_BYTES = 64 * 1024

_COMMAND_TEMPLATE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)\(\{value\}\)$")


class SettingsTransactionError(ValueError):
    pass


class InvalidSettingsTransactionRequestError(SettingsTransactionError):
    pass


class InvalidSettingsTransactionTokenError(SettingsTransactionError):
    pass


def _utc_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_operation(value: Any) -> str:
    operation = str(value or "").strip().lower()
    if operation not in SETTINGS_TRANSACTION_WIRE_COMMANDS:
        raise InvalidSettingsTransactionRequestError(
            "Settings transaction operation must be preview, apply, or rollback."
        )
    return operation


def _normalize_scope(value: Any) -> str:
    scope = str(value or "runtime_session").strip().lower()
    if scope != "runtime_session":
        raise InvalidSettingsTransactionRequestError(
            "Only runtime_session settings transactions are enabled."
        )
    return scope


def _normalize_change_records(changes: Any) -> list[dict[str, Any]]:
    if isinstance(changes, Mapping):
        items: Sequence[Any] = [
            {"key": key, "value": value}
            for key, value in changes.items()
        ]
    elif isinstance(changes, Sequence) and not isinstance(changes, (str, bytes, bytearray)):
        items = changes
    else:
        raise InvalidSettingsTransactionRequestError(
            "Settings changes must be a mapping or a sequence of key/value records."
        )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, Mapping):
            if "key" not in item or "value" not in item:
                raise InvalidSettingsTransactionRequestError(
                    f"Settings change {index + 1} requires key and value fields."
                )
            normalized.append({"key": item.get("key"), "value": item.get("value")})
            continue
        if (
            isinstance(item, Sequence)
            and not isinstance(item, (str, bytes, bytearray))
            and len(item) == 2
        ):
            normalized.append({"key": item[0], "value": item[1]})
            continue
        raise InvalidSettingsTransactionRequestError(
            f"Settings change {index + 1} must be a key/value record."
        )
    return normalized


def build_settings_transaction_request(
    operation: str,
    *,
    changes: Any = (),
    expected_version: str,
    scope: str = "runtime_session",
    rollback_handle: str = "",
    transaction_id: str = "",
) -> dict[str, Any]:
    normalized_operation = _normalize_operation(operation)
    normalized_scope = _normalize_scope(scope)
    normalized_expected_version = str(expected_version or "").strip()
    if not normalized_expected_version:
        raise InvalidSettingsTransactionRequestError(
            "Settings transactions require expected_version."
        )

    normalized_rollback_handle = str(rollback_handle or "").strip()
    normalized_changes = _normalize_change_records(changes)
    if normalized_operation == "rollback":
        if not normalized_rollback_handle:
            raise InvalidSettingsTransactionRequestError(
                "Rollback transactions require a rollback handle."
            )
        if normalized_changes:
            raise InvalidSettingsTransactionRequestError(
                "Rollback transactions do not accept direct setting changes."
            )
    elif not normalized_changes:
        raise InvalidSettingsTransactionRequestError(
            "Preview and apply transactions require at least one setting change."
        )

    return {
        "schema_version": SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION,
        "transaction_id": str(transaction_id or f"settings-tx-{uuid.uuid4().hex}").strip(),
        "operation": normalized_operation,
        "scope": normalized_scope,
        "expected_version": normalized_expected_version,
        "changes": normalized_changes,
        "rollback_handle": normalized_rollback_handle,
        "created_at": _utc_timestamp(),
    }


def encode_settings_transaction_request(request: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(request),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_TRANSACTION_TOKEN_BYTES:
        raise InvalidSettingsTransactionTokenError("Settings transaction request is too large.")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidSettingsTransactionTokenError(f"Duplicate transaction JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise InvalidSettingsTransactionTokenError(f"Non-finite transaction JSON value: {value}")


def _finite_json_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        _reject_json_constant(value)
    return parsed


def decode_settings_transaction_request(token: Any) -> dict[str, Any]:
    normalized = str(token or "").strip()
    if not normalized:
        raise InvalidSettingsTransactionTokenError("Settings transaction token is required.")
    if len(normalized) > MAX_TRANSACTION_TOKEN_BYTES * 2:
        raise InvalidSettingsTransactionTokenError("Settings transaction token is too large.")
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", normalized):
            raise InvalidSettingsTransactionTokenError("Settings transaction token is not URL-safe base64.")
        padding = "=" * (-len(normalized) % 4)
        payload = base64.b64decode((normalized + padding).encode("ascii"), altchars=b"-_", validate=True)
        if len(payload) > MAX_TRANSACTION_TOKEN_BYTES:
            raise InvalidSettingsTransactionTokenError("Settings transaction request is too large.")
        request = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object,
                             parse_constant=_reject_json_constant, parse_float=_finite_json_float)
    except InvalidSettingsTransactionTokenError:
        raise
    except Exception as error:
        raise InvalidSettingsTransactionTokenError(
            "Settings transaction token is not valid URL-safe JSON."
        ) from error
    if not isinstance(request, dict):
        raise InvalidSettingsTransactionTokenError("Settings transaction payload must be an object.")
    if request.get("schema_version") != SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION:
        raise InvalidSettingsTransactionTokenError(
            "Unsupported settings transaction request schema."
        )
    return request


def build_settings_transaction_command(request: Mapping[str, Any]) -> str:
    operation = _normalize_operation(request.get("operation"))
    return f"{SETTINGS_TRANSACTION_WIRE_COMMANDS[operation]}({encode_settings_transaction_request(request)})"


def _rejection(code: str, message: str, *, key: str = "", index: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if key:
        payload["key"] = key
    if index is not None:
        payload["index"] = index
    return payload


def setting_values_equal(key: Any, left: Any, right: Any) -> bool:
    try:
        return coerce_setting_value(key, left, for_readback=True) == coerce_setting_value(
            key,
            right,
            for_readback=True,
        )
    except (SettingRegistryError, TypeError, ValueError):
        return left == right


def inspect_settings_transaction_request(request: Mapping[str, Any], *, expected_operation=None) -> dict[str, Any]:
    """Validate wire shape and registry values without observing or changing runtime state."""
    rejections: list[dict[str, Any]] = []
    transaction_id = str(request.get("transaction_id") or "").strip()
    operation = str(request.get("operation") or "").strip().lower()
    scope = str(request.get("scope") or "").strip().lower()
    expected_version = str(request.get("expected_version") or "").strip()

    if request.get("schema_version") != SETTINGS_TRANSACTION_REQUEST_SCHEMA_VERSION:
        rejections.append(_rejection("unsupported_schema", "Unsupported settings transaction request schema."))
    if operation not in SETTINGS_TRANSACTION_WIRE_COMMANDS:
        rejections.append(_rejection("invalid_operation", "Operation must be preview, apply, or rollback."))
    if expected_operation is not None and operation != expected_operation:
        rejections.append(_rejection("operation_mismatch", f"Transaction operation {operation or '-'} does not match {expected_operation}."))
    for field in ("transaction_id", "operation", "scope", "expected_version", "rollback_handle"):
        if field in request and not isinstance(request[field], str):
            rejections.append(_rejection("invalid_field_type", f"{field} must be a string."))
    if scope != "runtime_session":
        rejections.append(_rejection("scope_not_enabled", "Only runtime_session settings transactions are enabled."))
    if not expected_version:
        rejections.append(_rejection("expected_version_required", "expected_version is required."))
    raw_changes = request.get("changes")
    if operation == "rollback":
        if not str(request.get("rollback_handle") or "").strip():
            rejections.append(_rejection("rollback_handle_required", "Rollback requires a rollback handle."))
        if raw_changes is not None and raw_changes != []:
            rejections.append(_rejection("unexpected_changes", "Rollback does not accept direct setting changes."))
        raw_changes = []
    elif not isinstance(raw_changes, list) or not raw_changes:
        rejections.append(_rejection("changes_required", "At least one settings change is required."))
        raw_changes = []
    if operation in {"preview", "apply"} and request.get("rollback_handle"):
        rejections.append(_rejection("unexpected_rollback_handle", "Preview/apply does not accept a rollback handle."))

    planned_changes: list[dict[str, Any]] = []
    seen_keys: dict[str, int] = {}
    for index, item in enumerate(raw_changes):
        display_index = index + 1
        if not isinstance(item, Mapping) or "key" not in item or "value" not in item:
            rejections.append(
                _rejection(
                    "invalid_change_shape",
                    "Each settings change requires key and value fields.",
                    index=display_index,
                )
            )
            continue
        input_key = item.get("key")
        try:
            definition = resolve_setting_definition(input_key)
        except InvalidSettingKeyError as error:
            rejections.append(_rejection("invalid_key", str(error), index=display_index))
            continue
        except UnknownSettingKeyError as error:
            rejections.append(_rejection("unknown_key", str(error), index=display_index))
            continue

        if definition.key in seen_keys:
            rejections.append(
                _rejection(
                    "duplicate_key",
                    f"{definition.key} appears more than once after alias resolution.",
                    key=definition.key,
                    index=display_index,
                )
            )
            continue
        seen_keys[definition.key] = display_index

        try:
            value = coerce_setting_value(definition.key, item.get("value"))
        except InvalidSettingValueError as error:
            rejections.append(
                _rejection("invalid_value", str(error), key=definition.key, index=display_index)
            )
            continue

        if scope not in definition.allowed_scopes:
            rejections.append(
                _rejection(
                    "scope_not_allowed",
                    f"{definition.key} does not allow scope {scope}.",
                    key=definition.key,
                    index=display_index,
                )
            )
        planned_changes.append(
            {
                "index": display_index,
                "input_key": str(input_key),
                "key": definition.key,
                "requested_value": item.get("value"),
                "value": value,
                "value_type": definition.value_type,
                "lock_key": definition.lock_key,
                "apply_timing": definition.apply_timing,
                "risk_class": definition.risk_class,
                "scope": scope,
            }
        )

    scheduler_leaf_keys = {
        "scheduler.mode",
        "scheduler.heartbeat_seconds",
        "scheduler.min_gap_seconds",
        "scheduler.capture_wake_enabled",
        "scheduler.capture_wake_debounce_seconds",
        "scheduler.post_action_settle_seconds",
    }
    planned_keys = {row["key"] for row in planned_changes}
    if "scheduler.profile" in planned_keys and planned_keys.intersection(scheduler_leaf_keys):
        rejections.append(
            _rejection(
                "conflicting_changes",
                "scheduler.profile cannot be combined with manual scheduler mode, wake, or timing changes in one transaction.",
                key="scheduler.profile",
            )
        )

    return {"transaction_id": transaction_id, "operation": operation, "scope": scope,
            "expected_version": expected_version, "changes": planned_changes, "rejections": rejections}


def parse_settings_transaction_command(name, args) -> dict[str, Any]:
    """Admit only a complete, structurally valid transaction; runtime checks stay fresh."""
    operations = {command: operation for operation, command in SETTINGS_TRANSACTION_WIRE_COMMANDS.items()}
    operation = operations.get(name.upper())
    if operation is None or len(args) != 1:
        raise InvalidSettingsTransactionRequestError(f"{name.upper()} requires one encoded request token.")
    request = decode_settings_transaction_request(args[0])
    inspected = inspect_settings_transaction_request(request, expected_operation=operation)
    if inspected["rejections"]:
        raise InvalidSettingsTransactionRequestError("; ".join(row["message"] for row in inspected["rejections"]))
    return request


def plan_settings_transaction(request: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    inspected = inspect_settings_transaction_request(request)
    rejections = inspected["rejections"]
    operation, scope = inspected["operation"], inspected["scope"]
    expected_version = inspected["expected_version"]
    current_version = build_settings_version(state)
    if operation not in {"preview", "apply"}:
        rejections.append(_rejection("invalid_operation", "Planner accepts preview or apply operations only."))
    if expected_version and expected_version != current_version:
        rejections.append(_rejection("version_conflict",
            f"Expected settings version {expected_version}, but current version is {current_version}."))
    planned_changes = inspected["changes"]
    for row in planned_changes:
        key = row["key"]
        readback = build_setting_readback(key, state, runtime_active=True, state_age_seconds=0.0)
        if not readback.get("effective"):
            rejections.append(_rejection("current_value_unavailable",
                f"Cannot safely transact {key}: current runtime value is {readback.get('value_status')}.",
                key=key, index=row["index"]))
        if readback.get("locked"):
            rejections.append(_rejection("setting_locked", f"{key} is locked by runtime lock {row['lock_key']}.",
                                         key=key, index=row["index"]))
        row.update(before_value=readback.get("value"), changed=not setting_values_equal(key, readback.get("value"), row["value"]))
    return {
        "schema_version": SETTINGS_TRANSACTION_PLAN_SCHEMA_VERSION,
        "request_schema_version": request.get("schema_version"),
        "transaction_id": inspected["transaction_id"],
        "operation": operation,
        "scope": scope,
        "expected_version": expected_version,
        "current_version": current_version,
        "valid": not rejections,
        "change_count": len(planned_changes),
        "changed_count": sum(1 for row in planned_changes if row.get("changed")),
        "changes": planned_changes,
        "rejections": rejections,
    }


def build_setting_command_invocation(key: Any, value: Any) -> tuple[str, list[str], str]:
    definition = resolve_setting_definition(key)
    coerced = coerce_setting_value(definition.key, value)
    match = _COMMAND_TEMPLATE_PATTERN.fullmatch(definition.command)
    if match is None:
        raise SettingsTransactionError(
            f"Unsupported settings command template for {definition.key}: {definition.command}"
        )
    if isinstance(coerced, bool):
        argument = "on" if coerced else "off"
    elif isinstance(coerced, float):
        argument = repr(coerced)
    else:
        argument = str(coerced)
    command_name = match.group(1)
    return command_name, [argument], f"{command_name}({argument})"


def extract_settings_transaction_receipt(command_receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = command_receipt.get("settings_transaction_receipts")
    if not isinstance(rows, list) or not rows:
        return None
    receipt = rows[-1]
    return dict(receipt) if isinstance(receipt, Mapping) else None
