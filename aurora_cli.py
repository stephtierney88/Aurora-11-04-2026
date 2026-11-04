from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Any, Callable

from aurora_command_catalog import load_generated_catalog

from aurora_control_plane import (
    append_bridge_request,
    append_durable_jsonl_record,
    build_operator_dashboard,
    build_operator_status,
    collect_command_receipts,
    control_plane_paths,
    format_operator_dashboard,
    journal_offsets,
    read_json_file,
    read_jsonl_from,
    wait_for_command_receipt,
)
from aurora_settings_registry import (
    build_setting_readback,
    build_settings_snapshot,
    describe_setting_definition,
    list_setting_definitions,
    registry_summary,
    resolve_setting_definition,
)
from aurora_settings_transactions import (
    build_settings_transaction_command,
    build_settings_transaction_request,
    extract_settings_transaction_receipt,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_SECONDS = 15.0
SHELL_HISTORY_SCHEMA_VERSION = "aurora_cli_history_v1"
SHELL_COMPLETION_SCHEMA_VERSION = "aurora_cli_completion_v1"
SHELL_HISTORY_MAX_LINE_CHARS = 4096
SHELL_HISTORY_DEFAULT_LIMIT = 200
SHELL_HISTORY_NAVIGATION_LIMIT = 500
SHELL_COMPLETION_DISPLAY_LIMIT = 60
SHELL_BUILTINS = (
    "help",
    "status",
    "dashboard",
    "doctor",
    "receipts",
    "capture",
    "command",
    "send",
    "commands",
    "settings",
    "history",
    "complete",
    "exit",
    "quit",
)
SHELL_SETTINGS_ACTIONS = (
    "list",
    "get",
    "describe",
    "version",
    "preview",
    "apply",
    "rollback",
)
SHELL_SENSITIVE_PATTERN = re.compile(
    r"(?i)(passcode|password|api[_-]?key|secret|\b(?:[a-z0-9]+[_-])?token\b|bearer\s+|authorization\s*[:=])"
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def _format_age(value: Any) -> str:
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


def load_command_catalog(root: Path) -> list[dict[str, Any]]:
    path = control_plane_paths(root)["command_index"]
    catalog_path = path.with_name("commands.json")
    if catalog_path.exists():
        return load_generated_catalog(catalog_path, root=root)
    if not path.exists():
        raise ValueError(
            "Aurora command index is unavailable. Run regenerate_aurora_skill_refs.ps1 -Force."
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = {"command", "signature", "category", "handler", "summary"}
        if not expected.issubset(set(reader.fieldnames or ())):
            raise ValueError(f"Aurora command index has an unexpected schema: {path}")
        rows = []
        seen = set()
        for raw_row in reader:
            row = {key: str(raw_row.get(key) or "").strip() for key in expected}
            command = row["command"].upper()
            if not command or command in seen:
                continue
            row["command"] = command
            rows.append(row)
            seen.add(command)
    return rows


def filter_command_catalog(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
    category: str = "",
    limit: int = 50,
    detail: bool = False,
) -> list[dict[str, Any]]:
    normalized_query = str(query or "").strip().lower()
    normalized_category = str(category or "").strip().lower()
    if normalized_category:
        categories = sorted({row["category"] for row in rows if row.get("category")})
        category_lookup = {value.lower(): value for value in categories}
        if normalized_category not in category_lookup:
            raise ValueError(
                "Unknown command category. Expected one of: " + ", ".join(categories)
            )
    filtered = []
    for row in rows:
        if normalized_category and row.get("category", "").lower() != normalized_category:
            continue
        haystack = " ".join(
            row.get(key, "") for key in ("command", "signature", "category", "summary")
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        result = dict(row)
        if not detail:
            contract = result.pop("contract", None)
            if contract:
                result["parameter_validation"] = contract["parameter_validation"]
            result.pop("source", None)
        filtered.append(result)
    if normalized_query:
        filtered.sort(key=lambda row: row["command"].lower() != normalized_query)
    return filtered[: max(1, min(500, int(limit or 50)))]


def commands_command(args: argparse.Namespace) -> int:
    rows = load_command_catalog(args.root)
    index_path = control_plane_paths(args.root)["command_index"]
    catalog_path = index_path.with_name("commands.json")
    filtered = filter_command_catalog(
        rows,
        query=args.query or "",
        category=args.category or "",
        limit=args.limit,
        detail=getattr(args, "detail", False),
    )
    payload = {
        "schema_version": "aurora_cli_command_discovery_v1",
        "path": str(catalog_path if catalog_path.exists() else index_path),
        "query": str(args.query or ""),
        "category": str(args.category or ""),
        "count": len(filtered),
        "commands": filtered,
    }
    if args.json:
        _print_json(payload)
        return 0
    if not filtered:
        print("No matching Aurora commands found.")
        return 1
    for row in filtered:
        print(f"{row['signature'] or row['command']} | {row['category']} | {row['summary']}")
    return 0


def _normalize_shell_history_line(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def shell_history_is_sensitive(command_line: Any) -> bool:
    normalized = _normalize_shell_history_line(command_line)
    return bool(
        not normalized
        or len(normalized) > SHELL_HISTORY_MAX_LINE_CHARS
        or SHELL_SENSITIVE_PATTERN.search(normalized)
    )


def append_shell_history(root: Path, command_line: Any, exit_code: int) -> bool:
    normalized = _normalize_shell_history_line(command_line)
    if shell_history_is_sensitive(normalized):
        return False
    now = time.time()
    append_durable_jsonl_record(
        control_plane_paths(root)["cli_history"],
        {
            "schema_version": SHELL_HISTORY_SCHEMA_VERSION,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_epoch": round(now, 6),
            "source": "aurora_shell",
            "command": normalized,
            "exit_code": int(exit_code),
        },
    )
    return True


def read_shell_history(
    root: Path,
    *,
    limit: int = SHELL_HISTORY_DEFAULT_LIMIT,
    query: str = "",
) -> list[dict[str, Any]]:
    rows, _ = read_jsonl_from(control_plane_paths(root)["cli_history"], 0)
    normalized_query = str(query or "").strip().lower()
    filtered = []
    for row in rows:
        if row.get("schema_version") != SHELL_HISTORY_SCHEMA_VERSION:
            continue
        command = _normalize_shell_history_line(row.get("command"))
        if not command or shell_history_is_sensitive(command):
            continue
        if normalized_query and normalized_query not in command.lower():
            continue
        filtered.append(
            {
                "timestamp": str(row.get("timestamp") or ""),
                "created_at_epoch": row.get("created_at_epoch"),
                "source": str(row.get("source") or "aurora_shell"),
                "command": command,
                "exit_code": int(row.get("exit_code", 0) or 0),
            }
        )
    return filtered[-max(1, min(5000, int(limit or SHELL_HISTORY_DEFAULT_LIMIT))) :]


def clear_shell_history(root: Path) -> None:
    path = control_plane_paths(root)["cli_history"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text("", encoding="utf-8")
    os.replace(temporary, path)


def history_command(args: argparse.Namespace) -> int:
    if args.history_action == "clear":
        if not args.yes:
            raise ValueError("Refusing to clear shell history without history clear --yes.")
        clear_shell_history(args.root)
        print(f"Cleared Aurora shell history: {control_plane_paths(args.root)['cli_history']}")
        return 0
    rows = read_shell_history(args.root, limit=args.limit, query=args.search or "")
    payload = {
        "schema_version": "aurora_cli_history_view_v1",
        "path": str(control_plane_paths(args.root)["cli_history"]),
        "count": len(rows),
        "search": str(args.search or ""),
        "history": rows,
    }
    if args.json:
        _print_json(payload)
        return 0
    if not rows:
        print("No matching Aurora shell history found.")
        return 0
    for index, row in enumerate(rows, start=1):
        print(
            f"{index:4} | {row['timestamp'] or '-'} | exit {row['exit_code']} | {row['command']}"
        )
    return 0


def _format_status(snapshot: dict[str, Any]) -> str:
    runtime = snapshot.get("runtime", {})
    panel = snapshot.get("control_panel", {})
    state = snapshot.get("state", {})
    modes = snapshot.get("modes", {})
    scheduler = snapshot.get("scheduler", {})
    monitors = snapshot.get("monitors", {})
    queue_bridge = snapshot.get("queue_bridge", {})
    mutation_admission = snapshot.get("mutation_admission", {})
    runtime_label = "running" if runtime.get("running") else "stopped"
    panel_label = "running" if panel.get("running") else "stopped"
    monitor_status = monitors.get("overall_status") or "unknown"
    return "\n".join(
        [
            f"Aurora runtime: {runtime_label} (pid {runtime.get('pid') or '-'})",
            f"Control Panel: {panel_label} (pid {panel.get('pid') or '-'})",
            f"State: {state.get('timestamp') or 'unavailable'} | age {_format_age(state.get('age_seconds'))} | session {state.get('session_id') or '-'}",
            (
                "Modes: "
                f"live={'on' if modes.get('live') else 'off'} | "
                f"execution={modes.get('execution') or '-'} | "
                f"action={modes.get('action') or '-'} | "
                f"auth={modes.get('auth') or '-'}"
            ),
            (
                "Scheduler: "
                f"profile={scheduler.get('profile') or '-'} | "
                f"mode={scheduler.get('mode') or '-'} | "
                f"pending={','.join(scheduler.get('pending_reasons') or []) or 'none'}"
            ),
            (
                f"Monitor: {monitor_status} | pending={queue_bridge.get('pending_count', 0)} | "
                f"bridge_caught_up={queue_bridge.get('bridge_caught_up', True)} | "
                f"result_caught_up={queue_bridge.get('command_result_caught_up', True)}"
            ),
            (
                "Mutations: "
                f"reserved={mutation_admission.get('reserved_count', 0)} | "
                f"terminal={mutation_admission.get('terminal_count', 0)} | "
                f"uncertain={mutation_admission.get('uncertain_count', 0)} | "
                "automatic_replay=off"
            ),
        ]
    )


def status_command(args: argparse.Namespace) -> int:
    while True:
        snapshot = build_operator_status(args.root)
        if args.json:
            _print_json(snapshot)
        else:
            print(_format_status(snapshot))
        if not args.watch:
            return 0 if snapshot.get("state", {}).get("exists") else 2
        try:
            time.sleep(max(0.2, args.interval))
        except KeyboardInterrupt:
            return 130
        if not args.json:
            print()


def dashboard_command(args: argparse.Namespace) -> int:
    first_frame = True
    try:
        while True:
            snapshot = build_operator_dashboard(args.root, event_limit=args.events)
            if args.json:
                if args.watch:
                    print(json.dumps(snapshot, ensure_ascii=True, sort_keys=True))
                else:
                    _print_json(snapshot)
            else:
                rendered = format_operator_dashboard(snapshot)
                if args.watch and not args.no_clear and sys.stdout.isatty():
                    sys.stdout.write("\x1b[2J\x1b[H" if first_frame else "\x1b[H\x1b[J")
                    sys.stdout.write(rendered + "\n")
                    sys.stdout.flush()
                else:
                    if not first_frame:
                        print()
                    print(rendered)
            first_frame = False
            if not args.watch:
                return 0 if snapshot.get("state", {}).get("exists") else 2
            time.sleep(max(0.2, float(args.interval)))
    except KeyboardInterrupt:
        return 130


def _print_submission(record: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        _print_json({"event": "request_submitted", "status": "queued", **record})
        return
    print(
        "Queued Aurora request "
        f"{record.get('request_id')} (message {record.get('message_id')})."
    )


def _print_receipt(receipt: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        _print_json(receipt)
        return
    print(
        f"Receipt {receipt.get('receipt_id') or '-'} | "
        f"request {receipt.get('request_id') or '-'} | "
        f"status {receipt.get('status') or receipt.get('outcome_status') or '-'} | "
        f"delivery {receipt.get('delivery_status') or '-'}"
    )
    reason = str(receipt.get("reason") or "").strip()
    if reason:
        print(reason)
    transaction = extract_settings_transaction_receipt(receipt)
    if transaction is not None:
        print(
            f"Settings transaction {transaction.get('transaction_id') or '-'} | "
            f"{transaction.get('operation') or '-'} | {transaction.get('status') or '-'} | "
            f"version {transaction.get('before_version') or '-'} -> {transaction.get('after_version') or '-'}"
        )
        for row in transaction.get("changes", []) or []:
            target = row.get("projected_value") if transaction.get("dry_run") else row.get("after_value")
            print(
                f"  {row.get('key')}: {_format_setting_value(row.get('before_value'))} -> "
                f"{_format_setting_value(target)}"
            )
        for rejection in transaction.get("rejections", []) or []:
            print(f"  rejected [{rejection.get('code') or 'error'}]: {rejection.get('message') or '-'}")
        rollback = transaction.get("rollback_handle") or {}
        if rollback.get("handle_id"):
            print(
                f"  rollback handle: {rollback['handle_id']} | "
                f"expected version {rollback.get('after_version') or transaction.get('after_version') or '-'}"
            )


def _receipt_exit_code(receipt: dict[str, Any]) -> int:
    status = str(receipt.get("status") or "").strip().lower()
    if status in {"processed", "completed", "ok"}:
        return 0
    if status in {"queued"}:
        return 0
    if status in {"routed_as_input"}:
        return 3
    if status in {"uncertain", "timeout"}:
        return 4
    return 2


def submit_command(
    args: argparse.Namespace,
    command_text: str,
    *,
    source: str = "aurora_cli",
    subject: str = "[AURORA CLI]",
    metadata: dict[str, Any] | None = None,
) -> int:
    offsets = journal_offsets(args.root)
    request_metadata = {"surface": "cli"}
    request_metadata.update(dict(metadata or {}))
    record = append_bridge_request(
        args.root,
        command_text,
        raw=True,
        source=source,
        author="operator",
        subject=subject,
        request_id=getattr(args, "request_id", None),
        client_id="aurora_cli",
        metadata=request_metadata,
    )
    if not args.wait:
        _print_submission(record, as_json=args.json)
        return 0
    if not args.json:
        _print_submission(record, as_json=False)

    status = build_operator_status(args.root)
    if not status.get("runtime", {}).get("running"):
        queued = {
            "event": "request_submitted",
            "request_id": record["request_id"],
            "message_id": record["message_id"],
            "client_id": record["client_id"],
            "status": "queued",
            "delivery_status": "queued",
            "terminal": False,
            "reason": "Aurora runtime is not active; the durable inbox request remains queued for its next launch.",
        }
        _print_receipt(queued, as_json=args.json)
        return 0

    receipt = wait_for_command_receipt(
        args.root,
        record["request_id"],
        client_id=record["client_id"],
        offsets=offsets,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
    )
    _print_receipt(receipt, as_json=args.json)
    return _receipt_exit_code(receipt)


def command_command(args: argparse.Namespace) -> int:
    command_text = " ".join(args.command_text).strip()
    if not command_text:
        raise SystemExit("aurora command requires command text")
    return submit_command(args, command_text)


def capture_command(args: argparse.Namespace) -> int:
    reason = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in args.reason).strip("_")
    reason = reason or "aurora_cli"
    if args.settle_seconds is None:
        command_text = f"REQUEST_SCREENSHOT_CAPTURE({reason})"
    else:
        command_text = f"REQUEST_SCREENSHOT_CAPTURE({reason},{max(0.0, args.settle_seconds):.3f})"
    return submit_command(args, command_text, subject="[AURORA CLI CAPTURE]")


def receipts_command(args: argparse.Namespace) -> int:
    rows = collect_command_receipts(
        args.root,
        limit=args.limit,
        request_id=args.request_id or "",
        client_id=args.client_id or "",
    )
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("No matching Aurora command receipts found.")
        return 1
    for row in rows:
        print(
            f"{row.get('timestamp') or '-'} | {row.get('request_id') or row.get('message_id') or '-'} | "
            f"{row.get('status') or '-'} | {row.get('command') or '-'}"
        )
    return 0


def doctor_command(args: argparse.Namespace) -> int:
    paths = control_plane_paths(args.root)
    status = build_operator_status(args.root)
    checks = [
        {
            "name": "root",
            "ok": paths["root"].is_dir(),
            "detail": str(paths["root"]),
        },
        {
            "name": "state",
            "ok": paths["state"].exists(),
            "detail": f"{paths['state']} | age {_format_age(status['state']['age_seconds'])}",
        },
        {
            "name": "inbox",
            "ok": paths["inbox"].exists(),
            "detail": str(paths["inbox"]),
        },
        {
            "name": "bridge_log",
            "ok": paths["bridge_log"].exists(),
            "detail": str(paths["bridge_log"]),
        },
        {
            "name": "command_log",
            "ok": paths["command_log"].exists(),
            "detail": str(paths["command_log"]),
        },
        {
            "name": "mutation_log",
            "ok": True,
            "detail": (
                str(paths["mutation_log"])
                if paths["mutation_log"].exists()
                else f"{paths['mutation_log']} | not created until first runtime admission"
            ),
        },
        {
            "name": "command_index",
            "ok": paths["command_index"].exists(),
            "detail": str(paths["command_index"]),
        },
        {
            "name": "cli_history",
            "ok": True,
            "detail": (
                str(paths["cli_history"])
                if paths["cli_history"].exists()
                else f"{paths['cli_history']} | created after the first stored shell command"
            ),
        },
        {
            "name": "runtime",
            "ok": True,
            "detail": "running" if status["runtime"]["running"] else "stopped (valid operator state)",
        },
    ]
    payload = {
        "schema_version": "aurora_cli_doctor_v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }
    if args.json:
        _print_json(payload)
    else:
        for check in checks:
            print(f"{'ok' if check['ok'] else 'FAIL':4} | {check['name']}: {check['detail']}")
    return 0 if payload["ok"] else 2


def _settings_context(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status = build_operator_status(root)
    state = read_json_file(control_plane_paths(root)["state"], {})
    if not isinstance(state, dict):
        state = {}
    return status, state


def _format_setting_value(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def settings_list_command(args: argparse.Namespace) -> int:
    status, state = _settings_context(args.root)
    snapshot = build_settings_snapshot(
        state,
        runtime_active=bool(status.get("runtime", {}).get("running")),
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
        category=args.category or "",
        maturity=args.maturity or "",
    )
    if args.json:
        _print_json(snapshot)
        return 0

    registry = snapshot["registry"]
    print(
        f"Aurora settings registry {registry['schema_version']} | "
        f"{snapshot['count']} settings | transactional runtime-session | version {snapshot['version']}"
    )
    for row in snapshot["settings"]:
        lock_label = "locked" if row.get("locked") else "unlocked"
        print(
            f"{row['key']} = {_format_setting_value(row.get('value'))} | "
            f"{row['value_status']} | {row['value_type']} | {lock_label} | "
            f"{row['maturity']} | {row['source']['kind']}"
        )
    return 0


def settings_get_command(args: argparse.Namespace) -> int:
    status, state = _settings_context(args.root)
    row = build_setting_readback(
        args.key,
        state,
        runtime_active=bool(status.get("runtime", {}).get("running")),
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )
    row["settings_version"] = build_settings_snapshot(
        state,
        runtime_active=bool(status.get("runtime", {}).get("running")),
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )["version"]
    if args.json:
        _print_json(row)
    else:
        print(
            f"{row['key']} = {_format_setting_value(row.get('value'))} | "
            f"status={row['value_status']} | source={row['source']['kind']} "
            f"({row['source']['path']}) | scope={row['scope']} | "
            f"maturity={row['maturity']} | locked={'yes' if row['locked'] else 'no'} | "
            f"version={row['settings_version']}"
        )
    return 0 if row["value_status"] not in {"unavailable", "invalid_runtime_value"} else 1


def settings_describe_command(args: argparse.Namespace) -> int:
    status, state = _settings_context(args.root)
    definition = describe_setting_definition(args.key, state=state)
    readback = build_setting_readback(
        definition["key"],
        state,
        runtime_active=bool(status.get("runtime", {}).get("running")),
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )
    payload = {
        "schema_version": "aurora_setting_description_v1",
        "definition": definition,
        "readback": readback,
    }
    if args.json:
        _print_json(payload)
        return 0

    allowed_values = definition.get("allowed_values") or []
    constraints = ", ".join(allowed_values) if allowed_values else definition["value_type"]
    if definition.get("minimum") is not None:
        constraints += f"; min={definition['minimum']}"
    if definition.get("maximum") is not None:
        constraints += f"; max={definition['maximum']}"
    print(f"{definition['key']}: {definition['title']}")
    print(definition["description"])
    print(
        f"Type: {definition['value_type']} | accepted: {constraints} | "
        f"maturity: {definition['maturity']} | GUI tier: {definition['gui_tier']}"
    )
    print(
        f"Current: {_format_setting_value(readback.get('value'))} ({readback['value_status']}) | "
        f"default: {_format_setting_value(definition.get('compatibility_default'))} "
        f"from {definition['compatibility_default_source']}"
    )
    print(
        f"Apply timing: {definition['apply_timing']} | scope: {', '.join(definition['allowed_scopes'])} | "
        f"write enabled: {'yes' if definition.get('write_enabled') else 'no'}"
    )
    print(f"Existing runtime command: {definition['command']}")
    notes = str(definition.get("notes") or "").strip()
    if notes:
        print(f"Note: {notes}")
    return 0


def _active_settings_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    status, state = _settings_context(args.root)
    if not status.get("runtime", {}).get("running"):
        raise ValueError("Aurora runtime must be active for settings transactions.")
    snapshot = build_settings_snapshot(
        state,
        runtime_active=True,
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )
    if not getattr(args, "expected_version", None):
        non_effective = [
            row["key"]
            for row in snapshot["settings"]
            if row.get("value_status") != "effective"
        ]
        if non_effective:
            raise ValueError(
                "A fresh effective settings snapshot is required before deriving expected_version."
            )
    return snapshot


def _parse_settings_change_arguments(values: list[str]) -> list[dict[str, str]]:
    changes = []
    for value in values:
        key, separator, raw_value = str(value).partition("=")
        if not separator or not key.strip() or not raw_value.strip():
            raise ValueError(
                f"Invalid settings change {value!r}; use canonical.key=value or alias=value."
            )
        changes.append({"key": key.strip(), "value": raw_value.strip()})
    return changes


def settings_version_command(args: argparse.Namespace) -> int:
    status, state = _settings_context(args.root)
    snapshot = build_settings_snapshot(
        state,
        runtime_active=bool(status.get("runtime", {}).get("running")),
        state_age_seconds=status.get("state", {}).get("age_seconds"),
        state_timestamp=str(state.get("timestamp") or ""),
    )
    payload = {
        "schema_version": snapshot["version_schema_version"],
        "version": snapshot["version"],
        "runtime_active": snapshot["runtime_active"],
        "state_timestamp": snapshot["state_timestamp"],
        "state_age_seconds": snapshot["state_age_seconds"],
        "status_counts": snapshot["status_counts"],
    }
    if args.json:
        _print_json(payload)
    else:
        print(
            f"{payload['version']} | runtime={'active' if payload['runtime_active'] else 'stopped'} | "
            f"state={payload['state_timestamp'] or 'unavailable'} | age={_format_age(payload['state_age_seconds'])}"
        )
    return 0 if state else 1


def settings_transaction_command(args: argparse.Namespace) -> int:
    snapshot = _active_settings_snapshot(args)
    expected_version = str(args.expected_version or snapshot["version"]).strip()
    request = build_settings_transaction_request(
        args.settings_action,
        changes=_parse_settings_change_arguments(args.changes),
        expected_version=expected_version,
        scope=args.scope,
        transaction_id=args.transaction_id or "",
    )
    command_text = build_settings_transaction_command(request)
    return submit_command(
        args,
        command_text,
        source="aurora_cli_settings",
        subject=f"[AURORA CLI SETTINGS {args.settings_action.upper()}]",
        metadata={
            "surface": "cli_settings",
            "settings_transaction_id": request["transaction_id"],
            "settings_operation": request["operation"],
            "expected_settings_version": expected_version,
        },
    )


def settings_rollback_command(args: argparse.Namespace) -> int:
    snapshot = _active_settings_snapshot(args)
    expected_version = str(args.expected_version or snapshot["version"]).strip()
    request = build_settings_transaction_request(
        "rollback",
        changes=(),
        expected_version=expected_version,
        scope=args.scope,
        rollback_handle=args.rollback_handle,
        transaction_id=args.transaction_id or "",
    )
    return submit_command(
        args,
        build_settings_transaction_command(request),
        source="aurora_cli_settings",
        subject="[AURORA CLI SETTINGS ROLLBACK]",
        metadata={
            "surface": "cli_settings",
            "settings_transaction_id": request["transaction_id"],
            "settings_operation": "rollback",
            "settings_rollback_handle": args.rollback_handle,
            "expected_settings_version": expected_version,
        },
    )


def _unique_completion_candidates(values: list[str]) -> list[str]:
    unique = {}
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            unique.setdefault(normalized.lower(), normalized)
    return sorted(unique.values(), key=lambda value: value.lower())


def _runtime_command_completion(row: dict[str, str]) -> str:
    command = str(row.get("command") or "").strip().upper()
    signature = str(row.get("signature") or "").strip()
    if command in {"GB", "PYAG"}:
        return f"{command}:"
    if signature == f"{command}()":
        return signature
    if signature.startswith(f"{command}("):
        return f"{command}("
    return command


def _setting_name_candidates(*, assignments: bool = False) -> list[str]:
    candidates = []
    for definition in list_setting_definitions():
        suffix = "=" if assignments else ""
        candidates.append(f"{definition.key}{suffix}")
        candidates.extend(f"{alias}{suffix}" for alias in definition.aliases)
    return _unique_completion_candidates(candidates)


def _setting_assignment_candidates(prefix: str) -> list[str]:
    key, separator, value_prefix = str(prefix or "").partition("=")
    if not separator:
        return _setting_name_candidates(assignments=True)
    try:
        definition = resolve_setting_definition(key)
    except ValueError:
        return []
    if definition.value_type == "boolean":
        values = ("on", "off")
    elif definition.value_type == "enum":
        values = definition.allowed_values
    else:
        values = ()
    if not values:
        return [f"{key}="]
    return [
        f"{key}={value}"
        for value in values
        if str(value).lower().startswith(value_prefix.lower())
    ]


def _safe_shell_split(value: str) -> list[str]:
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return value.split()


def complete_shell_line(
    line: str,
    *,
    cursor: int | None = None,
    root: Path = ROOT,
    catalog: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    normalized_line = str(line or "")
    cursor_index = len(normalized_line) if cursor is None else max(
        0, min(len(normalized_line), int(cursor))
    )
    before_cursor = normalized_line[:cursor_index]
    token_match = re.search(r"\S*$", before_cursor)
    start = token_match.start() if token_match else cursor_index
    prefix = before_cursor[start:]
    context = before_cursor[:start].strip()
    prior = _safe_shell_split(context) if context else []
    lowered = [token.lower() for token in prior]
    catalog_rows = catalog if catalog is not None else load_command_catalog(root)
    runtime_candidates = [_runtime_command_completion(row) for row in catalog_rows]
    registry = registry_summary()
    candidates: list[str]

    if not prior:
        candidates = list(SHELL_BUILTINS) + runtime_candidates
    else:
        head = lowered[0]
        if head in {"command", "send"}:
            candidates = runtime_candidates
        elif head == "settings":
            if len(prior) == 1:
                candidates = list(SHELL_SETTINGS_ACTIONS)
            else:
                action = lowered[1]
                if action in {"get", "describe"}:
                    candidates = _setting_name_candidates() + ["--json"]
                elif action in {"preview", "apply"}:
                    candidates = (
                        [
                            "--expected-version",
                            "--transaction-id",
                            "--scope",
                            "--wait",
                            "--no-wait",
                            "--timeout",
                            "--poll-interval",
                            "--request-id",
                            "--json",
                        ]
                        if prefix.startswith("-")
                        else _setting_assignment_candidates(prefix)
                    )
                elif action == "rollback":
                    candidates = [
                        "--expected-version",
                        "--transaction-id",
                        "--scope",
                        "--wait",
                        "--no-wait",
                        "--timeout",
                        "--poll-interval",
                        "--request-id",
                        "--json",
                    ]
                elif action == "list":
                    if lowered[-1:] == ["--category"]:
                        candidates = list(registry["categories"])
                    elif lowered[-1:] == ["--maturity"]:
                        candidates = list(registry["maturities"])
                    else:
                        candidates = ["--category", "--maturity", "--json"]
                elif action == "version":
                    candidates = ["--json"]
                else:
                    candidates = []
        elif head == "commands":
            if lowered[-1:] == ["--category"]:
                candidates = sorted(
                    {row.get("category", "") for row in catalog_rows if row.get("category")}
                )
            else:
                candidates = ["--category", "--limit", "--detail", "--json"]
        elif head == "history":
            candidates = ["show", "clear", "--search", "--limit", "--json", "--yes"]
        elif head == "status":
            candidates = ["--watch", "--interval", "--json"]
        elif head == "dashboard":
            candidates = ["--watch", "--interval", "--events", "--json", "--no-clear"]
        elif head == "doctor":
            candidates = ["--json"]
        elif head == "receipts":
            candidates = ["--request-id", "--client-id", "--limit", "--json"]
        elif head == "capture":
            candidates = [
                "now",
                "--reason",
                "--settle-seconds",
                "--wait",
                "--no-wait",
                "--timeout",
                "--request-id",
                "--json",
            ]
        elif head == "help":
            candidates = list(SHELL_BUILTINS)
        else:
            candidates = []

    filtered = _unique_completion_candidates(
        [candidate for candidate in candidates if candidate.lower().startswith(prefix.lower())]
    )
    return {
        "schema_version": SHELL_COMPLETION_SCHEMA_VERSION,
        "line": normalized_line,
        "cursor": cursor_index,
        "replace_start": start,
        "replace_end": cursor_index,
        "prefix": prefix,
        "count": len(filtered),
        "candidates": filtered,
    }


def complete_command(args: argparse.Namespace) -> int:
    line = " ".join(args.line or []).strip()
    payload = complete_shell_line(line, cursor=args.cursor, root=args.root)
    if args.json:
        _print_json(payload)
    else:
        for candidate in payload["candidates"]:
            print(candidate)
    return 0


def _print_shell_help() -> None:
    print("Aurora operator shell")
    print("  status | dashboard [--watch] | doctor | receipts | capture now")
    print("  command <RAW> | send <RAW> | or enter a known Aurora command directly")
    print("  commands [query] | settings list|get|describe|version|preview|apply|rollback")
    print("  history [show] | history clear --yes | complete <partial line>")
    print("  help [command] | exit [code] | quit")
    print("Tab completes shell commands, Aurora commands, setting keys, and enum/boolean values.")
    print("The shell has no operating-system command escape and never replays uncertain mutations.")


def _print_shell_search(root: Path, query: str) -> int:
    command_rows = filter_command_catalog(
        load_command_catalog(root), query=query, limit=20
    )
    normalized_query = str(query or "").strip().lower()
    setting_rows = []
    for definition in list_setting_definitions():
        haystack = " ".join(
            (
                definition.key,
                definition.title,
                definition.description,
                definition.category,
                *definition.aliases,
            )
        ).lower()
        if not normalized_query or normalized_query in haystack:
            setting_rows.append(definition)
    print(f"Commands ({len(command_rows)} shown):")
    for row in command_rows:
        print(f"  {row['signature'] or row['command']} | {row['summary']}")
    print(f"Settings ({len(setting_rows)} shown):")
    for definition in setting_rows[:20]:
        aliases = f" | aliases {', '.join(definition.aliases)}" if definition.aliases else ""
        print(f"  {definition.key} | {definition.title}{aliases}")
    return 0 if command_rows or setting_rows else 1


def _shell_cli_argv(line: str, catalog: list[dict[str, str]]) -> list[str]:
    stripped = str(line or "").strip()
    head, separator, remainder = stripped.partition(" ")
    lowered_head = head.lower()
    if lowered_head in {"command", "send"}:
        if not separator or not remainder.strip():
            raise ValueError(f"{lowered_head} requires an Aurora command.")
        return ["command", remainder.strip()]
    tokens = _safe_shell_split(stripped)
    if not tokens:
        return []
    if tokens[0].lower() in SHELL_BUILTINS:
        return tokens
    runtime_names = {row["command"].upper() for row in catalog}
    command_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z_][A-Za-z0-9_]*)?)(?=\s*\(|$)", stripped)
    if command_match and command_match.group(1).upper() in runtime_names:
        return ["command", stripped]
    # GB normalization includes controller shorthands, not standalone GB().
    if re.match(r"(?i)^GB:\s*\S", stripped):
        return ["command", stripped]
    return tokens


def execute_shell_line(
    line: str,
    *,
    root: Path,
    catalog: list[dict[str, str]] | None = None,
) -> int:
    stripped = str(line or "").strip()
    if not stripped:
        return 0
    catalog_rows = catalog if catalog is not None else load_command_catalog(root)
    if stripped == "?" or stripped.startswith("? "):
        return _print_shell_search(root, stripped[1:].strip())
    tokens = _safe_shell_split(stripped)
    if tokens and tokens[0].lower() == "help":
        if len(tokens) == 1:
            _print_shell_help()
            return 0
        help_argv = tokens[1:] + ["--help"]
        try:
            return main(["--root", str(root), *help_argv])
        except SystemExit as error:
            return int(error.code or 0)
    argv = _shell_cli_argv(stripped, catalog_rows)
    if argv and argv[0].lower() == "shell":
        print("Already inside the Aurora operator shell.")
        return 2
    try:
        return main(["--root", str(root), *argv])
    except SystemExit as error:
        return int(error.code or 0)


def _display_completion_candidates(candidates: list[str]) -> None:
    shown = candidates[:SHELL_COMPLETION_DISPLAY_LIMIT]
    for start in range(0, len(shown), 4):
        print("  ".join(shown[start : start + 4]))
    remaining = len(candidates) - len(shown)
    if remaining > 0:
        print(f"... {remaining} more; narrow the prefix or use complete/commands.")


def _windows_read_shell_line(
    prompt: str,
    history: list[str],
    completion: Callable[[str, int], dict[str, Any]],
) -> str:
    import msvcrt

    buffer: list[str] = []
    cursor = 0
    rendered_length = 0
    history_index = len(history)
    saved_current = ""

    def redraw() -> None:
        nonlocal rendered_length
        text = "".join(buffer)
        width = max(rendered_length, len(text))
        sys.stdout.write("\r" + prompt + text + (" " * (width - len(text))))
        if width > cursor:
            sys.stdout.write("\b" * (width - cursor))
        sys.stdout.flush()
        rendered_length = len(text)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    while True:
        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            key = msvcrt.getwch()
            if key == "K" and cursor > 0:
                cursor -= 1
            elif key == "M" and cursor < len(buffer):
                cursor += 1
            elif key == "G":
                cursor = 0
            elif key == "O":
                cursor = len(buffer)
            elif key == "S" and cursor < len(buffer):
                del buffer[cursor]
            elif key == "H" and history:
                if history_index == len(history):
                    saved_current = "".join(buffer)
                history_index = max(0, history_index - 1)
                buffer[:] = list(history[history_index])
                cursor = len(buffer)
            elif key == "P" and history:
                history_index = min(len(history), history_index + 1)
                value = saved_current if history_index == len(history) else history[history_index]
                buffer[:] = list(value)
                cursor = len(buffer)
            redraw()
            continue
        if char == "\r":
            print()
            return "".join(buffer)
        if char == "\x03":
            print("^C")
            raise KeyboardInterrupt
        if char == "\x04" and not buffer:
            print()
            raise EOFError
        if char == "\b":
            if cursor > 0:
                cursor -= 1
                del buffer[cursor]
                redraw()
            continue
        if char == "\t":
            payload = completion("".join(buffer), cursor)
            candidates = payload.get("candidates", []) or []
            if not candidates:
                continue
            prefix = str(payload.get("prefix") or "")
            replacement = ""
            if len(candidates) == 1:
                replacement = candidates[0]
            else:
                common = os.path.commonprefix(candidates)
                if len(common) > len(prefix):
                    replacement = common
            if replacement:
                start = int(payload.get("replace_start", cursor))
                end = int(payload.get("replace_end", cursor))
                buffer[start:end] = list(replacement)
                cursor = start + len(replacement)
                redraw()
            else:
                print()
                _display_completion_candidates(candidates)
                rendered_length = 0
                redraw()
            continue
        if char >= " " and char != "\x7f":
            buffer.insert(cursor, char)
            cursor += 1
            redraw()


def _read_shell_line(
    prompt: str,
    history: list[str],
    completion: Callable[[str, int], dict[str, Any]],
) -> str:
    if os.name == "nt" and sys.stdin.isatty() and sys.stdout.isatty():
        return _windows_read_shell_line(prompt, history, completion)
    return input(prompt)


def shell_command(args: argparse.Namespace) -> int:
    catalog = load_command_catalog(args.root)
    history_rows = (
        []
        if args.no_history
        else read_shell_history(
            args.root,
            limit=max(1, min(SHELL_HISTORY_NAVIGATION_LIMIT, args.history_limit)),
        )
    )
    navigation_history = [row["command"] for row in history_rows]
    if not args.no_banner:
        status = build_operator_status(args.root)
        runtime_label = "running" if status.get("runtime", {}).get("running") else "stopped"
        print(
            f"Aurora operator shell | runtime {runtime_label} | "
            f"{len(catalog)} commands | {registry_summary()['setting_count']} settings"
        )
        print("Type help for commands. Tab completes. Ctrl+D or exit closes the shell.")

    completion = lambda line, cursor: complete_shell_line(
        line,
        cursor=cursor,
        root=args.root,
        catalog=catalog,
    )
    while True:
        try:
            line = _read_shell_line("aurora> ", navigation_history, completion)
        except EOFError:
            return 0
        except KeyboardInterrupt:
            print("Interrupted current input.")
            continue
        stripped = str(line or "").strip()
        if not stripped:
            continue
        tokens = _safe_shell_split(stripped)
        if tokens and tokens[0].lower() in {"exit", "quit", "q"}:
            if len(tokens) > 2:
                print("exit accepts at most one numeric status code.")
                continue
            if len(tokens) == 2:
                try:
                    return int(tokens[1])
                except ValueError:
                    print("exit status must be an integer.")
                    continue
            return 0
        try:
            exit_code = execute_shell_line(stripped, root=args.root, catalog=catalog)
        except KeyboardInterrupt:
            exit_code = 130
            print(
                "Wait interrupted. Inspect receipts/status before retrying because the outcome may be uncertain."
            )
        history_cleared = (
            len(tokens) >= 2
            and tokens[0].lower() == "history"
            and tokens[1].lower() == "clear"
            and exit_code == 0
        )
        if history_cleared:
            navigation_history.clear()
        elif not args.no_history:
            stored = append_shell_history(args.root, stripped, exit_code)
            if stored:
                navigation_history.append(_normalize_shell_history_line(stripped))
                navigation_history[:] = navigation_history[-SHELL_HISTORY_NAVIGATION_LIMIT:]
            elif shell_history_is_sensitive(stripped):
                print("History: command not stored because it is sensitive or oversized.")
        if exit_code:
            print(f"[exit {exit_code}]")


def _add_wait_options(parser: argparse.ArgumentParser) -> None:
    wait_group = parser.add_mutually_exclusive_group()
    wait_group.add_argument("--wait", dest="wait", action="store_true")
    wait_group.add_argument("--no-wait", dest="wait", action="store_false")
    parser.set_defaults(wait=True)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval", type=float, default=0.10)
    parser.add_argument("--request-id")
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aurora",
        description="Aurora operator CLI over the file-backed control plane.",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    status_parser = subparsers.add_parser("status", help="Read the exported Aurora runtime status.")
    status_parser.add_argument("--watch", action="store_true")
    status_parser.add_argument("--interval", type=float, default=1.5)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=status_command)

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Show one shared operator dashboard snapshot or watch it live.",
    )
    dashboard_parser.add_argument("--watch", action="store_true")
    dashboard_parser.add_argument("--interval", type=float, default=1.5)
    dashboard_parser.add_argument("--events", type=int, default=8)
    dashboard_parser.add_argument("--json", action="store_true")
    dashboard_parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Append watched text frames instead of refreshing an interactive terminal.",
    )
    dashboard_parser.set_defaults(handler=dashboard_command)

    command_parser = subparsers.add_parser("command", help="Submit a raw Aurora command.")
    command_parser.add_argument("command_text", nargs="+")
    _add_wait_options(command_parser)
    command_parser.set_defaults(handler=command_command)

    capture_parser = subparsers.add_parser("capture", help="Request a one-off Aurora screenshot capture.")
    capture_parser.add_argument("action", nargs="?", choices=["now"], default="now")
    capture_parser.add_argument("--reason", default="aurora_cli")
    capture_parser.add_argument("--settle-seconds", type=float)
    _add_wait_options(capture_parser)
    capture_parser.set_defaults(handler=capture_command)

    receipts_parser = subparsers.add_parser("receipts", help="Show recent correlated command results.")
    receipts_parser.add_argument("--request-id")
    receipts_parser.add_argument("--client-id", help="Filter receipts by their originating client.")
    receipts_parser.add_argument("--limit", type=int, default=20)
    receipts_parser.add_argument("--json", action="store_true")
    receipts_parser.set_defaults(handler=receipts_command)

    doctor_parser = subparsers.add_parser("doctor", help="Check local control-plane files and process state.")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(handler=doctor_command)

    commands_parser = subparsers.add_parser(
        "commands",
        help="Search the generated Aurora command catalog without starting the runtime.",
    )
    commands_parser.add_argument("query", nargs="?", default="")
    commands_parser.add_argument("--category")
    commands_parser.add_argument("--limit", type=int, default=50)
    commands_parser.add_argument("--detail", action="store_true", help="Include reviewed parameter/result coverage in JSON output.")
    commands_parser.add_argument("--json", action="store_true")
    commands_parser.set_defaults(handler=commands_command)

    history_parser = subparsers.add_parser(
        "history",
        help="Show or explicitly clear local Aurora operator-shell history.",
    )
    history_parser.add_argument("history_action", nargs="?", choices=["show", "clear"], default="show")
    history_parser.add_argument("--search")
    history_parser.add_argument("--limit", type=int, default=SHELL_HISTORY_DEFAULT_LIMIT)
    history_parser.add_argument("--json", action="store_true")
    history_parser.add_argument("--yes", action="store_true", help="Confirm local history deletion.")
    history_parser.set_defaults(handler=history_command)

    complete_parser = subparsers.add_parser(
        "complete",
        help="Return context-aware completion candidates for a partial shell line.",
    )
    complete_parser.add_argument("--cursor", type=int)
    complete_parser.add_argument("--json", action="store_true")
    complete_parser.add_argument("line", nargs=argparse.REMAINDER)
    complete_parser.set_defaults(handler=complete_command)

    shell_parser = subparsers.add_parser(
        "shell",
        help="Open the interactive Aurora operator shell.",
    )
    shell_parser.add_argument("--no-history", action="store_true")
    shell_parser.add_argument("--no-banner", action="store_true")
    shell_parser.add_argument(
        "--history-limit",
        type=int,
        default=SHELL_HISTORY_NAVIGATION_LIMIT,
    )
    shell_parser.set_defaults(handler=shell_command)

    settings_parser = subparsers.add_parser(
        "settings",
        help="Inspect or atomically change Aurora's typed runtime-session settings.",
    )
    settings_subparsers = settings_parser.add_subparsers(dest="settings_action", required=True)
    registry = registry_summary()

    settings_list_parser = settings_subparsers.add_parser(
        "list",
        help="List registered settings and effective readback.",
    )
    settings_list_parser.add_argument("--category", choices=registry["categories"])
    settings_list_parser.add_argument("--maturity", choices=registry["maturities"])
    settings_list_parser.add_argument("--json", action="store_true")
    settings_list_parser.set_defaults(handler=settings_list_command)

    settings_get_parser = settings_subparsers.add_parser(
        "get",
        help="Read one setting by canonical key or documented alias.",
    )
    settings_get_parser.add_argument("key")
    settings_get_parser.add_argument("--json", action="store_true")
    settings_get_parser.set_defaults(handler=settings_get_command)

    settings_describe_parser = settings_subparsers.add_parser(
        "describe",
        help="Show one setting's type, constraints, scope, maturity, and readback.",
    )
    settings_describe_parser.add_argument("key")
    settings_describe_parser.add_argument("--json", action="store_true")
    settings_describe_parser.set_defaults(handler=settings_describe_command)

    settings_version_parser = settings_subparsers.add_parser(
        "version",
        help="Show the opaque settings version used by transaction preconditions.",
    )
    settings_version_parser.add_argument("--json", action="store_true")
    settings_version_parser.set_defaults(handler=settings_version_command)

    for operation in ("preview", "apply"):
        transaction_parser = settings_subparsers.add_parser(
            operation,
            help=f"{operation.title()} an all-or-none runtime-session settings transaction.",
        )
        transaction_parser.add_argument(
            "changes",
            nargs="+",
            metavar="KEY=VALUE",
            help="One or more canonical.key=value or alias=value changes.",
        )
        transaction_parser.add_argument("--expected-version")
        transaction_parser.add_argument("--transaction-id")
        transaction_parser.add_argument("--scope", choices=["runtime_session"], default="runtime_session")
        _add_wait_options(transaction_parser)
        transaction_parser.set_defaults(handler=settings_transaction_command)

    settings_rollback_parser = settings_subparsers.add_parser(
        "rollback",
        help="Consume an in-memory rollback handle if the settings version still matches.",
    )
    settings_rollback_parser.add_argument("rollback_handle")
    settings_rollback_parser.add_argument("--expected-version")
    settings_rollback_parser.add_argument("--transaction-id")
    settings_rollback_parser.add_argument("--scope", choices=["runtime_session"], default="runtime_session")
    _add_wait_options(settings_rollback_parser)
    settings_rollback_parser.set_defaults(handler=settings_rollback_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.root = Path(args.root).expanduser().resolve()
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as error:
        print(f"aurora: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
