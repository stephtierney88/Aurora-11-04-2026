"""Astra Responses conversation ownership and cache-preserving effort updates.

Network I/O stays in Aurora's existing bounded worker. Only the caller commits
completed responses. Provider history is linked explicitly, never truncated or
replayed automatically; this object retains metadata, not images or prompts.
"""
from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass


ASTRA_MODEL = "gpt-6-astra"
ASTRA_EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODEL_TRANSPORTS = ("chat_completions", "responses")


class ResponsesReasoningError(RuntimeError):
    """A request cannot continue without an explicit operator decision."""


def build_reasoning_configuration_update(effort: str) -> dict:
    """Build the documented item; invalid efforts never silently fall back."""
    if effort not in ASTRA_EFFORTS:
        raise ValueError("Astra reasoning effort must be " + "|".join(ASTRA_EFFORTS))
    return {"type": "configuration_update", "reasoning": {"effort": effort}}


def responses_input_messages(messages: list) -> list:
    """Translate Aurora's text/image messages without changing their authority."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("Responses requires a nonempty message list.")
    translated = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "developer", "user", "assistant"}:
            raise ValueError("Unsupported Responses message role.")
        content = message.get("content")
        if isinstance(content, str):
            converted = content
        elif isinstance(content, list):
            converted = []
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError("Invalid message content part.")
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    converted.append({"type": "input_text", "text": part["text"]})
                elif part.get("type") == "image_url" and isinstance(part.get("image_url"), dict):
                    image = part["image_url"]
                    url, detail = image.get("url"), image.get("detail", "auto")
                    if not isinstance(url, str) or not url or detail not in {"auto", "low", "high", "original"}:
                        raise ValueError("Invalid Responses image URL/detail.")
                    converted.append({"type": "input_image", "image_url": url, "detail": detail})
                else:
                    raise ValueError("Unsupported Responses content part.")
        else:
            raise ValueError("Invalid Responses message content.")
        translated.append({"role": message["role"], "content": converted})
    if translated[-1]["role"] != "user":
        raise ValueError("An adaptive Responses turn must end with its current user message.")
    return translated


def completed_response_text(data: dict) -> str:
    """Accept only a completed final assistant answer, never partial commands."""
    if not isinstance(data, dict) or data.get("status") != "completed" or data.get("error"):
        raise ResponsesReasoningError("Responses did not return a completed response; no actions accepted.")
    output = data.get("output")
    if not isinstance(output, list):
        raise ResponsesReasoningError("Responses output is missing or malformed.")
    answers = []
    for item in output:
        if not isinstance(item, dict):
            raise ResponsesReasoningError("Malformed Responses output item.")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise ResponsesReasoningError("Unexpected tool/output item in the text-only Responses lane.")
        if item.get("status") not in {None, "completed"}:
            raise ResponsesReasoningError("Incomplete assistant message; no actions accepted.")
        phase = item.get("phase")
        if phase not in {None, "commentary", "final_answer"}:
            raise ResponsesReasoningError("Unrecognized assistant phase.")
        parts = item.get("content")
        if not isinstance(parts, list):
            raise ResponsesReasoningError("Malformed assistant content.")
        texts = []
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise ResponsesReasoningError("Assistant output is refused or unsupported; no actions accepted.")
            texts.append(part["text"])
        if phase != "commentary":
            answers.append((phase, "".join(texts)))
    final_answers = [text for phase, text in answers if phase == "final_answer"]
    answer = "\n".join(final_answers or [text for _, text in answers]).strip()
    if not answer:
        raise ResponsesReasoningError("No final assistant answer; no actions accepted.")
    return answer


@dataclass(frozen=True)
class PreparedResponsesRequest:
    request_id: str
    generation: int
    payload: dict
    effective_effort: str
    configuration_update_sent: bool


class ResponsesReasoningSession:
    """One caller owns a bounded, explicitly resettable provider conversation."""

    def __init__(self, *, max_output_tokens=16384, max_input_tokens=800000, max_request_bytes=32 * 1024 * 1024):
        self._lock = threading.RLock()
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = max_input_tokens
        self.max_request_bytes = max_request_bytes
        self._generation = 0
        self._pending = None
        self._reset("startup")

    def _reset(self, reason):
        self._generation += 1
        self._previous_response_id = ""
        self._base_effort = ""
        self._effective_effort = ""
        self._reported_effort = ""
        self._completed_responses = 0
        self._last_input_tokens = 0
        self._last_cached_tokens = None
        self._last_request = {}
        self._blocked_reason = ""
        self._reset_reason = reason

    def reset(self, reason="explicit_reset"):
        with self._lock:
            if self._pending:
                raise ResponsesReasoningError("A Responses request is active; cancel it before resetting the session.")
            self._reset(reason)
            return self.snapshot()

    def invalidate(self, reason):
        """Detach stale context after explicit history edits or an intervening lane."""
        with self._lock:
            if self._previous_response_id or self._pending:
                if self._pending:
                    self._last_request["status"] = "failed_uncertain"
                    self._last_request["reason"] = str(reason)[:240]
                self._generation += 1
                self._pending = None
                self._blocked_reason = str(reason)[:240]

    def prepare(self, chat_payload, *, base_effort, current_messages=None):
        with self._lock:
            if self._pending:
                raise ResponsesReasoningError("Only one Responses request may own this session.")
            if self._blocked_reason:
                raise ResponsesReasoningError("Responses session is blocked; inspect Model Status and RESET_RESPONSES_SESSION().")
            if self._last_input_tokens >= self.max_input_tokens:
                raise ResponsesReasoningError("Responses context budget reached; explicitly reset the session. Automatic truncation is disabled.")
            if chat_payload.get("model") != ASTRA_MODEL:
                raise ValueError("The adaptive Responses transport requires exactly gpt-6-astra.")
            allowed = {"model", "messages", "reasoning_effort", "verbosity", "max_tokens", "max_completion_tokens"}
            if set(chat_payload) - allowed:
                raise ValueError("Unsupported parameters in the standard single-agent Responses lane.")
            desired = chat_payload.get("reasoning_effort") or base_effort
            build_reasoning_configuration_update(base_effort)
            update = build_reasoning_configuration_update(desired)
            original = self._base_effort or base_effort
            effective_before = self._effective_effort or original
            continuing = bool(self._previous_response_id)
            messages = current_messages if continuing and current_messages is not None else chat_payload.get("messages")
            items = responses_input_messages(messages)
            output_limit = self.max_output_tokens
            for key in ("max_tokens", "max_completion_tokens"):
                if key in chat_payload:
                    value = chat_payload[key]
                    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                        raise ValueError("Output token limits must be positive integers.")
                    output_limit = min(output_limit, value)
            changed = desired != effective_before
            if changed:
                # Existing history ends with assistant output. The fresh context
                # precedes the update; the current user message follows it.
                items.insert(len(items) - 1, update)
            payload = {"model": ASTRA_MODEL, "input": items, "store": True,
                       "reasoning": {"effort": original}, "truncation": "disabled",
                       "max_output_tokens": output_limit}
            if continuing:
                payload["previous_response_id"] = self._previous_response_id
            verbosity = chat_payload.get("verbosity")
            if verbosity:
                if verbosity not in {"low", "medium", "high"}:
                    raise ValueError("Invalid Responses verbosity.")
                payload["text"] = {"verbosity": verbosity}
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > self.max_request_bytes:
                raise ValueError("Responses request exceeds the byte budget; no request sent.")
            request = PreparedResponsesRequest(uuid.uuid4().hex, self._generation, payload, desired, changed)
            self._pending = request.request_id
            self._last_request = {"request_id": request.request_id, "status": "prepared",
                                  "request_level_effort": original, "selected_effort": desired,
                                  "configuration_update_sent": changed,
                                  "continued_from": self._previous_response_id}
            return request

    def complete(self, request, data):
        with self._lock:
            self._require_owner(request)
            answer = completed_response_text(data)
            response_id = data.get("id")
            if not isinstance(response_id, str) or not response_id.startswith("resp_") or len(response_id) > 256:
                raise ResponsesReasoningError("Missing or invalid Responses continuation identity.")
            if data.get("model") != ASTRA_MODEL:
                raise ResponsesReasoningError("Response model did not match the admitted Astra request.")
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                raise ResponsesReasoningError("Malformed Responses usage.")
            input_tokens = usage.get("input_tokens")
            if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
                raise ResponsesReasoningError("Invalid Responses input-token usage.")
            details = usage.get("input_tokens_details") or {}
            cached = details.get("cached_tokens") if isinstance(details, dict) else None
            reasoning = data.get("reasoning") or {}
            self._base_effort = self._last_request["request_level_effort"]
            self._effective_effort = request.effective_effort
            self._reported_effort = reasoning.get("effort", "") if isinstance(reasoning, dict) else ""
            self._previous_response_id = response_id
            self._completed_responses += 1
            self._last_input_tokens = input_tokens
            self._last_cached_tokens = cached if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0 else None
            self._last_request["status"] = "completed"
            self._last_request["response_id"] = response_id
            self._pending = None
            return answer

    def fail(self, request, reason):
        with self._lock:
            if request.generation != self._generation or request.request_id != self._pending:
                return  # A history edit/reset owns the newer generation.
            self._pending = None
            self._blocked_reason = str(reason)[:240]
            self._last_request["status"] = "failed_uncertain"
            self._last_request["reason"] = self._blocked_reason

    def _require_owner(self, request):
        if request.generation != self._generation or request.request_id != self._pending:
            raise ResponsesReasoningError("Stale Responses request cannot change this session.")

    def snapshot(self):
        with self._lock:
            blocked_reason = self._blocked_reason
            if not blocked_reason and self._last_input_tokens >= self.max_input_tokens:
                blocked_reason = "Responses context budget reached; explicitly reset before continuing."
            return {"schema_version": "aurora_responses_reasoning_v1", "model": ASTRA_MODEL,
                    "status": "blocked" if blocked_reason else "in_flight" if self._pending else "ready",
                    "completion_uncertain": self._last_request.get("status") == "failed_uncertain",
                    "generation": self._generation, "previous_response_id": self._previous_response_id,
                    "request_level_effort": self._base_effort, "effective_effort": self._effective_effort,
                    "api_reported_effort": self._reported_effort, "completed_responses": self._completed_responses,
                    "last_input_tokens": self._last_input_tokens, "last_cached_tokens": self._last_cached_tokens,
                    "last_request": copy.deepcopy(self._last_request), "blocked_reason": blocked_reason,
                    "reset_reason": self._reset_reason, "max_output_tokens": self.max_output_tokens,
                    "max_input_tokens": self.max_input_tokens, "max_request_bytes": self.max_request_bytes,
                    "provider_history": "previous_response_id; store=true; ids remain in this process only",
                    "automatic_truncation": False, "automatic_compaction": False,
                    "explicit_compaction_implemented": False, "automatic_replay": False,
                    "cache_hits_guaranteed": False}
