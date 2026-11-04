"""Generate/check Aurora reference artifacts using only the Python standard library."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from aurora_command_catalog import build_command_catalog
from tools.aurora_maps import generate_maps as mapper

GENERATOR_VERSION = "1.0.0"


def normalized_bytes(path: Path) -> bytes:
    return path.read_text(encoding="utf-8-sig").encode("utf-8")


def publish_artifact(target: Path, data: bytes) -> None:
    """Atomically publish with destination-directory access rules.

    Moving a file out of TemporaryDirectory can retain its private Windows ACL,
    making a sandbox-generated artifact unreadable to the normal user.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".aurora-ref-{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def generated_paths() -> set[str]:
    return {"commands/" + name for name in
            ("commands-low.md", "commands-medium.md", "commands-high.md", "commands-index.tsv", "commands.json")} | {
        "runtime/" + name for name in ("runtime-symbol-index.tsv", "runtime-generated-map.md",
        "runtime-generated-call-tree.md", "runtime-function-skeleton.jsonl", "control-plane-function-skeleton.jsonl")
    } | {"ui/" + name for name in ("ui-symbol-index.tsv", "ui-generated-map.md",
        "ui-generated-call-tree.md", "ui-function-skeleton.jsonl")}


def load_layout(root: Path) -> dict:
    layout = json.loads((root / "tools/aurora_maps/reference_layout.json").read_text(encoding="utf-8-sig"))
    for group, entries in layout.items():
        if group not in {"commands", "runtime", "ui", "reference_packs"} or not isinstance(entries, dict):
            raise ValueError("Invalid reference layout group")
        for value in entries.values():
            path = Path(value)
            if path.is_absolute() or path.parts[0] != group or len(path.parts) != 2 or ".." in path.parts:
                raise ValueError(f"Invalid reference layout path: {value}")
    return layout


def reference_inputs(root: Path, layout: dict) -> dict[str, str]:
    """Validate every source before publishing any generated file."""
    sources = {"aurora2.py", "aurora2_control_panel.py",
               "tools/generate_aurora_references.py", "tools/aurora_maps/generate_maps.py",
               "tools/aurora_maps/reference_layout.json", "tools/aurora_maps/PROVENANCE.md",
               "regenerate_aurora_skill_refs.ps1", "docs/notes/aurora_current_status.md",
               "docs/notes/aurora_runtime_roadmap.md"}
    sources.update(path.relative_to(mapper.ROOT).as_posix() for path in mapper.CONTROL_PLANE_PATHS)
    for group, entries in layout.items():
        for relative in entries.values():
            if group == "reference_packs":
                sources.add("docs/reference-packs/" + Path(relative).name)
            elif relative not in generated_paths():
                sources.add("aurora_reference_maps/" + relative)
    return {name: hashlib.sha256(normalized_bytes(root / name)).hexdigest() for name in sorted(sources)}


def write_catalog(output: Path, catalog: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows = catalog["commands"]
    low = ["# Aurora commands — compact", "", "Callable bindings only. See commands.json for aliases, provenance and contract coverage.", ""]
    medium = ["# Aurora commands — summaries", ""]
    high = ["# Aurora commands — details", "", "Help signatures are documentation; only contracts marked pre_dispatch are validated before a batch executes.", ""]
    index = io.StringIO(newline="")
    writer = csv.writer(index, delimiter="\t", lineterminator="\n")
    keys = ("command", "signature", "category", "handler", "summary")
    writer.writerow(keys)
    for row in rows:
        writer.writerow([row[key] for key in keys])
        low.append(f"- `{row['signature']}`")
        medium.append(f"- `{row['signature']}`: {row['summary']}")
        high.extend([f"### {row['command']}", "", f"- Signature: `{row['signature']}` ({row['signature_source']})",
                     f"- Summary: {row['summary']}", f"- Handler: `{row['handler']}`",
                     f"- Binding: {row['binding_kind']}", f"- Aliases: {', '.join(row['aliases']) or 'none'}",
                     f"- Parameter validation: {row['contract']['parameter_validation']}",
                     f"- Effects: {row['contract']['effects']}", ""])
        if row["contract"]["parameter_validation"] == "pre_dispatch":
            high.extend(["Arguments are positional; parameter metadata defines defaults and omitted-value behavior.", ""])
            if "action_routing" in row["contract"]:
                high.extend(["- Action routing: " + row["contract"]["action_routing"], ""])
            for parameter in row["contract"]["parameters"]:
                high.append("- Parameter: `" + json.dumps(parameter, sort_keys=True, ensure_ascii=False) + "`")
            result = row["contract"]["result"]
            if "setting_key" in row["contract"]:
                high.extend(["", "- Registered setting: `" + row["contract"]["setting_key"] + "`",
                             "- Runtime lock: " + (row["contract"]["lock_key"] or "none"),
                             "- Apply timing: " + row["contract"]["apply_timing"],
                             "- Related effects: " + row["contract"]["related_effects"]])
            high.extend(["", f"- Result protocol: `{result['protocol']}`"])
            if "receipt_field" in result:
                high.append("- Receipt field: `" + result["receipt_field"] + "`")
            if "verification" in result:
                high.append("- Verification: " + result["verification"])
                high.append("- Failure policy: " + result["failure_policy"])
            high.append("")
    for filename, lines in (("commands-low.md", low), ("commands-medium.md", medium), ("commands-high.md", high)):
        (output / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "commands-index.tsv").write_text(index.getvalue(), encoding="utf-8")
    (output / "commands.json").write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate(root: Path, *, check: bool = False, if_needed: bool = False) -> dict:
    """Stage complete output, then compare or publish; never read personal skills."""
    root = root.resolve()
    destination = root / "aurora_reference_maps"
    layout = load_layout(root)
    inputs = reference_inputs(root, layout)
    manifest_path = destination / "manifest.json"
    if if_needed and manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            outputs = previous["output_sha256"]
            if previous.get("input_sha256") == inputs and outputs and all(
                hashlib.sha256(normalized_bytes(destination / name)).hexdigest() == digest
                for name, digest in outputs.items()
            ):
                return {"status": "current", "changed": []}
        except (OSError, ValueError, KeyError):
            pass
    with tempfile.TemporaryDirectory(prefix=".aurora-refs-", dir=root) as folder:
        stage = Path(folder).resolve()
        if stage.parent != root:
            raise ValueError("Unexpected staging directory")
        mapper.configure(root, stage)
        mapper.generate_maps()
        catalog = build_command_catalog(root)
        write_catalog(stage / "commands", catalog)
        expected = {value for entries in layout.values() for value in entries.values()}
        if not generated_paths().issubset(expected):
            raise ValueError("Reference layout omits generated outputs")
        for group, entries in layout.items():
            for relative in set(entries.values()):
                if relative in generated_paths():
                    continue
                source = root / ("docs/reference-packs/" + Path(relative).name if group == "reference_packs"
                                 else "aurora_reference_maps/" + relative)
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(normalized_bytes(source))
        output_hashes = {name: hashlib.sha256(normalized_bytes(stage / name)).hexdigest() for name in sorted(expected)}
        manifest = {"schema_version": "aurora_reference_manifest_v2", "generator_version": GENERATOR_VERSION,
                    "root": ".", **layout, "input_sha256": inputs, "output_sha256": output_hashes,
                    "runtime_binding_count": catalog["runtime_binding_count"],
                    "desktop_binding_count": catalog["desktop_binding_count"]}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        expected.add("manifest.json")
        changed = [name for name in sorted(expected) if not (destination / name).exists()
                   or normalized_bytes(destination / name) != normalized_bytes(stage / name)]
        if not check:
            # Publish manifest last, so any interrupted publication is detectable by --check.
            for name in [value for value in changed if value != "manifest.json"] + (["manifest.json"] if "manifest.json" in changed else []):
                target = destination / name
                publish_artifact(target, (stage / name).read_bytes())
        return {"status": ("stale" if changed else "current") if check else "generated",
                "changed": changed, "runtime_bindings": catalog["runtime_binding_count"],
                "desktop_bindings": catalog["desktop_binding_count"], "checked_files": len(expected)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Compare without publishing or updating timestamps.")
    parser.add_argument("--if-needed", action="store_true", help="Skip when source and output hashes match.")
    args = parser.parse_args()
    try:
        result = generate(args.root, check=args.check, if_needed=args.if_needed and not args.check)
    except (OSError, ValueError, SyntaxError) as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 1 if result["status"] == "stale" else 0


if __name__ == "__main__":
    raise SystemExit(main())
