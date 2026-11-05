"""Regression checks for refresh recovery, draft ownership and display geometry."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import aurora2_control_panel as panel
from aurora_panel_layout import (clamp_window_geometry, load_layout_preferences, save_layout_preferences,
                                fit_popout_window, ui_scale, receipt_tree_items, reconcile_tree_rows)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTree:
    """Treeview contract without Tk/native rendering."""
    def __init__(self, items):
        self.order, self.values = [iid for iid, _ in items], dict(items)
        self.selected, self.focused, self.scroll_x, self.scroll_y = (), "", .4, 0
        self.writes = []

    def get_children(self): return tuple(self.order)
    def selection(self): return self.selected
    def selection_set(self, selected): self.selected = tuple(selected)
    def focus(self, value=None):
        if value is not None: self.focused = value
        return self.focused
    def xview(self): return self.scroll_x, 1
    def yview(self): return self.scroll_y, 1
    def xview_moveto(self, value): self.scroll_x = value
    def yview_moveto(self, value): self.scroll_y = value
    def delete(self, *items):
        for iid in items:
            self.order.remove(iid)
            self.values.pop(iid)
            self.writes.append(("delete", iid))
        self.selected = tuple(iid for iid in self.selected if iid not in items)
    def insert(self, parent, index, *, iid, values):
        self.order.insert(index, iid)
        self.values[iid] = values
        self.writes.append(("insert", iid))
    def item(self, iid, option=None, *, values=None):
        if values is not None:
            self.values[iid] = values
            self.writes.append(("item", iid))
        return self.values[iid]
    def move(self, iid, parent, index):
        self.order.remove(iid)
        self.order.insert(index, iid)
        self.writes.append(("move", iid))


class LayoutTests(unittest.TestCase):
    def test_receipt_identity_survives_status_changes_without_collapsing_duplicates(self):
        row = {"kind": "command_receipt", "request_id": "long-request", "client_id": "panel",
               "timestamp": "2026-11-04T12:00:00-08:00", "command_name": "SET_NEXT_INFERENCE", "status": "queued"}
        before, _ = receipt_tree_items([row, row, {}, {}])
        after, mapping = receipt_tree_items([{**row, "status": "completed"}, row, {}, {}])
        self.assertEqual([iid for iid, _ in before], [iid for iid, _ in after])
        self.assertEqual(len(mapping), 4)
        self.assertEqual(after[0][1][2], "completed")
        another, _ = receipt_tree_items([{**row, "client_id": "other"}])
        self.assertNotEqual(before[0][0], another[0][0])

    def test_receipt_reconciliation_preserves_reading_anchor_and_updates_only_changed_cells(self):
        tree = FakeTree([("a", ("one",)), ("b", ("two",)), ("c", ("three",)), ("d", ("four",))])
        tree.selected, tree.focused, tree.scroll_y = ("c",), "c", .5
        reconcile_tree_rows(tree, [("new", ("new",)), ("a", ("one",)), ("b", ("two",)), ("c", ("updated",)), ("d", ("four",))])
        self.assertEqual(tree.selected, ("c",))
        self.assertEqual(tree.focused, "c")
        self.assertEqual(tree.scroll_y, .6)  # Same top receipt after an insertion above it.
        self.assertEqual(tree.scroll_x, .4)
        self.assertEqual(tree.writes, [("insert", "new"), ("item", "c")])
        tree.writes.clear()
        reconcile_tree_rows(tree, [(iid, tree.values[iid]) for iid in tree.order])
        self.assertEqual(tree.writes, [])
        reconcile_tree_rows(tree, [("d", ("four",)), ("a", ("one",))])
        self.assertEqual(tree.order, ["d", "a"])
        self.assertEqual(tree.selected, ())
        reconcile_tree_rows(tree, [])
        self.assertEqual(tree.order, [])

    def test_small_strip_and_offscreen_history_are_clamped(self):
        result = clamp_window_geometry({"x": 900, "y": 680, "width": 1000, "height": 100},
                                      [(0, 0, 1280, 720)], minimum=(520, 74))
        self.assertEqual(result["height"], 100)
        self.assertLessEqual(result["x"] + result["width"], 1280)
        self.assertLessEqual(result["y"] + result["height"], 720)

    def test_display_scale_and_explicit_legacy_pixels(self):
        widget = SimpleNamespace(winfo_fpixels=lambda value: 288)
        with patch.dict("os.environ", {"AURORA_PANEL_SCALE": ""}):
            self.assertEqual(ui_scale(widget), 3.0)
        with patch.dict("os.environ", {"AURORA_PANEL_SCALE": "1"}):
            self.assertEqual(ui_scale(widget), 1.0)
        with patch.dict("os.environ", {"AURORA_PANEL_SCALE": "nan"}):
            self.assertEqual(ui_scale(widget), 1.0)

    def test_popout_uses_absolute_negative_monitor_coordinates(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 1280
        window.winfo_screenheight.return_value = 720
        parent = SimpleNamespace(winfo_x=lambda: -1200, winfo_y=lambda: 20)
        user32 = Mock()
        with patch("aurora_panel_layout.monitor_work_areas", return_value=[(-1280, 0, 0, 720)]), \
             patch("aurora_panel_layout.ctypes.windll", SimpleNamespace(user32=user32), create=True):
            geometry = fit_popout_window(window, 1380, 920, parent)
            window.after_idle.call_args.args[0]()
        self.assertLess(geometry["x"], 0)
        self.assertLessEqual(geometry["height"], 656)
        self.assertEqual(user32.SetWindowPos.call_args.args[2:4], (geometry["x"], geometry["y"]))
        self.assertEqual(window.geometry.call_count, 1)  # No ambiguous Tk negative-offset placement.

    def test_popout_fallback_stays_on_reachable_primary_monitor(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 1280
        window.winfo_screenheight.return_value = 720
        parent = SimpleNamespace(winfo_x=lambda: -1200, winfo_y=lambda: 20)
        with patch("aurora_panel_layout.monitor_work_areas", return_value=[(-1280, 0, 0, 720), (0, 0, 1280, 720)]), \
             patch("aurora_panel_layout.ctypes.windll", SimpleNamespace(), create=True):
            fit_popout_window(window, 1380, 920, parent)
            window.after_idle.call_args.args[0]()
        self.assertRegex(window.geometry.call_args.args[0], r"^1248x656\+\d+\+\d+$")

    def test_closed_popout_does_not_place_a_destroyed_window(self):
        window = Mock()
        window.winfo_exists.return_value = False
        with patch("aurora_panel_layout.monitor_work_areas", return_value=[(0, 0, 1280, 720)]):
            fit_popout_window(window, 1000, 800)
            window.after_idle.call_args.args[0]()
        self.assertEqual(window.geometry.call_count, 1)

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
        widget.yview.return_value = (0.4, 0.7)
        widget.xview.return_value = (0.0, 1.0)
        widget.tag_ranges.return_value = ("2.0", "2.7")
        widget.insert.side_effect = [RuntimeError("transient paint failure"), None]
        with self.assertRaises(RuntimeError):
            panel.AuroraControlPanel._write_text(app, widget, "receipt")
        self.assertEqual(app._text_content_cache, {})
        panel.AuroraControlPanel._write_text(app, widget, "receipt")
        self.assertEqual(widget.insert.call_count, 2)
        widget.yview_moveto.assert_called_with(0.4)
        widget.tag_add.assert_called_with("sel", "2.0", "2.7")
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
