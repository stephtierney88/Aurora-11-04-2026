"""Journal projection contracts without importing the native runtime."""
import ast
from pathlib import Path
import unittest


tree = ast.parse((Path(__file__).resolve().parents[1] / "aurora2.py").read_text(encoding="utf-8-sig"))
scope = {}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                             and n.name == "build_journal_projection"], type_ignores=[]),
             "aurora2.py", "exec"), scope)
project = scope["build_journal_projection"]


class JournalProjectionTests(unittest.TestCase):
    def test_partial_view_reports_retained_not_lifetime_count(self):
        entries = [f"entry {i}" for i in range(10)]
        result = project(entries, 5)
        self.assertTrue(result.startswith("\n".join(f"- entry {i}" for i in range(5))))
        self.assertIn("first 5 of 10 retained entries; 5 later retained entries omitted", result)
        self.assertNotIn("- entry 9", result)
        self.assertEqual(entries, [f"entry {i}" for i in range(10)])

    def test_full_view_preserves_legacy_text_and_duplicate_entries(self):
        self.assertEqual(project(["old", "new", "new"]), "- old\n- new\n- new")

    def test_no_false_omission_for_exact_or_larger_limit(self):
        for limit in (2, 5, None):
            self.assertEqual(project(["a", "b"], limit), "- a\n- b")

    def test_empty_and_zero_limit(self):
        self.assertEqual(project([], 5), "")
        self.assertIn("first 0 of 1 retained entries; 1 later", project(["a"], 0))


if __name__ == "__main__":
    unittest.main()
