"""Report launcher import resolution without importing Aurora or its hardware clients."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import site
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def inspect_display_environment() -> dict:
    """Read caller-visible geometry without capturing pixels or importing Aurora."""
    result = {"status": "unknown", "coordinate_space": "preflight process; not a verified runtime input/capture transform",
              "captures_taken": 0, "input_sent": False,
              "verification": "Compare with the running runtime and a deliberate fresh test capture before coordinate input."}
    if os.name != "nt":
        return dict(result, status="unsupported_platform")
    try:
        import ctypes
        from aurora_panel_layout import monitor_work_areas
        user32 = ctypes.windll.user32
        primary = [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]
        virtual = [user32.GetSystemMetrics(code) for code in (76, 77, 78, 79)]
        awareness = "unknown"
        try:
            user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            awareness = {0: "unaware", 1: "system", 2: "per_monitor"}.get(
                user32.GetAwarenessFromDpiAwarenessContext(user32.GetThreadDpiAwarenessContext()), "unknown")
        except (AttributeError, OSError):
            pass
        result.update(status="observed" if all(value > 0 for value in primary) else "unknown",
                      primary_size=primary, virtual_desktop=dict(zip(("x", "y", "width", "height"), virtual)),
                      monitor_work_areas=monitor_work_areas((0, 0, *primary)), caller_dpi_awareness=awareness)
    except (AttributeError, OSError) as error:
        result["error"] = type(error).__name__
    return result


def required_modules(source: Path) -> list[str]:
    modules = set()
    # The runtime is large; parse its import preamble, not every function at launch.
    with source.open(encoding="utf-8-sig") as handle:
        preamble = []
        for line in handle:
            if line.strip() == "# AURORA_PREFLIGHT_IMPORTS_END":
                break
            preamble.append(line)
    for node in ast.parse("".join(preamble)).body:
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.add(node.module.split(".")[0])
    return sorted(modules - sys.stdlib_module_names)


def inspect_environment(surface: str = "runtime", finder=importlib.util.find_spec) -> dict:
    source = ROOT / ("aurora2_control_panel.py" if surface == "panel" else "aurora2.py")
    modules = []
    for name in required_modules(source):
        try:
            spec = finder(name)
            modules.append({"module": name, "available": spec is not None,
                            "origin": str(spec.origin or "namespace") if spec else ""})
        except (ImportError, ValueError, OSError) as error:
            modules.append({"module": name, "available": False, "error": type(error).__name__})
    missing = [item["module"] for item in modules if not item["available"]]
    return {
        "schema_version": "aurora_preflight_v1", "surface": surface,
        "status": "missing_imports" if missing else "imports_resolved",
        "executable": sys.executable, "prefix": sys.prefix,
        "user_site": site.getusersitepackages(),
        "user_site_visible": site.getusersitepackages() in sys.path,
        "missing": missing, "modules": modules,
        "scope": "Import resolution only; offline startup separately validates loading and initialization.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=("runtime", "panel"), default="runtime")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Print only errors.")
    parser.add_argument("--display", action="store_true", help="Include read-only monitor geometry; no screenshot or input.")
    args = parser.parse_args(argv)
    result = inspect_environment(args.surface)
    if args.display:
        result["display"] = inspect_display_environment()
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["missing"]:
        print(f"Aurora {args.surface} cannot resolve: {', '.join(result['missing'])}", file=sys.stderr)
        print(f"Interpreter: {result['executable']}", file=sys.stderr)
        print("Check this interpreter's environment. AURORA_PYTHON can select another installation.", file=sys.stderr)
        print("Run aurora_preflight.py --json for paths and sandbox/user-site visibility.", file=sys.stderr)
    elif not args.quiet:
        print(f"Aurora {args.surface}: imports resolved using {result['executable']}")
        print(result["scope"])
        if args.display:
            print(json.dumps(result["display"], indent=2))
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
