"""Optional owned-process boundary for a subscription inference stream.

Auth/catalog preflight stays in the caller so cancellation cannot kill a rotating
credential-store write. Bearer and request travel only through an anonymous pipe.
The child performs one HTTP request, never executes commands, and never retries.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import aurora_execution_evidence as evidence

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_LINE_BYTES = 9 * 1024 * 1024
BOUNDED_IDLE_SECONDS = 90.0
BOUNDED_TOTAL_SECONDS = 180.0
_LOCK = threading.Lock()
_LAST = {"status": "idle", "active": False}


def stream_worker_snapshot():
    with _LOCK:
        return dict(_LAST)


def _limits(idle, total):
    values = (float(idle), float(total))
    if any(not math.isfinite(v) or v <= 0 or v > 600 for v in values):
        raise ValueError("Subscription stream limits must be finite, positive and at most 600 seconds.")
    return values


def run_bounded_stream(payload, bearer, cancellation_token, *, idle_seconds=BOUNDED_IDLE_SECONDS,
                       total_seconds=BOUNDED_TOTAL_SECONDS, worker_command=None):
    """One hidden HTTP worker; cancellation/deadline discards all unfinished output.

    The optional command/limits are dependency-injection seams for local fixtures,
    not endpoint/model-command configuration. Production uses this module only.
    """
    from aurora_chatgpt_auth import ChatGPTAuthError
    from aurora_responses_reasoning import completed_response_text

    idle_seconds, total_seconds = _limits(idle_seconds, total_seconds)
    cancellation_token.check()
    body = json.dumps({"payload": payload, "bearer": bearer, "idle_seconds": idle_seconds,
                       "total_seconds": total_seconds}, ensure_ascii=True).encode("utf-8")
    if len(body) > MAX_INPUT_BYTES:
        raise ChatGPTAuthError("Bounded subscription request exceeds the 32 MiB local input limit; no request sent.")
    command = worker_command or [sys.executable, "-u", str(Path(__file__).resolve()), "--stream-worker"]
    env = dict(os.environ)
    for key in ("OPENAI_API_KEY", "OPENAI_2023_API_KEY"):
        env.pop(key, None)
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=env, close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    diagnostics = dict(status="running", active=True, phase="worker_start", pid=process.pid, created_at=time.time(),
                       idle_seconds=idle_seconds, total_seconds=total_seconds, scope="inference_stream_only")
    with _LOCK:
        _LAST.clear()
        _LAST.update(diagnostics)
    def publish(**values):
        diagnostics.update(values)
        with _LOCK:
            if _LAST.get("pid") == process.pid:
                _LAST.update(values)
    messages = queue.Queue(maxsize=8)
    stop = threading.Event()

    def deliver(kind, value=None):
        while not stop.is_set():
            try:
                messages.put((kind, value), timeout=.1)
                return
            except queue.Full:
                continue

    def write_request():
        try:
            process.stdin.write(body)
            process.stdin.close()
        except (OSError, ValueError):
            deliver("pipe_error")

    def read_results():
        try:
            while not stop.is_set():
                line = process.stdout.readline(MAX_OUTPUT_LINE_BYTES + 1)
                if not line:
                    deliver("eof")
                    return
                if len(line) > MAX_OUTPUT_LINE_BYTES:
                    deliver("oversized")
                    return
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    deliver("protocol_error")
                    return
                deliver("message", value)
        except (OSError, ValueError):
            deliver("pipe_error")

    writer = threading.Thread(target=write_request, name="aurora-subscription-write", daemon=True)
    reader = threading.Thread(target=read_results, name="aurora-subscription-read", daemon=True)
    terminal = "failed"
    attempt_observed = False
    try:
        writer.start()
        reader.start()
        while True:
            cancellation_token.check()
            elapsed = time.monotonic() - started
            if elapsed >= total_seconds:
                terminal = "deadline"
                raise ChatGPTAuthError("Subscription inference deadline exceeded; no commands accepted and no request replayed.")
            try:
                kind, message = messages.get(timeout=min(.1, total_seconds-elapsed))
            except queue.Empty:
                continue
            if kind != "message" or not isinstance(message, dict):
                raise ChatGPTAuthError("Subscription worker ended without a validated completion; no commands accepted.")
            if message.get("kind") == "phase":
                phase = message.get("phase")
                if phase not in {"waiting_headers", "headers_received", "first_line"}:
                    raise ChatGPTAuthError("Invalid subscription worker phase.")
                if phase == "waiting_headers" and not attempt_observed:
                    evidence.attempt(payload, "chatgpt_subscription_responses", "openai_chatgpt")
                    attempt_observed = True
                if phase == "headers_received":
                    evidence.response()
                publish(phase=phase, phase_elapsed_seconds=round(elapsed, 3))
                continue
            if message.get("kind") != "terminal":
                raise ChatGPTAuthError("Invalid subscription worker result.")
            child_diagnostics = message.get("diagnostics") or {}
            if isinstance(child_diagnostics, dict):
                if type(child_diagnostics.get("http_status")) is int:
                    evidence.response(status=child_diagnostics["http_status"],
                        headers={"x-request-id": child_diagnostics.get("provider_request_id")})
                allowed = {key: value for key, value in child_diagnostics.items()
                           if key in {"headers_seconds", "first_line_seconds", "line_count", "max_line_gap_seconds", "elapsed_seconds"}
                           and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0}
                publish(**allowed)
            if message.get("ok") is not True:
                error = message.get("error")
                raise ChatGPTAuthError(error[:500] if isinstance(error, str) else "Subscription stream failed; no commands accepted.")
            result = message.get("result")
            answer = completed_response_text(result)
            evidence.response(body=result)
            cancellation_token.check()
            process.wait(timeout=2)
            if process.returncode != 0:
                raise ChatGPTAuthError("Subscription worker failed after output; no commands accepted.")
            if time.monotonic() - started >= total_seconds:
                terminal = "deadline"
                raise ChatGPTAuthError("Subscription inference deadline exceeded; no commands accepted.")
            cancellation_token.check()
            terminal = "completed"
            return result, answer, diagnostics
    except BaseException as error:
        from aurora_runtime_work import WorkCancelled
        if isinstance(error, WorkCancelled):
            terminal = "cancelled"
        raise
    finally:
        stop.set()
        terminated = process.poll() is None
        if terminated:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if writer.ident is not None:
            writer.join(2)
        if reader.ident is not None:
            reader.join(2)
        for stream in (process.stdin, process.stdout):
            if stream and not stream.closed:
                stream.close()
        publish(status=terminal, active=process.poll() is None, worker_exit=process.returncode,
                 locally_terminated=terminated, elapsed_seconds=round(time.monotonic()-started, 3),
                 pipe_threads_closed=not (writer.is_alive() or reader.is_alive()))


def worker_main():
    """Child protocol: bounded stdin; phase records; one complete result or safe error."""
    from aurora_chatgpt_auth import ChatGPTAuthError
    from aurora_chatgpt_transport import request_subscription_stream

    class WorkerToken:
        def check(self):
            pass  # The parent owns cancellation and termination of this child.

    def emit(value):
        line = json.dumps(value, ensure_ascii=True).encode("utf-8") + b"\n"
        if len(line) > MAX_OUTPUT_LINE_BYTES:
            raise ChatGPTAuthError("Bounded subscription completion exceeds the local result limit; no commands accepted.")
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()

    diagnostics = {}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ChatGPTAuthError("Bounded subscription input exceeds the local limit.")
        request = json.loads(raw)
        idle, total = _limits(request["idle_seconds"], request["total_seconds"])
        result, _answer = request_subscription_stream(request["payload"], request["bearer"], WorkerToken(),
            idle_seconds=idle, total_seconds=total, diagnostics=diagnostics,
            phase_callback=lambda phase: emit({"kind": "phase", "phase": phase}), chunk_size=1)
        emit({"kind": "terminal", "ok": True, "result": result, "diagnostics": diagnostics})
    except ChatGPTAuthError as error:
        emit({"kind": "terminal", "ok": False, "error": str(error), "diagnostics": diagnostics})
    except BaseException:
        emit({"kind": "terminal", "ok": False, "error": "Subscription worker failed before a validated completion; no commands accepted.", "diagnostics": diagnostics})


if __name__ == "__main__":
    if sys.argv[1:] != ["--stream-worker"]:
        raise SystemExit("This module is an internal Aurora subscription worker.")
    worker_main()
