"""Explicit subscription-only Responses transport; no API-key fallback or replay."""
import json
import time
import requests
from urllib3 import exceptions as network_errors
from aurora_chatgpt_auth import ChatGPTAuth, ChatGPTAuthError, RESOURCE, provider_error, safe_code
from aurora_responses_reasoning import completed_response_text
import aurora_execution_evidence as evidence


def network_failure_category(error):
    """Describe bounded exception types, never URLs, headers or provider bodies."""
    pending, seen, kinds = [error], set(), set()
    while pending and len(seen) < 16:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, requests.exceptions.ConnectTimeout) or type(item) is network_errors.ConnectTimeoutError:
            kinds.add("connect_timeout")
        if isinstance(item, (requests.exceptions.ReadTimeout, network_errors.ReadTimeoutError)):
            kinds.add("read_timeout")
        if isinstance(item, (requests.exceptions.SSLError, network_errors.SSLError)):
            kinds.add("tls_error")
        if isinstance(item, (requests.exceptions.ChunkedEncodingError, network_errors.ProtocolError)):
            kinds.add("stream_interrupted")
        pending.extend([item.__cause__, item.__context__])
        pending.extend(arg for arg in item.args[:8] if isinstance(arg, BaseException))
    return next((kind for kind in ("connect_timeout", "read_timeout", "tls_error", "stream_interrupted") if kind in kinds), "network_error")


def subscription_payload(chat):
    """Translate Aurora's text-command protocol, preserving ordered full history."""
    allowed = {"model", "messages", "reasoning_effort", "verbosity", "temperature", "max_tokens", "max_completion_tokens", "service_tier"}
    extra = set(chat) - allowed
    if extra:
        raise ChatGPTAuthError("Unsupported subscription request fields: " + ", ".join(sorted(extra)))
    # Route-inapplicable legacy sampling/length fields are reported explicitly,
    # never forwarded to the subscription endpoint or confused with enforcement.
    omitted = [key for key in ("temperature", "max_tokens", "max_completion_tokens") if key in chat]
    items = []
    for message in chat.get("messages", []):
        role = message.get("role")
        if role not in {"system", "developer", "user", "assistant"}:
            raise ChatGPTAuthError("Unsupported subscription message role.")
        role = "developer" if role == "system" else role
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    parts.append({"type": "output_text" if role == "assistant" else "input_text", "text": part["text"]})
                elif part.get("type") == "image_url" and role == "user":
                    image = part.get("image_url", {})
                    if not isinstance(image.get("url"), str) or not image["url"]:
                        raise ChatGPTAuthError("Invalid subscription image input.")
                    parts.append({"type": "input_image", "image_url": image["url"], "detail": image.get("detail", "auto")})
                else:
                    raise ChatGPTAuthError("Unsupported subscription content part.")
            content = parts
        elif not isinstance(content, str):
            raise ChatGPTAuthError("Invalid subscription message content.")
        items.append({"role": role, "content": content})
    if not items or not chat.get("model"):
        raise ChatGPTAuthError("Subscription request requires a model and history.")
    payload = {"model": chat["model"], "input": items, "store": False, "stream": True}
    if chat.get("reasoning_effort"):
        payload["reasoning"] = {"effort": chat["reasoning_effort"]}
    if chat.get("verbosity"):
        payload["text"] = {"verbosity": chat["verbosity"]}
    if chat.get("service_tier") and chat["service_tier"] != "regular":
        payload["service_tier"] = chat["service_tier"]
    return payload, omitted


def account_models(auth=None):
    token, account = (auth or ChatGPTAuth()).access()
    try:
        with requests.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + token}, timeout=20) as response:
            if response.status_code != 200:
                raise provider_error(response)
            data = response.json()
        if not isinstance(data.get("models"), list):
            raise ChatGPTAuthError("Unexpected subscription model catalog; API-key catalogs are not interchangeable.")
        models = [row for row in data["models"] if row.get("visibility") == "list" and isinstance(row.get("slug"), str)]
        return account, models
    except requests.RequestException:
        raise ChatGPTAuthError("ChatGPT catalog network failure; no fallback attempted.") from None


def consume_events(lines, cancellation_token, *, deadline=None):
    """Discard deltas; only validated completed output can reach command admission."""
    data, event_bytes = [], 0
    done_items = {}
    response_id = None
    for line in lines:
        cancellation_token.check()
        if deadline is not None and time.monotonic() >= deadline:
            raise ChatGPTAuthError("Subscription response deadline exceeded; no commands accepted.")
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if line == "":
            if not data:
                continue
            try:
                event = json.loads("\n".join(data))
            except (ValueError, TypeError):
                raise ChatGPTAuthError("Malformed subscription stream event; no commands accepted.") from None
            data, event_bytes = [], 0
            kind = event.get("type")
            if kind == "response.created":
                response_id = (event.get("response") or {}).get("id")
            if kind == "response.output_item.done":
                index, item = event.get("output_index"), event.get("item")
                if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index > 1000 or not isinstance(item, dict):
                    raise ChatGPTAuthError("Malformed completed output item.")
                if index in done_items and done_items[index] != item:
                    raise ChatGPTAuthError("Conflicting completed output items.")
                done_items[index] = item
            if kind == "response.completed":
                result = event.get("response", {})
                if response_id and result.get("id") != response_id:
                    raise ChatGPTAuthError("Subscription response identity changed within the stream.")
                if not result.get("output") and done_items:
                    if sorted(done_items) != list(range(len(done_items))):
                        raise ChatGPTAuthError("Incomplete output item sequence.")
                    result = {**result, "output": [done_items[i] for i in sorted(done_items)]}
                answer = completed_response_text(result)
                cancellation_token.check()
                return result, answer
            if kind in {"error", "response.failed", "response.incomplete"}:
                error = event.get("error") or (event.get("response") or {}).get("error") or event
                code = error.get("code", kind) if isinstance(error, dict) else kind
                raise ChatGPTAuthError("Subscription response stopped: " + safe_code(code))
        elif line.startswith("data:"):
            value = line[5:].lstrip(" ")
            event_bytes += len(value)
            if event_bytes > 8 * 1024 * 1024:
                raise ChatGPTAuthError("Subscription event exceeds local limit; no commands accepted.")
            data.append(value)
    raise ChatGPTAuthError("Subscription stream ended without completion; no commands accepted.")


class CompletedSubscriptionResponse:
    status_code = 200
    def __init__(self, result, answer, *, omitted, account, tier="regular"):
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        self.data = {"id": result.get("id"), "model": result.get("model"),
                     "choices": [{"message": {"role": "assistant", "content": answer}}],
                     "usage": {"prompt_tokens": usage.get("input_tokens"), "completion_tokens": usage.get("output_tokens"), "total_tokens": usage.get("total_tokens")},
                     "aurora_subscription": {"account": account, "omitted_unsupported_fields": omitted,
                         "requested_service_tier": tier, "provider_service_tier": result.get("service_tier", "unknown")}}
    def json(self):
        return self.data


def request_subscription_stream(payload, bearer, cancellation_token, *, idle_seconds=30, total_seconds=180,
                                diagnostics=None, phase_callback=None, chunk_size=None):
    """One HTTP stream; legacy caller stays cooperative, bounded caller owns a process."""
    diagnostics = diagnostics if diagnostics is not None else {}
    started = last_line = time.monotonic()
    phase = phase_callback or (lambda _value: None)
    evidence.attempt(payload, "chatgpt_subscription_responses", "openai_chatgpt")
    phase("waiting_headers")
    try:
        with requests.post(RESOURCE + "/responses", headers={"Authorization": "Bearer " + bearer, "Content-Type": "application/json", "Accept": "text/event-stream"},
                           json=payload, stream=True, timeout=(15, idle_seconds)) as response:
            diagnostics["headers_seconds"] = round(time.monotonic()-started, 3)
            diagnostics["http_status"] = response.status_code
            diagnostics["provider_request_id"] = evidence.code(response.headers.get("x-request-id"))
            evidence.response(status=response.status_code, headers=response.headers)
            phase("headers_received")
            if response.status_code != 200:
                raise provider_error(response)
            content_type = response.headers.get("Content-Type", "")
            if content_type and "text/event-stream" not in content_type:
                raise ChatGPTAuthError("Subscription provider did not return an event stream.")
            lines = response.iter_lines() if chunk_size is None else response.iter_lines(chunk_size=chunk_size)
            def observed_lines():
                nonlocal last_line
                for line in lines:
                    now = time.monotonic()
                    diagnostics["max_line_gap_seconds"] = round(max(diagnostics.get("max_line_gap_seconds", 0), now-last_line), 3)
                    last_line = now
                    diagnostics["line_count"] = diagnostics.get("line_count", 0)+1
                    if diagnostics["line_count"] == 1:
                        diagnostics["first_line_seconds"] = round(now-started, 3)
                        phase("first_line")
                    yield line
            result, answer = consume_events(observed_lines(), cancellation_token, deadline=time.monotonic()+total_seconds)
            evidence.response(body=result)
            return result, answer
    except requests.RequestException as error:
        category = network_failure_category(error)
        raise ChatGPTAuthError("Subscription connection interrupted (" + category + "); no commands accepted and no request replayed.") from None
    finally:
        diagnostics["elapsed_seconds"] = round(time.monotonic()-started, 3)


def perform_subscription_request(chat, cancellation_token, auth=None, *, policy="legacy"):
    evidence.instrumented()
    if policy not in {"legacy", "bounded"}:
        raise ChatGPTAuthError("Unknown subscription request policy; no request sent.")
    auth = auth or ChatGPTAuth()
    payload, omitted = subscription_payload(chat)
    cancellation_token.check()
    account, models = account_models(auth)
    if payload["model"] not in {row["slug"] for row in models}:
        raise ChatGPTAuthError("Requested model is not listed for this ChatGPT account; choose an available model in Connection settings.")
    profile = next(row for row in models if row["slug"] == payload["model"])
    tiers = {row.get("id") for row in profile.get("service_tiers", [])}
    if payload.get("service_tier") and payload["service_tier"] not in tiers:
        raise ChatGPTAuthError("Requested speed tier is not advertised for this account/model; select Regular or another advertised tier.")
    levels = {row.get("effort") for row in profile.get("supported_reasoning_levels", [])}
    if payload.get("reasoning") and payload["reasoning"]["effort"] not in levels:
        raise ChatGPTAuthError("Requested reasoning effort is not advertised for this account/model.")
    if payload.get("text") and not profile.get("support_verbosity"):
        raise ChatGPTAuthError("Requested verbosity is unsupported for this account/model.")
    token, current = auth.access()
    if current != account:
        raise ChatGPTAuthError("ChatGPT account changed before inference; retry explicitly.")
    cancellation_token.check()
    if policy == "bounded":
        from aurora_subscription_worker import run_bounded_stream
        result, answer, diagnostics = run_bounded_stream(payload, token, cancellation_token)
    else:
        diagnostics = {}
        result, answer = request_subscription_stream(payload, token, cancellation_token, diagnostics=diagnostics)
    cancellation_token.check()
    response = CompletedSubscriptionResponse(result, answer, omitted=omitted, account=account, tier=payload.get("service_tier", "regular"))
    response.data["aurora_subscription"].update(request_policy=policy, transport_diagnostics=diagnostics)
    return response
