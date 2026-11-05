"""Opt-in real Tk/runtime checks in a disposable, offline source copy.

Run with the canonical Aurora Python. --interactive retains the checked fixture
for native visual/keyboard QA for up to 15 minutes; close it to finish cleanup.
--hidden withdraws Tk windows and skips displayed-layout assertions; it still
checks real settings transactions, draft preservation, refresh and Dashboard data.
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from offline_runtime_smoke import CONTRACT_IMPORT_GUARD, CONTRACT_FIXTURE

ROOT = Path(__file__).resolve().parents[1]
COPY_FILES = (
    "aurora_task_continuation.py",
    "aurora_delivery_receipts.py",
    "aurora_conversation_delivery.py",
    "aurora_openai_signin_reference.png",
    "aurora_agent_controls.py", "aurora_chatgpt_auth.py", "aurora_chatgpt_transport.py", "aurora_chatgpt_panel.py",
    "aurora_conversation_navigator.py",
    "aurora_gameplay_scene.py", "aurora_goal_store.py",
    "aurora_switchboard.py", "aurora_command_catalog.py", "aurora_portal_spinner.png", "aurora_flow_emblem.png",
    "aurora2.py", "aurora2_control_panel.py", "aurora_panel_layout.py", "aurora_preflight.py",
    "aurora_runtime_work.py", "aurora_input_ownership.py", "aurora_responses_reasoning.py", "aurora_capture_store.py", "aurora_capture_provenance.py", "aurora_capture_geometry.py", "aurora_command_protocol.py", "aurora_command_contracts.py", "aurora_default_profiles.py",
    "aurora_pending_commands.py", "aurora_history_controls.py", "aurora_episodic_retrieval.py", "aurora_search_query.py", "aurora_retrieval_results.py", "aurora_retrieval_commands.py", "aurora_conversation.py", "aurora_control_plane.py", "aurora_codex_oauth.py", "aurora_settings_registry.py",
    "aurora_settings_transactions.py", "launch_aurora2.cmd", "launch_aurora2_ui.cmd",
)


def check_visible_layout(app, pump):
    from aurora_panel_layout import ui_scale, monitor_work_areas
    scale = ui_scale(app)
    work_area = monitor_work_areas()[0]
    def size(width, height):
        return min(round(width * scale), work_area[2]-work_area[0]-64), min(round(height * scale), work_area[3]-work_area[1]-100)
    app.state("normal")
    pump(.4)  # Wait for the native restore transition before sizing/docking.
    width, height = size(1000, 700)
    app.geometry(f"{width}x{height}+30+30")
    pump()
    app._apply_settings_mode("docked")
    # Sash placement is scheduled after Tk geometry events; wait for the
    # observable layout instead of assuming it settled within 400 ms.
    deadline = time.monotonic() + 3
    while True:
        pump(0.1)
        widths = {"settings": app.settings_view.winfo_width(), "workspace": app.workspace_frame.winfo_width()}
        if (widths["settings"] >= 390 and widths["workspace"] >= 400) or time.monotonic() >= deadline:
            break
    assert widths["settings"] >= 390 and widths["workspace"] >= 400, {
        **widths, "root": app.geometry(), "mode": app.settings_mode, "panes": app.content_panes.panes(),
        "content": (app.content_panes.winfo_width(), app.content_panes.winfo_height()),
        "header": (app.header_frame.winfo_width(), app.header_frame.winfo_height()),
        "status": (app.runtime_status_frame.winfo_width(), app.runtime_status_frame.winfo_height()),
        "actions": (app.runtime_actions.winfo_width(), app.runtime_actions.winfo_height()),
        "detail": (app.runtime_status_detail.winfo_width(), app.runtime_status_detail.winfo_height()),
        "sash_pending": str(app._sash_after_id)}
    for _ in range(3):
        app._apply_settings_mode("hidden")
        pump(.06)
        app._apply_settings_mode("docked")
        pump(.2)
        assert app.settings_view.winfo_width() >= 390 and app.workspace_frame.winfo_width() >= 400
    app._apply_settings_mode("expanded")
    pump()
    assert len(app.content_panes.panes()) == 1 and app.settings_view.winfo_width() > 900
    app.settings_filter_var.set("episodic")
    pump()
    visible_sections = [section.title for section in app.settings_sections if section.winfo_ismapped()]
    assert "Episodic Memory" in visible_sections, visible_sections
    assert len(visible_sections) < len(app.settings_sections)
    app._expand_all_settings(False)
    pump()
    assert all(not section.expanded for section in app.settings_sections)
    app._expand_all_settings(True)
    app.settings_filter_var.set("")
    app.show_tab("Dashboard")
    pump()
    print("Checking drafts and settings transactions", flush=True)
    assert app.settings_mode == "hidden"

    sizes = []
    views = []
    header_sizes = []
    for index, (width, height) in enumerate((size(900, 640), size(1180, 760))):
        app.geometry(f"{width}x{height}+30+30")
        pump()
        app.compact_header_var.set(False)
        app._apply_header_layout()
        pump(.2)
        expanded_height = app.header_frame.winfo_height()
        expanded_workspace = app.content_panes.winfo_height()
        assert app.header_utilities.winfo_ismapped() and app.header_reset_button.winfo_ismapped()
        app.compact_header_var.set(True)
        app._apply_header_layout()
        pump(.2)
        compact_height = app.header_frame.winfo_height()
        assert compact_height < expanded_height, (compact_height, expanded_height, width)
        assert app.content_panes.winfo_height() > expanded_workspace
        assert not app.header_utilities.winfo_ismapped() and not app.header_reset_button.winfo_ismapped()
        assert app.header_options_button.winfo_ismapped()
        assert not app.refresh_health_label.winfo_ismapped(), "Empty refresh status wastes a header row"
        header_sizes.append({"width": width, "compact": compact_height, "expanded": expanded_height,
                             "workspace_gain": app.content_panes.winfo_height() - expanded_workspace})
        for name, page in app.page_views.items():
            assert app.show_tab(name), name
            deadline = time.monotonic() + 2
            while not (page.canvas.winfo_ismapped() and page.vertical.winfo_ismapped()) and time.monotonic() < deadline:
                pump(0.05)
            assert page.canvas.winfo_ismapped() and page.vertical.winfo_ismapped(), (name, app._get_active_tab_name(), app.state())
            assert app.runtime_shutdown_button.winfo_ismapped(), name
            assert app.runtime_shutdown_button.winfo_rooty() < page.canvas.winfo_rooty(), name
            for button in (app.signin_buttons.sign_in, app.signin_buttons.openai):
                assert button.winfo_ismapped(), "Sign-in entry point hidden"
                assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + app.winfo_width(), "Sign-in button clipped"
            if name == "Dashboard":
                assert page.inner.winfo_width() <= page.canvas.winfo_width() + 1
                for card in app.dashboard_cards:
                    assert card.winfo_x()+card.winfo_width() <= card.master.winfo_width()+1, "Dashboard card overflow"
            if name == "The Switchboard":
                board = app.switchboard
                for level in ("Overview", "Groups", "Functions"):
                    board.level.set(level)
                    board.draw_flow(force=True)
                    pump()
                    for tag, box, items in board._flow_boxes:
                        for item in items:
                            bounds = board.graph.bbox(item)
                            assert bounds[0] >= box[0] and bounds[2] <= box[2], (level, tag, "text width", box, bounds)
                            assert bounds[1] >= box[1] and bounds[3] <= box[3], (level, tag, "text height", box, bounds)
                    boxes = [box for _tag, box, _items in board._flow_boxes]
                    for i, a in enumerate(boxes):
                        for b in boxes[i+1:]:
                            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (level, "overlapping cards", a, b)
                board.level.set("Overview")
                board.draw_flow(force=True)
            if name == "Conversation":
                assert app.conversation_navigator.winfo_height() >= round(170 * scale), "Conversation was squeezed below its readable minimum"
                # On short/high-DPI displays, preserve readable messages and let
                # the page scroll to the composer instead of crushing the chat.
                page.canvas.yview_moveto(1)
                pump()
                assert app.conversation_send_button.winfo_rooty() >= page.canvas.winfo_rooty(), "Composer scrolled above the page"
                assert app.conversation_send_button.winfo_rooty() + app.conversation_send_button.winfo_height() <= page.canvas.winfo_rooty() + page.canvas.winfo_height(), "Composer is not reachable by scrolling"
                page.canvas.yview_moveto(0)
                pump()
            if index == 0:
                views.append(name)
        sizes.append({"width": app.winfo_width(), "height": app.winfo_height()})
    assert len(views) == 24
    app.toggle_maximized()
    pump()
    assert app.state() == "zoomed", app.state()
    app.toggle_maximized()
    pump()
    assert app.state() == "normal"
    assert app.winfo_width() == size(1180, 760)[0], app.winfo_width()
    app._header_layout_proof = header_sizes
    return sizes


def check_dashboard_refresh_stability(app, pump, hidden=False):
    """Alternating synthetic snapshots exercise real Tk, without native input/capture."""
    import copy
    from tkinter import font as tkfont
    from unittest.mock import patch
    import aurora2_control_panel as panel
    # Do not let periodic runtime exports replace this controlled UI dataset.
    if app._refresh_after_id is not None:
        app.after_cancel(app._refresh_after_id)
        app._refresh_after_id = None
    geometry = app.geometry()
    try:
        fixture = copy.deepcopy(app.dashboard_snapshot)
        rows = [{"kind": "command_receipt", "timestamp": f"2026-11-04T12:00:{i:02d}-08:00",
                 "request_id": f"fixture-receipt-{i}-" + "long-identifier-" * 12,
                 "client_id": "offline-dashboard-fixture", "command_name": "SET_NEXT_INFERENCE_CONFIGURATION",
                 "status": "completed", "delivery_status": "duplicate_suppressed", "terminal": True,
                 "detail": "Sanitized synthetic lifecycle metadata. " * 20} for i in range(12)]
        fixture["events"]["rows"] = rows
        with patch.object(panel, "build_operator_dashboard", side_effect=lambda *_args, **_kw: copy.deepcopy(fixture)):
            app.refresh_dashboard()
            pump()
            tree = app.dashboard_events_tree
            identifiers = tree.get_children()
            selected = identifiers[6]
            tree.selection_set(selected)
            tree.focus(selected)
            tree.yview_moveto(.25)
            tree.xview_moveto(.3)
            pump()
            initial_x, initial_y = tree.xview()[0], tree.yview()[0]
            def children(widget):
                return 1 + sum(children(child) for child in widget.winfo_children())
            widget_count = children(app)
            for index in range(36):
                fixture["observed_at"] = f"synthetic refresh {index}"
                fixture["models"]["text"] = "fixture-primary-with-a-long-model-identifier" if index % 2 else "fixture-short"
                rows[6]["status"] = "uncertain" if index % 2 else "completed"
                rows[6]["detail"] = "No automatic replay. " * (50 if index % 2 else 2)
                app.refresh_dashboard()
                pump(.025)
                assert tree.get_children() == identifiers, "Receipt rows were recreated/reordered"
                assert tree.selection() == (selected,) and tree.focus() == selected
                if index < 6:
                    assert abs(tree.xview()[0] - initial_x) < .01
                    assert abs(tree.yview()[0] - initial_y) < .01
                assert rows[6]["status"] == tree.item(selected, "values")[2]
                assert app.dashboard_text.get("1.0", "end-1c") == app.dashboard_popout_text.get("1.0", "end-1c")
                if index in (7, 19, 31) and not hidden:
                    app.show_tab("Conversation")
                    pump(.06)
                    app.show_tab("Dashboard")
                    app.compact_header_var.set(not app.compact_header_var.get())
                    app._apply_header_layout()
                    pump(.12)
            assert children(app) == widget_count, "Refresh accumulated widgets"
            app._show_dashboard_receipt()
            assert rows[6]["request_id"] in app.dashboard_receipt_text.get("1.0", "end-1c")
            app.open_dashboard_receipt()
            if hidden:
                app.dashboard_receipt_window.withdraw()
            pump()
            pending = [app.dashboard_receipt_window]
            content = []
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if widget.winfo_class() == "Text":
                    content.append(widget.get("1.0", "end-1c"))
            assert any(rows[6]["request_id"] in value and rows[6]["detail"] in value for value in content)
            app.dashboard_receipt_window.destroy()
            assert tree.bind("<Return>") and tree.bind("<Double-Button-1>")
            if not hidden:
                # Reveal the table inside the scrolling page for a real row bbox.
                page = app.page_views["Dashboard"]
                page.canvas.yview_moveto(0)
                tree.see(selected)
                pump()
                bbox = tree.bbox(selected)
                line_height = tkfont.nametofont("TkDefaultFont").metrics("linespace")
                assert bbox and bbox[3] >= line_height, (bbox, line_height)
            # Same request/client may have multiple distinct receipts. Keep them
            # separate, and clear a selection when its exact receipt leaves view.
            fixture["events"]["rows"] = [rows[0], rows[0], {}, {}]
            app.refresh_dashboard()
            pump()
            assert len(tree.get_children()) == 4 and not tree.selection()
            assert "Select a receipt" in app.dashboard_receipt_text.get("1.0", "end-1c")
            fixture["events"]["rows"] = []
            app.refresh_dashboard()
            assert not tree.get_children()
        return {"updates": 36, "selection_focus_scroll_preserved": True, "stable_row_ids": True,
                "no_widget_accumulation": True, "long_identifiers_and_detail_inspectable": True,
                "duplicate_and_missing_identity_rows": True, "empty_list_clears_selection": True,
                "scaled_row_height_checked": not hidden,
                "scope": "Synthetic Tk refresh/geometry checks, not live-turn or mixed-DPI pixel qualification"}
    finally:
        app.compact_header_var.set(True)
        app._apply_header_layout()
        app.geometry(geometry)
        app.refresh_dashboard(app.state_cache)
        app._refresh_after_id = app.after(250, app.refresh_loop)



def check_panel(work, interactive=False, hidden=False):
    import faulthandler
    faulthandler.dump_traceback_later(25, repeat=True)
    os.chdir(work)
    sys.path.insert(0, str(work))
    import aurora2_control_panel as panel
    from aurora_control_plane import read_jsonl_from
    from aurora_panel_layout import monitor_work_areas

    if hidden:
        panel.save_layout_preferences(panel.LAYOUT_PATH, {"maximized": False})
    panel.write_pid_file(panel.CONTROL_PANEL_PID_PATH, os.getpid())
    app = panel.AuroraControlPanel()
    import aurora_chatgpt_panel as connection_panel
    # Both native and programmatic QA can click sign-in without opening a real
    # authentication page, reading credentials or changing a saved account.
    class FixtureAuth:
        calls = []
        connected = False
        def status(self):
            time.sleep(.05)
            return {"active": "fixture-account" if self.connected else "", "accounts": [
                {"id": "fixture-account", "email": "offline fixture", "connected": True, "plan_enabled": True}
            ] if self.connected else []}
        def login(self, account_id=None, *, cancel, notify):
            self.calls.append(account_id)
            notify("Offline sign-in fixture; no browser, credentials or provider request.")
            if cancel.wait(.25):
                raise connection_panel.ChatGPTAuthError("Fixture sign-in canceled.")
            type(self).connected = True
            return "fixture-account"
    connection_panel.ChatGPTAuth = FixtureAuth
    if hidden:
        app.withdraw()
    app.title("Aurora 2 - isolated GUI validation")
    errors = []
    app.report_callback_exception = lambda kind, value, trace: errors.append(f"{kind.__name__}: {value}")
    def unexpected_dialog(title, message, **_kwargs):
        raise AssertionError(f"Unexpected modal {title}: {message}")
    panel.messagebox.showerror = panel.messagebox.showinfo = panel.messagebox.askyesno = unexpected_dialog
    if hidden:
        app._open_settings_text_dialog = lambda title, text: None

    def pump(seconds=0.12):
        until = time.monotonic() + seconds
        while time.monotonic() < until and not app._closing:
            app.update()
            time.sleep(0.01)
        assert not errors, errors

    def until(predicate, label, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        raise AssertionError(f"Timed out: {label}; {app._last_refresh_perf}; {app.settings_transaction_status_var.get()}")

    def snapshot():
        # A Windows replace can briefly deny a concurrent reader. Production
        # refresh already retries; keep the fixture's direct assertions bounded.
        for attempt in range(5):
            try:
                return json.loads(panel.STATE_PATH.read_text(encoding="utf-8-sig"))
            except (PermissionError, FileNotFoundError, json.JSONDecodeError):
                if attempt == 4:
                    raise
                pump(.03)

    def receipt(request_id):
        rows, _ = read_jsonl_from(panel.CMD_LOG_PATH)
        return next((row for row in reversed(rows) if row.get("request_id") == request_id
                     and row.get("event") == "command_result"), None)

    def command(text):
        record = app.send_raw(text)
        until(lambda: receipt(record["request_id"]), text)
        result = receipt(record["request_id"])
        assert result["status"] == "processed", result
        return {"request_id": record["request_id"], "status": result["status"], "command": text}

    try:
        print("Checking layout and navigation" if not hidden else "Hidden Tk: skipping displayed-layout assertions", flush=True)
        until(lambda: app.state_cache.get("settings", {}).get("version"), "fresh settings")
        assert app._last_refresh_perf.get("consecutive_errors", 0) == 0, app._last_refresh_perf
        assert app._get_active_tab_name() == "Conversation"
        before_auth = snapshot()["modes"]["auth"]
        app.ui_preferences["last_signin_provider"] = "unavailable-future-provider"
        app.signin_buttons.sign_in.invoke()
        app.signin_buttons.sign_in.invoke()  # Coalesce with the pending status read.
        until(lambda: app.ui_preferences.get("last_signin_provider") == "openai", "first provider sign-in")
        assert FixtureAuth.calls == [None], FixtureAuth.calls
        connection = app.chatgpt_connection
        until(lambda: not connection.worker.is_alive(), "auth worker completed")
        connection.close()
        until(lambda: not connection.winfo_exists(), "auth window close")
        app.signin_buttons.openai.invoke()
        until(lambda: len(FixtureAuth.calls) == 2, "explicit OpenAI sign-in")
        assert FixtureAuth.calls[-1] == "fixture-account", "Saved registration not resumed"
        connection = app.chatgpt_connection
        connection.cancel_sign_in()
        until(lambda: not connection.worker.is_alive(), "sign-in cancellation")
        # Reopening a closing-but-existing connection must clear closing, rather
        # than briefly displaying a window its poll loop immediately destroys.
        connection.close()
        same = connection_panel.ChatGPTConnection.open(app)
        assert same is connection and not same.closing
        pump(.2)
        assert same.winfo_exists()
        same.close()
        until(lambda: not same.winfo_exists(), "reopened connection cleanup")
        assert snapshot()["modes"]["auth"] == before_auth, "Sign-in changed runtime billing route"
        assert not snapshot()["modes"]["live"], "Sign-in enabled inference"
        app.conversation_composer.insert("1.0", "Draft survives refresh")
        app.refresh_now()
        assert app.conversation_composer.get("1.0", "end-1c") == "Draft survives refresh"
        from aurora_conversation import build_conversation_snapshot
        visible = {"role": "user", "content": {"type": "text", "text": "visible fixture message"}}
        old = {"role": "user", "content": {"type": "text", "text": "archived fixture message"}}
        app.state_cache["conversation"] = build_conversation_snapshot({"history_store": [old, visible], "recent_prompt_history": [visible]})
        app.render_conversation()
        rendered = app.conversation_text.get("1.0", "end-1c")
        assert "visible fixture message" in rendered and "archived fixture message" not in rendered
        visible.update(role="assistant", model="fixture-model", model_source="provider_reported",
                       timestamp_iso="2026-11-04T15:00:00-08:00", edited_by="model:fixture-editor")
        app.state_cache["conversation"] = build_conversation_snapshot({"history_store": [visible], "recent_prompt_history": [visible]})
        app.render_conversation()
        rendered = app.conversation_text.get("1.0", "end-1c")
        assert "fixture-model" in rendered and "15:00:00" in rendered and "fixture-editor" in rendered
        for variable in (app.conversation_time_var, app.conversation_model_var, app.conversation_edits_var):
            assert variable.get()
            variable.set(False)
        app.render_conversation()
        rendered = app.conversation_text.get("1.0", "end-1c")
        assert "fixture-model" not in rendered and "15:00:00" not in rendered and "fixture-editor" not in rendered
        for variable in (app.conversation_time_var, app.conversation_model_var, app.conversation_edits_var):
            variable.set(True)
        from aurora_conversation import ConversationArchive, ensure_message_ids
        from types import SimpleNamespace
        archive = ConversationArchive()
        messages = [{"role": "assistant", "model": "fixture-model", "timestamp": str(i),
                     "content": {"type": "text", "text": f"Message {i}\n" + "fixture text " * 30}, "Exemption": "Pinned" if i == 2 else "None"}
                    for i in range(32)]
        ensure_message_ids(messages)
        archive.observe(messages)
        messages[2]["content"]["text"] = "edited pinned message"
        messages[2]["edited_by"] = "fixture-model"
        archive.observe(messages)
        archive.observe(messages[1:], reason="removed by DELETE_MSG")
        conversation_fixture = build_conversation_snapshot(
            {"history_store": messages[1:], "recent_prompt_history": messages[-5:]}, archive=archive,
            models={"Primary": "fixture-model", "Review": "fixture-review"},
            decay={"ordinary_enabled": True, "ordinary_minutes": 10, "important_enabled": False})
        # This block intentionally replaces exported history with synthetic rows.
        # A periodic runtime refresh would erase the fixture mid-redock and make
        # an empty canvas look like a navigator failure. Resume before receipt QA.
        if app._refresh_after_id:
            app.after_cancel(app._refresh_after_id)
            app._refresh_after_id = None
        app.state_cache["conversation"] = conversation_fixture
        app.render_conversation()
        nav = app.conversation_navigator
        pump()
        assert len(nav.map_rows) == 32 and len(nav.rows) == 5
        assert "Message 0" not in app.conversation_text.get("1.0", "end-1c")
        assert nav.windows[0]["budget"] is None
        assert nav.canvas.find_withtag("preview_text"), "Readable mini preview is missing"
        assert any("Message" in nav.canvas.itemcget(item, "text") for item in nav.canvas.find_withtag("preview_text"))
        canvas_items = nav.canvas.find_all()
        nav.render(nav.snapshot)
        nav.update_idletasks()
        assert nav.canvas.find_all() == canvas_items, "Unchanged conversation repainted the minimap"
        nav.text.yview_moveto(.3)
        nav.text.tag_add("sel", "2.1", "2.4")
        position_before_metadata = nav.text.yview()[0]
        metadata_fixture = json.loads(json.dumps(conversation_fixture))
        metadata_fixture["decay"]["ordinary_minutes"] = 11
        nav.render(metadata_fixture)
        nav.update_idletasks()
        assert tuple(map(str, nav.text.tag_ranges("sel"))) == ("2.1", "2.4")
        assert abs(nav.text.yview()[0] - position_before_metadata) < .04, "Metadata refresh moved the reader"
        nav.render(conversation_fixture)
        nav.mini_style.set("Compact map (legacy)")
        nav.draw()
        assert not nav.canvas.find_withtag("preview_text")
        nav.mini_style.set("Readable text")
        nav.draw()
        assert nav.canvas.find_withtag("preview_text")
        nav.dock("left")
        nav.toggle_collapse()
        assert nav.collapsed and nav.canvas is None and nav.side == "left"
        nav.toggle_collapse()
        nav.detach()
        if hidden:
            nav.popout.withdraw()
        pump()
        assert nav.popout is not None
        # Exercise the real window-manager close callback: reopen on right.
        nav.popout.tk.call(nav.popout.protocol("WM_DELETE_WINDOW"))
        pump()
        assert nav.popout is None and nav.side == "right" and not nav.collapsed
        app.state_cache["conversation"] = conversation_fixture
        app.render_conversation()
        nav.draw()
        if hidden:
            assert not nav.canvas.find_withtag("viewport"), "Hidden transcript was marked on-screen"
        else:
            nav.text.yview_moveto(1)
            pump()
            nav.draw()
            for _ in range(3):
                nav.dock("right")
                pump()
                viewport_top = nav.canvas.canvasy(0)
                viewport_bottom = nav.canvas.canvasy(nav.canvas.winfo_height())
                assert any(nav.canvas.bbox(item)[3] >= viewport_top and nav.canvas.bbox(item)[1] <= viewport_bottom
                           for item in nav.canvas.find_withtag("viewport")), {
                               "error": "Redocked preview lost the current message", "canvas_height": nav.canvas.winfo_height(),
                               "mini_height": nav.mini.winfo_height(), "text_height": nav.text.winfo_height(),
                               "canvas_view": nav.canvas.yview(), "text_view": nav.text.yview(),
                               "visible_ids": list(nav._preview_visible_ids or []),
                               "map_count": len(nav.map_rows), "row_count": len(nav.rows),
                               "preview_geometry": nav._preview_geometry,
                               "viewport": [viewport_top, viewport_bottom],
                               "marks": [nav.canvas.bbox(item) for item in nav.canvas.find_withtag("viewport")]}
            nav._mini_scroll("moveto", 0)
            before_independent = nav.canvas.yview()[0]
            nav._preview_geometry = None  # force the settled-geometry branch without changing main IDs
            nav.draw()
            assert abs(nav.canvas.yview()[0] - before_independent) < .01, "Resize stole independent mini scrolling"
        top, bottom, _ = nav.hit_rows[0]
        nav.canvas.yview_moveto(0)
        nav._click(SimpleNamespace(y=(top + bottom) / 2))
        assert app.conversation_mode_var.get() == "SHOW_ALL"
        assert "Message 0" in app.conversation_text.get("1.0", "end-1c")
        app.conversation_mode_var.set("SHOW_ALL_IN_ORDER")
        app.render_conversation()
        assert "edited pinned message" not in app.conversation_text.get("1.0", "end-1c")
        nav.open_settings()
        if hidden:
            nav.settings.withdraw()
        pump()
        for variable in nav._budget_fields.values():
            variable.set("150")
        nav.reset_view()
        assert all(variable.get() == "0" for variable in nav._budget_fields.values())
        nav.settings.destroy()
        nav.reset_view()
        assert app.conversation_mode_var.get() == "Current context"
        assert app.conversation_composer.get("1.0", "end-1c") == "Draft survives refresh"
        app.state_cache["conversation"] = build_conversation_snapshot({"history_store": [old], "recent_prompt_history": []})
        app.render_conversation()
        assert "visible fixture message" not in app.conversation_text.get("1.0", "end-1c")
        app._refresh_after_id = app.after(250, app.refresh_loop)
        app.send_conversation_message()
        assert app.conversation_composer.get("1.0", "end-1c") == ""
        assert "Queued" in app.conversation_delivery_var.get()
        sent_count = len(app.conversation_outbox.rows)
        app.send_conversation_message()
        assert len(app.conversation_outbox.rows) == sent_count, "Empty second send duplicated input"
        until(lambda: (work / "aurora_external_bridge_log.jsonl").exists() and "Draft survives refresh" in (work / "aurora_external_bridge_log.jsonl").read_text(encoding="utf-8"), "conversation ingestion")
        first_send = next(iter(app.conversation_outbox.rows))
        until(lambda: app.conversation_outbox.rows[first_send]["phase"] == "received", "correlated outbox receipt")
        assert "Draft survives refresh" in app.conversation_delivery_var.get()
        assert "Model delivery unconfirmed" in app.conversation_delivery_var.get()
        assert "Draft survives refresh" in app.conversation_awaiting.text.get("1.0", "end-1c")
        assert app.conversation_awaiting.winfo_manager() == "grid"
        app.conversation_awaiting.toggle.invoke()
        assert not app.conversation_awaiting.content.winfo_manager()
        app.conversation_awaiting.toggle.invoke()
        assert app.conversation_awaiting.content.winfo_manager() == "grid"
        nav.send_feedback.set(False)
        nav.changed()
        app.refresh_conversation_feedback()
        assert "Draft survives refresh" not in app.conversation_delivery_var.get()
        assert not app.conversation_awaiting.winfo_manager(), "Compact mode kept the expanded waiting area"
        nav.send_feedback.set(True)
        nav.changed()
        app.refresh_conversation_feedback()
        assert "Draft survives refresh" in app.conversation_delivery_var.get()
        assert "Draft survives refresh" not in app.conversation_text.get("1.0", "end-1c"), "Local display entry leaked into AI context"
        outbox = app.open_conversation_outbox()
        if hidden:
            outbox.withdraw()
        outbox.tree.selection_set(first_send)
        outbox.show_selected()
        assert first_send in outbox.details.get("1.0", "end-1c")
        app.conversation_composer.insert("1.0", "Existing draft must not be replaced")
        outbox.copy_draft()
        assert app.conversation_composer.get("1.0", "end-1c") == "Existing draft must not be replaced"
        original_append = panel.append_external_message
        def failed_send(*_args, **_kwargs):
            raise OSError("fixture write failure")
        panel.append_external_message = failed_send
        app.send_conversation_message()
        panel.append_external_message = original_append
        assert app.conversation_composer.get("1.0", "end-1c") == "Existing draft must not be replaced"
        assert next(reversed(app.conversation_outbox.rows.values()))["phase"] == "uncertain"
        app.refresh_conversation_feedback()
        assert "inspect before resending" in app.conversation_delivery_var.get()
        app.conversation_composer.delete("1.0", "end")
        outbox.copy_draft()
        assert app.conversation_composer.get("1.0", "end-1c") == "Draft survives refresh"
        assert "Copied" in outbox.notice.get()
        outbox.show_selected(object())
        assert "Closing this list" in outbox.notice.get(), "Old copy notice survived a selection change"
        app.conversation_composer.delete("1.0", "end")
        outbox.withdraw()
        app.state_cache["conversation"] = conversation_fixture
        app.render_conversation()
        chat = app.open_conversation_popout()
        if hidden:
            chat.withdraw()
        assert chat.text.get("1.0", "end-1c") == app.conversation_text.get("1.0", "end-1c")
        chat.composer.insert("1.0", "Independent popout draft")
        chat.withdraw()
        same_chat = app.open_conversation_popout()
        assert same_chat is chat and chat.composer.get("1.0", "end-1c") == "Independent popout draft"
        assert "Draft survives refresh" in chat.awaiting.text.get("1.0", "end-1c")
        chat.awaiting.toggle.invoke()
        assert not chat.awaiting.content.winfo_manager() and not app.conversation_awaiting.content.winfo_manager()
        chat.awaiting.toggle.invoke()
        app.show_tab("Dashboard")
        app.state_cache["conversation"] = build_conversation_snapshot({"history_store": [visible], "recent_prompt_history": [visible]})
        app.render_logs("Dashboard")
        assert "fixture-model" in chat.text.get("1.0", "end-1c"), "Visible popout stopped following state outside Conversation tab"
        app.send_conversation_message(composer=chat.composer)
        assert chat.composer.get("1.0", "end-1c") == ""
        pump()
        assert chat.awaiting.text.yview()[1] >= .98, "Newest queued message did not scroll into view"
        last_send = next(reversed(app.conversation_outbox.rows))
        until(lambda: app.conversation_outbox.rows[last_send]["phase"] == "received", "popout message receipt")
        if not hidden:
            chat.geometry(f"{round(500 * nav.scale)}x{round(420 * nav.scale)}")
            pump()
            chat.page.canvas.yview_moveto(1)
            pump()
            assert chat.send.winfo_rooty() + chat.send.winfo_height() <= chat.winfo_rooty() + chat.winfo_height(), "Compact popout clipped Send"
            assert chat.text.winfo_height() > 40 * nav.scale, "Compact popout lost its transcript"
            chat.page.canvas.yview_moveto(0)
            pump()
            outbox.deiconify()
            outbox.geometry(f"{round(500 * nav.scale)}x{round(360 * nav.scale)}")
            pump()
            assert outbox.details.winfo_height() > 40 * nav.scale, "Compact outbox lost details"
            assert outbox.tree.winfo_height() > 40 * nav.scale, "Compact outbox lost message list"
            outbox.withdraw()
        chat.withdraw()
        # Synthetic transport receipts exercise display transitions; the
        # separate offline_delivery_smoke drives the real model-turn path.
        from aurora_delivery_receipts import TurnDelivery
        def delivery_writer(event, **fields):
            record = dict(event=event, timestamp="fixture receipt", **fields)
            with (work / "aurora_external_bridge_log.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        delivery = TurnDelivery(delivery_writer, [app.conversation_outbox.rows[last_send]])
        for phase in ("preparing", "prepared", "submitted"):
            delivery.emit(phase, model="fixture-request-model")
            app.refresh_conversation_feedback()
            assert app.conversation_outbox.rows[last_send]["phase"] == phase
        delivery.emit("cancelled", reason="Fixture local cancellation; no remote proof")
        delivery.emit("responded", provider_model="late fixture model")
        app.refresh_conversation_feedback()
        assert "Cancelled locally" in chat.awaiting.text.get("1.0", "end-1c")
        assert app.conversation_outbox.rows[last_send]["provider_model"] == ""
        completed = TurnDelivery(delivery_writer, [app.conversation_outbox.rows[first_send]])
        completed.emit("responded", provider_model="fixture-reported-model")
        app.refresh_conversation_feedback()
        assert "Draft survives refresh" not in chat.awaiting.text.get("1.0", "end-1c")
        assert app.conversation_outbox.rows[first_send]["phase"] == "responded"
        app.conversation_awaiting.inspect_latest()
        assert outbox.tree.selection() == (last_send,)
        outbox.withdraw()
        old_toggle = app.toggle_chat_head_request
        legacy_calls = []
        app.toggle_chat_head_request = lambda: legacy_calls.append(True)
        nav.legacy_popout.set(True)
        nav.changed()
        app.open_conversation_popout()
        assert legacy_calls == [True]
        app.toggle_chat_head_request = old_toggle
        nav.reset_view()
        assert not app.ui_preferences["legacy_chat_popout"] and app.ui_preferences["conversation_send_feedback"]
        assert not snapshot()["modes"]["live"]
        app.send_raw("OPEN_CHAT_HEAD()")
        until(lambda: app._is_chat_head_strip_open(), "chat strip opened by runtime state")
        app.open_chat_head_history()
        if hidden:
            app.chat_head_strip_window.withdraw()
            app.chat_head_history_window.withdraw()
        pump()
        app.chat_head_strip_text.insert("1.0", "Legacy strip draft")
        app.apply_chat_head_window_settings()
        pump()
        assert app.chat_head_strip_text.get("1.0", "end-1c") == "Legacy strip draft"
        if not hidden:
            assert app.chat_head_strip_text.winfo_height() >= 20 * nav.scale
        app.send_raw("CLOSE_CHAT_HEAD()")
        until(lambda: not app._is_chat_head_strip_open(), "chat strip closed by runtime state")
        sizes = check_visible_layout(app, pump) if not hidden else []
        widths = {"settings": app.settings_view.winfo_width(), "workspace": app.workspace_frame.winfo_width()}
        views = list(app.page_views)
        app.show_tab("Dashboard")
        pump()
        print("Checking drafts and settings transactions", flush=True)
        field = app.interval_var
        old_value = float(field.get())
        new_value = old_value + 1
        field.set(str(new_value))
        command_result = command("SET_TIME_LOGGING(on)")
        until(lambda: snapshot().get("modes", {}).get("time_logging") is True, "raw command state")
        app.refresh_now()
        assert float(field.get()) == new_value, "Refresh overwrote an unfinished edit"
        transaction_results = []
        for operation in ("preview", "apply", "rollback"):
            print(f"Settings {operation}", flush=True)
            if operation == "rollback":
                request = app._submit_settings_transaction(operation,
                    rollback_handle=app.settings_transaction_last_rollback_handle)
            else:
                request = app._submit_settings_transaction(operation)
            assert request is not None, app.settings_transaction_status_var.get()
            pending_id = app.settings_transaction_pending["request_id"]
            until(lambda: app.settings_transaction_pending is None, operation)
            result = app.settings_transaction_last_receipt
            expected = {"preview": "previewed", "apply": "applied", "rollback": "rolled_back"}[operation]
            assert result.get("status") == expected, result
            assert receipt(pending_id), pending_id
            if app.settings_transaction_dialog is not None:
                app.settings_transaction_dialog.destroy()
                app.settings_transaction_dialog = None
            expected_value = new_value if operation == "apply" else old_value
            until(lambda: float(snapshot()["modes"]["screenshot_interval"]) == expected_value, f"{operation} state")
            app.refresh_now()
            transaction_results.append({"operation": operation, "status": expected, "request_id": pending_id})
        app.reload_observed_settings()
        assert float(field.get()) == old_value

        print("Checking selected-message edit/pin and stale-editor receipt", flush=True)
        command('PIN("Message editor fixture")')
        until(lambda: any('Message editor fixture' in row['text'] for row in snapshot()['conversation']['retained']['rows']), 'message editor seed')
        app.show_tab('Conversation')
        app.conversation_mode_var.set('Retained messages')
        app.conversation_system_var.set(True)
        app.refresh_now()
        target = next(row for row in app.conversation_navigator.rows if row.get('exemption') == 'Pinned' and 'Message editor fixture' in row['text'])
        target_id = target['message_id']
        app.conversation_navigator.selected_message_id = target_id
        app.conversation_navigator.highlight_selection()
        editor = app.edit_conversation_message()
        stale = app.edit_conversation_message()
        if hidden:
            editor.withdraw(); stale.withdraw()
        editor.text.delete('1.0', 'end')
        editor.text.insert('1.0', 'GUI edited text; CLEAR() is literal, not a command.\nSecond line.')
        editor.pin.set(False)
        editor.apply()
        print('Message editor submission: ' + editor.status.get(), flush=True)
        until(lambda: editor.receipt is not None or not editor.status.get().startswith('Queued.'), 'message edit receipt')
        assert editor.status.get().startswith('Applied.'), editor.status.get()
        until(lambda: any(row['message_id']==target_id and row.get('edited_by')=='operator' for row in snapshot()['conversation']['retained']['rows']), 'message edit readback')
        observed = next(row for row in snapshot()['conversation']['retained']['rows'] if row['message_id']==target_id)
        assert not observed['pinned'] and observed['text'].startswith('GUI edited text;')
        stale.pin.set(True)
        stale.apply()
        until(lambda: stale.receipt is not None, 'stale edit rejection')
        assert 'changed since' in stale.status.get(), stale.status.get()
        editor.destroy(); stale.destroy()
        app.refresh_now()
        editor = app.edit_conversation_message()
        if hidden:
            editor.withdraw()
        editor.pin.set(True)
        editor.apply()
        until(lambda: editor.receipt is not None, 'repin receipt')
        assert editor.status.get().startswith('Applied.'), editor.status.get()
        until(lambda: any(row['message_id']==target_id and row['pinned'] for row in snapshot()['conversation']['retained']['rows']), 'repin readback')
        editor.destroy()
        app.conversation_mode_var.set('Current context')
        app.conversation_system_var.set(False)

        print("Checking Switchboard drafts, capture mode and receipts", flush=True)
        app.show_tab("The Switchboard")
        app.refresh_now()
        board = app.switchboard
        style = panel.ttk.Style(app)
        for toggle_style in ("TCheckbutton", "TRadiobutton"):
            assert style.lookup(toggle_style, "background", ("active",)) == panel.PANEL_2
            assert style.lookup(toggle_style, "foreground", ("active",)) == panel.TEXT
            assert style.lookup(toggle_style, "foreground", ("active", "disabled")) == panel.MUTED
        assert "game.scene_policy" in board.variables and "goals.save_format" in board.variables
        assert board.variables["game.scene_policy"].get() in {"evidence", "legacy"}
        assert board.variables["goals.save_format"].get() in {"versioned", "legacy"}
        assert len(board.rows) == 376
        assert board.level.get() == "Overview" and board.flow_section.expanded
        assert not board.controls.expanded and not board.commands_section.expanded
        for kind in ("init", "system", "memory", "current", "conversation", "screen"):
            board.show_contents(kind)
            pump(.05)
            assert board.init_text.get("1.0", "end-1c").strip()
        board.show_init_tip()
        assert board._init_tip is not None
        board.hide_init_tip()
        assert board._init_tip is None
        board.init_section.set_expanded(False)
        if not hidden:
            board.jump(board.flow_section)
            pump()
            page = app.page_views["The Switchboard"]
            offset = board.flow_section.winfo_rooty() - page.canvas.winfo_rooty()
            assert -30 <= offset < page.canvas.winfo_height(), "Flow-map heading must be reachable"
            board.jump(board.commands_section)
            pump()
            offset = board.commands_section.winfo_rooty() - page.canvas.winfo_rooty()
            assert -30 <= offset < page.canvas.winfo_height(), "Command-desk heading must be reachable"
        item = next(str(i) for i, row in enumerate(board.rows) if row["command"] == "SHOW_RUNTIME")
        board.tree.selection_set(item)
        board.prepare_selected()
        assert board.pending is None and board.editor.get("1.0", "end-1c") == "SHOW_RUNTIME()"
        board.run_text("SET_TIME_LOGGING(off)")
        until(lambda: board.pending is None, "Switchboard raw receipt")
        until(lambda: snapshot()["modes"]["time_logging"] is False, "Switchboard raw state")
        board.variables["capture.mode"].set("request_only")
        assert "Draft: request_only" in board.readbacks["capture.mode"].get()
        assert "not applied" in board.readbacks["capture.mode"].get()
        assert "Observed: heartbeat" in board.readbacks["capture.mode"].get()
        assert str(board.readback_labels["capture.mode"].cget("style")) == "Draft.TLabel"
        assert "1 edited switches" in board.hint.get(), "Draft feedback must not wait for polling"
        app.refresh_now()
        assert board.variables["capture.mode"].get() == "request_only"
        # A boolean switch and the numeric dial must remain drafts until Apply,
        # and reverting the draft must clear its badge without a runtime write.
        board.variables["capture.demand_enabled"].set("false")
        board.variables["capture.screenshot_interval"].set("4.50")
        assert "Draft: false" in board.readbacks["capture.demand_enabled"].get()
        assert board.sliders["capture.screenshot_interval"][0].get() == 4.5
        assert snapshot()["scheduler"]["demand_capture_enabled"] is True
        assert snapshot()["modes"]["screenshot_interval"] == 30.0
        board.variables["capture.demand_enabled"].set(board.observed["capture.demand_enabled"])
        board.variables["capture.screenshot_interval"].set(board.observed["capture.screenshot_interval"])
        assert "Draft:" not in board.readbacks["capture.demand_enabled"].get()
        assert str(board.readback_labels["capture.demand_enabled"].cget("style")) == "Muted.TLabel"
        original_primary = snapshot()["models"]["text"]
        board.variables["model.text"].set("gpt-6.1-terra")
        request = board.submit_settings("apply", keys=board.model_keys)
        assert request is not None
        until(lambda: app.settings_transaction_pending is None, "model choices apply")
        until(lambda: snapshot()["models"]["text"] == "gpt-6.1-terra", "primary model observed")
        assert snapshot()["modes"]["capture_mode"] == "heartbeat", "Model-only apply applied an unrelated draft"
        assert board.variables["capture.mode"].get() == "request_only"
        assert board.rollback() is not None
        until(lambda: app.settings_transaction_pending is None, "model choices undo")
        until(lambda: snapshot()["models"]["text"] == original_primary, "primary model restored")
        board.variables["capture.geometry_policy"].set("verified")
        board.variables["capture.target"].set("foreground")
        board.variables["capture.request_timeout_seconds"].set("15")
        board.variables["capture.request_max_attempts"].set("3")
        board.variables["scheduler.readback_scope"].set("reviewed")
        for operation in ("preview", "apply", "rollback"):
            request = board.rollback() if operation == "rollback" else board.submit_settings(operation)
            assert request is not None, app.settings_transaction_status_var.get()
            until(lambda: app.settings_transaction_pending is None, "Switchboard " + operation)
            expected = "request_only" if operation == "apply" else "heartbeat"
            until(lambda: snapshot()["modes"]["capture_mode"] == expected, "capture mode " + operation)
            until(lambda: snapshot()["modes"]["capture_geometry_policy"] == ("verified" if operation == "apply" else "legacy"), "geometry policy " + operation)
            until(lambda: snapshot()["modes"]["capture_target"] == ("foreground" if operation == "apply" else "legacy_options"), "capture target " + operation)
            until(lambda: snapshot()["modes"]["capture_request_timeout_seconds"] == (15.0 if operation == "apply" else 0.0), "capture timeout " + operation)
            until(lambda: snapshot()["modes"]["capture_request_max_attempts"] == (3 if operation == "apply" else 0), "capture attempts " + operation)
            until(lambda: snapshot()["scheduler"]["readback_scope"] == ("reviewed" if operation == "apply" else "discovery"), "readback scope " + operation)
            assert app.settings_transaction_last_receipt["status"] == {"preview": "previewed", "apply": "applied", "rollback": "rolled_back"}[operation]
            app.refresh_now()
            assert ("not applied" in board.readbacks["capture.mode"].get()) is (operation == "preview")
            if app.settings_transaction_dialog is not None:
                app.settings_transaction_dialog.destroy()
                app.settings_transaction_dialog = None
        board.reload()
        board.open_defaults()
        assert board.defaults_section.expanded
        assert "runtime.live" in board.defaults_preview.get("1.0", "end-1c")
        for operation in ("preview", "apply", "rollback"):
            request = board.rollback() if operation == "rollback" else board.submit_defaults(operation)
            assert request is not None, app.settings_transaction_status_var.get()
            until(lambda: app.settings_transaction_pending is None, "preview defaults " + operation)
            assert app.settings_transaction_last_receipt["status"] == {"preview": "previewed", "apply": "applied", "rollback": "rolled_back"}[operation]
            until(lambda: snapshot()["modes"]["capture_mode"] == ("request_only" if operation == "apply" else "heartbeat"), "reset capture mode")
            assert not snapshot()["modes"]["live"]
        board.defaults_section.set_expanded(False)
        board.reload()
        print("Checking compact Agent controls and command-driven preset", flush=True)
        mini = app.agent_controls
        mini.set_expanded(True)
        app.show_tab("Conversation")
        pump()
        app.refresh_now()
        assert mini.pane.winfo_height() > 1 or hidden
        if not hidden:
            from aurora_panel_layout import ui_scale
            assert mini.pane.winfo_height() <= round(136 * ui_scale(app)), "Compact pane ignored its height bound"
            nav.dock("right")
            if nav.collapsed:
                nav.toggle_collapse()
            pump()
            assert nav.canvas.winfo_height() >= nav.px(32), f"Expanded controls squeezed the minimap: graph={nav.canvas.winfo_height()} transcript={nav.winfo_height()} scale={nav.scale}"
        mini.variables["model.text"].set("gpt-6.1-terra")
        app.refresh_now()
        assert mini.variables["model.text"].get() == "gpt-6.1-terra", "Refresh overwrote a model draft"
        original_primary = snapshot()["models"]["text"]
        mini.scope.set("Next turn only")
        mini.variables["inference.reasoning_effort"].set("medium")
        until(lambda: board._fresh and board.pending is None, "compact next-turn availability")
        assert mini.apply_primary() is not None, mini.feedback.get()
        until(lambda: board.pending is None, "compact next-turn receipt")
        assert snapshot()["models"]["text"] == original_primary, "Next-turn plan changed session model"
        until(lambda: ((snapshot().get("planning") or {}).get("next_inference") or {}).get("reasoning_effort") == "medium", "compact next-turn state")
        mini.command("CLEAR_NEXT_INFERENCE()")
        until(lambda: board.pending is None, "compact clear override receipt")
        mini.scope.set("Hold for session")
        mini.apply_primary()
        until(lambda: app.settings_transaction_pending is None, "compact hold receipt")
        until(lambda: snapshot()["models"]["text"] == "gpt-6.1-terra", "compact hold state")
        board.rollback()
        until(lambda: app.settings_transaction_pending is None, "compact hold rollback")
        before_flow = snapshot()["scheduler"]
        before_execution = snapshot()["modes"]["execution"]
        before_policy = snapshot()["modes"]["assistant_policy"]
        assert set(mini.selectors["runtime.execution"]["values"]) == {"safe", "assist", "auto"}
        assert set(mini.selectors["runtime.assistant_policy"]["values"]) == {"legacy", "task_flow"}
        mini.demand_preset()
        until(lambda: app.settings_transaction_pending is None, "compact flow receipt")
        until(lambda: snapshot()["scheduler"]["heartbeat_seconds"] == 0, "heartbeat disabled")
        assert snapshot()["modes"]["capture_mode"] == "request_only"
        assert snapshot()["scheduler"]["mode"] == "per_capture"
        assert snapshot()["modes"]["assistant_policy"] == "task_flow"
        assert snapshot()["modes"]["execution"] == before_execution, "Flow preset enabled Auto"
        assert not snapshot()["modes"]["live"], "Flow preset enabled model spending"
        board.rollback()
        until(lambda: app.settings_transaction_pending is None, "compact flow rollback")
        until(lambda: snapshot()["scheduler"]["heartbeat_seconds"] == before_flow["heartbeat_seconds"], "heartbeat restored")
        assert snapshot()["modes"]["assistant_policy"] == before_policy
        mini.reload()
        mini.variables["runtime.execution"].set("auto")
        mini.variables["runtime.assistant_policy"].set("task_flow")
        mini.apply_flow()
        until(lambda: app.settings_transaction_pending is None, "compact execution/policy receipt")
        until(lambda: snapshot()["modes"]["execution"] == "auto", "compact execution state")
        assert snapshot()["modes"]["assistant_policy"] == "task_flow"
        assert not snapshot()["modes"]["live"]
        board.rollback()
        until(lambda: app.settings_transaction_pending is None, "compact execution/policy rollback")
        until(lambda: snapshot()["modes"]["execution"] == before_execution, "compact execution restored")
        mini.reload()
        from aurora_agent_controls import CONTINUATION_KEYS
        before_task = snapshot()["continuation"]
        mini.variables["task.continuation_mode"].set("bounded")
        mini.variables["task.max_model_turns"].set("4")
        mini.variables["task.max_seconds"].set("60")
        mini.variables["scheduler.readback_wake_enabled"].set("true")
        mini.variables["context.init_delivery"].set("system_once")
        mini.apply_keys(CONTINUATION_KEYS)
        until(lambda: app.settings_transaction_pending is None, "compact task settings receipt")
        until(lambda: snapshot()["continuation"]["mode"] == "bounded", "bounded task settings observed")
        assert snapshot()["continuation"]["max_model_turns"] == 4
        assert snapshot()["continuation"]["max_seconds"] == 60
        assert snapshot()["modes"]["init_delivery"] == "system_once"
        assert snapshot()["scheduler"]["readback_wake_enabled"]
        assert not snapshot()["modes"]["live"], "Task controls enabled model spending"
        board.rollback()
        until(lambda: app.settings_transaction_pending is None, "compact task settings rollback")
        until(lambda: snapshot()["continuation"]["mode"] == before_task["mode"], "task settings restored")
        assert snapshot()["continuation"]["max_model_turns"] == before_task["max_model_turns"]
        mini.reload()
        mini.set_expanded(False)
        app.show_tab("Dashboard")

        app.refresh_dashboard(app.state_cache)
        print("Checking Dashboard and refresh recovery", flush=True)
        app.open_dashboard_popout()
        if hidden:
            app.dashboard_popout_window.withdraw()
        pump()
        assert app.dashboard_text.get("1.0", "end-1c") == app.dashboard_popout_text.get("1.0", "end-1c")
        assert "RUNNING" in app.dashboard_popout_summary_var.get()
        item = app.dashboard_events_tree.get_children()[0]
        app.dashboard_events_tree.selection_set(item)
        app._show_dashboard_receipt()
        assert app._dashboard_events_by_iid[item]["request_id"] in app.dashboard_receipt_text.get("1.0", "end-1c")
        app.dashboard_wrap_var.set(False)
        app._update_dashboard_wrap()
        assert app.dashboard_text.cget("wrap") == app.dashboard_popout_text.cget("wrap") == app.dashboard_receipt_text.cget("wrap") == "none"
        app.dashboard_wrap_var.set(True)
        app._update_dashboard_wrap()
        dashboard_refresh = check_dashboard_refresh_stability(app, pump, hidden)
        app.close_dashboard_popout()

        # Force a paint failure while a periodic refresh is due; the same file
        # revision must be retried and the periodic callback must survive.
        original_render = app.render_state
        failed = [False]
        def fail_once():
            if not failed[0]:
                failed[0] = True
                raise RuntimeError("injected one-time render failure")
            return original_render()
        app.render_state = fail_once
        app.refresh_loop()
        assert app._refresh_after_id and app._last_refresh_perf["consecutive_errors"] == 1
        until(lambda: app._last_refresh_perf.get("recoveries", 0) >= 1, "automatic refresh recovery")
        app.render_state = original_render

        timings = []
        for _ in range(15):
            until(app.refresh_now, "bounded refresh sample after transient file contention", timeout=3)
            timings.append(app._last_refresh_perf["last_refresh_ms"])
            pump(0.03)
        result = {"status": "passed", "displayed_layout_checked": not hidden, "hidden_tk": hidden, "views": views, "window_sizes": sizes, "pane_widths": widths,
                  "work_areas": monitor_work_areas(), "raw_command": command_result,
                  "settings_transactions": transaction_results, "draft_preserved": True,
                  "switchboard_feedback": {"boolean_and_numeric_drafts_nonmutating": True,
                      "draft_badges_immediate_and_preserved_by_refresh": True,
                      "preview_apply_undo_badges_match_readback": True,
                      "reverted_draft_clears_badge": True,
                      "dark_toggle_active_disabled_contrast": True},
                  "conversation_delivery": {"visible_queued_text": True, "exact_ingestion_receipt": True,
                      "awaiting_reply_shared_collapse": True, "newest_send_scrolled_into_view": True,
                      "synthetic_model_receipt_stages": True, "cancelled_late_reply_ignored": True,
                      "responded_removed_from_waiting_only": True, "inspect_latest_selection": True,
                      "no_provider_delivery_claim": True, "no_context_insertion": True,
                      "write_failure_keeps_draft": True, "copy_does_not_replace_draft": True,
                      "popout_current_view_and_send": True, "popout_close_retains_draft": True,
                      "popout_updates_off_main_tab": True, "legacy_shortcut_option": True},
                  "signin_controls": {"fallback_openai": True, "saved_registration": True,
                      "duplicate_click_coalesced": True, "cancellation": True,
                      "closing_window_reopen": True, "billing_and_inference_unchanged": True,
                      "provider_mocked": True},
                  "conversation_navigator": {"left_right_dock": True, "collapse_expand": True,
                      "popout_close_redocks_right": True, "archive_click_navigation": True,
                      "redock_reveals_current_message": not hidden,
                      "metadata_refresh_keeps_selection_and_scroll": True,
                      "original_order_and_metadata": True, "view_options_and_reset": True,
                      "readable_minimum_and_scrollable_composer": not hidden},
                  "message_editor": {"literal_text_edit_and_unpin": True,
                      "repin": True, "stale_revision_rejected": True,
                      "editor_attribution": True, "exact_runtime_receipt": True},
                  "task_flow_controls": {"policy_and_execution_selectors": True,
                      "preset_leaves_execution_and_inference_unchanged": True,
                      "policy_execution_apply_and_rollback": True,
                      "bounded_task_and_init_apply_rollback": True,
                      "task_controls_do_not_enable_inference": True},
                  "automatic_refresh_recovered": True, "dashboard_tab_popout_match": True,
                  "header_layout": getattr(app, "_header_layout_proof", []), "dashboard_refresh": dashboard_refresh,
                  "readable_preview_and_legacy_map": True,
                  "flow_text_contained_all_detail_levels": not hidden,
                  "refresh_ms": {"samples": len(timings), "p50": statistics.median(timings),
                                 "p95": sorted(timings)[-1]}, "callback_errors": errors}
        (work / "panel-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if not hidden and os.getenv("AURORA_PANEL_EVIDENCE_PATH"):
            from PIL import ImageGrab
            app._apply_settings_mode("hidden")
            app.geometry("1180x640+20+20")
            app.show_tab("Conversation")
            app.attributes("-topmost", True)
            pump(.4)
            app.lift()
            app.focus_force()
            pump(.2)
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            hwnd = user32.GetAncestor(app.winfo_id(), 2)
            capture_result = ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
            assert capture_result == 0
            ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(os.environ["AURORA_PANEL_EVIDENCE_PATH"])
            app.show_tab("Dashboard")
        if interactive:
            faulthandler.cancel_dump_traceback_later()
            # A persistent synthetic transcript lets native QA exercise archive,
            # viewport and metadata controls without reading personal history.
            interactive_render = app.render_conversation
            def render_fixture_conversation():
                app.state_cache["conversation"] = conversation_fixture
                interactive_render()
            if not os.getenv('AURORA_PANEL_INTERACTIVE_REAL'):
                app.render_conversation = render_fixture_conversation
            else:
                app.conversation_mode_var.set('Retained messages')
                app.conversation_system_var.set(True)
            app.title("Aurora 2 - isolated viewer QA (synthetic conversation)")
            app.state("normal")
            from aurora_panel_layout import clamp_window_geometry
            area = monitor_work_areas()[0]
            geometry = clamp_window_geometry({"width": round(1180*nav.scale), "height": round(760*nav.scale), "x": area[0]+40, "y": area[1]+40}, [area])
            app.geometry(f"{geometry['width']}x{geometry['height']}+{max(0, geometry['x'])}+{max(0, geometry['y'])}")
            app.show_tab("Conversation")
            app.render_conversation()
            app.conversation_delivery_var.set("Offline walkthrough: inference is locked off; messages queue locally.")
            app.after(15 * 60 * 1000, app.on_close)
            app.mainloop()
        else:
            app.on_close()
        saved = panel.load_layout_preferences(panel.LAYOUT_PATH)
        assert saved["active_view"] in (views if interactive else ["Dashboard"]) and saved["version"] == 1
        assert saved["compact_header"] is True
        result["layout_saved"] = True
        (work / "panel-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        faulthandler.cancel_dump_traceback_later()
        if not app._closing:
            app.on_close()


def run_smoke(interactive=False, hidden=False):
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".aurora-panel-smoke-") as folder:
        work = Path(folder).resolve()
        assert ROOT.resolve() in work.parents
        for name in COPY_FILES:
            shutil.copy2(ROOT / name, work / name)
        (work / "panel_runtime_fixture.py").write_text(CONTRACT_IMPORT_GUARD + CONTRACT_FIXTURE, encoding="utf-8")
        env = dict(os.environ, AURORA_ENABLE_TEXT_INPUT_PROCESS="0", AURORA_AUTH_MODE="api_key", AURORA_READBACK_SCOPE="discovery",
                   PYTHONUNBUFFERED="1", AURORA_PYTHON=sys.executable)
        flags = ["--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
                 "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none",
                 "--screenshot-interval", "30"]
        with (work / "runtime.log").open("w", encoding="utf-8") as log:
            runtime = subprocess.Popen([sys.executable, str(work / "panel_runtime_fixture.py"), *flags], cwd=work, env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            worker = None
            try:
                launch = [sys.executable, str(Path(__file__).resolve()), "--worker", str(work)]
                if interactive:
                    launch.append("--interactive")
                if hidden:
                    launch.append("--hidden")
                with (work / "panel.log").open("w", encoding="utf-8") as panel_log:
                    worker = subprocess.Popen(launch, cwd=work, env=env, stdout=panel_log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if interactive:
                        print(json.dumps({"interactive_workspace": str(work), "runtime_pid": runtime.pid,
                                          "panel_pid": worker.pid}), flush=True)
                    try:
                        worker.wait(timeout=1000 if interactive else 160)
                    except subprocess.TimeoutExpired as error:
                        raise AssertionError((work / "panel.log").read_text(errors="replace")[-6000:]) from error
                assert worker.returncode == 0, (work / "panel.log").read_text(errors="replace")[-6000:]
                result = json.loads((work / "panel-proof.json").read_text())
                sys.path.insert(0, str(ROOT))
                from aurora_control_plane import append_bridge_request
                append_bridge_request(work, "SHUTDOWN_RUNTIME()", raw=True, client_id="panel_smoke_cleanup")
                runtime.wait(timeout=12)
                assert runtime.returncode == 0
                result["runtime_exit"] = runtime.returncode
                return result
            finally:
                for process in (worker, runtime):
                    if process is not None and process.poll() is None:
                        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, timeout=10)
                        process.wait(timeout=10)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        check_panel(Path(sys.argv[sys.argv.index("--worker") + 1]), "--interactive" in sys.argv, "--hidden" in sys.argv)
    else:
        print(json.dumps(run_smoke("--interactive" in sys.argv, "--hidden" in sys.argv), indent=2))
