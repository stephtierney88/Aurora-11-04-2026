"""Local-only catalog and bounded offline validation service. Never imports aurora2."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aurora_command_catalog import build_command_catalog
from aurora_command_contracts import parse_inference_plan_arguments
from aurora_settings_registry import coerce_setting_value

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "aurora_validation_web"
SCHEMA = "aurora_offline_validation_v1"
MODELS = ("gpt-6-astra", "gpt-5.4", "gpt-5.2")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PRESETS = {
    "effort": dict(name="One-turn effort", case="effort", transport="responses", model="gpt-6-astra",
                   alternate_model="gpt-5.2", baseline_effort="low", changed_effort="high"),
    "model": dict(name="One-turn model", case="model", transport="chat_completions", model="gpt-5.4",
                  alternate_model="gpt-5.2", baseline_effort="low", changed_effort="high"),
    "dynamic": dict(name="Dynamic inference off / on / off", case="dynamic", transport="chat_completions",
                    model="gpt-5.4", alternate_model="gpt-5.2", baseline_effort="low", changed_effort="high"),
}
for _preset in PRESETS.values():
    _preset.update(prompt="Inspect this offline fixture and report readiness.", timeout_seconds=45, max_calls=3)


def digest(value):
    """Stable identity for JSON-safe profile, input and evidence values."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    """Publish a complete artifact atomically within its owned directory."""
    path = Path(path)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_profile(value):
    """Strict offline recipe validation, sharing Aurora's setting/plan coercion."""
    if not isinstance(value, dict) or set(value) != set(PRESETS["effort"]):
        raise ValueError("Profile must contain exactly the documented preset fields.")
    profile = dict(value)
    for field, limit in (("name", 100), ("prompt", 1000)):
        if not isinstance(profile[field], str) or not 1 <= len(profile[field].strip()) <= limit:
            raise ValueError(f"{field} must contain 1–{limit} characters.")
    if profile["case"] not in PRESETS or profile["transport"] not in ("responses", "chat_completions"):
        raise ValueError("Unsupported offline case/transport.")
    if profile["model"] not in MODELS or profile["alternate_model"] not in MODELS:
        raise ValueError("Model is outside the offline fixture matrix; no live support is implied.")
    if profile["transport"] == "responses" and (profile["model"] != "gpt-6-astra" or profile["case"] == "model"):
        raise ValueError("The current Responses fixture supports Astra and no model switching.")
    for field in ("baseline_effort", "changed_effort"):
        models = (profile["model"], profile["alternate_model"]) if profile["case"] == "model" else (profile["model"],)
        if profile[field] not in EFFORTS or (any(model != "gpt-6-astra" for model in models) and profile[field] == "max"):
            raise ValueError("Effort is outside the selected offline model matrix.")
        coerce_setting_value("inference.reasoning_effort", profile[field])
    if profile["case"] == "model" and profile["model"] == profile["alternate_model"]:
        raise ValueError("Choose a different intervention model.")
    if profile["case"] != "model" and profile["baseline_effort"] == profile["changed_effort"]:
        raise ValueError("Choose a different intervention effort.")
    if type(profile["timeout_seconds"]) is not int or not 10 <= profile["timeout_seconds"] <= 60:
        raise ValueError("timeout_seconds must be an integer from 10 to 60.")
    if type(profile["max_calls"]) is not int or profile["max_calls"] != 3:
        raise ValueError("This bounded recipe requires exactly three fake calls, including restoration.")
    parse_inference_plan_arguments("SET_NEXT_INFERENCE", ["model=" + profile["alternate_model"]])
    parse_inference_plan_arguments("SET_NEXT_REASONING_EFFORT", [profile["changed_effort"]])
    return profile


def source_files(root):
    """Only executable fixture inputs and UI assets, never private runtime data."""
    root = Path(root)
    return sorted(list(root.glob("aurora*.py")) + list((root / "aurora_validation_web").glob("*.*")))


def source_identity(root):
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source_files(root)}
    return {"fingerprint": digest(hashes), "hashes": hashes}


def git_read(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                                timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def command_subsystems(row):
    """Presentation tags, not a second source of command admission authority."""
    name = row["command"].upper()
    tags = []
    if row["binding_kind"] == "desktop":
        tags.append("Desktop interaction")
    if any(word in name for word in ("HELD_INPUT", "CANCEL", "SHUTDOWN", "RELEASE")):
        tags.append("Held inputs / cancellation")
    if any(word in name for word in ("REASONING", "NEXT_INFERENCE", "RESPONSES")):
        tags.append("Adaptive reasoning")
    if any(word in name for word in ("SCHEDUL", "TURN", "INFERENCE", "PENDING", "QUEUE", "WAIT")):
        tags.append("Turn scheduling")
    if any(word in name for word in ("MODEL", "TEMPERATURE", "VERBOSITY", "LIVE_MODE", "DEFAULT", "SETTING")):
        tags.append("Model execution / configuration")
    return tags or ["Other capabilities"]


class ValidationService:
    """Single-run owner with persistent profiles/results and restart uncertainty."""

    def __init__(self, root, storage):
        self.root, self.storage = Path(root).resolve(), Path(storage).resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.thread = None
        self.active = None
        self.catalog = build_command_catalog(self.root)
        for row in self.catalog["commands"]:
            row["subsystems"] = command_subsystems(row)
        self.identity = source_identity(self.root)
        self.owner_file = (self.storage / "owner.lock").open("a+b")
        self.owner_file.seek(0)
        self.owner_file.write(b"0")
        self.owner_file.flush()
        self.owner_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.owner_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.owner_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner_file.close()
            raise ValueError("Another console owns this storage directory.")
        for folder in ("runs", "profiles", "scratch"):
            (self.storage / folder).mkdir(exist_ok=True)
        for path in (self.storage / "runs").glob("*.json"):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["status"] in ("running", "cancelling"):
                row.update(status="interrupted_unknown", error="Console restarted; no automatic replay.")
                write_json(path, row)

    def snapshot(self):
        head = git_read(self.root, "rev-parse", "HEAD")
        status = git_read(self.root, "status", "--porcelain")
        return {"schema": SCHEMA, "catalog": self.catalog, "source": self.identity,
                "local_head": head, "local_dirty": bool(status) if head and status is not None else None,
                "connected_repository": {"head": None, "status": "not queried"},
                "existing_runtime": {"identity": None, "status": "not connected"},
                "presets": PRESETS, "fixture_matrix": {"models": MODELS, "efforts": EFFORTS},
                "live_execution": False}

    def preview(self, profile, fingerprint):
        profile = validate_profile(profile)
        if fingerprint != self.identity["fingerprint"] or source_identity(self.root) != self.identity:
            raise ValueError("Source changed. Restart the console to refresh catalog and runner identity.")
        return {"schema": SCHEMA, "mode": "dry_run", "profile": profile, "profile_version": digest(profile),
                "source_fingerprint": fingerprint, "steps": ["baseline", profile["case"], "restoration"],
                "real_api_calls": 0, "native_effects": 0, "estimated_api_cost": 0,
                "expected_fake_calls": 3, "runtime_mutated": False,
                "notes": "Offline only. Dynamic case uses review cadence 1 with constant review effort; other cases disable cadence."}

    def records(self, folder):
        with self.lock:
            paths = sorted((self.storage / folder).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            return [json.loads(path.read_text(encoding="utf-8")) for path in paths[:100]]

    def retain(self, folder):
        paths = sorted((self.storage / folder).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[100:]:
            path.unlink()  # Exact files owned by this store; no age/process sweep.

    def save_profile(self, profile):
        profile = validate_profile(profile)
        row = {"version": digest(profile), "profile": profile}
        with self.lock:
            write_json(self.storage / "profiles" / (row["version"] + ".json"), row)
            self.retain("profiles")
        return row

    def start(self, profile, fingerprint, request_id):
        preview = self.preview(profile, fingerprint)
        try:
            request_id = str(uuid.UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("request_id must be a UUID; reuse it for an identical retry.")
        path = self.storage / "runs" / (request_id + ".json")
        with self.lock:
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                if old["profile_version"] != preview["profile_version"] or old["source_fingerprint"] != fingerprint:
                    raise ValueError("Request ID already belongs to different inputs.")
                return old
            if self.thread and self.thread.is_alive():
                raise ValueError("Another offline run is active.")
            row = dict(preview, run_id=request_id, mode="fake_provider", runtime_mutated="isolated fixture only",
                       status="running", started_at=time.time(),
                       result=None, error=None, cleanup=None)
            write_json(path, row)
            self.active = request_id
            self.cancel_event.clear()
            self.thread = threading.Thread(target=self._run, args=(row,), name="aurora-validation-run")
            self.thread.start()
            return row

    def cancel(self, run_id):
        with self.lock:
            if self.active != run_id or not self.thread or not self.thread.is_alive():
                return {"status": "not_active", "run_id": run_id}
            self.cancel_event.set()
            return {"status": "cancelling", "run_id": run_id}

    def _run(self, row):
        started = time.monotonic()
        process, work, temporary = None, None, None
        try:
            temporary = tempfile.TemporaryDirectory(prefix="run-", dir=self.storage / "scratch")
            work = Path(temporary.name)
            # Cleanup is below process termination, including exceptions during setup.
            if work.parent == self.storage / "scratch":
                for path in source_files(self.root):
                    target = work / path.relative_to(self.root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                if source_identity(work) != self.identity:
                    raise ValueError("Source changed during fixture copy; run rejected.")
                write_json(work / "profile.json", row["profile"])
                # Do not pass API credentials or Aurora configuration to the child.
                allowed = {"systemroot", "windir", "path", "temp", "tmp", "userprofile", "appdata", "localappdata"}
                env = {key: value for key, value in os.environ.items() if key.lower() in allowed}
                env.update(AURORA_ENABLE_TEXT_INPUT_PROCESS="0", AURORA_AUTH_MODE="api_key", PYTHONUNBUFFERED="1")
                with (work / "process.log").open("w", encoding="utf-8") as output:
                    process = subprocess.Popen([sys.executable, str(work / "aurora_validation_worker.py")],
                                               cwd=work, env=env, stdout=output, stderr=subprocess.STDOUT,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    row["ownership"] = {"pid": process.pid, "started_at": time.time(), "path": str(work)}
                    write_json(self.storage / "runs" / (row["run_id"] + ".json"), row)
                    deadline = started + row["profile"]["timeout_seconds"]
                    while process.poll() is None:
                        if self.cancel_event.wait(0.05) or time.monotonic() > deadline:
                            (work / "cancel").touch()
                            row["status"] = "cancelled" if self.cancel_event.is_set() else "timed_out"
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                process.terminate()
                                try:
                                    process.wait(timeout=3)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                    process.wait(timeout=3)
                            break
                    if (work / "result.json").exists():
                        row["result"] = json.loads((work / "result.json").read_text(encoding="utf-8"))
                    if row["status"] == "running":
                        row["status"] = "passed" if process.returncode == 0 and (row["result"] or {}).get("status") == "passed" else "failed"
                    if row["status"] != "passed":
                        row["error"] = (row["result"] or {}).get("error") or "Worker did not complete; restoration inside discarded fixture is unverified."
                if row["status"] != "passed":
                    with (work / "process.log").open("rb") as log:
                        log.seek(max(0, log.seek(0, 2) - 2000))
                        row["worker_log_tail"] = log.read().decode("utf-8", errors="replace")
        except Exception as error:
            row.update(status="failed", error=f"{type(error).__name__}: {error}")
        finally:
            try:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if temporary is not None:
                    temporary.cleanup()
            except (OSError, subprocess.TimeoutExpired) as error:
                row.update(status="cleanup_failed", error="Owned fixture cleanup failed: " + str(error))
            row.update(elapsed_ms=round((time.monotonic() - started) * 1000, 2), finished_at=time.time(),
                       cleanup={"worker_stopped": process is None or process.poll() is not None,
                                "fixture_removed": work is None or not work.exists()})
            with self.lock:
                write_json(self.storage / "runs" / (row["run_id"] + ".json"), row)
                self.active = None
                self.retain("runs")

    def close(self):
        self.cancel_event.set()
        if self.thread:
            self.thread.join(15)
            if self.thread.is_alive():
                raise RuntimeError("Offline worker cleanup is still pending.")
        self.owner_file.close()


def make_server(service, port=0):
    """Loopback-only HTTP adapter; APIs require bearer auth and same-origin writes."""
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_args):
            pass  # Never log bootstrap tokens or profile text.

        def reply(self, status, value, content_type="application/json"):
            data = json.dumps(value, allow_nan=False).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self, api=False):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                self.reply(403, {"error": "Invalid local host."})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin != "http://" + host:
                self.reply(403, {"error": "Cross-origin access is disabled."})
                return False
            if api and not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"error": "Open the console using its launch URL."})
                return False
            return True

        def do_GET(self):
            if not self.allowed(self.path.startswith("/api/")):
                return
            if self.path == "/api/catalog":
                self.reply(200, service.snapshot())
            elif self.path in ("/api/runs", "/api/profiles"):
                self.reply(200, service.records(self.path.split("/")[-1]))
            elif self.path in ("/", "/app.js", "/style.css"):
                name = "index.html" if self.path == "/" else self.path[1:]
                mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
                self.reply(200, (ASSETS / name).read_bytes(), mime)
            else:
                self.reply(404, {"error": "Not found."})

        def do_POST(self):
            if not self.allowed(True):
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Expected bounded application/json body.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected object.")
                if self.path == "/api/preview":
                    result = service.preview(body["profile"], body["fingerprint"])
                elif self.path == "/api/run":
                    result = service.start(body["profile"], body["fingerprint"], body["request_id"])
                elif self.path == "/api/cancel":
                    result = service.cancel(body["run_id"])
                elif self.path == "/api/profiles":
                    result = service.save_profile(body["profile"])
                else:
                    self.reply(404, {"error": "No such offline operation."})
                    return
                self.reply(200, result)
            except (ValueError, KeyError, TypeError) as error:
                self.reply(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--storage", type=Path, default=ROOT / ".aurora-validation")
    parser.add_argument("--preview", type=Path, help="Validate a profile JSON file without starting HTTP.")
    parser.add_argument("--run", type=Path, help="Run a profile JSON file with the guarded fake provider.")
    args = parser.parse_args()
    service = ValidationService(ROOT, args.storage)
    server = None
    try:
        if args.preview or args.run:
            profile = json.loads((args.preview or args.run).read_text(encoding="utf-8"))
            if args.preview:
                result = service.preview(profile, service.identity["fingerprint"])
            else:
                result = service.start(profile, service.identity["fingerprint"], str(uuid.uuid4()))
                service.thread.join()
                result = next(row for row in service.records("runs") if row["run_id"] == result["run_id"])
            print(json.dumps(result, indent=2))
            return 0 if result.get("status", "passed") == "passed" else 1
        server, token = make_server(service, args.port)
        print(f"Aurora offline console: http://127.0.0.1:{server.server_port}/#token={token}", flush=True)
        print("Local only; no live API calls. Ctrl+C stops the server and its owned worker.", flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
