"""Summarize an owned Horizons trial without exporting text, paths or pixels.

Usage: python tests/analyze_horizons_trial.py WORKSPACE [--output SUMMARY.json]
The report deliberately does not infer gameplay milestones from command success.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
import math


HORIZON_FIELDS = ("pinned_immediate_actions", "pinned_short_term_actions", "mid_term_context", "long_term_context", "notes", "journal_entries")


def memory_revision_summary(batches, started):
    """Keep receipt timing/count evidence, never command arguments or previews.

    Receipt wall times are local, second-resolution observations. They are not
    causal timings or a substitute for the controller's monotonic progress log.
    """
    revisions = []
    for batch in batches:
        try:
            elapsed = datetime.strptime(batch["timestamp"], "%Y-%m-%d %H:%M:%S").timestamp() - started
            elapsed = round(elapsed, 3) if elapsed >= 0 else None
        except (KeyError, TypeError, ValueError, OverflowError):
            elapsed = None
        for item in batch.get("memory_command_results", []):
            if item.get("success") is not True:
                continue
            before, after = item.get("before") or {}, item.get("after") or {}
            if after.get("field") not in HORIZON_FIELDS:
                continue
            revisions.append({
                "command": item["command"], "field": after["field"],
                "inference_turn": batch.get("executed_inference_turn"),
                "elapsed_seconds_approx": elapsed, "changed": item.get("changed"),
                "before_count": before.get("count"), "after_count": after.get("count"),
            })
    return revisions


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def distribution(values):
    if not values:
        return {"count": 0, "median": None, "p95": None, "maximum": None}
    ordered = sorted(values)
    return dict(count=len(values), median=statistics.median(values),
                p95=ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], maximum=max(values))


def dynamic_flow_summary(events, chat_records, frame_records):
    """Measure local continuation gaps and exact-frame age, never infer progress.

    Same-host wall timestamps are diagnostic only. Negative/missing times and
    duplicate identities stay unknown; no nearest-time or filename substitution.
    """
    def unique(rows, key):
        found = {}
        for row in rows:
            identity = row.get(key)
            if isinstance(identity, str) and identity:
                found[identity] = None if identity in found else row
        return found

    def seconds(first, last):
        valid = lambda n: type(n) in (int, float) and math.isfinite(n)
        return round(last-first, 4) if valid(first) and valid(last) and last >= first else None

    starts = [row for row in events if row.get('event') == 'request_started']
    finishes = unique([row for row in events if row.get('event') == 'request_finished'], 'request_id')
    requests = unique([row for row in chat_records if row.get('event') == 'model_request'], 'inference_request_id')
    frames = unique([row.get('capture', {}).get('provenance', {}) for row in frame_records], 'frame_id')
    ages, gaps, reasons = [], [], Counter()
    unknown_age = unknown_gap = missing_request = 0
    frame_use = Counter()
    for index, start in enumerate(starts):
        request = requests.get(start.get('request_id'))
        if request is None:
            missing_request += 1
        else:
            reasons[str(request.get('wake_reason') or 'unknown')] += 1
        frame_id = start.get('frame_id')
        if frame_id:
            frame_use[frame_id] += 1
            frame = frames.get(frame_id) or {}
            age = seconds(frame.get('acquired_end_epoch'), start.get('at')) if frame.get('status') == 'acquired' else None
            if age is None: unknown_age += 1
            else: ages.append(age)
        if index:
            prior = finishes.get(starts[index-1].get('request_id')) or {}
            gap = seconds(prior.get('at'), start.get('at'))
            if gap is None: unknown_gap += 1
            else: gaps.append(gap)
    prepared_reasons = Counter(str(row.get('wake_reason') or 'unknown') for row in chat_records if row.get('event') == 'model_request')
    return dict(scope='same-host observed wall times; gaps include command execution, settle, capture and preparation; not verified gameplay',
        request_count=len(starts), wake_reasons=dict(reasons), missing_or_ambiguous_request_metadata=missing_request,
        prepared_wake_reasons=dict(prepared_reasons), prepared_wake_scope='prepared request logs, independently counted; not a substitute for missing transport correlation',
        request_complete_to_next_start_seconds=distribution(gaps), unknown_continuation_gaps=unknown_gap,
        selected_frame_end_to_request_start_seconds=distribution(ages), unknown_selected_frame_ages=unknown_age,
        requests_without_recorded_frame_id=sum(not row.get('frame_id') for row in starts),
        selected_distinct_frames=len(frame_use), repeated_selected_frame_uses=sum(n-1 for n in frame_use.values()),
        retained_frame_records=len(frame_records), ambiguous_frame_identities=sum(row is None for row in frames.values()),
        interpretation='Missing frame IDs do not imply image-free requests. More captured than selected frames may include setup, intermediate observations or freshness replacement; repetition is not automatically stale or erroneous.')


def analyze(work):
    runtime = work / "runtime"
    owner = read_json(work / "owner.json")
    seed = read_json(work / "seed.json")
    start = read_json(work / "start.json")
    result = read_json(work / "result.json")
    state = read_json(runtime / "aurora_control_panel_state.json")
    events = rows(runtime / "acceptance-events.jsonl")
    logs = rows(runtime / "aurora_command_execution_log.jsonl")
    flow = dynamic_flow_summary(events, rows(runtime / 'aurora_chat_history_log.jsonl'),
        [read_json(path) for path in (runtime / 'aurora_image_context_index').glob('*.json')])
    starts = [row for row in events if row.get("event") == "request_started"]
    finished = [row for row in events if row.get("event") == "request_finished"]
    batches = [row for row in logs if row.get("event") == "command_result" and row.get("source") == "assistant_response"]
    memory = [item for row in batches for item in row.get("memory_command_results", [])]
    game_counts = [sum(cmd.startswith("GB:") for cmd in row.get("executed_commands", [])) for row in batches]
    balance = Counter()
    for row in events:
        if row.get("event") == "game_key":
            balance[row["key"]] += -1 if row.get("up") else 1
    terminal = [row for row in logs if row.get("event") == "model_turn" and row.get("status") not in ("success", "started")]
    failure_categories = Counter()
    for row in terminal:
        if "cancel" in str(row.get("status", "")).lower():
            continue
        note = row.get("note", "")
        categories = ("connect_timeout", "read_timeout", "tls_error", "stream_interrupted", "network_error")
        category = next((kind for kind in categories if "(" + kind + ")" in note), None)
        failure_categories[category or ("uncategorized_network_error" if "Subscription connection interrupted" in note else "other_terminal")] += 1
    worker_final = [row for row in events if row.get("event") == "worker_finished"]
    held = worker_final[-1].get("held_inputs", {}) if worker_final else {}
    hashes = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
              for name in ("aurora2.py", "aurora2_init.txt", "aurora_chatgpt_transport.py", "aurora_gameplay_scene.py", "acceptance.py")}
    if (runtime / "aurora_subscription_worker.py").exists():
        hashes["aurora_subscription_worker.py"] = hashlib.sha256((runtime / "aurora_subscription_worker.py").read_bytes()).hexdigest()
    for name in ("aurora_task_continuation.py", "aurora_task_objective.py", "aurora_settings_registry.py", "aurora_capture_provenance.py"):
        if (runtime / name).exists():
            hashes[name] = hashlib.sha256((runtime / name).read_bytes()).hexdigest()
    usages = [row.get("usage") or {} for row in finished]
    effort_sequence = []
    for row in starts:
        effort = row.get("effort")
        if effort_sequence and effort_sequence[-1]["effort"] == effort:
            effort_sequence[-1]["requests"] += 1
        else:
            effort_sequence.append({"effort": effort, "requests": 1})
    return {
        "schema": "aurora_horizons_trial_summary_v1",
        "condition": owner["condition"],
        "seed_sha256": hashlib.sha256(json.dumps(seed["commands"], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "checkpoint_memory_sha256": seed.get("memory_sha256"),
        "checkpoint_game_sha256": sorted(digest for path, digest in owner.get("originals", {}).items() if path.lower().endswith(".sgm")),
        "task_prompt_sha256": hashlib.sha256(start["prompt"].encode("utf-8")).hexdigest(),
        "requested_seconds": result["deadline"] - result["started"],
        "elapsed_seconds": result["elapsed_seconds"],
        "end_reason": result["reason"],
        "completed_duration": result["reason"] == "duration_reached",
        "primary_model": owner["primary_model"], "review_model": owner["review_model"],
        "configured_effort": owner["reasoning_effort"],
        "requested_efforts": dict(Counter(str(row.get("effort")) for row in starts)),
        "effort_sequence": effort_sequence,
        "returned_models": dict(Counter(str(row.get("returned_model")) for row in finished)),
        "authentication_modes": dict(Counter(str(row.get("auth_mode")) for row in finished)),
        "policy": {"hierarchy_dispatch": owner["hierarchy_dispatch"], "horizon_sync": owner["horizon_sync"],
                   "subscription_policy": owner.get("subscription_policy", "legacy"),
                   "task_objective_mode": owner.get("objective_mode", "not_instrumented"),
                   "capture_command_policy": owner.get("capture_command_policy", "not_instrumented")},
        "subscription_stream": {
            "response_policies": dict(Counter(str(row.get("subscription_policy", "unrecorded")) for row in finished)),
            "closed_completion_workers": sum(row.get("transport_diagnostics", {}).get("active") is False
                and row.get("transport_diagnostics", {}).get("pipe_threads_closed") is True for row in finished),
            "max_line_gap_seconds": distribution([row["transport_diagnostics"]["max_line_gap_seconds"] for row in finished
                if "max_line_gap_seconds" in row.get("transport_diagnostics", {})]),
            "first_line_seconds": distribution([row["transport_diagnostics"]["first_line_seconds"] for row in finished
                if "first_line_seconds" in row.get("transport_diagnostics", {})]),
        },
        "source_sha256": hashes,
        "production_workers": True, "codex_computer_use": False,
        "dynamic_flow": flow,
        "requests_started": len(starts), "responses_received": len(finished),
        "seconds_from_last_response_to_run_end": round(max(0, result["started"] + result["elapsed_seconds"] - finished[-1]["at"]), 3) if finished else None,
        "request_latency_seconds": distribution([row["latency_seconds"] for row in finished]),
        "memory_text_characters": distribution([row["memory_text_chars"] for row in starts if "memory_text_chars" in row]),
        "memory_source_counts": dict(Counter(str(row.get("memory_sources")) for row in starts)),
        "init_copy_counts": dict(Counter(str(row.get("init_count")) for row in starts)),
        "images_per_request": dict(Counter(str(row.get("images")) for row in starts)),
        "acceptance_objective_marker": dict(Counter(
            "present" if row.get("acceptance_objective_present") is True else
            "absent" if row.get("acceptance_objective_present") is False else "not_instrumented"
            for row in starts)),
        "retained_operator_context_counts": dict(Counter(str(row.get('retained_operator_context_count', 'not_instrumented')) for row in starts)),
        "reported_usage": {key: sum(row[key] for row in usages if isinstance(row.get(key), (int, float)))
                           for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "usage_missing_responses": sum(any(row.get(key) is None for key in ("prompt_tokens", "completion_tokens", "total_tokens")) for row in usages),
        "usage_scope": "Repeated provider-reported totals, not unique tokens, cache hits, or billing; memory text is characters, not tokens.",
        "assistant_batches": len(batches), "game_commands": sum(game_counts),
        "game_commands_per_batch": dict(Counter(str(n) for n in game_counts)),
        "failed_assistant_batches": sum(bool(row.get("failed_commands")) for row in batches),
        "executed_command_counts": dict(Counter(command.split("(", 1)[0] for row in batches for command in row.get("executed_commands", []))),
        "reviewed_memory_command_counts": dict(Counter(item["command"] for item in memory)),
        "memory_revisions": memory_revision_summary(batches, result["started"]),
        "memory_revision_timing_scope": "Local second-resolution receipt times relative to run start; missing/negative timing stays null.",
        "failed_memory_commands": sum(item.get("success") is not True for item in memory),
        "final_memory_counts": {key: len(state.get(key, [])) for key in HORIZON_FIELDS},
        "final_pending_count": len(state.get("pending_commands", [])),
        "final_scene": state.get("planning", {}).get("gameplay_scene"),
        "final_scene_conflicts": state.get("planning", {}).get("gameplay_scene_evidence", {}).get("conflicts", []),
        "failure_categories": dict(failure_categories),
        "terminal_request_statuses": dict(Counter(str(row.get("status")) for row in terminal)),
        "terminal_request_latency_ms": [row.get("model_latency_ms") for row in terminal],
        "cleanup": {"runtime_exit": result.get("runtime_exit"), "emulator_exit": result.get("emulator_exit"),
                    "runtime_forced_stop": result.get("runtime_forced_stop", False),
                    "emulator_forced_stop": result.get("emulator_forced_stop", False),
                    "originals_unchanged": result.get("originals_unchanged"),
                    "worker_finished": bool(worker_final), "held_count": held.get("held_count"),
                    "uncertain_count": held.get("uncertain_count"), "key_submission_balance": dict(balance)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(analyze(args.workspace), indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
