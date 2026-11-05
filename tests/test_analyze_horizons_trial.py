"""Sanitized trial evidence must not leak memory content or invent timing."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("horizon_analysis", Path(__file__).with_name("analyze_horizons_trial.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class MemoryRevisionEvidenceTests(unittest.TestCase):
    def receipt(self, **changes):
        row = dict(command="UPDATE_PINNED_SHORT_TERM", success=True, changed=True,
                   input="private command text", reason="private reason",
                   before=dict(field="pinned_short_term_actions", count=5, preview="private old plan"),
                   after=dict(field="pinned_short_term_actions", count=1, preview="private new plan"))
        row.update(changes)
        return row

    def test_only_count_timing_and_identity_evidence_is_exported(self):
        start = datetime(2026, 11, 5, 9, 0, 0).timestamp()
        rows = analysis.memory_revision_summary([dict(timestamp="2026-11-05 09:00:12", executed_inference_turn=2,
            memory_command_results=[self.receipt()])], start)
        self.assertEqual(rows[0]["elapsed_seconds_approx"], 12)
        self.assertEqual((rows[0]["before_count"], rows[0]["after_count"]), (5, 1))
        self.assertEqual(rows[0]["inference_turn"], 2)
        self.assertNotIn("private", json.dumps(rows))

    def test_failed_and_unrelated_mutations_are_not_horizon_revisions(self):
        rows = analysis.memory_revision_summary([dict(memory_command_results=[
            self.receipt(success=False), self.receipt(after=dict(field="unknown", count=1))])], 0)
        self.assertEqual(rows, [])

    def test_unknown_or_incomparable_timing_stays_unknown(self):
        for stamp in (None, "bad", "2026-11-05 08:59:59"):
            rows = analysis.memory_revision_summary([dict(timestamp=stamp, memory_command_results=[self.receipt()])],
                datetime(2026, 11, 5, 9, 0, 0).timestamp())
            self.assertIsNone(rows[0]["elapsed_seconds_approx"])

    def test_noop_receipts_remain_distinguishable_from_changes(self):
        rows = analysis.memory_revision_summary([dict(memory_command_results=[self.receipt(changed=False)])], 0)
        self.assertIs(rows[0]["changed"], False)


if __name__ == "__main__":
    unittest.main()
