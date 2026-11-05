"""Source-backed discovery for all runtime and explicit desktop bindings.

Only static AST data is read; importing Aurora or executing a handler is never
needed to inspect commands. The dispatch dictionaries remain authoritative.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from aurora_command_contracts import describe_command_contract, reviewed_command_description, setting_command_definition, setting_shortcut_definition


CATALOG_SCHEMA = "aurora_command_catalog_v1"
CATALOG_SOURCE_FILES = ("aurora2.py", "aurora_command_contracts.py", "aurora_command_catalog.py", "aurora_settings_registry.py", "aurora_settings_transactions.py", "aurora_history_controls.py", "aurora_goal_store.py", "aurora_episodic_retrieval.py", "aurora_search_query.py", "aurora_retrieval_results.py", "aurora_retrieval_commands.py", "aurora_task_continuation.py")


def parse_dispatch(tree: ast.Module, variable: str) -> dict[str, str]:
    """Read a literal dispatch table and reject ambiguous/shadowed bindings."""
    tables = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets)]
    if len(tables) != 1 or not isinstance(tables[0], ast.Dict):
        raise ValueError(f"Expected one literal {variable} dictionary.")
    bindings: dict[str, str] = {}
    for key, value in zip(tables[0].keys, tables[0].values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not isinstance(value, ast.Name):
            raise ValueError(f"Unsupported dynamic binding in {variable}.")
        name = key.value
        if name in bindings:
            raise ValueError(f"Duplicate {variable} binding: {name}")
        bindings[name] = value.id
    return bindings


def parse_help(tree: ast.Module) -> dict[str, dict[str, str]]:
    """Extract human prose as documentation, never as proof of callability."""
    entries: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == "help_message" for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        category = "General"
        for raw in node.value.value.splitlines():
            line = raw.strip()
            heading = re.match(r"- \*\*(.+?)\*\*:$", line)
            if heading:
                category = heading.group(1)
            bullet = re.match(r"-\s+([A-Z0-9_:%\-]+(?:\([^)]*\))?)\s*:\s*(.+)", line)
            if bullet:
                signature, summary = bullet.groups()
                entries[signature.split("(", 1)[0]] = {
                    "signature": signature, "summary": summary, "category": category,
                }
    return entries


def build_command_catalog(root: Path) -> dict[str, Any]:
    """Build the exact binding inventory with aliases and reviewed coverage."""
    source = (Path(root) / "aurora2.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    runtime = parse_dispatch(tree, "command_dispatch")
    desktop = parse_dispatch(tree, "pyautogui_dispatch")
    help_entries = parse_help(tree)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    names_by_handler: dict[tuple[str, str], list[str]] = defaultdict(list)
    bindings = [(name, handler, "runtime") for name, handler in runtime.items()]
    bindings += [("pyag:" + name, handler, "desktop") for name, handler in desktop.items()]
    seen: set[str] = set()
    for name, handler, kind in bindings:
        if name.upper() in seen:
            raise ValueError(f"Ambiguous case-insensitive command: {name}")
        if handler not in functions:
            raise ValueError(f"Missing handler {handler} for {name}")
        seen.add(name.upper())
        names_by_handler[(kind, handler)].append(name)
    rows = []
    for name, handler, kind in sorted(bindings, key=lambda row: row[0].upper()):
        aliases = sorted(other for other in names_by_handler[(kind, handler)] if other != name)
        definition = setting_command_definition(name)
        if definition and not setting_shortcut_definition(name):
            family = (definition.command.split("(", 1)[0], *definition.command_aliases)
            aliases = sorted(set(aliases) | {other for other in family if other != name and other in runtime})
        help_name = name if name in help_entries else next((other for other in aliases if other in help_entries), "")
        entry = help_entries.get(help_name, {})
        signature = entry.get("signature", name + "(...)")
        if help_name and help_name != name:
            signature = name + signature[len(help_name):]
        doc = ast.get_docstring(functions[handler]) or ""
        summary = entry.get("summary") or (doc.splitlines()[0] if doc else "Inspect the handler; detailed usage has not been reviewed.")
        contract = describe_command_contract(name)
        reviewed = reviewed_command_description(name)
        if reviewed:
            signature, summary = reviewed["signature"], reviewed["summary"]
        rows.append({
            "command": name, "signature": signature,
            "category": entry.get("category") or ("Desktop actions" if kind == "desktop" else "Runtime commands"),
            "handler": handler, "summary": summary, "aliases": aliases,
            "binding_kind": kind, "callable": True,
            "signature_source": "reviewed_contract" if reviewed else ("help_text" if entry else "placeholder"),
            "source": {"file": "aurora2.py", "line": functions[handler].lineno},
            "contract": contract,
        })
    return {
        "schema_version": CATALOG_SCHEMA,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_hashes": {name: hashlib.sha256((Path(root) / name).read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()
                          for name in CATALOG_SOURCE_FILES},
        "runtime_binding_count": len(runtime), "desktop_binding_count": len(desktop),
        "commands": rows,
        "syntax_notes": {
            "GB": "GB: is a game-input namespace handled by action normalization, not a standalone function.",
            "PYAG": "Use an explicit pyag: command; the namespace label itself is not callable.",
        },
    }


def load_generated_catalog(path: Path, *, root: Path | None = None) -> list[dict[str, Any]]:
    """Read the generated machine catalog without parsing the runtime again."""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA:
        raise ValueError(f"Unexpected Aurora command catalog schema: {path}")
    if root is not None:
        for name in CATALOG_SOURCE_FILES:
            source = Path(root) / name
            if source.exists() and payload.get("source_hashes", {}).get(name) != hashlib.sha256(
                source.read_text(encoding="utf-8-sig").encode("utf-8")
            ).hexdigest():
                raise ValueError("Aurora command catalog is stale. Run regenerate_aurora_skill_refs.ps1 -Force.")
    rows = payload.get("commands")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in
            ("command", "signature", "category", "handler", "summary")) for row in rows
    ):
        raise ValueError(f"Invalid Aurora command catalog rows: {path}")
    return rows
