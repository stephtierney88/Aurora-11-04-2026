"""Real inbox/queue/receipts/shutdown with simulated input; no native desktop I/O."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from offline_panel_smoke import COPY_FILES
from offline_runtime_smoke import CONTRACT_FIXTURE
from aurora_control_plane import append_bridge_request, read_jsonl_from

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = CONTRACT_FIXTURE.rsplit("runtime.main()", 1)[0] + '''
import json
failed_shift = False
def event(name, *args, **kwargs):
    global failed_shift
    with Path("fake-input.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"name": name, "args": args, "kwargs": kwargs}) + "\\n")
    if name == "keyUp" and args == ("shift",) and not failed_shift:
        failed_shift = True
        raise RuntimeError("fixture partial release failure")
    if name == "scancode_down":
        runtime.GAME_INPUT_BACKEND = "keyboard"
        runtime.GAME_CONTROL_KEY_TRANSLATIONS["a"] = "invalid_changed_mapping"
        runtime.GAME_INPUT_SCANCODES["x"] = 999
for name in ("press", "keyDown", "keyUp", "mouseDown", "mouseUp", "moveTo", "click", "doubleClick"):
    setattr(runtime.pyautogui, name, lambda *args, _name=name, **kwargs: event(_name, *args, **kwargs))
runtime.pyautogui.position = lambda: (10, 20)
runtime.pyautogui._normalizeButton = lambda button: {"primary": "left", "secondary": "right"}.get(button, button)
runtime.pyautogui.PAUSE = 0
runtime.GAME_CONTROL_KEY_TRANSLATIONS["a"] = "x"
runtime.send_scancode_key_event = lambda key, is_key_up=False, **kwargs: event("scancode_up" if is_key_up else "scancode_down", key, **kwargs)
runtime.focus_game_input_target = lambda title: {"success": True, "title": "fake emulator"}
runtime.get_foreground_window_title = lambda: "fake desktop"
runtime.main()
'''


def run_smoke():
    started = time.monotonic()
    receipts, measurements = [], {}
    with tempfile.TemporaryDirectory(prefix=".aurora-input-smoke-", dir=ROOT) as directory:
        work = Path(directory).resolve()
        assert work.parent == ROOT.resolve()
        for name in COPY_FILES:
            shutil.copy2(ROOT / name, work / name)
        (work / "fixture.py").write_text(FIXTURE, encoding="utf-8")
        flags = ["--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
                 "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none"]
        env = dict(os.environ, AURORA_ENABLE_TEXT_INPUT_PROCESS="0", AURORA_AUTH_MODE="api_key", PYTHONUNBUFFERED="1")
        with (work / "process.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(work / "fixture.py"), *flags], cwd=work, env=env,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ownership = {"pid": process.pid, "started_at_epoch": time.time(), "fixture_path": str(work)}
            deadline = time.monotonic() + 45
            def rows():
                return read_jsonl_from(work / "aurora_command_execution_log.jsonl")[0]
            def inputs():
                return read_jsonl_from(work / "fake-input.jsonl")[0]
            def wait_for(predicate):
                while time.monotonic() < deadline:
                    value = predicate()
                    if value:
                        return value
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)
                raise AssertionError((work / "process.log").read_text(errors="replace")[-7000:])
            def receipt(identity, *, duplicate=False):
                result = wait_for(lambda: next((row for row in reversed(rows()) if row.get("event") == "command_result"
                    and row.get("request_id") == identity and (not duplicate or row.get("duplicate_suppressed"))), None))
                receipts.append(result)
                return result
            def send(command, identity):
                append_bridge_request(work, command, raw=True, client_id="input_smoke", request_id=identity)
            try:
                send("SHOW_HELD_INPUTS()", "ready")
                assert receipt("ready")["held_input_results"][0]["held_count"] == 0
                send("GB:hold(a)", "game-hold")
                hold = receipt("game-hold")
                assert hold["status"] == "processed", hold
                owner = hold["desktop_results"][0]["input_ownership"]["held"][0]
                assert owner["owner"]["request_id"] == "game-hold"
                assert owner["owner"]["client_id"] == "input_smoke"
                send("GB:release(a)", "game-release")
                released = receipt("game-release")
                assert released["status"] == "processed", released
                game = inputs()
                assert [row["name"] for row in game] == ["scancode_down", "scancode_up"]
                assert game[0]["kwargs"] == game[1]["kwargs"]
                send("PYAG:multi_hold(ctrl,shift)", "chord")
                assert receipt("chord")["status"] == "processed"
                send("CANCEL_ACTIVE_WORK()", "partial-stop")
                partial = receipt("partial-stop")
                assert partial["status"] == "failed", partial
                assert [row["success"] for row in partial["input_cleanup_results"][0]["results"]] == [False, True]
                count = len(inputs())
                send("CANCEL_ACTIVE_WORK()", "partial-stop")
                duplicate = receipt("partial-stop", duplicate=True)
                assert duplicate["input_cleanup_results"] == partial["input_cleanup_results"]
                assert len(inputs()) == count, "Duplicate stop retried a native operation"
                send("SHOW_HELD_INPUTS()", "uncertain")
                assert receipt("uncertain")["held_input_results"][0]["uncertain_count"] == 1
                send("RELEASE_HELD_INPUTS()", "retry")
                assert receipt("retry")["status"] == "processed"
                send("PYAG:drag(100,200,60); PYAG:type(never)", "drag")
                wait_for(lambda: any(row["name"] == "moveTo" for row in inputs()))
                send("PYAG:press(z)", "queued")
                cancelling = time.monotonic()
                send("CANCEL_ACTIVE_WORK()", "drag-stop")
                assert receipt("drag-stop")["status"] == "processed"
                measurements["cancel_receipt_ms"] = round((time.monotonic() - cancelling) * 1000, 2)
                drag_receipt = receipt("drag")
                assert drag_receipt["status"] == "cancelled", drag_receipt
                queued_receipt = receipt("queued")
                assert queued_receipt["status"] == "cancelled", queued_receipt
                send("SHOW_HELD_INPUTS()", "clear")
                clear = receipt("clear")["held_input_results"][0]
                assert clear["held_count"] == 0
                send("PYAG:hold(b)", "shutdown-hold")
                assert receipt("shutdown-hold")["status"] == "processed"
                send("SHUTDOWN_RUNTIME()", "shutdown")
                assert receipt("shutdown")["status"] == "processed"
                code = process.wait(timeout=max(1, deadline-time.monotonic()))
                events = inputs()
                assert code == 0
                assert not any(row["name"] in {"press", "dragTo"} for row in events)
                assert all(row["kwargs"]["duration"] == 0 for row in events if row["name"] == "moveTo")
                assert events[-1]["name"] == "keyUp" and events[-1]["args"] == ["b"]
                assert not (work / "forbidden-native-input.txt").exists()
                state = json.loads((work / "aurora_control_panel_state.json").read_text(encoding="utf-8-sig"))
                assert state["work"]["held_inputs"]["held_count"] == 0
                assert state["modes"]["live"] is False and state["locks"]["live"] is True
                proof = {"status": "passed", "receipt_checks": len(receipts), "measurements": measurements,
                         "input_events": events, "original_hold": owner, "partial_cleanup": partial["input_cleanup_results"],
                         "duplicate_preserved_without_replay": True, "final_held_inputs": state["work"]["held_inputs"],
                         "native_capture_network_guards_unused": True, "real_api_calls": 0,
                         "runtime_exit_code": code, "ownership": ownership}
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
    proof.update(fixture_removed=not work.exists(), elapsed_seconds=round(time.monotonic()-started, 3))
    return proof


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2))
