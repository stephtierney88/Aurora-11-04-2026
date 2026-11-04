import contextlib
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from obs_readonly_client import (
    MAX_MESSAGE_BYTES, PASSWORD_ENV, READ_REQUESTS, ObsReadOnlyClient,
    ObsReadOnlyError, authentication_response, read_obs_configuration,
)
from obs_readonly_mcp_server import ObsReadOnlyMcpServer


ROOT = Path(__file__).resolve().parents[1]
SECRET = "fixture-password-never-return"
PRIVATE = "private-settings-never-return"
CHALLENGE = {"salt": "test-salt", "challenge": "test-challenge"}


def fixture_responses():
    return {
        "GetVersion": {"obsVersion": "31.0.3", "obsWebSocketVersion": "5.5.4", "rpcVersion": 1,
                       "availableRequests": sorted(READ_REQUESTS) + ["StartStream", "GetStreamServiceSettings"]},
        "GetSceneList": {"currentProgramSceneName": "Scene A", "currentPreviewSceneName": None,
                         "scenes": [{"sceneName": "Scene A", "sceneIndex": 0}, {"sceneName": "Scene B", "sceneIndex": 1}]},
        "GetInputList": {"inputs": [{"inputName": "Source A", "inputKind": "color_source_v3", "inputSettings": PRIVATE}]},
        "GetSceneItemList": {"sceneItems": [{"sourceName": "Source A", "sceneItemId": 1, "sceneItemEnabled": True,
                                             "sceneItemLocked": False, "isGroup": False, "inputKind": "color_source_v3"}]},
        "GetRecordStatus": {"outputActive": False, "outputPaused": False, "outputDuration": 0, "outputBytes": 0, "outputPath": PRIVATE},
        "GetStreamStatus": {"outputActive": False, "outputReconnecting": False, "outputDuration": 0, "outputBytes": 0, "streamKey": PRIVATE},
    }


@contextlib.contextmanager
def fake_obs(mode="ready"):
    messages, errors = [], []
    stopped = threading.Event()
    logger = logging.Logger("test.obs.private")
    logger.disabled = True

    def handler(connection):
        try:
            hello = {"rpcVersion": 1, "authentication": CHALLENGE}
            if mode == "unauthenticated":
                hello.pop("authentication")
            connection.send(json.dumps({"op": 0, "d": hello}))
            identify = json.loads(connection.recv(timeout=2))
            messages.append({"op": identify["op"], "eventSubscriptions": identify["d"].get("eventSubscriptions")})
            if identify["d"].get("authentication") != authentication_response(SECRET, CHALLENGE):
                connection.close(code=4009, reason=PRIVATE)
                return
            connection.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
            responses = fixture_responses()
            if mode == "unsupported":
                responses["GetVersion"]["availableRequests"].remove("GetRecordStatus")
            if mode == "malformed_recording":
                responses["GetRecordStatus"]["outputActive"] = "false"
            for raw in connection:
                request = json.loads(raw)
                messages.append(request)
                name = request["d"]["requestType"]
                if mode == "timeout":
                    stopped.wait(0.4)
                    return
                if mode == "oversized":
                    connection.send("x" * (MAX_MESSAGE_BYTES + 1))
                    continue
                if mode == "event":
                    connection.send(json.dumps({"op": 5, "d": {"private": PRIVATE}}))
                    continue
                request_id = "wrong-request" if mode == "wrong_identity" else request["d"]["requestId"]
                failed = mode == "failed_recording" and name == "GetRecordStatus"
                payload = {"requestType": name, "requestId": request_id,
                           "requestStatus": {"result": not failed, "code": 500 if failed else 100, "comment": PRIVATE},
                           "responseData": responses[name]}
                connection.send(json.dumps({"op": 7, "d": payload}))
        except ConnectionClosed:
            pass
        except Exception as error:
            errors.append(type(error).__name__)

    with serve(handler, "127.0.0.1", 0, subprotocols=["obswebsocket.json"], ping_interval=None, logger=logger) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.socket.getsockname()[1], messages, errors
        finally:
            stopped.set()
            server.shutdown()
            thread.join(timeout=3)
            if thread.is_alive():
                raise AssertionError("Fixture server did not stop")


class ObsReadOnlyTests(unittest.TestCase):
    def make_config(self, directory, **updates):
        path = Path(directory) / "obs-websocket.json"
        data = {"server_enabled": True, "auth_required": True, "server_port": 4455, "server_password": SECRET}
        data.update(updates)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_configuration_never_returns_credential_or_writes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {PASSWORD_ENV: ""}):
            path = self.make_config(directory)
            before = path.read_bytes()
            config = read_obs_configuration(path)
            client = ObsReadOnlyClient(config_path=path)
            self.assertNotIn(SECRET, repr(config))
            self.assertNotIn(SECRET, json.dumps(client.configuration_snapshot()))
            self.assertEqual(path.read_bytes(), before)
            path.write_bytes(b"x" * 65537)
            self.assertEqual(read_obs_configuration(path).reason, "configuration_invalid")

    def test_missing_disabled_insecure_and_invalid_config_do_not_connect(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {PASSWORD_ENV: ""}), patch("socket.create_connection") as connect:
            path = Path(directory) / "missing.json"
            self.assertEqual(ObsReadOnlyClient(config_path=path).observe()["reason"], "configuration_missing")
            cases = [({"server_enabled": False}, "server_disabled"),
                     ({"auth_required": False}, "authentication_required"),
                     ({"server_port": True}, "invalid_port"),
                     ({"server_password": ""}, "credential_missing")]
            for updates, reason in cases:
                with self.subTest(reason=reason):
                    path = self.make_config(directory, **updates)
                    result = ObsReadOnlyClient(config_path=path).observe()
                    self.assertEqual(result["reason"], reason)
                    self.assertFalse(result["complete"])
                    self.assertEqual(result["sections"], {})
            connect.assert_not_called()

    def test_limits_and_identity_reject_invalid_values(self):
        for values in ({"port": True}, {"port": 65536}, {"timeout_seconds": float("nan")},
                       {"timeout_seconds": 0}, {"max_items": 0}, {"max_items": True}):
            with self.subTest(values=values), self.assertRaises(ObsReadOnlyError):
                ObsReadOnlyClient(**values)
        client = ObsReadOnlyClient()
        for identity in (None, "", "bad id", "x" * 129, True):
            with self.subTest(identity=identity), self.assertRaises(ObsReadOnlyError):
                client.observation_receipt(identity, "request")

    def test_transport_refuses_mutating_or_parameterized_reads(self):
        client = ObsReadOnlyClient()
        for name, data in (("StartRecord", {}), ("SetCurrentProgramScene", {}),
                           ("GetStreamServiceSettings", {}), ("GetVersion", {"injected": True}),
                           ("GetSceneItemList", {"sceneName": "ok", "extra": True})):
            with self.subTest(name=name), self.assertRaises(ObsReadOnlyError):
                client._request(None, time.monotonic() + 1, name, data)

    def test_real_authenticated_socket_round_trip_and_privacy(self):
        with fake_obs() as (port, messages, errors), patch.dict(os.environ, {PASSWORD_ENV: SECRET, "HTTP_PROXY": "http://invalid.invalid:1"}):
            client = ObsReadOnlyClient(port=port, max_items=1)
            receipt = client.observation_receipt("client-a", "request-a")
        self.assertEqual(errors, [])
        self.assertEqual(receipt["result"], "observed")
        self.assertTrue(receipt["terminal"])
        self.assertFalse(receipt["uncertain"])
        self.assertFalse(receipt["mutation_attempted"])
        self.assertFalse(receipt["automatic_replay_allowed"])
        self.assertEqual(receipt["client_id"], "client-a")
        self.assertEqual(receipt["request_id"], "request-a")
        snapshot = receipt["observation"]
        self.assertTrue(snapshot["authenticated"])
        self.assertFalse(snapshot["atomic"])
        self.assertTrue(snapshot["sections"]["scenes"]["truncated"])
        self.assertEqual(snapshot["sections"]["scenes"]["total"], 2)
        self.assertFalse(snapshot["sections"]["recording"]["active"])
        self.assertEqual(messages[0], {"op": 1, "eventSubscriptions": 0})
        requests = [row["d"]["requestType"] for row in messages[1:]]
        self.assertEqual(set(requests), READ_REQUESTS)
        self.assertEqual(len(requests), len(READ_REQUESTS))
        for secret in (SECRET, PRIVATE, "streamKey", "outputPath", "inputSettings", "StartStream"):
            self.assertNotIn(secret, json.dumps(receipt))

    def test_failures_never_guess_stopped_or_retry(self):
        cases = {"unauthenticated": "authentication_required", "wrong_identity": "response_identity_mismatch",
                 "event": "unexpected_message", "timeout": "timeout", "oversized": "connection_closed"}
        for mode, reason in cases.items():
            with self.subTest(mode=mode), fake_obs(mode) as (port, messages, errors), patch.dict(os.environ, {PASSWORD_ENV: SECRET}):
                start = time.monotonic()
                result = ObsReadOnlyClient(port=port, timeout_seconds=0.15 if mode == "timeout" else 2).observe()
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["complete"])
                self.assertNotIn("recording", result["sections"])
                self.assertLess(time.monotonic() - start, 3)
                self.assertLessEqual(len([row for row in messages if row["op"] == 6]), 1)
        with fake_obs() as (port, messages, errors), patch.dict(os.environ, {PASSWORD_ENV: "wrong-password"}):
            self.assertEqual(ObsReadOnlyClient(port=port).observe()["reason"], "authentication_failed")

    def test_partial_sections_keep_unknown_distinct_from_false(self):
        for mode, reason in (("unsupported", "unsupported_request"), ("failed_recording", "request_failed"), ("malformed_recording", "invalid_response")):
            with self.subTest(mode=mode), fake_obs(mode) as (port, messages, errors), patch.dict(os.environ, {PASSWORD_ENV: SECRET}):
                receipt = ObsReadOnlyClient(port=port).observation_receipt("client", "request")
                self.assertEqual(receipt["result"], "partial")
                self.assertEqual(receipt["observation"]["sections"]["recording"], {"available": False, "reason": reason})
                self.assertFalse(receipt["observation"]["sections"]["streaming"]["active"])
                self.assertNotIn(PRIVATE, json.dumps(receipt))

    def test_connection_refusal_is_unavailable(self):
        with patch.dict(os.environ, {PASSWORD_ENV: SECRET}), patch("socket.create_connection", side_effect=ConnectionRefusedError(SECRET)):
            result = ObsReadOnlyClient(port=4455).observe()
        self.assertEqual(result["reason"], "connection_unavailable")
        self.assertNotIn(SECRET, json.dumps(result))

    def test_mcp_authority_discovery_and_argument_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            server = ObsReadOnlyMcpServer(directory, client=ObsReadOnlyClient(config_path=Path(directory) / "missing.json"))
            def request(method, params=None):
                return server.handle_message({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
            self.assertEqual(request("initialize", {"protocolVersion": "not-supported"})["result"]["protocolVersion"], "2025-11-25")
            tools = request("tools/list")["result"]["tools"]
            self.assertEqual(len(tools), 3)
            self.assertTrue(all(row["annotations"]["readOnlyHint"] for row in tools))
            self.assertEqual(len(request("resources/list")["result"]["resources"]), 3)
            self.assertEqual(len(request("prompts/list")["result"]["prompts"]), 1)
            for args in ({"name": "StartRecord"}, {"name": "obs_get_status", "arguments": {"host": "example.com"}},
                         {"name": "obs_observe", "arguments": {"request_id": "one"}}):
                self.assertEqual(request("tools/call", args)["error"]["code"], -32602)
            self.assertEqual(request("resources/read", {"uri": "file:///secret"})["error"]["code"], -32602)
            self.assertIsNone(server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            self.assertEqual(request("resources/read", {"uri": "obs://installation"})["result"]["contents"][0]["mimeType"], "application/json")

    def test_real_stdio_to_authenticated_socket(self):
        with fake_obs() as (port, messages, errors):
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "obs_observe", "arguments": {"client_id": "stdio-test", "request_id": "obs-proof"}}},
            ]
            completed = subprocess.run(
                [sys.executable, str(ROOT / "obs_readonly_mcp_server.py"), "--port", str(port)],
                input="\n".join(json.dumps(row) for row in requests) + "\n", text=True, capture_output=True,
                timeout=10, env={**os.environ, PASSWORD_ENV: SECRET},
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([row["id"] for row in responses], [1, 2])
        self.assertEqual(responses[1]["result"]["structuredContent"]["result"], "observed")
        self.assertNotIn(SECRET, completed.stdout)

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher regression")
    def test_windows_launcher_is_read_only_and_forwards_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_config(directory, server_enabled=False)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "call", str(ROOT / "obs-readonly-mcp.cmd"), "--obs-config", str(path), "--self-check"],
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["server_name"], "obs-readonly")
        self.assertFalse(payload["opens_connection"])
        self.assertFalse(payload["installation"]["connection"]["server_enabled"])
        self.assertNotIn(SECRET, completed.stdout)


if __name__ == "__main__":
    unittest.main()
