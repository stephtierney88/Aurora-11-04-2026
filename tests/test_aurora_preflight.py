import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import aurora_preflight


class PreflightTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows launchers")
    def test_both_launchers_preserve_interpreter_override_and_failure_exit(self):
        with tempfile.TemporaryDirectory(prefix="Aurora missing interpreter ") as folder:
            env = dict(os.environ, AURORA_PYTHON=os.path.join(folder, "missing-python.exe"))
            for name in ("launch_aurora2.cmd", "launch_aurora2_ui.cmd"):
                completed = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c",
                                            str(aurora_preflight.ROOT / name), "--preflight"],
                                           env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)

    def test_resolution_report_does_not_import_runtime(self):
        report = aurora_preflight.inspect_environment(finder=lambda name: None)
        self.assertEqual(report["status"], "missing_imports")
        self.assertIn("requests", report["missing"])
        self.assertIn("aurora_command_protocol", report["missing"])
        self.assertNotIn("os", report["missing"])
        self.assertIn("user_site_visible", report)

    def test_missing_imports_produce_actionable_nonzero_exit(self):
        with patch.object(aurora_preflight, "inspect_environment", return_value={
            "missing": ["example_dependency"], "executable": "test-python",
        }), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(aurora_preflight.main(["--quiet"]), 2)
        self.assertIn("example_dependency", error.getvalue())
        self.assertIn("test-python", error.getvalue())

    def test_display_unknown_is_not_a_calibration_success(self):
        with patch.object(aurora_preflight.os, "name", "posix"):
            report = aurora_preflight.inspect_display_environment()
        self.assertEqual(report["status"], "unsupported_platform")
        self.assertEqual(report["captures_taken"], 0)
        self.assertFalse(report["input_sent"])
        self.assertIn("not a verified", report["coordinate_space"])

    def test_display_json_keeps_import_failure_and_unknown_geometry(self):
        with patch.object(aurora_preflight, "inspect_environment", return_value={"missing": ["dependency"]}), \
             patch.object(aurora_preflight, "inspect_display_environment", return_value={"status": "unknown"}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(aurora_preflight.main(["--display", "--json"]), 2)
        self.assertEqual(json.loads(output.getvalue())["display"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
