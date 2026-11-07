"""Exercise actual child/socket cleanup with synthetic localhost streams only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from aurora_chatgpt_auth import ChatGPTAuthError
from aurora_chatgpt_transport import perform_subscription_request
from aurora_runtime_work import BoundedModelIO, WorkToken, WorkCancelled
from aurora_subscription_worker import run_bounded_stream, stream_worker_snapshot


class SubscriptionWorkerTests(unittest.TestCase):
    def test_request_local_evidence_survives_child_protocol(self):
        import aurora_execution_evidence as evidence
        item = evidence.TransportEvidence({'reasoning_effort': 'low'})
        with evidence.observe_transport(item):
            evidence.instrumented()
            self.run_stream('complete')
        result = item.snapshot(close=True)
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(result['attempts'][0]['transport'], 'chatgpt_subscription_responses')
        self.assertEqual(result['attempts'][0]['provider_model'], 'fixture-model')
        self.assertEqual(result['attempts'][0]['provider_request_id'], 'req_local_fixture')
        self.assertTrue(result['attempts'][0]['http_response_observed'])
        self.assert_clean('completed')

    def setUp(self):
        self.requests = []
        self.received = threading.Event()
        self.release = threading.Event()
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((self.path, body, self.headers.get("Authorization")))
                outer.received.set()
                try:
                    if self.path.startswith("/headers"):
                        outer.release.wait(5)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("x-request-id", "req_local_fixture")
                    self.end_headers()
                    if self.path.startswith("/partial"):
                        self.wfile.write(b'data: {"type":"response.output_text.delta","delta":"UNEXECUTABLE_PARTIAL"}\n\n')
                        self.wfile.flush()
                        outer.release.wait(5)
                        return
                    if self.path.startswith("/slow"):
                        time.sleep(.6)
                    if self.path.startswith("/failure"):
                        event = {"type": "response.failed", "response": {"error": {"code": "fixture_failure", "message": "PRIVATE_PROVIDER_BODY"}}}
                    else:
                        event = {"type": "response.completed", "response": {"id": "fixture", "status": "completed", "model": "fixture-model",
                                 "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "validated final"}]}]}}
                    self.wfile.write(("data: "+json.dumps(event)+"\n\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def run_stream(self, route, token=None, **limits):
        command = [sys.executable, str(Path(__file__).with_name("subscription_worker_fixture.py")),
                   f"http://127.0.0.1:{self.server.server_port}/{route}"]
        return run_bounded_stream({"model": "fixture-model", "input": [{"role": "user", "content": "synthetic"}]},
            "fixture-only-bearer", token or WorkToken(1), worker_command=command,
            idle_seconds=limits.get("idle_seconds", 2), total_seconds=limits.get("total_seconds", 4))

    def assert_clean(self, status):
        snapshot = stream_worker_snapshot()
        self.assertEqual(snapshot["status"], status)
        self.assertFalse(snapshot["active"])
        self.assertTrue(snapshot["pipe_threads_closed"])
        self.assertIsNotNone(snapshot["worker_exit"])
        self.assertFalse(any(t.name.startswith("aurora-subscription-") for t in threading.enumerate()))
        self.assertNotIn("fixture-only-bearer", json.dumps(snapshot))
        self.assertNotIn("PRIVATE_PROVIDER_BODY", json.dumps(snapshot))
        self.assertEqual(len(self.requests), 1)

    def test_real_completion_with_idle_budget_and_metadata(self):
        result, answer, diagnostics = self.run_stream("slow")
        self.assertEqual(answer, "validated final")
        self.assertEqual(result["model"], "fixture-model")
        self.assertGreaterEqual(diagnostics["first_line_seconds"], .5)
        self.assertGreater(diagnostics["line_count"], 0)
        self.assertEqual(self.requests[0][2], "Bearer fixture-only-bearer")
        self.assert_clean("completed")

    def test_socket_idle_failure_never_replays(self):
        with self.assertRaisesRegex(ChatGPTAuthError, "read_timeout"):
            self.run_stream("slow", idle_seconds=.15)
        self.assert_clean("failed")

    def test_cancel_during_header_wait_or_partial_stream(self):
        for route in ("headers", "partial"):
            with self.subTest(route=route):
                self.requests.clear()
                self.received.clear()
                token = WorkToken(1)
                def cancel():
                    self.received.wait(3)
                    time.sleep(.15)
                    token.event.set()
                helper = threading.Thread(target=cancel)
                helper.start()
                start = time.monotonic()
                try:
                    with self.assertRaises(WorkCancelled):
                        self.run_stream(route, token)
                finally:
                    helper.join(4)
                self.assertLess(time.monotonic()-start, 2.5)
                self.assert_clean("cancelled")

    def test_deadline_discards_partial_and_releases_owned_process(self):
        with self.assertRaisesRegex(ChatGPTAuthError, "deadline"):
            self.run_stream("partial", total_seconds=.8)
        self.assert_clean("deadline")

    def test_provider_failure_does_not_export_body(self):
        with self.assertRaisesRegex(ChatGPTAuthError, "fixture_failure") as error:
            self.run_stream("failure")
        self.assertNotIn("PRIVATE_PROVIDER_BODY", str(error.exception))
        self.assert_clean("failed")

    def test_runtime_slot_drains_after_cancel_and_explicit_request_can_resume(self):
        io, token = BoundedModelIO(), WorkToken(1)
        self.addCleanup(token.event.set)
        def cancel_when_connected():
            if self.received.is_set():
                token.event.set()
        with self.assertRaises(WorkCancelled):
            io.call(lambda _packet: self.run_stream("partial", token), {}, token,
                    service_control=cancel_when_connected)
        deadline = time.monotonic()+2.5
        while io.busy and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertFalse(io.busy)
        self.assertEqual(io.snapshot()["discarded_results"], 1)
        self.assert_clean("cancelled")
        self.requests.clear()
        self.received.clear()
        next_token = WorkToken(2)
        result, answer, _diagnostics = io.call(lambda _packet: self.run_stream("ok", next_token), {}, next_token)
        self.assertEqual(answer, "validated final")
        self.assert_clean("completed")

    def test_cancelled_input_never_starts_process(self):
        token = WorkToken(1)
        token.event.set()
        with patch("aurora_subscription_worker.subprocess.Popen") as create, self.assertRaises(WorkCancelled):
            self.run_stream("ok", token)
        create.assert_not_called()

    def test_policy_rejection_happens_before_auth_or_network(self):
        with patch("aurora_chatgpt_transport.ChatGPTAuth") as auth, self.assertRaisesRegex(ChatGPTAuthError, "Unknown"):
            perform_subscription_request({}, WorkToken(1), policy="invented")
        auth.assert_not_called()

    def test_worker_crash_closes_pipes_without_accepting_output(self):
        command = [sys.executable, "-c", "raise SystemExit(7)"]
        with self.assertRaises(ChatGPTAuthError):
            run_bounded_stream({}, "fixture-only-bearer", WorkToken(1), worker_command=command)
        snapshot = stream_worker_snapshot()
        self.assertFalse(snapshot["active"])
        self.assertTrue(snapshot["pipe_threads_closed"])

    def test_bounded_route_keeps_parent_catalog_checks_and_receipt(self):
        auth = Mock()
        auth.access.return_value = ("fixture-only-bearer", "one")
        result = {"model": "fixture-model", "id": "synthetic"}
        with patch("aurora_chatgpt_transport.account_models", return_value=("one", [{"slug": "fixture-model"}])), \
             patch("aurora_subscription_worker.run_bounded_stream", return_value=(result, "done", {"status": "completed"})) as worker, \
             patch("aurora_chatgpt_transport.requests.post") as direct:
            response = perform_subscription_request({"model": "fixture-model", "messages": [{"role": "user", "content": "hello"}]},
                                                     WorkToken(1), auth, policy="bounded")
            self.assertEqual(response.json()["aurora_subscription"]["request_policy"], "bounded")
            self.assertEqual(worker.call_args.args[1], "fixture-only-bearer")
            worker.assert_called_once()
            direct.assert_not_called()
            worker.reset_mock()
            with self.assertRaisesRegex(ChatGPTAuthError, "not listed"):
                perform_subscription_request({"model": "unknown", "messages": [{"role": "user", "content": "hello"}]}, WorkToken(1), auth, policy="bounded")
            worker.assert_not_called()
            direct.assert_not_called()


if __name__ == "__main__":
    unittest.main()
