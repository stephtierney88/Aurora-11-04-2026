"""Regression checks for refresh recovery, draft ownership and display geometry."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import aurora2_control_panel as panel
from aurora_panel_layout import clamp_window_geometry, load_layout_preferences, save_layout_preferences


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class LayoutTests(unittest.TestCase):
    def test_removed_monitor_and_oversized_window_stay_reachable(self):
        result = clamp_window_geometry({"x": 5000, "y": -2000, "width": 4000, "height": 3000},
                                       [(0, 0, 1280, 720)])
        self.assertGreaterEqual(result["x"], 0)
        self.assertGreaterEqual(result["y"], 0)
        self.assertLessEqual(result["x"] + result["width"], 1280)
        self.assertLessEqual(result["y"] + result["height"], 720)

    def test_negative_monitor_position_is_preserved(self):
        result = clamp_window_geometry({"x": -1750, "y": 50, "width": 1000, "height": 700},
                                       [(0, 0, 1920, 1040), (-1920, 0, 0, 1040)])
        self.assertEqual(result, {"x": -1750, "y": 50, "width": 1000, "height": 700})

    def test_invalid_geometry_values_use_fallbacks(self):
        result = clamp_window_geometry({"x": "nan", "y": True, "width": None, "height": -8}, [(0, 0, 900, 640)])
        self.assertEqual(result["x"], 16)
        self.assertEqual(result["height"], 240)

    def test_preferences_round_trip_and_bad_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.json"
            self.assertEqual(load_layout_preferences(path), {})
            save_layout_preferences(path, {"settings_mode": "hidden", "sections": {"Modes": False}})
            self.assertEqual(load_layout_preferences(path)["sections"], {"Modes": False})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
            for invalid in ('{"version":2}', '[]', '{'):
                path.write_text(invalid)
                self.assertEqual(load_layout_preferences(path), {})

    def test_draft_survives_external_changes_and_converges_after_apply(self):
        app = SimpleNamespace(_settings_variables={}, _settings_observed_values={})
        field = Value()
        sync = lambda value: panel.AuroraControlPanel._sync_setting_var(app, field, value)
        sync("2")
        field.set("7")
        sync("3")
        sync("4")
        self.assertEqual(field.get(), "7")
        sync("7")  # Runtime acknowledges our apply.
        sync("8")  # Untouched field follows subsequent external edits again.
        self.assertEqual(field.get(), "8")
        field.set("draft")
        app._settings_observed_values.clear()
        sync("8")
        self.assertEqual(field.get(), "8")

    def test_failed_text_paint_is_retried_for_identical_content(self):
        app = SimpleNamespace(_text_content_cache={})
        widget = Mock()
        widget.insert.side_effect = [RuntimeError("transient paint failure"), None]
        with self.assertRaises(RuntimeError):
            panel.AuroraControlPanel._write_text(app, widget, "receipt")
        self.assertEqual(app._text_content_cache, {})
        panel.AuroraControlPanel._write_text(app, widget, "receipt")
        self.assertEqual(widget.insert.call_count, 2)
        panel.AuroraControlPanel._write_text(app, widget, "receipt")
        self.assertEqual(widget.insert.call_count, 2)

    def test_refresh_loop_reschedules_even_after_unexpected_failure(self):
        app = SimpleNamespace(_closing=False, _refresh_after_id="old", _last_refresh_perf={},
                              after_cancel=Mock(), refresh_now=Mock(side_effect=RuntimeError("paint")),
                              after=Mock(return_value="new"))
        app.refresh_loop = lambda: panel.AuroraControlPanel.refresh_loop(app)
        with self.assertRaises(RuntimeError):
            app.refresh_loop()
        app.after_cancel.assert_called_once_with("old")
        app.after.assert_called_once_with(panel.REFRESH_INTERVAL_MS, app.refresh_loop)
        self.assertEqual(app._refresh_after_id, "new")

    def test_bad_snapshot_and_failed_render_do_not_commit_file_revision(self):
        app = SimpleNamespace(_closing=False, _last_state_signature=None, last_state_mtime=0,
            state_cache={"version": "old"}, _settings_variables={}, _settings_observed_values={},
            _last_refresh_perf={}, settings_edit_status_var=Value(), refresh_health_var=Value(),
            _drain_settings_transaction_results=Mock(), render_state=Mock(), render_logs=Mock(),
            _get_active_tab_name=lambda: "Dashboard")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            with patch.object(panel, "STATE_PATH", path), patch.object(panel, "decorate_state_processes", side_effect=lambda state: state):
                for invalid in ("{", "[]"):
                    path.write_text(invalid)
                    self.assertFalse(panel.AuroraControlPanel.refresh_now(app))
                    self.assertEqual(app.state_cache, {"version": "old"})
                    self.assertIsNone(app._last_state_signature)
                path.write_text(json.dumps({"version": "new"}))
                app.render_state.side_effect = [RuntimeError("paint"), None]
                self.assertFalse(panel.AuroraControlPanel.refresh_now(app))
                self.assertIsNone(app._last_state_signature)
                self.assertTrue(panel.AuroraControlPanel.refresh_now(app))
                self.assertEqual(app.state_cache, {"version": "new"})
                self.assertEqual(app._last_refresh_perf["recoveries"], 1)
                self.assertIsNotNone(app._last_state_signature)


if __name__ == "__main__":
    unittest.main()
