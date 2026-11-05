"""Conversation archival/estimate contracts; no runtime/native/provider imports."""
import copy
import unittest

from aurora_conversation import (ConversationArchive, ensure_message_ids, build_conversation_snapshot,
    conversation_text, estimate_model_windows, select_conversation_rows)


def entry(text, **fields):
    return {"role": "assistant", "timestamp": "2026-11-04 12:00:00", "model": "fixture-model",
            "content": {"type": "text", "text": text}, **fields}


class NavigatorContracts(unittest.TestCase):
    def test_decay_explains_snapshot_age_archives_and_unknown_timestamps(self):
        from aurora_conversation import message_metadata
        policy = {"ordinary_enabled": True, "ordinary_minutes": 10, "observed_at": "2026-11-04T20:00:00Z"}
        row = {"timestamp_iso": "2026-11-04T19:49:00Z", "retained": True}
        detail = " · ".join(message_metadata(row, policy))
        self.assertIn("age at snapshot 11.0 min", detail)
        self.assertIn("checked on next history append", detail)
        row["retained"] = False
        detail = " · ".join(message_metadata(row, policy))
        self.assertIn("archived view; no active expiry timer", detail)
        self.assertNotIn("next history append", detail)
        detail = " · ".join(message_metadata({"timestamp": "31"}, policy))
        self.assertIn("age unknown", detail)
        self.assertNotIn("past threshold", detail)

    def test_same_second_identical_messages_get_distinct_stable_ids(self):
        rows = [entry("same"), entry("same")]
        ensure_message_ids(rows)
        original = copy.deepcopy(rows)
        ensure_message_ids(rows)
        self.assertEqual(rows, original)
        self.assertNotEqual(rows[0]["message_id"], rows[1]["message_id"])

    def test_archive_keeps_original_edit_and_deleted_without_resurrecting_context(self):
        rows = [entry("original", Exemption="Pinned")]
        ensure_message_ids(rows)
        archive = ConversationArchive()
        archive.observe(rows)
        rows[0]["content"]["text"] = "edited"
        rows[0].update(edited_by="fixture-model", edited_at="12:01")
        archive.observe(rows)
        active = archive.snapshot({rows[0]["message_id"]})
        self.assertTrue(active["latest"][0]["in_current"])
        self.assertFalse(active["original"][0]["in_current"])
        archive.observe([], reason="removed by DELETE_MSG")
        snapshot = build_conversation_snapshot({"history_store": [], "recent_prompt_history": []}, archive=archive)
        latest, _ = select_conversation_rows(snapshot, "SHOW_ALL")
        original, _ = select_conversation_rows(snapshot, "SHOW_ALL_IN_ORDER")
        events, _ = select_conversation_rows(snapshot, "SHOW_ALL_FULL_TRANSCRIPT")
        self.assertEqual(snapshot["current"]["rows"], [])
        self.assertEqual(latest[0]["text"], "edited")
        self.assertFalse(latest[0]["retained"])
        self.assertEqual(original[0]["text"], "original")
        self.assertEqual([row["event"] for row in events], ["first observed", "changed", "removed by DELETE_MSG"])
        shown = conversation_text({"rows": latest}, show_metadata=True,
            decay={"important_enabled": True, "important_minutes": 30})
        for text in ("sent from fixture-model", "last edited by fixture-model", "Pinned", "30 min", "DELETE_MSG"):
            self.assertIn(text, shown)

    def test_archive_bounds_and_off_mode_are_explicit(self):
        archive = ConversationArchive(max_chars=100, max_rows=2)
        rows = [entry(str(i)*30) for i in range(8)]
        ensure_message_ids(rows)
        archive.observe(rows)
        snapshot = archive.snapshot(set())
        self.assertGreater(snapshot["evicted"], 0)
        self.assertLessEqual(len(snapshot["latest"]), 2)
        self.assertLessEqual(sum(len(r["text"]) for r in snapshot["events"]), 100)
        off = ConversationArchive(enabled=False)
        off.observe(rows)
        self.assertEqual(off.snapshot(set())["latest"], [])

    def test_images_and_unknown_event_fields_never_enter_archive(self):
        row = entry("")
        row["content"] = {"type": "image", "data": "PRIVATE_PIXELS"}
        ensure_message_ids([row])
        archive = ConversationArchive()
        archive.observe([row])
        archive.record_event({"event": "test", "timestamp": "now", "command": "SHOW_RUNTIME", "image": "PRIVATE_PIXELS", "private_field": "PRIVATE_TEXT"})
        text = str(archive.snapshot(set()))
        self.assertNotIn("PRIVATE_PIXELS", text)
        self.assertNotIn("PRIVATE_TEXT", text)

    def test_filters_are_view_only_and_commands_can_be_revealed(self):
        rows = [entry("Hello\nCommands: STATUS()\nObservation: A room"), entry("guidance", role="system")]
        snapshot = build_conversation_snapshot({"history_store": rows, "recent_prompt_history": rows})
        before = copy.deepcopy(snapshot)
        compact, _ = select_conversation_rows(snapshot, "Current context")
        full, _ = select_conversation_rows(snapshot, "Current context", include_system=True, include_commands=True)
        self.assertEqual(len(compact), 1)
        self.assertNotIn("STATUS()", compact[0]["text"])
        self.assertIn("Observation: A room", compact[0]["text"])
        self.assertIn("STATUS()", full[0]["text"])
        self.assertEqual(snapshot, before)

    def test_prepared_system_text_is_optional_and_not_claimed_delivered(self):
        archive = ConversationArchive()
        archive.record_prepared({"prepared_at": "now", "model": "test-model", "sections": {
            "system": {"text": "Example system text", "truncated": False}}})
        snapshot = {"archive": archive.snapshot(set())}
        hidden, _ = select_conversation_rows(snapshot, "SHOW_ALL_FULL_TRANSCRIPT")
        shown, _ = select_conversation_rows(snapshot, "SHOW_ALL_FULL_TRANSCRIPT", include_system=True)
        self.assertEqual(hidden, [])
        self.assertIn("Example system text", shown[0]["text"])
        self.assertIn("delivery is not established", shown[0]["text"])

    def test_model_lanes_use_separate_budgets_unknown_is_not_excluded(self):
        rows = [{"message_id": str(i), "text": "x"*40, "kind": "text"} for i in range(3)]
        estimates = estimate_model_windows(rows, {"Primary": "small", "Review": "large", "Vision": "unknown"}, {"small": 15, "large": 99})
        self.assertEqual(list(estimates[0]["fits"].values()), [True, False, False])
        self.assertTrue(all(estimates[1]["fits"].values()))
        self.assertTrue(all(value is None for value in estimates[2]["fits"].values()))
        self.assertIn("excludes images", estimates[0]["note"])

    def test_move_preserves_first_observed_order_and_copies_are_detached(self):
        rows = [entry("first"), entry("second")]
        ensure_message_ids(rows)
        archive = ConversationArchive()
        archive.observe(rows)
        archive.observe(list(reversed(rows)))
        result = archive.snapshot({rows[0]["message_id"]})
        self.assertEqual([row["text"] for row in result["original"]], ["first", "second"])
        self.assertEqual([row["text"] for row in result["latest"]], ["second", "first"])
        self.assertTrue(all(row["moved"] for row in result["latest"]))
        result["original"][0]["text"] = "mutated view"
        self.assertEqual(archive.snapshot(set())["original"][0]["text"], "first")

    def test_deleting_a_predecessor_is_not_a_message_move(self):
        rows = [entry("first"), entry("second")]
        ensure_message_ids(rows)
        archive = ConversationArchive()
        archive.observe(rows)
        archive.observe(rows[1:])
        self.assertFalse(any(row["moved"] for row in archive.snapshot(set())["latest"]))
        self.assertFalse(any(row["event"] == "position changed" for row in archive.snapshot(set())["events"]))

    def test_missing_edit_time_and_no_exemption_do_not_add_empty_labels(self):
        row = {"role": "assistant", "text": "edited", "model": "same", "edited_by": "same", "edited_at": "", "exemption": "None"}
        shown = conversation_text({"rows": [row]}, show_edits=True, show_metadata=True)
        self.assertIn("last edited by same", shown)
        self.assertNotIn("· ·", shown)
        self.assertNotIn("· None", shown)


if __name__ == "__main__":
    unittest.main()
