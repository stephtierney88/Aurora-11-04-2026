"""Report launcher import resolution without importing Aurora or its hardware clients."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import site
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


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
    args = parser.parse_args(argv)
    result = inspect_environment(args.surface)
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
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
