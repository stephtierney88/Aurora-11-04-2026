"""Defaults profile contracts and file persistence; no runtime or native imports.

The existing JSON shape remains the wire format. Unknown fields are retained in
saved documents and reported as unapplied; they never grant new capabilities.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aurora_settings_registry import coerce_setting_value, resolve_setting_definition


DEFAULT_PROFILE_RESULT_SCHEMA = "aurora_default_profile_result_v1"
DEFAULT_PROFILE_COMMANDS = {
    "SAVE_PERSONAL_DEFAULTS": "Atomically save current profile settings, retaining unknown fields in a valid existing file.",
    "APPLY_PERSONAL_DEFAULTS": "Validate and apply the saved personal profile; reapply retains setter effects, while changed_only skips unchanged values.",
    "APPLY_SYSTEM_DEFAULTS": "Validate and apply the process-start system profile; reapply retains setter effects, while changed_only skips unchanged values.",
    "SHOW_DEFAULT_PROFILES": "Inspect system/personal profiles and distinguish missing, invalid and unreadable saved files.",
}
MAX_PROFILE_BYTES = 8 * 1024 * 1024

# path: (existing runtime setter, coercion contract, additional runtime lock)
# Registered fields reuse the authoritative registry, including value aliases.
PROFILE_FIELDS = {
    "auth_mode": ("set_auth_mode", "auth.mode", ""),
    "execution_mode": ("set_execution_mode", "runtime.execution", ""),
    "action_mode": ("set_action_mode", "runtime.action", ""),
    "game_profile": ("set_game_profile", "game.profile", ""),
    "text_model": ("set_text_model", "model.text", ""),
    "vision_model": ("set_vision_model", "model.vision", ""),
    "reasoning_model": ("set_reasoning_model", "model.reasoning", ""),
    "reasoning_effort": ("set_default_reasoning_effort", "inference.reasoning_effort", ""),
    "battle_reasoning_effort": ("set_battle_reasoning_effort", "inference.reasoning_effort", ""),
    "review_reasoning_effort": ("set_review_reasoning_effort", "inference.reasoning_effort", ""),
    "critique_reasoning_effort": ("set_critique_reasoning_effort", "inference.reasoning_effort", ""),
    "verbosity": ("set_model_verbosity", "inference.verbosity", ""),
    "battle_verbosity": ("set_battle_model_verbosity", "inference.verbosity", ""),
    "review_verbosity": ("set_review_model_verbosity", "inference.verbosity", ""),
    "critique_verbosity": ("set_critique_model_verbosity", "inference.verbosity", ""),
    "summary_mode": ("set_reasoning_summary_mode", "summary", "reasoning"),
    "temperature": ("set_model_temperature", "inference.temperature", ""),
    "screenshot_interval": ("set_screenshot_interval", "capture.screenshot_interval", ""),
    "turn_scheduler_profile": ("", "scheduler.profile", ""),
    "turn_scheduler_mode": ("set_turn_scheduler_mode", "scheduler.mode", ""),
    "turn_heartbeat_seconds": ("set_turn_heartbeat_seconds", "scheduler.heartbeat_seconds", ""),
    "turn_min_gap_seconds": ("set_turn_min_gap_seconds", "scheduler.min_gap_seconds", ""),
    "turn_capture_wake_enabled": ("set_turn_capture_wake_enabled", "scheduler.capture_wake_enabled", ""),
    "turn_capture_wake_debounce_seconds": ("set_turn_capture_wake_debounce_seconds", "scheduler.capture_wake_debounce_seconds", ""),
    "turn_post_action_settle_seconds": ("set_turn_post_action_settle_seconds", "scheduler.post_action_settle_seconds", ""),
    "demand_capture_enabled": ("set_demand_capture_enabled", "capture.demand_enabled", ""),
    "unchanged_screenshot_persist_interval": ("set_unchanged_screenshot_persist_interval", "persist_interval", "screenshot_interval"),
    "auto_dynamic_inference": ("set_auto_dynamic_inference_enabled", "boolean", "reasoning"),
    "review_turn_interval": ("set_review_turn_interval", "nonnegative_int", "reasoning"),
    "critique_turn_interval": ("set_critique_turn_interval", "nonnegative_int", "reasoning"),
    "pending_queue_mode": ("set_pending_queue_mode", "pending_mode", "execution"),
    "command_drip_retention_turns": ("set_command_drip_retention_turns", "positive_int", "reasoning"),
    "command_drip_lookahead_turns": ("set_command_drip_lookahead_turns", "positive_int", "reasoning"),
    "command_drip_show_variants": ("set_command_drip_show_variants_enabled", "boolean", "reasoning"),
    "command_drip_show_likely_dropped": ("set_command_drip_show_likely_dropped_enabled", "boolean", "reasoning"),
    "load_live_init_prompt": ("set_live_init_mode", "runtime.live_init", ""),
    "sound_effects": ("set_sound_effects_enabled", "boolean", "sound"),
    "time_logging": ("set_time_logging_enabled", "boolean", "time_logging"),
    "chat_log_echo": ("set_chat_log_echo_enabled", "boolean", "chat_log_echo"),
    "overlay.tile_grid": ("set_tile_grid_enabled", "boolean", "overlay"),
    "overlay.cursor_label": ("set_cursor_label_enabled", "boolean", "overlay"),
    "overlay.keypoint_grid": ("set_keypoint_grid_enabled", "boolean", "overlay"),
    "overlay.status_text": ("set_status_overlay_enabled", "boolean", "overlay"),
    "advanced.auto_prompt": ("set_auto_prompt_enabled", "boolean", ""),
    "advanced.always_on": ("set_always_mode", "boolean", ""),
    "advanced.hide_input": ("set_always_mode", "boolean", ""),
    "advanced.image_detail": ("set_image_detail", "vision.image_detail", ""),
    "advanced.latest_image_detail": ("set_latest_image_detail", "vision.image_detail", ""),
    "advanced.high_detail": ("set_high_detail", "high_detail", ""),
    "advanced.max_images_in_history": ("set_max_images_in_history", "nonnegative_int", ""),
    "advanced.show_user_text": ("set_show_user_text_enabled", "boolean", ""),
    "advanced.show_ai_text": ("set_show_ai_text_enabled", "boolean", ""),
    "advanced.show_ai_commands": ("set_show_ai_commands_enabled", "boolean", ""),
    "advanced.show_user_commands": ("set_show_user_commands_enabled", "boolean", ""),
    "advanced.enable_unimportant_messages": ("set_unimportant_messages_enabled", "boolean", ""),
    "advanced.enable_important_messages": ("set_important_messages_enabled", "boolean", ""),
    "advanced.add_umsgs_to_history": ("set_add_umsgs_to_history_enabled", "boolean", ""),
    "advanced.add_imsgs_to_history": ("set_add_imsgs_to_history_enabled", "boolean", ""),
    "advanced.check_umsgs_decay": ("set_umsgs_decay_check_enabled", "boolean", ""),
    "advanced.check_imsgs_decay": ("set_imsgs_decay_check_enabled", "boolean", ""),
}
SCHEDULER_PROFILE_FIELDS = {
    "turn_scheduler_mode": "mode",
    "turn_heartbeat_seconds": "heartbeat_seconds",
    "turn_min_gap_seconds": "min_gap_seconds",
    "turn_capture_wake_enabled": "capture_wake_enabled",
    "turn_capture_wake_debounce_seconds": "capture_wake_debounce_seconds",
    "turn_post_action_settle_seconds": "post_action_settle_seconds",
}


class DefaultProfileError(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get("reason") or "Defaults profile operation failed.")


def profile_value(profile, path):
    value = profile
    for part in path.split("."):
        value = value[part]
    return value


def set_profile_value(profile, path, value):
    parts = path.split(".")
    current = profile
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = copy.deepcopy(value)


def _profile_integer(value, minimum):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Expected an integer.")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < minimum or number > 9223372036854775807 or number != number.to_integral_value():
            raise ValueError("Expected an integer in the supported range.")
        return int(number)
    except InvalidOperation as error:
        raise ValueError("Expected an integer.") from error


def coerce_profile_value(path, value):
    _, contract, _ = PROFILE_FIELDS[path]
    if "." in contract:
        if path == "turn_scheduler_profile" and isinstance(value, str) and value.strip().lower() == "custom":
            return "custom"
        return coerce_setting_value(contract, value)
    if contract == "boolean":
        return coerce_setting_value("runtime.live", value)
    if contract in {"nonnegative_int", "positive_int"}:
        return _profile_integer(value, 1 if contract == "positive_int" else 0)
    if contract == "high_detail":
        if isinstance(value, str) and value.strip().lower() in {"true", "all", "t", "a"}:
            return value.strip().lower()
        if value is True:
            return "true"
        return _profile_integer(value, -9223372036854775808)
    if contract == "persist_interval":
        number = coerce_setting_value("scheduler.heartbeat_seconds", value)
        if number < 0.5:
            raise ValueError("Unchanged screenshot persistence must be at least 0.5 seconds.")
        return number
    allowed = {"summary": {"auto", "none", "brief", "detailed"}, "pending_mode": {"normal", "replace", "insert"}}[contract]
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if normalized not in allowed:
        raise ValueError("Expected one of: " + ", ".join(sorted(allowed)))
    return normalized


def normalize_profile_snapshot(snapshot):
    """Validate every supplied field without applying it; omission keeps current state."""
    if not isinstance(snapshot, dict):
        raise ValueError("Profile snapshot must be a dictionary.")
    normalized, ignored = {}, []
    for key, value in snapshot.items():
        if key in {"overlay", "advanced"}:
            if value is None:
                continue  # Older profiles may omit a section using null.
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object.")
            entries = [(key + "." + str(child), item) for child, item in value.items()]
        else:
            entries = [(key, value)]
        for path, item in entries:
            if path not in PROFILE_FIELDS:
                ignored.append(str(path))
                continue
            contract = PROFILE_FIELDS[path][1]
            if item in (None, "") and contract not in {"boolean", "nonnegative_int", "positive_int"}:
                continue  # Preserve legacy optional blank fields.
            try:
                set_profile_value(normalized, path, coerce_profile_value(path, item))
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid defaults field {path}: {error}") from error
    if normalized.get("turn_scheduler_profile") == "custom" and not all(key in normalized for key in SCHEDULER_PROFILE_FIELDS):
        raise ValueError("A saved custom scheduler requires all six scheduler settings.")
    return normalized, sorted(ignored)


def supplied_profile_fields(profile):
    fields = []
    for path in PROFILE_FIELDS:
        try:
            profile_value(profile, path)
        except KeyError:
            continue
        fields.append(path)
    return fields


def profile_lock_keys(profile):
    locks = set()
    for path in supplied_profile_fields(profile):
        _, contract, lock = PROFILE_FIELDS[path]
        if "." in contract:
            lock = resolve_setting_definition(contract).lock_key
        if lock:
            locks.add(lock)
    return sorted(locks)


def project_profile_snapshot(before, supplied, scheduler_profiles):
    """Expand named presets before explicit knobs; custom is a derived readback label."""
    target = copy.deepcopy(before)
    selected = supplied.get("turn_scheduler_profile")
    if selected and selected != "custom":
        preset = scheduler_profiles[selected]
        for field, key in SCHEDULER_PROFILE_FIELDS.items():
            target[field] = preset[key]
    for path in supplied_profile_fields(supplied):
        set_profile_value(target, path, profile_value(supplied, path))
    target["turn_scheduler_profile"] = "custom"
    for name, preset in scheduler_profiles.items():
        matches = all((abs(float(target[field]) - float(preset[key])) < 1e-9
                       if isinstance(preset[key], (float, int)) and not isinstance(preset[key], bool)
                       else target[field] == preset[key]) for field, key in SCHEDULER_PROFILE_FIELDS.items())
        if matches:
            target["turn_scheduler_profile"] = name
            break
    return target


def profile_version(profile):
    encoded = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "profile:" + hashlib.sha256(encoded).hexdigest()


def _unique_profile_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate defaults field: {key}")
        result[key] = value
    return result


def _finite_profile_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Defaults numbers must be finite.")
    return number


def read_profile_document(path):
    result = {"status": "missing", "profile": None, "version": "", "reason": ""}
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(MAX_PROFILE_BYTES + 1)
    except FileNotFoundError:
        return result
    except OSError as error:
        return dict(result, status="unreadable", reason=str(error))
    result["version"] = "file:" + hashlib.sha256(data).hexdigest()
    try:
        if len(data) > MAX_PROFILE_BYTES:
            result["version"] = ""  # A bounded prefix is not a fingerprint of the complete file.
            raise ValueError("Defaults file exceeds the 8 MiB limit.")
        profile = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_profile_object,
                             parse_float=_finite_profile_number, parse_constant=_finite_profile_number)
        _, ignored = normalize_profile_snapshot(profile)
        return dict(result, status="available", profile=profile, ignored_fields=ignored)
    except (ValueError, UnicodeError, RecursionError) as error:
        return dict(result, status="invalid", reason=str(error))


def merge_profile_document(existing, current):
    """Keep forward/extension fields without carrying stale values of known settings."""
    merged = copy.deepcopy(existing)
    for key, value in current.items():
        if key in {"advanced", "overlay"}:
            section = merged.get(key)
            section = section if isinstance(section, dict) else {}
            section.update(copy.deepcopy(value))
            merged[key] = section
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def save_profile_document(path, current):
    """Publish in the destination directory, fsync, replace, then verify file bytes."""
    path = Path(path)
    before = read_profile_document(path)
    result = {"success": False, "effect_status": "not_started", "before_file_version": before["version"],
              "file_version": before["version"], "file_status": before["status"], "reason": "", "profile": None}
    if before["status"] not in {"available", "missing"}:
        return dict(result, reason="Existing personal defaults are " + before["status"] + ": " + before["reason"])
    temporary = None
    published = False
    try:
        normalize_profile_snapshot(current)
        profile = merge_profile_document(before["profile"] or {}, current)
        data = (json.dumps(profile, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        if len(data) > MAX_PROFILE_BYTES:
            raise ValueError("Defaults file exceeds the 8 MiB limit.")
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix="." + path.name + ".aurora-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        fresh = read_profile_document(path)
        if fresh["version"] != before["version"] or fresh["status"] != before["status"]:
            raise RuntimeError("Personal defaults changed before publication; save was not applied.")
        os.replace(temporary, path)
        published = True
        expected = "file:" + hashlib.sha256(data).hexdigest()
        after = read_profile_document(path)
        result.update(file_version=after["version"], file_status=after["status"])
        if after["status"] != "available" or after["version"] != expected:
            raise RuntimeError("Saved defaults readback did not match; reconcile the file before retrying.")
        result.update(success=True, effect_status="observed", profile=profile)
    except Exception as error:
        result.update(effect_status="uncertain" if published else "not_started", reason=str(error))
        after = read_profile_document(path)
        result.update(file_version=after["version"], file_status=after["status"])
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as error:
                result.update(success=False, effect_status="uncertain", cleanup_error=str(error), temporary_path=str(temporary))
    return result


def validate_default_profile_arguments(name, args):
    name = name.upper()
    if name in {"APPLY_PERSONAL_DEFAULTS", "APPLY_SYSTEM_DEFAULTS"}:
        if len(args) > 1:
            raise ValueError(f"{name} accepts one optional mode: reapply or changed_only.")
        mode = str(args[0]).strip().lower() if args else "reapply"
        if mode not in {"reapply", "changed_only"}:
            raise ValueError(f"{name} mode must be reapply or changed_only.")
        return mode
    if name not in DEFAULT_PROFILE_COMMANDS or args:
        raise ValueError(f"{name} takes no arguments.")
    return None


def describe_default_profile_contract(name):
    applies = name.upper() in {"APPLY_PERSONAL_DEFAULTS", "APPLY_SYSTEM_DEFAULTS"}
    parameters = [{"name": "mode", "type": "string", "enum": ["reapply", "changed_only"],
                   "required": False, "default": "reapply"}] if applies else []
    return {"parameter_validation": "pre_dispatch", "argument_style": "positional", "parameters": parameters,
            "min_arguments": 0, "max_arguments": 1 if applies else 0, "effects": DEFAULT_PROFILE_COMMANDS[name.upper()],
            "profile_fields": list(PROFILE_FIELDS), "unknown_fields": "preserved_on_save_reported_but_not_applied",
            "omitted_fields": "retain_current_runtime_values", "validation_owner": "aurora_default_profiles",
            "result": {"protocol": DEFAULT_PROFILE_RESULT_SCHEMA, "receipt_field": "default_profile_results",
                       "schema": {"type": "object", "required": ["schema_version", "command", "operation", "success", "effect_status",
                                  "before_profile", "profile", "before_version", "after_version", "attempted_fields", "restoration", "reason"],
                                  "properties": {"schema_version": {"const": DEFAULT_PROFILE_RESULT_SCHEMA},
                                                 "command": {"enum": list(DEFAULT_PROFILE_COMMANDS)},
                                                 "operation": {"enum": ["read", "save", "apply"]}, "success": {"type": "boolean"},
                                                 "apply_mode": {"enum": ["reapply", "changed_only"]},
                                                 "effect_status": {"enum": ["observed", "not_started", "restored", "uncertain"]},
                                                 **{key: {"type": "object"} for key in ("before_profile", "profile", "restoration")},
                                                 **{key: {"type": "array", "items": {"type": "string"}} for key in ("requested_fields", "changed_fields", "attempted_fields", "ignored_fields")},
                                                 **{key: {"type": "string"} for key in ("before_version", "after_version", "before_file_version", "file_version", "reason")}}},
                       "failure_policy": "Stop the batch tail. Prevalidate before writes; attempt and verify restoration after partial apply. Never replay automatically.",
                       "verification": "Runtime profile state or saved file bytes; not provider, overlay, native-effect or cross-process CAS proof."}}
