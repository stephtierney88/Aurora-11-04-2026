from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = ROOT / "aurora2.py"
UI_PATH = ROOT / "aurora2_control_panel.py"
CONTROL_PLANE_PATHS = (
    ROOT / "aurora_capture_geometry.py", ROOT / "aurora_capture_provenance.py", ROOT / "aurora_capture_store.py",
    ROOT / "aurora_conversation_delivery.py", ROOT / "aurora_delivery_receipts.py",
    ROOT / "aurora_agent_controls.py", ROOT / "aurora_chatgpt_auth.py",
    ROOT / "aurora_chatgpt_transport.py", ROOT / "aurora_chatgpt_panel.py", ROOT / "aurora_subscription_worker.py",
    ROOT / "aurora_conversation_navigator.py",
    ROOT / "aurora_gameplay_scene.py", ROOT / "aurora_goal_store.py",
    ROOT / "aurora_command_catalog.py",
    ROOT / "aurora_validation_console.py",
    ROOT / "aurora_validation_worker.py",
    ROOT / "aurora_command_contracts.py",
    ROOT / "aurora_default_profiles.py",
    ROOT / "aurora_pending_commands.py",
    ROOT / "aurora_history_controls.py",
    ROOT / "aurora_episodic_retrieval.py",
    ROOT / "aurora_search_query.py", ROOT / "aurora_retrieval_results.py", ROOT / "aurora_retrieval_commands.py", ROOT / "aurora_conversation.py", ROOT / "aurora_switchboard.py",
    ROOT / "aurora_panel_layout.py",
    ROOT / "obs_readonly_mcp_server.py",
    ROOT / "obs_readonly_client.py",
    ROOT / "aurora_capture_store.py",
    ROOT / "aurora_runtime_work.py", ROOT / "aurora_input_ownership.py", ROOT / "aurora_task_continuation.py",
    ROOT / "aurora_responses_reasoning.py",
    ROOT / "aurora_control_plane.py",
    ROOT / "aurora_command_protocol.py",
    ROOT / "aurora_preflight.py",
    ROOT / "aurora_settings_registry.py",
    ROOT / "aurora_settings_transactions.py",
    ROOT / "aurora_cli.py",
    ROOT / "aurora_mcp_server.py",
    ROOT / "blender_readonly_mcp_server.py",
    ROOT / "blender_scene_inventory.py",
    ROOT / "fl_studio_readonly_mcp_server.py",
    ROOT / "fl_studio_device_script.py",
)
RUNTIME_REF_DIR = ROOT / "aurora_reference_maps" / "runtime"
UI_REF_DIR = ROOT / "aurora_reference_maps" / "ui"

RUNTIME_OUTPUTS = (
    RUNTIME_REF_DIR / "runtime-symbol-index.tsv",
    RUNTIME_REF_DIR / "runtime-generated-map.md",
    RUNTIME_REF_DIR / "runtime-generated-call-tree.md",
    RUNTIME_REF_DIR / "runtime-function-skeleton.jsonl",
)
UI_OUTPUTS = (
    UI_REF_DIR / "ui-symbol-index.tsv",
    UI_REF_DIR / "ui-generated-map.md",
    UI_REF_DIR / "ui-generated-call-tree.md",
    UI_REF_DIR / "ui-function-skeleton.jsonl",
)
CONTROL_PLANE_SKELETON_OUTPUT = RUNTIME_REF_DIR / "control-plane-function-skeleton.jsonl"


def configure(root: Path, output_root: Path) -> None:
    """Bind a checkout and staging directory without requiring installed skills."""
    global ROOT, RUNTIME_PATH, UI_PATH, CONTROL_PLANE_PATHS
    global RUNTIME_REF_DIR, UI_REF_DIR, RUNTIME_OUTPUTS, UI_OUTPUTS, CONTROL_PLANE_SKELETON_OUTPUT
    filenames = [path.relative_to(ROOT) for path in CONTROL_PLANE_PATHS]
    ROOT = Path(root).resolve()
    RUNTIME_PATH, UI_PATH = ROOT / "aurora2.py", ROOT / "aurora2_control_panel.py"
    CONTROL_PLANE_PATHS = tuple(ROOT / name for name in filenames)
    RUNTIME_REF_DIR, UI_REF_DIR = Path(output_root) / "runtime", Path(output_root) / "ui"
    RUNTIME_OUTPUTS = tuple(RUNTIME_REF_DIR / path.name for path in RUNTIME_OUTPUTS)
    UI_OUTPUTS = tuple(UI_REF_DIR / path.name for path in UI_OUTPUTS)
    CONTROL_PLANE_SKELETON_OUTPUT = RUNTIME_REF_DIR / "control-plane-function-skeleton.jsonl"

RUNTIME_ROOTS = (
    "execute_command_entry",
    "cancel_active_work_command",
    "persist_runtime_capture",
    "drain_runtime_command_results",
    "drain_runtime_processed_capture",
    "service_runtime_control_during_model_wait",
    "post_openai_model_request",
    "main",
    "handle_commands",
    "poll_external_inbox_messages",
    "poll_external_reply_bridges",
    "write_control_panel_state_snapshot",
    "monitor_and_restart_processes",
    "handle_queued_input",
    "maybe_run_smoke_test_step",
    "shutdown_runtime_command",
)
UI_ROOTS = (
    "_build_ui",
    "_build_settings_card",
    "_build_pending_tab",
    "_build_screenshots_tab",
    "_build_image_memory_tab",
    "refresh_now",
    "refresh_loop",
    "send_raw",
)


@dataclass
class Symbol:
    kind: str
    simple_name: str
    qualname: str
    line: int
    end_line: int
    container: str
    domain: str
    doc: str
    calls: list[str]
    args: list[dict[str, str]]
    return_annotation: str
    return_style: str
    yields_value: bool
    side_effect_hints: list[str]
    commands: list[str] = field(default_factory=list)


def first_doc_line(node: ast.AST) -> str:
    value = ast.get_docstring(node) or ""
    return value.splitlines()[0].strip() if value else ""


def iter_calls(node: ast.AST) -> Iterable[str]:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                yield func.id
            elif isinstance(func, ast.Attribute):
                yield func.attr


def safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        text = ast.unparse(node)
    except Exception:
        return ""
    text = " ".join(text.strip().split())
    if len(text) > 120:
        return text[:117] + "..."
    return text


def build_arg_rows(node: ast.AST) -> list[dict[str, str]]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    rows: list[dict[str, str]] = []
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    posonly_count = len(args.posonlyargs)
    for index, (arg, default) in enumerate(zip(positional, defaults)):
        kind = "posonly" if index < posonly_count else "arg"
        rows.append(
            {
                "name": arg.arg,
                "kind": kind,
                "annotation": safe_unparse(arg.annotation),
                "default": safe_unparse(default),
            }
        )
    if args.vararg:
        rows.append(
            {
                "name": args.vararg.arg,
                "kind": "vararg",
                "annotation": safe_unparse(args.vararg.annotation),
                "default": "",
            }
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        rows.append(
            {
                "name": arg.arg,
                "kind": "kwonly",
                "annotation": safe_unparse(arg.annotation),
                "default": safe_unparse(default),
            }
        )
    if args.kwarg:
        rows.append(
            {
                "name": args.kwarg.arg,
                "kind": "kwarg",
                "annotation": safe_unparse(args.kwarg.annotation),
                "default": "",
            }
        )
    return rows


def format_args_for_index(args: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for arg in args:
        name = arg["name"]
        prefix = "*" if arg["kind"] == "vararg" else "**" if arg["kind"] == "kwarg" else ""
        annotation = f":{arg['annotation']}" if arg.get("annotation") else ""
        default = f"={arg['default']}" if arg.get("default") else ""
        parts.append(f"{prefix}{name}{annotation}{default}")
    return "(" + ", ".join(parts) + ")"


def infer_return_style(node: ast.AST) -> tuple[str, bool]:
    if isinstance(node, ast.ClassDef):
        return "class", False
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "unknown", False
    returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
    value_returns = [
        child for child in returns
        if child.value is not None
        and not (isinstance(child.value, ast.Constant) and child.value.value is None)
    ]
    yields_value = any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))
    if yields_value:
        return "yields", True
    if node.returns is not None:
        return "annotated", False
    if value_returns and len(value_returns) == len(returns):
        return "value", False
    if value_returns:
        return "mixed", False
    if returns:
        return "none", False
    return "implicit", False


def infer_side_effect_hints(name: str, calls: list[str], domain: str) -> list[str]:
    haystack = " ".join([name, domain, *calls]).lower()
    hints: list[str] = []
    checks = (
        ("state_export", ("control_panel_state", "state_snapshot", "export", "snapshot")),
        ("file_io", ("open", "read_text", "write_text", "jsonl", "path", "file")),
        ("log_write", ("log", "write_command_execution_log", "append", "jsonl")),
        ("external_bridge", ("external", "inbox", "bridge", "reply")),
        ("command_queue", ("command", "pending", "queue", "dispatch", "approve")),
        ("model_api", ("openai", "chat", "completion", "responses", "model")),
        ("auth_oauth", ("auth", "oauth", "token", "login")),
        ("process_lifecycle", ("process", "thread", "worker", "shutdown", "terminate", "restart")),
        ("ui_update", ("tk", "widget", "tab", "canvas", "label", "tree", "refresh")),
        ("gameplay_input", ("game", "gb", "pyag", "keyboard", "mouse", "input", "emulator")),
    )
    for label, tokens in checks:
        if any(token in haystack for token in tokens):
            hints.append(label)
    return hints or ["pure_or_unknown"]


def classify_runtime(name: str) -> str:
    upper = name.upper()
    if any(token in upper for token in ("CONTROL_PANEL", "STATE_SNAPSHOT")):
        return "UI Export Boundary"
    if any(token in upper for token in ("EXTERNAL", "INBOX", "REPLY_BRIDGE", "OPERATOR", "OAUTH")):
        return "External Operator Bridge"
    if any(token in upper for token in ("SCREENSHOT", "VISION", "GAME", "GB", "IMAGE", "SCENE", "EMULATOR", "DRAWING", "INPUT")):
        return "Screenshot / Vision / Gameplay"
    if any(token in upper for token in ("COMMAND", "PENDING", "QUEUE", "APPROVE", "CLEAR_", "DISPATCH", "HELP")):
        return "Command Intake / Dispatch"
    if any(token in upper for token in ("STATE", "MEMORY", "GOAL", "JOURNAL", "HANDOFF", "ROUTE", "SNAPSHOT", "CONTEXT")):
        return "State / Memory"
    if any(token in upper for token in ("PROCESS", "THREAD", "MONITOR", "RESTART", "SHUTDOWN", "TERMINATE", "CLEANUP", "MAIN")):
        return "Worker Lifecycle / Shutdown"
    if any(token in upper for token in ("CLI", "AUTH", "LIVE", "MODE", "INIT", "INITIALIZE", "STARTUP", "LAUNCH", "OVERLAY")):
        return "Startup / Config / Modes"
    return "Other"


def classify_ui(name: str) -> str:
    lower = name.lower()
    if "screenshot" in lower:
        return "Screenshot Viewer"
    if "image_memory" in lower or ("image" in lower and "memory" in lower):
        return "Image Memory Viewer"
    if "pending" in lower:
        return "Pending Queue UI"
    if lower.startswith("_build_") or "tab" in lower or "card" in lower:
        return "Layout / Tabs"
    if "refresh" in lower or "state" in lower:
        return "Refresh / State Load"
    if any(token in lower for token in ("send_raw", "apply_", "approve_", "clear_", "queue_", "reload", "login", "oauth")):
        return "Command Sink / Actions"
    if any(token in lower for token in ("dialog", "help", "popout", "viewer")):
        return "Dialogs / Popouts"
    return "Other"


def collect_symbols(path: Path, classifier) -> list[Symbol]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: list[Symbol] = []

    def add_symbol(node: ast.AST, kind: str, container: str = "") -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        simple_name = node.name
        qualname = f"{container}.{simple_name}" if container else simple_name
        if isinstance(node, ast.ClassDef):
            calls = []
            args = []
            return_annotation = ""
            return_style = "class"
            yields_value = False
        else:
            calls = sorted(set(iter_calls(node)))
            args = build_arg_rows(node)
            return_annotation = safe_unparse(getattr(node, "returns", None))
            return_style, yields_value = infer_return_style(node)
        domain = classifier(simple_name)
        symbols.append(
            Symbol(
                kind=kind,
                simple_name=simple_name,
                qualname=qualname,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                container=container,
                domain=domain,
                doc=first_doc_line(node),
                calls=calls,
                args=args,
                return_annotation=return_annotation,
                return_style=return_style,
                yields_value=yields_value,
                side_effect_hints=infer_side_effect_hints(simple_name, calls, domain),
            )
        )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            add_symbol(node, "class")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_symbol(child, "method", node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_symbol(node, "function")

    return symbols


def parse_command_dispatch(path: Path) -> dict[str, str]:
    from aurora_command_catalog import parse_dispatch
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    dispatch = parse_dispatch(tree, "command_dispatch")
    dispatch.update({"pyag:" + name: handler for name, handler in parse_dispatch(tree, "pyautogui_dispatch").items()})
    return dispatch


def attach_runtime_command_bindings(symbols: list[Symbol]) -> None:
    commands_by_handler: dict[str, list[str]] = defaultdict(list)
    for command_name, handler_name in parse_command_dispatch(RUNTIME_PATH).items():
        commands_by_handler[handler_name].append(command_name)
    for symbol in symbols:
        symbol.commands = sorted(commands_by_handler.get(symbol.simple_name, []))


def outputs_are_fresh(sources: tuple[Path, ...], outputs: tuple[Path, ...]) -> bool:
    if not all(path.exists() for path in outputs):
        return False
    newest_source = max(path.stat().st_mtime for path in sources)
    return all(path.stat().st_mtime >= newest_source for path in outputs)


def write_index(path: Path, symbols: list[Symbol]) -> None:
    lines = [
        "kind\tsimple_name\tqualname\tline\tend_line\tcontainer\tdomain\targs\treturns\tcommands\teffects\tdoc"
    ]
    for symbol in symbols:
        returns = symbol.return_annotation or symbol.return_style
        row = [
            symbol.kind,
            symbol.simple_name,
            symbol.qualname,
            str(symbol.line),
            str(symbol.end_line),
            symbol.container,
            symbol.domain,
            format_args_for_index(symbol.args),
            returns,
            ",".join(symbol.commands) or "-",
            ",".join(symbol.side_effect_hints) or "-",
            symbol.doc.replace("\t", " ") or "-",
        ]
        lines.append("\t".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_function_skeleton_records(source_path: Path, symbols: list[Symbol]) -> list[str]:
    name_map = resolve_name_map(symbols)
    records: list[str] = []
    for symbol in sorted(symbols, key=lambda item: (item.line, item.qualname.lower())):
        resolved_calls = []
        for call in symbol.calls:
            target = name_map.get(call)
            if target:
                resolved_calls.append(target)
        record = {
            "file": source_path.relative_to(ROOT).as_posix(),
            "kind": symbol.kind,
            "name": symbol.simple_name,
            "qualname": symbol.qualname,
            "line": symbol.line,
            "end_line": symbol.end_line,
            "container": symbol.container,
            "domain": symbol.domain,
            "args": symbol.args,
            "returns": {
                "annotation": symbol.return_annotation,
                "style": symbol.return_style,
                "yields": symbol.yields_value,
            },
            "commands": symbol.commands,
            "internal_calls": sorted(set(resolved_calls))[:40],
            "internal_call_count": len(set(resolved_calls)),
            "side_effect_hints": symbol.side_effect_hints,
            "doc": symbol.doc,
            "analysis": "static_ast_heuristic",
        }
        records.append(json.dumps(record, ensure_ascii=True, sort_keys=True))
    return records


def write_function_skeleton(path: Path, source_path: Path, symbols: list[Symbol]) -> None:
    records = build_function_skeleton_records(source_path, symbols)
    path.write_text("\n".join(records) + "\n", encoding="utf-8")


def write_combined_function_skeleton(path: Path, source_paths: tuple[Path, ...]) -> None:
    records: list[str] = []
    for source_path in source_paths:
        symbols = collect_symbols(source_path, classify_runtime)
        records.extend(build_function_skeleton_records(source_path, symbols))
    path.write_text("\n".join(records) + "\n", encoding="utf-8")


def write_grouped_map(path: Path, title: str, symbols: list[Symbol]) -> None:
    groups: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        groups[symbol.domain].append(symbol)
    lines = [f"# {title}", ""]
    for domain, items in sorted(groups.items(), key=lambda item: item[0].lower()):
        lines.append(f"## {domain}")
        lines.append("")
        for symbol in sorted(items, key=lambda item: (item.line, item.qualname.lower())):
            summary = symbol.doc or "No docstring summary."
            container = f" ({symbol.container})" if symbol.container else ""
            lines.append(
                f"- `{symbol.qualname}` [{symbol.kind}{container}] `L{symbol.line}`: {summary}"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_name_map(symbols: list[Symbol]) -> dict[str, str]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for symbol in symbols:
        grouped[symbol.simple_name].add(symbol.qualname)
    resolved: dict[str, str] = {}
    for simple_name, qualnames in grouped.items():
        if len(qualnames) == 1:
            resolved[simple_name] = next(iter(qualnames))
    return resolved


def call_tree_lines(
    symbols: list[Symbol],
    roots: tuple[str, ...],
    title: str,
    depth_limit: int = 2,
) -> str:
    by_qualname = {symbol.qualname: symbol for symbol in symbols}
    simple_name_map = resolve_name_map(symbols)

    def format_children(symbol: Symbol, depth: int, seen: set[str]) -> list[str]:
        if depth >= depth_limit:
            return []
        lines: list[str] = []
        for call in symbol.calls:
            target = simple_name_map.get(call)
            if not target or target in seen:
                continue
            target_symbol = by_qualname[target]
            lines.append(f"{'  ' * (depth + 1)}- `{target_symbol.qualname}` `L{target_symbol.line}`")
            lines.extend(format_children(target_symbol, depth + 1, seen | {target}))
        return lines

    lines = [f"# {title}", ""]
    for root in roots:
        target = simple_name_map.get(root)
        if not target:
            continue
        symbol = by_qualname[target]
        lines.append(f"## `{symbol.qualname}` `L{symbol.line}`")
        lines.append("")
        lines.append(f"- Domain: {symbol.domain}")
        lines.append(f"- Summary: {symbol.doc or 'No docstring summary.'}")
        lines.append("- Internal calls:")
        children = format_children(symbol, 0, {target})
        if children:
            lines.extend(children)
        else:
            lines.append("  - none resolved from static analysis")
        lines.append("")
    return "\n".join(lines) + "\n"


def generate_maps() -> None:
    RUNTIME_REF_DIR.mkdir(parents=True, exist_ok=True)
    UI_REF_DIR.mkdir(parents=True, exist_ok=True)

    runtime_symbols = collect_symbols(RUNTIME_PATH, classify_runtime)
    ui_symbols = collect_symbols(UI_PATH, classify_ui)
    attach_runtime_command_bindings(runtime_symbols)

    write_index(RUNTIME_OUTPUTS[0], runtime_symbols)
    write_grouped_map(RUNTIME_OUTPUTS[1], "Aurora 2 Runtime Generated Map", runtime_symbols)
    RUNTIME_OUTPUTS[2].write_text(
        call_tree_lines(runtime_symbols, RUNTIME_ROOTS, "Aurora 2 Runtime Generated Call Tree"),
        encoding="utf-8",
    )
    write_function_skeleton(RUNTIME_OUTPUTS[3], RUNTIME_PATH, runtime_symbols)

    write_index(UI_OUTPUTS[0], ui_symbols)
    write_grouped_map(UI_OUTPUTS[1], "Aurora 2 UI Generated Map", ui_symbols)
    UI_OUTPUTS[2].write_text(
        call_tree_lines(ui_symbols, UI_ROOTS, "Aurora 2 UI Generated Call Tree"),
        encoding="utf-8",
    )
    write_function_skeleton(UI_OUTPUTS[3], UI_PATH, ui_symbols)
    write_combined_function_skeleton(CONTROL_PLANE_SKELETON_OUTPUT, CONTROL_PLANE_PATHS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Aurora 2 runtime and UI map references.")
    parser.add_argument(
        "--if-needed",
        action="store_true",
        help="Skip generation when the map outputs are newer than aurora2.py and aurora2_control_panel.py.",
    )
    args = parser.parse_args()

    sources = (RUNTIME_PATH, UI_PATH, *CONTROL_PLANE_PATHS)
    outputs = RUNTIME_OUTPUTS + UI_OUTPUTS + (CONTROL_PLANE_SKELETON_OUTPUT,)
    if args.if_needed and outputs_are_fresh(sources, outputs):
        print("Aurora map references are already up to date.")
        return

    generate_maps()
    print("Generated Aurora 2 runtime and UI map references.")


if __name__ == "__main__":
    # Direct callers use the same staged/checkable entry point as the wrapper.
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.generate_aurora_references import main as generate_references_main
    raise SystemExit(generate_references_main())
