import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.generate_aurora_references import load_layout, reference_inputs

ROOT = Path(__file__).resolve().parents[1]


def snapshot(folder):
    return {path.relative_to(folder).as_posix(): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in folder.rglob("*") if path.is_file()}


class PortableReferenceTests(unittest.TestCase):
    def test_moved_checkout_isolated_python_check_and_missing_pack(self):
        inputs = reference_inputs(ROOT, load_layout(ROOT))
        with tempfile.TemporaryDirectory(prefix="aurora-portable-") as folder:
            root = Path(folder).resolve() / "checkout with spaces"
            root.mkdir()
            for relative in inputs:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            output = root / "aurora_reference_maps"

            def invoke(*args):
                return subprocess.run(
                    [sys.executable, "-I", str(root / "tools/generate_aurora_references.py"), "--root", str(root), *args],
                    cwd=folder, env=dict(os.environ, CODEX_HOME=str(root / "no-codex-installed")),
                    capture_output=True, text=True, timeout=45,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

            generated = invoke()
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["root"], ".")
            self.assertEqual(manifest["runtime_binding_count"], 368)
            self.assertEqual(manifest["desktop_binding_count"], 19)
            first = json.loads((output / "runtime/runtime-function-skeleton.jsonl").read_text().splitlines()[0])
            self.assertEqual(first["file"], "aurora2.py")
            before = snapshot(output)
            checked = invoke("--check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(snapshot(output), before)
            with (root / "aurora2.py").open("a", encoding="utf-8") as handle:
                handle.write("\n# Changed source must invalidate provenance.\n")
            stale = invoke("--check")
            self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
            self.assertEqual(snapshot(output), before)
            (root / "docs/reference-packs/roadmap-reference.md").unlink()
            missing = invoke()
            self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
            self.assertIn("roadmap-reference.md", missing.stderr)
            self.assertEqual(snapshot(output), before)
            self.assertFalse(list(root.glob(".aurora-refs-*")))


if __name__ == "__main__":
    unittest.main()
