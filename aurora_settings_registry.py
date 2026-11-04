from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


SETTINGS_REGISTRY_SCHEMA_VERSION = "aurora_settings_registry_v1"
SETTING_READBACK_SCHEMA_VERSION = "aurora_setting_readback_v1"
SETTINGS_SNAPSHOT_SCHEMA_VERSION = "aurora_settings_snapshot_v1"
SETTINGS_VERSION_SCHEMA_VERSION = "aurora_settings_version_v1"
DEFAULT_STATE_FRESH_SECONDS = 10.0
SETTING_WRITES_ENABLED = True
SETTING_MUTATION_STATUS = "atomic_runtime_transactions"

RUNTIME_LOCK_ALIASES = {'auth': 'auth',
 'live': 'live',
 'execution': 'execution',
 'action': 'action',
 'model': 'models',
 'models': 'models',
 'reasoning': 'reasoning',
 'thinking': 'reasoning',
 'temperature': 'temperature',
 'temp': 'temperature',
 'screenshot_interval': 'screenshot_interval',
 'screenshot-interval': 'screenshot_interval',
 'interval': 'screenshot_interval',
 'overlay': 'overlay',
 'overlays': 'overlay',
 'visuals': 'overlay',
 'display': 'overlay',
 'tile_grid': 'overlay',
 'tile-grid': 'overlay',
 'cursor_label': 'overlay',
 'cursor-label': 'overlay',
 'keypoint_grid': 'overlay',
 'keypoint-grid': 'overlay',
 'status_overlay': 'overlay',
 'status-overlay': 'overlay',
 'live_init': 'live_init',
 'live-init': 'live_init',
 'init': 'live_init',
 'sound': 'sound',
 'time_logging': 'time_logging',
 'time-logging': 'time_logging',
 'timing': 'time_logging',
 'chat_log_echo': 'chat_log_echo',
 'chat-log-echo': 'chat_log_echo',
 'chatlog': 'chat_log_echo',
 'echo': 'chat_log_echo'}
RUNTIME_LOCK_KEYS = tuple(dict.fromkeys(RUNTIME_LOCK_ALIASES.values()))


def normalize_runtime_lock_key(name):
    return RUNTIME_LOCK_ALIASES.get(str(name or "").strip().lower(), "")


_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MISSING = object()


class SettingRegistryError(ValueError):
    pass


class InvalidSettingKeyError(SettingRegistryError):
    pass


class UnknownSettingKeyError(SettingRegistryError):
    pass


class InvalidSettingValueError(SettingRegistryError):
    pass


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    title: str
    category: str
    description: str
    value_type: str
    state_path: tuple[str, ...]
    compatibility_default_path: tuple[str, ...]
    command: str
    aliases: tuple[str, ...] = ()
    command_aliases: tuple[str, ...] = ()
    value_aliases: tuple[tuple[str, Any], ...] = ()
    lock_key: str = ""
    allowed_values: tuple[str, ...] = ()
    readback_only_values: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    compatibility_default: Any = None
    allowed_scopes: tuple[str, ...] = ("runtime_session",)
    maturity: str = "stable"
    gui_tier: str = "advanced"
    risk_class: str = "advanced"
    apply_timing: str = "immediate"
    origin_state_path: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state_path"] = list(self.state_path)
        payload["compatibility_default_path"] = list(self.compatibility_default_path)
        payload["aliases"] = list(self.aliases)
        payload["command_aliases"] = list(self.command_aliases)
        payload["value_aliases"] = dict(self.value_aliases)
        payload["allowed_values"] = list(self.allowed_values)
        payload["readback_only_values"] = list(self.readback_only_values)
        payload["allowed_scopes"] = list(self.allowed_scopes)
        payload["origin_state_path"] = list(self.origin_state_path)
        payload["write_enabled"] = SETTING_WRITES_ENABLED
        payload["mutation_status"] = SETTING_MUTATION_STATUS
        return payload


def _setting(
    key: str,
    title: str,
    category: str,
    description: str,
    value_type: str,
    state_path: tuple[str, ...],
    compatibility_default_path: tuple[str, ...],
    command: str,
    **kwargs: Any,
) -> SettingDefinition:
    return SettingDefinition(
        key=key,
        title=title,
        category=category,
        description=description,
        value_type=value_type,
        state_path=state_path,
        compatibility_default_path=compatibility_default_path,
        command=command,
        **kwargs,
    )


SETTING_DEFINITIONS = (
    _setting(
        "auth.mode",
        "Authentication mode",
        "access",
        "Credential route Aurora will resolve before a model request.",
        "enum",
        ("modes", "auth"),
        ("defaults", "system_profile", "auth_mode"),
        "SET_AUTH_MODE({value})",
        aliases=("auth", "auth_mode"),
        lock_key="auth",
        allowed_values=("api_key", "codex_oauth", "auto"),
        compatibility_default="api_key",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_auth_resolution",
    ),
    _setting(
        "runtime.live",
        "Live model loop",
        "runtime",
        "Whether Aurora may send model requests and process model responses.",
        "boolean",
        ("modes", "live"),
        (),
        "SET_LIVE_MODE({value})",
        aliases=("live", "live_mode"),
        value_aliases=(("live", True), ("safe", False)),
        lock_key="live",
        compatibility_default=False,
        gui_tier="recovery-critical",
        risk_class="recovery-critical",
        apply_timing="immediate_model_loop_gate",
    ),
    _setting(
        "runtime.execution",
        "Execution mode",
        "runtime",
        "Approval and execution posture for commands proposed by the model.",
        "enum",
        ("modes", "execution"),
        ("defaults", "system_profile", "execution_mode"),
        "SET_EXECUTION_MODE({value})",
        aliases=("execution", "execution_mode"),
        value_aliases=(("review", "safe"), ("guided", "assist"), ("live", "auto")),
        lock_key="execution",
        allowed_values=("safe", "assist", "auto"),
        compatibility_default="assist",
        gui_tier="recovery-critical",
        risk_class="recovery-critical",
        apply_timing="immediate_command_policy",
    ),
    _setting(
        "runtime.action",
        "Action mode",
        "runtime",
        "Controller family available to Aurora for approved actions.",
        "enum",
        ("modes", "action"),
        ("defaults", "system_profile", "action_mode"),
        "SET_ACTION_MODE({value})",
        aliases=("action", "action_mode"),
        value_aliases=(("game", "gb"), ("gameboy", "gb"), ("game_boy", "gb"),
                       ("pyautogui", "pyag"), ("desktop", "pyag"), ("off", "none"),
                       ("disabled", "none"), ("clear", "none")),
        lock_key="action",
        allowed_values=("none", "gb", "pyag"),
        compatibility_default="gb",
        gui_tier="recovery-critical",
        risk_class="recovery-critical",
        apply_timing="immediate_action_dispatch",
    ),
    _setting(
        "game.profile",
        "Game profile",
        "gameplay",
        "Gameplay assumptions, prompts, controls, and save-state guidance.",
        "enum",
        ("modes", "game_profile"),
        ("defaults", "system_profile", "game_profile"),
        "SET_GAME_PROFILE({value})",
        aliases=("game", "game_profile"),
        allowed_values=("firered", "blue"),
        compatibility_default="firered",
        gui_tier="basic",
        risk_class="basic",
        apply_timing="next_gameplay_reasoning",
        origin_state_path=("modes", "game_profile_source"),
    ),
    _setting(
        "model.text",
        "Text model",
        "models",
        "Model used for text-oriented Aurora turns.",
        "string",
        ("models", "text"),
        ("defaults", "system_profile", "text_model"),
        "SET_TEXT_MODEL({value})",
        aliases=("text_model",),
        lock_key="models",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
        notes="Available model names come from the runtime model catalog and are not frozen in this registry.",
    ),
    _setting(
        "model.vision",
        "Vision model",
        "models",
        "Model selected for vision-oriented Aurora turns.",
        "string",
        ("models", "vision"),
        ("defaults", "system_profile", "vision_model"),
        "SET_VISION_MODEL({value})",
        aliases=("vision_model",),
        lock_key="models",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
        notes="Available model names come from the runtime model catalog and are not frozen in this registry.",
    ),
    _setting(
        "model.reasoning",
        "Reasoning model",
        "models",
        "Model selected when Aurora requests a reasoning-oriented turn.",
        "string",
        ("models", "reasoning"),
        ("defaults", "system_profile", "reasoning_model"),
        "SET_REASONING_MODEL({value})",
        aliases=("reasoning_model",),
        lock_key="models",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
        notes="Available model names come from the runtime model catalog and are not frozen in this registry.",
    ),
    _setting(
        "model.transport", "Model transport", "models",
        "Explicit live transport selection. Responses requires Astra/API-key auth and keeps provider history. An intervening Chat Completions turn requires an explicit Responses reset. Does not enable live mode.",
        "enum", ("models", "transport"), ("defaults", "system_profile", "model_transport"),
        "SET_MODEL_TRANSPORT({value})", aliases=("model_transport",), lock_key="models",
        allowed_values=("chat_completions", "responses"), compatibility_default="chat_completions",
        gui_tier="advanced", risk_class="advanced", apply_timing="next_model_turn",
        notes="Session-only; defaults profiles do not save transport. Changes are rejected while model I/O is active or draining.",
    ),
    _setting(
        "inference.reasoning_effort",
        "Session reasoning effort",
        "inference",
        "Default reasoning effort before model-specific compatibility normalization.",
        "enum",
        ("models", "reasoning_effort"),
        ("defaults", "system_profile", "reasoning_effort"),
        "SET_SESSION_REASONING_EFFORT({value})",
        aliases=("reasoning_effort", "effort"),
        command_aliases=("SET_REASONING_EFFORT",),
        lock_key="reasoning",
        allowed_values=("minimal", "none", "low", "medium", "high", "xhigh", "max"),
        compatibility_default="none",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
        notes="The active model may support only a subset; Model Status remains the compatibility truth surface.",
    ),
    _setting(
        "inference.verbosity",
        "Session verbosity",
        "inference",
        "Default response verbosity for model families that support it.",
        "enum",
        ("models", "verbosity"),
        ("defaults", "system_profile", "verbosity"),
        "SET_MODEL_VERBOSITY({value})",
        aliases=("verbosity", "model_verbosity"),
        lock_key="reasoning",
        allowed_values=("low", "medium", "high"),
        compatibility_default="medium",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
    ),
    _setting(
        "inference.temperature",
        "Model temperature",
        "inference",
        "Sampling temperature used by Aurora where the selected model accepts it.",
        "float",
        ("models", "temperature"),
        ("defaults", "system_profile", "temperature"),
        "SET_TEMPERATURE({value})",
        aliases=("temperature",),
        lock_key="temperature",
        minimum=0.0,
        maximum=2.0,
        compatibility_default=0.0,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_model_turn",
    ),
    _setting(
        "scheduler.profile",
        "Turn scheduler profile",
        "scheduler",
        "Named bundle for Aurora turn wake and pacing thresholds.",
        "enum",
        ("scheduler", "profile"),
        ("defaults", "system_profile", "turn_scheduler_profile"),
        "SET_TURN_SCHEDULER_PROFILE({value})",
        aliases=("scheduler_profile", "turn_scheduler_profile"),
        value_aliases=(("default", "balanced"), ("fast", "responsive"), ("quick", "responsive"),
                       ("slow", "conservative"), ("per_capture", "legacy"), ("per-capture", "legacy")),
        lock_key="reasoning",
        allowed_values=("responsive", "balanced", "conservative", "legacy"),
        readback_only_values=("custom",),
        compatibility_default="balanced",
        gui_tier="basic",
        risk_class="basic",
        apply_timing="immediate_scheduler",
        notes="custom is a readback state produced by manual timing changes; it is not directly applicable as a named profile.",
    ),
    _setting(
        "scheduler.mode",
        "Turn scheduler mode",
        "scheduler",
        "Wake strategy for capture-driven, event-driven, or hybrid turns.",
        "enum",
        ("scheduler", "mode"),
        ("defaults", "system_profile", "turn_scheduler_mode"),
        "SET_TURN_SCHEDULER_MODE({value})",
        aliases=("scheduler_mode", "turn_scheduler_mode"),
        value_aliases=(("legacy", "per_capture"), ("capture", "per_capture"), ("per-capture", "per_capture"),
                       ("capture_tick", "per_capture"), ("capture-tick", "per_capture"),
                       ("event_driven", "event"), ("event-driven", "event"), ("tool_loop", "event"),
                       ("tool-loop", "event"), ("hybrid_event", "hybrid"), ("hybrid-event", "hybrid"),
                       ("codex_like", "hybrid"), ("codex-like", "hybrid")),
        lock_key="reasoning",
        allowed_values=("per_capture", "event", "hybrid"),
        compatibility_default="hybrid",
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "scheduler.heartbeat_seconds",
        "Turn heartbeat seconds",
        "scheduler",
        "Maximum quiet interval before the scheduler heartbeat can wake a turn.",
        "float",
        ("scheduler", "heartbeat_seconds"),
        ("defaults", "system_profile", "turn_heartbeat_seconds"),
        "SET_TURN_HEARTBEAT_SECONDS({value})",
        aliases=("heartbeat", "turn_heartbeat_seconds"),
        lock_key="reasoning",
        minimum=0.25,
        compatibility_default=2.25,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "scheduler.min_gap_seconds",
        "Turn minimum gap seconds",
        "scheduler",
        "Minimum spacing between model-turn submissions.",
        "float",
        ("scheduler", "min_gap_seconds"),
        ("defaults", "system_profile", "turn_min_gap_seconds"),
        "SET_TURN_MIN_GAP_SECONDS({value})",
        aliases=("min_gap", "turn_min_gap_seconds"),
        lock_key="reasoning",
        minimum=0.0,
        compatibility_default=0.55,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "scheduler.capture_wake_enabled",
        "Capture-change scheduler wake",
        "scheduler",
        "Whether settled capture changes may wake a model turn in hybrid scheduler mode.",
        "boolean",
        ("scheduler", "capture_wake_enabled"),
        ("defaults", "system_profile", "turn_capture_wake_enabled"),
        "SET_TURN_CAPTURE_WAKE({value})",
        aliases=("capture_wake_enabled",),
        lock_key="reasoning",
        compatibility_default=True,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "scheduler.capture_wake_debounce_seconds",
        "Capture-change debounce seconds",
        "scheduler",
        "Settle delay before a changed capture may wake a model turn.",
        "float",
        ("scheduler", "capture_wake_debounce_seconds"),
        ("defaults", "system_profile", "turn_capture_wake_debounce_seconds"),
        "SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS({value})",
        aliases=("capture_wake_debounce",),
        lock_key="reasoning",
        minimum=0.0,
        compatibility_default=0.9,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "scheduler.post_action_settle_seconds",
        "Post-action settle seconds",
        "scheduler",
        "Delay after an action result before scheduler follow-up may proceed.",
        "float",
        ("scheduler", "post_action_settle_seconds"),
        ("defaults", "system_profile", "turn_post_action_settle_seconds"),
        "SET_TURN_POST_ACTION_SETTLE_SECONDS({value})",
        aliases=("post_action_settle",),
        lock_key="reasoning",
        minimum=0.0,
        compatibility_default=0.55,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_scheduler",
    ),
    _setting(
        "capture.screenshot_interval",
        "Screenshot interval seconds",
        "capture",
        "Requested screenshot polling interval before idle floors and other effective cadence rules.",
        "float",
        ("modes", "screenshot_interval"),
        ("defaults", "system_profile", "screenshot_interval"),
        "SET_SCREENSHOT_INTERVAL({value})",
        aliases=("screenshot_interval", "capture_interval"),
        lock_key="screenshot_interval",
        minimum=0.02,
        compatibility_default=0.12,
        gui_tier="advanced",
        risk_class="risky",
        apply_timing="next_capture_cycle",
        notes="The exported effective_screenshot_interval may be slower while Aurora is idle.",
    ),
    _setting(
        "capture.demand_enabled",
        "Demand capture enabled",
        "capture",
        "Whether commands and explicit requests may ask the capture service for a fresh frame.",
        "boolean",
        ("scheduler", "demand_capture_enabled"),
        ("defaults", "system_profile", "demand_capture_enabled"),
        "SET_DEMAND_CAPTURE({value})",
        aliases=("demand_capture", "demand_capture_enabled"),
        lock_key="screenshot_interval",
        compatibility_default=True,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="immediate_capture_service",
    ),
    _setting(
        "vision.image_detail",
        "Image detail",
        "vision",
        "Default image detail before model-specific compatibility normalization.",
        "enum",
        ("advanced", "image_detail"),
        ("defaults", "system_profile", "advanced", "image_detail"),
        "SET_IMAGE_DETAIL({value})",
        aliases=("image_detail",),
        allowed_values=("low", "high", "auto", "original"),
        compatibility_default="low",
        gui_tier="advanced",
        risk_class="risky",
        apply_timing="next_image_request",
        notes="original is model-dependent; the runtime may normalize it to high for unsupported models.",
    ),
    _setting(
        "runtime.live_init",
        "Live initialization prompt",
        "runtime",
        "Whether Aurora loads its full live initialization prompt when that path is used.",
        "boolean",
        ("modes", "load_live_init_prompt"),
        ("defaults", "system_profile", "load_live_init_prompt"),
        "SET_LIVE_INIT({value})",
        aliases=("live_init", "load_live_init_prompt"),
        lock_key="live_init",
        compatibility_default=False,
        gui_tier="advanced",
        risk_class="advanced",
        apply_timing="next_live_initialization",
    ),
)


def normalize_setting_key(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidSettingKeyError("Setting keys must be strings.")
    normalized = value.strip().lower()
    if not normalized or not _KEY_PATTERN.fullmatch(normalized):
        raise InvalidSettingKeyError(
            "Invalid setting key syntax. Use a canonical dotted key or a documented alias."
        )
    return normalized


def _build_setting_indexes() -> tuple[dict[str, SettingDefinition], dict[str, str]]:
    definitions: dict[str, SettingDefinition] = {}
    aliases: dict[str, str] = {}
    for definition in SETTING_DEFINITIONS:
        key = normalize_setting_key(definition.key)
        if key != definition.key or key in definitions or key in aliases:
            raise RuntimeError(f"Duplicate or non-normalized setting key: {definition.key}")
        if definition.value_type not in {"boolean", "enum", "float", "string"}:
            raise RuntimeError(f"Unsupported setting value type for {key}: {definition.value_type}")
        if definition.value_type == "enum" and not definition.allowed_values:
            raise RuntimeError(f"Enum setting {key} requires allowed values.")
        definitions[key] = definition
        for alias in definition.aliases:
            normalized_alias = normalize_setting_key(alias)
            if normalized_alias in definitions or normalized_alias in aliases:
                raise RuntimeError(f"Duplicate setting alias: {normalized_alias}")
            aliases[normalized_alias] = key
    return definitions, aliases


_SETTING_BY_KEY, _SETTING_ALIAS_TO_KEY = _build_setting_indexes()


def registry_summary() -> dict[str, Any]:
    categories = sorted({definition.category for definition in SETTING_DEFINITIONS})
    maturities = sorted({definition.maturity for definition in SETTING_DEFINITIONS})
    return {
        "schema_version": SETTINGS_REGISTRY_SCHEMA_VERSION,
        "mode": "transactional_runtime_session",
        "write_enabled": SETTING_WRITES_ENABLED,
        "setting_count": len(SETTING_DEFINITIONS),
        "alias_count": len(_SETTING_ALIAS_TO_KEY),
        "categories": categories,
        "maturities": maturities,
        "mutation_status": SETTING_MUTATION_STATUS,
    }


def resolve_setting_definition(key: Any) -> SettingDefinition:
    normalized = normalize_setting_key(key)
    canonical = _SETTING_ALIAS_TO_KEY.get(normalized, normalized)
    definition = _SETTING_BY_KEY.get(canonical)
    if definition is not None:
        return definition
    candidates = list(_SETTING_BY_KEY) + list(_SETTING_ALIAS_TO_KEY)
    suggestions = difflib.get_close_matches(normalized, candidates, n=3, cutoff=0.58)
    suffix = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise UnknownSettingKeyError(f"Unknown Aurora setting key: {normalized}.{suffix}")


def list_setting_definitions(
    *,
    category: str = "",
    maturity: str = "",
) -> list[SettingDefinition]:
    normalized_category = str(category or "").strip().lower()
    normalized_maturity = str(maturity or "").strip().lower()
    categories = set(registry_summary()["categories"])
    maturities = set(registry_summary()["maturities"])
    if normalized_category and normalized_category not in categories:
        raise SettingRegistryError(
            f"Unknown settings category: {normalized_category}. Expected one of: {', '.join(sorted(categories))}."
        )
    if normalized_maturity and normalized_maturity not in maturities:
        raise SettingRegistryError(
            f"Unknown settings maturity: {normalized_maturity}. Expected one of: {', '.join(sorted(maturities))}."
        )
    return [
        definition
        for definition in SETTING_DEFINITIONS
        if (not normalized_category or definition.category == normalized_category)
        and (not normalized_maturity or definition.maturity == normalized_maturity)
    ]


def coerce_setting_value(key: Any, value: Any, *, for_readback: bool = False) -> Any:
    definition = resolve_setting_definition(key)
    if isinstance(value, str) and not for_readback:
        value = dict(definition.value_aliases).get(value.strip().lower(), value)
    if definition.value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"on", "true", "1", "yes"}:
                return True
            if normalized in {"off", "false", "0", "no"}:
                return False
        raise InvalidSettingValueError(f"{definition.key} requires a boolean value.")

    if definition.value_type == "enum":
        if not isinstance(value, str):
            raise InvalidSettingValueError(
                f"{definition.key} requires one of: {', '.join(definition.allowed_values)}."
            )
        normalized = value.strip().lower()
        accepted_values = definition.allowed_values + (
            definition.readback_only_values if for_readback else ()
        )
        if normalized not in accepted_values:
            raise InvalidSettingValueError(
                f"{definition.key} requires one of: {', '.join(definition.allowed_values)}."
            )
        return normalized

    if definition.value_type == "float":
        if isinstance(value, bool):
            raise InvalidSettingValueError(f"{definition.key} requires a numeric value.")
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise InvalidSettingValueError(f"{definition.key} requires a numeric value.") from error
        if not math.isfinite(numeric):
            raise InvalidSettingValueError(f"{definition.key} requires a finite numeric value.")
        if definition.minimum is not None and numeric < definition.minimum:
            raise InvalidSettingValueError(
                f"{definition.key} must be at least {definition.minimum}."
            )
        if definition.maximum is not None and numeric > definition.maximum:
            raise InvalidSettingValueError(
                f"{definition.key} must be at most {definition.maximum}."
            )
        return numeric

    if definition.value_type == "string":
        if not isinstance(value, str) or not value.strip():
            raise InvalidSettingValueError(f"{definition.key} requires a non-empty string.")
        return value.strip()

    raise InvalidSettingValueError(f"Unsupported value type for {definition.key}.")


def _read_state_path(state: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    if not path:
        return False, None
    current: Any = state
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _version_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        json.dumps(value, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        return {"repr": repr(value)}
    return value


def build_settings_version(state: Mapping[str, Any] | None) -> str:
    state_mapping = state if isinstance(state, Mapping) else {}
    rows: list[dict[str, Any]] = []
    for definition in SETTING_DEFINITIONS:
        found, value = _read_state_path(state_mapping, definition.state_path)
        if found:
            try:
                value = coerce_setting_value(definition.key, value, for_readback=True)
            except InvalidSettingValueError:
                value = {"invalid_runtime_value": _version_safe_value(value)}
        lock_found, lock_value = _read_state_path(
            state_mapping,
            ("locks", definition.lock_key) if definition.lock_key else (),
        )
        rows.append(
            {
                "key": definition.key,
                "value_found": found,
                "value": _version_safe_value(value) if found else None,
                "lock_key": definition.lock_key,
                "lock_found": lock_found,
                "locked": bool(lock_value) if lock_found else None,
            }
        )

    payload = {
        "schema_version": SETTINGS_VERSION_SCHEMA_VERSION,
        "settings": rows,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sv1:{hashlib.sha256(encoded).hexdigest()}"


def _resolve_compatibility_default(
    definition: SettingDefinition,
    state: Mapping[str, Any],
) -> tuple[Any, str, str]:
    found, value = _read_state_path(state, definition.compatibility_default_path)
    if found:
        return value, "resolved", ".".join(definition.compatibility_default_path)
    if definition.compatibility_default_path:
        if definition.compatibility_default is not None:
            return definition.compatibility_default, "fallback", "registry_fallback"
        return None, "unavailable", ".".join(definition.compatibility_default_path)
    return definition.compatibility_default, "literal", "registry_literal"


def describe_setting_definition(
    key: Any,
    *,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    definition = resolve_setting_definition(key)
    payload = definition.to_dict()
    default_value, default_status, default_source = _resolve_compatibility_default(
        definition,
        state or {},
    )
    payload["compatibility_default"] = default_value
    payload["compatibility_default_status"] = default_status
    payload["compatibility_default_source"] = default_source
    payload["registry_schema_version"] = SETTINGS_REGISTRY_SCHEMA_VERSION
    return payload


def build_setting_readback(
    key: Any,
    state: Mapping[str, Any] | None,
    *,
    runtime_active: bool,
    state_age_seconds: float | None = None,
    state_timestamp: str = "",
    fresh_after_seconds: float = DEFAULT_STATE_FRESH_SECONDS,
) -> dict[str, Any]:
    definition = resolve_setting_definition(key)
    state_mapping = state if isinstance(state, Mapping) else {}
    found, observed_value = _read_state_path(state_mapping, definition.state_path)
    validation_error = ""
    if found:
        try:
            observed_value = coerce_setting_value(
                definition.key,
                observed_value,
                for_readback=True,
            )
        except InvalidSettingValueError as error:
            validation_error = str(error)

    if not found:
        value_status = "unavailable"
    elif validation_error:
        value_status = "invalid_runtime_value"
    elif not runtime_active:
        value_status = "last_observed"
    elif state_age_seconds is None or state_age_seconds > max(0.0, fresh_after_seconds):
        value_status = "stale"
    else:
        value_status = "effective"

    origin_found, origin_value = _read_state_path(state_mapping, definition.origin_state_path)
    lock_found, lock_value = _read_state_path(
        state_mapping,
        ("locks", definition.lock_key) if definition.lock_key else (),
    )
    default_value, default_status, default_source = _resolve_compatibility_default(
        definition,
        state_mapping,
    )
    return {
        "schema_version": SETTING_READBACK_SCHEMA_VERSION,
        "registry_schema_version": SETTINGS_REGISTRY_SCHEMA_VERSION,
        "key": definition.key,
        "title": definition.title,
        "category": definition.category,
        "value_type": definition.value_type,
        "value": observed_value if found else None,
        "value_status": value_status,
        "effective": value_status == "effective",
        "validation_error": validation_error,
        "source": {
            "kind": "runtime_state_export",
            "status": "available" if found else "unavailable",
            "path": ".".join(definition.state_path),
            "snapshot_timestamp": str(state_timestamp or state_mapping.get("timestamp") or ""),
            "age_seconds": state_age_seconds,
            "origin": origin_value if origin_found else "not_tracked",
            "origin_status": (
                "reported"
                if origin_found
                else "unavailable"
                if definition.origin_state_path
                else "not_tracked"
            ),
        },
        "scope": "runtime_session",
        "allowed_scopes": list(definition.allowed_scopes),
        "maturity": definition.maturity,
        "gui_tier": definition.gui_tier,
        "risk_class": definition.risk_class,
        "apply_timing": definition.apply_timing,
        "locked": bool(lock_value) if lock_found else False,
        "lock_key": definition.lock_key,
        "lock_status": (
            "reported"
            if lock_found
            else "unavailable"
            if definition.lock_key
            else "not_applicable"
        ),
        "compatibility_default": default_value,
        "compatibility_default_status": default_status,
        "compatibility_default_source": default_source,
        "write_enabled": SETTING_WRITES_ENABLED,
        "mutation_status": SETTING_MUTATION_STATUS,
    }


def build_settings_snapshot(
    state: Mapping[str, Any] | None,
    *,
    runtime_active: bool,
    state_age_seconds: float | None = None,
    state_timestamp: str = "",
    category: str = "",
    maturity: str = "",
) -> dict[str, Any]:
    state_mapping = state if isinstance(state, Mapping) else {}
    definitions = list_setting_definitions(category=category, maturity=maturity)
    rows = [
        build_setting_readback(
            definition.key,
            state_mapping,
            runtime_active=runtime_active,
            state_age_seconds=state_age_seconds,
            state_timestamp=state_timestamp,
        )
        for definition in definitions
    ]
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("value_status") or "unavailable")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": SETTINGS_SNAPSHOT_SCHEMA_VERSION,
        "version_schema_version": SETTINGS_VERSION_SCHEMA_VERSION,
        "version": build_settings_version(state_mapping),
        "registry": registry_summary(),
        "runtime_active": bool(runtime_active),
        "state_timestamp": str(state_timestamp or ""),
        "state_age_seconds": state_age_seconds,
        "filters": {
            "category": str(category or "").strip().lower(),
            "maturity": str(maturity or "").strip().lower(),
        },
        "count": len(rows),
        "status_counts": counts,
        "settings": rows,
    }
