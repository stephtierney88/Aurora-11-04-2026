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

ROOT = Path(__file__).resolve().parents[1]
COPY_FILES = (
    "aurora_switchboard.py", "aurora_command_catalog.py", "aurora_portal_spinner.png", "aurora_flow_emblem.png",
    "aurora2.py", "aurora2_control_panel.py", "aurora_panel_layout.py", "aurora_preflight.py",
    "aurora_runtime_work.py", "aurora_input_ownership.py", "aurora_responses_reasoning.py", "aurora_capture_store.py", "aurora_command_protocol.py", "aurora_command_contracts.py", "aurora_default_profiles.py",
    "aurora_pending_commands.py", "aurora_history_controls.py", "aurora_episodic_retrieval.py", "aurora_search_query.py", "aurora_retrieval_results.py", "aurora_retrieval_commands.py", "aurora_conversation.py", "aurora_control_plane.py", "aurora_codex_oauth.py", "aurora_settings_registry.py",
    "aurora_settings_transactions.py", "launch_aurora2.cmd", "launch_aurora2_ui.cmd",
)


def check_visible_layout(app, pump):
    app.state("normal")
    pump(.4)  # Wait for the native restore transition before sizing/docking.
    app.geometry("1000x700+30+30")
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
    assert widths["settings"] >= 390 and widths["workspace"] >= 400, widths
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
    for width, height in ((900, 640), (1180, 760)):
        app.geometry(f"{width}x{height}+30+30")
        pump()
        for name, page in app.page_views.items():
            assert app.show_tab(name), name
            pump(0.05)
            assert page.canvas.winfo_ismapped() and page.vertical.winfo_ismapped(), name
            assert app.runtime_shutdown_button.winfo_ismapped(), name
            assert app.runtime_shutdown_button.winfo_rooty() < page.canvas.winfo_rooty(), name
            if name == "Dashboard":
                assert page.inner.winfo_width() <= page.canvas.winfo_width() + 1
            if name == "Conversation":
                assert app.conversation_send_button.winfo_rooty() + app.conversation_send_button.winfo_height() <= page.canvas.winfo_rooty() + page.canvas.winfo_height(), "Composer must remain visible"
            if width == 900:
                views.append(name)
        sizes.append({"width": app.winfo_width(), "height": app.winfo_height()})
    assert len(views) == 24
    app.toggle_maximized()
    pump()
    assert app.state() == "zoomed", app.state()
    app.toggle_maximized()
    pump()
    assert app.state() == "normal"
    assert app.winfo_width() == 1180, app.winfo_width()



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
        return json.loads(panel.STATE_PATH.read_text(encoding="utf-8-sig"))

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
        app.state_cache["conversation"] = build_conversation_snapshot({"history_store": [old], "recent_prompt_history": []})
        app.render_conversation()
        assert "visible fixture message" not in app.conversation_text.get("1.0", "end-1c")
        app.send_conversation_message()
        assert app.conversation_composer.get("1.0", "end-1c") == ""
        assert "Queued" in app.conversation_delivery_var.get()
        until(lambda: (work / "aurora_external_bridge_log.jsonl").exists() and "Draft survives refresh" in (work / "aurora_external_bridge_log.jsonl").read_text(encoding="utf-8"), "conversation ingestion")
        if not hidden:
            check_visible_layout(app, pump)
        widths = {"settings": app.settings_view.winfo_width(), "workspace": app.workspace_frame.winfo_width()}
        views = list(app.page_views)
        sizes = [] if hidden else [{"width": 900, "height": 640}, {"width": 1180, "height": 760}]
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

        print("Checking Switchboard drafts, capture mode and receipts", flush=True)
        app.show_tab("The Switchboard")
        app.refresh_now()
        board = app.switchboard
        assert len(board.rows) == 360
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
            assert page.canvas.yview()[0] > 0, "Flow-map jump did not scroll"
            assert abs(board.flow_section.winfo_rooty() - page.canvas.winfo_rooty()) < 30
            board.jump(board.commands_section)
            pump()
            assert page.canvas.yview()[0] > .1, "Command-desk jump did not scroll"
        item = next(str(i) for i, row in enumerate(board.rows) if row["command"] == "SHOW_RUNTIME")
        board.tree.selection_set(item)
        board.prepare_selected()
        assert board.pending is None and board.editor.get("1.0", "end-1c") == "SHOW_RUNTIME()"
        board.run_text("SET_TIME_LOGGING(off)")
        until(lambda: board.pending is None, "Switchboard raw receipt")
        until(lambda: snapshot()["modes"]["time_logging"] is False, "Switchboard raw state")
        board.variables["capture.mode"].set("request_only")
        app.refresh_now()
        assert board.variables["capture.mode"].get() == "request_only"
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
        for operation in ("preview", "apply", "rollback"):
            request = board.rollback() if operation == "rollback" else board.submit_settings(operation)
            assert request is not None, app.settings_transaction_status_var.get()
            until(lambda: app.settings_transaction_pending is None, "Switchboard " + operation)
            expected = "request_only" if operation == "apply" else "heartbeat"
            until(lambda: snapshot()["modes"]["capture_mode"] == expected, "capture mode " + operation)
            assert app.settings_transaction_last_receipt["status"] == {"preview": "previewed", "apply": "applied", "rollback": "rolled_back"}[operation]
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
        assert app.dashboard_text.cget("wrap") == app.dashboard_popout_text.cget("wrap") == "none"
        app.dashboard_wrap_var.set(True)
        app._update_dashboard_wrap()
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
            assert app.refresh_now(), app._last_refresh_perf
            timings.append(app._last_refresh_perf["last_refresh_ms"])
            pump(0.03)
        result = {"status": "passed", "displayed_layout_checked": not hidden, "hidden_tk": hidden, "views": views, "window_sizes": sizes, "pane_widths": widths,
                  "work_areas": monitor_work_areas(), "raw_command": command_result,
                  "settings_transactions": transaction_results, "draft_preserved": True,
                  "automatic_refresh_recovered": True, "dashboard_tab_popout_match": True,
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
            app.state("zoomed")
            app.show_tab("Conversation")
            app.conversation_delivery_var.set("Offline walkthrough: inference is locked off; messages queue locally.")
            app.after(15 * 60 * 1000, app.on_close)
            app.mainloop()
        else:
            app.on_close()
        saved = panel.load_layout_preferences(panel.LAYOUT_PATH)
        assert saved["active_view"] in (views if interactive else ["Dashboard"]) and saved["version"] == 1
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
        env = dict(os.environ, AURORA_ENABLE_TEXT_INPUT_PROCESS="0", AURORA_AUTH_MODE="api_key",
                   PYTHONUNBUFFERED="1", AURORA_PYTHON=sys.executable)
        flags = ["--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
                 "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none",
                 "--screenshot-interval", "30"]
        with (work / "runtime.log").open("w", encoding="utf-8") as log:
            runtime = subprocess.Popen([sys.executable, str(work / "aurora2.py"), *flags], cwd=work, env=env,
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
                        worker.wait(timeout=1000 if interactive else 100)
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
