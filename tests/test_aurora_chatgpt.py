import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from aurora_chatgpt_auth import (ChatGPTAuth, ChatGPTAuthError, CredentialStore, ISSUER,
                                merge_tokens, validate_callback, verify_identity)
from aurora_chatgpt_transport import consume_events, subscription_payload, perform_subscription_request, CompletedSubscriptionResponse
from aurora_agent_controls import model_command
from aurora_command_contracts import parse_inference_plan_arguments
from aurora_settings_registry import coerce_setting_value


class ChatGPTTests(unittest.TestCase):
    def test_missing_subscription_usage_is_unknown(self):
        for usage in (None, {}, "invalid"):
            response = CompletedSubscriptionResponse({"usage": usage}, "ready", omitted=[], account="fixture")
            self.assertEqual(response.json()["usage"], dict(prompt_tokens=None, completion_tokens=None, total_tokens=None))
        response = CompletedSubscriptionResponse({"usage": {"input_tokens": 0, "output_tokens": 3}}, "ready", omitted=[], account="fixture")
        self.assertEqual(response.json()["usage"], dict(prompt_tokens=0, completion_tokens=3, total_tokens=None))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-auth-test-")
        self.addCleanup(self.temp.cleanup)
        self.store = CredentialStore(Path(self.temp.name) / "auth.bin")
        self.auth = ChatGPTAuth(self.store)

    def save_account(self, **overrides):
        row = {"subject": "synthetic-sub", "client_id": "synthetic-client", "email": "test.invalid",
               "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
               "scopes": ["chatgpt.tokens.use.direct"], "expires_at": time.time() + 1000, **overrides}
        with self.store.locked():
            data = self.store.read()
            data.update(active="synthetic", accounts={"synthetic": row})
            self.store.write(data)
        return row

    def test_callback_rejects_missing_state_origin_duplicates_and_client_swap(self):
        redirect = "http://127.0.0.1:4567/auth/callback"
        good = redirect + "?code=x&state=expected&client_id=issued"
        self.assertEqual(validate_callback(good, redirect, "expected", "dynamic_agent_client"), ("x", "issued"))
        for url, client in [(good.replace("state=expected&", ""), "issued"),
                            (good.replace("127.0.0.1", "localhost"), "issued"),
                            (good + "&state=expected", "issued"), (good, "other"),
                            (good.replace("issued", "dynamic_agent_client"), "dynamic_agent_client"),
                            (redirect + "?error=access_denied", "issued")]:
            with self.subTest(url=url), self.assertRaises(ChatGPTAuthError):
                validate_callback(url, redirect, "expected", client)

    def test_windows_store_atomic_protection_and_redacted_status(self):
        self.save_account()
        self.assertNotIn(b"synthetic-access", self.store.path.read_bytes())
        self.assertNotIn("synthetic-access", json.dumps(self.auth.status()))
        self.assertEqual(self.auth.access(), ("synthetic-access", "synthetic"))
        self.assertEqual(list(self.store.path.parent.glob(".chatgpt-*")), [])

    def test_login_cancel_closes_listener_and_preserves_active_account(self):
        self.save_account()
        cancel = threading.Event()
        opened = []
        def browser(url):
            opened.append(url); cancel.set()
        with self.assertRaises(ChatGPTAuthError):
            self.auth.login(cancel=cancel, open_browser=browser, timeout=.5)
        query = parse_qs(urlsplit(opened[0]).query)
        import socket
        callback = urlsplit(query["redirect_uri"][0])
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex((callback.hostname, callback.port)), 0)
        self.assertEqual(self.auth.status()["active"], "synthetic")

    def test_refresh_rotation_serialized_across_threads(self):
        self.save_account(expires_at=0)
        response = Mock(status_code=200)
        response.json.return_value = {"access_token": "new-synthetic", "refresh_token": "rotated", "expires_in": 3600, "token_type": "Bearer"}
        with patch("aurora_chatgpt_auth.requests.post", return_value=response) as post:
            results = []
            threads = [threading.Thread(target=lambda: results.append(self.auth.access())) for _ in range(4)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(3)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(results, [("new-synthetic", "synthetic")] * 4)
        with self.store.locked():
            self.assertEqual(self.store.read()["accounts"]["synthetic"]["refresh_token"], "rotated")

    def test_terminal_refresh_clears_tokens_temporary_preserves(self):
        for code, cleared in [("invalid_grant", True), ("temporarily_unavailable", False)]:
            self.save_account(expires_at=0)
            response = Mock(status_code=400)
            response.json.return_value = {"error": code, "error_description": "PRIVATE DETAIL"}
            with patch("aurora_chatgpt_auth.requests.post", return_value=response), self.assertRaises(ChatGPTAuthError) as error:
                self.auth.access()
            self.assertNotIn("PRIVATE", str(error.exception))
            self.assertEqual(self.auth.status()["accounts"][0]["connected"], not cleared)

    def test_missing_plan_grant_does_not_attempt_requests(self):
        self.save_account(scopes=["openid"])
        with patch("aurora_chatgpt_auth.requests.post") as post, self.assertRaises(ChatGPTAuthError):
            self.auth.access()
        post.assert_not_called()

    def test_id_token_signature_nonce_audience_expiry_and_subject(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"sub": "account", "iss": ISSUER, "aud": "issued", "exp": time.time()+600, "nonce": "n"}
        with patch("aurora_chatgpt_auth.identity_metadata", return_value={"jwks_uri": ISSUER+"/.well-known/jwks.json"}), patch("jwt.PyJWKClient") as client:
            client.return_value.get_signing_key_from_jwt.return_value.key = key.public_key()
            token = jwt.encode(claims, key, algorithm="RS256")
            self.assertEqual(verify_identity(token, "issued", "n", "account")["sub"], "account")
            for changes, audience, nonce, subject in [({}, "other", "n", "account"), ({}, "issued", "wrong", "account"),
                    ({}, "issued", "n", "other"), ({"exp": 1}, "issued", "n", "account"), ({"iss": "https://wrong.invalid"}, "issued", "n", "account")]:
                with self.assertRaises(ChatGPTAuthError):
                    verify_identity(jwt.encode({**claims, **changes}, key, algorithm="RS256"), audience, nonce, subject)

    def test_invalid_token_response_does_not_silently_accept(self):
        for tokens in [{}, {"access_token": "x", "expires_in": "nan", "token_type": "Bearer", "scope": "openid"}]:
            with self.assertRaises(ChatGPTAuthError): merge_tokens({}, tokens)

    def test_payload_preserves_roles_and_images_and_reports_inapplicable_fields(self):
        payload, omitted = subscription_payload({"model": "synthetic", "reasoning_effort": "low", "temperature": .2,
            "messages": [{"role": "system", "content": "rules"}, {"role": "assistant", "content": "prior"},
                         {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,synthetic"}}, {"type": "text", "text": "look"}]}]})
        self.assertEqual([row["role"] for row in payload["input"]], ["developer", "assistant", "user"])
        self.assertEqual(payload["input"][-1]["content"][0]["type"], "input_image")
        self.assertEqual(omitted, ["temperature"])
        self.assertFalse(payload["store"])
        self.assertTrue(payload["stream"])
        with self.assertRaises(ChatGPTAuthError): subscription_payload({"model": "synthetic", "tools": []})

    def test_stream_only_commits_completed_and_never_partial_commands(self):
        token = Mock()
        delta = {"type": "response.output_text.delta", "delta": "GB: move right"}
        def lines(*events):
            for event in events:
                yield "data: " + json.dumps(event)
                yield ""
        for ending in [{"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}}, {"type": "response.incomplete"}, {"type": "error", "code": "bad"}, None]:
            with self.assertRaises(ChatGPTAuthError):
                consume_events(lines(delta, *([ending] if ending else [])), token)
        complete = {"type": "response.completed", "response": {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "final only"}]}]}}
        self.assertEqual(consume_events(lines(delta, complete), token)[1], "final only")
        done = {"type": "response.output_item.done", "output_index": 0, "item": complete["response"]["output"][0]}
        terminal = {"type": "response.completed", "response": {"status": "completed", "output": []}}
        self.assertEqual(consume_events(lines(delta, done, terminal), token)[1], "final only")
        with self.assertRaises(ChatGPTAuthError):
            consume_events(lines(done, {"type": "response.failed"}), token)
        token.check.side_effect = RuntimeError("canceled")
        with self.assertRaisesRegex(RuntimeError, "canceled"):
            consume_events(lines(complete), token)

    def test_unknown_model_no_inference_or_api_fallback(self):
        with patch("aurora_chatgpt_transport.account_models", return_value=("one", [{"slug": "allowed"}])), patch("aurora_chatgpt_transport.requests.post") as post:
            with self.assertRaises(ChatGPTAuthError):
                perform_subscription_request({"model": "unknown", "messages": [{"role": "user", "content": "hi"}]}, Mock(), Mock())
            post.assert_not_called()

    def test_agent_controls_existing_contracts_and_heartbeat_off(self):
        command = model_command("gpt-6.1-sol", "medium")
        parsed = parse_inference_plan_arguments("SET_NEXT_INFERENCE", [command[len("SET_NEXT_INFERENCE("):-1]])
        self.assertEqual(parsed["reasoning_effort"], "medium")
        self.assertEqual(coerce_setting_value("scheduler.heartbeat_seconds", 0), 0)
        self.assertEqual(coerce_setting_value("auth.mode", "openai_chatgpt"), "openai_chatgpt")

    def test_unadvertised_speed_rejected_before_inference(self):
        model = {"slug": "allowed", "service_tiers": [{"id": "priority"}]}
        with patch("aurora_chatgpt_transport.account_models", return_value=("one", [model])), patch("aurora_chatgpt_transport.requests.post") as post:
            with self.assertRaises(ChatGPTAuthError):
                perform_subscription_request({"model": "allowed", "service_tier": "ultrafast", "messages": [{"role": "user", "content": "hi"}]}, Mock(), Mock())
            post.assert_not_called()

    def test_command_driven_scheduler_has_no_idle_turns_and_wakes_on_new_capture(self):
        import ast
        import test_aurora_command_ingress as ingress
        from aurora_task_continuation import TaskContinuation
        from aurora_capture_provenance import CaptureService
        import copy
        state = {"last_screenshot_path": "synthetic.png", "turn_scheduler_capture_counter": 1,
                 "turn_scheduler_last_submitted_capture_counter": 1, "last_turn_completed_at_epoch": time.time()-30}
        scope = {"time": time, "copy": copy, "CAPTURE_SERVICE": CaptureService(), "CAPTURE_PROVENANCE_POLICY": "legacy", "runtime_state": state, "SEND_TO_MODEL": True, "ENABLE_MODEL_RESPONSES": True,
                 "active_command_queue": None, "active_runtime_context": None,
                 "COMMAND_WORK": ingress.CancellationDomain(),
                 "TASK_CONTINUATION_MODE": "legacy", "READBACK_WAKE_ENABLED": False, "TASK_CONTINUATION": TaskContinuation(),
                 "normalize_text_content": lambda value: str(value or ""), "set_runtime_value": state.__setitem__,
                 "TURN_SCHEDULER_MODE": "per_capture", "TURN_SCHEDULER_HEARTBEAT_SECONDS": 0,
                 "TURN_SCHEDULER_MIN_GAP_SECONDS": .1}
        exec(compile(ast.Module(body=[ingress.FUNCTIONS["evaluate_turn_scheduler"]], type_ignores=[]), "runtime_scheduler", "exec"), scope)
        evaluate = scope["evaluate_turn_scheduler"]
        self.assertFalse(evaluate()["should_run"])
        self.assertEqual(evaluate(True)["reasons"], ["user_input"])
        state["turn_scheduler_capture_counter"] = 2
        self.assertEqual(evaluate()["reasons"], ["capture_tick"])
        state["turn_scheduler_last_submitted_capture_counter"] = 2
        scope["TURN_SCHEDULER_HEARTBEAT_SECONDS"] = 8
        self.assertEqual(evaluate()["reasons"], ["heartbeat"])


if __name__ == "__main__":
    unittest.main()
