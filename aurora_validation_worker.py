"""Disposable real-runtime fixture. Invoked only in a copied offline workspace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace


def main():
    work = Path.cwd().resolve()
    if (not work.name.startswith("run-") or work.parent.name != "scratch"
            or not (work / "profile.json").is_file()
            or (work / "aurora_validation_worker.py").resolve() != Path(__file__).resolve()):
        raise RuntimeError("Run this worker through the validation service, not in the project workspace.")
    profile = json.loads((work / "profile.json").read_text(encoding="utf-8"))
    violations = []

    def deny(name):
        def blocked(*_args, **_kwargs):
            violations.append(name)
            raise RuntimeError("Offline fixture blocked " + name)
        return blocked

    def audit(event, _args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
                     "socket.sendto", "subprocess.Popen", "os.system"}:
            deny(event)()

    sys.addaudithook(audit)
    # urllib3 otherwise probes IPv6 by binding a local socket during import.
    socket.has_ipv6 = False
    # Runtime imports a tokenizer that may download vocabulary on a cold cache.
    # This fixture tests control flow, not tokenization; never fetch that data.
    tokenizer = SimpleNamespace(encode=lambda text, **_kwargs: list(str(text).encode("utf-8")),
                                decode=lambda values: bytes(values).decode("utf-8", errors="replace"))
    sys.modules["tiktoken"] = SimpleNamespace(get_encoding=lambda *_a, **_k: tokenizer,
                                            encoding_for_model=lambda *_a, **_k: tokenizer)
    import aurora2 as runtime

    for name in ("press", "keyDown", "keyUp", "hotkey", "write", "typewrite", "moveTo", "dragTo", "click",
                 "doubleClick", "mouseDown", "mouseUp", "scroll", "screenshot"):
        setattr(runtime.pyautogui, name, deny("pyautogui." + name))
    runtime.keyboard.press = deny("keyboard.press")
    runtime.keyboard.release = deny("keyboard.release")
    runtime.send_scancode_key_event = deny("scancode")
    runtime.requests.post = deny("requests.post")
    runtime.screenshot_capture = deny("capture worker")
    runtime.initialize_overlay = deny("overlay")
    runtime.focus_window_by_title = deny("window focus")
    runtime.focus_game_input_target = deny("game focus")
    runtime.get_foreground_window_title = lambda: "Aurora offline fixture"
    runtime.apply_cli_args(runtime.build_cli_parser().parse_args([
        "--offline", "--lock-live", "--no-ui", "--no-live-init", "--init-mode", "skip",
        "--no-chat-log-echo", "--no-smoke-test", "--no-sound", "--action-mode", "none"]))
    runtime.display_message = lambda *_a, **_k: None
    runtime.maybe_build_episodic_planning_context = lambda *_a, **_k: {"used": False, "reason": "offline fixture"}
    runtime.maybe_run_game_focus_recovery = lambda *_a, **_k: None
    # No main loop, capture threads, command worker, or arbitrary assistant commands.
    runtime.process_assistant_response = lambda *_a, **_k: None
    runtime.AUTO_DYNAMIC_INFERENCE_ENABLED = False
    runtime.REVIEW_TURN_INTERVAL = 1 if profile["case"] == "dynamic" else 0
    runtime.CRITIQUE_TURN_INTERVAL = 0
    runtime.DEFAULT_REASONING_EFFORT = runtime.BATTLE_REASONING_EFFORT = profile["baseline_effort"]
    runtime.REVIEW_REASONING_EFFORT = profile["changed_effort"]
    runtime.ACTIVE_TEXT_MODEL = runtime.ACTIVE_VISION_MODEL = runtime.ACTIVE_REASONING_MODEL = profile["model"]
    runtime.MODEL_TRANSPORT = profile["transport"]
    runtime.AUTH_MODE = "api_key"
    runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = True
    requests, turns, receipts = [], [], []
    effective = profile["baseline_effort"]

    def checkpoint():
        if (work / "cancel").exists():
            raise InterruptedError("Offline run cancelled.")

    def state():
        return {"text_model": runtime.ACTIVE_TEXT_MODEL, "vision_model": runtime.ACTIVE_VISION_MODEL,
                "reasoning_model": runtime.ACTIVE_REASONING_MODEL,
                "effort": runtime.DEFAULT_REASONING_EFFORT, "dynamic": runtime.AUTO_DYNAMIC_INFERENCE_ENABLED,
                "next_plan": runtime.get_next_inference_plan_snapshot(), "transport": runtime.MODEL_TRANSPORT}

    def command(text):
        result = runtime.handle_commands(text, is_user=True)
        receipts.append({"command": text, "result": result})
        if not result.get("success"):
            raise RuntimeError("Fixture command rejected: " + text)

    def fake_provider(packet, token):
        nonlocal effective
        checkpoint()
        token.check()
        if len(requests) >= profile["max_calls"]:
            raise RuntimeError("Fake-call limit exceeded.")
        payload = packet["payload"]
        updates = [item["reasoning"]["effort"] for item in payload.get("input", [])
                   if item.get("type") == "configuration_update"]
        effort = payload.get("reasoning_effort", payload.get("reasoning", {}).get("effort"))
        effective = updates[-1] if updates else (effective if profile["transport"] == "responses" else effort)
        usage = {"input_tokens": 1200, "output_tokens": 8, "input_tokens_details": {"cached_tokens": 0}}
        row = {"model": payload["model"], "sent_effort": effort, "configuration_updates": updates,
               "fake_provider_effective_effort": effective, "provider_reported_effort": effort,
               "request_hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
               "usage": usage, "usage_provenance": "synthetic", "provider_latency_ms": None}
        requests.append(row)
        text = "Offline fixture complete. No commands."
        if profile["transport"] == "responses":
            data = {"id": "resp_offline_" + str(len(requests)), "model": payload["model"], "status": "completed",
                    "reasoning": {"effort": effort}, "usage": usage,
                    "output": [{"type": "message", "role": "assistant", "status": "completed", "phase": "final_answer",
                                "content": [{"type": "output_text", "text": text}]}]}
        else:
            data = {"model": payload["model"], "choices": [{"message": {"content": text}}],
                    "usage": {"prompt_tokens": 1200, "completion_tokens": 8, "total_tokens": 1208}}
        return SimpleNamespace(status_code=200, json=lambda: data), "api_key", "guarded fake provider"

    runtime.perform_model_http_request = fake_provider
    initial = state()
    result = {"status": "failed", "turns": turns, "receipts": receipts, "before": initial,
              "real_api_calls": 0, "native_effects": 0, "telemetry": "synthetic", "error": None}
    result["tokenizer"] = "synthetic UTF-8 bytes; not a token count or tokenization test"
    try:
        for index, label in enumerate(("baseline", "intervention", "restoration")):
            checkpoint()
            if index == 1:
                if profile["case"] == "effort":
                    command("SET_NEXT_REASONING_EFFORT(" + profile["changed_effort"] + ", offline validation)")
                elif profile["case"] == "model":
                    command("SET_NEXT_INFERENCE(model=" + profile["alternate_model"] + ")")
                else:
                    command("SET_AUTO_DYNAMIC_INFERENCE(on)")
            if index == 2 and profile["case"] == "dynamic":
                command("SET_AUTO_DYNAMIC_INFERENCE(off)")
            before_count = len(requests)
            start = time.perf_counter()
            answer = runtime.send_prompt_to_chatgpt(profile["prompt"])
            if not answer or len(requests) != before_count + 1:
                raise RuntimeError("Expected one completed fake request: " + str(runtime.runtime_state.get("last_response_summary", "")))
            turns.append(dict(requests[-1], phase=label, elapsed_ms=round((time.perf_counter()-start)*1000, 2),
                              controller_effort=runtime.runtime_state.get("last_reasoning_effort"),
                              plan_source=runtime.runtime_state.get("last_turn_plan_source")))
        expected_models = [profile["model"], profile["alternate_model"] if profile["case"] == "model" else profile["model"], profile["model"]]
        expected_efforts = [profile["baseline_effort"], profile["baseline_effort"] if profile["case"] == "model" else profile["changed_effort"], profile["baseline_effort"]]
        if [turn["model"] for turn in turns] != expected_models:
            raise AssertionError("Model sequence did not match profile.")
        if [turn["controller_effort"] for turn in turns] != expected_efforts:
            raise AssertionError("Effective effort sequence did not match profile.")
        if [turn["fake_provider_effective_effort"] for turn in turns] != expected_efforts:
            raise AssertionError("Fake provider effort sequence did not match profile.")
        result["status"] = "passed"
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        try:
            command("CLEAR_NEXT_INFERENCE()")
            command("SET_AUTO_DYNAMIC_INFERENCE(off)")
            after = state()
            # Cleared plans retain audit metadata; test effective emptiness separately.
            comparable = lambda value: {key: val for key, val in value.items() if key != "next_plan"}
            restored = comparable(initial) == comparable(after) and not runtime.has_effective_next_inference_plan(after["next_plan"])
            result.update(after=after, restoration_verified=restored)
            if not restored:
                result.update(status="failed", error="Fixture settings restoration did not verify.")
        except Exception as error:
            result.update(status="failed", restoration_verified=False, error="Restoration failed: " + str(error))
        runtime.SEND_TO_MODEL = runtime.ENABLE_MODEL_RESPONSES = False
        result["guard_violations"] = violations
        result["model_worker_idle"] = not runtime.MODEL_IO.busy
        if violations or runtime.MODEL_IO.busy:
            result.update(status="failed", error="Offline guard violation or model worker still busy.")
        (work / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
