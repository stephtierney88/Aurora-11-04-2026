"""Reviewed command contracts shared by admission, execution and discovery.

Coverage is deliberately explicit. Unreviewed handlers retain their existing
argument behavior; discovery must not present heuristic signatures as schemas.
"""
from __future__ import annotations

from aurora_goal_store import (GOAL_FILE_COMMANDS, parse_task_file_arguments, describe_goal_file_contract,
                               MEMORY_COMMANDS, HORIZON_COMMANDS, parse_memory_command_arguments, describe_memory_command_contract)

import copy
import hashlib
import json
import math
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple

from aurora_default_profiles import (
    DEFAULT_PROFILE_COMMANDS, validate_default_profile_arguments, describe_default_profile_contract,
)
from aurora_pending_commands import PENDING_COMMANDS, validate_pending_arguments, describe_pending_contract
from aurora_retrieval_commands import EPISODIC_COMMANDS, parse_episodic_command, describe_episodic_contract
from aurora_retrieval_results import RETRIEVAL_RESULT_COMMANDS, parse_retrieval_result_arguments, describe_retrieval_result_contract
from aurora_history_controls import HISTORY_COMMANDS, parse_history_arguments, describe_history_contract
from aurora_settings_registry import (
    SETTING_DEFINITIONS, RUNTIME_LOCK_ALIASES, RUNTIME_LOCK_KEYS, coerce_setting_value, normalize_runtime_lock_key,
)
from aurora_settings_transactions import (
    SETTINGS_TRANSACTION_WIRE_COMMANDS, SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION, parse_settings_transaction_command,
    inspect_settings_transaction_request,
)


def _registered_setting_commands():
    commands = {}
    for definition in SETTING_DEFINITIONS:
        for name in (definition.command.split("(", 1)[0], *definition.command_aliases):
            if name in commands:
                raise ValueError(f"Duplicate registered setting command: {name}")
            commands[name] = definition
    return commands


REGISTERED_SETTING_COMMANDS = _registered_setting_commands()
SIMPLE_BOOLEAN_COMMANDS = frozenset({
    "SET_AUTO_DYNAMIC_INFERENCE", "SET_AUTO_PROMPT", "SET_SHOW_USER_TEXT", "SET_SHOW_AI_TEXT",
    "SET_SHOW_AI_COMMANDS", "SET_SHOW_USER_COMMANDS", "SET_UNIMPORTANT_MESSAGES", "SET_IMPORTANT_MESSAGES",
    "SET_ADD_UMSGS_TO_HISTORY", "SET_ADD_IMSGS_TO_HISTORY", "SET_UMSGS_DECAY_CHECK", "SET_IMSGS_DECAY_CHECK",
    "SET_COMMAND_DRIP_SHOW_VARIANTS", "SET_COMMAND_DRIP_SHOW_LIKELY_DROPPED", "SET_CHAT_HEAD_TOPMOST",
    "SET_EPISODIC_MEMORY", "SET_EPISODIC_MEMORY_PERIODIC", "SET_EPISODIC_MEMORY_SCENE_TRIGGER",
})


def parse_boolean_command_arguments(name, args):
    """Existing boolean aliases; omitted value is a query, not false."""
    if not args:
        return None
    if len(args) != 1 or not isinstance(args[0], str):
        raise ValueError(f"{name} accepts one on/off value, or no arguments to inspect it.")
    value = args[0].strip().lower()
    if value in {'on', 'true', '1', 'yes'}:
        return True
    if value in {'off', 'false', '0', 'no'}:
        return False
    raise ValueError(f"{name} requires on/off (also true/false, 1/0, yes/no).")


def describe_boolean_command_contract(name):
    return {"parameter_validation": "pre_dispatch", "min_arguments": 0, "max_arguments": 1,
            "parameters": [{"name": "enabled", "type": "boolean", "required": False,
                            "omitted": "read_current_value", "accepted_text": ["on", "off", "true", "false", "1", "0", "yes", "no"]}],
            "effects": "Existing runtime toggle only; preserves current query and setting behavior. Not a registered settings transaction.",
            "result": {"protocol": "boolean_handler_result", "failure_policy": "Validate the whole batch before effects; a handler failure stops its remaining commands.",
                       "verification": "Query or inspect runtime state; no versioned setting receipt is implied."}}


SETTING_SHORTCUT_COMMANDS = {
    "TOGGLE_LIVE_MODE": {"setting_command": "SET_LIVE_MODE", "operation": "toggle"},
    "TOGGLE_IMAGE_DETAIL": {"setting_command": "SET_IMAGE_DETAIL", "operation": "toggle"},
    "GB_MODE": {"setting_command": "SET_ACTION_MODE", "value": "gb", "operation": "set"},
    "PYAG_MODE": {"setting_command": "SET_ACTION_MODE", "value": "pyag", "operation": "set"},
    "NO_ACTION_MODE": {"setting_command": "SET_ACTION_MODE", "value": "none", "operation": "set"},
}
LOCK_COMMANDS = {"LOCK_SETTING": True, "UNLOCK_SETTING": False}
TRANSACTION_COMMANDS = {command: operation for operation, command in SETTINGS_TRANSACTION_WIRE_COMMANDS.items()}
INPUT_CONTROL_COMMANDS = {
    "SHOW_HELD_INPUTS": "Inspect Aurora-owned inputs, their request identity, frozen route and release uncertainty.",
    "RELEASE_HELD_INPUTS": "Cancel active/queued command batches and release Aurora-owned inputs. Model work and Live stay unchanged.",
    "CANCEL_ACTIVE_WORK": "Cancel model and command work and release Aurora-owned inputs. Live stays unchanged; remote model work may still drain.",
    "SHUTDOWN_RUNTIME": "Request shutdown, cancel work and release Aurora-owned inputs; report incomplete cleanup.",
}

INFERENCE_PLAN_COMMANDS = frozenset({
    "SET_NEXT_INFERENCE", "SET_NEXT_REASONING_EFFORT", "CLEAR_NEXT_INFERENCE", "SHOW_NEXT_INFERENCE",
})
INFERENCE_PLAN_RESULT_SCHEMA = "aurora_inference_plan_result_v1"
INFERENCE_PLAN_SUMMARIES = {
    "SET_NEXT_INFERENCE": "Replace the queued one-turn model/effort/verbosity/image/temperature plan; omit arguments to inspect. Session defaults stay unchanged.",
    "SET_NEXT_REASONING_EFFORT": "Replace the queued plan with one turn's reasoning effort and optional note; omit arguments to inspect. Model compatibility normalization still applies.",
    "CLEAR_NEXT_INFERENCE": "Clear the queued one-turn override, retaining normal session policy. Works while setting locks are enabled.",
    "SHOW_NEXT_INFERENCE": "Read the queued one-turn plan and its content fingerprint without changing it.",
}
NEXT_INFERENCE_ALIASES = {
    "reasoning": "reasoning_effort", "verbosity_level": "verbosity", "summary": "summary_mode",
    "detail": "image_detail", "latest_detail": "latest_image_detail",
}
NEXT_INFERENCE_SETTING_KEYS = {
    "service_tier": "inference.service_tier",
    "reasoning_effort": "inference.reasoning_effort", "verbosity": "inference.verbosity",
    "image_detail": "vision.image_detail", "latest_image_detail": "vision.image_detail",
    "temperature": "inference.temperature", "model": "model.text", "text_model": "model.text",
    "vision_model": "model.vision", "reasoning_model": "model.reasoning",
}
NEXT_INFERENCE_KEYS = (*NEXT_INFERENCE_SETTING_KEYS, "summary_mode", "note", "target_turn")


def _inference_option_segments(text):
    """Split legacy semicolon/newline options without losing quoted delimiters."""
    quote, escaped, stack, current = "", False, [], []
    for char in text:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char in "([{":
            stack.append(char)
            current.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[char]:
                raise ValueError("Unmatched bracket in next inference options.")
            current.append(char)
        elif char in ";\n" and not stack:
            if "".join(current).strip():
                yield "".join(current).strip()
            current = []
        else:
            current.append(char)
    if quote or stack:
        raise ValueError("Incomplete quoted/bracketed next inference option.")
    if "".join(current).strip():
        yield "".join(current).strip()


def normalize_next_inference_pairs(pairs):
    """Validate a detached plan; reject unknown, ambiguous or invalid fields before effects."""
    entries = pairs.items() if isinstance(pairs, dict) else pairs
    normalized = {}
    for raw_key, raw_value in entries:
        key = str(raw_key).strip().lower().replace(" ", "_")
        key = NEXT_INFERENCE_ALIASES.get(key, key)
        if key not in NEXT_INFERENCE_KEYS:
            raise ValueError(f"Unknown next inference option: {raw_key}. Expected: {', '.join(NEXT_INFERENCE_KEYS)}.")
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            continue  # Existing blank fields mean omitted; other supplied fields still apply.
        if isinstance(raw_value, (dict, list, tuple, set, bool)):
            raise ValueError(f"{key} requires a scalar value.")
        if key in NEXT_INFERENCE_SETTING_KEYS:
            value = coerce_setting_value(NEXT_INFERENCE_SETTING_KEYS[key], raw_value)
            if key == "temperature":
                value = f"{value:.2f}"  # Preserve the existing two-decimal plan representation.
        elif key == "summary_mode":
            value = str(raw_value).strip().lower()
            if value not in {"auto", "none", "brief", "detailed"}:
                raise ValueError("summary_mode must be auto, none, brief, or detailed.")
        elif key == "target_turn":
            try:
                number = Decimal(str(raw_value).strip())
                if not number.is_finite() or number < 0 or number > 9223372036854775807 or number != number.to_integral_value():
                    raise ValueError
                value = int(number)
            except (ValueError, InvalidOperation, OverflowError) as error:
                raise ValueError("target_turn must be an integer from 0 to 9223372036854775807; zero selects the next turn.") from error
        else:
            value = str(raw_value).strip()
        if key in normalized and normalized[key] != value:
            raise ValueError(f"Conflicting values for next inference option: {key}.")
        normalized[key] = value
    if not any(key != "target_turn" for key in normalized):
        raise ValueError("SET_NEXT_INFERENCE requires at least one setting or note.")
    return normalized


def parse_inference_plan_arguments(name, args):
    """Use the same option parser for whole-batch admission and direct execution."""
    name = name.upper()
    if name not in INFERENCE_PLAN_COMMANDS:
        raise ValueError(f"Unknown inference-plan command: {name}.")
    if name in {"CLEAR_NEXT_INFERENCE", "SHOW_NEXT_INFERENCE"}:
        if args:
            raise ValueError(f"{name} takes no arguments.")
        return {}
    if not args:
        return {}
    if name == "SET_NEXT_REASONING_EFFORT":
        if len(args) > 2:
            raise ValueError("SET_NEXT_REASONING_EFFORT takes an effort and optional note, or no arguments to inspect.")
        # A blank effort is invalid, even if a note was supplied.
        effort = coerce_setting_value("inference.reasoning_effort", args[0])
        return normalize_next_inference_pairs({
            "reasoning_effort": effort, "note": args[1] if len(args) > 1 else "one-turn reasoning effort override",
        })
    entries = []
    for argument in args:
        if not isinstance(argument, str):
            raise ValueError("SET_NEXT_INFERENCE options must be key=value text.")
        for segment in _inference_option_segments(argument):
            separator = "=" if "=" in segment else ":" if ":" in segment else ""
            if not separator:
                raise ValueError(f"Expected a key=value next inference option: {segment}.")
            key, value = segment.split(separator, 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            entries.append((key, value))
    return normalize_next_inference_pairs(entries)


def inference_plan_version(plan):
    """A content fingerprint, not the settings version or proof of provider application."""
    payload = json.dumps(plan, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return "inference-plan-v1:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def describe_inference_plan_contract(name):
    no_options = name.upper() in {"SHOW_NEXT_INFERENCE", "CLEAR_NEXT_INFERENCE"}
    effort_only = name.upper() == "SET_NEXT_REASONING_EFFORT"
    definitions = {definition.key: definition for definition in SETTING_DEFINITIONS}
    options = {}
    for key, setting_key in NEXT_INFERENCE_SETTING_KEYS.items():
        definition = definitions[setting_key]
        option = {"type": "number" if definition.value_type == "float" else "string", "setting_contract": setting_key}
        if definition.allowed_values:
            option["enum"] = list(definition.allowed_values)
        for bound in ("minimum", "maximum"):
            if getattr(definition, bound) is not None:
                option[bound] = getattr(definition, bound)
        if definition.value_type == "float":
            option["finite"] = True
        options[key] = option
    options.update(summary_mode={"type": "string", "enum": ["auto", "none", "brief", "detailed"]},
                   note={"type": "string"},
                   target_turn={"type": "integer", "minimum": 0, "maximum": 9223372036854775807,
                                "default": 0, "zero": "next_turn"})
    return {
        "parameter_validation": "pre_dispatch", "argument_style": "positional" if no_options or effort_only else "named_options",
        "min_arguments": 0, "max_arguments": 0 if no_options else 2 if effort_only else None,
        "parameters": [] if no_options else (
            [{"name": "effort", "type": "string", "required": False, "omitted": "read_current_plan",
              "enum": list(REGISTERED_SETTING_COMMANDS["SET_REASONING_EFFORT"].allowed_values)},
             {"name": "note", "type": "string", "required": False}] if effort_only else
            [{"name": "options", "type": "string", "required": False, "variadic": True, "omitted": "read_current_plan",
              "keys": list(NEXT_INFERENCE_KEYS), "accepted_aliases": dict(NEXT_INFERENCE_ALIASES),
              "option_schema": {"type": "object", "properties": options, "additionalProperties": False},
              "separators": ["semicolon", "newline", "separate command arguments"], "assignment": ["=", ":"]}]),
        "effects": INFERENCE_PLAN_SUMMARIES[name.upper()],
        "replacement_semantics": "Supplied options replace the entire queued plan; omitted fields do not carry forward. Empty fields are omitted; conflicting duplicates or aliases reject.",
        "validation_owner": "aurora_command_contracts.parse_inference_plan_arguments",
        "runtime_validation": "Model/reasoning/temperature locks, plan replacement and turn consumption share the settings lock. target_turn=0 selects the next turn; past targets apply at the next resolution.",
        "result": {"protocol": INFERENCE_PLAN_RESULT_SCHEMA, "receipt_field": "inference_plan_results",
                   "failure_policy": "Reject malformed batches before effects. Stop the batch tail on execution failure; do not replay uncertain outcomes.",
                   "verification": "Detached before/after queued plans and content fingerprints. A queued plan is not proof of provider acceptance; model compatibility normalization still applies."},
    }


class DesktopActionContext(NamedTuple):
    """Serializable action meaning admitted before queueing; contains no live API objects."""
    namespace: str
    origin: str
    action_mode: str
    backend: str
    requested_key: str = ""
    effective_key: str = ""

    def to_dict(self):
        return self._asdict()


_DESKTOP_ACTION_CONTEXT = ContextVar("aurora_desktop_action_context", default=None)


def current_desktop_action_context():
    return _DESKTOP_ACTION_CONTEXT.get()


@contextmanager
def desktop_action_scope(context):
    """Keep a command's route local to its execution thread, restoring nested callers."""
    token = _DESKTOP_ACTION_CONTEXT.set(context)
    try:
        yield
    finally:
        _DESKTOP_ACTION_CONTEXT.reset(token)


def projected_action_mode(name, args, current_mode):
    """Project explicit setting writes only; unknown profile/rollback outcomes require a prefix."""
    name = name.upper()
    definition = setting_command_definition(name)
    if definition and definition.key == "runtime.action" and (args or setting_shortcut_definition(name)):
        return parse_setting_command_arguments(name, args)
    if name == "APPLY_SETTINGS_TRANSACTION":
        request = parse_settings_transaction_command(name, args)
        for change in inspect_settings_transaction_request(request)["changes"]:
            if change["key"] == "runtime.action":
                return change["value"]
    if name in {"ROLLBACK_SETTINGS_TRANSACTION", "APPLY_PERSONAL_DEFAULTS", "APPLY_SYSTEM_DEFAULTS",
                "ARM_LIVE_VISUAL_HARNESS_PROBE", "ARM_CHEAP_LIVE_VISUAL_HARNESS", "ARM_STRONG_LIVE_VISUAL_HARNESS"}:
        return None
    return current_mode


def setting_shortcut_definition(name):
    return SETTING_SHORTCUT_COMMANDS.get(name.strip().upper())


def setting_command_definition(name):
    shortcut = setting_shortcut_definition(name)
    return REGISTERED_SETTING_COMMANDS.get(shortcut["setting_command"] if shortcut else name.strip().upper())


def parse_setting_command_arguments(name, args):
    """Reuse registry coercion; an omitted value is a read, never a default write."""
    definition = setting_command_definition(name)
    if definition is None:
        raise ValueError(f"Unknown registered setting command: {name}")
    shortcut = setting_shortcut_definition(name)
    if shortcut:
        if args:
            raise ValueError(f"{name.upper()} accepts no arguments; received {len(args)}.")
        return shortcut.get("value")
    if len(args) > 1:
        raise ValueError(f"{name.upper()} accepts zero arguments to read or one value to set; received {len(args)}.")
    return coerce_setting_value(definition.key, args[0]) if args else None


def setting_command_result(name, *, requested_value=None, operation="set"):
    definition = setting_command_definition(name)
    return {"schema_version": "aurora_setting_command_result_v1", "command": name.upper(),
            "key": definition.key, "operation": operation, "success": False, "effect_status": "not_started",
            "requested_value": requested_value, "before_value": None, "value": None,
            "value_status": "unavailable", "before_version": "", "after_version": "", "reason": ""}


def parse_lock_command_arguments(name, args):
    if name.upper() not in LOCK_COMMANDS or len(args) > 1:
        raise ValueError(f"{name.upper()} accepts zero arguments to read locks or one lock name.")
    if not args:
        return ""
    key = normalize_runtime_lock_key(args[0])
    if not key:
        raise ValueError("Unknown runtime lock. Expected one of: " + ", ".join(RUNTIME_LOCK_KEYS))
    return key


def command_failure_stops_batch(name):
    if name.upper() in MEMORY_COMMANDS or name.upper() in SIMPLE_BOOLEAN_COMMANDS:
        return True
    return bool(name.upper() in GOAL_FILE_COMMANDS or setting_command_definition(name) or name.upper() in LOCK_COMMANDS or name.upper() in TRANSACTION_COMMANDS or name.upper() in INPUT_CONTROL_COMMANDS or name.upper() in INFERENCE_PLAN_COMMANDS or name.upper() in DEFAULT_PROFILE_COMMANDS or name.upper() in PENDING_COMMANDS or name.upper() in HISTORY_COMMANDS or name.upper() in RETRIEVAL_RESULT_COMMANDS or name.upper() in EPISODIC_COMMANDS or name.upper() == "RESET_RESPONSES_SESSION")


def describe_setting_command_contract(name):
    definition = setting_command_definition(name)
    parameter = {"name": "value", "type": {"enum": "string", "float": "number"}.get(definition.value_type, definition.value_type),
                 "required": False, "omitted": "read_current_value", "nullable": False}
    if definition.allowed_values:
        parameter["enum"] = list(definition.allowed_values)
    if definition.value_aliases:
        parameter["accepted_aliases"] = dict(definition.value_aliases)
    if definition.value_type == "boolean":
        parameter["accepted_text"] = ["on", "true", "1", "yes", "off", "false", "0", "no"]
    if definition.value_type == "string":
        parameter["nonempty"] = True
    if definition.value_type == "float":
        parameter["finite"] = True
    for bound in ("minimum", "maximum"):
        if getattr(definition, bound) is not None:
            parameter[bound] = getattr(definition, bound)
    contract = {"parameter_validation": "pre_dispatch", "parameters": [parameter], "argument_style": "positional",
            "min_arguments": 0, "max_arguments": 1, "setting_key": definition.key,
            "validation_owner": "aurora_settings_registry.coerce_setting_value", "lock_key": definition.lock_key,
            "apply_timing": definition.apply_timing, "scope": "runtime_session",
            "effects": f"Read {definition.key} when omitted; otherwise set it in this runtime session. {definition.description} Saved defaults are unchanged.",
            "related_effects": ("A scheduler profile changes its timing/wake bundle; manual scheduler values may change the profile readback."
                                if definition.key.startswith("scheduler.") else
                                "Turning live mode off cancels pending model work; completed actions are not undone."
                                if definition.key == "runtime.live" else "See setting metadata for application timing."),
            "result": {"protocol": "aurora_setting_command_result_v1", "receipt_field": "setting_results",
                       "schema": {"type": "object", "required": ["schema_version", "command", "key", "operation", "success", "effect_status", "requested_value", "before_value", "value", "value_status", "before_version", "after_version", "reason"],
                                  "properties": {"schema_version": {"const": "aurora_setting_command_result_v1"},
                                                 "command": {"type": "string"}, "key": {"const": definition.key},
                                                 "operation": {"enum": ["read", "set", "toggle"]}, "success": {"type": "boolean"},
                                                 "effect_status": {"enum": ["observed", "not_started", "uncertain"]},
                                                 **{field: {"type": ["boolean", "number", "string", "null"]} for field in ("requested_value", "before_value", "value")},
                                                 **{field: {"type": "string"} for field in ("value_status", "before_version", "after_version", "reason")}}},
                       "failure_policy": "Stop the remaining batch after failure; no automatic replay or rollback of raw setters.",
                       "verification": "Observed registered runtime value under the settings transaction lock; not proof of credentials, model availability or downstream application behavior."}}
    shortcut = setting_shortcut_definition(name)
    if shortcut:
        effect = ("Flip live mode on/off." if definition.key == "runtime.live" else
                  "Switch low image detail to high; every other supported detail switches to low." if shortcut["operation"] == "toggle" else
                  f"Set {definition.key} to {shortcut['value']}.")
        contract.update(parameters=[], min_arguments=0, max_arguments=0,
                        effects=effect + " Uses the same runtime setting lock and observed readback.",
                        setting_shortcut=copy.deepcopy(shortcut))
    return contract


def describe_lock_command_contract(name):
    return {"parameter_validation": "pre_dispatch", "argument_style": "positional", "min_arguments": 0, "max_arguments": 1,
            "parameters": [{"name": "lock", "type": "string", "required": False, "omitted": "read_current_locks",
                            "enum": list(RUNTIME_LOCK_KEYS), "accepted_aliases": dict(RUNTIME_LOCK_ALIASES)}],
            "effects": "Read locks when omitted; otherwise enable or disable the named runtime setting lock. Settings values are unchanged.",
            "validation_owner": "aurora_settings_registry.normalize_runtime_lock_key",
            "result": {"protocol": "aurora_lock_command_result_v1", "receipt_field": "lock_results",
                       "schema": {"type": "object", "required": ["schema_version", "command", "operation", "lock_key", "success", "effect_status", "before_locks", "locks", "before_version", "after_version", "reason"],
                                  "properties": {"schema_version": {"const": "aurora_lock_command_result_v1"},
                                                 "operation": {"enum": ["read", "lock", "unlock"]},
                                                 "success": {"type": "boolean"},
                                                 "effect_status": {"enum": ["observed", "not_started", "uncertain"]},
                                                 **{key: {"type": "object", "additionalProperties": {"type": "boolean"}} for key in ("before_locks", "locks")},
                                                 **{key: {"type": "string"} for key in ("command", "lock_key", "before_version", "after_version", "reason")}}},
                       "failure_policy": "Stop the remaining batch after failure; no automatic replay or rollback.",
                       "verification": "Runtime lock readback under the settings transaction lock; not an access-control boundary."}}


def describe_transaction_command_contract(name):
    return {"parameter_validation": "pre_dispatch", "argument_style": "positional", "min_arguments": 1, "max_arguments": 1,
            "parameters": [{"name": "token", "type": "string", "required": True, "format": "url_safe_base64_json",
                            "request_schema": "aurora_settings_transaction_request_v1", "operation": TRANSACTION_COMMANDS[name.upper()]}],
            "validation_owner": "aurora_settings_transactions.parse_settings_transaction_command",
            "effects": "Preview, atomically apply, or explicitly roll back registered runtime settings through the existing transaction service.",
            "runtime_validation": "Version, setting locks, current values and rollback-handle availability are checked at execution under the transaction lock.",
            "result": {"protocol": SETTINGS_TRANSACTION_RECEIPT_SCHEMA_VERSION, "receipt_field": "settings_transaction_receipts",
                       "failure_policy": "Stop the remaining batch on any rejected or failed transaction. No automatic replay. Apply attempts restoration on failure; restoration is separately verified.",
                       "verification": "Observed registered runtime settings; failed_uncertain means an unexpected service failure prevents a definitive completion claim."}}


def wait_duration(args) -> float:
    """Parse WAIT's single finite, non-negative duration without side effects."""
    if len(args) != 1:
        raise ValueError("WAIT requires one finite, non-negative duration in seconds.")
    try:
        seconds = float(args[0])
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("WAIT requires one finite, non-negative duration in seconds.") from error
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("WAIT requires one finite, non-negative duration in seconds.")
    return seconds


def _parameter(name, kind, *, default=None, required=False, minimum=None, **metadata):
    value = {"name": name, "type": kind, "required": required, **metadata}
    if not required:
        value["default"] = default
    if minimum is not None:
        value["minimum"] = minimum
    if kind == "number":
        value["finite"] = True
    return value


_X = _parameter("x", "integer", nullable=True)
_Y = _parameter("y", "integer", nullable=True)
_DURATION = _parameter("duration", "number", default=0.0, minimum=0)
_INTERVAL = _parameter("interval", "number", default=0.0, minimum=0)
_BUTTON = _parameter("button", "string", default="left",
                     enum=["left", "middle", "right", "primary", "secondary"])
_KEY = _parameter("key", "string", required=True, format="keyboard_key", nonempty=True)
_KEYS = _parameter("keys", "string", required=True, variadic=True, format="desktop_keyboard_key", nonempty=True)


def _desktop(parameters, summary, effects, *, key_space="none"):
    return {"parameters": parameters, "summary": summary, "effects": effects, "key_space": key_space}


DESKTOP_COMMAND_SPECS = {
    "move": _desktop([_parameter("x", "integer", required=True), _parameter("y", "integer", required=True), _DURATION],
                     "Move the pointer to desktop coordinates; negative coordinates support other monitors.", "Moves the pointer."),
    "drag": _desktop([_parameter("x", "integer", required=True), _parameter("y", "integer", required=True), _DURATION, _BUTTON],
                     "Drag to desktop coordinates with the selected mouse button.", "Moves the pointer while holding a mouse button."),
    "scroll_up": _desktop([_parameter("amount", "integer", default=1)],
                          "Scroll upward by signed units; negative units reverse direction.", "Scrolls the current target."),
    "scroll_down": _desktop([_parameter("amount", "integer", default=1)],
                            "Scroll downward by signed units; negative units reverse direction.", "Scrolls the current target."),
    "press": _desktop([_KEY, _parameter("presses", "integer", default=1, minimum=1), _INTERVAL],
                      "Press one key a positive integer number of times, with an optional interval.",
                     "PYAG sends literal desktop keys. GB translates game controls through the admitted game backend and requires confirmed focus.", key_space="game_or_desktop"),
    "hold": _desktop([_KEY, _parameter("duration", "number", minimum=0, nullable=True)],
                     "Hold a key; omit duration for an indefinite hold requiring an explicit release.",
                     "Holds a key; timed holds release on completion or cancellation. Game input requires confirmed focus.", key_space="game_or_desktop"),
    "release": _desktop([_KEY, _parameter("routing", "string", default="owned", enum=["owned", "current"])],
                        "Release a key using its owned route; optional current explicitly uses the current mapping.",
                        "Uses the original hold backend/key, without changing focus. Repeated owned release is a no-op. Untracked keys retain legacy current-route key-up; current explicitly bypasses ownership lookup and does not clear another owned route.", key_space="game_or_desktop"),
    "move_key": _desktop([_KEY, _parameter("tiles", "integer", required=True, minimum=1)],
                         "Hold a game direction using the existing tile-duration calibration; game-specific accuracy is not guaranteed.",
                         "Waits 1.35 seconds, then performs a timed key hold; requires confirmed game focus when using that backend.", key_space="game_or_desktop"),
    "hotkey": _desktop([_KEYS], "Press a complete chord; every key must be valid before any key is sent.",
                       "Presses the chord keys in order and releases them in reverse order.", key_space="desktop"),
    "multi_press": _desktop([_KEYS], "Press every listed key in order; invalid keys reject the whole request.",
                            "Sends a sequence of desktop key presses.", key_space="desktop"),
    "multi_hold": _desktop([_KEYS], "Hold all listed keys until explicitly released.",
                           "Holds desktop keys; an interrupted setup attempts to release keys already held.", key_space="desktop"),
    "multi_release": _desktop([_KEYS], "Release every listed desktop key.",
                              "Attempts every requested key release even if one release reports an error.", key_space="desktop"),
    "type": _desktop([_parameter("text", "string", required=True), _INTERVAL],
                     "Type text supported by the active PyAutoGUI character set, with an optional interval.",
                     "Types into the focused target. Unsupported characters reject the entire request before typing.", key_space="text"),
    "click": _desktop([_X, _Y, _BUTTON], "Click at optional coordinates; omitted or null coordinates use the current position.",
                      "Sends one mouse click."),
    "doubleclick": _desktop([_X, _Y, _BUTTON], "Double-click at optional coordinates using the selected mouse button.",
                            "Sends two mouse clicks."),
    "hold_click": _desktop([_X, _Y, _DURATION, _BUTTON], "Hold a mouse button for a finite duration, releasing on completion or cancellation.",
                           "Moves to optional coordinates and holds a mouse button for the requested duration."),
    "focus_window": _desktop([_parameter("title", "string", nonempty=True, nullable=True)],
                             "Focus a matching window, or the configured emulator title when omitted; failure blocks later batch actions.",
                             "May restore/foreground a window; reports whether target focus was confirmed."),
    "screenshot": _desktop([_parameter("filename", "string", default="screenshot.png", nonempty=True)],
                           "Save a desktop screenshot at the supplied path or screenshot.png.",
                           "Captures the desktop and writes an image file, potentially replacing an existing file."),
}
DESKTOP_COMMAND_SPECS["leftclick"] = DESKTOP_COMMAND_SPECS["click"]


class DesktopCommandError(RuntimeError):
    """A desktop action with an explicit reason and knowledge of its effect."""
    def __init__(self, reason, *, effect_status="uncertain"):
        super().__init__(reason)
        self.effect_status = effect_status


def _parse_parameter(command, value, parameter):
    label = f"pyag:{command}: {parameter['name']}"
    if value is None or (parameter.get("nullable") and str(value).strip().lower() in {"none", "null"}):
        if parameter.get("nullable"):
            return None
        raise ValueError(f"{label} cannot be null.")
    kind = parameter["type"]
    if kind in {"number", "integer"}:
        try:
            number = Decimal(str(value).strip())
            if not number.is_finite() or not math.isfinite(float(number)) or (kind == "integer" and number != number.to_integral_value()):
                raise ValueError
            parsed = int(number) if kind == "integer" else float(number)
            if kind == "number" and not math.isfinite(parsed):
                raise ValueError
        except (InvalidOperation, TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{label} must be a finite {kind}.") from error
        if "minimum" in parameter and parsed < parameter["minimum"]:
            raise ValueError(f"{label} must be at least {parameter['minimum']}.")
        return parsed
    parsed = str(value) if parameter["name"] == "text" else str(value).strip()
    if parameter.get("nonempty") and not parsed:
        raise ValueError(f"{label} cannot be empty.")
    if "enum" in parameter:
        parsed = parsed.lower()
        if parsed not in parameter["enum"]:
            raise ValueError(f"{label} must be one of {', '.join(parameter['enum'])}.")
    if parameter.get("format"):
        parsed = parsed.lower()
    return parsed


def parse_desktop_arguments(name: str, args) -> dict[str, Any]:
    """Parse all desktop parameters without importing or operating a desktop API."""
    command = name.lower().removeprefix("pyag:")
    if command not in DESKTOP_COMMAND_SPECS:
        raise ValueError(f"Unknown desktop action: {name}")
    parameters = DESKTOP_COMMAND_SPECS[command]["parameters"]
    minimum = sum(parameter["required"] for parameter in parameters)
    variadic = bool(parameters and parameters[-1].get("variadic"))
    if len(args) < minimum or (not variadic and len(args) > len(parameters)):
        maximum = "unbounded" if variadic else str(len(parameters))
        raise ValueError(f"pyag:{command} requires {minimum}..{maximum} positional arguments; received {len(args)}.")
    values = {}
    for index, parameter in enumerate(parameters):
        if parameter.get("variadic"):
            values[parameter["name"]] = [_parse_parameter(command, value, parameter) for value in args[index:]]
        elif index < len(args):
            values[parameter["name"]] = _parse_parameter(command, args[index], parameter)
        else:
            values[parameter["name"]] = parameter["default"]
    return values


def validate_desktop_keys(name, values, *, keyboard_keys, game_key_validator):
    """Check the complete key/text set against the active runtime before input."""
    command = name.lower().removeprefix("pyag:")
    space = DESKTOP_COMMAND_SPECS[command]["key_space"]
    if space == "game_or_desktop":
        if not game_key_validator(values["key"]):
            raise ValueError(f"pyag:{command}: invalid keyboard/game key {values['key']!r}.")
    elif space in {"desktop", "text"}:
        valid = set(keyboard_keys)
        keys = values["keys"] if space == "desktop" else values["text"]
        invalid = next((key for key in keys if key.lower() not in valid), None)
        if invalid is not None:
            raise ValueError(f"pyag:{command}: unsupported {'character' if space == 'text' else 'key'} {invalid!r}.")


def validate_command_arguments(name: str, args) -> None:
    """Validate reviewed parameters before any member of a batch dispatches."""
    if name.upper() in MEMORY_COMMANDS:
        parse_memory_command_arguments(name, args)
    elif name.upper() in SIMPLE_BOOLEAN_COMMANDS:
        parse_boolean_command_arguments(name, args)
    elif name.upper() in GOAL_FILE_COMMANDS:
        parse_task_file_arguments(name, args)
    elif name.upper() in EPISODIC_COMMANDS:
        parse_episodic_command(name, args)
    elif name.upper() in RETRIEVAL_RESULT_COMMANDS:
        parse_retrieval_result_arguments(name, args)
    elif name.upper() in HISTORY_COMMANDS:
        parse_history_arguments(name, args)
    elif name.upper() in PENDING_COMMANDS:
        validate_pending_arguments(name, args)
    elif name.upper() in INPUT_CONTROL_COMMANDS:
        if args:
            raise ValueError(f"{name.upper()} takes no arguments.")
    elif name.upper() == "RESET_RESPONSES_SESSION":
        if args:
            raise ValueError("RESET_RESPONSES_SESSION takes no arguments.")
    elif name.upper() in DEFAULT_PROFILE_COMMANDS:
        validate_default_profile_arguments(name, args)
    elif name.upper() in INFERENCE_PLAN_COMMANDS:
        parse_inference_plan_arguments(name, args)
    elif name.upper() == "WAIT":
        wait_duration(args)
    elif name.lower().startswith("pyag:"):
        parse_desktop_arguments(name, args)
    elif setting_command_definition(name):
        parse_setting_command_arguments(name, args)
    elif name.upper() in LOCK_COMMANDS:
        parse_lock_command_arguments(name, args)
    elif name.upper() in TRANSACTION_COMMANDS:
        parse_settings_transaction_command(name, args)


def desktop_result(name, *, success=True, effect_status="submitted", reason=""):
    """Keep API submission distinct from a verified application effect."""
    return {"schema_version": "aurora_desktop_result_v1", "command": "pyag:" + name.lower().removeprefix("pyag:"),
            "success": bool(success), "effect_status": effect_status, "reason": str(reason)}


def reviewed_command_description(name):
    if name.upper() in SIMPLE_BOOLEAN_COMMANDS:
        return {"signature": f"{name.upper()}([on|off])", "summary": "Set this existing runtime toggle, or omit the value to inspect it. Also accepts true/false, 1/0, yes/no."}
    if name.upper() in MEMORY_COMMANDS:
        signature = ("goal_text[, priority, significance]" if name.upper() == "ADD_GOAL" else
                     "goal_id" if name.upper() == "COMPLETE_GOAL" else "" if name.upper() == "TASKS" else
                     "text..." if name.upper() in HORIZON_COMMANDS else "text")
        return {"signature": f"{name.upper()}({signature})", "summary": describe_memory_command_contract(name)["semantics"]}
    if name.upper() in GOAL_FILE_COMMANDS:
        return {"signature": f"{name.upper()}([path])", "summary": describe_goal_file_contract(name)["effects"]}
    if name.upper() in EPISODIC_COMMANDS:
        signature = ("query, [k,] options..." if name.upper() in {"RECALL", "MEM"} else
                     "query_or_filters, options..." if name.upper() == "RETRIEVAL_PULL" else
                     "[reason, tags]" if name.upper() == "WRITE_EPISODIC_SNAPSHOT" else
                     "[limit]" if name.upper() == "LIST_EPISODIC_SNAPSHOTS" else "query[, limit]")
        return {"signature": f"{name.upper()}({signature})", "summary": describe_episodic_contract(name)["semantics"]}
    if name.upper() in RETRIEVAL_RESULT_COMMANDS:
        signature = "handle[, offset, limit]" if name.upper() == "SHOW_RETRIEVAL_RESULT" else "index, target[, prefix, result_handle]"
        return {"signature": f"{name.upper()}({signature})", "summary": describe_retrieval_result_contract(name)["semantics"]}
    if name.upper() in HISTORY_COMMANDS:
        operation = HISTORY_COMMANDS[name.upper()]
        signature = ("message_id, revision, text_json_base64url, on|off|keep" if operation == "update_message" else
                     "text..." if operation in {"pin", "replace_init"} else
                     "percentage[, random|oldest|newest]" if operation == "clear_unprotected_percentage" else
                     "percentage" if operation == "clear_percentage" else
                     "timestamp, text[, timestamp, text...]" if operation == "edit" else
                     "timestamp" if operation == "delete" else "[path_prefix]" if operation == "save" else "")
        return {"signature": f"{name.upper()}({signature})", "summary": describe_history_contract(name)["semantics"]}
    if name.upper() in PENDING_COMMANDS:
        operation = PENDING_COMMANDS[name.upper()]
        signature = "command" if operation == "queue" else "" if operation == "show" else "[selectors..., version:hash]"
        return {"signature": f"{name.upper()}({signature})", "summary": {
            "queue": "Hold a validated command/batch using the chosen normal, insert or replace mode.",
            "show": "Inspect held command identities, queue version, state and recovery evidence.",
            "approve": "Submit the selected held commands once; preserve unstarted or uncertain items for inspection.",
            "clear": "Drop matching held/uncertain items without execution; an empty match changes nothing.",
        }[operation]}
    if name.upper() in DEFAULT_PROFILE_COMMANDS:
        mode = "[mode]" if name.upper().startswith("APPLY_") else ""
        return {"signature": f"{name.upper()}({mode})", "summary": DEFAULT_PROFILE_COMMANDS[name.upper()]}
    if name.upper() in INFERENCE_PLAN_COMMANDS:
        signature = ("[key=value; ...]" if name.upper() == "SET_NEXT_INFERENCE" else
                     "[effort[, note]]" if name.upper() == "SET_NEXT_REASONING_EFFORT" else "")
        return {"signature": f"{name.upper()}({signature})",
                "summary": INFERENCE_PLAN_SUMMARIES[name.upper()]}
    if name.upper() in INPUT_CONTROL_COMMANDS:
        return {"signature": f"{name.upper()}()", "summary": INPUT_CONTROL_COMMANDS[name.upper()]}
    definition = setting_command_definition(name)
    if definition:
        if setting_shortcut_definition(name):
            return {"signature": f"{name.upper()}()", "summary": describe_setting_command_contract(name)["effects"]}
        return {"signature": f"{name.upper()}([value])", "summary": f"Set {definition.key}, or omit value to read it. {definition.description}"}
    if name.upper() in LOCK_COMMANDS:
        return {"signature": f"{name.upper()}([lock])", "summary": describe_lock_command_contract(name)["effects"]}
    if name.upper() in TRANSACTION_COMMANDS:
        return {"signature": f"{name.upper()}(token)", "summary": describe_transaction_command_contract(name)["effects"]}
    command = name.lower().removeprefix("pyag:")
    if name.lower().startswith("pyag:") and command in DESKTOP_COMMAND_SPECS:
        spec = DESKTOP_COMMAND_SPECS[command]
        arguments = []
        for parameter in spec["parameters"]:
            argument = parameter["name"]
            if parameter.get("variadic"):
                argument += "..."
            elif not parameter["required"]:
                argument += "=" + repr(parameter["default"])
            arguments.append(argument)
        return {"signature": f"pyag:{command}({', '.join(arguments)})", "summary": spec["summary"]}
    if name.upper() == "WAIT":
        return {"signature": "WAIT(seconds)", "summary": "Wait for a finite, non-negative duration in seconds while servicing cancellation and controls."}
    return None


def command_result_failed(result: Any) -> bool:
    """Recognize explicit failure while retaining legacy None-as-completion."""
    return result is False or (isinstance(result, dict) and result.get("success") is False)


def describe_command_contract(name: str) -> dict[str, Any]:
    if name.upper() in SIMPLE_BOOLEAN_COMMANDS:
        return describe_boolean_command_contract(name)
    if name.upper() in MEMORY_COMMANDS:
        return describe_memory_command_contract(name)
    if name.upper() in GOAL_FILE_COMMANDS:
        return describe_goal_file_contract(name)
    """Expose exact coverage instead of inferring contracts from command names."""
    if name.upper() in EPISODIC_COMMANDS:
        return describe_episodic_contract(name)
    if name.upper() in RETRIEVAL_RESULT_COMMANDS:
        return describe_retrieval_result_contract(name)
    if name.upper() in HISTORY_COMMANDS:
        return describe_history_contract(name)
    if name.upper() in PENDING_COMMANDS:
        return describe_pending_contract(name)
    if name.upper() in DEFAULT_PROFILE_COMMANDS:
        return describe_default_profile_contract(name)
    if name.upper() in INFERENCE_PLAN_COMMANDS:
        return describe_inference_plan_contract(name)
    if setting_command_definition(name):
        return describe_setting_command_contract(name)
    if name.upper() in LOCK_COMMANDS:
        return describe_lock_command_contract(name)
    if name.upper() in TRANSACTION_COMMANDS:
        return describe_transaction_command_contract(name)
    contract = {
        "parameter_validation": "legacy_handler",
        "parameters": None,
        "effects": "not_reviewed",
        "result": {
            "protocol": "legacy_handler_return",
            "explicit_failure": "false or an object with success=false",
            "none": "legacy_completion_without_typed_value",
            "typed_value_schema": None,
        },
    }
    if name.upper() in INPUT_CONTROL_COMMANDS:
        contract.update(parameter_validation="pre_dispatch", parameters=[], min_arguments=0, max_arguments=0,
                        effects=INPUT_CONTROL_COMMANDS[name.upper()],
                        result={"protocol": "aurora_held_inputs_v1" if name.upper() == "SHOW_HELD_INPUTS" else "aurora_input_cleanup_v1",
                                "receipt_field": "held_input_results" if name.upper() == "SHOW_HELD_INPUTS" else "input_cleanup_results",
                                "failure_policy": "Stop the remaining batch on failure. Failed releases stay tracked for explicit retry; an in-flight native call may defer cleanup to its owner.",
                                "verification": "Backend submission only; no proof of application behavior or ownership of physically held human inputs."})
    elif name.upper() == "RESET_RESPONSES_SESSION":
        contract.update(parameter_validation="pre_dispatch", parameters=[], min_arguments=0, max_arguments=0,
                        effects="Clear local provider continuation identity between requests under the reasoning lock; no API request, no remote-history deletion, no automatic replay.",
                        result={"protocol": "boolean_handler_result", "success": "true after local reset",
                                "failure_policy": "Stop batch tail on failure; reject active/draining model I/O.",
                                "verification": "Inspect model_status.responses_reasoning for generation and reset reason."})
    elif name.upper() == "WAIT":
        contract.update(
            parameter_validation="pre_dispatch",
            parameters=[{"name": "seconds", "type": "number", "required": True,
                         "minimum": 0, "finite": True}],
            min_arguments=1,
            max_arguments=1,
            effects="cooperative_delay; cancellation and control servicing remain active",
        )
    elif name.lower().startswith("pyag:"):
        spec = DESKTOP_COMMAND_SPECS.get(name.lower()[5:])
        if spec:
            parameters = copy.deepcopy(spec["parameters"])
            contract.update(parameter_validation="pre_dispatch", parameters=parameters,
                            min_arguments=sum(parameter["required"] for parameter in parameters),
                            max_arguments=None if parameters[-1].get("variadic") else len(parameters),
                            argument_style="positional", effects=spec["effects"], key_validation=spec["key_space"],
                            action_routing="Explicit PYAG is literal desktop input; GB uses game mappings/backend/focus. Known preceding action-mode setters guide later unprefixed commands. The resolved namespace/backend/key are frozen at admission and retained through queueing; foreground heuristics cannot retarget a prepared action.",
                            result={"protocol": "aurora_desktop_result_v1", "receipt_field": "desktop_results",
                                    "schema": {"type": "object", "required": ["schema_version", "command", "success", "effect_status", "reason"],
                                               "properties": {"schema_version": {"const": "aurora_desktop_result_v1"},
                                                              "command": {"type": "string"}, "success": {"type": "boolean"},
                                                              "effect_status": {"enum": ["submitted", "observed", "not_started", "uncertain"]},
                                                              "reason": {"type": "string"},
                                                              "action_route": {"type": "object", "description": "Present for prepared runtime commands, including cancellation/failure and duplicate receipts.",
                                                                               "required": ["namespace", "origin", "action_mode", "backend", "requested_key", "effective_key"],
                                                                               "properties": {"namespace": {"enum": ["gb", "pyag"]}, "origin": {"enum": ["explicit", "implicit"]},
                                                                                              **{key: {"type": "string"} for key in ("action_mode", "backend", "requested_key", "effective_key")}}}}},
                                    "failure_policy": "Stop the remaining batch; do not retry uncertain input automatically.",
                                    "verification": "submitted means API completion, not observed application behavior"})
    return contract
