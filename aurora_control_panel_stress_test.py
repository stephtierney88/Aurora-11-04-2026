from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import time
from pathlib import Path

import aurora2_control_panel as panel_mod

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "soak_runs"

ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn0x6wAAAAASUVORK5CYII="
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def wait_for(predicate, timeout_seconds: float, tick_seconds: float = 0.2) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(tick_seconds)
    return False


class StressRunner:
    def __init__(self, run_id: str, artifact_dir: Path, state_fresh_seconds: float) -> None:
        self.run_id = run_id
        self.artifact_dir = artifact_dir
        self.state_fresh_seconds = state_fresh_seconds
        self.log_path = artifact_dir / "ui_stress.log"
        self.report_path = artifact_dir / "ui_stress_report.json"
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.steps: list[dict[str, object]] = []
        self.app: panel_mod.AuroraControlPanel | None = None
        self.synthetic_valid_image = artifact_dir / "synthetic-valid.png"
        self.synthetic_invalid_image = artifact_dir / "synthetic-invalid.png"
        self.synthetic_valid_image.write_bytes(ONE_BY_ONE_PNG)
        self.synthetic_invalid_image.write_text("not a real image", encoding="utf-8")

    def log(self, message: str) -> None:
        line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line)

    def record_step(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(
            {
                "name": name,
                "ok": ok,
                "detail": detail,
                "timestamp": dt.datetime.now().isoformat(),
            }
        )
        prefix = "PASS" if ok else "FAIL"
        self.log(f"{prefix}: {name}{' | ' + detail if detail else ''}")
        if not ok:
            self.failures.append(f"{name}: {detail}".rstrip(": "))

    def pump(self, seconds: float = 0.0) -> None:
        assert self.app is not None
        end = time.time() + seconds
        while True:
            self.app.update_idletasks()
            self.app.update()
            if time.time() >= end:
                break
            time.sleep(0.05)

    def require_state_fresh(self) -> dict[str, object]:
        state_path = panel_mod.STATE_PATH
        if not state_path.exists():
            raise RuntimeError(f"State file missing: {state_path}")

        def state_is_fresh() -> bool:
            age = time.time() - state_path.stat().st_mtime
            return age <= self.state_fresh_seconds

        if not wait_for(state_is_fresh, timeout_seconds=20.0, tick_seconds=0.5):
            raise RuntimeError(
                f"State file is stale. age={time.time() - state_path.stat().st_mtime:.1f}s threshold={self.state_fresh_seconds:.1f}s"
            )
        return json.loads(state_path.read_text(encoding="utf-8"))

    def wait_for_pending_count(self, minimum: int, timeout_seconds: float = 12.0) -> int:
        assert self.app is not None

        def have_rows() -> bool:
            self.app.refresh_now()
            self.pump(0.1)
            return len(self.app.pending_rows) >= minimum

        if not wait_for(have_rows, timeout_seconds=timeout_seconds, tick_seconds=0.35):
            return len(self.app.pending_rows)
        return len(self.app.pending_rows)

    def run(self) -> dict[str, object]:
        started_at = dt.datetime.now().isoformat()
        try:
            self.app = panel_mod.AuroraControlPanel()
            self.pump(0.5)

            state = self.require_state_fresh()
            self.record_step(
                "state_fresh",
                True,
                f"timestamp={state.get('timestamp', '')} last_screenshot={state.get('last_screenshot_path', '')}",
            )

            self.exercise_refresh_loop()
            self.exercise_raw_command_path()
            self.exercise_pending_controls()
            self.exercise_screenshot_viewer(state)
            self.exercise_image_memory_viewer(state)
            self.exercise_model_catalog_reload()
            self.exercise_help_surface()
        except Exception as error:
            self.record_step("unhandled_exception", False, repr(error))
        finally:
            if self.app is not None:
                try:
                    self.pump(0.1)
                    self.app.destroy()
                except Exception as error:
                    self.warnings.append(f"destroy_failed: {error!r}")

        verdict = "pass" if not self.failures else "fail"
        report = {
            "run_id": self.run_id,
            "started_at": started_at,
            "ended_at": dt.datetime.now().isoformat(),
            "verdict": verdict,
            "failures": self.failures,
            "warnings": self.warnings,
            "steps": self.steps,
            "artifacts": {
                "log": str(self.log_path),
                "report": str(self.report_path),
            },
        }
        write_json(self.report_path, report)
        return report

    def exercise_refresh_loop(self) -> None:
        assert self.app is not None
        for _ in range(12):
            self.app.refresh_now()
            self.pump(0.05)
        self.record_step(
            "rapid_refresh",
            True,
            f"chat_lines={len(self.app.chat_text.get('1.0', 'end-1c').splitlines())} command_lines={len(self.app.command_text.get('1.0', 'end-1c').splitlines())}",
        )

    def exercise_raw_command_path(self) -> None:
        assert self.app is not None
        before_size = panel_mod.INBOX_PATH.stat().st_size if panel_mod.INBOX_PATH.exists() else 0
        self.app.send_raw("SHOW_RUNTIME()")
        self.app.send_raw("SHOW_AUTH()")
        self.app.send_raw("SHOW_LOCKS()")
        self.app.send_raw("SHOW_MODEL_STATUS()")
        self.app.interval_var.set("0.40")
        self.app.review_turn_interval_var.set("9")
        self.app.critique_turn_interval_var.set("33")
        self.app.apply_settings(show_confirmation=False)
        self.pump(0.2)
        after_size = panel_mod.INBOX_PATH.stat().st_size if panel_mod.INBOX_PATH.exists() else 0
        ok = after_size > before_size
        detail = f"inbox_bytes_before={before_size} inbox_bytes_after={after_size}"
        self.record_step("raw_command_send_and_apply_settings", ok, detail)

    def exercise_pending_controls(self) -> None:
        assert self.app is not None
        self.app.send_raw("SET_EXECUTION_MODE(assist)")
        self.app.send_raw("QUEUE_PENDING(SHOW_RUNTIME())")
        self.app.send_raw("QUEUE_PENDING(SHOW_AUTH())")
        self.app.send_raw("QUEUE_PENDING(SHOW_LOCKS())")
        pending_count = self.wait_for_pending_count(1)
        if pending_count < 1:
            self.record_step("pending_queue_population", False, f"pending_rows={pending_count}")
            return
        self.record_step("pending_queue_population", True, f"pending_rows={pending_count}")

        first_item = self.app.pending_tree.get_children()[0]
        self.app.pending_tree.selection_set(first_item)
        before_size = panel_mod.INBOX_PATH.stat().st_size if panel_mod.INBOX_PATH.exists() else 0
        self.app.approve_selected_pending()
        self.pump(0.1)
        self.app.send_raw("QUEUE_PENDING(SHOW_MODEL_STATUS())")
        self.wait_for_pending_count(1)
        second_item = self.app.pending_tree.get_children()[0]
        self.app.pending_tree.selection_set(second_item)
        self.app.clear_selected_pending()
        self.pump(0.1)
        after_size = panel_mod.INBOX_PATH.stat().st_size if panel_mod.INBOX_PATH.exists() else 0
        self.record_step(
            "pending_approve_clear",
            after_size > before_size,
            f"inbox_bytes_before={before_size} inbox_bytes_after={after_size}",
        )

    def resolve_valid_image_path(self, state: dict[str, object]) -> Path:
        candidates = []
        last_screenshot = state.get("last_screenshot_path")
        if isinstance(last_screenshot, str) and last_screenshot.strip():
            candidates.append(Path(last_screenshot))
        candidates.extend(getattr(self.app, "screenshot_files", []) or [])
        candidates.append(self.synthetic_valid_image)
        for candidate in candidates:
            path = Path(candidate)
            if path.exists():
                return path
        raise RuntimeError("No valid image path available for viewer testing.")

    def exercise_screenshot_viewer(self, state: dict[str, object]) -> None:
        assert self.app is not None
        self.app.refresh_now()
        self.pump(0.2)
        valid_path = self.resolve_valid_image_path(state)
        self.app.screenshot_files = [valid_path]
        self.app.screenshot_index = 0
        self.app.render_screenshot()
        self.pump(0.1)
        self.app.open_screenshot_popout()
        self.pump(0.2)
        self.app.set_screenshot_popout_mode("actual")
        self.pump(0.1)
        self.app.toggle_screenshot_popout_mode()
        self.pump(0.1)
        self.app.step_screenshot(0)
        self.pump(0.1)
        popout_ok = self.app.popout_window is not None and self.app.popout_window.winfo_exists()
        self.record_step("screenshot_popout", popout_ok, f"valid_path={valid_path}")

        self.app.close_screenshot_popout()
        self.app.screenshot_files = [self.synthetic_invalid_image]
        self.app.screenshot_index = 0
        self.app.render_screenshot()
        preview_text = str(self.app.screenshot_preview.cget("text"))
        self.record_step(
            "screenshot_corrupt_fallback",
            "Failed to load" in preview_text,
            preview_text[:220],
        )
        self.app.refresh_now()
        self.pump(0.1)

    def exercise_image_memory_viewer(self, state: dict[str, object]) -> None:
        assert self.app is not None
        valid_path = self.resolve_valid_image_path(state)
        self.app.image_memory_rows = [
            {
                "path": str(valid_path),
                "detail": "low",
                "sticky": False,
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        self.app.image_memory_index = 0
        self.app.render_image_memory()
        self.pump(0.1)
        self.app.open_image_memory_popout()
        self.pump(0.2)
        self.app.set_image_memory_popout_mode("actual")
        self.pump(0.1)
        self.app.toggle_image_memory_popout_mode()
        self.pump(0.1)
        popout_ok = self.app.memory_popout_window is not None and self.app.memory_popout_window.winfo_exists()
        self.record_step("image_memory_popout", popout_ok, f"valid_path={valid_path}")

        self.app.image_memory_rows = [
            {
                "path": str(self.synthetic_invalid_image),
                "detail": "high",
                "sticky": True,
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        self.app.image_memory_index = 0
        self.app.render_image_memory()
        preview_text = str(self.app.image_memory_preview.cget("text"))
        self.record_step(
            "image_memory_corrupt_fallback",
            "Failed to load" in preview_text,
            preview_text[:220],
        )
        self.app.close_image_memory_popout()
        self.app.refresh_now()
        self.pump(0.1)

    def exercise_model_catalog_reload(self) -> None:
        assert self.app is not None
        before = list(self.app.current_model_choices)
        self.app.refresh_model_catalog()
        self.pump(0.2)
        after = list(self.app.current_model_choices)
        self.record_step(
            "model_catalog_reload",
            bool(after),
            f"choices_before={len(before)} choices_after={len(after)}",
        )

    def exercise_help_surface(self) -> None:
        assert self.app is not None
        self.app.show_command_list()
        self.pump(0.1)
        help_text = self.app.help_text.get("1.0", "end-1c")
        self.record_step(
            "help_command_list",
            "SHOW_RUNTIME()" in help_text and "SET_LIVE_MODE(on|off)" in help_text,
            f"help_chars={len(help_text)}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exercise Aurora 2 control-panel UI paths against the live runtime state/inbox files.")
    parser.add_argument(
        "--state-fresh-seconds",
        type=float,
        default=20.0,
        help="Maximum allowed age for aurora_control_panel_state.json before the test starts.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional directory where ui_stress.log and ui_stress_report.json should be written.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional stable run id to embed in the report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id.strip() or ("aurora-ui-stress-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    artifact_dir = args.artifact_dir or (RUN_ROOT / run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    runner = StressRunner(run_id=run_id, artifact_dir=artifact_dir, state_fresh_seconds=args.state_fresh_seconds)
    report = runner.run()
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
