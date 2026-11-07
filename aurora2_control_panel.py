import json
import heapq
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import ctypes
from pathlib import Path
from tkinter import font as tkfont, messagebox, simpledialog, ttk
from ctypes import wintypes
from aurora_episodic_retrieval import (
    RETRIEVAL_WEIGHT_KEYS, RETRIEVAL_OPTION_DEFAULTS, rebalance_score_weights,
    distribution_preview, finite_number,
)
import aurora_retrieval_commands as retrieval_commands
from aurora_retrieval_results import parse_retrieval_result_arguments
from aurora_conversation import conversation_text, VIEW_MODES
from aurora_conversation_navigator import ConversationNavigator, MessageEditor
from aurora_conversation_delivery import SessionOutbox, OutboxWindow, ConversationPopout, AwaitingReply, conversation_activity
from aurora_switchboard import Switchboard, PortalShortcuts
from aurora_search_query import SEARCH_DEFAULTS, SEARCH_CHOICES, normalize_search_options, search_has_filter
from aurora_panel_layout import (
    CollapsibleSection, FlowBar, ScrollablePane, clamp_window_geometry,
    load_layout_preferences, monitor_work_areas, save_layout_preferences, fit_popout_window, ui_scale,
    bind_label_wrap, wrap_packed_labels, receipt_tree_items, reconcile_tree_rows,
)

from aurora_control_plane import (
    release_info,
    append_bridge_request,
    build_operator_dashboard,
    build_operator_status,
    format_operator_dashboard,
    journal_offsets,
    wait_for_command_receipt,
)
from aurora_settings_registry import build_settings_snapshot
from aurora_settings_transactions import (
    SettingsTransactionError,
    build_settings_transaction_command,
    build_settings_transaction_request,
    extract_settings_transaction_receipt,
    setting_values_equal,
)

# AURORA_PREFLIGHT_IMPORTS_END
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "aurora_control_panel_state.json"
LAYOUT_PATH = ROOT / "aurora_control_panel_layout.json"
INBOX_PATH = ROOT / "aurora_external_inbox.jsonl"
BROWSER_BRIDGE_STATE_PATH = ROOT / "aurora_browser_bridge_state.json"
CHAT_LOG_PATH = ROOT / "aurora_chat_history_log.jsonl"
CMD_LOG_PATH = ROOT / "aurora_command_execution_log.jsonl"
EPISODIC_MEMORY_PATH = ROOT / "aurora_memory" / "episodic_snapshots.jsonl"
MODEL_CATALOG_PATH = ROOT / "aurora_model_catalog.json"
RUNTIME_PID_PATH = ROOT / "aurora_runtime.pid"
CONTROL_PANEL_PID_PATH = ROOT / "aurora_control_panel.pid"
RUNTIME_STATUS_ICON_PATH = ROOT / "aurora_runtime_status_icon.png"
CONTROL_PANEL_MUTEX_NAME = "Aurora2ControlPanelMain"
REFRESH_INTERVAL_MS = 1200
INLINE_PREVIEW_MAX_WIDTH = 1120
INLINE_PREVIEW_MAX_HEIGHT = 560
INLINE_PREVIEW_MIN_WIDTH = 320
INLINE_PREVIEW_MIN_HEIGHT = 220
SCREENSHOT_LIST_CACHE_TTL_SECONDS = 3.0
SCREENSHOT_LIST_DEFAULT_LIMIT = 24
THUMBNAIL_CACHE_MAX_ENTRIES = 96
THUMBNAIL_SIZE = (140, 88)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
SCREENSHOT_LIST_CACHE = {}

GAME_PROFILES = ["firered", "blue"]
CONTROL_PANEL_REGISTERED_NON_SCHEDULER_KEYS = (
    "auth.mode",
    "runtime.live",
    "runtime.execution",
    "runtime.action",
    "game.profile",
    "model.text",
    "model.vision",
    "model.reasoning",
    "model.transport",
    "inference.reasoning_effort",
    "inference.verbosity",
    "inference.temperature",
    "capture.screenshot_interval",
    "capture.demand_enabled",
    "vision.image_detail",
    "runtime.live_init",
)
CONTROL_PANEL_SCHEDULER_LEAF_KEYS = (
    "scheduler.mode",
    "scheduler.heartbeat_seconds",
    "scheduler.min_gap_seconds",
    "scheduler.capture_wake_enabled",
    "scheduler.capture_wake_debounce_seconds",
    "scheduler.post_action_settle_seconds",
)
CONTROL_PANEL_SETTINGS_SUCCESS_STATUSES = {
    "previewed",
    "applied",
    "applied_noop",
    "rolled_back",
}

MODELS = [
    "gpt-6.1-sol",
    "gpt-6.1-terra",
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
]
AUTH_MODES = ["api_key", "openai_chatgpt", "codex_oauth", "auto"]
EXECUTION_MODES = ["safe", "assist", "auto"]
ACTION_MODES = ["gb", "pyag", "none"]
EFFORTS = ["", "minimal", "none", "low", "medium", "high", "xhigh", "max"]
VERBOSITIES = ["", "low", "medium", "high"]
SUMMARY_MODES = ["", "auto", "none", "brief", "detailed"]
PENDING_QUEUE_MODES = ["normal", "replace", "insert"]
TURN_SCHEDULER_MODES = ["hybrid", "event", "per_capture"]
TURN_SCHEDULER_PROFILE_NAMES = ["balanced", "responsive", "conservative", "legacy", "custom"]
RETRIEVAL_DISTRIBUTION_SHAPES = ["balanced", "gaussian", "geometric", "exponential"]
EPISODIC_PROMOTION_TARGETS = [
    "notes",
    "journal",
    "recent_context",
    "pinned_immediate",
    "pinned_short_term",
    "apriority_goal",
    "overarching_goal",
]
TURN_SCHEDULER_PROFILE_DEFAULTS = {
    "balanced": {
        "mode": "hybrid",
        "heartbeat_seconds": "2.25",
        "min_gap_seconds": "0.55",
        "capture_wake_enabled": True,
        "capture_wake_debounce_seconds": "0.90",
        "post_action_settle_seconds": "0.55",
        "description": "recommended default for gameplay and desktop observation",
    },
    "responsive": {
        "mode": "hybrid",
        "heartbeat_seconds": "1.50",
        "min_gap_seconds": "0.25",
        "capture_wake_enabled": True,
        "capture_wake_debounce_seconds": "0.35",
        "post_action_settle_seconds": "0.25",
        "description": "fastest loop for active debugging and hands-on testing",
    },
    "conservative": {
        "mode": "event",
        "heartbeat_seconds": "3.50",
        "min_gap_seconds": "0.95",
        "capture_wake_enabled": False,
        "capture_wake_debounce_seconds": "1.35",
        "post_action_settle_seconds": "0.85",
        "description": "lowest-chatter mode; best when false urgency is a problem",
    },
    "legacy": {
        "mode": "per_capture",
        "heartbeat_seconds": "2.00",
        "min_gap_seconds": "0.00",
        "capture_wake_enabled": True,
        "capture_wake_debounce_seconds": "0.00",
        "post_action_settle_seconds": "0.25",
        "description": "closest to the older screenshot conveyor behavior",
    },
}
PENDING_RISKS = ["all", "low", "medium", "high"]
PENDING_CATEGORIES = ["all", "memory", "desktop_action", "runtime", "persistence", "other"]
CHAT_HEAD_SEND_ANIMATIONS = ["pulse", "none"]

MODEL_PRESETS = {
    "Frontier 5.5": {
        "text": "gpt-5.5",
        "vision": "gpt-5.5",
        "reasoning": "gpt-5.5",
        "effort": "none",
        "battle_effort": "low",
        "temperature": "0.0",
    },
    "Flagship 5.4": {
        "text": "gpt-5.4",
        "vision": "gpt-5.4",
        "reasoning": "gpt-5.4",
        "effort": "none",
        "battle_effort": "low",
        "temperature": "0.0",
    },
    "Budget 5.4 Mini": {
        "text": "gpt-5.4-mini",
        "vision": "gpt-5.4-mini",
        "reasoning": "gpt-5.4-mini",
        "effort": "none",
        "battle_effort": "low",
        "temperature": "0.0",
    },
    "Balanced 4o": {
        "text": "gpt-4o",
        "vision": "gpt-4o",
        "reasoning": "gpt-4o",
        "effort": "none",
        "battle_effort": "low",
        "temperature": "0.0",
    },
    "Cheap Mini": {
        "text": "gpt-4o-mini",
        "vision": "gpt-4o-mini",
        "reasoning": "gpt-4o-mini",
        "effort": "none",
        "battle_effort": "low",
        "temperature": "0.0",
    },
}
MODEL_PRESET_HINTS = {
    "Frontier 5.5": "highest-cost frontier preset for unusually hard planning/debugging turns",
    "Flagship 5.4": "default balance for normal hard Aurora work",
    "Budget 5.4 Mini": "lower-cost preset for sanity checks, smoke turns, and routine probes",
    "Balanced 4o": "legacy balanced fallback",
    "Cheap Mini": "legacy low-cost fallback",
}
MODEL_PRESET_GUIDE_TEXT = (
    "Preset guide: Flagship 5.4 is the default; Budget 5.4 Mini or Cheap Mini are for cheap checks; "
    "Frontier 5.5 is for hard cases; current presets are stateless; stateful profiles are explicit in Model Status."
)
STATEFUL_MODEL_PRESET_BUTTONS = {
    "Stateless": "stateless-default",
    "Responses Link": "responses-link-preview",
    "Conversation": "conversation-preview",
}

OVERLAY_PRESETS = {
    "Minimal": {
        "tile_grid": False,
        "cursor_label": False,
        "keypoint_grid": False,
        "status_overlay": True,
    },
    "Navigation": {
        "tile_grid": True,
        "cursor_label": True,
        "keypoint_grid": True,
        "status_overlay": True,
    },
    "Debug": {
        "tile_grid": True,
        "cursor_label": True,
        "keypoint_grid": True,
        "status_overlay": True,
    },
}

OPERATOR_PROFILES = {
    "Safe Offline": {
        "live": False,
        "execution": "safe",
        "action": "none",
        "model_preset": "Budget 5.4 Mini",
        "overlay_preset": "Minimal",
        "reasoning_effort": "none",
        "battle_effort": "low",
        "review_effort": "low",
        "critique_effort": "low",
        "verbosity": "low",
        "review_verbosity": "low",
        "battle_verbosity": "low",
        "critique_verbosity": "low",
        "summary_mode": "none",
        "auto_dynamic_inference": False,
        "turn_scheduler_profile": "conservative",
        "screenshot_interval": "30",
        "demand_capture_enabled": False,
        "pending_queue_mode": "normal",
        "command_drip_retention": "3",
        "command_drip_lookahead": "1",
        "live_init": False,
        "sound_effects": False,
        "time_logging": False,
        "chat_log_echo": False,
        "image_detail": "low",
        "latest_image_detail": "low",
        "high_detail": "0",
        "max_images_in_history": "3",
        "extra_commands": ["CLEAR_NEXT_INFERENCE()"],
        "hint": "offline baseline for cleanup, local UI checks, and low-cost setup",
    },
    "Safe Live Model": {
        "live": True,
        "execution": "safe",
        "action": "none",
        "model_preset": "Flagship 5.4",
        "overlay_preset": "Minimal",
        "reasoning_effort": "none",
        "battle_effort": "low",
        "review_effort": "low",
        "critique_effort": "medium",
        "verbosity": "medium",
        "summary_mode": "auto",
        "auto_dynamic_inference": True,
        "turn_scheduler_profile": "balanced",
        "screenshot_interval": "15",
        "demand_capture_enabled": True,
        "pending_queue_mode": "normal",
        "command_drip_retention": "5",
        "command_drip_lookahead": "3",
        "live_init": False,
        "image_detail": "low",
        "latest_image_detail": "low",
        "max_images_in_history": "5",
        "extra_commands": ["CLEAR_NEXT_INFERENCE()"],
        "hint": "live model observation without desktop/game action execution",
    },
    "Cheap Visual Test": {
        "live": True,
        "execution": "safe",
        "action": "none",
        "model_preset": "Budget 5.4 Mini",
        "overlay_preset": "Minimal",
        "reasoning_effort": "none",
        "battle_effort": "low",
        "review_effort": "low",
        "critique_effort": "low",
        "verbosity": "low",
        "summary_mode": "none",
        "auto_dynamic_inference": False,
        "turn_scheduler_profile": "balanced",
        "screenshot_interval": "10",
        "demand_capture_enabled": True,
        "pending_queue_mode": "normal",
        "command_drip_retention": "3",
        "command_drip_lookahead": "1",
        "image_detail": "low",
        "latest_image_detail": "low",
        "max_images_in_history": "3",
        "extra_commands": ["CLEAR_NEXT_INFERENCE()"],
        "hint": "cheap live visual sanity check with no action execution",
    },
    "Gameplay Test": {
        "live": False,
        "execution": "assist",
        "action": "gb",
        "model_preset": "Budget 5.4 Mini",
        "overlay_preset": "Navigation",
        "reasoning_effort": "none",
        "battle_effort": "low",
        "review_effort": "low",
        "critique_effort": "medium",
        "verbosity": "low",
        "summary_mode": "auto",
        "auto_dynamic_inference": True,
        "turn_scheduler_profile": "responsive",
        "screenshot_interval": "2",
        "demand_capture_enabled": True,
        "pending_queue_mode": "normal",
        "command_drip_retention": "5",
        "command_drip_lookahead": "2",
        "image_detail": "low",
        "latest_image_detail": "low",
        "max_images_in_history": "5",
        "hint": "offline supervised gameplay/input test posture",
    },
    "Minimal Cost": {
        "live": False,
        "execution": "safe",
        "action": "none",
        "model_preset": "Cheap Mini",
        "overlay_preset": "Minimal",
        "reasoning_effort": "none",
        "battle_effort": "low",
        "review_effort": "low",
        "critique_effort": "low",
        "verbosity": "low",
        "summary_mode": "none",
        "auto_dynamic_inference": False,
        "turn_scheduler_profile": "conservative",
        "screenshot_interval": "45",
        "demand_capture_enabled": False,
        "pending_queue_mode": "normal",
        "command_drip_retention": "2",
        "command_drip_lookahead": "1",
        "live_init": False,
        "sound_effects": False,
        "time_logging": False,
        "chat_log_echo": False,
        "image_detail": "low",
        "latest_image_detail": "low",
        "max_images_in_history": "2",
        "episodic_planning_mode": "off",
        "episodic_backend": "off",
        "extra_commands": ["CLEAR_NEXT_INFERENCE()"],
        "hint": "quietest low-cost posture for parking or cheap UI checks",
    },
    "Full Capability": {
        "live": False,
        "execution": "assist",
        "action": "gb",
        "model_preset": "Flagship 5.4",
        "overlay_preset": "Debug",
        "reasoning_effort": "low",
        "battle_effort": "medium",
        "review_effort": "medium",
        "critique_effort": "high",
        "verbosity": "medium",
        "review_verbosity": "medium",
        "battle_verbosity": "medium",
        "critique_verbosity": "high",
        "summary_mode": "auto",
        "auto_dynamic_inference": True,
        "turn_scheduler_profile": "balanced",
        "screenshot_interval": "5",
        "demand_capture_enabled": True,
        "pending_queue_mode": "normal",
        "command_drip_retention": "7",
        "command_drip_lookahead": "3",
        "live_init": True,
        "time_logging": True,
        "chat_log_echo": True,
        "image_detail": "auto",
        "latest_image_detail": "auto",
        "max_images_in_history": "8",
        "episodic_planning_mode": "review_critique",
        "episodic_backend": "auto",
        "confirm": "Full Capability enables richer context, live-init loading, timing logs, and a more capable model posture. Apply it?",
        "hint": "advanced full-feature setup; still leaves live mode off until the operator starts it",
    },
    "Inspect": {
        "live": False,
        "execution": "safe",
        "action": "gb",
        "model_preset": "Flagship 5.4",
        "overlay_preset": "Navigation",
    },
    "Assist Live": {
        "live": True,
        "execution": "assist",
        "action": "gb",
        "model_preset": "Flagship 5.4",
        "overlay_preset": "Navigation",
    },
    "Battle": {
        "live": True,
        "execution": "assist",
        "action": "gb",
        "model_preset": "Flagship 5.4",
        "overlay_preset": "Debug",
        "reasoning_effort": "low",
        "battle_effort": "medium",
    },
}
RECOVERY_PROFILE_NAMES = [
    "Safe Offline",
    "Safe Live Model",
    "Cheap Visual Test",
    "Gameplay Test",
    "Minimal Cost",
    "Full Capability",
]

SETTING_SAFETY_CLASS_ORDER = [
    "recovery-critical",
    "basic",
    "advanced",
    "risky",
    "hidden-by-default",
]
SETTING_SAFETY_CLASS_LABELS = {
    "recovery-critical": "Recovery-critical",
    "basic": "Basic",
    "advanced": "Advanced",
    "risky": "Risky",
    "hidden-by-default": "Hidden-by-default candidate",
}
SETTING_SAFETY_INVENTORY = [
    {
        "name": "Live mode",
        "class": "recovery-critical",
        "surface": "Header quick actions; Runtime Controls",
        "state_path": ("modes", "live"),
        "commands": "SET_LIVE_MODE(on|off)",
        "novice": "Keep off while setting up, cleaning up, or changing several settings.",
        "intermediate": "Turn on only after auth, models, capture, and action mode look intentional.",
    },
    {
        "name": "Execution mode",
        "class": "recovery-critical",
        "surface": "Header quick actions; Runtime Controls",
        "state_path": ("modes", "execution"),
        "commands": "SET_EXECUTION_MODE(safe|assist|auto)",
        "novice": "Safe is the least surprising mode; Assist is the usual supervised mode.",
        "intermediate": "Auto raises the blast radius because approved actions can execute with less friction.",
    },
    {
        "name": "Action mode",
        "class": "recovery-critical",
        "surface": "Header quick actions; Runtime Controls",
        "state_path": ("modes", "action"),
        "commands": "SET_ACTION_MODE(gb|pyag|none), GB_MODE(), PYAG_MODE()",
        "novice": "Use none when you only want observation or chat; GB is gameplay-specific.",
        "intermediate": "PYAG points at desktop automation and deserves a visible pause before live work.",
    },
    {
        "name": "Auth mode",
        "class": "advanced",
        "surface": "Access & Safety; Models & Modes",
        "state_path": ("modes", "auth"),
        "commands": "SET_AUTH_MODE(api_key|openai_chatgpt|codex_oauth|auto), SHOW_AUTH()",
        "novice": "If auth looks unresolved, fix that before judging model behavior.",
        "intermediate": "Use SHOW_AUTH() when live turns silently do not start.",
    },
    {
        "name": "Operator passcode",
        "class": "recovery-critical",
        "surface": "Access & Safety",
        "state_paths": (("required", ("security", "passcode_required")), ("authorized", ("security", "authorized"))),
        "commands": "SET_OPERATOR_PASSCODE(...), SET_OPERATOR_PASSCODE_REQUIRED(...), AUTHORIZE_OPERATOR(...), LOCK_OPERATOR_ACCESS()",
        "novice": "Use this when external control should be fenced off.",
        "intermediate": "Passcode state explains why external raw commands may be rejected.",
    },
    {
        "name": "Runtime locks",
        "class": "recovery-critical",
        "surface": "Locks summary; raw commands",
        "state_path": ("locks",),
        "commands": "LOCK_SETTING(...), UNLOCK_SETTING(...), SHOW_LOCKS()",
        "novice": "Locks are why a visible setting may refuse to change.",
        "intermediate": "Use SHOW_LOCKS() before debugging a setting that seems ignored.",
    },
    {
        "name": "Known-good recovery profiles",
        "class": "recovery-critical",
        "surface": "Recovery tab; Operator Profiles",
        "state_path": (),
        "value_hint": "profile buttons available",
        "commands": "Safe Offline, Safe Live Model, Cheap Visual Test, Gameplay Test, Minimal Cost, Full Capability",
        "novice": "Use these when the cockpit feels confusing and you want a coherent baseline.",
        "intermediate": "Profiles are visible settings batches; they still route through normal Aurora commands and locks.",
    },
    {
        "name": "Model presets",
        "class": "basic",
        "surface": "Models, Presets & Next Turn",
        "state_path": ("model_status", "text_model"),
        "commands": "Control Panel preset buttons",
        "novice": "Pick Budget/Mini for cheap checks and Flagship 5.4 for normal serious work.",
        "intermediate": "Presets are stateless bundles; they do not change transport or memory policy.",
    },
    {
        "name": "Active model family",
        "class": "advanced",
        "surface": "Modes & Models; Model Status",
        "state_paths": (
            ("text", ("models", "text")),
            ("vision", ("models", "vision")),
            ("reasoning", ("models", "reasoning")),
        ),
        "commands": "SET_TEXT_MODEL(...), SET_VISION_MODEL(...), SET_REASONING_MODEL(...), SHOW_MODEL_STATUS()",
        "novice": "Changing models can change cost, vision behavior, and supported reasoning values.",
        "intermediate": "Check model status after changing families; capabilities are model-specific.",
    },
    {
        "name": "Session reasoning defaults",
        "class": "advanced",
        "surface": "Modes & Models",
        "state_paths": (
            ("session", ("models", "reasoning_effort")),
            ("battle", ("models", "battle_reasoning_effort")),
            ("review", ("models", "review_reasoning_effort")),
            ("critique", ("models", "critique_reasoning_effort")),
        ),
        "commands": "SET_SESSION_REASONING_EFFORT(...), SET_BATTLE_REASONING_EFFORT(...), SET_REVIEW_REASONING_EFFORT(...), SET_CRITIQUE_REASONING_EFFORT(...)",
        "novice": "Leave these low/none unless you know which turn type is active.",
        "intermediate": "Battle/review/critique defaults can override what a single session-effort row seems to imply.",
    },
    {
        "name": "Next-turn inference override",
        "class": "risky",
        "surface": "Models, Presets & Next Turn",
        "state_path": ("planning", "next_inference"),
        "commands": "SET_NEXT_REASONING_EFFORT(...), SET_NEXT_INFERENCE(...), CLEAR_NEXT_INFERENCE()",
        "novice": "A queued next-turn setting is easy to forget; clear it after the test.",
        "intermediate": "It applies once, then clears; it does not reorder pending commands.",
    },
    {
        "name": "Stateful preview profiles",
        "class": "hidden-by-default",
        "surface": "Stateful Profiles row; Model Status",
        "state_path": ("model_status", "stateful_preset_family", "active_profile"),
        "commands": "SET_STATEFUL_MODEL_PRESET(...), SHOW_STATEFUL_MODEL_PRESETS()",
        "novice": "These are previews only; they should not be treated as real memory transport yet.",
        "intermediate": "Use only when comparing future Responses/conversation transport plans.",
    },
    {
        "name": "Model temperature",
        "class": "advanced",
        "surface": "Turn Timing",
        "state_path": ("models", "temperature"),
        "commands": "SET_TEMPERATURE(...)",
        "novice": "Zero is the least surprising default.",
        "intermediate": "Raise only for deliberate exploration, not validation.",
    },
    {
        "name": "Scheduler profile",
        "class": "basic",
        "surface": "Turn Timing",
        "state_path": ("scheduler", "profile"),
        "commands": "SET_TURN_SCHEDULER_PROFILE(...), SHOW_TURN_SCHEDULER_PROFILES()",
        "novice": "Balanced is the normal default; Conservative is calmer.",
        "intermediate": "Use Responsive only when actively watching a fast test.",
    },
    {
        "name": "Scheduler raw timing",
        "class": "advanced",
        "surface": "Turn Timing",
        "state_paths": (
            ("mode", ("scheduler", "mode")),
            ("heartbeat", ("scheduler", "heartbeat_seconds")),
            ("min_gap", ("scheduler", "min_gap_seconds")),
            ("debounce", ("scheduler", "capture_wake_debounce_seconds")),
        ),
        "commands": "SET_TURN_SCHEDULER_MODE(...), SET_TURN_HEARTBEAT_SECONDS(...), SET_TURN_MIN_GAP_SECONDS(...), SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS(...)",
        "novice": "Prefer named profiles over tuning these directly.",
        "intermediate": "Raw timing changes can look like model bugs when the real issue is wake cadence.",
    },
    {
        "name": "Screenshot interval",
        "class": "risky",
        "surface": "Turn Timing",
        "state_path": ("modes", "screenshot_interval"),
        "commands": "SET_SCREENSHOT_INTERVAL(...)",
        "novice": "Very fast capture can make the app feel hot or laggy.",
        "intermediate": "Capture cadence and model-turn cadence are separate but still interact through wakes.",
    },
    {
        "name": "Demand capture",
        "class": "advanced",
        "surface": "Turn Timing",
        "state_paths": (
            ("enabled", ("scheduler", "demand_capture_enabled")),
            ("pending", ("scheduler", "demand_capture_pending")),
        ),
        "commands": "SET_DEMAND_CAPTURE(...), REQUEST_SCREENSHOT_CAPTURE(...)",
        "novice": "This is for asking Aurora to look again after a command or screen change.",
        "intermediate": "Good for validation, but pending captures can create confusing next-action cues.",
    },
    {
        "name": "Pending queue mode",
        "class": "risky",
        "surface": "Command Queue; Pending tab",
        "state_path": ("planning", "pending_queue_mode"),
        "commands": "SET_PENDING_QUEUE_MODE(normal|insert|replace)",
        "novice": "Normal is safest; replace/override can drop pending candidates.",
        "intermediate": "Insert claims the next slot and defers later pending rows.",
    },
    {
        "name": "Command drip display",
        "class": "advanced",
        "surface": "Command Queue; Command Drip tab",
        "state_paths": (
            ("retention", ("planning", "command_drip_retention_turns")),
            ("lookahead", ("planning", "command_drip_lookahead_turns")),
        ),
        "commands": "SET_COMMAND_DRIP_RETENTION(...), SET_COMMAND_DRIP_LOOKAHEAD(...)",
        "novice": "This is visibility into candidates, not approval.",
        "intermediate": "Longer retention helps debugging but adds reading load.",
    },
    {
        "name": "Pending approvals and clears",
        "class": "recovery-critical",
        "surface": "Pending tab",
        "state_path": ("pending_commands",),
        "commands": "APPROVE_PENDING(...), CLEAR_PENDING_COMMANDS(...)",
        "novice": "Clear removes without running; Approve runs through Aurora's normal command path.",
        "intermediate": "Filters and selection scope matter before approving or clearing.",
    },
    {
        "name": "Advanced message visibility",
        "class": "advanced",
        "surface": "Advanced Context",
        "state_paths": (
            ("user_text", ("advanced", "show_user_text")),
            ("ai_text", ("advanced", "show_ai_text")),
            ("ai_cmds_hidden", ("advanced", "hide_ai_commands")),
            ("user_cmds_hidden", ("advanced", "hide_user_commands")),
        ),
        "commands": "SET_SHOW_USER_TEXT(...), SET_SHOW_AI_TEXT(...), SET_SHOW_AI_COMMANDS(...), SET_SHOW_USER_COMMANDS(...)",
        "novice": "These change what is displayed, not necessarily what Aurora knows.",
        "intermediate": "Useful for clutter control, but can hide evidence during debugging.",
    },
    {
        "name": "History storage and decay",
        "class": "risky",
        "surface": "Advanced Context",
        "state_paths": (
            ("unimportant", ("advanced", "enable_unimportant_messages")),
            ("important", ("advanced", "enable_important_messages")),
            ("add_umsgs", ("advanced", "add_umsgs_to_history")),
            ("add_imsgs", ("advanced", "add_imsgs_to_history")),
        ),
        "commands": "SET_UNIMPORTANT_MESSAGES(...), SET_IMPORTANT_MESSAGES(...), SET_ADD_UMSGS_TO_HISTORY(...), SET_ADD_IMSGS_TO_HISTORY(...), SET_UMSGS_DECAY_CHECK(...), SET_IMSGS_DECAY_CHECK(...)",
        "novice": "These affect what survives and decays; changing them can make memory feel inconsistent.",
        "intermediate": "Treat these as retention controls, not attention controls.",
    },
    {
        "name": "Always/input hiding",
        "class": "hidden-by-default",
        "surface": "Advanced Context",
        "state_paths": (
            ("always", ("advanced", "always_on")),
            ("hide_input", ("advanced", "hide_input")),
        ),
        "commands": "SET_ALWAYS(on|off, true|false)",
        "novice": "Leave alone unless you are deliberately changing operator-input behavior.",
        "intermediate": "This is a UI/input-mode control that can make the panel feel strange.",
    },
    {
        "name": "Image detail",
        "class": "risky",
        "surface": "Advanced Context; Next Turn",
        "state_paths": (
            ("current", ("advanced", "image_detail")),
            ("latest", ("advanced", "latest_image_detail")),
        ),
        "commands": "SET_IMAGE_DETAIL(...), SET_LATEST_IMAGE_DETAIL(...), SET_NEXT_INFERENCE(image_detail=...)",
        "novice": "low is cheapest; original/high should be used only when inspecting visual details.",
        "intermediate": "Supported detail values vary by model family; Model Status is the truth surface.",
    },
    {
        "name": "Image history limits",
        "class": "risky",
        "surface": "Advanced Context; Visual Context",
        "state_paths": (
            ("max", ("advanced", "max_images_in_history")),
            ("high_count", ("advanced", "high_detail")),
        ),
        "commands": "SET_MAX_IMAGES_IN_HISTORY(...), SET_HIGH_DETAIL(...)",
        "novice": "Retained images are not the same as images included in the next prompt.",
        "intermediate": "Compare Visual Context and Prompt Ledger before trusting model self-reports.",
    },
    {
        "name": "Live init prompt",
        "class": "advanced",
        "surface": "Modes & Models",
        "state_path": ("modes", "load_live_init_prompt"),
        "commands": "SET_LIVE_INIT(on|off)",
        "novice": "Leave off for simple local tests unless you need the full init context.",
        "intermediate": "This changes startup prompt load, not just UI wording.",
    },
    {
        "name": "Logs and feedback toggles",
        "class": "basic",
        "surface": "Modes & Models",
        "state_paths": (
            ("sound", ("modes", "sound_effects")),
            ("time_logging", ("modes", "time_logging")),
            ("chat_echo", ("modes", "chat_log_echo")),
        ),
        "commands": "SET_SOUND_EFFECTS(...), SET_TIME_LOGGING(...), SET_CHAT_LOG_ECHO(...)",
        "novice": "These mostly affect operator feedback and diagnostics.",
        "intermediate": "Time logging helps performance tests; chat echo can add visible noise.",
    },
    {
        "name": "Overlay toggles",
        "class": "basic",
        "surface": "Overlay presets; screenshots",
        "state_paths": (
            ("tile", ("overlay", "tile_grid")),
            ("cursor", ("overlay", "cursor_label")),
            ("keypoints", ("overlay", "keypoint_grid")),
            ("status", ("overlay", "status_text")),
        ),
        "commands": "SET_TILE_GRID(...), SET_CURSOR_LABEL(...), SET_KEYPOINT_GRID(...), SET_STATUS_OVERLAY(...)",
        "novice": "Navigation preset is the normal visual aid; Minimal reduces clutter.",
        "intermediate": "Old tile overlays are sighting aids, not calibrated emulator tile math.",
    },
    {
        "name": "Chat head controls",
        "class": "basic",
        "surface": "Chat Head",
        "state_paths": (
            ("topmost", ("panel", "chat_head_topmost")),
            ("opacity", ("panel", "chat_head_opacity")),
        ),
        "commands": "OPEN_CHAT_HEAD(), CLOSE_CHAT_HEAD(), SET_CHAT_HEAD_...( ... )",
        "novice": "Use Open/Close first; size and opacity are polish controls.",
        "intermediate": "Topmost can cover other windows during visual debugging.",
    },
    {
        "name": "Episodic snapshots",
        "class": "advanced",
        "surface": "Episodic Memory; Episodic tab",
        "state_paths": (
            ("enabled", ("episodic_memory", "enabled")),
            ("periodic", ("episodic_memory", "periodic_enabled")),
            ("scene", ("episodic_memory", "scene_trigger_enabled")),
        ),
        "commands": "SET_EPISODIC_MEMORY(...), SET_EPISODIC_MEMORY_PERIODIC(...), SET_EPISODIC_MEMORY_SCENE_TRIGGER(...)",
        "novice": "Snapshots preserve continuity, but they are not automatically prompt pins.",
        "intermediate": "Use SHOW_REHYDRATION_STATUS() to see whether retrieval gates are active.",
    },
    {
        "name": "Episodic embeddings",
        "class": "risky",
        "surface": "Episodic Memory; Episodic tab",
        "state_paths": (
            ("backend", ("episodic_memory", "embeddings_mode")),
            ("model", ("episodic_memory", "embedding_model")),
        ),
        "commands": "SET_EPISODIC_EMBEDDINGS(off|auto|force), SET_EPISODIC_EMBEDDING_MODEL(...)",
        "novice": "auto is safer than force; off keeps retrieval lexical-only.",
        "intermediate": "Force can turn a missing embedding path into a hard failure.",
    },
    {
        "name": "Planning assist",
        "class": "advanced",
        "surface": "Episodic Memory; Episodic tab",
        "state_paths": (
            ("mode", ("episodic_memory", "planning_assist_mode")),
            ("k", ("episodic_memory", "planning_assist_k")),
            ("cooldown", ("episodic_memory", "planning_assist_cooldown_turns")),
        ),
        "commands": "SET_EPISODIC_PLANNING_ASSIST(...), SET_EPISODIC_PLANNING_ASSIST_K(...), SET_EPISODIC_PLANNING_ASSIST_COOLDOWN(...)",
        "novice": "This injects bounded retrieval only on configured review/critique turns.",
        "intermediate": "Cooldown prevents every routine turn from becoming a memory retrieval turn.",
    },
    {
        "name": "Retrieval and promotion",
        "class": "advanced",
        "surface": "Episodic tab",
        "state_path": ("episodic_memory", "last_retrieval_count"),
        "commands": "RETRIEVAL_PULL(...), RECALL(...), PROMOTE_EPISODIC_MEMORY(...)",
        "novice": "Preview first; promotion copies a selected result into live memory.",
        "intermediate": "Promotion is explicit so retrieval does not silently become prompt inclusion.",
    },
    {
        "name": "Continuity handoff helpers",
        "class": "basic",
        "surface": "Continuity & Operator Input",
        "state_path": ("continuity", "default_handoff_filename"),
        "commands": "SAVE_HANDOFF(...), RETRIEVE_HANDOFF(...), CHECK_PREVIOUS_HANDOFF(), RECALL_PREVIOUS_SUMMARY()",
        "novice": "Use these to load or save handoff context without changing live mode.",
        "intermediate": "Treat retrieved handoff as context, not proof of current runtime state.",
    },
    {
        "name": "Scoped clear commands",
        "class": "risky",
        "surface": "Continuity & Operator Input",
        "state_path": ("memory_tiers",),
        "commands": "CLEAR_NONPIN(), CLEAR_INIT(), CLEAR_PIN(), CLEAR_HANDOFF(), CLEAR_RECENT_CONTEXT(), CLEAR_ROUTE_STATE()",
        "novice": "These remove context; use only when you know what lane you are clearing.",
        "intermediate": "Prefer scoped clears over broad resets, but record why in notes when it matters.",
    },
    {
        "name": "Raw command entry",
        "class": "hidden-by-default",
        "surface": "Continuity & Operator Input; Raw State",
        "state_path": ("queue_bridge",),
        "commands": "Any supported Aurora command",
        "novice": "Use named buttons first; raw commands are for precise operator/debug work.",
        "intermediate": "Raw commands can wake turns, mutate state, or queue pending approvals.",
    },
]

DEFAULT_RUNTIME_ACTIVATION_PROFILE = {
    "execution": "assist",
    "action": "gb",
    "text_model": "gpt-6.1-sol",
    "vision_model": "gpt-6.1-sol",
    "reasoning_model": "gpt-6-astra",
    "reasoning_effort": "low",
    "verbosity": "low",
    "screenshot_interval": "15",
}

BG = "#0b1220"
PANEL = "#111827"
PANEL_2 = "#172033"
TEXT = "#e5eefc"
MUTED = "#9fb0c7"
ACCENT = "#60a5fa"
ACCENT_2 = "#22c55e"
WARN = "#f59e0b"
BORDER = "#243247"
BANNER_TICK_MS = 70
BANNER_STEP_PX = 2
BANNER_GAP_PX = 80
CHAT_HEAD_BG = "#0f172a"
CHAT_HEAD_FIELD = "#111827"
CHAT_HEAD_BORDER = "#355173"
CHAT_HEAD_TOGGLE_FILL = "#162033"
CHAT_HEAD_TOGGLE_FILL_ACTIVE = "#1e3a5f"
CHAT_HEAD_HISTORY_ACCENT = "#38bdf8"
CHAT_HEAD_CLOSE = "#ef4444"
CHAT_HEAD_FIELD_SENT = "#1d4ed8"
CHAT_HEAD_TEXT = "#e5eefc"
CHAT_HEAD_MUTED = "#9fb0c7"
RUNTIME_ICON_FRAME_MS = 110
ERROR_ALREADY_EXISTS = 183
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
if KERNEL32 is not None:
    KERNEL32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    KERNEL32.CreateMutexW.restype = wintypes.HANDLE
    KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    KERNEL32.OpenProcess.restype = wintypes.HANDLE
    KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    KERNEL32.CloseHandle.restype = wintypes.BOOL

HELP_TEXT = """[Overview]
Aurora 2 Control Panel is a separate operator UI process. It reads runtime state from
aurora_control_panel_state.json and sends operator commands through aurora_external_inbox.jsonl.
The default surface is compact. Use Chat / Commands / Memory / Episodic / Images tabs for deeper views.

[Recovery / Settings Safety]
- Recovery is a safe home base plus a read-only map of user-facing settings and toggles.
- The Recovery Home row summarizes current risk, suggested known-good profiles, restore confidence, and diagnostic links.
- The map classifies controls as basic, advanced, risky, recovery-critical, or hidden-by-default candidates.
- It names the novice interpretation, intermediate caution, and technician command path for each control.
- Known-good recovery profiles include Safe Offline, Safe Live Model, Cheap Visual Test, Gameplay Test, Minimal Cost, and Full Capability.
- The same tab summarizes what looks weird right now: live/action posture, auth, queued overrides, locks, queues, demand capture, image detail, retained-vs-included image posture, stateful profile previews, high-cost models, and monitor status.
- Recovery also shows current differences from system/personal defaults and provides confirmed apply/save controls for those baselines.

[Screenshot Viewer]
- Double-click a screenshot preview to open the popout viewer.
- In the popout, use Fit to resize to the window, 1:1 for actual pixels, and Close or Esc to return.
- Double-click inside the popout image to toggle between Fit and 1:1.
- Click the left edge of the preview for previous and the right edge for next. Left/Right arrow keys also navigate.
- Screenshots tab shows recent captures from disk.
- Images In Memory shows only retained visual-memory entries still carried in Aurora state.

[Runtime Modes]
- live_mode: whether Aurora will send model turns.
- execution_mode=safe|assist|auto: controls whether assistant commands are held or executed.
- action_mode=gb|pyag|none: controls how unprefixed action commands resolve.
- locks: locked settings reject changes from the UI and raw operator commands.

[Model Management]
- The model comboboxes show the current built-in and custom Aurora catalog.
- Add Model validates an exact model id with a short chat/completions call before saving it.
- Remove Model only removes custom models; built-in Aurora models stay available.
- Current Model Status shows the active text/vision/reasoning models, effort defaults, verbosity, next-turn plan, and cadence heuristics.
- Stateful preset profiles remain metadata. The separate Transport setting selects Chat Completions or opt-in Astra Responses.
- Stateful profile buttons send SET_STATEFUL_MODEL_PRESET(...); those preview profiles do not select Transport.
- SET_MODEL_TRANSPORT(responses) requires API-key auth and gpt-6-astra for every active model role. It does not enable Live mode.
- RESET_RESPONSES_SESSION() clears local continuation IDs between requests; no remote-history deletion or request replay occurs.
- Efforts are model-specific. Astra supports low/medium/high/xhigh/max; Model Status shows each profile's supported set.
- Verbosity is supported for GPT-5 and Astra; transport maps the appropriate request field.
- Image detail allows low/high/auto/original; original is only native on newer GPT-5.4+ style models and is downgraded to high otherwise.
- reasoning.summary is shown as metadata only today; Aurora does not currently send it on the chat/completions path.
- Dynamic inference planning can escalate the next turn based on battle risk, blocked progress, review cadence, critique cadence, or an explicit queued next-turn plan.
- Queue lane shorthand: pending planning holds proposed commands, next-turn override changes one model turn, and observation wake requests captures/follow-up timing.
- Use the Defaults controls to save a personal baseline and quickly roll back to Aurora's built-in system defaults.
- Security: optional external-operator passcode protection gates privileged raw commands coming from the panel/email bridge. Use Set / Unlock / Lock / Clear in the left pane.
- Passcode-bearing commands are masked as ******* in logs/history by default. Use the Show Raw Cmds toggle only when you explicitly want raw passcode commands visible.

[Common Operator Commands]
- SHOW_RUNTIME()
- SHOW_RUNTIME_HEALTH()
- SHOW_OPERATOR_RISK_SUMMARY()
- SHOW_COMPANION_CONTRACT_READINESS()
- SHOW_COMPANION_PROTOCOL_CONTRACT()
- SHOW_COMPANION_RECEIPT_AUDIT()
- SHOW_COMPANION_CONTRACT_CLOSURE()
- RUN_COMPANION_CONTRACT_CLOSURE_CHECK()
- SHOW_AUTH()
- SHOW_LOCKS()
- SHOW_SECURITY()
- SHOW_OVERLAY()
- OPEN_CHAT_HEAD()
- CLOSE_CHAT_HEAD()
- TOGGLE_CHAT_HEAD()
- SHOW_CHAT_HEAD()
- SET_CHAT_HEAD_OPACITY(0.87)
- SET_CHAT_HEAD_TOPMOST(on|off)
- SET_CHAT_HEAD_STRIP_SIZE(1000,100)
- SET_CHAT_HEAD_HISTORY_SIZE(420,620)
- SET_CHAT_HEAD_SEND_ANIMATION(pulse|none)
- SET_CHAT_HEAD_SEND_ANIMATION_SECONDS(0.75)
- SET_LIVE_MODE(on|off)
- SET_EXECUTION_MODE(safe|assist|auto)
- SET_ACTION_MODE(gb|pyag|none)
- SET_TEXT_MODEL(name)
- SET_VISION_MODEL(name)
- SET_REASONING_MODEL(name)
- SET_MODEL_VERBOSITY(low|medium|high)
- SET_REVIEW_VERBOSITY(low|medium|high)
- SET_BATTLE_VERBOSITY(low|medium|high)
- SET_CRITIQUE_VERBOSITY(low|medium|high)
- SET_NEXT_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max, optional_note)
- SET_SESSION_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)
- SET_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max) [legacy alias for session/default]
- SET_BATTLE_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)
- SET_REVIEW_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)
- SET_CRITIQUE_REASONING_EFFORT(minimal|none|low|medium|high|xhigh|max)
- SET_REASONING_SUMMARY_MODE(auto|none|brief|detailed)
- SET_AUTO_DYNAMIC_INFERENCE(on|off)
- SET_TURN_SCHEDULER_MODE(per_capture|event|hybrid)
- SET_TURN_SCHEDULER_PROFILE(balanced|responsive|conservative|legacy)
- SET_TURN_HEARTBEAT_SECONDS(seconds)
- SET_TURN_MIN_GAP_SECONDS(seconds)
- SET_TURN_CAPTURE_WAKE(on|off)
- SET_TURN_CAPTURE_WAKE_DEBOUNCE_SECONDS(seconds)
- SET_TURN_POST_ACTION_SETTLE_SECONDS(seconds)
- SHOW_TURN_SCHEDULER()
- SHOW_TURN_SCHEDULER_PROFILES()
- SET_DEMAND_CAPTURE(on|off)
- REQUEST_SCREENSHOT_CAPTURE(optional_reason, optional_settle_seconds)
- SET_REVIEW_TURN_INTERVAL(turns)
- SET_CRITIQUE_TURN_INTERVAL(turns)
- SET_PENDING_QUEUE_MODE(normal|replace|insert)
- SET_COMMAND_DRIP_RETENTION(turns)
- SET_COMMAND_DRIP_LOOKAHEAD(turns)
- SET_COMMAND_DRIP_SHOW_VARIANTS(on|off)
- SET_COMMAND_DRIP_SHOW_LIKELY_DROPPED(on|off)
- SET_NEXT_INFERENCE(reasoning_effort=...; verbosity=...; summary_mode=...; note=...)
- CLEAR_NEXT_INFERENCE()
- SHOW_NEXT_INFERENCE()
- SHOW_COMMAND_DRIP()
- QUEUE_PENDING(command)
- INSERT_PENDING(command)
- REPLACE_PENDING(command)
- OVERRIDE_PENDING(command)
- SAVE_PERSONAL_DEFAULTS()
- APPLY_PERSONAL_DEFAULTS()
- APPLY_SYSTEM_DEFAULTS()
- SHOW_DEFAULT_PROFILES()
- SET_TEMPERATURE(0.0)
- SET_SCREENSHOT_INTERVAL(0.12)
- SHOW_MODELS()
- SHOW_MODEL_STATUS()
- ADD_MODEL(name)
- REMOVE_MODEL(name)
- SET_OPERATOR_PASSCODE(passcode)
- SET_OPERATOR_PASSCODE_REQUIRED(on|off)
- SET_PASSCODE_COMMAND_VISIBILITY(on|off)
- AUTHORIZE_OPERATOR(passcode)
- LOCK_OPERATOR_ACCESS()
- CLEAR_OPERATOR_PASSCODE()
- SET_LIVE_INIT(on|off)
- SET_SOUND_EFFECTS(on|off)
- SET_TIME_LOGGING(on|off)
- SET_CHAT_LOG_ECHO(on|off)
- SET_TILE_GRID(on|off)
- SET_CURSOR_LABEL(on|off)
- SET_KEYPOINT_GRID(on|off)
- SET_STATUS_OVERLAY(on|off)
- LOGIN_CODEX_OAUTH()
- LAUNCH_CONTROL_PANEL()
- SET_EPISODIC_MEMORY(on|off)
- SET_EPISODIC_MEMORY_INTERVAL(seconds)
- SET_EPISODIC_MEMORY_PERIODIC(on|off)
- SET_EPISODIC_MEMORY_SCENE_TRIGGER(on|off)
- SET_EPISODIC_EMBEDDINGS(off|auto|force)
- SET_EPISODIC_PLANNING_ASSIST(off|review|critique|review_critique)
- SET_EPISODIC_PLANNING_ASSIST_K(k)
- SET_EPISODIC_PLANNING_ASSIST_COOLDOWN(turns)
- SET_EPISODIC_EMBEDDING_MODEL(name)
- SHOW_EPISODIC_MEMORY_STATUS()
- WRITE_EPISODIC_SNAPSHOT("reason", "tag1;tag2")
- LIST_EPISODIC_SNAPSHOTS(optional_limit)
- SEARCH_EPISODIC_SNAPSHOTS("query", optional_limit)
- RETRIEVAL_PULL(query="...", k=4, semantic_backend=auto, embedding_model="text-embedding-3-small", time_weight=0.5, semantic_weight=0.5, distribution_shape=balanced)
- RECALL(query, optional_k)  [shorthand; expands to RETRIEVAL_PULL(...)]
- MEM(query, optional_k)  [alias for RECALL(...)]
- PROMOTE_EPISODIC_MEMORY(item_index, target, optional_prefix)
- SHOW_CONTEXT_MARKS()  [writable metadata policy/store for prompt/local/search/retention marks]
- MARK_CONTEXT(target, mark_type=..., note=..., approval=draft|requested|approved|rejected)  [metadata-only context mark]
- MARK_TURN(target, mark_type=..., note=..., approval=...)  [metadata-only turn mark]
- MARK_REPLY(target, mark_type=..., note=..., approval=...)  [metadata-only reply mark]
- CLEAR_CONTEXT_MARK(mark_id|target|all, optional mark_type=...)  [clear active mark, keep audit]
- MARK_DO_NOT_INCLUDE(target, note=...)  [metadata-only do-not-include/drop mark; keeps evidence]
- CLEAR_DO_NOT_INCLUDE(mark_id|target|all)  [clear active drop mark, keep audit]
- SHOW_DO_NOT_INCLUDE()  [preview do-not-include/drop marks]
- SHOW_AGENTS()  [metadata-only Agent Registry / History ACL status]
- SHOW_AGENT_HISTORY_ACLS()  [per-agent history ACL preview and audit-log path readiness]
- SHOW_AGENT_SUGGESTION_ROUTES()  [metadata-only sub-agent suggestion route and policy-tag preview]
- SHOW_AGENT_SUGGESTIONS()  [append-only sub-agent suggestion audit rows]
- SHOW_AGENT_TASKS()  [append-only sub-agent task packets and review states]
- SHOW_AGENT_PENDING_GATE()  [task/suggestion review links and closed Pending gate preview]
- SHOW_AGENT_PENDING_INSERT_CHECKLIST()  [no-exec Pending insertion checklist]
- RUN_AGENT_PENDING_INSERT_DRY_RUN()  [dry-run only; leaves executable Pending queue unchanged]
- INSERT_AGENT_PENDING_COMMAND(review_id, confirm=dry_run:<id>)  [exact-confirm insert into held Pending; still needs APPROVE_PENDING]
- RUN_AGENT_HELPER_CLOSURE_CHECK()  [prove metadata-first sub-agent helper closure/readiness]
- SHOW_AGENT_HELPER_CLOSURE()  [display helper closure guardrails and Pending cleanup status]
- ASSIGN_AGENT_TASK(agent_id, title=..., objective=..., expected=..., context=...)  [task packet only; no worker/model]
- SET_AGENT_TASK_STATUS(latest|task_id|agent, status=review|blocked|closed)  [review metadata only]
- LINK_AGENT_TASK_SUGGESTION(latest|task_id|agent, suggestion=latest|id|agent)  [review provenance only; no Pending insert]
- SUGGEST_AGENT_COMMAND(agent_id, command=..., reason=..., risk=low|medium|high)  [audit only; no Pending insert]
- APPROVE_AGENT_SUGGESTION(latest|id|agent, note=...)  [review metadata only]
- REJECT_AGENT_SUGGESTION(latest|id|agent, note=...)  [review metadata only]
- STAGE_AGENT_SUGGESTION(latest|id|agent, note=...)  [visible candidate only; no Pending insert]
- MARK_AGENT_SUGGESTION_PROVENANCE(latest|id|agent, mark_type=operator_pin, note=...)  [Context Mark link only]
- SHOW_HISTORY_CONTEXT_SERVICE()  [Window 16 history/context inventory and companion contract preview]
- SUMMON_AGENT(agent_id, role=..., rank=..., urgency=..., allow=..., deny=..., history=private|parent_visible)  [registry only, no worker spawn]
- MOD_AGENT(agent_id, role=..., rank=..., urgency=..., allow=..., deny=..., history=..., status=...)  [modify registry metadata]
- SILENCE_AGENT(agent_id, note=...)  [silence registry row, keep audit]
- REQUEST_PROMPT_PIN(target, note=...)  [request metadata-only Prompt Pin]
- APPROVE_PROMPT_PIN(mark_id|target, note=...)  [approve Prompt Pin metadata; no model inclusion yet]
- REJECT_PROMPT_PIN(mark_id|target, note=...)  [reject Prompt Pin metadata]
- SET_CONTEXT_MARK_APPROVAL(mark_id|target, approval=...)  [update context mark approval]
- SHOW_PROMPT_PINS()  [preview Prompt Pins before model-visible inclusion]
- SHOW_PROMPT_INCLUSION_READINESS()  [preview-only Prompt Inclusion gates and rollback controls]
- SHOW_PROMPT_INCLUSION_PREVIEW()  [no-send Prompt Inclusion diff before activation]
- RUN_PROMPT_INCLUSION_PREVIEW_REHEARSAL()  [temporary approved test marks, no-send diff proof, auto-clear]
- SHOW_PROMPT_INCLUSION_REHEARSAL()  [latest Prompt Inclusion rehearsal result]
- SHOW_PROMPT_INCLUSION_ACTIVATION_CHECKLIST()  [activation review checklist and rollback plan]
- SET_PROMPT_INCLUSION_ACTIVATION(on|off, preview_id=latest|fresh, checklist_id=latest|fresh, confirm=offline_proof|rollback)  [reversible prompt inclusion]
- SHOW_PROMPT_INCLUSION_ACTIVATION()  [activation state and offline proof]
- RUN_PROMPT_INCLUSION_CLOSURE_CHECK()  [Window 19 closure/readiness proof]
- SHOW_PROMPT_INCLUSION_CLOSURE()  [Window 19 parked-off closure posture]
- SHOW_CHECKPOINT_READINESS()  [read-only Window 18-21 checkpoint posture rollup; no stage/commit]
- SHOW_LIVE_VISUAL_HARNESS()  [Window 11 visual/reasoning harness contract and readiness]
- RUN_LIVE_VISUAL_HARNESS_REHEARSAL()  [offline harness rehearsal, no model calls]
- SHOW_LIVE_VISUAL_HARNESS_REHEARSAL()  [latest offline harness rehearsal result]
- ARM_LIVE_VISUAL_HARNESS_PROBE(optional_model)  [arm live probe; tier inferred from model]
- ARM_CHEAP_LIVE_VISUAL_HARNESS(optional_model)  [arm cheap live probe; keeps live mode off]
- ARM_STRONG_LIVE_VISUAL_HARNESS(optional_model)  [arm stronger-model comparison; keeps live mode off]
- QUEUE_LIVE_VISUAL_HARNESS_PROBE_PROMPT()  [queue bounded probe prompt while live mode is off]
- RECORD_LIVE_VISUAL_HARNESS_PROBE_RESULT()  [record latest post-arm model-turn diagnostics]
- SHOW_LIVE_VISUAL_HARNESS_PROBE()  [show live probe contract/result]
- SHOW_IMAGE_CONTEXT_INDEX()  [Window 12 screenshot sidecar/index metadata]
- SHOW_IMAGE_COST_POSTURE()  [Window 18 screenshot/image-index cost posture]
- BACKFILL_IMAGE_CONTEXT_INDEX(optional_limit)  [bounded recent screenshot sidecar backfill]
- UPDATE_IMAGE_CONTEXT_METADATA(image_id_or_path, caption="...", ocr="...", tags="tag1;tag2")  [explicit sidecar metadata fill]
- SEARCH_IMAGE_CONTEXT_INDEX(query, optional_limit)  [search screenshot sidecar metadata]
- REF(query_or_pack, optional_pack|all)  [shorthand; expands to SHOW_REFERENCE_PACK(...) or SEARCH_REFERENCE_PACK(...)]
- FIND_REFERENCE(query, optional_pack|all)  [alias for REF(...)]

[Continuity / Scoped Clear]
- SAVE_HANDOFF(optional_filename)
- RETRIEVE_HANDOFF(optional_filename)
- CHECK_PREVIOUS_HANDOFF()
- RECALL_PREVIOUS_SUMMARY(optional_character_name)
- CLEAR_NONPIN()
- CLEAR_INIT()
- CLEAR_PIN()
- CLEAR_HANDOFF()
- CLEAR_RECENT_CONTEXT()
- CLEAR_ROUTE_STATE()

[Advanced Context Controls]
- SET_AUTO_PROMPT(on|off)
- SET_SHOW_USER_TEXT(on|off)
- SET_SHOW_AI_TEXT(on|off)
- SET_SHOW_AI_COMMANDS(on|off)
- SET_SHOW_USER_COMMANDS(on|off)
- SET_UNIMPORTANT_MESSAGES(on|off)
- SET_IMPORTANT_MESSAGES(on|off)
- SET_ADD_UMSGS_TO_HISTORY(on|off)
- SET_ADD_IMSGS_TO_HISTORY(on|off)
- SET_UMSGS_DECAY_CHECK(on|off)
- SET_IMSGS_DECAY_CHECK(on|off)
- SET_ALWAYS(on|off, true|false)
- TOGGLE_AUTO_PROMPT()
- TOGGLE_ALWAYS(on|off, true|false)
- SET_IMAGE_DETAIL(low|high|auto|original)
- SET_LATEST_IMAGE_DETAIL(low|high|auto|original)
- SET_HIGH_DETAIL(number)
- SET_MAX_IMAGES_IN_HISTORY(number)
- HIDE_USER_TEXT()
- HIDE_AI_TEXT()
- HIDE_AI_COMMANDS()
- HIDE_USER_COMMANDS()
- TOGGLE_UMSGS()
- TOGGLE_IMSGS()
- TOGGLE_ADD_UMSGS_TO_HISTORY()
- TOGGLE_ADD_IMSGS_TO_HISTORY()
- TOGGLE_UMSGS_DECAY_CHECK()
- TOGGLE_IMSGS_DECAY_CHECK()

[Pending Queue]
- This is the pending-command planning lane: held commands wait for support, approval, auto-policy, or clearing.
- normal keeps a held candidate in its near-term place; insert claims the next slot and defers later pending items; replace / override claims the next slot and marks displaced immediate items dropped.
- Approve executes the chosen pending commands through the normal runtime path. Clear drops them without execution.
- Pending filters only narrow the view. Selection actions affect selected visible rows; all/risk/category commands address the runtime queue scope named in the command.
- SHOW_PENDING_COMMANDS()
- APPROVE_PENDING(index|all|low|medium|high|memory|desktop_action)
- CLEAR_PENDING_COMMANDS(index|all|low|medium|high|memory|desktop_action)

[Queue Lanes]
- Pending-command planning: QUEUE_PENDING(...), INSERT_PENDING(...), REPLACE_PENDING(...), OVERRIDE_PENDING(...), SHOW_PENDING_COMMANDS(), APPROVE_PENDING(...), CLEAR_PENDING_COMMANDS(...).
- Next-turn override: SET_NEXT_REASONING_EFFORT(...) for a one-turn effort change, or SET_NEXT_INFERENCE(...) for broader one-turn posture changes; CLEAR_NEXT_INFERENCE() resets the queued override.
- Observation / wake requests: REQUEST_SCREENSHOT_CAPTURE(...), SET_DEMAND_CAPTURE(...), and command-result wake; these ask Aurora to capture or wake after results, and do not approve, clear, or reorder pending commands.
- Command Drip is the recent plus near-future command tree. Lookahead buckets are candidate forecasts, not already-approved actions.

[Game / Desktop Actions]
- GB:press(a)
- GB:hold(b, 0.25)
- GB:move_key(up, 1)
- GB:Start
- GB:Select
- PYAG:move(x, y, 0.15)
- PYAG:click(left)
- PYAG:type("text")

[Structured Memory Commands]
- ADD_GOAL(text; priority; significance)
- ADD_APRIORITY_GOAL(text)
- ADD_OVERARCHING_GOAL(text)
- ADD_UNKNOWN_PRIORITY(text)
- UPDATE_CONTEXT(items)
- UPDATE_CURRENT_AREA(area)
- UPDATE_TARGET_AREA(area)
- UPDATE_TRAVEL_HEADING(direction_or_mode)
- UPDATE_LAST_LANDMARK(landmark)
- UPDATE_ROUTE_INTENT(items)
- UPDATE_LOCAL_PATH_PLAN(items)
- UPDATE_ROUTE_BLOCKERS(items)
- UPDATE_RECENT_MOVEMENT_RESULTS(items)
- UPDATE_MID_TERM_CONTEXT(items)
- UPDATE_LONG_TERM_CONTEXT(items)
- UPDATE_NOTES(items)
- ADD_JOURNAL(entry)
- UPDATE_PINNED_IMMEDIATE(items)
- UPDATE_PINNED_SHORT_TERM(items)

[Current Overlay Notes]
- Aurora still draws cursor position, last key, timestamp, red key-point dots, and optional tile/grid overlays.
- The colored tile grid code still exists in the runtime, but it is disabled by default.
- The UI overlay toggles control tile grid, near-cursor XY label, key-point dots, and top status text separately.
- Overlay presets: Minimal, Navigation, and Debug.
- Operator profiles: Inspect, Assist Live, and Battle.

[Dynamic Planning Notes]
- Review turns are periodic "check surroundings / plans / goals" turns.
- Critique turns are deeper self-review turns that should check for stale plans, repeated failures, and contradictions.
- Turn Scheduler controls how a full model turn wakes: the `balanced` profile is the default and uses `hybrid` mode so Aurora behaves more like a Codex-style event loop without dropping the screenshot heartbeat.
- `event` wakes on meaningful events plus a safety heartbeat; `per_capture` is the legacy conveyor where each fresh screenshot can trigger a turn.
- Profile guide: `balanced` = recommended general use, `responsive` = faster follow-ups, `conservative` = quieter/cheaper, `legacy` = old per-capture behavior.
- Screenshot capture cadence is separate from turn cadence now. Faster capture does not have to mean more model calls.
- A queued next-turn plan overrides the automatic planner for one turn.
- Command Drip stores a short rolling command tree across recent turns plus 1-3 turns ahead by default.
- Pending queue mode controls only how new held commands enter the pending planning lane: normal=hold, insert=next slot plus defer later pending entries, replace/override=next slot plus drop displaced immediate entries.
- Demand capture and command-result wake are observation/timing requests; they are not pending approvals and do not reorder the command queue.
- Use 3-7 retained turns as the normal operating range unless you are deliberately debugging longer histories.
- On-Hand Memory should stay compact and foregrounded every turn; Retrievable Memory is stable context that can be pulled back when needed.
- The actual screenshot interval remains operator-controlled; cadence estimates show how often deeper turns are likely to happen at the current interval and effort multipliers.
"""


def short(value, limit=120):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def format_source_mix(items, limit=10, item_limit=32):
    if not isinstance(items, list):
        return "-"
    cleaned = [short(item, item_limit) for item in items if str(item or "").strip()]
    if not cleaned:
        return "-"
    suffix = " ..." if len(cleaned) > limit else ""
    return ", ".join(cleaned[:limit]) + suffix


def format_pending_queue_mode_semantics(mode):
    normalized = str(mode or "normal").strip().lower()
    descriptions = {
        "normal": "normal holds new pending candidates",
        "insert": "insert claims next slot and defers later pending entries",
        "replace": "replace/override claims next slot and drops displaced immediate entries",
    }
    return descriptions.get(normalized, descriptions["normal"])


def has_effective_next_inference_plan(next_plan):
    if not isinstance(next_plan, dict):
        return False
    for key in (
        "reasoning_effort",
        "verbosity",
        "summary_mode",
        "image_detail",
        "latest_image_detail",
        "temperature",
        "model",
        "text_model",
        "vision_model",
        "reasoning_model",
        "note",
    ):
        if str(next_plan.get(key, "") or "").strip():
            return True
    return False


def build_queue_next_action_cue(state):
    state = state or {}
    continuation = state.get("continuation") or {}
    task = continuation.get("active_task") or {}
    if continuation.get("mode") == "bounded" and task.get("status") == "stopped":
        return f"Next: task stopped ({task.get('stop_reason', 'unknown')}); new operator input starts another bounded task."
    scheduler = state.get("scheduler", {}) or {}
    planning = state.get("planning", {}) or {}
    monitors = state.get("monitors", {}) or {}
    queue_bridge = monitors.get("queue_bridge", {}) or state.get("queue_bridge", {}) or {}
    pending_rows = state.get("pending_commands", []) or []
    next_plan = planning.get("next_inference", {}) or {}
    if not isinstance(next_plan, dict):
        next_plan = {}

    if not queue_bridge.get("bridge_caught_up", True):
        latest_id = queue_bridge.get("latest_raw_inbox_message_id", "") or "-"
        return f"Next: wait for bridge ingestion to catch up to raw inbox {short(latest_id, 28)}."
    if not queue_bridge.get("command_result_caught_up", True):
        latest_status = queue_bridge.get("latest_external_command_result_status", "") or "pending"
        return f"Next: wait for command-result logging to catch up ({latest_status})."
    if scheduler.get("demand_capture_pending", False):
        reason = scheduler.get("demand_capture_reason") or scheduler.get("demand_capture_last_reason") or "capture"
        return f"Next: capture requested observation for {short(reason, 42)}, then scheduler can wake."
    if scheduler.get("pending_command_result", False):
        return "Next: command-result wake is waiting for the follow-up observation/turn boundary."
    if has_effective_next_inference_plan(next_plan):
        return "Next: queued model-turn override applies once; pending commands stay separate."
    due_count = int(queue_bridge.get("due_pending_count", 0) or 0)
    if due_count > 0:
        return f"Next: {due_count} due pending command(s) need approval or auto-policy."
    if pending_rows:
        return f"Next: {len(pending_rows)} pending command(s) are held for support, approval, or clear."
    pending_reasons = scheduler.get("pending_reasons", []) or []
    if pending_reasons:
        return "Next: scheduler wake pending for " + short(", ".join(str(item) for item in pending_reasons), 70) + "."
    return "Next: queue lanes are idle; the scheduler controls the next model turn."


def format_monitor_summary(monitors):
    monitors = monitors or {}
    status = short(monitors.get("overall_status", "ok"), 16) or "ok"
    counts = monitors.get("status_counts", {}) or {}
    checks = len(monitors.get("checks", []) or [])
    warnings = int(counts.get("warning", 0) or 0)
    errors = int(counts.get("error", 0) or 0)
    watch = int(counts.get("watch", 0) or 0)
    return f"{status} | checks {checks} | warn {warnings} | err {errors} | watch {watch}"


def format_gameplay_monitor_summary(monitors, fallback_gameplay=None):
    monitors = monitors or {}
    gameplay = monitors.get("gameplay", {}) or fallback_gameplay or {}
    visibility = short(gameplay.get("visibility", "unknown"), 18) or "unknown"
    scene = short(gameplay.get("scene", "unknown"), 18) or "unknown"
    focus_ok = gameplay.get("last_input_focus_ok", None)
    focus_label = "ok" if focus_ok is True else "needs focus" if focus_ok is False and gameplay.get("last_input_attempt_at_epoch") else "idle"
    input_age = gameplay.get("last_input_age_seconds", None)
    input_label = format_age_seconds(input_age) if input_age is not None else "none"
    return f"{visibility} | scene {scene} | input {input_label} | focus {focus_label}"


def format_state_export_monitor_summary(monitors, fallback_export=None):
    monitors = monitors or {}
    export = monitors.get("state_export", {}) or fallback_export or {}
    if not export:
        return "unknown"
    success_age = export.get("last_success_age_seconds", None)
    file_age = export.get("file_age_seconds", None)
    error = short(export.get("last_error", ""), 28)
    parts = [
        f"success {format_age_seconds(success_age) if success_age is not None else 'none'}",
        f"file {format_age_seconds(file_age) if file_age is not None else 'missing'}",
    ]
    if error:
        parts.append(f"err {error}")
    return " | ".join(parts)


def format_queue_bridge_monitor_summary(monitors, fallback_queue_bridge=None):
    monitors = monitors or {}
    queue_bridge = monitors.get("queue_bridge", {}) or fallback_queue_bridge or {}
    if not queue_bridge:
        return "unknown"
    pending_count = int(queue_bridge.get("pending_count", 0) or 0)
    due_count = int(queue_bridge.get("due_pending_count", 0) or 0)
    stale_due = int(queue_bridge.get("stale_due_count", 0) or 0)
    raw_age = queue_bridge.get("latest_raw_inbox_age_seconds", None)
    result_age = queue_bridge.get("latest_external_command_result_age_seconds", None)
    bridge_label = "caught" if queue_bridge.get("bridge_caught_up", True) else "drift"
    command_label = "caught" if queue_bridge.get("command_result_caught_up", True) else "waiting"
    return (
        f"pending {pending_count}/{due_count}"
        f" | stale due {stale_due}"
        f" | bridge {bridge_label} {format_age_seconds(raw_age)}"
        f" | result {command_label} {format_age_seconds(result_age)}"
    )


def format_mutation_admission_summary(mutation_admission):
    mutation_admission = mutation_admission or {}
    if not mutation_admission:
        return "not exported"
    if mutation_admission.get("status") == "error":
        return f"error | {short(mutation_admission.get('error', ''), 48) or 'journal unavailable'}"
    return (
        f"reserved {mutation_admission.get('reserved_count', 0)}"
        f" | terminal {mutation_admission.get('terminal_count', 0)}"
        f" | uncertain {mutation_admission.get('uncertain_count', 0)}"
        " | replay off"
    )


def format_age_seconds(age):
    if age is None:
        return "-"
    try:
        age = max(0.0, float(age))
    except Exception:
        return "-"
    if age < 1:
        return "now"
    if age < 60:
        return f"{int(age)}s"
    if age < 3600:
        return f"{age / 60:.1f}m"
    return f"{age / 3600:.1f}h"


def parse_state_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(text[:19], pattern))
        except Exception:
            continue
    return None


def build_state_freshness_text(state):
    state = state or {}
    export_epoch = parse_state_timestamp(state.get("timestamp", ""))
    file_epoch = None
    if STATE_PATH.exists():
        try:
            file_epoch = STATE_PATH.stat().st_mtime
        except Exception:
            file_epoch = None
    truth_epoch = export_epoch or file_epoch
    age = (time.time() - truth_epoch) if truth_epoch else None
    if age is None:
        freshness = "missing"
    elif age <= 5:
        freshness = "fresh"
    elif age <= 30:
        freshness = "aging"
    else:
        freshness = "stale"
    exported = short(state.get("timestamp", ""), 24) or "-"
    file_time = time.strftime("%H:%M:%S", time.localtime(file_epoch)) if file_epoch else "missing"
    return f"State {freshness} | exported {exported} | file {file_time} | age {format_age_seconds(age)}"


def format_timestamp_age_text(value, label="timestamp"):
    epoch = parse_state_timestamp(value)
    text = short(value, 19) or "-"
    if epoch is None:
        return f"{label} {text}"
    return f"{label} {text} ({format_age_seconds(time.time() - epoch)} old)"


def format_file_age_text(path, label="file"):
    if not path:
        return f"{label} -"
    path = Path(path)
    if not path.exists():
        return f"{label} missing"
    try:
        epoch = path.stat().st_mtime
    except Exception:
        return f"{label} age unknown"
    return f"{label} {time.strftime('%H:%M:%S', time.localtime(epoch))} ({format_age_seconds(time.time() - epoch)} old)"


def format_price_value(value):
    if value is None:
        return "n/a"
    try:
        return f"${float(value):g}"
    except Exception:
        return str(value)


def format_model_pricing_compact(pricing):
    pricing = pricing or {}
    if not pricing:
        return "price unknown"
    return (
        f"in {format_price_value(pricing.get('input'))} / "
        f"cache {format_price_value(pricing.get('cached_input'))} / "
        f"out {format_price_value(pricing.get('output'))} per 1M"
    )


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def acquire_windows_single_instance_mutex(name):
    if KERNEL32 is None:
        return None
    handle = KERNEL32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        KERNEL32.CloseHandle(handle)
        return None
    return handle


def release_windows_single_instance_mutex(handle):
    if KERNEL32 is None or not handle:
        return
    KERNEL32.CloseHandle(handle)


def is_windows_pid_running(pid):
    try:
        candidate = int(pid or 0)
    except Exception:
        return False
    if candidate <= 0:
        return False
    if KERNEL32 is None:
        try:
            os.kill(candidate, 0)
            return True
        except OSError:
            return False
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, candidate)
    if not handle:
        return False
    KERNEL32.CloseHandle(handle)
    return True


def read_pid_file(path):
    try:
        return int((path.read_text(encoding="utf-8") or "").strip() or 0)
    except Exception:
        return 0


def write_pid_file(path, pid):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(pid)), encoding="utf-8")


def remove_pid_file(path, expected_pid=None):
    try:
        if expected_pid is not None and path.exists():
            current_pid = read_pid_file(path)
            if current_pid and int(current_pid) != int(expected_pid):
                return False
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def decorate_state_processes(state):
    snapshot = dict(state or {})
    processes = dict(snapshot.get("processes", {}) or {})
    runtime = dict(processes.get("runtime", {}) or {})
    control_panel = dict(processes.get("control_panel", {}) or {})

    runtime_pid = int(runtime.get("pid") or read_pid_file(RUNTIME_PID_PATH) or 0)
    control_panel_pid = int(control_panel.get("pid") or read_pid_file(CONTROL_PANEL_PID_PATH) or 0)

    runtime["pid"] = runtime_pid
    runtime["active"] = is_windows_pid_running(runtime_pid)
    control_panel["pid"] = control_panel_pid
    control_panel["active"] = is_windows_pid_running(control_panel_pid)

    if control_panel_pid > 0 and not control_panel["active"]:
        remove_pid_file(CONTROL_PANEL_PID_PATH, expected_pid=control_panel_pid)

    processes["runtime"] = runtime
    processes["control_panel"] = control_panel
    snapshot["processes"] = processes
    return snapshot


def show_duplicate_instance_notice(title, message):
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        pass


def format_runtime_seconds(value):
    try:
        numeric = float(value)
    except Exception:
        return "-"
    if numeric <= 0:
        return "-"
    if numeric >= 10:
        return f"{int(round(numeric))}s"
    if numeric >= 1:
        return f"{numeric:.1f}s"
    return f"{numeric:.2f}s"


def get_runtime_activation_plan(state):
    snapshot = decorate_state_processes(state)
    defaults = snapshot.get("defaults", {}) or {}
    if bool(defaults.get("personal_available")):
        return {
            "label": "personal defaults",
            "commands": ["APPLY_PERSONAL_DEFAULTS()", "SET_LIVE_MODE(on)"],
        }

    profile = DEFAULT_RUNTIME_ACTIVATION_PROFILE
    return {
        "label": (
            f"{profile['text_model']} | {profile['screenshot_interval']}s | "
            f"{profile['reasoning_effort']} thinking | {profile['verbosity']} verbosity"
        ),
        "commands": [
            f"SET_EXECUTION_MODE({profile['execution']})",
            f"SET_ACTION_MODE({profile['action']})",
            f"SET_TEXT_MODEL({profile['text_model']})",
            f"SET_VISION_MODEL({profile['vision_model']})",
            f"SET_REASONING_MODEL({profile['reasoning_model']})",
            f"SET_SESSION_REASONING_EFFORT({profile['reasoning_effort']})",
            f"SET_MODEL_VERBOSITY({profile['verbosity']})",
            f"SET_SCREENSHOT_INTERVAL({profile['screenshot_interval']})",
            "SET_LIVE_MODE(on)",
        ],
    }


def build_runtime_mode_spec(snapshot):
    modes = snapshot.get("modes", {}) or {}
    live_value = "on" if bool(modes.get("live", False)) else "off"
    execution = (modes.get("execution") or "").strip() or "-"
    action = (modes.get("action") or "").strip() or "-"
    game_profile = (modes.get("game_profile") or "").strip() or "-"
    return f"Execution: {execution} | Action: {action} | Profile: {game_profile} | Live: {live_value}"


def build_runtime_model_spec(snapshot):
    model_status = snapshot.get("model_status", {}) or {}
    models = snapshot.get("models", {}) or {}
    text_model = (model_status.get("text_model") or models.get("text") or "").strip() or "-"
    vision_model = (model_status.get("vision_model") or models.get("vision") or "").strip() or "-"
    reasoning_model = (model_status.get("reasoning_model") or models.get("reasoning") or "").strip() or "-"
    reasoning_effort = (model_status.get("reasoning_effort") or models.get("reasoning_effort") or "").strip() or "-"
    verbosity = (model_status.get("verbosity") or models.get("verbosity") or "").strip() or "-"
    screenshot_interval = model_status.get("screenshot_interval_seconds")
    if screenshot_interval in {None, ""}:
        screenshot_interval = (snapshot.get("modes", {}) or {}).get("screenshot_interval")
    effective_interval = model_status.get("effective_screenshot_interval_seconds")
    if effective_interval in {None, ""}:
        effective_interval = (snapshot.get("modes", {}) or {}).get("effective_screenshot_interval")
    tick_text = format_runtime_seconds(screenshot_interval)
    if effective_interval not in {None, ""} and format_runtime_seconds(effective_interval) != tick_text:
        tick_text = f"{tick_text} active {format_runtime_seconds(effective_interval)}"
    return (
        f"Models: {text_model} / {vision_model} / {reasoning_model} | "
        f"Thinking: {reasoning_effort} | Verbosity: {verbosity} | Tick: {tick_text}"
    )


def launch_runtime_process(with_ui=True, paused=False):
    launcher_path = ROOT / "launch_aurora2.cmd"
    if not launcher_path.exists():
        raise FileNotFoundError(f"Aurora launcher not found: {launcher_path}")

    command = ["cmd.exe", "/c", str(launcher_path)]
    if with_ui:
        command.append("--with-ui")
    if paused:
        command.extend(["--offline", "--no-ui", "--no-live-init", "--no-smoke-test", "--no-sound", "--execution-mode", "safe", "--action-mode", "none", "--screenshot-interval", "2.0"])

    creationflags = 0
    if os.name == "nt":
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        command,
        cwd=str(ROOT),
        creationflags=creationflags,
        close_fds=True,
    )


def tail_lines(path, limit=40):
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if limit is None or limit <= 0:
        return lines
    return lines[-limit:]


def read_jsonl_records(path, limit=None):
    if not path.exists():
        return []
    rows = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    if limit is None or limit <= 0:
        return rows
    return rows[-limit:]


def read_model_catalog():
    payload = read_json(MODEL_CATALOG_PATH, {"custom_models": {}})
    custom_models = payload.get("custom_models", {})
    if not isinstance(custom_models, dict):
        return {}
    cleaned = {}
    for model_name, metadata in custom_models.items():
        normalized = str(model_name or "").strip()
        if not normalized:
            continue
        cleaned[normalized] = metadata if isinstance(metadata, dict) else {}
    return cleaned


def build_model_choices(model_catalog=None):
    custom_models = model_catalog if model_catalog is not None else read_model_catalog()
    return sorted({*MODELS, *custom_models.keys()})


def append_external_message(text, raw=False, source="control_panel", subject="[AURORA CONTROL PANEL]", metadata=None, request_id=None, message_id=None):
    return append_bridge_request(
        ROOT,
        text,
        raw=raw,
        source=source,
        author="operator",
        subject=subject,
        metadata=metadata or {},
        client_id="aurora_control_panel",
        request_id=request_id,
        message_id=message_id,
    )


def build_control_panel_registered_changes(values):
    values = values if isinstance(values, dict) else {}
    changes = [
        {"key": key, "value": values.get(key)}
        for key in CONTROL_PANEL_REGISTERED_NON_SCHEDULER_KEYS
        if key in values
    ]
    scheduler_profile = str(values.get("scheduler.profile", "") or "").strip().lower()
    if scheduler_profile and scheduler_profile != "custom":
        changes.append({"key": "scheduler.profile", "value": scheduler_profile})
    else:
        changes.extend(
            {"key": key, "value": values.get(key)}
            for key in CONTROL_PANEL_SCHEDULER_LEAF_KEYS
            if key in values
        )
    return changes


def filter_changed_control_panel_settings(changes, snapshot):
    rows = {
        str(row.get("key") or ""): row
        for row in (snapshot.get("settings", []) if isinstance(snapshot, dict) else [])
        if isinstance(row, dict)
    }
    changed = []
    for change in changes or []:
        key = str(change.get("key") or "")
        current = rows.get(key)
        if current is None or not setting_values_equal(key, current.get("value"), change.get("value")):
            changed.append(dict(change))
    return changed


def _format_control_panel_setting_value(value):
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def format_control_panel_settings_snapshot(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    lines = [
        f"Settings version: {snapshot.get('version') or 'unavailable'}",
        f"Runtime active: {bool(snapshot.get('runtime_active', False))}",
        f"State timestamp: {snapshot.get('state_timestamp') or 'unavailable'}",
        f"Registered settings: {snapshot.get('count', 0)}",
        "",
    ]
    for row in snapshot.get("settings", []) or []:
        if not isinstance(row, dict):
            continue
        source = row.get("source", {}) or {}
        lines.extend(
            [
                f"{row.get('key')}: {_format_control_panel_setting_value(row.get('value'))}",
                (
                    f"  status={row.get('value_status') or '-'} | source={source.get('kind') or '-'} "
                    f"({source.get('path') or '-'}) | locked={'yes' if row.get('locked') else 'no'}"
                ),
                (
                    f"  maturity={row.get('maturity') or '-'} | tier={row.get('gui_tier') or '-'} | "
                    f"risk={row.get('risk_class') or '-'} | apply={row.get('apply_timing') or '-'}"
                ),
            ]
        )
    return "\n".join(lines)


def format_control_panel_settings_receipt(receipt):
    receipt = receipt if isinstance(receipt, dict) else {}
    lines = [
        (
            f"Settings transaction {receipt.get('transaction_id') or '-'} | "
            f"{receipt.get('operation') or '-'} | {receipt.get('status') or '-'}"
        ),
        (
            f"Version {receipt.get('before_version') or '-'} -> "
            f"{receipt.get('after_version') or '-'}"
        ),
        f"Scope {receipt.get('scope') or '-'} | automatic replay {'off' if receipt.get('no_automatic_replay') else 'unknown'}",
        "",
    ]
    for row in receipt.get("changes", []) or []:
        if not isinstance(row, dict):
            continue
        target = row.get("projected_value") if receipt.get("dry_run") else row.get("after_value")
        readback = row.get("effective_readback", {}) or {}
        source = readback.get("source", {}) or {}
        lines.extend(
            [
                (
                    f"{row.get('key')}: {_format_control_panel_setting_value(row.get('before_value'))} -> "
                    f"{_format_control_panel_setting_value(target)}"
                ),
                (
                    f"  source={source.get('kind') or '-'} | locked={'yes' if readback.get('locked') else 'no'} | "
                    f"maturity={readback.get('maturity') or '-'} | apply={row.get('apply_timing') or '-'}"
                ),
            ]
        )
    for rejection in receipt.get("rejections", []) or []:
        if isinstance(rejection, dict):
            setting_key = str(rejection.get("key") or "transaction")
            lines.append(
                f"Rejected {setting_key} [{rejection.get('code') or 'error'}]: "
                f"{rejection.get('message') or '-'}"
            )
    rollback = receipt.get("rollback_handle") or {}
    if isinstance(rollback, dict) and rollback.get("handle_id"):
        lines.extend(
            [
                "",
                f"Rollback handle: {rollback.get('handle_id')}",
                f"Rollback status: {rollback.get('status') or '-'} | expires: {rollback.get('expires') or 'runtime shutdown'}",
            ]
        )
    return "\n".join(lines)


def _normalize_screenshot_limit(limit):
    try:
        return max(1, int(limit))
    except Exception:
        return SCREENSHOT_LIST_DEFAULT_LIMIT


def _recent_screenshot_cache_key(directory, limit):
    return str(Path(directory or "").resolve()), _normalize_screenshot_limit(limit)


def _sort_recent_paths(paths, limit):
    rows = []
    for path in paths:
        candidate = Path(path)
        try:
            stat = candidate.stat()
            rows.append((stat.st_mtime, stat.st_mtime_ns, stat.st_size, str(candidate), candidate))
        except OSError:
            continue
    rows.sort()
    return [row[-1] for row in rows[-limit:]]


def _merge_forced_screenshot(files, force_path, limit):
    if not force_path:
        return list(files), False
    candidate = Path(force_path)
    try:
        exists = candidate.exists()
    except OSError:
        exists = False
    if not exists or candidate.suffix.lower() not in IMAGE_SUFFIXES:
        return list(files), False
    merged = list(files)
    if candidate not in merged:
        merged.append(candidate)
        return _sort_recent_paths(merged, limit), True
    return merged, False


def _scan_recent_screenshots(directory, limit):
    newest = []
    scanned = 0
    skipped = 0
    with os.scandir(directory) as entries:
        for entry in entries:
            try:
                if not entry.is_file():
                    skipped += 1
                    continue
                if Path(entry.name).suffix.lower() not in IMAGE_SUFFIXES:
                    skipped += 1
                    continue
                stat = entry.stat()
            except OSError:
                skipped += 1
                continue
            scanned += 1
            item = (stat.st_mtime, stat.st_mtime_ns, stat.st_size, entry.path)
            if len(newest) < limit:
                heapq.heappush(newest, item)
            elif item > newest[0]:
                heapq.heapreplace(newest, item)
    newest.sort()
    return [Path(item[-1]) for item in newest], scanned, skipped


def safe_list_screenshots(screenshots_dir, limit=SCREENSHOT_LIST_DEFAULT_LIMIT, force_path=None):
    if not str(screenshots_dir or "").strip():
        return []
    directory = Path(screenshots_dir or "")
    normalized_limit = _normalize_screenshot_limit(limit)
    key = _recent_screenshot_cache_key(directory, normalized_limit)
    now = time.monotonic()
    cached = SCREENSHOT_LIST_CACHE.get(key)
    if cached and now - float(cached.get("updated_monotonic", 0.0)) <= SCREENSHOT_LIST_CACHE_TTL_SECONDS:
        files, forced_inserted = _merge_forced_screenshot(cached.get("files", []), force_path, normalized_limit)
        stats = dict(cached.get("stats", {}))
        stats.update({
            "cache_hit": True,
            "forced_latest_inserted": forced_inserted,
            "age_seconds": round(now - float(cached.get("updated_monotonic", now)), 2),
            "returned": len(files),
        })
        cached["last_stats"] = stats
        return files

    started = time.perf_counter()
    files = []
    scanned = 0
    skipped = 0
    error = ""
    if directory.exists():
        try:
            files, scanned, skipped = _scan_recent_screenshots(directory, normalized_limit)
        except OSError as exc:
            error = str(exc)
    files, forced_inserted = _merge_forced_screenshot(files, force_path, normalized_limit)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    stats = {
        "cache_hit": False,
        "directory": str(directory),
        "scanned": scanned,
        "skipped": skipped,
        "returned": len(files),
        "limit": normalized_limit,
        "elapsed_ms": elapsed_ms,
        "ttl_seconds": SCREENSHOT_LIST_CACHE_TTL_SECONDS,
        "forced_latest_inserted": forced_inserted,
        "error": error,
    }
    SCREENSHOT_LIST_CACHE[key] = {
        "files": list(files),
        "updated_monotonic": now,
        "updated_wall": time.time(),
        "stats": stats,
        "last_stats": stats,
    }
    return files


def get_screenshot_list_cache_stats(screenshots_dir, limit=SCREENSHOT_LIST_DEFAULT_LIMIT):
    if not str(screenshots_dir or "").strip():
        return {}
    key = _recent_screenshot_cache_key(screenshots_dir, limit)
    cached = SCREENSHOT_LIST_CACHE.get(key)
    if not cached:
        return {}
    stats = dict(cached.get("last_stats") or cached.get("stats") or {})
    stats["cache_age_seconds"] = round(time.monotonic() - float(cached.get("updated_monotonic", time.monotonic())), 2)
    return stats


class AuroraControlPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(release_info()['panel_title'])
        self.ui_preferences = load_layout_preferences(LAYOUT_PATH)
        self._closing = False
        self._refresh_after_id = None
        self._last_state_signature = None
        self._normal_geometry = {}
        self.settings_sections = []
        self.page_views = {}
        self.settings_mode = "hidden"
        self._sash_after_id = None
        self.refresh_health_var = tk.StringVar(value="")
        self.compact_status_var = tk.StringVar(value="Waiting for runtime state")
        self.header_status_var = tk.StringVar(value="Waiting for runtime state")
        self.compact_header_var = tk.BooleanVar(value=self.ui_preferences.get("compact_header", True) is not False)
        self._configure_initial_window_geometry()
        self.configure(bg=BG)
        self.state_cache = {}
        self.conversation_outbox = SessionOutbox(ROOT)
        self.conversation_outbox_window = None
        self.conversation_popout_window = None
        self.conversation_activity_var = tk.StringVar(value="Waiting for runtime state.")
        self.pending_rows = []
        self.pending_candidates_text = None
        self.screenshot_files = []
        self.episodic_rows = []
        self.screenshot_index = -1
        self.image_memory_rows = []
        self.image_memory_index = -1
        self.visual_context_text = None
        self.image_context_index_text = None
        self.live_harness_text = None
        self.responses_shadow_text = None
        self.context_files_text = None
        self.history_context_text = None
        self.portal_intake_text = None
        self.prompt_ledger_text = None
        self.dashboard_text = None
        self.dashboard_events_tree = None
        self.dashboard_summary_vars = {}
        self.dashboard_snapshot = {}
        self.dashboard_popout_window = None
        self.dashboard_popout_text = None
        self.dashboard_popout_button = None
        self.dashboard_receipt_window = None
        self.dashboard_status_var = tk.StringVar(value="Dashboard popout closed.")
        self.dashboard_wrap_var = tk.BooleanVar(value=True)
        self.dashboard_popout_summary_var = tk.StringVar(value="Waiting for an observed snapshot.")
        self._dashboard_events_by_iid = {}
        self._last_dashboard_event_signature = None
        self.preview_image = None
        self.thumbnail_images = []
        self.memory_preview_image = None
        self.memory_thumbnail_images = []
        self._thumbnail_photo_cache = {}
        self._thumbnail_cache_stats = {"hits": 0, "misses": 0, "entries": 0}
        self._screenshot_list_cache_stats = {}
        self.popout_window = None
        self.popout_label = None
        self.popout_canvas = None
        self.popout_meta = None
        self.popout_image = None
        self.popout_scale_mode = "fit"
        self.popout_status_var = tk.StringVar(value="Screenshot viewer closed.")
        self.memory_popout_window = None
        self.memory_popout_label = None
        self.memory_popout_canvas = None
        self.memory_popout_meta = None
        self.memory_popout_image = None
        self.memory_popout_scale_mode = "fit"
        self.memory_popout_status_var = tk.StringVar(value="Image-memory viewer closed.")
        self.chat_log_limit = 40
        self.command_log_limit = 40
        self.last_state_mtime = 0.0
        self._text_content_cache = {}
        self._last_log_signatures = {}
        self._last_screenshot_list_signature = None
        self._last_screenshot_render_signature = None
        self._last_thumbnail_signature = None
        self._last_image_memory_signature = None
        self._last_image_memory_render_signature = None
        self._last_memory_thumbnail_signature = None
        self._last_popout_render_signature = None
        self._last_memory_popout_render_signature = None
        self._last_refresh_perf = {}
        self._settings_observed_values = {}
        self._settings_variables = {}
        self.lockable_widgets = {}
        self.quick_action_widgets = {}
        self.widget_lock_dependencies = {}
        self.workflow_status_vars = {}
        self.focus_nav_buttons = {}
        self.current_model_choices = build_model_choices()
        self.banner_text_value = ""
        self.banner_scroll_offset = 0
        self.banner_overflow = 0
        self.banner_text_width = 0
        self.banner_window = None
        self.window_icon_image = None
        self.runtime_orb_static_image = None
        self.runtime_orb_frames = []
        self.runtime_orb_after = None
        self.runtime_orb_frame_index = 0
        self.runtime_orb_button = None
        self.runtime_orb_click_after = None
        self.runtime_orb_single_click_suppressed_until = 0.0
        self.runtime_orb_note_var = tk.StringVar(value="Aurora runtime is inactive.")
        self.runtime_status_var = tk.StringVar(value="Runtime: Inactive")
        self.image_index_search_var = tk.StringVar(value="control panel smoke")
        self.runtime_client_var = tk.StringVar(value="Client: Inactive")
        self.runtime_mode_spec_var = tk.StringVar(value="Execution: - | Action: - | Profile: - | Live: off")
        self.runtime_model_spec_var = tk.StringVar(value="Models: - / - / - | Thinking: - | Verbosity: - | Tick: -")
        self.runtime_activation_hint_var = tk.StringVar(value="Double-click the orb to activate Aurora2.")
        self.runtime_deactive_button = None
        self.runtime_shutdown_button = None
        self.operator_activity_var = tk.StringVar(value="Operator activity: no commands sent this session.")
        self.pending_selection_status_var = tk.StringVar(value="No pending commands loaded.")
        self.main_canvas = None
        self.main_canvas_window = None
        self.main_scrollbar = None
        self.focus_tab_var = tk.StringVar(value="Overview")
        self.focus_tab_by_label = {}
        self.focus_label_by_tab = {}
        self.chat_head_requested_open = False
        self.chat_head_strip_window = None
        self.chat_head_history_window = None
        self.chat_head_strip_text = None
        self.chat_head_history_text = None
        self.chat_head_expand_canvas = None
        self.chat_head_toggle_canvas = None
        self.chat_head_window_signature = None
        self.chat_head_history_signature = None
        self.chat_head_send_animation_after = None
        self.chat_head_send_animation_active = False
        self.chat_head_send_animation_pending = False
        self.chat_head_status_var = tk.StringVar(value="Chat head closed.")
        self.chat_head_strip_status_var = tk.StringVar(value="Enter sends. History panel closed.")
        self.chat_head_history_status_var = tk.StringVar(value="No recent chat history loaded.")
        self.settings_transaction_result_queue = queue.Queue()
        self.settings_transaction_pending = None
        self.settings_transaction_last_receipt = {}
        self.settings_transaction_last_snapshot = {}
        self.settings_transaction_last_rollback_handle = ""
        self.settings_transaction_buttons = []
        self.settings_transaction_preview_button = None
        self.settings_transaction_apply_button = None
        self.settings_transaction_rollback_button = None
        self.settings_transaction_details_button = None
        self.settings_transaction_dialog = None
        self._build_styles()
        self._configure_window_icon()
        self._build_ui()
        self._bind_navigation_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_loop()
        self.after(BANNER_TICK_MS, self._banner_tick)
        self.bind("<Configure>", self._remember_window_geometry, add="+")

    def _configure_initial_window_geometry(self):
        self._work_areas = monitor_work_areas((0, 0, self.winfo_screenwidth(), self.winfo_screenheight()))
        scale = ui_scale(self)
        defaults = {"width": round(1600 * scale), "height": round(980 * scale)}
        geometry = clamp_window_geometry(self.ui_preferences.get("geometry") or defaults, self._work_areas)
        self._normal_geometry = geometry
        self.geometry(f"{geometry['width']}x{geometry['height']}")
        area_width = max(area[2]-area[0] for area in self._work_areas)
        area_height = max(area[3]-area[1] for area in self._work_areas)
        self.minsize(min(round(900*scale), area_width-32), min(round(560*scale), area_height-64))
        self.after_idle(lambda: self._restore_window_position(geometry))

    def _restore_window_position(self, geometry):
        if self._closing:
            return
        try:
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            handle = user32.GetAncestor(self.winfo_id(), 2)
            user32.SetWindowPos(handle, None, geometry["x"], geometry["y"], 0, 0, 0x0015)
        except (AttributeError, OSError):
            self.geometry(f"{geometry['width']}x{geometry['height']}{geometry['x']:+d}{geometry['y']:+d}")
        if self.ui_preferences.get("maximized", True) is True:
            self.state("zoomed")

    def _remember_window_geometry(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self.state() == "normal" and self.winfo_width() > 100:
            self._normal_geometry = {"width": self.winfo_width(), "height": self.winfo_height(),
                                     "x": self.winfo_x(), "y": self.winfo_y()}
        if hasattr(self, "maximize_button"):
            self.maximize_button.configure(text="Restore window" if self.state() == "zoomed" else "Maximize window")

    def toggle_maximized(self, _event=None):
        self.state("normal" if self.state() == "zoomed" else "zoomed")
        return "break"

    def _register_widget_locks(self, widget, lock_names, quick=False):
        bucket = self.quick_action_widgets if quick else self.lockable_widgets
        for lock_name in [name for name in lock_names if name]:
            bucket.setdefault(lock_name, []).append(widget)
            self.widget_lock_dependencies.setdefault(widget, set()).add(lock_name)

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL_2)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("SelectedCard.TFrame", background="#1b2d49")
        style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 18))
        style.configure("CompactHeader.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 13))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Draft.TLabel", background=BG, foreground="#f2cd70")
        # Clam's inherited active background is pale; keep light toggle text
        # legible while hovering, keyboard-focusing or disabling a control.
        for toggle_style in ("TCheckbutton", "TRadiobutton"):
            style.configure(toggle_style, background=BG, foreground=TEXT)
            style.map(toggle_style, background=[("disabled", BG), ("active", PANEL_2)],
                      foreground=[("disabled", MUTED), ("active", TEXT)])
        style.configure("CardTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("CardBody.TLabel", background=PANEL, foreground=MUTED)
        style.configure("SectionTitle.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI Semibold", 10))
        style.configure("SectionHint.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Accent.TButton", background=ACCENT, foreground="#08101d")
        style.configure("SwitchPrepare.TButton", background="#f2cd70", foreground="#17202b", padding=(10, 5))
        style.map("SwitchPrepare.TButton", background=[("active", "#ffe3a0")])
        style.configure("SwitchRun.TButton", background="#8ce0b5", foreground="#10241c", padding=(10, 5))
        style.map("SwitchRun.TButton", background=[("active", "#b4f3d2")])
        style.map("Accent.TButton", background=[("active", "#87bfff")])
        style.configure("Nav.TButton", background="#0f172a", foreground=TEXT, padding=(8, 4), bordercolor=BORDER)
        style.map("Nav.TButton", background=[("active", "#1f314d")], foreground=[("active", TEXT)])
        style.configure("SelectedNav.TButton", background="#1d4b87", foreground=TEXT, padding=(8, 4), bordercolor=ACCENT)
        style.map("SelectedNav.TButton", background=[("active", "#2563a8")], foreground=[("active", TEXT)])
        style.configure("Quiet.TButton", background=PANEL, foreground=MUTED, padding=(8, 4), bordercolor=BORDER)
        style.map("Quiet.TButton", background=[("active", "#1a2639")], foreground=[("active", TEXT)])
        style.configure("TButton", background=PANEL_2, foreground=TEXT, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)], selectbackground=[("readonly", PANEL_2)], selectforeground=[("readonly", TEXT)])
        style.map("TButton", background=[("active", "#21324c")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.layout("Workspace.TNotebook.Tab", [])
        style.configure("TNotebook.Tab", background=PANEL_2, foreground=MUTED, padding=(10, 6))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", TEXT)])
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, bordercolor=BORDER,
                        rowheight=tkfont.nametofont("TkDefaultFont").metrics("linespace") + round(6 * ui_scale(self)))
        style.configure("Treeview.Heading", background=PANEL_2, foreground=TEXT)
        style.map("Treeview", background=[("selected", "#1d4b87")], foreground=[("selected", TEXT)])

    def _configure_window_icon(self):
        # Preserve the original Tk feather icon by not overriding the window icon.
        self.window_icon_image = None

    def _load_runtime_orb_assets(self):
        if not RUNTIME_STATUS_ICON_PATH.exists():
            return
        try:
            if Image is not None and ImageTk is not None:
                base = Image.open(RUNTIME_STATUS_ICON_PATH).convert("RGBA").resize((30, 30))
                self.runtime_orb_static_image = ImageTk.PhotoImage(base)
                self.runtime_orb_frames = [
                    ImageTk.PhotoImage(base.rotate(-angle, resample=Image.BICUBIC))
                    for angle in range(0, 360, 45)
                ]
                return
        except Exception:
            self.runtime_orb_static_image = None
            self.runtime_orb_frames = []
        try:
            self.runtime_orb_static_image = tk.PhotoImage(file=str(RUNTIME_STATUS_ICON_PATH))
        except Exception:
            self.runtime_orb_static_image = None

    def _stop_runtime_orb_animation(self):
        if self.runtime_orb_after is not None:
            self.after_cancel(self.runtime_orb_after)
            self.runtime_orb_after = None
        if self.runtime_orb_button is not None:
            self.runtime_orb_button.configure(image=self.runtime_orb_static_image or "", text="" if self.runtime_orb_static_image else "Status")

    def _tick_runtime_orb_animation(self):
        if self.runtime_orb_button is None or not self.runtime_orb_frames:
            return
        frame = self.runtime_orb_frames[self.runtime_orb_frame_index % len(self.runtime_orb_frames)]
        self.runtime_orb_button.configure(image=frame, text="")
        self.runtime_orb_frame_index = (self.runtime_orb_frame_index + 1) % len(self.runtime_orb_frames)
        self.runtime_orb_after = self.after(RUNTIME_ICON_FRAME_MS, self._tick_runtime_orb_animation)

    def _start_runtime_orb_animation(self):
        if not self.runtime_orb_frames or self.runtime_orb_button is None:
            return
        if self.runtime_orb_after is not None:
            return
        self.runtime_orb_frame_index = 0
        self._tick_runtime_orb_animation()

    def _cancel_runtime_orb_click(self):
        if self.runtime_orb_click_after is not None:
            self.after_cancel(self.runtime_orb_click_after)
            self.runtime_orb_click_after = None

    def _handle_runtime_orb_single_click(self):
        self.runtime_orb_click_after = None
        snapshot = decorate_state_processes(self.state_cache or {})
        runtime_active = bool(((snapshot.get("processes", {}) or {}).get("runtime", {}) or {}).get("active", False))
        if runtime_active:
            self.send_raw("SHOW_RUNTIME()")
        else:
            self.refresh_now()

    def _queue_runtime_orb_click(self, _event=None):
        if time.monotonic() < self.runtime_orb_single_click_suppressed_until:
            return "break"
        self._cancel_runtime_orb_click()
        self.runtime_orb_click_after = self.after(220, self._handle_runtime_orb_single_click)
        return "break"

    def _handle_runtime_orb_double_click(self, _event=None):
        self._cancel_runtime_orb_click()
        self.runtime_orb_single_click_suppressed_until = time.monotonic() + 0.4
        snapshot = decorate_state_processes(self.state_cache or {})
        processes = snapshot.get("processes", {}) or {}
        runtime_active = bool((processes.get("runtime", {}) or {}).get("active", False))
        client_active = bool((snapshot.get("modes", {}) or {}).get("live", False))

        if runtime_active and client_active:
            self.send_raw("SET_LIVE_MODE(off)")
            self.after(650, self.refresh_now)
            self.after(1800, self.refresh_now)
            return "break"

        activation_plan = get_runtime_activation_plan(snapshot)
        for command in activation_plan["commands"]:
            self.send_raw(command)

        if not runtime_active:
            try:
                launch_runtime_process(with_ui=True)
            except Exception as error:
                messagebox.showerror("Aurora 2", str(error), parent=self)
                return "break"

        self.after(800, self.refresh_now)
        self.after(2600, self.refresh_now)
        return "break"

    def start_or_enable_runtime(self):
        """Start paused from the primary button; preserve the legacy orb profile path."""
        snapshot = decorate_state_processes(self.state_cache or {})
        active = bool(snapshot.get("processes", {}).get("runtime", {}).get("active", False))
        if active:
            self.send_raw("SET_LIVE_MODE(on)")
        else:
            try:
                launch_runtime_process(with_ui=False, paused=True)
                self.conversation_delivery_var.set("Starting runtime with inference paused. Inspect settings, then Enable inference for paid replies.")
            except Exception as error:
                self.conversation_delivery_var.set(f"Could not start runtime ({type(error).__name__}). See README_FOR_HUMANS.md for setup.")
        self.after(650, self.refresh_now)
        self.after(1800, self.refresh_now)

    def _build_runtime_status_strip(self, outer):
        self._load_runtime_orb_assets()
        status = self.runtime_status_frame = ttk.Frame(outer, style="Card.TFrame", padding=(10, 8))
        self.runtime_orb_button = ttk.Button(status, text="Runtime" if self.runtime_orb_static_image is None else "",
            image=self.runtime_orb_static_image, width=8)
        self.runtime_orb_button.pack(side="left", padx=(0, 8))
        self.runtime_orb_button.bind("<ButtonRelease-1>", self._queue_runtime_orb_click)
        self.runtime_orb_button.bind("<Double-Button-1>", self._handle_runtime_orb_double_click)
        ttk.Label(status, textvariable=self.runtime_status_var, style="CardTitle.TLabel").pack(side="left", padx=(0, 12))
        detail = ttk.Label(status, textvariable=self.compact_status_var, style="CardBody.TLabel", wraplength=900, justify="left", cursor="hand2", takefocus=True)
        detail.pack(side="left", fill="x", expand=True)
        bind_label_wrap(detail)
        detail.bind("<Button-1>", lambda _event: self.switchboard.focus_models())
        detail.bind("<Return>", lambda _event: self.switchboard.focus_models())
        self.runtime_status_detail = detail
        actions = self.runtime_actions = FlowBar(outer)
        self.runtime_activate_button = actions.add(ttk.Button(actions, text="Start runtime", command=self.start_or_enable_runtime))
        self.runtime_deactive_button = actions.add(ttk.Button(actions, text="Pause inference", command=lambda: self.send_raw("SET_LIVE_MODE(off)")))
        self.runtime_cancel_button = actions.add(ttk.Button(actions, text="Cancel work", command=lambda: self.send_raw("CANCEL_ACTIVE_WORK()")))
        self.runtime_shutdown_button = actions.add(ttk.Button(actions, text="Stop runtime", command=lambda: self.send_raw("SHUTDOWN_RUNTIME()")))
        self.header_reset_button = actions.add(ttk.Button(actions, text="Reset to preview defaults", command=lambda: self.switchboard.open_defaults()))
        capture = actions.add(ttk.Button(actions, text="Capture now", command=lambda: self.send_raw("REQUEST_SCREENSHOT_CAPTURE(control_panel)")))
        self._register_widget_locks(capture, ["screenshot_interval"], quick=True)
        self.header_options_button = actions.add(ttk.Menubutton(actions, text="Panel options ▾"))
        menu = tk.Menu(self.header_options_button, tearoff=False)
        menu.add_checkbutton(label="Compact header", variable=self.compact_header_var, command=self._apply_header_layout)
        menu.add_separator()
        menu.add_command(label="Runtime details", command=self.open_banner_dialog)
        menu.add_command(label="Advanced settings", command=self.toggle_settings_pane)
        menu.add_command(label="Maximize / restore window", command=self.toggle_maximized)
        menu.add_separator()
        menu.add_command(label="Reset to preview defaults…", command=lambda: self.switchboard.open_defaults())
        self.header_options_button.configure(menu=menu)

    def _apply_header_layout(self):
        """Presentation preference only; keep the full header and every control reachable."""
        compact = self.compact_header_var.get()
        self.ui_preferences["compact_header"] = compact
        self.header_title.configure(style="CompactHeader.TLabel" if compact else "Header.TLabel")
        self.runtime_status_detail.configure(textvariable=self.header_status_var if compact else self.compact_status_var)
        self.runtime_status_frame.configure(padding=(6, 2) if compact else (10, 8))
        self.runtime_status_frame.grid(row=0 if compact else 1, column=1 if compact else 0,
                                       columnspan=1 if compact else 3, sticky="ew", padx=(0, 8) if compact else 0)
        self.runtime_actions.grid(row=1 if compact else 2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        if compact:
            self.header_utilities.grid_remove()
        else:
            self.header_utilities.grid()
        self.runtime_actions.set_visible(self.header_reset_button, not compact)

    def _sync_refresh_health_visibility(self, *_args):
        if self.refresh_health_var.get():
            if not self.refresh_health_label.winfo_manager():
                self.refresh_health_label.pack(fill="x", pady=(0, 2), after=self.header_frame)
        else:
            self.refresh_health_label.pack_forget()

    def _build_ui(self):
        shell = ttk.Frame(self, padding=10)
        shell.pack(fill="both", expand=True)
        titlebar = self.header_frame = ttk.Frame(shell)
        titlebar.pack(fill="x", pady=(0, 6))
        titlebar.columnconfigure(1, weight=1)
        self.header_title = ttk.Label(titlebar, text="Aurora 2", style="Header.TLabel")
        self.header_title.grid(row=0, column=0, sticky="w", padx=(0, 12))
        utilities = self.header_utilities = FlowBar(titlebar)
        utilities.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        utilities.add(ttk.Button(utilities, text="Runtime details", command=self.open_banner_dialog))
        self.settings_toggle_button = utilities.add(ttk.Button(utilities, text="Advanced settings", command=self.toggle_settings_pane))
        self.maximize_button = utilities.add(ttk.Button(utilities, text="Maximize window", command=self.toggle_maximized))
        from aurora_chatgpt_panel import SignInButtons
        self.signin_buttons = SignInButtons(titlebar, self, ROOT)
        self.signin_buttons.grid(row=0, column=2, sticky="e")
        self._build_runtime_status_strip(titlebar)
        self._apply_header_layout()
        self.refresh_health_label = ttk.Label(shell, textvariable=self.refresh_health_var, style="Muted.TLabel", wraplength=900)
        bind_label_wrap(self.refresh_health_label)
        self.refresh_health_var.trace_add("write", self._sync_refresh_health_visibility)

        navigation = FlowBar(shell)
        navigation.pack(fill="x", pady=(4, 6))
        navigation.add(ttk.Label(navigation, text="View", style="Muted.TLabel"))
        self.focus_combo = navigation.add(ttk.Combobox(navigation, textvariable=self.focus_tab_var, width=30))
        self.focus_combo.bind("<<ComboboxSelected>>", self._navigate_from_selector)
        self.focus_combo.bind("<Return>", self._navigate_from_selector)
        self.focus_combo.bind("<KeyRelease>", self._filter_view_choices)
        self.focus_combo.bind("<Escape>", lambda _event: self._sync_focus_nav_state())
        for label in ("The Switchboard", "Dashboard", "Screenshots"):
            button = navigation.add(ttk.Button(navigation, text=label, style="Nav.TButton", command=lambda target=label: self.show_tab(target)))
            self.focus_nav_buttons[label] = button
        navigation.add(PortalShortcuts(navigation, self, ROOT))


        self.content_panes = ttk.Panedwindow(shell, orient="horizontal")
        self.content_panes.pack(fill="both", expand=True)
        self.settings_view = ScrollablePane(self.content_panes, background=PANEL, padding=10)
        self.settings_view.configure(width=600, height=200)
        self.settings_view.grid_propagate(False)
        self.left_inner, self.left_canvas = self.settings_view.inner, self.settings_view.canvas
        self.left_scrollbar = self.settings_view.vertical
        settings_tools = FlowBar(self.left_inner)
        settings_tools.pack(fill="x", pady=(0, 6))
        self.settings_expand_button = settings_tools.add(ttk.Button(settings_tools, text="Expand settings", command=self.toggle_expanded_settings))
        settings_tools.add(ttk.Button(settings_tools, text="Expand all", command=lambda: self._expand_all_settings(True)))
        settings_tools.add(ttk.Button(settings_tools, text="Collapse all", command=lambda: self._expand_all_settings(False)))
        settings_tools.add(ttk.Button(settings_tools, text="Reload observed", command=self.reload_observed_settings))
        self.settings_filter_var = tk.StringVar()
        filter_row = ttk.Frame(self.left_inner)
        filter_row.pack(fill="x", pady=(0, 4))
        ttk.Label(filter_row, text="Find settings", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self.settings_filter_entry = ttk.Entry(filter_row, textvariable=self.settings_filter_var)
        self.settings_filter_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(filter_row, text="Clear", command=lambda: self.settings_filter_var.set("")).pack(side="left", padx=(6, 0))
        self.settings_edit_status_var = tk.StringVar(value="Values follow the runtime until edited.")
        ttk.Label(self.left_inner, textvariable=self.settings_edit_status_var, style="Muted.TLabel").pack(fill="x")
        self._build_quick_controls(self.left_inner)
        self._build_sidebar_runtime_details(self.left_inner)
        self._build_settings_card(self.left_inner)
        from aurora_agent_controls import AgentControls
        self.agent_controls = AgentControls(shell, self)
        self.agent_controls.pack(fill="x", pady=(0, 4), before=self.content_panes)
        self._build_feedback_card(self.left_inner)
        for section in self.settings_sections:
            section.index_labels()
        self.settings_filter_var.trace_add("write", self._filter_settings_sections)

        self.workspace_frame = ttk.Frame(self.content_panes, width=420, height=200)
        self.workspace_frame.pack_propagate(False)
        self.notebook = ttk.Notebook(self.workspace_frame, style="Workspace.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.notebook.enable_traversal()
        self._build_overview_tab()
        self._build_dashboard_tab()
        self._build_memory_tab()
        self._build_episodic_tab()
        self._build_pending_tab()
        self._build_command_drip_tab()
        self._build_chat_tab()
        self._build_conversation_tab()
        self._build_switchboard_tab()
        self._build_command_tab()
        self._build_prompt_ledger_tab()
        self._build_agents_tab()
        self._build_history_context_tab()
        self._build_portal_intake_tab()
        self._build_visual_context_tab()
        self._build_image_context_index_tab()
        self._build_live_harness_tab()
        self._build_responses_shadow_tab()
        self._build_context_files_tab()
        self._build_settings_safety_tab()
        self._build_screenshots_tab()
        self._build_image_memory_tab()
        self._build_help_tab()
        self._build_raw_tab()
        wrap_packed_labels(self.notebook)

        names = [self.notebook.tab(tab, "text") for tab in self.notebook.tabs()]
        self.focus_tab_by_label = {name: name for name in names}
        self.focus_label_by_tab = dict(self.focus_tab_by_label)
        self.focus_combo.configure(values=names)
        self.notebook.bind("<<NotebookTabChanged>>", self._sync_focus_nav_state)
        self._apply_settings_mode(self.ui_preferences.get("settings_mode", "hidden"))
        self.content_panes.bind("<Configure>", self._schedule_sash_clamp)
        self.content_panes.bind("<Map>", self._schedule_sash_clamp, add="+")
        self.settings_view.bind("<Map>", self._schedule_sash_clamp, add="+")
        self.content_panes.bind("<ButtonRelease-1>", self._remember_sash)
        initial_view = self.ui_preferences.get("active_view", "Conversation") if self.ui_preferences.get("restore_last_view", False) else "Conversation"
        if not self.show_tab(initial_view):
            self.show_tab("Conversation")
        self.bind_all("<MouseWheel>", self._on_main_mousewheel, add="+")
        self.bind_all("<Shift-MouseWheel>", self._on_main_mousewheel, add="+")
        self._protect_unfocused_combobox_wheel(self)

    def _new_work_page(self, title):
        page = ScrollablePane(self.notebook, background=BG, padding=10, fit_width=title in {"Dashboard", "Conversation", "The Switchboard"})
        self.notebook.add(page, text=title)
        self.page_views[title] = page
        return page.inner

    def _new_settings_section(self, parent, title):
        states = self.ui_preferences.get("sections", {})
        expanded = states.get(title, True) if isinstance(states, dict) else True
        section = CollapsibleSection(parent, title, expanded=expanded is not False, on_change=self._remember_section)
        section.pack(fill="x")
        self.settings_sections.append(section)
        return section

    def _remember_section(self, title, expanded):
        states = self.ui_preferences.get("sections")
        if not isinstance(states, dict):
            states = self.ui_preferences["sections"] = {}
        states[title] = expanded

    def _expand_all_settings(self, expanded):
        self.settings_filter_var.set("")
        for section in self.settings_sections:
            section.set_expanded(expanded)

    def _filter_settings_sections(self, *_args):
        query = self.settings_filter_var.get().strip().casefold()
        states = self.ui_preferences.get("sections", {})
        states = states if isinstance(states, dict) else {}
        for section in self.settings_sections:
            section.pack_forget()
            if not query or query in section.search_text:
                if section.master is self.left_inner:
                    section.pack(fill="x", before=self.settings_card_container)
                else:
                    section.pack(fill="x")
                section.set_expanded(True if query else states.get(section.title, True), remember=False)
        self.settings_view.reveal_top()

    def _build_sidebar_runtime_details(self, parent):
        section = self._new_settings_section(parent, "Runtime detail and banner")
        for variable in (self.runtime_client_var, self.runtime_orb_note_var, self.runtime_mode_spec_var,
                         self.runtime_model_spec_var, self.runtime_activation_hint_var):
            ttk.Label(section.body, textvariable=variable, wraplength=620, justify="left", style="CardBody.TLabel").pack(fill="x", pady=2)
        self.banner_auto_scroll_var = tk.BooleanVar(value=self.ui_preferences.get("banner_auto_scroll", False) is True)
        self.runtime_banner_canvas = tk.Canvas(section.body, bg=BG, height=30, highlightthickness=0)
        self.runtime_banner_canvas.pack(fill="x", pady=(4, 0))
        self.runtime_banner_canvas.bind("<Configure>", lambda _event: self._render_runtime_banner(reset=False))
        self.runtime_banner_canvas.bind("<Double-Button-1>", lambda _event: self.open_banner_dialog())
        controls = FlowBar(section.body)
        controls.pack(fill="x")
        controls.add(ttk.Checkbutton(controls, text="Animate banner", variable=self.banner_auto_scroll_var, command=self._on_banner_autoscroll_toggle))
        controls.add(ttk.Button(controls, text="<", width=3, command=lambda: self._adjust_banner_offset(-120)))
        controls.add(ttk.Button(controls, text=">", width=3, command=lambda: self._adjust_banner_offset(120)))
        controls.add(ttk.Button(controls, text="Full banner", command=self.open_banner_dialog))

    def _build_quick_controls(self, parent):
        actions = self._new_settings_section(parent, "Quick controls").body
        actions.columnconfigure(0, weight=1)
        def register_quick_button(lock_name, widget):
            self._register_widget_locks(widget, [lock_name], quick=True)

        def add_quick_group(parent, title, buttons, row, columns=4):
            group = ttk.Frame(parent)
            group.grid(row=row, column=0, sticky="ew", pady=(0, 6))
            group.columnconfigure(1, weight=1)
            ttk.Label(group, text=title, style="Muted.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 8), pady=(6, 0))
            button_frame = ttk.Frame(group)
            button_frame.grid(row=0, column=1, sticky="ew")
            for column in range(columns):
                button_frame.columnconfigure(column, weight=1, uniform=f"quick-{row}")
            for index, (label, command, style_name, lock_name) in enumerate(buttons):
                widget = ttk.Button(button_frame, text=label, command=lambda c=command: self.send_raw(c), style=style_name)
                widget.grid(row=index // columns, column=index % columns, sticky="ew", padx=(0, 4), pady=(0, 4))
                register_quick_button(lock_name, widget)

        add_quick_group(
            actions,
            "Mode",
            [
                ("Live On", "SET_LIVE_MODE(on)", "Accent.TButton", "live"),
                ("Live Off", "SET_LIVE_MODE(off)", "TButton", "live"),
                ("Safe", "SET_EXECUTION_MODE(safe)", "TButton", "execution"),
                ("Assist", "SET_EXECUTION_MODE(assist)", "TButton", "execution"),
                ("Auto", "SET_EXECUTION_MODE(auto)", "TButton", "execution"),
                ("GB", "GB_MODE()", "TButton", "action"),
                ("PYAG", "PYAG_MODE()", "TButton", "action"),
            ],
            row=0,
            columns=3,
        )
        add_quick_group(
            actions,
            "Inspect",
            [
                ("Runtime", "SHOW_RUNTIME()", "TButton", None),
                ("Health", "SHOW_RUNTIME_HEALTH()", "TButton", None),
                ("Risk", "SHOW_OPERATOR_RISK_SUMMARY()", "TButton", None),
                ("Monitor", "SHOW_MONITOR_STATUS()", "TButton", None),
                ("Checkpoint", "SHOW_CHECKPOINT_READINESS()", "TButton", None),
                ("Auth", "SHOW_AUTH()", "TButton", None),
                ("Locks", "SHOW_LOCKS()", "TButton", None),
                ("Capture Now", "REQUEST_SCREENSHOT_CAPTURE(control_panel)", "TButton", "screenshot_interval"),
            ],
            row=1,
            columns=3,
        )
        utility_row = ttk.Frame(actions)
        utility_row.grid(row=2, column=0, sticky="ew")
        add_quick_group(utility_row, "Access", [("Login OAuth", "LOGIN_CODEX_OAUTH()", "TButton", None)], row=0, columns=1)
        self.chat_head_toggle_canvas = tk.Canvas(
            utility_row,
            width=68,
            height=34,
            bg=BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.chat_head_toggle_canvas.grid(row=0, column=1, padx=(12, 6), sticky="w")
        self.chat_head_toggle_canvas.bind("<Button-1>", self.toggle_chat_head_request)
        self._draw_chat_head_toggle_button(False)
        ttk.Button(utility_row, text="Help", command=self.show_help_tab, style="Quiet.TButton").grid(row=0, column=2, padx=(12, 6), sticky="ew")
        ttk.Button(utility_row, text="Commands", command=self.show_command_list, style="Quiet.TButton").grid(row=0, column=3, sticky="ew")


    def _on_main_mousewheel(self, event):
        widget = event.widget
        try:
            if widget.winfo_class() in {"Text", "Treeview", "Listbox", "TCombobox", "Combobox", "Entry", "TEntry", "Spinbox"}:
                return
            return self._scroll_ancestor(widget, event)
        except tk.TclError:
            return

    def _scroll_ancestor(self, widget, event):
        while widget is not None:
            owner = getattr(widget, "_aurora_scroll_owner", None)
            if owner is not None:
                if not event.delta:
                    return "break"
                steps = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
                if event.state & 0x0001:
                    owner.canvas.xview_scroll(steps, "units")
                else:
                    owner.canvas.yview_scroll(steps, "units")
                return "break"
            widget = getattr(widget, "master", None)

    def _protect_unfocused_combobox_wheel(self, parent):
        for widget in parent.winfo_children():
            if widget.winfo_class() in {"TCombobox", "Combobox", "Spinbox", "TSpinbox"}:
                widget.bind("<MouseWheel>", self._on_combobox_mousewheel, add="+")
            self._protect_unfocused_combobox_wheel(widget)

    def _on_combobox_mousewheel(self, event):
        if self.focus_get() is not event.widget:
            return self._scroll_ancestor(event.widget, event) or "break"

    def _apply_settings_mode(self, mode):
        mode = mode if mode in {"hidden", "docked", "expanded"} else "hidden"
        if self.settings_mode == "docked" and len(self.content_panes.panes()) == 2:
            self.ui_preferences["sash"] = self.content_panes.sashpos(0)
        for pane in self.content_panes.panes():
            self.content_panes.forget(pane)
        if mode != "hidden":
            self.content_panes.add(self.settings_view, weight=2)
        if mode != "expanded":
            self.content_panes.add(self.workspace_frame, weight=3)
        self.settings_mode = mode
        self.settings_toggle_button.configure(text="Advanced settings" if mode == "hidden" else "Hide settings")
        self.settings_expand_button.configure(text="Dock settings" if mode == "expanded" else "Expand settings")
        self._schedule_sash_clamp()

    def toggle_settings_pane(self, _event=None):
        self._apply_settings_mode("expanded" if self.settings_mode == "hidden" else "hidden")
        return "break"

    def toggle_expanded_settings(self):
        self._apply_settings_mode("docked" if self.settings_mode == "expanded" else "expanded")

    def _schedule_sash_clamp(self, _event=None):
        if not self._closing and self._sash_after_id is None:
            self._sash_after_id = self.after(40, self._clamp_settings_sash)

    def _clamp_settings_sash(self):
        self._sash_after_id = None
        if self.settings_mode != "docked" or len(self.content_panes.panes()) != 2:
            return
        width = self.content_panes.winfo_width()
        if width < 100:
            return
        desired = self.ui_preferences.get("sash", 600)
        desired = desired if type(desired) is int else 600
        lower = min(400, width // 2)
        upper = max(lower, width - 420)
        self.content_panes.sashpos(0, max(lower, min(desired, upper)))

    def _remember_sash(self, _event=None):
        if self.settings_mode == "docked" and len(self.content_panes.panes()) == 2:
            self.ui_preferences["sash"] = self.content_panes.sashpos(0)
            self._schedule_sash_clamp()

    def _navigate_from_selector(self, _event=None):
        query = self.focus_tab_var.get().strip().casefold()
        matches = [name for name in self.focus_tab_by_label if query in name.casefold()]
        exact = next((name for name in matches if name.casefold() == query), None)
        target = exact or (matches[0] if len(matches) == 1 else None)
        if target:
            self.show_tab(target)
        return "break"

    def _filter_view_choices(self, event=None):
        if event is not None and event.keysym in {"Return", "Escape", "Up", "Down", "Tab"}:
            return
        query = self.focus_tab_var.get().strip().casefold()
        self.focus_combo.configure(values=[name for name in self.focus_tab_by_label if query in name.casefold()])

    def _focus_view_selector(self, _event=None):
        self.focus_combo.focus_set()
        self.focus_combo.selection_range(0, tk.END)
        self.focus_combo.configure(values=list(self.focus_tab_by_label))
        return "break"

    def _build_settings_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x")
        self.settings_card_container = card
        self.security_status_var = tk.StringVar(value="Operator security: off")
        self.setting_safety_status_var = tk.StringVar(value="Settings safety map is ready.")
        ttk.Label(card, text="Runtime Controls", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.lock_summary_label = ttk.Label(card, text="Locks: none", style="CardBody.TLabel")
        self.lock_summary_label.pack(anchor="w", pady=(0, 8))
        self.security_summary_label = ttk.Label(card, textvariable=self.security_status_var, style="CardBody.TLabel")
        self.security_summary_label.pack(anchor="w", pady=(0, 8))
        safety_row = ttk.Frame(card)
        safety_row.pack(fill="x", pady=(0, 8))
        ttk.Label(
            safety_row,
            textvariable=self.setting_safety_status_var,
            style="CardBody.TLabel",
            wraplength=300,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(safety_row, text="Recovery Map", command=lambda: self.show_tab("Recovery")).pack(side="left", padx=(8, 0))
        label_width = 18

        section_parent = card
        def add_section(title, hint=None):
            nonlocal card
            card = self._new_settings_section(section_parent, title).body
            if hint:
                ttk.Label(card, text=hint, style="SectionHint.TLabel", wraplength=620,
                          justify="left").pack(anchor="w", pady=(0, 6))

        self.auth_var = tk.StringVar()
        self.exec_var = tk.StringVar()
        self.action_var = tk.StringVar()
        self.game_profile_var = tk.StringVar(value="firered")
        self.text_model_var = tk.StringVar()
        self.model_transport_var = tk.StringVar(value="chat_completions")
        self.vision_model_var = tk.StringVar()
        self.reasoning_model_var = tk.StringVar()
        self.model_verbosity_var = tk.StringVar()
        self.reasoning_effort_var = tk.StringVar()
        self.battle_effort_var = tk.StringVar()
        self.review_effort_var = tk.StringVar()
        self.critique_effort_var = tk.StringVar()
        self.reasoning_summary_var = tk.StringVar()
        self.review_verbosity_var = tk.StringVar()
        self.battle_verbosity_var = tk.StringVar()
        self.critique_verbosity_var = tk.StringVar()
        self.temperature_var = tk.StringVar()
        self.interval_var = tk.StringVar()
        self.review_turn_interval_var = tk.StringVar()
        self.critique_turn_interval_var = tk.StringVar()
        self.turn_scheduler_profile_var = tk.StringVar(value="balanced")
        self.turn_scheduler_mode_var = tk.StringVar(value="hybrid")
        self.turn_heartbeat_var = tk.StringVar(value="2.25")
        self.turn_min_gap_var = tk.StringVar(value="0.55")
        self.turn_capture_wake_var = tk.BooleanVar(value=True)
        self.turn_capture_wake_debounce_var = tk.StringVar(value="0.90")
        self.turn_post_action_settle_var = tk.StringVar(value="0.55")
        self.demand_capture_var = tk.BooleanVar(value=True)
        self.scheduler_status_var = tk.StringVar(
            value="Balanced is recommended: event-driven turns plus a calmer capture-change wake."
        )
        self.command_drip_retention_var = tk.StringVar()
        self.command_drip_lookahead_var = tk.StringVar()
        self.pending_queue_mode_var = tk.StringVar(value="normal")
        self.live_var = tk.BooleanVar()
        self.live_init_var = tk.BooleanVar()
        self.sound_var = tk.BooleanVar()
        self.time_logging_var = tk.BooleanVar()
        self.chat_log_echo_var = tk.BooleanVar()
        self.auto_dynamic_var = tk.BooleanVar(value=True)
        self.command_drip_show_variants_var = tk.BooleanVar(value=True)
        self.command_drip_show_likely_dropped_var = tk.BooleanVar(value=True)
        self.tile_grid_var = tk.BooleanVar()
        self.cursor_label_var = tk.BooleanVar()
        self.keypoint_grid_var = tk.BooleanVar()
        self.status_overlay_var = tk.BooleanVar()
        self.auto_prompt_var = tk.BooleanVar()
        self.show_user_text_var = tk.BooleanVar()
        self.show_ai_text_var = tk.BooleanVar()
        self.show_ai_commands_var = tk.BooleanVar()
        self.show_user_commands_var = tk.BooleanVar()
        self.enable_unimportant_messages_var = tk.BooleanVar()
        self.enable_important_messages_var = tk.BooleanVar()
        self.add_umsgs_to_history_var = tk.BooleanVar()
        self.add_imsgs_to_history_var = tk.BooleanVar()
        self.check_umsgs_decay_var = tk.BooleanVar()
        self.check_imsgs_decay_var = tk.BooleanVar()
        self.always_mode_var = tk.StringVar()
        self.hide_input_pref_var = tk.BooleanVar()
        self.image_detail_var = tk.StringVar()
        self.latest_image_detail_var = tk.StringVar()
        self.high_detail_var = tk.StringVar()
        self.max_images_var = tk.StringVar()
        self.chat_head_opacity_var = tk.StringVar(value="0.87")
        self.chat_head_topmost_var = tk.BooleanVar(value=True)
        self.chat_head_strip_width_var = tk.StringVar(value="1000")
        self.chat_head_strip_height_var = tk.StringVar(value="100")
        self.chat_head_history_width_var = tk.StringVar(value="420")
        self.chat_head_history_height_var = tk.StringVar(value="620")
        self.chat_head_send_animation_var = tk.StringVar(value="pulse")
        self.chat_head_send_animation_seconds_var = tk.StringVar(value="0.75")
        self.episodic_enabled_var = tk.BooleanVar(value=True)
        self.episodic_interval_var = tk.StringVar(value="900")
        self.episodic_periodic_var = tk.BooleanVar(value=True)
        self.episodic_scene_var = tk.BooleanVar(value=True)
        self.episodic_backend_var = tk.StringVar(value="auto")
        self.episodic_planning_mode_var = tk.StringVar(value="review_critique")
        self.episodic_planning_k_var = tk.StringVar(value="2")
        self.episodic_planning_cooldown_var = tk.StringVar(value="12")
        self.episodic_embedding_model_var = tk.StringVar(value="text-embedding-3-small")
        self.episodic_status_var = tk.StringVar(value="Episodic memory is ready.")
        self.episodic_query_var = tk.StringVar()
        self.episodic_search_vars = {key: tk.StringVar(value=str(value)) for key, value in SEARCH_DEFAULTS.items()}
        self.episodic_search_vars["value_encoding"].set("json")
        self.episodic_search_vars["feedback_session"].set(f"panel-{os.getpid()}")
        self.episodic_limit_var = tk.StringVar(value="4")
        self.episodic_time_weight_var = tk.StringVar(value="0.50")
        self.episodic_semantic_weight_var = tk.StringVar(value="0.50")
        self.episodic_tag_weight_var = tk.StringVar(value="0.00")
        self.episodic_semantic_tag_weight_var = tk.StringVar(value="0.50")
        self.episodic_time_mode_var = tk.StringVar(value="ordinal")
        self.episodic_score_mode_var = tk.StringVar(value="legacy")
        self.episodic_score_weights = {key: tk.DoubleVar(value=RETRIEVAL_OPTION_DEFAULTS[key]) for key in RETRIEVAL_WEIGHT_KEYS}
        self._episodic_weights_updating = False
        self.episodic_age_half_life_hours_var = tk.StringVar(value="168")
        self.episodic_min_relevance_var = tk.StringVar(value="0")
        self.episodic_embedding_fallback_var = tk.StringVar(value="lexical")
        self.episodic_time_anchor_var = tk.StringVar(value="")
        self.episodic_time_scale_var = tk.StringVar(value="1")
        self.episodic_shape_var = tk.StringVar(value="balanced")
        self.episodic_center_var = tk.StringVar(value="0.00")
        self.episodic_spread_var = tk.StringVar(value="0.22")
        self.episodic_variance_var = tk.StringVar(value="0.00")
        self.episodic_tags_required_var = tk.StringVar()
        self.episodic_tags_preferred_var = tk.StringVar()
        self.episodic_source_buckets_var = tk.StringVar()
        self.episodic_snapshot_reason_var = tk.StringVar()
        self.episodic_snapshot_tags_var = tk.StringVar()
        self.episodic_recent_limit_var = tk.StringVar(value="8")
        self.episodic_promote_index_var = tk.StringVar(value="1")
        self.episodic_promote_target_var = tk.StringVar(value="notes")
        self.episodic_promote_prefix_var = tk.StringVar()
        self.episodic_result_handle_var = tk.StringVar()
        self._episodic_displayed_result_handle = ""
        self.episodic_control_status_var = tk.StringVar(value="Planning assist status loads from Aurora state.")
        self.episodic_tab_planning_status_var = tk.StringVar(value="Planning assist injects bounded retrieval only on configured review/critique turns.")
        self.episodic_retrieval_status_var = tk.StringVar(value="Retrieval preview is ready; Recall sends shorthand over the same query.")
        self.episodic_promotion_status_var = tk.StringVar(value="Promotion copies one retrieval result into a live memory target.")
        self.handoff_file_var = tk.StringVar()
        self.follow_latest_var = tk.BooleanVar(value=True)
        self.command_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.next_reasoning_var = tk.StringVar()
        self.next_verbosity_var = tk.StringVar()
        self.next_summary_var = tk.StringVar()
        self.next_image_detail_var = tk.StringVar()
        self.next_latest_image_detail_var = tk.StringVar()
        self.next_temperature_var = tk.StringVar()
        self.next_model_var = tk.StringVar()
        self.next_note_var = tk.StringVar()
        self.defaults_status_var = tk.StringVar(value="System defaults ready | personal defaults: not saved")
        self.model_cost_status_var = tk.StringVar(value="Model pricing loads from Aurora state.")
        self.model_preset_guide_var = tk.StringVar(value=MODEL_PRESET_GUIDE_TEXT)
        self.next_turn_status_var = tk.StringVar(value="Next-turn override: none queued.")
        self.advanced_context_status_var = tk.StringVar(value="Advanced context controls are ready.")
        self.settings_transaction_version_var = tk.StringVar(value="Settings version: unavailable")
        self.settings_transaction_status_var = tk.StringVar(value="Atomic settings: waiting for runtime state.")
        self.security_required_var = tk.BooleanVar()
        self.show_passcode_commands_var = tk.BooleanVar()
        self.operator_passcode_var = tk.StringVar()

        def register_lock_widget(lock_name, widget):
            self._register_widget_locks(widget, [lock_name], quick=False)

        def register_lock_widgets(lock_names, widget):
            self._register_widget_locks(widget, lock_names, quick=False)

        add_section("Access & Safety", "Passcode and command visibility controls for external operator access.")
        security_row = ttk.Frame(card)
        security_row.pack(fill="x", pady=(0, 8))
        ttk.Label(security_row, text="Security", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Entry(security_row, textvariable=self.operator_passcode_var, show="*", width=18).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(
            security_row,
            text="Require",
            variable=self.security_required_var,
            command=self.apply_operator_security_requirement,
        ).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(
            security_row,
            text="Show Raw Cmds",
            variable=self.show_passcode_commands_var,
            command=self.apply_passcode_command_visibility,
        ).pack(side="left", padx=(0, 10))
        ttk.Button(security_row, text="Set", command=self.set_operator_passcode).pack(side="left")
        ttk.Button(security_row, text="Unlock", command=self.authorize_operator_access).pack(side="left", padx=(6, 0))
        ttk.Button(security_row, text="Lock", command=lambda: self.send_raw("LOCK_OPERATOR_ACCESS()")).pack(side="left", padx=(6, 0))
        ttk.Button(security_row, text="Clear", command=self.clear_operator_passcode).pack(side="left", padx=(6, 0))
        ttk.Button(security_row, text="Show", command=lambda: self.send_raw("SHOW_SECURITY()")).pack(side="left", padx=(6, 0))

        add_section("Modes & Models", "Core runtime mode, action mode, active model, session reasoning defaults, and cadence.")
        controls = [
            ("Auth", self.auth_var, AUTH_MODES),
            ("Execution", self.exec_var, EXECUTION_MODES),
            ("Action", self.action_var, ACTION_MODES),
            ("Game Profile", self.game_profile_var, GAME_PROFILES),
            ("Text Model", self.text_model_var, self.current_model_choices),
            ("Transport", self.model_transport_var, ["chat_completions", "responses"]),
            ("Vision Model", self.vision_model_var, self.current_model_choices),
            ("Reasoning Model", self.reasoning_model_var, self.current_model_choices),
            ("Verbosity", self.model_verbosity_var, VERBOSITIES),
            ("Review Verbosity", self.review_verbosity_var, VERBOSITIES),
            ("Battle Verbosity", self.battle_verbosity_var, VERBOSITIES),
            ("Critique Verbosity", self.critique_verbosity_var, VERBOSITIES),
            ("Session Effort", self.reasoning_effort_var, EFFORTS),
            ("Battle Reasoning", self.battle_effort_var, EFFORTS),
            ("Review Reasoning", self.review_effort_var, EFFORTS),
            ("Critique Reasoning", self.critique_effort_var, EFFORTS),
            ("Summary Mode", self.reasoning_summary_var, SUMMARY_MODES),
        ]
        lock_bindings = {
            "Auth": "auth",
            "Execution": "execution",
            "Action": "action",
            "Game Profile": None,
            "Text Model": "models",
            "Transport": "models",
            "Vision Model": "models",
            "Reasoning Model": "models",
            "Verbosity": "reasoning",
            "Review Verbosity": "reasoning",
            "Battle Verbosity": "reasoning",
            "Critique Verbosity": "reasoning",
            "Session Effort": "reasoning",
            "Battle Reasoning": "reasoning",
            "Review Reasoning": "reasoning",
            "Critique Reasoning": "reasoning",
            "Summary Mode": "reasoning",
        }
        for label, variable, values in controls:
            row = ttk.Frame(card)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="CardBody.TLabel", width=label_width).pack(side="left")
            widget = ttk.Combobox(row, textvariable=variable, values=values, state="readonly")
            widget.pack(side="left", fill="x", expand=True)
            register_lock_widget(lock_bindings[label], widget)
            if label == "Text Model":
                self.text_model_combo = widget
            elif label == "Vision Model":
                self.vision_model_combo = widget
            elif label == "Reasoning Model":
                self.reasoning_model_combo = widget

        add_section("Turn Timing", "Loop cadence, review/critique intervals, and scheduler wake behavior.")
        scalar_lock_bindings = {
            "Temperature": "temperature",
            "Screenshot Interval": "screenshot_interval",
            "Review Turn Interval": "reasoning",
            "Critique Turn Interval": "reasoning",
        }
        for label, variable in [
            ("Temperature", self.temperature_var),
            ("Screenshot Interval", self.interval_var),
            ("Review Turn Interval", self.review_turn_interval_var),
            ("Critique Turn Interval", self.critique_turn_interval_var),
        ]:
            row = ttk.Frame(card)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="CardBody.TLabel", width=label_width).pack(side="left")
            widget = ttk.Entry(row, textvariable=variable)
            widget.pack(side="left", fill="x", expand=True)
            register_lock_widget(scalar_lock_bindings[label], widget)

        scheduler_profile_row = ttk.Frame(card)
        scheduler_profile_row.pack(fill="x", pady=(0, 4))
        ttk.Label(scheduler_profile_row, text="Scheduler Profile", style="CardBody.TLabel", width=label_width).pack(side="left")
        scheduler_profile_combo = ttk.Combobox(
            scheduler_profile_row,
            textvariable=self.turn_scheduler_profile_var,
            values=TURN_SCHEDULER_PROFILE_NAMES,
            state="readonly",
            width=14,
        )
        scheduler_profile_combo.pack(side="left", padx=(0, 10))
        scheduler_profile_combo.bind("<<ComboboxSelected>>", self.on_turn_scheduler_profile_selected)
        register_lock_widget("reasoning", scheduler_profile_combo)
        ttk.Button(
            scheduler_profile_row,
            text="Show",
            command=lambda: self.send_raw("SHOW_TURN_SCHEDULER_PROFILES()"),
        ).pack(side="left")

        scheduler_row = ttk.Frame(card)
        scheduler_row.pack(fill="x", pady=(0, 4))
        ttk.Label(scheduler_row, text="Turn Scheduler", style="CardBody.TLabel", width=label_width).pack(side="left")
        scheduler_combo = ttk.Combobox(
            scheduler_row,
            textvariable=self.turn_scheduler_mode_var,
            values=TURN_SCHEDULER_MODES,
            state="readonly",
            width=12,
        )
        scheduler_combo.pack(side="left", padx=(0, 10))
        scheduler_combo.bind("<<ComboboxSelected>>", self.on_turn_scheduler_leaf_changed)
        register_lock_widget("reasoning", scheduler_combo)
        ttk.Label(scheduler_row, text="Heartbeat", style="CardBody.TLabel").pack(side="left")
        scheduler_heartbeat_entry = ttk.Entry(scheduler_row, textvariable=self.turn_heartbeat_var, width=6)
        scheduler_heartbeat_entry.pack(side="left", padx=(6, 10))
        scheduler_heartbeat_entry.bind("<KeyRelease>", self.on_turn_scheduler_leaf_changed)
        register_lock_widget("reasoning", scheduler_heartbeat_entry)
        ttk.Label(scheduler_row, text="Min Gap", style="CardBody.TLabel").pack(side="left")
        scheduler_gap_entry = ttk.Entry(scheduler_row, textvariable=self.turn_min_gap_var, width=6)
        scheduler_gap_entry.pack(side="left", padx=(6, 10))
        scheduler_gap_entry.bind("<KeyRelease>", self.on_turn_scheduler_leaf_changed)
        register_lock_widget("reasoning", scheduler_gap_entry)
        capture_wake_widget = ttk.Checkbutton(
            scheduler_row,
            text="Capture Wake",
            variable=self.turn_capture_wake_var,
            command=self.on_turn_scheduler_leaf_changed,
        )
        capture_wake_widget.pack(side="left", padx=(0, 10))
        register_lock_widget("reasoning", capture_wake_widget)
        ttk.Label(scheduler_row, text="Debounce", style="CardBody.TLabel").pack(side="left")
        scheduler_debounce_entry = ttk.Entry(
            scheduler_row,
            textvariable=self.turn_capture_wake_debounce_var,
            width=6,
        )
        scheduler_debounce_entry.pack(side="left", padx=(6, 0))
        scheduler_debounce_entry.bind("<KeyRelease>", self.on_turn_scheduler_leaf_changed)
        register_lock_widget("reasoning", scheduler_debounce_entry)

        scheduler_settle_row = ttk.Frame(card)
        scheduler_settle_row.pack(fill="x", pady=(0, 6))
        ttk.Label(scheduler_settle_row, text="Turn Timing", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(scheduler_settle_row, text="Post Action Settle", style="CardBody.TLabel").pack(side="left")
        scheduler_settle_entry = ttk.Entry(
            scheduler_settle_row,
            textvariable=self.turn_post_action_settle_var,
            width=6,
        )
        scheduler_settle_entry.pack(side="left", padx=(6, 10))
        scheduler_settle_entry.bind("<KeyRelease>", self.on_turn_scheduler_leaf_changed)
        register_lock_widget("reasoning", scheduler_settle_entry)
        demand_capture_widget = ttk.Checkbutton(
            scheduler_settle_row,
            text="Demand Capture",
            variable=self.demand_capture_var,
        )
        demand_capture_widget.pack(side="left", padx=(0, 10))
        register_lock_widget("screenshot_interval", demand_capture_widget)

        ttk.Label(
            card,
            textvariable=self.scheduler_status_var,
            style="CardBody.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Command Queue", "Pending-command retention, lookahead, and queue display controls.")
        drip_row = ttk.Frame(card)
        drip_row.pack(fill="x", pady=(0, 6))
        ttk.Label(drip_row, text="Command Drip", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(drip_row, text="Retention", style="CardBody.TLabel").pack(side="left")
        drip_retention_entry = ttk.Entry(drip_row, textvariable=self.command_drip_retention_var, width=6)
        drip_retention_entry.pack(side="left", padx=(6, 10))
        ttk.Label(drip_row, text="Lookahead", style="CardBody.TLabel").pack(side="left")
        drip_lookahead_entry = ttk.Entry(drip_row, textvariable=self.command_drip_lookahead_var, width=6)
        drip_lookahead_entry.pack(side="left", padx=(6, 10))
        ttk.Button(drip_row, text="Show", command=lambda: self.send_raw("SHOW_COMMAND_DRIP()")).pack(side="left")
        register_lock_widget("reasoning", drip_retention_entry)
        register_lock_widget("reasoning", drip_lookahead_entry)

        drip_mode_row = ttk.Frame(card)
        drip_mode_row.pack(fill="x", pady=(0, 6))
        ttk.Label(drip_mode_row, text="Queue Mode", style="CardBody.TLabel", width=label_width).pack(side="left")
        pending_queue_combo = ttk.Combobox(
            drip_mode_row,
            textvariable=self.pending_queue_mode_var,
            values=PENDING_QUEUE_MODES,
            state="readonly",
            width=12,
        )
        pending_queue_combo.pack(side="left", padx=(0, 12))
        register_lock_widget("execution", pending_queue_combo)
        variants_widget = ttk.Checkbutton(
            drip_mode_row,
            text="Variants",
            variable=self.command_drip_show_variants_var,
        )
        variants_widget.pack(side="left", padx=(0, 10))
        register_lock_widget("reasoning", variants_widget)
        likely_dropped_widget = ttk.Checkbutton(
            drip_mode_row,
            text="Likely Dropped",
            variable=self.command_drip_show_likely_dropped_var,
        )
        likely_dropped_widget.pack(side="left", padx=(0, 10))
        register_lock_widget("reasoning", likely_dropped_widget)
        ttk.Label(
            card,
            text=(
                "Queue lane: pending commands are held plans. normal keeps candidates in place; "
                "insert claims the next slot and defers later pending entries; replace/override claims "
                "the next slot and drops displaced immediate entries. Demand Capture and command-result "
                "wake are observation timing requests, not queue approvals."
            ),
            style="CardBody.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Runtime Toggles & Overlay", "Live init, logging, planning visibility, and on-screen overlay switches.")
        toggles = ttk.Frame(card)
        toggles.pack(fill="x", pady=(10, 6))
        toggle_lock_bindings = {
            "Live": "live",
            "Live Init": "live_init",
            "Sound": "sound",
            "Time Logging": "time_logging",
            "Chat Log Echo": "chat_log_echo",
        }
        for text, variable in [
            ("Live", self.live_var),
            ("Live Init", self.live_init_var),
            ("Sound", self.sound_var),
            ("Time Logging", self.time_logging_var),
            ("Chat Log Echo", self.chat_log_echo_var),
            ("Follow Latest", self.follow_latest_var),
        ]:
            widget = ttk.Checkbutton(toggles, text=text, variable=variable)
            widget.pack(side="left", padx=(0, 10))
            lock_name = toggle_lock_bindings.get(text)
            if lock_name:
                register_lock_widget(lock_name, widget)

        planning_toggle_row = ttk.Frame(card)
        planning_toggle_row.pack(fill="x", pady=(0, 6))
        ttk.Label(planning_toggle_row, text="Planning", style="CardBody.TLabel", width=label_width).pack(side="left")
        auto_dynamic_widget = ttk.Checkbutton(planning_toggle_row, text="Dynamic Inference", variable=self.auto_dynamic_var)
        auto_dynamic_widget.pack(side="left", padx=(0, 10))
        register_lock_widget("reasoning", auto_dynamic_widget)

        overlay_row = ttk.Frame(card)
        overlay_row.pack(fill="x", pady=(4, 6))
        ttk.Label(overlay_row, text="Overlay", style="CardBody.TLabel", width=label_width).pack(side="left")
        overlay_toggles = ttk.Frame(overlay_row)
        overlay_toggles.pack(side="left", fill="x", expand=True)
        for text, variable in [
            ("Tile Grid", self.tile_grid_var),
            ("Cursor Label", self.cursor_label_var),
            ("Keypoint Grid", self.keypoint_grid_var),
            ("Status Text", self.status_overlay_var),
        ]:
            widget = ttk.Checkbutton(overlay_toggles, text=text, variable=variable)
            widget.pack(side="left", padx=(0, 10))
            register_lock_widget("overlay", widget)

        buttons = ttk.Frame(card)
        buttons.pack(fill="x", pady=(8, 4))
        self.settings_transaction_preview_button = ttk.Button(
            buttons,
            text="Preview Atomic",
            command=self.preview_settings,
        )
        self.settings_transaction_preview_button.pack(side="left")
        self.settings_transaction_apply_button = ttk.Button(
            buttons,
            text="Apply Atomic",
            style="Accent.TButton",
            command=lambda: self.apply_settings(show_confirmation=True),
        )
        self.settings_transaction_apply_button.pack(side="left", padx=(6, 0))
        self.settings_transaction_rollback_button = ttk.Button(
            buttons,
            text="Rollback",
            command=self.rollback_settings,
        )
        self.settings_transaction_rollback_button.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh_now).pack(side="left", padx=(6, 0))

        settings_tools = ttk.Frame(card)
        settings_tools.pack(fill="x", pady=(0, 4))
        self.settings_transaction_details_button = ttk.Button(
            settings_tools,
            text="Settings Details",
            command=self.show_settings_details,
        )
        self.settings_transaction_details_button.pack(side="left")
        ttk.Button(
            settings_tools,
            text="Apply Additional",
            command=lambda: self.apply_additional_settings(show_confirmation=True),
        ).pack(side="left", padx=(6, 0))
        self.settings_transaction_buttons = [
            self.settings_transaction_preview_button,
            self.settings_transaction_apply_button,
            self.settings_transaction_rollback_button,
        ]
        ttk.Label(
            card,
            textvariable=self.settings_transaction_version_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 2))
        ttk.Label(
            card,
            textvariable=self.settings_transaction_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Models, Presets & Next Turn", "Catalog maintenance, operator presets, session defaults, and one-shot next-turn overrides.")
        model_tools = ttk.Frame(card)
        model_tools.pack(fill="x", pady=(0, 8))
        ttk.Label(model_tools, text="Model Catalog", style="CardBody.TLabel", width=label_width).pack(side="left")
        add_model_button = ttk.Button(model_tools, text="Add Model", command=self.add_model_dialog)
        add_model_button.pack(side="left")
        remove_model_button = ttk.Button(model_tools, text="Remove Model", command=self.remove_selected_model_dialog)
        remove_model_button.pack(side="left", padx=(6, 0))
        refresh_models_button = ttk.Button(model_tools, text="Reload", command=self.refresh_model_catalog)
        refresh_models_button.pack(side="left", padx=(6, 0))
        self.model_catalog_summary_label = ttk.Label(model_tools, text="", style="CardBody.TLabel")
        self.model_catalog_summary_label.pack(side="left", padx=(12, 0))
        register_lock_widgets(["models"], add_model_button)
        register_lock_widgets(["models"], remove_model_button)
        register_lock_widgets(["models"], refresh_models_button)

        presets = ttk.Frame(card)
        presets.pack(fill="x", pady=(0, 8))
        ttk.Label(presets, text="Model Presets", style="CardBody.TLabel", width=label_width).pack(side="left")
        for label in MODEL_PRESETS:
            widget = ttk.Button(
                presets,
                text=label,
                command=lambda preset_name=label: self.apply_model_preset(preset_name),
            )
            widget.pack(side="left", padx=(0, 6))
            register_lock_widgets(["models", "reasoning", "temperature"], widget)

        stateful_presets = ttk.Frame(card)
        stateful_presets.pack(fill="x", pady=(0, 8))
        ttk.Label(stateful_presets, text="Stateful Profiles", style="CardBody.TLabel", width=label_width).pack(side="left")
        for label, profile_name in STATEFUL_MODEL_PRESET_BUTTONS.items():
            widget = ttk.Button(
                stateful_presets,
                text=label,
                command=lambda selected_profile=profile_name: self.apply_stateful_model_preset(selected_profile),
            )
            widget.pack(side="left", padx=(0, 6))
            register_lock_widgets(["models"], widget)
        ttk.Button(stateful_presets, text="Show", command=lambda: self.send_raw("SHOW_STATEFUL_MODEL_PRESETS()")).pack(side="left", padx=(0, 6))

        ttk.Label(
            card,
            textvariable=self.model_preset_guide_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            card,
            textvariable=self.model_cost_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        model_status_row = ttk.Frame(card)
        model_status_row.pack(fill="both", pady=(0, 8))
        ttk.Label(model_status_row, text="Model Status", style="CardBody.TLabel", width=label_width).pack(anchor="nw", side="left")
        self.model_status_text = tk.Text(model_status_row, height=9, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.model_status_text.pack(side="left", fill="both", expand=True)

        next_plan_row = ttk.Frame(card)
        next_plan_row.pack(fill="x", pady=(0, 8))
        ttk.Label(next_plan_row, text="Next Turn", style="CardBody.TLabel", width=label_width).pack(side="left")
        next_plan_fields = ttk.Frame(next_plan_row)
        next_plan_fields.pack(side="left", fill="x", expand=True)
        next_plan_primary = ttk.Frame(next_plan_fields)
        next_plan_primary.pack(fill="x", pady=(0, 4))
        next_plan_secondary = ttk.Frame(next_plan_fields)
        next_plan_secondary.pack(fill="x")

        def add_labeled_combo(parent, label, variable, values, width):
            ttk.Label(parent, text=label, style="CardBody.TLabel").pack(side="left")
            ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=width).pack(side="left", padx=(4, 8))

        def add_labeled_entry(parent, label, variable, width=None, expand=False):
            ttk.Label(parent, text=label, style="CardBody.TLabel").pack(side="left")
            entry = ttk.Entry(parent, textvariable=variable, width=width) if width else ttk.Entry(parent, textvariable=variable)
            if expand:
                entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
            else:
                entry.pack(side="left", padx=(4, 8))

        add_labeled_combo(next_plan_primary, "Next Effort", self.next_reasoning_var, EFFORTS, 9)
        add_labeled_combo(next_plan_primary, "Verbosity", self.next_verbosity_var, VERBOSITIES, 9)
        add_labeled_combo(next_plan_primary, "Summary", self.next_summary_var, SUMMARY_MODES, 9)
        add_labeled_entry(next_plan_primary, "Model", self.next_model_var, width=18)
        add_labeled_combo(next_plan_secondary, "Image", self.next_image_detail_var, ["", "low", "high", "auto", "original"], 8)
        add_labeled_combo(next_plan_secondary, "Latest", self.next_latest_image_detail_var, ["", "low", "high", "auto", "original"], 8)
        add_labeled_entry(next_plan_secondary, "Temp", self.next_temperature_var, width=7)
        add_labeled_entry(next_plan_secondary, "Note", self.next_note_var, expand=True)
        queue_next_button = ttk.Button(next_plan_row, text="Queue Next", command=self.queue_next_inference_plan)
        queue_next_button.pack(side="left", padx=(6, 0))
        clear_next_button = ttk.Button(next_plan_row, text="Clear", command=lambda: self.send_raw("CLEAR_NEXT_INFERENCE()"))
        clear_next_button.pack(side="left", padx=(6, 0))
        register_lock_widgets(["models", "reasoning", "temperature"], queue_next_button)
        register_lock_widgets(["models", "reasoning", "temperature"], clear_next_button)
        ttk.Label(
            card,
            textvariable=self.next_turn_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        defaults_row = ttk.Frame(card)
        defaults_row.pack(fill="x", pady=(0, 8))
        ttk.Label(defaults_row, text="Defaults", style="CardBody.TLabel", width=label_width).pack(side="left")
        apply_system_button = ttk.Button(defaults_row, text="Apply System", command=lambda: self.send_raw("APPLY_SYSTEM_DEFAULTS()"))
        apply_system_button.pack(side="left")
        apply_personal_button = ttk.Button(defaults_row, text="Apply Personal", command=lambda: self.send_raw("APPLY_PERSONAL_DEFAULTS()"))
        apply_personal_button.pack(side="left", padx=(6, 0))
        save_personal_button = ttk.Button(defaults_row, text="Save Personal", command=lambda: self.send_raw("SAVE_PERSONAL_DEFAULTS()"))
        save_personal_button.pack(side="left", padx=(6, 0))
        show_defaults_button = ttk.Button(defaults_row, text="Show Defaults", command=lambda: self.send_raw("SHOW_DEFAULT_PROFILES()"))
        show_defaults_button.pack(side="left", padx=(6, 0))
        register_lock_widgets(["auth", "execution", "action", "models", "reasoning", "temperature", "screenshot_interval", "overlay", "live_init", "sound", "time_logging", "chat_log_echo"], apply_system_button)
        register_lock_widgets(["auth", "execution", "action", "models", "reasoning", "temperature", "screenshot_interval", "overlay", "live_init", "sound", "time_logging", "chat_log_echo"], apply_personal_button)
        register_lock_widgets(["auth", "execution", "action", "models", "reasoning", "temperature", "screenshot_interval", "overlay", "live_init", "sound", "time_logging", "chat_log_echo"], save_personal_button)
        ttk.Label(card, textvariable=self.defaults_status_var, style="CardBody.TLabel").pack(anchor="w", pady=(0, 8))

        overlay_presets = ttk.Frame(card)
        overlay_presets.pack(fill="x", pady=(0, 8))
        ttk.Label(overlay_presets, text="Overlay Presets", style="CardBody.TLabel", width=label_width).pack(side="left")
        for label in OVERLAY_PRESETS:
            widget = ttk.Button(
                overlay_presets,
                text=label,
                command=lambda preset_name=label: self.apply_overlay_preset(preset_name),
            )
            widget.pack(side="left", padx=(0, 6))
            register_lock_widgets(["overlay"], widget)

        profiles = ttk.Frame(card)
        profiles.pack(fill="x", pady=(0, 8))
        profiles.columnconfigure(1, weight=1)
        ttk.Label(profiles, text="Operator Profiles", style="CardBody.TLabel", width=label_width).grid(
            row=0,
            column=0,
            sticky="nw",
            pady=(4, 0),
        )
        profile_buttons = ttk.Frame(profiles)
        profile_buttons.grid(row=0, column=1, sticky="ew")
        for column in range(3):
            profile_buttons.columnconfigure(column, weight=1, uniform="operator-profile")
        for index, label in enumerate(OPERATOR_PROFILES):
            widget = ttk.Button(
                profile_buttons,
                text=label,
                command=lambda profile_name=label: self.apply_operator_profile(profile_name),
            )
            widget.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 6), pady=(0, 4))
            register_lock_widgets(
                ["live", "execution", "action", "models", "reasoning", "temperature", "overlay"],
                widget,
            )

        add_section("Advanced Context", "Fine-grained message visibility, history storage, and image-history controls.")
        advanced_visibility = ttk.Frame(card)
        advanced_visibility.pack(fill="x", pady=(0, 6))
        ttk.Label(advanced_visibility, text="Message View", style="CardBody.TLabel", width=label_width).pack(side="left")
        for text, variable in [
            ("Auto Prompt", self.auto_prompt_var),
            ("User Text", self.show_user_text_var),
            ("AI Text", self.show_ai_text_var),
        ]:
            ttk.Checkbutton(advanced_visibility, text=text, variable=variable).pack(side="left", padx=(0, 10))

        advanced_command_visibility = ttk.Frame(card)
        advanced_command_visibility.pack(fill="x", pady=(0, 6))
        ttk.Label(advanced_command_visibility, text="Command View", style="CardBody.TLabel", width=label_width).pack(side="left")
        for text, variable in [
            ("AI Cmds", self.show_ai_commands_var),
            ("User Cmds", self.show_user_commands_var),
        ]:
            ttk.Checkbutton(advanced_command_visibility, text=text, variable=variable).pack(side="left", padx=(0, 10))

        advanced_history = ttk.Frame(card)
        advanced_history.pack(fill="x", pady=(0, 6))
        ttk.Label(advanced_history, text="History Store", style="CardBody.TLabel", width=label_width).pack(side="left")
        for text, variable in [
            ("Unimportant", self.enable_unimportant_messages_var),
            ("Important", self.enable_important_messages_var),
            ("Add UMsgs", self.add_umsgs_to_history_var),
            ("Add IMsgs", self.add_imsgs_to_history_var),
        ]:
            ttk.Checkbutton(advanced_history, text=text, variable=variable).pack(side="left", padx=(0, 10))

        advanced_decay = ttk.Frame(card)
        advanced_decay.pack(fill="x", pady=(0, 6))
        ttk.Label(advanced_decay, text="History Decay", style="CardBody.TLabel", width=label_width).pack(side="left")
        for text, variable in [
            ("UMsg Decay", self.check_umsgs_decay_var),
            ("IMsg Decay", self.check_imsgs_decay_var),
        ]:
            ttk.Checkbutton(advanced_decay, text=text, variable=variable).pack(side="left", padx=(0, 10))

        advanced_inputs = ttk.Frame(card)
        advanced_inputs.pack(fill="x", pady=(0, 6))
        ttk.Label(advanced_inputs, text="Input Mode", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(advanced_inputs, text="Always", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(advanced_inputs, textvariable=self.always_mode_var, values=["off", "on"], state="readonly", width=6).pack(side="left", padx=(6, 10))
        ttk.Checkbutton(advanced_inputs, text="Hide Input", variable=self.hide_input_pref_var).pack(side="left", padx=(0, 10))

        advanced_images = ttk.Frame(card)
        advanced_images.pack(fill="x", pady=(0, 8))
        ttk.Label(advanced_images, text="Image Detail", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(advanced_images, text="Current", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(advanced_images, textvariable=self.image_detail_var, values=["low", "high", "auto", "original"], state="readonly", width=8).pack(side="left", padx=(6, 8))
        ttk.Label(advanced_images, text="Latest", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(advanced_images, textvariable=self.latest_image_detail_var, values=["low", "high", "auto", "original"], state="readonly", width=8).pack(side="left", padx=(6, 8))
        ttk.Label(advanced_images, text="High Count", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(advanced_images, textvariable=self.high_detail_var, width=6).pack(side="left", padx=(6, 8))
        ttk.Label(advanced_images, text="Max", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(advanced_images, textvariable=self.max_images_var, width=6).pack(side="left", padx=(6, 10))
        ttk.Button(advanced_images, text="Apply Advanced", command=self.apply_advanced_settings).pack(side="left")
        ttk.Label(
            card,
            textvariable=self.advanced_context_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Chat Head", "Floating chat strip and attached history window controls.")
        chat_head_row = ttk.Frame(card)
        chat_head_row.pack(fill="x", pady=(0, 8))
        ttk.Label(chat_head_row, text="Window", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Checkbutton(chat_head_row, text="Topmost", variable=self.chat_head_topmost_var).pack(side="left", padx=(0, 10))
        ttk.Label(chat_head_row, text="Opacity", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_row, textvariable=self.chat_head_opacity_var, width=6).pack(side="left", padx=(6, 10))
        ttk.Label(chat_head_row, text="Strip", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_row, textvariable=self.chat_head_strip_width_var, width=6).pack(side="left", padx=(6, 4))
        ttk.Label(chat_head_row, text="x", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_row, textvariable=self.chat_head_strip_height_var, width=6).pack(side="left", padx=(4, 10))
        ttk.Label(chat_head_row, text="History", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_row, textvariable=self.chat_head_history_width_var, width=6).pack(side="left", padx=(6, 4))
        ttk.Label(chat_head_row, text="x", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_row, textvariable=self.chat_head_history_height_var, width=6).pack(side="left", padx=(4, 10))
        ttk.Button(chat_head_row, text="Apply", command=self.apply_chat_head_settings).pack(side="left")
        ttk.Button(chat_head_row, text="Show", command=lambda: self.send_raw("SHOW_CHAT_HEAD()")).pack(side="left", padx=(6, 0))
        ttk.Button(chat_head_row, text="Open", command=lambda: self.send_raw("OPEN_CHAT_HEAD()")).pack(side="left", padx=(6, 0))
        ttk.Button(chat_head_row, text="Close", command=lambda: self.send_raw("CLOSE_CHAT_HEAD()")).pack(side="left", padx=(6, 0))

        chat_head_anim_row = ttk.Frame(card)
        chat_head_anim_row.pack(fill="x", pady=(0, 8))
        ttk.Label(chat_head_anim_row, text="Send Feedback", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(chat_head_anim_row, text="Animation", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            chat_head_anim_row,
            textvariable=self.chat_head_send_animation_var,
            values=CHAT_HEAD_SEND_ANIMATIONS,
            state="readonly",
            width=8,
        ).pack(side="left", padx=(6, 10))
        ttk.Label(chat_head_anim_row, text="Seconds", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(chat_head_anim_row, textvariable=self.chat_head_send_animation_seconds_var, width=6).pack(side="left", padx=(6, 10))
        ttk.Button(chat_head_anim_row, text="Apply", command=self.apply_chat_head_settings).pack(side="left")
        ttk.Label(
            card,
            textvariable=self.chat_head_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Episodic Memory", "Snapshot writing, embedding backend, and bounded planning-assist retrieval.")
        episodic_row = ttk.Frame(card)
        episodic_row.pack(fill="x", pady=(0, 8))
        ttk.Label(episodic_row, text="Snapshots", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Checkbutton(episodic_row, text="Enabled", variable=self.episodic_enabled_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(episodic_row, text="Periodic", variable=self.episodic_periodic_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(episodic_row, text="Scene", variable=self.episodic_scene_var).pack(side="left", padx=(0, 8))
        ttk.Label(episodic_row, text="Interval", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(episodic_row, textvariable=self.episodic_interval_var, width=6).pack(side="left", padx=(6, 4))
        ttk.Label(episodic_row, text="s", style="CardBody.TLabel").pack(side="left", padx=(0, 10))
        ttk.Button(episodic_row, text="Apply", command=self.apply_episodic_memory_settings).pack(side="left")
        ttk.Button(episodic_row, text="Show", command=lambda: self.send_raw("SHOW_EPISODIC_MEMORY_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(episodic_row, text="Open Tab", command=self.show_episodic_tab).pack(side="left", padx=(6, 0))

        episodic_semantic_row = ttk.Frame(card)
        episodic_semantic_row.pack(fill="x", pady=(0, 8))
        ttk.Label(episodic_semantic_row, text="Embedding", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(episodic_semantic_row, text="Backend", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            episodic_semantic_row,
            textvariable=self.episodic_backend_var,
            values=["off", "auto", "force"],
            state="readonly",
            width=8,
        ).pack(side="left", padx=(6, 10))
        ttk.Label(episodic_semantic_row, text="Model", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(episodic_semantic_row, textvariable=self.episodic_embedding_model_var, width=24).pack(side="left", padx=(6, 10))
        ttk.Button(episodic_semantic_row, text="Apply", command=self.apply_episodic_memory_settings).pack(side="left")

        episodic_planning_row = ttk.Frame(card)
        episodic_planning_row.pack(fill="x", pady=(0, 8))
        ttk.Label(episodic_planning_row, text="Planning Assist", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Label(episodic_planning_row, text="Mode", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            episodic_planning_row,
            textvariable=self.episodic_planning_mode_var,
            values=["off", "review", "critique", "review_critique"],
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 10))
        ttk.Label(episodic_planning_row, text="Items", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(episodic_planning_row, textvariable=self.episodic_planning_k_var, width=5).pack(side="left", padx=(6, 10))
        ttk.Label(episodic_planning_row, text="Cooldown", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(episodic_planning_row, textvariable=self.episodic_planning_cooldown_var, width=5).pack(side="left", padx=(6, 10))
        ttk.Button(episodic_planning_row, text="Apply", command=self.apply_episodic_memory_settings).pack(side="left")
        ttk.Label(
            card,
            textvariable=self.episodic_control_status_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        add_section("Continuity & Operator Input", "Handoff helpers, scoped clear commands, raw commands, and notes.")
        continuity_row = ttk.Frame(card)
        continuity_row.pack(fill="x", pady=(0, 8))
        ttk.Label(continuity_row, text="Continuity", style="CardBody.TLabel", width=label_width).pack(side="left")
        ttk.Entry(continuity_row, textvariable=self.handoff_file_var).pack(side="left", fill="x", expand=True)
        ttk.Button(continuity_row, text="Save Handoff", command=self.send_save_handoff).pack(side="left", padx=(6, 0))
        ttk.Button(continuity_row, text="Retrieve", command=self.send_retrieve_handoff).pack(side="left", padx=(6, 0))
        ttk.Button(continuity_row, text="Load Yesterday", command=lambda: self.send_raw("CHECK_PREVIOUS_HANDOFF()")).pack(side="left", padx=(6, 0))
        ttk.Button(continuity_row, text="Recall Prev", command=lambda: self.send_raw("RECALL_PREVIOUS_SUMMARY()")).pack(side="left", padx=(6, 0))

        clear_row = ttk.Frame(card)
        clear_row.pack(fill="x", pady=(0, 8))
        ttk.Label(clear_row, text="Scoped Clear", style="CardBody.TLabel", width=label_width).pack(side="left")
        for label, command in [
            ("Non-pinned", "CLEAR_NONPIN()"),
            ("Init", "CLEAR_INIT()"),
            ("Pinned", "CLEAR_PIN()"),
            ("Handoff", "CLEAR_HANDOFF()"),
            ("Recent Ctx", "CLEAR_RECENT_CONTEXT()"),
            ("Route", "CLEAR_ROUTE_STATE()"),
        ]:
            ttk.Button(clear_row, text=label, command=lambda value=command: self.send_raw(value)).pack(side="left", padx=(0, 6))

        command_row = ttk.Frame(card)
        command_row.pack(fill="x", pady=(8, 4))
        ttk.Label(command_row, text="Raw Command", style="CardBody.TLabel", width=label_width).pack(side="left")
        command_entry = ttk.Entry(command_row, textvariable=self.command_var)
        command_entry.pack(side="left", fill="x", expand=True)
        command_entry.bind("<Return>", self.send_command_entry)
        ttk.Button(command_row, text="Send Command", command=self.send_command_entry).pack(side="left", padx=(6, 0))

        note_row = ttk.Frame(card)
        note_row.pack(fill="x")
        ttk.Label(note_row, text="Operator Note", style="CardBody.TLabel", width=label_width).pack(side="left")
        note_entry = ttk.Entry(note_row, textvariable=self.note_var)
        note_entry.pack(side="left", fill="x", expand=True)
        note_entry.bind("<Return>", self.send_note_entry)
        ttk.Button(note_row, text="Send Note", command=self.send_note_entry).pack(side="left", padx=(6, 0))

    def _build_feedback_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(0, 14, 0, 0))
        card.pack(fill="both", expand=True)
        ttk.Label(card, text="Operator Activity", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(
            card,
            textvariable=self.operator_activity_var,
            style="SectionHint.TLabel",
            wraplength=390,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        operator_tools = ttk.Frame(card, style="Card.TFrame")
        operator_tools.pack(fill="x", pady=(0, 12))
        ttk.Button(operator_tools, text="Refresh", command=self.refresh_now, style="Quiet.TButton").pack(side="left")
        ttk.Button(operator_tools, text="Dashboard", command=lambda: self.show_tab("Dashboard"), style="Quiet.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(operator_tools, text="Commands", command=lambda: self.show_tab("Commands"), style="Quiet.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(operator_tools, text="Raw State", command=lambda: self.show_tab("Raw State"), style="Quiet.TButton").pack(side="left", padx=(6, 0))
        ttk.Label(card, text="Latest Feedback", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.feedback_text = tk.Text(card, height=10, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.feedback_text.pack(fill="both", expand=True)

    def _build_overview_tab(self):
        frame = self._new_work_page("Overview")
        self.overview_summary_vars = {}
        summary = ttk.Frame(frame)
        summary.pack(fill="x", pady=(0, 8))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)

        def add_summary_card(key, title, row, column):
            card = ttk.Frame(summary, style="Card.TFrame", padding=10)
            card.grid(row=row, column=column, sticky="ew", padx=(0, 8), pady=(0, 8))
            ttk.Label(card, text=title, style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 4))
            value_var = tk.StringVar(value="-")
            self.overview_summary_vars[key] = value_var
            ttk.Label(
                card,
                textvariable=value_var,
                style="CardBody.TLabel",
                wraplength=390,
                justify="left",
            ).pack(anchor="w", fill="x")

        add_summary_card("runtime", "Runtime", 0, 0)
        add_summary_card("queue", "Queue", 0, 1)
        add_summary_card("memory", "Memory", 1, 0)
        add_summary_card("browser", "Browser Bridge", 1, 1)
        add_summary_card("harness", "Live Harness", 2, 0)
        add_summary_card("responses", "Responses Shadow", 2, 1)
        add_summary_card("health", "Operator Health", 3, 0)
        add_summary_card("image_cost", "Image Cost", 3, 1)
        add_summary_card("operator_risk", "Operator Risk", 4, 0)
        add_summary_card("prompt_inclusion", "Prompt Inclusion", 4, 1)
        add_summary_card("checkpoint", "Window 18-21 Checkpoint", 5, 0)
        add_summary_card("portal_intake", "Portal Intake", 5, 1)
        self.overview_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.overview_text.pack(fill="both", expand=True)

    def _build_dashboard_tab(self):
        frame = self._new_work_page("Dashboard")

        controls = FlowBar(frame)
        controls.pack(fill="x", pady=(0, 8))
        controls.add(ttk.Button(
            controls,
            text="Refresh",
            command=lambda: self.refresh_dashboard(self.state_cache or None),
        ))
        self.dashboard_popout_button = ttk.Button(
            controls,
            text="Open Popout",
            command=self.toggle_dashboard_popout,
        )
        controls.add(self.dashboard_popout_button)
        controls.add(ttk.Button(controls, text="Execution inspector", command=self.open_execution_inspector))
        controls.add(ttk.Checkbutton(controls, text="Wrap detail", variable=self.dashboard_wrap_var,
                                    command=self._update_dashboard_wrap))
        ttk.Label(
            frame,
            textvariable=self.dashboard_status_var,
            style="Muted.TLabel",
            wraplength=740,
        ).pack(fill="x", pady=(0, 8))

        summary = ttk.Frame(frame)
        summary.pack(fill="x", pady=(0, 8))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        self.dashboard_cards = []
        self._dashboard_card_columns = None
        summary.bind("<Configure>", self._layout_dashboard_cards)

        def add_summary(key, title, row, column):
            card = ttk.Frame(summary, style="Card.TFrame", padding=10)
            self.dashboard_cards.append(card)
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 8), pady=(0, 8))
            ttk.Label(card, text=title, style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 4))
            value_var = tk.StringVar(value="-")
            self.dashboard_summary_vars[key] = value_var
            label = ttk.Label(
                card,
                textvariable=value_var,
                style="CardBody.TLabel",
                wraplength=390,
                justify="left",
            )
            label.pack(anchor="w", fill="x")
            bind_label_wrap(label, source=card, inset=24)

        add_summary("runtime", "Runtime", 0, 0)
        add_summary("operation", "Operation", 0, 1)
        add_summary("control_plane", "Control Plane", 1, 0)
        add_summary("settings", "Settings", 1, 1)
        wrap_packed_labels(frame)

        receipt_tools = FlowBar(frame)
        receipt_tools.pack(fill="x", pady=(0, 4))
        receipt_tools.add(ttk.Label(receipt_tools, text="Recent receipts", style="SectionTitle.TLabel"))
        receipt_tools.add(ttk.Button(receipt_tools, text="Open selected receipt ↗", command=self.open_dashboard_receipt))
        receipt_tools.add(ttk.Label(receipt_tools, text="Select to read below · Enter or double-click to expand", style="Muted.TLabel"))
        event_shell = ttk.Frame(frame)
        event_shell.pack(fill="x", pady=(0, 8))
        columns = ("time", "command", "status", "delivery", "request")
        self.dashboard_events_tree = ttk.Treeview(
            event_shell,
            columns=columns,
            show="headings",
            height=7,
        )
        for key, title, width in [
            ("time", "Time", 150),
            ("command", "Command", 270),
            ("status", "Status", 110),
            ("delivery", "Delivery", 160),
            ("request", "Request", 280),
        ]:
            self.dashboard_events_tree.heading(key, text=title)
            self.dashboard_events_tree.column(key, width=round(width * ui_scale(self)),
                minwidth=round((170 if key in {"command", "request"} else 70) * ui_scale(self)),
                stretch=key in {"command", "request"})
        self.dashboard_events_tree.grid(row=0, column=0, sticky="nsew")
        event_scroll = ttk.Scrollbar(event_shell, orient="vertical", command=self.dashboard_events_tree.yview)
        event_scroll.grid(row=0, column=1, sticky="ns")
        event_x = ttk.Scrollbar(event_shell, orient="horizontal", command=self.dashboard_events_tree.xview)
        event_x.grid(row=1, column=0, sticky="ew")
        event_shell.columnconfigure(0, weight=1)
        self.dashboard_events_tree.configure(yscrollcommand=event_scroll.set, xscrollcommand=event_x.set)
        self.dashboard_events_tree.bind("<<TreeviewSelect>>", self._show_dashboard_receipt)
        self.dashboard_events_tree.bind("<Return>", self.open_dashboard_receipt)
        self.dashboard_events_tree.bind("<Double-Button-1>", self.open_dashboard_receipt)
        self.dashboard_receipt_text = self._dashboard_detail_widget(frame, height=6)
        self._write_text(self.dashboard_receipt_text, "Select a receipt to inspect its full identifiers and status. Raw command arguments and payloads are omitted.")

        ttk.Label(frame, text="Structured Detail", style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 4))
        self.dashboard_text = self._dashboard_detail_widget(frame, height=12)
        self.dashboard_text.bind("<Double-Button-1>", lambda _event: self.open_dashboard_popout())

    def open_execution_inspector(self):
        from aurora_execution_inspector import ExecutionInspector
        return ExecutionInspector.open(self)

    def _dashboard_detail_widget(self, parent, *, height=12):
        shell = ttk.Frame(parent)
        shell.pack(fill="both", expand=True, pady=(0, 8))
        text = tk.Text(shell, height=height, width=1, bg=PANEL, fg=TEXT,
                       insertbackground=TEXT, relief="flat", wrap="word", font=("Consolas", 9))
        vertical = ttk.Scrollbar(shell, orient="vertical", command=text.yview)
        horizontal = ttk.Scrollbar(shell, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        text.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)
        return text

    def _layout_dashboard_cards(self, event):
        columns = 2 if event.width >= round(760 * ui_scale(self)) else 1
        if columns != self._dashboard_card_columns:
            self._dashboard_card_columns = columns
            event.widget.columnconfigure(0, weight=1, uniform="dashboard")
            event.widget.columnconfigure(1, weight=1 if columns == 2 else 0, uniform="dashboard" if columns == 2 else "")
            for index, card in enumerate(self.dashboard_cards):
                card.grid_configure(row=index // columns, column=index % columns,
                                    padx=(0, 8 if columns == 2 and index % 2 == 0 else 0))

    def _update_dashboard_wrap(self):
        for widget in (self.dashboard_text, self.dashboard_popout_text, self.dashboard_receipt_text):
            if widget is not None:
                widget.configure(wrap="word" if self.dashboard_wrap_var.get() else "none")

    def _show_dashboard_receipt(self, _event=None):
        selected = self.dashboard_events_tree.selection()
        row = self._dashboard_events_by_iid.get(selected[0]) if selected else None
        self._write_text(self.dashboard_receipt_text, json.dumps(row, indent=2, ensure_ascii=False)
                         if row else "Select a receipt to inspect its full identifiers and status. Raw command arguments and payloads are omitted.")

    def open_dashboard_receipt(self, event=None):
        tree = self.dashboard_events_tree
        if event is not None and getattr(event, "num", None) == 1:
            item = tree.identify_row(event.y)
            if not item:
                return
            tree.selection_set(item)
        selected = tree.selection()
        row = self._dashboard_events_by_iid.get(selected[0]) if selected else None
        if row is None:
            tree.focus_set()
            return "break"
        if self.dashboard_receipt_window is not None and self.dashboard_receipt_window.winfo_exists():
            self.dashboard_receipt_window.destroy()
        window = self.dashboard_receipt_window = tk.Toplevel(self)
        window.title("Aurora — receipt snapshot")
        window.configure(bg=BG)
        fit_popout_window(window, round(860 * ui_scale(self)), round(480 * ui_scale(self)), self)
        window.minsize(320, 240)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        label = ttk.Label(body, text="Read-only snapshot of the selected receipt. Command arguments and payloads are omitted.",
                          style="Muted.TLabel", wraplength=600)
        label.pack(fill="x", pady=(0, 8))
        bind_label_wrap(label)
        ttk.Button(body, text="Close (Esc)", command=window.destroy).pack(side="bottom", anchor="e")
        detail = self._dashboard_detail_widget(body, height=10)
        self._write_text(detail, json.dumps(row, indent=2, ensure_ascii=False))
        detail.focus_set()
        window.bind("<Escape>", lambda _event: window.destroy())
        return "break"

    def _add_workflow_status_strip(self, frame, key, title):
        strip = ttk.Frame(frame)
        strip.pack(fill="x", pady=(0, 8))
        ttk.Label(strip, text=title, style="SectionTitle.TLabel").pack(side="left")
        value_var = tk.StringVar(value="-")
        self.workflow_status_vars[key] = value_var
        ttk.Label(
            strip,
            textvariable=value_var,
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))
        return value_var

    def _build_memory_tab(self):
        frame = self._new_work_page("Memory")
        self._add_workflow_status_strip(frame, "memory", "Memory")
        columns = ("item", "value")
        self.memory_tree = ttk.Treeview(frame, columns=columns, show="tree headings")
        self.memory_tree.heading("#0", text="Section")
        self.memory_tree.heading("item", text="Item")
        self.memory_tree.heading("value", text="Value")
        self.memory_tree.column("#0", width=170, anchor="w")
        self.memory_tree.column("item", width=220, anchor="w")
        self.memory_tree.column("value", width=900, anchor="w")
        self.memory_tree.pack(fill="both", expand=True)

    def _build_episodic_tab(self):
        frame = self._new_work_page("Episodic")
        self.episodic_tab = frame
        self._add_workflow_status_strip(frame, "episodic", "Episodic")

        status_row = ttk.Frame(frame)
        status_row.pack(fill="x", pady=(0, 8))
        ttk.Label(status_row, text="Status", style="CardBody.TLabel").pack(side="left")
        ttk.Label(status_row, textvariable=self.episodic_status_var, style="CardBody.TLabel").pack(
            side="left", fill="x", expand=True, padx=(8, 10)
        )
        ttk.Button(status_row, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(status_row, text="Runtime Status", command=lambda: self.send_raw("SHOW_EPISODIC_MEMORY_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(status_row, text="Rehydration", command=lambda: self.send_raw("SHOW_REHYDRATION_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(status_row, text="List Snapshots", command=self.send_episodic_list_recent).pack(side="left", padx=(6, 0))

        planning_status_row = ttk.Frame(frame)
        planning_status_row.pack(fill="x", pady=(0, 8))
        ttk.Label(planning_status_row, text="Planning Assist", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            planning_status_row,
            textvariable=self.episodic_tab_planning_status_var,
            style="CardBody.TLabel",
            wraplength=1050,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

        retrieval_row = ttk.Frame(frame)
        retrieval_row.pack(fill="x", pady=(0, 8))
        ttk.Label(retrieval_row, text="Retrieval Preview", style="CardBody.TLabel").pack(side="left")
        query_entry = ttk.Entry(retrieval_row, textvariable=self.episodic_query_var)
        query_entry.pack(side="left", fill="x", expand=True, padx=(6, 10))
        query_entry.bind("<Return>", self.send_episodic_retrieval)
        ttk.Label(retrieval_row, text="Items", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_row, textvariable=self.episodic_limit_var, width=5).pack(side="left", padx=(6, 10))
        ttk.Label(retrieval_row, text="Backend", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            retrieval_row,
            textvariable=self.episodic_backend_var,
            values=["off", "auto", "force"],
            state="readonly",
            width=8,
        ).pack(side="left", padx=(6, 10))
        ttk.Label(retrieval_row, text="Shape", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            retrieval_row,
            textvariable=self.episodic_shape_var,
            values=RETRIEVAL_DISTRIBUTION_SHAPES,
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 10))
        ttk.Button(retrieval_row, text="Preview", command=self.send_episodic_retrieval).pack(side="left")
        ttk.Button(retrieval_row, text="Recall", command=self.send_episodic_recall_shorthand).pack(side="left", padx=(6, 0))

        self._build_episodic_search_filters(frame)
        self._build_episodic_visual_search(frame)

        retrieval_weights = ttk.Frame(frame)
        retrieval_weights.pack(fill="x", pady=(0, 8))
        ttk.Label(retrieval_weights, text="Legacy weights", style="CardBody.TLabel").pack(side="left")
        ttk.Label(retrieval_weights, text="Time", style="CardBody.TLabel").pack(side="left", padx=(10, 0))
        ttk.Entry(retrieval_weights, textvariable=self.episodic_time_weight_var, width=6).pack(side="left", padx=(6, 8))
        ttk.Label(retrieval_weights, text="Semantic", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_weights, textvariable=self.episodic_semantic_weight_var, width=6).pack(side="left", padx=(6, 8))
        ttk.Label(retrieval_weights, text="Tag", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_weights, textvariable=self.episodic_tag_weight_var, width=6).pack(side="left", padx=(6, 14))
        ttk.Label(retrieval_weights, text="Center", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_weights, textvariable=self.episodic_center_var, width=6).pack(side="left", padx=(6, 8))
        ttk.Label(retrieval_weights, text="Spread", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_weights, textvariable=self.episodic_spread_var, width=6).pack(side="left", padx=(6, 8))
        ttk.Label(retrieval_weights, text="Variance", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_weights, textvariable=self.episodic_variance_var, width=6).pack(side="left", padx=(6, 0))

        advanced = CollapsibleSection(frame, "Advanced retrieval (this query only)", expanded=False)
        advanced.pack(fill="x", pady=(0, 8))
        time_row = ttk.Frame(advanced.body)
        time_row.pack(fill="x", pady=(0, 6))
        ttk.Label(time_row, text="Time mode").pack(side="left")
        ttk.Combobox(time_row, textvariable=self.episodic_time_mode_var, values=["ordinal", "age"], state="readonly", width=9).pack(side="left", padx=6)
        for label, variable in (("Half-life hours", self.episodic_age_half_life_hours_var),
                                ("Ordinal anchor", self.episodic_time_anchor_var),
                                ("Anchor scale", self.episodic_time_scale_var)):
            ttk.Label(time_row, text=label).pack(side="left", padx=(8, 0))
            ttk.Entry(time_row, textvariable=variable, width=8).pack(side="left", padx=6)
        relevance_row = ttk.Frame(advanced.body)
        relevance_row.pack(fill="x", pady=(0, 6))
        for label, variable in (("Minimum query relevance", self.episodic_min_relevance_var),
                                ("Semantic tag mix", self.episodic_semantic_tag_weight_var)):
            ttk.Label(relevance_row, text=label).pack(side="left")
            ttk.Entry(relevance_row, textvariable=variable, width=7).pack(side="left", padx=(6, 12))
        ttk.Label(relevance_row, text="Auto fallback").pack(side="left")
        ttk.Combobox(relevance_row, textvariable=self.episodic_embedding_fallback_var, values=["lexical", "partial"], state="readonly", width=9).pack(side="left", padx=6)
        ttk.Label(advanced.body, text="ordinal + relevance 0 retains legacy ranking. Age uses real timestamps; leave ordinal anchor empty. Partial permits incomplete embeddings; force requires full coverage.", wraplength=1000).pack(anchor="w")

        retrieval_tags = ttk.Frame(frame)
        retrieval_tags.pack(fill="x", pady=(0, 8))
        ttk.Label(retrieval_tags, text="Required Tags", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_tags, textvariable=self.episodic_tags_required_var, width=28).pack(side="left", padx=(6, 10))
        ttk.Label(retrieval_tags, text="Preferred Tags", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_tags, textvariable=self.episodic_tags_preferred_var, width=32).pack(side="left", padx=(6, 10))
        ttk.Label(retrieval_tags, text="Buckets", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_tags, textvariable=self.episodic_source_buckets_var, width=18).pack(side="left", padx=(6, 0))

        ttk.Label(frame, text="Result score breakdown • colored bars show base-score contributions; adjusted scores also include the curve and jitter.", wraplength=1000).pack(anchor="w", pady=(2, 4))
        self.episodic_score_canvas = tk.Canvas(frame, height=80, background="#101827", highlightthickness=0)
        self.episodic_score_canvas.pack(fill="x", pady=(0, 8))
        self.episodic_score_canvas.bind("<Configure>", lambda _event: self._draw_episodic_score_results(getattr(self, "_episodic_visual_results", [])))
        retrieval_status_row = ttk.Frame(frame)
        retrieval_status_row.pack(fill="x", pady=(0, 8))
        ttk.Label(retrieval_status_row, text="Retrieval Status", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            retrieval_status_row,
            textvariable=self.episodic_retrieval_status_var,
            style="CardBody.TLabel",
            wraplength=1050,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

        retrieval_model_row = ttk.Frame(frame)
        retrieval_model_row.pack(fill="x", pady=(0, 8))
        ttk.Label(retrieval_model_row, text="Embedding Model", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(retrieval_model_row, textvariable=self.episodic_embedding_model_var).pack(side="left", fill="x", expand=True, padx=(6, 10))
        ttk.Label(
            retrieval_model_row,
            text="auto = lexical fallback, force = require embeddings",
            style="CardBody.TLabel",
        ).pack(side="left")

        write_row = ttk.Frame(frame)
        write_row.pack(fill="x", pady=(0, 8))
        ttk.Label(write_row, text="Snapshot", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(write_row, textvariable=self.episodic_snapshot_reason_var).pack(side="left", fill="x", expand=True, padx=(6, 10))
        ttk.Label(write_row, text="Tags", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(write_row, textvariable=self.episodic_snapshot_tags_var, width=28).pack(side="left", padx=(6, 10))
        ttk.Label(write_row, text="Recent", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(write_row, textvariable=self.episodic_recent_limit_var, width=5).pack(side="left", padx=(6, 10))
        ttk.Button(write_row, text="Write Snapshot", command=self.send_episodic_snapshot).pack(side="left")

        promote_row = ttk.Frame(frame)
        promote_row.pack(fill="x", pady=(0, 8))
        ttk.Label(promote_row, text="Promote Result", style="CardBody.TLabel").pack(side="left")
        ttk.Label(promote_row, text="Item #", style="CardBody.TLabel").pack(side="left", padx=(10, 0))
        ttk.Entry(promote_row, textvariable=self.episodic_promote_index_var, width=5).pack(side="left", padx=(6, 10))
        ttk.Label(promote_row, text="Memory Target", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(
            promote_row,
            textvariable=self.episodic_promote_target_var,
            values=EPISODIC_PROMOTION_TARGETS,
            state="readonly",
            width=18,
        ).pack(side="left", padx=(6, 10))
        ttk.Label(promote_row, text="Prefix", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(promote_row, textvariable=self.episodic_promote_prefix_var).pack(side="left", fill="x", expand=True, padx=(6, 10))
        ttk.Button(promote_row, text="Promote Selected", command=self.send_episodic_promotion).pack(side="left")

        retained_row = ttk.Frame(frame)
        retained_row.pack(fill="x", pady=(0, 8))
        ttk.Label(retained_row, text="Retained handle (blank = legacy preview)").pack(side="left")
        ttk.Entry(retained_row, textvariable=self.episodic_result_handle_var, width=38).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(retained_row, text="Use displayed handle", command=self.use_displayed_retrieval_handle).pack(side="left", padx=4)
        ttk.Button(retained_row, text="Inspect retained (Chat)", command=self.inspect_retained_retrieval).pack(side="left")

        promotion_status_row = ttk.Frame(frame)
        promotion_status_row.pack(fill="x", pady=(0, 8))
        ttk.Label(promotion_status_row, text="Promotion Status", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            promotion_status_row,
            textvariable=self.episodic_promotion_status_var,
            style="CardBody.TLabel",
            wraplength=1050,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

        body = ttk.Panedwindow(frame, orient="vertical")
        body.pack(fill="both", expand=True)

        recent_frame = ttk.Frame(body)
        retrieval_frame = ttk.Frame(body)
        body.add(recent_frame, weight=1)
        body.add(retrieval_frame, weight=1)

        ttk.Label(recent_frame, text="Recent Snapshot Store", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.episodic_recent_text = tk.Text(
            recent_frame,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
        )
        self.episodic_recent_text.pack(fill="both", expand=True)

        ttk.Label(retrieval_frame, text="Retrieval Preview And Planning Injection", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.episodic_retrieval_text = tk.Text(
            retrieval_frame,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
        )
        self.episodic_retrieval_text.pack(fill="both", expand=True)

    def _build_pending_tab(self):
        frame = self._new_work_page("Pending")
        self.pending_risk_var = tk.StringVar(value="all")
        self.pending_category_var = tk.StringVar(value="all")
        self.pending_search_var = tk.StringVar()
        self._add_workflow_status_strip(frame, "pending", "Pending")
        ttk.Label(
            frame,
            textvariable=self.pending_selection_status_var,
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Label(
            frame,
            text=(
                "Pending planning lane: Approve submits chosen held commands through the normal runtime path; "
                "Clear removes them without execution. Filters narrow the visible rows; selection actions affect "
                "selected visible rows, while All/Low/Medium/High buttons address that runtime scope."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))

        filters = ttk.Frame(frame)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Risk", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(filters, textvariable=self.pending_risk_var, values=PENDING_RISKS, state="readonly", width=10).pack(side="left", padx=(6, 10))
        ttk.Label(filters, text="Category", style="CardBody.TLabel").pack(side="left")
        ttk.Combobox(filters, textvariable=self.pending_category_var, values=PENDING_CATEGORIES, state="readonly", width=16).pack(side="left", padx=(6, 10))
        ttk.Label(filters, text="Search", style="CardBody.TLabel").pack(side="left")
        ttk.Entry(filters, textvariable=self.pending_search_var).pack(side="left", fill="x", expand=True, padx=(6, 10))
        ttk.Button(filters, text="Apply Filters", command=self.render_pending_current).pack(side="left")
        ttk.Button(filters, text="Reset Filters", command=self.reset_pending_filters).pack(side="left", padx=(6, 0))

        columns = ("idx", "support", "mode", "score", "risk", "due", "category", "command")
        self.pending_tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        widths = {"idx": 50, "support": 70, "mode": 80, "score": 100, "risk": 70, "due": 70, "category": 110, "command": 620}
        for column in columns:
            self.pending_tree.heading(column, text=column.upper())
            self.pending_tree.column(column, width=widths[column], anchor="w")
        self.pending_tree.pack(fill="both", expand=True)
        self.pending_tree.bind("<<TreeviewSelect>>", self.update_pending_selection_status)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Approve Selection", command=self.approve_selected_pending).pack(side="left")
        ttk.Button(buttons, text="Approve All", command=lambda: self.send_raw("APPROVE_PENDING(all)")).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Clear Selection", command=self.clear_selected_pending).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Clear All", command=lambda: self.send_raw("CLEAR_PENDING_COMMANDS(all)")).pack(side="left", padx=(6, 0))
        ttk.Label(frame, text="Sub-Agent Suggestion Candidates", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 4))
        self.pending_candidates_text = tk.Text(
            frame,
            height=7,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
        )
        self.pending_candidates_text.pack(fill="x")

        risk_buttons = ttk.Frame(frame)
        risk_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(risk_buttons, text="Approve Low", command=lambda: self.send_raw("APPROVE_PENDING(low)")).pack(side="left")
        ttk.Button(risk_buttons, text="Approve Medium", command=lambda: self.send_raw("APPROVE_PENDING(medium)")).pack(side="left", padx=(6, 0))
        ttk.Button(risk_buttons, text="Approve High", command=lambda: self.send_raw("APPROVE_PENDING(high)")).pack(side="left", padx=(6, 0))
        ttk.Button(risk_buttons, text="Clear Low", command=lambda: self.send_raw("CLEAR_PENDING_COMMANDS(low)")).pack(side="left", padx=(18, 0))
        ttk.Button(risk_buttons, text="Clear Medium", command=lambda: self.send_raw("CLEAR_PENDING_COMMANDS(medium)")).pack(side="left", padx=(6, 0))
        ttk.Button(risk_buttons, text="Clear High", command=lambda: self.send_raw("CLEAR_PENDING_COMMANDS(high)")).pack(side="left", padx=(6, 0))

    def _build_command_drip_tab(self):
        frame = self._new_work_page("Command Drip")
        self._add_workflow_status_strip(frame, "command_drip", "Command Drip")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Runtime Status", command=lambda: self.send_raw("SHOW_COMMAND_DRIP()")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Command Drip is the recent plus near-future command tree. Lookahead rows are candidate forecasts, "
                "not approvals; deferred/dropped/variant lanes explain what got pushed back or left behind."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.command_drip_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.command_drip_text.pack(fill="both", expand=True)

    def _build_chat_tab(self):
        frame = self._new_work_page("Chat")
        ttk.Label(frame, text="Historical chat log — includes messages no longer in current context.", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self._add_workflow_status_strip(frame, "chat", "Chat")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Recent 40", command=lambda: self.set_log_limit("chat", 40)).pack(side="left")
        ttk.Button(controls, text="Recent 200", command=lambda: self.set_log_limit("chat", 200)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="All", command=lambda: self.set_log_limit("chat", None)).pack(side="left", padx=(6, 0))
        self.chat_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="none")
        self.chat_text.pack(fill="both", expand=True)

    def _build_conversation_tab(self):
        frame = self._new_work_page("Conversation")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1, minsize=round(170 * ui_scale(self)))
        ttk.Label(frame, text="Conversation", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        self.conversation_status_var = tk.StringVar(value="Waiting for the runtime’s current conversation.")
        status_label = ttk.Label(frame, textvariable=self.conversation_status_var, style="Muted.TLabel", wraplength=round(780*ui_scale(self)))
        status_label.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        status_label.bind("<Configure>", lambda event: status_label.configure(wraplength=max(200, event.width-12)))
        tools = FlowBar(frame)
        tools.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.conversation_mode_var = tk.StringVar(value="Current context")
        self.conversation_system_var = tk.BooleanVar(value=False)
        self.conversation_time_var = tk.BooleanVar(value=bool(self.ui_preferences.get("conversation_time", True)))
        self.conversation_model_var = tk.BooleanVar(value=bool(self.ui_preferences.get("conversation_model", True)))
        self.conversation_edits_var = tk.BooleanVar(value=bool(self.ui_preferences.get("conversation_edits", True)))
        modes = tools.add(ttk.Combobox(tools, textvariable=self.conversation_mode_var,
            values=VIEW_MODES, state="readonly", width=24))
        modes.bind("<<ComboboxSelected>>", lambda _event: self.render_conversation())
        tools.add(ttk.Button(tools, text="Historical log", command=lambda: self.show_tab("Chat")))
        tools.add(ttk.Button(tools, text="Edit / pin…", command=self.edit_conversation_message))
        tools.add(ttk.Button(tools, text="Latest", command=lambda: self.conversation_text.see(tk.END)))
        self.restore_last_view_var = tk.BooleanVar(value=bool(self.ui_preferences.get("restore_last_view", False)))
        tools.add(ttk.Checkbutton(tools, text="Reopen last view", variable=self.restore_last_view_var))
        transcript = ConversationNavigator(frame, preferences=self.ui_preferences,
            mode=self.conversation_mode_var, system=self.conversation_system_var,
            times=self.conversation_time_var, models=self.conversation_model_var,
            edits=self.conversation_edits_var, on_change=self.render_conversation)
        transcript.grid(row=3, column=0, sticky="nsew")
        self.conversation_navigator = transcript
        self.conversation_text = transcript.text
        tools.add(ttk.Button(tools, text="⚙ View options", command=transcript.open_settings))
        self.conversation_activity_label = ttk.Label(frame, textvariable=self.conversation_activity_var,
            style="CardTitle.TLabel", wraplength=round(780*ui_scale(self)))
        self.conversation_activity_label.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        self.conversation_activity_label.bind("<Configure>", lambda event: self.conversation_activity_label.configure(wraplength=max(100, event.width)))
        self.conversation_composer = tk.Text(frame, bg=PANEL_2, fg=TEXT, insertbackground=TEXT,
            wrap="word", height=2, relief="flat", padx=12, pady=8, font=("Segoe UI", 11))
        self.conversation_awaiting = AwaitingReply(frame, self)
        self.conversation_awaiting.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        self.conversation_composer.grid(row=6, column=0, sticky="ew")
        self.conversation_composer.bind("<Control-Return>", self.send_conversation_message)
        send_row = FlowBar(frame)
        send_row.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self.conversation_send_button = send_row.add(ttk.Button(send_row, text="Send message", command=self.send_conversation_message))
        self.conversation_outbox_button = send_row.add(ttk.Button(send_row, text="Outbox (0)", command=self.open_conversation_outbox))
        send_row.add(ttk.Button(send_row, text="Quick start", command=self.show_conversation_quick_start))
        send_row.add(ttk.Label(send_row, text="Ctrl+Enter to send · Enter for a new line", style="Muted.TLabel"))
        self.conversation_delivery_var = tk.StringVar(value="Start the runtime, then enable inference for replies. Sending does not enable it.")
        delivery_label = ttk.Label(frame, textvariable=self.conversation_delivery_var, style="Muted.TLabel", wraplength=round(780*ui_scale(self)))
        delivery_label.grid(row=8, column=0, sticky="ew", pady=(5, 0))
        delivery_label.bind("<Configure>", lambda event: delivery_label.configure(wraplength=max(200, event.width-12)))
        self._conversation_revision = None

    def edit_conversation_message(self):
        row = self.conversation_navigator.selected_message()
        if not row:
            self.conversation_status_var.set("Click a message in the conversation, then choose Edit / pin message.")
            return None
        if row.get("exemption") == "PinnedInfo":
            self.conversation_status_var.set("This is a runtime-maintained summary. Select the original message to edit or pin it.")
            return None
        if row.get("retained") is not True or row.get("kind") != "text" or row.get("shortened") or row.get("historical_revision") or row.get("event"):
            self.conversation_status_var.set("Choose a complete retained text message in Current context or Retained messages. Historical revisions and screenshots are read-only.")
            return None
        return MessageEditor(self, row, root=ROOT, send=self.send_raw)

    def send_conversation_message(self, _event=None, *, composer=None):
        composer = composer if composer is not None else self.conversation_composer
        text = composer.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        prepared = self.conversation_outbox.prepare(text)
        try:
            record = append_external_message(text, raw=False, source="panel_conversation", subject="[AURORA CONVERSATION]",
                request_id=prepared["request_id"], message_id=prepared["message_id"])
        except Exception as error:
            self.conversation_outbox.track(prepared, uncertain=True)
            self.conversation_delivery_var.set(f"Queue write unconfirmed ({type(error).__name__}). Draft kept; inspect Outbox before resending.")
            self.refresh_conversation_feedback(update_preview=False)
            return "break"
        self.conversation_outbox.track(record)
        composer.delete("1.0", tk.END)
        paused = not bool((self.state_cache.get("modes", {}) or {}).get("live", False))
        self.conversation_delivery_var.set("Queued locally. " + ("Inference is paused; use Enable inference when ready. " if paused else "Waiting for the next inference. ") + "Track your message in Awaiting reply or Outbox.")
        self.refresh_conversation_feedback()
        self.mark_operator_activity("Queued conversation message for runtime ingestion")
        return "break"

    def open_conversation_outbox(self):
        window = self.conversation_outbox_window
        if window is None or not window.winfo_exists():
            window = self.conversation_outbox_window = OutboxWindow(self)
        window.deiconify()
        window.lift()
        window.refresh()
        return window

    def open_conversation_popout(self):
        if self.ui_preferences.get("legacy_chat_popout", False):
            return self.toggle_chat_head_request()
        window = self.conversation_popout_window
        if window is None or not window.winfo_exists():
            window = self.conversation_popout_window = ConversationPopout(self)
        window.deiconify()
        window.lift()
        self.render_conversation()
        return window

    def refresh_conversation_feedback(self, *, update_preview=True):
        self.conversation_outbox.poll()
        fresh = build_state_freshness_text(self.state_cache).startswith("State fresh |")
        self.conversation_activity_var.set(conversation_activity(self.state_cache, fresh=fresh))
        enhanced = self.ui_preferences.get("conversation_send_feedback", True)
        if enhanced:
            self.conversation_activity_label.grid()
        else:
            self.conversation_activity_label.grid_remove()
        if update_preview and self.conversation_outbox.rows:
            self.conversation_delivery_var.set(self.conversation_outbox.summary(include_text=enhanced))
        recovery = (self.state_cache.get("conversation_io") or {}).get("input_recovery") or {}
        retained = recovery.get("total", 0)
        suffix = f" · {retained} retained" if (self.state_cache.get("modes") or {}).get("input_recovery") == "durable" else ""
        self.conversation_outbox_button.configure(text=f"Outbox ({len(self.conversation_outbox.rows)}{suffix})")
        self.conversation_awaiting.refresh()
        popout = self.conversation_popout_window
        if popout is not None and popout.winfo_exists():
            popout.awaiting.refresh()
        window = self.conversation_outbox_window
        if window is not None and window.winfo_exists() and window.state() != "withdrawn":
            window.refresh()

    def show_conversation_quick_start(self):
        self._open_settings_text_dialog("Aurora quick start", (
            "1. Start runtime starts the worker with inference paused.\n"
            "2. Advanced settings shows models and execution policy; Dock settings keeps them beside chat.\n"
            "3. Send a message, then Enable inference when ready for paid requests. Pause inference when finished.\n"
            "4. Current context shows eligible conversation now. Retained messages and Historical log are separate views.\n"
            "5. Cancel work interrupts work; Stop runtime ends the worker.\n\n"
            "Use Maximize window if space is tight. The View selector exposes all tools.\n"
            "Full setup: README_FOR_HUMANS.md. For your coding assistant: README_FOR_AI.md.\n"
            "The older orb double-click still applies its activation profile; the main Enable inference button keeps your current settings."
        ), font=("Segoe UI", 11), height=480)

    def render_conversation(self):
        if hasattr(self, "conversation_navigator"):
            note = self.conversation_navigator.render(self.state_cache.get("conversation", {}))
            self.conversation_status_var.set(note)
            window = self.conversation_popout_window
            if window is not None and window.winfo_exists() and window.state() != "withdrawn":
                window.refresh(self.conversation_text.get("1.0", "end-1c"))
            return
        snapshot = self.state_cache.get("conversation", {})
        mode = "retained" if self.conversation_mode_var.get() == "Retained messages" else "current"
        view = snapshot.get(mode)
        if not isinstance(view, dict):
            self.conversation_status_var.set("Current conversation unavailable. Start an updated runtime; historical logs are separate.")
            content = "Your current conversation will appear here.\n\nMessages that decay, are deleted, or leave the current context window disappear from this view."
        else:
            all_rows = view.get("rows", [])
            shown_rows = all_rows if self.conversation_system_var.get() else [row for row in all_rows if row.get("role") != "system"]
            hidden_system = len(all_rows) - len(shown_rows)
            self.conversation_status_var.set(
                f"{len(shown_rows)} messages" + (f" · {hidden_system} system details hidden" if hidden_system else "") + " · "
                + ("Eligible conversation now; other prompt material is in Context details." if mode == "current" else "Retained runtime messages, including those outside the current context window.")
                + (f" {view.get('omitted', 0)} omitted / {view.get('shortened', 0)} shortened by display limits." if view.get('omitted') or view.get('shortened') else "")
            )
            content = conversation_text({"rows": shown_rows}, show_time=self.conversation_time_var.get(),
                show_model=self.conversation_model_var.get(), show_edits=self.conversation_edits_var.get()) or "No conversation messages in this view yet.\n\nSend a message below to begin. System details and historical logs are available above."
        revision = (mode, content)
        if revision != self._conversation_revision:
            at_bottom = self.conversation_text.yview()[1] >= 0.98
            old_position = self.conversation_text.yview()[0]
            self._write_text(self.conversation_text, content)
            for line, text in enumerate(content.splitlines(), 1):
                if text.startswith("User  "):
                    self.conversation_text.tag_add("user_role", f"{line}.0", f"{line}.end")
                elif text.startswith("Assistant  "):
                    self.conversation_text.tag_add("assistant_role", f"{line}.0", f"{line}.end")
            self.conversation_text.see(tk.END) if at_bottom else self.conversation_text.yview_moveto(old_position)
            self._conversation_revision = revision

    def _build_switchboard_tab(self):
        frame = self._new_work_page("The Switchboard")
        self.switchboard = Switchboard(frame, self, ROOT)
        self.switchboard.pack(fill="both", expand=True)

    def _build_command_tab(self):
        frame = self._new_work_page("Commands")
        self._add_workflow_status_strip(frame, "commands", "Commands")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Recent 40", command=lambda: self.set_log_limit("command", 40)).pack(side="left")
        ttk.Button(controls, text="Recent 200", command=lambda: self.set_log_limit("command", 200)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="All", command=lambda: self.set_log_limit("command", None)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Reset to preview defaults", command=lambda: self.switchboard.open_defaults()).pack(side="left", padx=(6, 0))
        self.command_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="none")
        self.command_text.pack(fill="both", expand=True)

    def _build_prompt_ledger_tab(self):
        frame = self._new_work_page("Prompt Ledger")
        self._add_workflow_status_strip(frame, "prompt_ledger", "Prompt Ledger")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 4))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Marks", command=lambda: self.send_raw("SHOW_CONTEXT_MARKS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Pins", command=lambda: self.send_raw("SHOW_PROMPT_PINS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Drops", command=lambda: self.send_raw("SHOW_DO_NOT_INCLUDE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Inclusion Gates", command=lambda: self.send_raw("SHOW_PROMPT_INCLUSION_READINESS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Preview Diff", command=lambda: self.send_raw("SHOW_PROMPT_INCLUSION_PREVIEW()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Rehearse Diff", command=lambda: self.send_raw("RUN_PROMPT_INCLUSION_PREVIEW_REHEARSAL()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Activation Review", command=lambda: self.send_raw("SHOW_PROMPT_INCLUSION_ACTIVATION_CHECKLIST()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="History Map", command=lambda: self.show_tab("History Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Visual Context", command=lambda: self.show_tab("Visual Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Context Files", command=lambda: self.show_tab("Context Files")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))

        activation_controls = ttk.Frame(frame)
        activation_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(activation_controls, text="Activation Status", command=lambda: self.send_raw("SHOW_PROMPT_INCLUSION_ACTIVATION()")).pack(side="left")
        ttk.Button(
            activation_controls,
            text="Enable Proof",
            command=lambda: self.send_raw("SET_PROMPT_INCLUSION_ACTIVATION(on, preview_id=latest, checklist_id=latest, confirm=offline_proof)"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            activation_controls,
            text="Disable",
            command=lambda: self.send_raw("SET_PROMPT_INCLUSION_ACTIVATION(off, confirm=rollback)"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            activation_controls,
            text="Closure Check",
            command=lambda: self.send_raw("RUN_PROMPT_INCLUSION_CLOSURE_CHECK()"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            activation_controls,
            text="Show Closure",
            command=lambda: self.send_raw("SHOW_PROMPT_INCLUSION_CLOSURE()"),
        ).pack(side="left", padx=(6, 0))

        mark_controls = ttk.Frame(frame)
        mark_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(
            mark_controls,
            text="Request Prompt Pin",
            command=lambda: self.send_raw('REQUEST_PROMPT_PIN(latest, note="Control Panel requested prompt pin")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            mark_controls,
            text="Approve Latest Pin",
            command=lambda: self.send_raw('APPROVE_PROMPT_PIN(latest, note="Control Panel approval")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            mark_controls,
            text="Reject Latest Pin",
            command=lambda: self.send_raw('REJECT_PROMPT_PIN(latest, note="Control Panel rejection")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            mark_controls,
            text="Local Pin",
            command=lambda: self.send_raw('MARK_TURN(latest, mark_type=operator_pin, note="Control Panel local pin")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            mark_controls,
            text="Do Not Include",
            command=lambda: self.send_raw('MARK_DO_NOT_INCLUDE(latest, note="Control Panel do-not-include mark")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            mark_controls,
            text="Clear Drops",
            command=lambda: self.send_raw("CLEAR_DO_NOT_INCLUDE(all)"),
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Prompt Ledger maps what Aurora included or could include, what it retained locally, what is available on disk, "
                "what is retrievable, what was omitted, and which writable metadata marks are visible but not model-visible yet."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.prompt_ledger_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.prompt_ledger_text.pack(fill="both", expand=True)

    def _build_agents_tab(self):
        frame = self._new_work_page("Agents")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 4))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Agents", command=lambda: self.send_raw("SHOW_AGENTS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show ACLs", command=lambda: self.send_raw("SHOW_AGENT_HISTORY_ACLS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show History", command=lambda: self.send_raw("SHOW_AGENT_HISTORY()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Routes", command=lambda: self.send_raw("SHOW_AGENT_SUGGESTION_ROUTES()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Suggestions", command=lambda: self.send_raw("SHOW_AGENT_SUGGESTIONS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Tasks", command=lambda: self.send_raw("SHOW_AGENT_TASKS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Pending Gate", command=lambda: self.send_raw("SHOW_AGENT_PENDING_GATE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Insert Check", command=lambda: self.send_raw("SHOW_AGENT_PENDING_INSERT_CHECKLIST()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Dry Run Insert", command=lambda: self.send_raw("RUN_AGENT_PENDING_INSERT_DRY_RUN()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Insert Ready", command=self.insert_latest_agent_pending_dry_run).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Run Closure", command=lambda: self.send_raw("RUN_AGENT_HELPER_CLOSURE_CHECK()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Closure", command=lambda: self.send_raw("SHOW_AGENT_HELPER_CLOSURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Prompt Ledger", command=lambda: self.show_tab("Prompt Ledger")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="History Map", command=lambda: self.show_tab("History Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))

        agent_controls = ttk.Frame(frame)
        agent_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(
            agent_controls,
            text="Summon Scout",
            command=lambda: self.send_raw('SUMMON_AGENT(scout, role="visual/context scout", rank=2, urgency=1, history=private|parent_visible, deny=PYAG:*|GB:*|SET_LIVE_MODE)'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            agent_controls,
            text="Mod Scout",
            command=lambda: self.send_raw('MOD_AGENT(scout, urgency=3, note="Control Panel metadata update")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            agent_controls,
            text="Silence Scout",
            command=lambda: self.send_raw('SILENCE_AGENT(scout, note="Control Panel silence")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            agent_controls,
            text="Suggest Status",
            command=lambda: self.send_raw('SUGGEST_AGENT_COMMAND(scout, command=SHOW_RUNTIME(), reason="Control Panel metadata-only status suggestion", risk=low)'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            agent_controls,
            text="Append Note",
            command=lambda: self.send_raw('APPEND_AGENT_HISTORY(scout, visibility=private, summary="Control Panel private scout note", text="Operator recorded a private scout note from the Agents tab.")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            agent_controls,
            text="Append Summary",
            command=lambda: self.send_raw('APPEND_AGENT_HISTORY(scout, visibility=parent_visible, summary="Control Panel parent-visible scout summary", text="Operator recorded a parent-visible scout summary from the Agents tab.")'),
        ).pack(side="left", padx=(6, 0))
        task_controls = ttk.Frame(frame)
        task_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(
            task_controls,
            text="Assign Task",
            command=lambda: self.send_raw('ASSIGN_AGENT_TASK(scout, title="Control Panel scout task", objective="Record a metadata-only scout work brief from the Agents tab.", expected="Task packet visible in Agents and Prompt Ledger", visibility=parent_visible, priority=3, tags=control_panel|task_packet)'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            task_controls,
            text="Review Task",
            command=lambda: self.send_raw('SET_AGENT_TASK_STATUS(latest, status=review, note="Control Panel review metadata")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            task_controls,
            text="Close Task",
            command=lambda: self.send_raw('SET_AGENT_TASK_STATUS(latest, status=closed, note="Control Panel closed metadata")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            task_controls,
            text="Link Review",
            command=lambda: self.send_raw('LINK_AGENT_TASK_SUGGESTION(latest, suggestion=latest, note="Control Panel task/suggestion review link")'),
        ).pack(side="left", padx=(6, 0))
        suggestion_controls = ttk.Frame(frame)
        suggestion_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(
            suggestion_controls,
            text="Approve Latest",
            command=lambda: self.send_raw('APPROVE_AGENT_SUGGESTION(latest, note="Control Panel review approval")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            suggestion_controls,
            text="Stage Latest",
            command=lambda: self.send_raw('STAGE_AGENT_SUGGESTION(latest, note="Control Panel candidate staging")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            suggestion_controls,
            text="Mark Provenance",
            command=lambda: self.send_raw('MARK_AGENT_SUGGESTION_PROVENANCE(latest, mark_type=operator_pin, note="Control Panel provenance mark")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            suggestion_controls,
            text="Reject Latest",
            command=lambda: self.send_raw('REJECT_AGENT_SUGGESTION(latest, note="Control Panel review rejection")'),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            suggestion_controls,
            text="Suggest Blocked Py",
            command=lambda: self.send_raw('SUGGEST_AGENT_COMMAND(scout, command=PYAG:blocked_test, reason="Control Panel blocked policy check", risk=high)'),
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Agent Registry records parent/sub-agent roles, command policy, "
                "rank, urgency, history ACL intent, and private-history audit-log paths without spawning workers, calling models, "
                "writing parent chat history, or making hidden model-visible changes. Explicit private-history appends "
                "write only per-agent JSONL audit rows. Suggestion rows and task packets are append-only audit metadata; "
                "only exact-confirmed dry-run rows can enter the held Pending queue, and they still require normal Pending approval before execution."
                " Closure readiness keeps those promises visible before the roadmap moves on."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.agent_registry_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.agent_registry_text.pack(fill="both", expand=True)

    def _build_history_context_tab(self):
        frame = self._new_work_page("History Context")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Inventory", command=lambda: self.send_raw("SHOW_HISTORY_CONTEXT_SERVICE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Companion Ready", command=lambda: self.send_raw("SHOW_COMPANION_CONTRACT_READINESS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Protocol", command=lambda: self.send_raw("SHOW_COMPANION_PROTOCOL_CONTRACT()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Receipts", command=lambda: self.send_raw("SHOW_COMPANION_RECEIPT_AUDIT()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Run Closure", command=lambda: self.send_raw("RUN_COMPANION_CONTRACT_CLOSURE_CHECK()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Closure", command=lambda: self.send_raw("SHOW_COMPANION_CONTRACT_CLOSURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Prompt Ledger", command=lambda: self.show_tab("Prompt Ledger")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Agents", command=lambda: self.show_tab("Agents")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Context Files", command=lambda: self.show_tab("Context Files")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "History Context is the Window 16 inventory surface. It maps where chat history, prompt ledger data, "
                "context marks, image sidecars, agent ACLs, suggestion audit rows, and companion read/write boundaries live before cleanup work moves them behind a cleaner service. "
                "Window 21 companion readiness keeps Portal/Chats/Browser/AGB contracts visible while integrations stay parked."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.history_context_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.history_context_text.pack(fill="both", expand=True)

    def _build_portal_intake_tab(self):
        frame = self._new_work_page("Portal Intake")
        self._add_workflow_status_strip(frame, "portal_intake", "Portal Intake")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Intake", command=lambda: self.send_raw("SHOW_PORTAL_COMPANION_INTAKE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Gates", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_GATES()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Review Packets", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_REVIEW()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Registry Contract", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_REGISTRY()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Audit Matrix", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_AUDIT()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Evidence Docket", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_DOCKET()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Handoff Packets", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_HANDOFFS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Proof Ledger", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_PROOF()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Operator Report", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_REPORT()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Unblockers", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_UNBLOCKERS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Waitlist", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_WAITLIST()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Parking", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_PARKING()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Closure", command=lambda: self.send_raw("SHOW_PORTAL_INTAKE_CLOSURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Companion Contract", command=lambda: self.send_raw("SHOW_COMPANION_CONTRACT_CLOSURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Overview", command=lambda: self.show_tab("Overview")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="History Map", command=lambda: self.show_tab("History Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))
        self.portal_intake_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.portal_intake_text.pack(fill="both", expand=True)

    def _build_visual_context_tab(self):
        frame = self._new_work_page("Visual Context")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Screenshots", command=lambda: self.show_tab("Screenshots")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Images In Memory", command=lambda: self.show_tab("Images In Memory")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Image Index", command=lambda: self.show_tab("Image Index")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Visual context lanes: In Prompt is what the model just got or can get through recent prompt history; "
                "Retained is Aurora's visual-memory metadata; Local Only is recent screenshot files on disk."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.visual_context_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.visual_context_text.pack(fill="both", expand=True)

    def _build_image_context_index_tab(self):
        frame = self._new_work_page("Image Index")
        self._add_workflow_status_strip(frame, "image_index", "Image Index")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Index", command=lambda: self.send_raw("SHOW_IMAGE_CONTEXT_INDEX()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Cost", command=lambda: self.send_raw("SHOW_IMAGE_COST_POSTURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Backfill Recent 24", command=lambda: self.send_raw("BACKFILL_IMAGE_CONTEXT_INDEX(24)")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Visual Context", command=lambda: self.show_tab("Visual Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Screenshots", command=lambda: self.show_tab("Screenshots")).pack(side="left", padx=(6, 0))
        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Search", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(search_row, textvariable=self.image_index_search_var, width=36).pack(side="left", padx=(0, 6))
        ttk.Button(search_row, text="Search Index", command=self.search_image_context_index).pack(side="left")
        ttk.Label(
            frame,
            text=(
                "Image Index is the Window 12 metadata shelf for screenshot sidecars. "
                "Captures keep immutable IDs; legacy filenames remain readable. Capture reason, prompt-context state, hashes, captions/OCR/tags, and embedding ids live here."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.image_context_index_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.image_context_index_text.pack(fill="both", expand=True)

    def _build_live_harness_tab(self):
        frame = self._new_work_page("Live Harness")
        self._add_workflow_status_strip(frame, "live_harness", "Live Harness")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Harness", command=lambda: self.send_raw("SHOW_LIVE_VISUAL_HARNESS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Run Offline Rehearsal", command=lambda: self.send_raw("RUN_LIVE_VISUAL_HARNESS_REHEARSAL()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Rehearsal", command=lambda: self.send_raw("SHOW_LIVE_VISUAL_HARNESS_REHEARSAL()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Safe Offline", command=lambda: self.apply_operator_profile("Safe Offline")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Cheap Visual Test", command=lambda: self.apply_operator_profile("Cheap Visual Test")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Visual Context", command=lambda: self.show_tab("Visual Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Prompt Ledger", command=lambda: self.show_tab("Prompt Ledger")).pack(side="left", padx=(6, 0))
        probe_controls = ttk.Frame(frame)
        probe_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(probe_controls, text="Arm Cheap Probe", command=lambda: self.send_raw("ARM_CHEAP_LIVE_VISUAL_HARNESS()")).pack(side="left")
        ttk.Button(probe_controls, text="Arm Strong Probe", command=lambda: self.send_raw("ARM_STRONG_LIVE_VISUAL_HARNESS()")).pack(side="left", padx=(6, 0))
        ttk.Button(probe_controls, text="Queue Probe Prompt", command=lambda: self.send_raw("QUEUE_LIVE_VISUAL_HARNESS_PROBE_PROMPT()")).pack(side="left", padx=(6, 0))
        ttk.Button(probe_controls, text="Record Probe", command=lambda: self.send_raw("RECORD_LIVE_VISUAL_HARNESS_PROBE_RESULT()")).pack(side="left", padx=(6, 0))
        ttk.Button(probe_controls, text="Show Probe", command=lambda: self.send_raw("SHOW_LIVE_VISUAL_HARNESS_PROBE()")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Live Harness is the Window 11 contract surface. It names what Aurora expects the model to see "
                "before any live probe, keeps setup/cleanup safe, and escalates from offline rehearsal to cheap live checks "
                "before stronger models."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.live_harness_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.live_harness_text.pack(fill="both", expand=True)

    def _build_responses_shadow_tab(self):
        frame = self._new_work_page("Responses Shadow")
        self._add_workflow_status_strip(frame, "responses_shadow", "Responses Shadow")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Show Contract", command=lambda: self.send_raw("SHOW_RESPONSES_SHADOW_TRANSPORT()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Build Preview", command=lambda: self.send_raw("BUILD_RESPONSES_SHADOW_PAYLOAD_PREVIEW()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Payload", command=lambda: self.send_raw("SHOW_RESPONSES_SHADOW_PAYLOAD_PREVIEW()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Build Posture", command=lambda: self.send_raw("BUILD_RESPONSES_SHADOW_OFFLINE_POSTURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Show Posture", command=lambda: self.send_raw("SHOW_RESPONSES_SHADOW_OFFLINE_POSTURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Model Status", command=lambda: self.send_raw("SHOW_MODEL_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Prompt Ledger", command=lambda: self.show_tab("Prompt Ledger")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Visual Context", command=lambda: self.show_tab("Visual Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="History Map", command=lambda: self.show_tab("History Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Live Harness", command=lambda: self.show_tab("Live Harness")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))
        probe_controls = ttk.Frame(frame)
        probe_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(probe_controls, text="Arm Cheap Probe", command=lambda: self.send_raw("ARM_CHEAP_RESPONSES_SHADOW_PROBE()")).pack(side="left")
        ttk.Button(probe_controls, text="Arm Nano Probe", command=lambda: self.send_raw("ARM_CHEAP_RESPONSES_SHADOW_PROBE(nano)")).pack(side="left", padx=(6, 0))
        ttk.Button(probe_controls, text="Show Probe", command=lambda: self.send_raw("SHOW_RESPONSES_SHADOW_PROBE()")).pack(side="left", padx=(6, 0))
        ttk.Button(probe_controls, text="Clear Probe", command=lambda: self.send_raw("CLEAR_RESPONSES_SHADOW_PROBE()")).pack(side="left", padx=(6, 0))
        closure_controls = ttk.Frame(frame)
        closure_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(closure_controls, text="Run Closure Check", command=lambda: self.send_raw("RUN_RESPONSES_SHADOW_CLOSURE_CHECK()")).pack(side="left")
        ttk.Button(closure_controls, text="Show Closure", command=lambda: self.send_raw("SHOW_RESPONSES_SHADOW_CLOSURE()")).pack(side="left", padx=(6, 0))
        ttk.Button(closure_controls, text="Monitor", command=lambda: self.send_raw("SHOW_MONITOR_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Responses Shadow is the Window 17 comparison surface. It shows what would need to match before a "
                "Responses transport trial, then checks closure/fallback readiness without switching Aurora away from "
                "chat/completions or spending model calls."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.responses_shadow_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.responses_shadow_text.pack(fill="both", expand=True)

    def _build_context_files_tab(self):
        frame = self._new_work_page("Context Files")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Visual Context", command=lambda: self.show_tab("Visual Context")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="History Map", command=lambda: self.show_tab("History Context")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Context Files is a read-only shelf for important local files and folders. "
                "Rows here are visible to the operator; they are not attached to the model prompt by this shelf."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        self.context_files_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.context_files_text.pack(fill="both", expand=True)

    def _build_settings_safety_tab(self):
        frame = self._new_work_page("Recovery")
        self._add_workflow_status_strip(frame, "settings_safety", "Recovery")
        self.recovery_home_risk_var = tk.StringVar(value="Risk: not loaded")
        self.recovery_home_profile_var = tk.StringVar(value="Profile: waiting for state")
        self.recovery_home_restore_var = tk.StringVar(value="Restore: waiting for defaults")
        self.recovery_home_checkpoint_var = tk.StringVar(value="Checkpoint: waiting for readiness")
        self.recovery_home_next_var = tk.StringVar(value="Next: refresh state, then choose a confirmed profile or restore action.")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        ttk.Button(controls, text="Runtime", command=lambda: self.send_raw("SHOW_RUNTIME()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Health", command=lambda: self.send_raw("SHOW_RUNTIME_HEALTH()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Risk", command=lambda: self.send_raw("SHOW_OPERATOR_RISK_SUMMARY()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Model", command=lambda: self.send_raw("SHOW_MODEL_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Monitor", command=lambda: self.send_raw("SHOW_MONITOR_STATUS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Locks", command=lambda: self.send_raw("SHOW_LOCKS()")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Defaults", command=lambda: self.send_raw("SHOW_DEFAULT_PROFILES()")).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls,
            text="Apply System",
            command=lambda: self.confirm_and_send_raw("APPLY_SYSTEM_DEFAULTS()", "Apply Aurora's built-in system defaults?"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls,
            text="Apply Personal",
            command=lambda: self.confirm_and_send_raw("APPLY_PERSONAL_DEFAULTS()", "Apply your saved personal defaults?"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls,
            text="Save Personal",
            command=lambda: self.confirm_and_send_raw("SAVE_PERSONAL_DEFAULTS()", "Save the current settings as your personal defaults?"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Raw State", command=lambda: self.show_tab("Raw State")).pack(side="left", padx=(6, 0))
        ttk.Label(
            frame,
            text=(
                "Read-only settings safety inventory. It classifies visible controls by the kind of operator "
                "attention they deserve. Known-good profiles set coherent baselines, and diagnostics call out odd current-state combinations."
            ),
            style="CardBody.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        home_row = ttk.Frame(frame)
        home_row.pack(fill="x", pady=(0, 8))
        for column in range(4):
            home_row.columnconfigure(column, weight=1, uniform="recovery-home")
        for column, (title, variable) in enumerate(
            [
                ("Current Risk", self.recovery_home_risk_var),
                ("Profile Suggestion", self.recovery_home_profile_var),
                ("Restore Confidence", self.recovery_home_restore_var),
                ("Checkpoint Readiness", self.recovery_home_checkpoint_var),
            ]
        ):
            card = ttk.Frame(home_row, style="Card.TFrame", padding=10)
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8), pady=(0, 6))
            ttk.Label(card, text=title, style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 4))
            ttk.Label(
                card,
                textvariable=variable,
                style="CardBody.TLabel",
                wraplength=250,
                justify="left",
            ).pack(anchor="w", fill="x")
        ttk.Label(
            frame,
            textvariable=self.recovery_home_next_var,
            style="SectionHint.TLabel",
            wraplength=1120,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 8))
        link_row = ttk.Frame(frame)
        link_row.pack(fill="x", pady=(0, 8))
        ttk.Label(link_row, text="Diagnostic Links", style="SectionTitle.TLabel").pack(side="left", padx=(0, 8))
        ttk.Button(link_row, text="Checkpoint", command=lambda: self.send_raw("SHOW_CHECKPOINT_READINESS()")).pack(side="left", padx=(0, 6))
        for label, target in [
            ("Pending", "Pending"),
            ("Prompt Ledger", "Prompt Ledger"),
            ("Image Index", "Image Index"),
            ("Visual Context", "Visual Context"),
            ("History Context", "History Context"),
            ("Responses Shadow", "Responses Shadow"),
        ]:
            ttk.Button(link_row, text=label, command=lambda tab=target: self.show_tab(tab)).pack(side="left", padx=(0, 6))
        profile_row = ttk.Frame(frame)
        profile_row.pack(fill="x", pady=(0, 8))
        ttk.Label(profile_row, text="Known Good Profiles", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=(4, 0))
        recovery_buttons = ttk.Frame(profile_row)
        recovery_buttons.grid(row=0, column=1, sticky="ew")
        profile_row.columnconfigure(1, weight=1)
        for column in range(3):
            recovery_buttons.columnconfigure(column, weight=1, uniform="recovery-profile")
        for index, profile_name in enumerate(RECOVERY_PROFILE_NAMES):
            ttk.Button(
                recovery_buttons,
                text=profile_name,
                command=lambda selected=profile_name: self.apply_operator_profile(selected),
            ).grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 6), pady=(0, 4))
        self.settings_safety_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.settings_safety_text.pack(fill="both", expand=True)

    def _build_screenshots_tab(self):
        frame = self._new_work_page("Screenshots")
        self._add_workflow_status_strip(frame, "screenshots", "Screenshots")
        self.screenshot_meta = ttk.Label(frame, text="", style="Muted.TLabel")
        self.screenshot_meta.pack(anchor="w", pady=(0, 6))
        ttk.Label(
            frame,
            text="Double-click preview to open the popout viewer. Click left/right edges or use arrow keys to browse. Use Fit / 1:1 / Esc there.",
            style="CardBody.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        preview_shell = ttk.Frame(frame, style="Card.TFrame", padding=8)
        preview_shell.pack(fill="both", expand=True)
        self.screenshot_preview = ttk.Label(preview_shell, text="No screenshot loaded.", anchor="center")
        self.screenshot_preview.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(8, 6))
        ttk.Button(controls, text="Prev", command=lambda: self.step_screenshot(-1)).pack(side="left")
        ttk.Button(controls, text="Latest", command=self.jump_to_latest_screenshot).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Pause Follow", command=self.pause_screenshot_follow_latest).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Next", command=lambda: self.step_screenshot(1)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Pop Out", command=self.open_screenshot_popout).pack(side="left", padx=(18, 0))

        thumb_shell = ttk.Frame(frame, style="Card.TFrame", padding=6)
        thumb_shell.pack(fill="x")
        self.thumbnail_canvas = tk.Canvas(thumb_shell, bg=PANEL, highlightthickness=0, height=118)
        self.thumbnail_scroll = ttk.Scrollbar(thumb_shell, orient="horizontal", command=self.thumbnail_canvas.xview)
        self.thumbnail_canvas.configure(xscrollcommand=self.thumbnail_scroll.set)
        self.thumbnail_canvas.pack(fill="x", expand=True)
        self.thumbnail_scroll.pack(fill="x")
        self.thumbnail_inner = ttk.Frame(self.thumbnail_canvas)
        self.thumbnail_window = self.thumbnail_canvas.create_window((0, 0), window=self.thumbnail_inner, anchor="nw")
        self.thumbnail_inner.bind("<Configure>", self._refresh_thumbnail_region)
        self.thumbnail_canvas.bind("<Configure>", self._resize_thumbnail_window)
        self.screenshot_preview.bind("<Double-Button-1>", lambda _event: self.open_screenshot_popout())
        self.screenshot_preview.bind("<Button-1>", self.on_screenshot_preview_click)
        self.screenshot_preview.bind("<Configure>", self.invalidate_screenshot_preview)

    def _build_image_memory_tab(self):
        frame = self._new_work_page("Images In Memory")
        self._add_workflow_status_strip(frame, "image_memory", "Images")
        self.image_memory_meta = ttk.Label(frame, text="", style="Muted.TLabel")
        self.image_memory_meta.pack(anchor="w", pady=(0, 6))
        ttk.Label(
            frame,
            text="Retained visual-memory entries still on hand. Double-click preview for popout viewer. Click left/right edges or use arrow keys to browse.",
            style="CardBody.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        preview_shell = ttk.Frame(frame, style="Card.TFrame", padding=8)
        preview_shell.pack(fill="both", expand=True)
        self.image_memory_preview = ttk.Label(preview_shell, text="No retained image memory available.", anchor="center")
        self.image_memory_preview.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(8, 6))
        ttk.Button(controls, text="Prev", command=lambda: self.step_image_memory(-1)).pack(side="left")
        ttk.Button(controls, text="Latest", command=self.jump_to_latest_image_memory).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Next", command=lambda: self.step_image_memory(1)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Pop Out", command=self.open_image_memory_popout).pack(side="left", padx=(18, 0))

        thumb_shell = ttk.Frame(frame, style="Card.TFrame", padding=6)
        thumb_shell.pack(fill="x")
        self.memory_thumbnail_canvas = tk.Canvas(thumb_shell, bg=PANEL, highlightthickness=0, height=118)
        self.memory_thumbnail_scroll = ttk.Scrollbar(thumb_shell, orient="horizontal", command=self.memory_thumbnail_canvas.xview)
        self.memory_thumbnail_canvas.configure(xscrollcommand=self.memory_thumbnail_scroll.set)
        self.memory_thumbnail_canvas.pack(fill="x", expand=True)
        self.memory_thumbnail_scroll.pack(fill="x")
        self.memory_thumbnail_inner = ttk.Frame(self.memory_thumbnail_canvas)
        self.memory_thumbnail_window = self.memory_thumbnail_canvas.create_window((0, 0), window=self.memory_thumbnail_inner, anchor="nw")
        self.memory_thumbnail_inner.bind("<Configure>", self._refresh_memory_thumbnail_region)
        self.memory_thumbnail_canvas.bind("<Configure>", self._resize_memory_thumbnail_window)
        self.image_memory_preview.bind("<Double-Button-1>", lambda _event: self.open_image_memory_popout())
        self.image_memory_preview.bind("<Button-1>", self.on_image_memory_preview_click)
        self.image_memory_preview.bind("<Configure>", self.invalidate_image_memory_preview)

    def _build_help_tab(self):
        frame = self._new_work_page("Help")
        self.help_tab = frame
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Top", command=self.show_help_tab).pack(side="left")
        ttk.Button(controls, text="Command List", command=self.show_command_list).pack(side="left", padx=(6, 0))
        self.help_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.help_text.pack(fill="both", expand=True)
        self._write_text(self.help_text, HELP_TEXT)

    def _build_raw_tab(self):
        frame = self._new_work_page("Raw State")
        self._add_workflow_status_strip(frame, "raw", "Raw State")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Refresh", command=self.refresh_now).pack(side="left")
        self.raw_text = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="none")
        self.raw_text.pack(fill="both", expand=True)

    def _is_dashboard_popout_open(self):
        return bool(
            self.dashboard_popout_window is not None
            and self.dashboard_popout_window.winfo_exists()
        )

    def toggle_dashboard_popout(self):
        if self._is_dashboard_popout_open():
            self.close_dashboard_popout()
        else:
            self.open_dashboard_popout()

    def open_dashboard_popout(self):
        if self._is_dashboard_popout_open():
            self.dashboard_popout_window.deiconify()
            self.dashboard_popout_window.lift()
            self.refresh_dashboard(self.state_cache or None)
            return

        self.dashboard_popout_window = tk.Toplevel(self)
        self.dashboard_popout_window.title("Aurora Operator Dashboard")
        geometry = fit_popout_window(self.dashboard_popout_window, 1120, 760, self)
        self.dashboard_popout_window.minsize(min(760, geometry["width"]), min(520, geometry["height"]))
        self.dashboard_popout_window.configure(bg=BG)
        self.dashboard_popout_window.protocol("WM_DELETE_WINDOW", self.close_dashboard_popout)
        self.dashboard_popout_window.bind(
            "<Escape>",
            lambda _event: self.close_dashboard_popout(),
        )

        header = ttk.Frame(self.dashboard_popout_window, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Operator Dashboard", style="SectionTitle.TLabel").pack(side="left")
        ttk.Button(
            header,
            text="Refresh",
            command=lambda: self.refresh_dashboard(self.state_cache or None),
        ).pack(side="right", padx=(6, 0))
        ttk.Button(header, text="Close", command=self.close_dashboard_popout).pack(side="right")
        ttk.Checkbutton(header, text="Wrap detail", variable=self.dashboard_wrap_var,
                        command=self._update_dashboard_wrap).pack(side="right", padx=8)
        observed = ttk.Label(self.dashboard_popout_window, textvariable=self.dashboard_popout_summary_var,
                             wraplength=1000, justify="left", padding=(12, 6))
        observed.pack(fill="x")
        observed.bind("<Configure>", lambda event: observed.configure(wraplength=max(240, event.width - 24)))

        detail_shell = ttk.Frame(self.dashboard_popout_window, padding=(12, 0, 12, 12))
        detail_shell.pack(fill="both", expand=True)
        self.dashboard_popout_text = tk.Text(
            detail_shell,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word" if self.dashboard_wrap_var.get() else "none",
            font=("Consolas", 10),
        )
        popout_y = ttk.Scrollbar(
            detail_shell,
            orient="vertical",
            command=self.dashboard_popout_text.yview,
        )
        popout_x = ttk.Scrollbar(
            detail_shell,
            orient="horizontal",
            command=self.dashboard_popout_text.xview,
        )
        self.dashboard_popout_text.configure(
            yscrollcommand=popout_y.set,
            xscrollcommand=popout_x.set,
        )
        self.dashboard_popout_text.grid(row=0, column=0, sticky="nsew")
        popout_y.grid(row=0, column=1, sticky="ns")
        popout_x.grid(row=1, column=0, sticky="ew")
        detail_shell.rowconfigure(0, weight=1)
        detail_shell.columnconfigure(0, weight=1)
        if self.dashboard_popout_button is not None:
            self.dashboard_popout_button.configure(text="Close Popout")
        self.refresh_dashboard(self.state_cache or None)

    def close_dashboard_popout(self):
        if self._is_dashboard_popout_open():
            self.dashboard_popout_window.destroy()
        self.dashboard_popout_window = None
        self.dashboard_popout_text = None
        if self.dashboard_popout_button is not None:
            self.dashboard_popout_button.configure(text="Open Popout")
        self.dashboard_status_var.set("Dashboard popout closed.")

    def refresh_dashboard(self, state=None):
        try:
            snapshot = build_operator_dashboard(
                ROOT,
                event_limit=12,
                state_snapshot=state if isinstance(state, dict) else None,
            )
        except Exception as error:
            message = f"Dashboard unavailable: {error}"
            self.dashboard_status_var.set(message)
            if self.dashboard_text is not None:
                self._write_text(self.dashboard_text, message)
            if self.dashboard_popout_text is not None:
                self._write_text(self.dashboard_popout_text, message)
            return

        self.dashboard_snapshot = snapshot
        summary = snapshot.get("summary", {}) or {}
        runtime = snapshot.get("runtime", {}) or {}
        panel = snapshot.get("control_panel", {}) or {}
        state_status = snapshot.get("state", {}) or {}
        modes = snapshot.get("modes", {}) or {}
        models = snapshot.get("models", {}) or {}
        scheduler = snapshot.get("scheduler", {}) or {}
        monitor = snapshot.get("monitor", {}) or {}
        queue_bridge = snapshot.get("queue_bridge", {}) or {}
        mutation = snapshot.get("mutation_admission", {}) or {}
        settings = snapshot.get("settings", {}) or {}
        event_rows = (snapshot.get("events", {}) or {}).get("rows", []) or []

        freshness = str(summary.get("state_freshness") or "unknown")
        qualifier = "" if freshness == "fresh" and runtime.get("running") else f"Last observed ({freshness})\n"
        def observed_flag(value):
            return "yes" if value is True else "no" if value is False else "unknown"

        values = {
            "runtime": (
                f"{str(summary.get('runtime_status') or 'unknown').upper()} | pid {runtime.get('pid') or '-'}\n"
                f"Panel {str(summary.get('control_panel_status') or 'unknown')} | pid {panel.get('pid') or '-'}\n"
                f"State {summary.get('state_freshness') or 'unknown'} | age {state_status.get('age_seconds') if state_status.get('age_seconds') is not None else '-'}s"
            ),
            "operation": (
                qualifier + f"Inference {('on' if modes['live'] else 'off') if type(modes.get('live')) is bool else 'unknown'} | {modes.get('execution') or '-'} / {modes.get('action') or '-'}\n"
                f"{models.get('text') or '-'} | effort {models.get('reasoning_effort') or '-'}\n"
                f"Scheduler {scheduler.get('profile') or '-'} / {scheduler.get('mode') or '-'}"
            ),
            "control_plane": (
                qualifier + f"Monitor {monitor.get('overall_status') or 'unknown'} | pending {queue_bridge.get('pending_count', 'unknown')}\n"
                f"Bridge caught up {observed_flag(queue_bridge.get('bridge_caught_up'))} | results {observed_flag(queue_bridge.get('command_result_caught_up'))}\n"
                f"Mutations {mutation.get('terminal_count') or 0}/{mutation.get('reserved_count') or 0} terminal | uncertain {mutation.get('uncertain_count') or 0}"
            ),
            "settings": (
                qualifier + f"{settings.get('count') or 0} registered | {settings.get('effective_count') or 0} effective\n"
                f"Locked {settings.get('locked_count') or 0} | runtime_session only\n"
                f"Version {short(settings.get('version') or '-', 34)}"
            ),
        }
        for key, value in values.items():
            value_var = self.dashboard_summary_vars.get(key)
            if value_var is not None and value_var.get() != value:
                value_var.set(value)

        event_signature = json.dumps(event_rows, sort_keys=True, ensure_ascii=False)
        if self.dashboard_events_tree is not None and event_signature != self._last_dashboard_event_signature:
            items, by_id = receipt_tree_items(event_rows)
            reconcile_tree_rows(self.dashboard_events_tree, items)
            self._dashboard_events_by_iid = by_id
            self._last_dashboard_event_signature = event_signature
            self._show_dashboard_receipt()

        rendered = format_operator_dashboard(snapshot)
        if self.dashboard_text is not None:
            self._write_text(self.dashboard_text, rendered)
        if self.dashboard_popout_text is not None:
            self._write_text(self.dashboard_popout_text, rendered)
        self.dashboard_popout_summary_var.set(
            " | ".join((values["runtime"].replace("\n", " | "), values["operation"].replace("\n", " | ")))
        )
        view_status = "popout open" if self._is_dashboard_popout_open() else "tab ready"
        self.dashboard_status_var.set(
            f"Observed {snapshot.get('observed_at') or '-'} | {len(event_rows)} receipts | {view_status}."
        )

    @staticmethod
    def sanitize_operator_activity_command(command):
        text = str(command or "")
        stripped = text.lstrip()
        upper = stripped.upper()
        for name in ("SET_OPERATOR_PASSCODE", "AUTHORIZE_OPERATOR"):
            if upper.startswith(name + "("):
                return f"{name}(*******)"
        return text

    def mark_operator_activity(self, message):
        if hasattr(self, "operator_activity_var"):
            self.operator_activity_var.set(f"{time.strftime('%H:%M:%S')} | {message}")

    def send_raw(self, command):
        record = append_external_message(command, raw=True)
        request_id = short((record or {}).get("request_id", ""), 48)
        self.mark_operator_activity(
            "Queued raw command for Aurora ingestion"
            f" | request {request_id}"
            f" | {short(self.sanitize_operator_activity_command(command), 120)}"
        )
        return record

    def _collect_registered_settings_form_values(self):
        return {
            "auth.mode": self.auth_var.get(),
            "runtime.live": bool(self.live_var.get()),
            "runtime.execution": self.exec_var.get(),
            "runtime.action": self.action_var.get(),
            "game.profile": self.game_profile_var.get(),
            "model.text": self.text_model_var.get(),
            "model.transport": self.model_transport_var.get() or "chat_completions",
            "model.vision": self.vision_model_var.get(),
            "model.reasoning": self.reasoning_model_var.get(),
            "inference.reasoning_effort": self.reasoning_effort_var.get() or "none",
            "inference.verbosity": self.model_verbosity_var.get() or "medium",
            "inference.temperature": self.temperature_var.get(),
            "scheduler.profile": self.turn_scheduler_profile_var.get(),
            "scheduler.mode": self.turn_scheduler_mode_var.get() or "hybrid",
            "scheduler.heartbeat_seconds": self.turn_heartbeat_var.get() or "2.25",
            "scheduler.min_gap_seconds": self.turn_min_gap_var.get() or "0.55",
            "scheduler.capture_wake_enabled": bool(self.turn_capture_wake_var.get()),
            "scheduler.capture_wake_debounce_seconds": self.turn_capture_wake_debounce_var.get() or "0.90",
            "scheduler.post_action_settle_seconds": self.turn_post_action_settle_var.get() or "0.55",
            "capture.screenshot_interval": self.interval_var.get(),
            "capture.demand_enabled": bool(self.demand_capture_var.get()),
            "vision.image_detail": self.image_detail_var.get() or "low",
            "runtime.live_init": bool(self.live_init_var.get()),
        }

    def _build_additional_settings_commands(self):
        return [
            f"SET_BATTLE_REASONING_EFFORT({self.battle_effort_var.get() or 'low'})",
            f"SET_REVIEW_REASONING_EFFORT({self.review_effort_var.get() or 'medium'})",
            f"SET_CRITIQUE_REASONING_EFFORT({self.critique_effort_var.get() or 'high'})",
            f"SET_REVIEW_VERBOSITY({self.review_verbosity_var.get() or 'medium'})",
            f"SET_BATTLE_VERBOSITY({self.battle_verbosity_var.get() or 'low'})",
            f"SET_CRITIQUE_VERBOSITY({self.critique_verbosity_var.get() or 'high'})",
            f"SET_REASONING_SUMMARY_MODE({self.reasoning_summary_var.get() or 'auto'})",
            f"SET_AUTO_DYNAMIC_INFERENCE({'on' if self.auto_dynamic_var.get() else 'off'})",
            f"SET_REVIEW_TURN_INTERVAL({self.review_turn_interval_var.get() or '10'})",
            f"SET_CRITIQUE_TURN_INTERVAL({self.critique_turn_interval_var.get() or '30'})",
            f"SET_PENDING_QUEUE_MODE({self.pending_queue_mode_var.get() or 'normal'})",
            f"SET_COMMAND_DRIP_RETENTION({self.command_drip_retention_var.get() or '5'})",
            f"SET_COMMAND_DRIP_LOOKAHEAD({self.command_drip_lookahead_var.get() or '3'})",
            f"SET_COMMAND_DRIP_SHOW_VARIANTS({'on' if self.command_drip_show_variants_var.get() else 'off'})",
            f"SET_COMMAND_DRIP_SHOW_LIKELY_DROPPED({'on' if self.command_drip_show_likely_dropped_var.get() else 'off'})",
            f"SET_SOUND_EFFECTS({'on' if self.sound_var.get() else 'off'})",
            f"SET_TIME_LOGGING({'on' if self.time_logging_var.get() else 'off'})",
            f"SET_CHAT_LOG_ECHO({'on' if self.chat_log_echo_var.get() else 'off'})",
            f"SET_TILE_GRID({'on' if self.tile_grid_var.get() else 'off'})",
            f"SET_CURSOR_LABEL({'on' if self.cursor_label_var.get() else 'off'})",
            f"SET_KEYPOINT_GRID({'on' if self.keypoint_grid_var.get() else 'off'})",
            f"SET_STATUS_OVERLAY({'on' if self.status_overlay_var.get() else 'off'})",
        ]

    def _build_advanced_context_commands(self):
        commands = [
            f"SET_AUTO_PROMPT({'on' if self.auto_prompt_var.get() else 'off'})",
            f"SET_SHOW_USER_TEXT({'on' if self.show_user_text_var.get() else 'off'})",
            f"SET_SHOW_AI_TEXT({'on' if self.show_ai_text_var.get() else 'off'})",
            f"SET_SHOW_AI_COMMANDS({'on' if self.show_ai_commands_var.get() else 'off'})",
            f"SET_SHOW_USER_COMMANDS({'on' if self.show_user_commands_var.get() else 'off'})",
            f"SET_UNIMPORTANT_MESSAGES({'on' if self.enable_unimportant_messages_var.get() else 'off'})",
            f"SET_IMPORTANT_MESSAGES({'on' if self.enable_important_messages_var.get() else 'off'})",
            f"SET_ADD_UMSGS_TO_HISTORY({'on' if self.add_umsgs_to_history_var.get() else 'off'})",
            f"SET_ADD_IMSGS_TO_HISTORY({'on' if self.add_imsgs_to_history_var.get() else 'off'})",
            f"SET_UMSGS_DECAY_CHECK({'on' if self.check_umsgs_decay_var.get() else 'off'})",
            f"SET_IMSGS_DECAY_CHECK({'on' if self.check_imsgs_decay_var.get() else 'off'})",
        ]
        desired_always = (self.always_mode_var.get() or "off").strip().lower()
        commands.append(
            f"SET_ALWAYS({'on' if desired_always == 'on' else 'off'}, "
            f"{'true' if self.hide_input_pref_var.get() else 'false'})"
        )
        desired_latest_detail = (self.latest_image_detail_var.get() or "").strip().lower()
        if desired_latest_detail in {"low", "high", "auto", "original"}:
            commands.append(f"SET_LATEST_IMAGE_DETAIL({desired_latest_detail})")
        desired_high_detail = (self.high_detail_var.get() or "").strip()
        if desired_high_detail:
            commands.append(f"SET_HIGH_DETAIL({desired_high_detail})")
        desired_max_images = (self.max_images_var.get() or "").strip()
        if desired_max_images:
            commands.append(f"SET_MAX_IMAGES_IN_HISTORY({desired_max_images})")
        return commands

    def _get_control_panel_settings_snapshot(self, require_effective=False):
        status = build_operator_status(ROOT)
        state = read_json(STATE_PATH, {}) if STATE_PATH.exists() else {}
        if not isinstance(state, dict) or not state:
            state = self.state_cache if isinstance(self.state_cache, dict) else {}
        runtime_active = bool((status.get("runtime", {}) or {}).get("running", False))
        snapshot = build_settings_snapshot(
            state,
            runtime_active=runtime_active,
            state_age_seconds=(status.get("state", {}) or {}).get("age_seconds"),
            state_timestamp=str(state.get("timestamp") or ""),
        )
        self.settings_transaction_last_snapshot = snapshot
        if require_effective:
            if not runtime_active:
                raise ValueError("Aurora runtime must be active for settings transactions.")
            non_effective = [
                row.get("key")
                for row in snapshot.get("settings", []) or []
                if row.get("value_status") != "effective"
            ]
            if non_effective:
                raise ValueError(
                    "A fresh effective settings snapshot is required. Unavailable or stale: "
                    + ", ".join(str(key) for key in non_effective[:8])
                )
        return status, snapshot

    def _set_settings_transaction_button_states(self, state=None):
        state = state if isinstance(state, dict) else self.state_cache or {}
        runtime_active = bool(
            ((state.get("processes", {}) or {}).get("runtime", {}) or {}).get("active", False)
        )
        settings_state = state.get("settings", {}) or {}
        available = runtime_active and bool(settings_state.get("version"))
        pending = self.settings_transaction_pending is not None
        for button in (
            self.settings_transaction_preview_button,
            self.settings_transaction_apply_button,
        ):
            if button is not None:
                button.state(["!disabled"] if available and not pending else ["disabled"])
        if self.settings_transaction_rollback_button is not None:
            rollback_available = bool(self.settings_transaction_last_rollback_handle)
            self.settings_transaction_rollback_button.state(
                ["!disabled"] if available and rollback_available and not pending else ["disabled"]
            )

    def _update_settings_transaction_surface(self, state):
        state = state if isinstance(state, dict) else {}
        settings_state = state.get("settings", {}) or {}
        registry = settings_state.get("registry", {}) or {}
        version = str(settings_state.get("version") or "").strip()
        count = int(registry.get("setting_count", 0) or 0)
        rollback_count = int(settings_state.get("rollback_handle_count", 0) or 0)
        self.settings_transaction_version_var.set(
            f"Settings version: {version or 'unavailable'} | registered {count} | rollback handles {rollback_count}"
        )
        if not ((state.get("processes", {}) or {}).get("runtime", {}) or {}).get("active", False):
            self.settings_transaction_last_rollback_handle = ""
        if self.settings_transaction_pending is None and not self.settings_transaction_last_receipt:
            self.settings_transaction_status_var.set(
                "Atomic settings ready." if version else "Atomic settings unavailable until the runtime exports fresh state."
            )
        self._set_settings_transaction_button_states(state)

    def _submit_settings_transaction(
        self,
        operation,
        *,
        changes=None,
        rollback_handle="",
        post_commands=None,
        show_confirmation=False,
        show_result_dialog=False,
        activity_label="registered settings",
        inline_results=False,
    ):
        if self.settings_transaction_pending is not None:
            messagebox.showinfo("Aurora 2", "A settings transaction is already waiting for its receipt.", parent=self)
            return None
        try:
            _status, snapshot = self._get_control_panel_settings_snapshot(require_effective=True)
            expected_version = str(snapshot.get("version") or "").strip()
            candidate_changes = list(changes or [])
            if operation != "rollback" and not candidate_changes:
                candidate_changes = build_control_panel_registered_changes(
                    self._collect_registered_settings_form_values()
                )
            if operation != "rollback":
                candidate_changes = filter_changed_control_panel_settings(candidate_changes, snapshot)
                if not candidate_changes:
                    if operation == "apply" and post_commands:
                        for command in post_commands:
                            self.send_raw(command)
                        self.settings_transaction_status_var.set(
                            f"No registered changes; sent {len(post_commands)} additional independent command(s)."
                        )
                    else:
                        self.settings_transaction_status_var.set("No registered settings differ from current state.")
                    if show_confirmation:
                        messagebox.showinfo("Aurora 2", self.settings_transaction_status_var.get(), parent=self)
                    return None
            if operation == "apply" and show_confirmation:
                preview_lines = [
                    f"{row.get('key')}: {_format_control_panel_setting_value(row.get('value'))}"
                    for row in candidate_changes[:8]
                ]
                if len(candidate_changes) > 8:
                    preview_lines.append(f"...and {len(candidate_changes) - 8} more")
                if not messagebox.askyesno(
                    "Aurora 2",
                    "Apply this atomic runtime-session settings transaction?\n\n"
                    + "\n".join(preview_lines)
                    + f"\n\nExpected version: {expected_version}",
                    parent=self,
                ):
                    return None
            request = build_settings_transaction_request(
                operation,
                changes=candidate_changes if operation != "rollback" else (),
                expected_version=expected_version,
                rollback_handle=rollback_handle,
            )
            offsets = journal_offsets(ROOT)
            record = append_external_message(
                build_settings_transaction_command(request),
                raw=True,
                source="control_panel_settings",
                subject=f"[AURORA CONTROL PANEL SETTINGS {operation.upper()}]",
                metadata={
                    "surface": "control_panel_settings",
                    "settings_transaction_id": request.get("transaction_id"),
                    "settings_operation": operation,
                    "expected_settings_version": expected_version,
                },
            )
        except (SettingsTransactionError, ValueError, OSError) as error:
            self.settings_transaction_status_var.set(f"Settings transaction unavailable: {error}")
            messagebox.showerror("Aurora 2", str(error), parent=self)
            return None

        request_id = str((record or {}).get("request_id") or "").strip()
        self.settings_transaction_pending = {
            "request_id": request_id,
            "operation": operation,
            "request": request,
            "post_commands": list(post_commands or []),
            "show_confirmation": bool(show_confirmation),
            "show_result_dialog": bool(show_result_dialog),
            "inline_results": bool(inline_results),
            "activity_label": activity_label,
        }
        self.settings_transaction_status_var.set(
            f"Waiting for {operation} receipt | request {short(request_id, 42)} | expected {expected_version}"
        )
        self.mark_operator_activity(
            f"Queued atomic settings {operation} | request {short(request_id, 48)} | changes {len(candidate_changes)}"
        )
        self._set_settings_transaction_button_states(self.state_cache)
        threading.Thread(
            target=self._wait_for_settings_transaction_receipt,
            args=(request_id, offsets, record["client_id"]),
            name=f"aurora-settings-{operation}",
            daemon=True,
        ).start()
        return record

    def _wait_for_settings_transaction_receipt(self, request_id, offsets, client_id):
        try:
            receipt = wait_for_command_receipt(
                ROOT,
                request_id,
                client_id=client_id,
                offsets=offsets,
                timeout_seconds=20.0,
                poll_interval_seconds=0.10,
            )
            self.settings_transaction_result_queue.put(
                {"request_id": request_id, "receipt": receipt, "error": ""}
            )
        except Exception as error:
            self.settings_transaction_result_queue.put(
                {"request_id": request_id, "receipt": {}, "error": str(error)}
            )

    def _drain_settings_transaction_results(self):
        while True:
            try:
                result = self.settings_transaction_result_queue.get_nowait()
            except queue.Empty:
                return
            self._handle_settings_transaction_result(result)

    def _handle_settings_transaction_result(self, result):
        pending = self.settings_transaction_pending or {}
        request_id = str(result.get("request_id") or "")
        if pending and request_id != pending.get("request_id"):
            return
        self.settings_transaction_pending = None
        error = str(result.get("error") or "").strip()
        outer_receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
        transaction = extract_settings_transaction_receipt(outer_receipt)
        if error:
            self.settings_transaction_status_var.set(f"Settings receipt wait failed: {error}")
            self.mark_operator_activity(f"Settings receipt wait failed | request {short(request_id, 48)}")
            self._set_settings_transaction_button_states(self.state_cache)
            return
        if transaction is None:
            outer_status = str(outer_receipt.get("status") or outer_receipt.get("outcome_status") or "unknown")
            reason = str(outer_receipt.get("reason") or "No nested settings receipt was returned.")
            self.settings_transaction_status_var.set(
                f"Settings outcome {outer_status}; do not replay automatically. {reason}"
            )
            self.mark_operator_activity(
                f"Settings outcome {outer_status} | request {short(request_id, 48)} | inspect before retry"
            )
            self._set_settings_transaction_button_states(self.state_cache)
            return

        self.settings_transaction_last_receipt = dict(transaction)
        status = str(transaction.get("status") or "unknown")
        operation = str(transaction.get("operation") or pending.get("operation") or "settings")
        activity_label = str(pending.get("activity_label") or "registered settings")
        follow_up_count = 0
        rollback = transaction.get("rollback_handle") or {}
        if operation == "apply" and status in {"applied", "applied_noop"}:
            self.settings_transaction_last_rollback_handle = str(rollback.get("handle_id") or "")
            for command in pending.get("post_commands", []) or []:
                self.send_raw(command)
                follow_up_count += 1
        elif operation == "rollback" and status == "rolled_back":
            self.settings_transaction_last_rollback_handle = ""

        changed_count = sum(1 for row in transaction.get("changes", []) or [] if row.get("changed"))
        rejection_codes = [
            str(row.get("code") or "error")
            for row in transaction.get("rejections", []) or []
            if isinstance(row, dict)
        ]
        suffix = f" | rejected {', '.join(rejection_codes)}" if rejection_codes else ""
        if follow_up_count:
            suffix += f" | follow-up independent commands queued {follow_up_count}"
        self.settings_transaction_status_var.set(
            f"Atomic {activity_label} {operation}: {status} | changes {changed_count} | "
            f"version {transaction.get('before_version') or '-'} -> {transaction.get('after_version') or '-'}{suffix}"
        )
        self.mark_operator_activity(
            f"Atomic {activity_label} {operation} {status} | request {short(request_id, 48)} | "
            f"changes {changed_count} | follow-up commands {follow_up_count}"
        )
        if "version_conflict" in rejection_codes:
            self.last_state_mtime = 0.0
            self.after(50, self.refresh_now)
        elif status in CONTROL_PANEL_SETTINGS_SUCCESS_STATUSES:
            self.last_state_mtime = 0.0
            self.after(250, self.refresh_now)
            self.after(900, self.refresh_now)

        if (pending.get("show_result_dialog") or operation == "preview") and not pending.get("inline_results"):
            self._open_settings_text_dialog("Aurora Settings Transaction", format_control_panel_settings_receipt(transaction))
        elif pending.get("show_confirmation"):
            if status in CONTROL_PANEL_SETTINGS_SUCCESS_STATUSES:
                messagebox.showinfo("Aurora 2", self.settings_transaction_status_var.get(), parent=self)
            else:
                messagebox.showerror(
                    "Aurora 2",
                    self.settings_transaction_status_var.get() + "\n\n" + format_control_panel_settings_receipt(transaction),
                    parent=self,
                )
        self._set_settings_transaction_button_states(self.state_cache)

    def _open_settings_text_dialog(self, title, text, *, font=None, height=640):
        if self.settings_transaction_dialog is not None and self.settings_transaction_dialog.winfo_exists():
            self.settings_transaction_dialog.destroy()
        window = tk.Toplevel(self)
        self.settings_transaction_dialog = window
        window.title(title)
        geometry = fit_popout_window(window, 920, height, self)
        window.minsize(min(680, geometry["width"]), min(420, geometry["height"]))
        window.configure(bg=BG)
        ttk.Button(window, text="Close (Esc)", command=window.destroy).pack(side="bottom", anchor="e", padx=12, pady=(0, 10))
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        text_widget = tk.Text(body, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        if font is not None:
            text_widget.configure(font=font)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._write_text(text_widget, text)
        window.bind("<Escape>", lambda _event: window.destroy())

    def show_settings_details(self):
        try:
            _status, snapshot = self._get_control_panel_settings_snapshot(require_effective=False)
        except Exception as error:
            messagebox.showerror("Aurora 2", str(error), parent=self)
            return
        self._open_settings_text_dialog(
            "Aurora Settings Details",
            format_control_panel_settings_snapshot(snapshot),
        )

    def preview_settings(self):
        return self._submit_settings_transaction(
            "preview",
            show_result_dialog=True,
            activity_label="registered settings preview",
        )

    def rollback_settings(self):
        handle = str(self.settings_transaction_last_rollback_handle or "").strip()
        if not handle:
            messagebox.showinfo("Aurora 2", "No available Control Panel rollback handle is recorded.", parent=self)
            return None
        if not messagebox.askyesno(
            "Aurora 2",
            f"Rollback the last atomic Control Panel settings apply?\n\nHandle: {handle}",
            parent=self,
        ):
            return None
        return self._submit_settings_transaction(
            "rollback",
            rollback_handle=handle,
            show_confirmation=True,
            activity_label="registered settings rollback",
        )

    def insert_latest_agent_pending_dry_run(self):
        self.refresh_now()
        dry_run = (self.state_cache or {}).get("agent_pending_insert_dry_run", {}) or {}
        rows = [row for row in (dry_run.get("rows", []) or []) if isinstance(row, dict)]
        ready_rows = [
            row for row in rows
            if row.get("contract_ready") and row.get("would_insert") and not row.get("pending_command_inserted")
        ]
        if not ready_rows:
            messagebox.showinfo(
                "Aurora 2",
                "No exact-confirm Pending insert row is ready. Run Dry Run Insert after approving, staging, marking provenance, and linking a reviewed task.",
                parent=self,
            )
            return
        row = ready_rows[-1]
        dry_run_id = str(row.get("dry_run_id", "") or "").strip()
        review_id = str(row.get("review_link_id", "") or "").strip()
        command_text = str(row.get("command", "") or "").strip()
        if not dry_run_id or not review_id:
            messagebox.showinfo("Aurora 2", "The ready dry-run row is missing its review or dry-run id.", parent=self)
            return
        raw_command = (
            f'INSERT_AGENT_PENDING_COMMAND({review_id}, confirm=dry_run:{dry_run_id}, '
            'note="Control Panel exact confirmed insert")'
        )
        if messagebox.askyesno(
            "Aurora 2",
            "Insert this sub-agent suggestion into the held Pending queue?\n\n"
            f"{short(command_text, 220)}\n\n"
            "It will still require APPROVE_PENDING before execution.",
            parent=self,
        ):
            self.send_raw(raw_command)

    def search_image_context_index(self):
        query = (self.image_index_search_var.get() or "").strip()
        if not query:
            self.mark_operator_activity("Image Index search skipped | empty query")
            return
        self.send_raw(f"SEARCH_IMAGE_CONTEXT_INDEX({json.dumps(query)}, 12)")

    def confirm_and_send_raw(self, command, prompt):
        if messagebox.askyesno("Aurora 2", prompt):
            self.send_raw(command)

    def _draw_chat_head_toggle_button(self, pressed, canvas=None):
        canvas = canvas if canvas is not None else self.chat_head_toggle_canvas
        if canvas is None:
            return
        canvas.delete("all")
        fill = CHAT_HEAD_TOGGLE_FILL_ACTIVE if pressed else CHAT_HEAD_TOGGLE_FILL
        border = CHAT_HEAD_HISTORY_ACCENT if pressed else CHAT_HEAD_BORDER
        bubble_fill = "#0b1120" if pressed else PANEL_2
        line_fill = CHAT_HEAD_HISTORY_ACCENT if pressed else MUTED
        canvas.create_rectangle(4, 4, 64, 30, fill=fill, outline=border, width=2)
        canvas.create_rectangle(13, 10, 39, 23, fill=bubble_fill, outline=line_fill, width=2)
        canvas.create_polygon(21, 23, 26, 28, 31, 23, fill=bubble_fill, outline=line_fill, width=2)
        canvas.create_line(18, 15, 34, 15, fill=line_fill, width=2)
        canvas.create_line(18, 19, 30, 19, fill=line_fill, width=2)
        canvas.create_polygon(
            46,
            10,
            58,
            17,
            46,
            24,
            fill=CHAT_HEAD_HISTORY_ACCENT if pressed else ACCENT,
            outline=border,
            width=1,
        )

    def _set_panel_chat_head_requested(self, enabled):
        enabled = bool(enabled)
        self.chat_head_requested_open = enabled
        if not isinstance(self.state_cache, dict):
            self.state_cache = {}
        panel_state = self.state_cache.setdefault("panel", {})
        if isinstance(panel_state, dict):
            panel_state["chat_head_open"] = enabled
        self._draw_chat_head_toggle_button(enabled)

    def _is_chat_head_strip_open(self):
        return self.chat_head_strip_window is not None and self.chat_head_strip_window.winfo_exists()

    def _is_chat_head_history_open(self):
        return self.chat_head_history_window is not None and self.chat_head_history_window.winfo_exists()

    def toggle_chat_head_request(self, _event=None):
        desired_open = not bool(self.chat_head_requested_open or self._is_chat_head_strip_open())
        self._set_panel_chat_head_requested(desired_open)
        if desired_open:
            self.open_chat_head_strip()
            self.send_raw("OPEN_CHAT_HEAD()")
        else:
            self.close_chat_head_windows(local_only=True)
            self.send_raw("CLOSE_CHAT_HEAD()")

    def request_close_chat_head(self, _event=None):
        self._set_panel_chat_head_requested(False)
        self.close_chat_head_windows(local_only=True)
        self.send_raw("CLOSE_CHAT_HEAD()")

    def sync_chat_head_visibility(self):
        panel_state = (self.state_cache or {}).get("panel", {}) or {}
        requested_open = bool(panel_state.get("chat_head_open", False))
        self._set_panel_chat_head_requested(requested_open)
        if requested_open:
            self.open_chat_head_strip()
            self.apply_chat_head_window_settings()
            self.refresh_chat_head_content()
        else:
            self.close_chat_head_windows(local_only=True)

    def get_panel_chat_head_settings(self):
        panel_state = (self.state_cache or {}).get("panel", {}) or {}
        scale = ui_scale(self)
        return {
            "opacity": float(panel_state.get("chat_head_opacity", 0.87) or 0.87),
            "topmost": bool(panel_state.get("chat_head_topmost", True)),
            "strip_width": round(int(panel_state.get("chat_head_strip_width", 1000) or 1000) * scale),
            "strip_height": round(int(panel_state.get("chat_head_strip_height", 100) or 100) * scale),
            "history_width": round(int(panel_state.get("chat_head_history_width", 420) or 420) * scale),
            "history_height": round(int(panel_state.get("chat_head_history_height", 620) or 620) * scale),
            "send_animation": str(panel_state.get("chat_head_send_animation", "pulse") or "pulse"),
            "send_animation_seconds": float(panel_state.get("chat_head_send_animation_seconds", 0.75) or 0.75),
        }

    def _build_chat_head_history_text(self, state):
        rows = list(state.get("chat_history_tail", []) or [])
        if not rows:
            return "No recent chat history available."
        blocks = []
        for row in rows[-20:]:
            role = str(row.get("role", "") or "system").strip().title() or "System"
            text = str(row.get("text", "") or row.get("summary", "") or "").strip()
            if not text:
                continue
            blocks.append(f"{role}: {text}")
        return "\n\n".join(blocks) if blocks else "No recent chat history available."

    def _draw_chat_head_expand_button(self):
        if self.chat_head_expand_canvas is None:
            return
        canvas = self.chat_head_expand_canvas
        expanded = self._is_chat_head_history_open()
        canvas.delete("all")
        fill = "#132039" if expanded else "#0b1120"
        canvas.create_rectangle(2, 2, 82, 82, fill=fill, outline=CHAT_HEAD_BORDER, width=2)
        canvas.create_line(16, 12, 16, 72, fill=CHAT_HEAD_BORDER, width=2)
        canvas.create_polygon(
            32,
            18,
            66,
            42,
            32,
            66,
            fill=CHAT_HEAD_HISTORY_ACCENT if expanded else ACCENT,
            outline=CHAT_HEAD_BORDER,
            width=2,
        )
        canvas.scale("all", 0, 0, ui_scale(self), ui_scale(self))

    @staticmethod
    def _blend_chat_head_color(start_hex, end_hex, mix):
        mix = min(1.0, max(0.0, float(mix)))
        start_hex = (start_hex or "#000000").lstrip("#")
        end_hex = (end_hex or "#000000").lstrip("#")
        start_rgb = tuple(int(start_hex[index:index + 2], 16) for index in (0, 2, 4))
        end_rgb = tuple(int(end_hex[index:index + 2], 16) for index in (0, 2, 4))
        blended = tuple(int(round(start + (end - start) * mix)) for start, end in zip(start_rgb, end_rgb))
        return "#{:02x}{:02x}{:02x}".format(*blended)

    def _restore_chat_head_strip_visual(self):
        if self.chat_head_strip_text is None:
            return
        try:
            self.chat_head_strip_text.configure(
                bg=CHAT_HEAD_FIELD,
                fg=CHAT_HEAD_TEXT,
                insertbackground=CHAT_HEAD_TEXT,
            )
        except Exception:
            pass

    def _run_chat_head_send_animation_step(self, start_time, duration_seconds):
        if self.chat_head_strip_text is None or not self._is_chat_head_strip_open():
            self.chat_head_send_animation_after = None
            self.chat_head_send_animation_active = False
            self.chat_head_send_animation_pending = False
            return
        elapsed = time.time() - start_time
        progress = min(1.0, elapsed / max(0.1, duration_seconds))
        midpoint_mix = 1.0 - abs((progress * 2.0) - 1.0)
        bg_color = self._blend_chat_head_color(CHAT_HEAD_FIELD, CHAT_HEAD_FIELD_SENT, midpoint_mix)
        fg_color = self._blend_chat_head_color(CHAT_HEAD_TEXT, "#fbfbfa", midpoint_mix)
        try:
            self.chat_head_strip_text.configure(bg=bg_color, fg=fg_color, insertbackground=fg_color)
        except Exception:
            pass
        if progress >= 1.0:
            self.chat_head_send_animation_after = None
            self.chat_head_send_animation_active = False
            self._restore_chat_head_strip_visual()
            if self.chat_head_send_animation_pending:
                self.chat_head_send_animation_pending = False
                self.start_chat_head_send_animation()
            return
        self.chat_head_send_animation_after = self.after(
            28,
            lambda: self._run_chat_head_send_animation_step(start_time, duration_seconds),
        )

    def start_chat_head_send_animation(self):
        settings = self.get_panel_chat_head_settings()
        mode = str(settings.get("send_animation", "pulse") or "pulse").strip().lower()
        duration_seconds = max(0.1, float(settings.get("send_animation_seconds", 0.75) or 0.75))
        if mode == "none" or self.chat_head_strip_text is None or not self._is_chat_head_strip_open():
            self._restore_chat_head_strip_visual()
            return
        if self.chat_head_send_animation_active:
            self.chat_head_send_animation_pending = True
            return
        if self.chat_head_send_animation_after is not None:
            try:
                self.after_cancel(self.chat_head_send_animation_after)
            except Exception:
                pass
            self.chat_head_send_animation_after = None
        self.chat_head_send_animation_active = True
        self.chat_head_send_animation_pending = False
        self._run_chat_head_send_animation_step(time.time(), duration_seconds)

    def submit_chat_head_message(self, _event=None):
        if self.chat_head_strip_text is None:
            return "break"
        text = self.chat_head_strip_text.get("1.0", tk.END).strip()
        if not text:
            return "break"
        record = append_external_message(
            text,
            raw=False,
            source="chat_head",
            subject="[AURORA CHAT STRIP]",
            metadata={"surface": "chat_head"},
        )
        self.chat_head_strip_text.delete("1.0", tk.END)
        self.mark_operator_activity(
            f"Queued chat strip note | id {short((record or {}).get('message_id', ''), 48)} | {short(text, 120)}"
        )
        self.start_chat_head_send_animation()
        return "break"

    def _position_chat_head_strip(self):
        if not self._is_chat_head_strip_open():
            return
        window = self.chat_head_strip_window
        settings = self.get_panel_chat_head_settings()
        width = settings["strip_width"]
        height = settings["strip_height"]
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(24, int((screen_width - width) / 2))
        y = max(24, screen_height - height - 120)
        fit_popout_window(window, width, height, self, position=(x, y), minimum=(520, 74))

    def apply_chat_head_window_settings(self):
        settings = self.get_panel_chat_head_settings()
        strip_signature = (
            settings["opacity"],
            settings["topmost"],
            settings["strip_width"],
            settings["strip_height"],
        )
        history_signature = (
            settings["opacity"],
            settings["topmost"],
            settings["history_width"],
            settings["history_height"],
        )
        if self._is_chat_head_strip_open():
            try:
                self.chat_head_strip_window.attributes("-topmost", settings["topmost"])
            except Exception:
                pass
            try:
                self.chat_head_strip_window.attributes("-alpha", settings["opacity"])
            except Exception:
                pass
            if self.chat_head_window_signature != strip_signature:
                self._position_chat_head_strip()
                self.chat_head_window_signature = strip_signature
        if self._is_chat_head_history_open():
            try:
                self.chat_head_history_window.attributes("-topmost", settings["topmost"])
            except Exception:
                pass
            try:
                self.chat_head_history_window.attributes("-alpha", settings["opacity"])
            except Exception:
                pass
            if self.chat_head_history_signature != history_signature:
                fit_popout_window(self.chat_head_history_window, settings['history_width'], settings['history_height'], self.chat_head_strip_window)
                self.chat_head_history_signature = history_signature
            self.reposition_chat_head_history_window()

    def open_chat_head_strip(self):
        if self._is_chat_head_strip_open():
            self.apply_chat_head_window_settings()
            self.refresh_chat_head_content()
            return
        settings = self.get_panel_chat_head_settings()
        self.chat_head_strip_window = tk.Toplevel(self)
        window = self.chat_head_strip_window
        window.title("Aurora Chat Strip")
        window.configure(bg=CHAT_HEAD_BG)
        window.resizable(True, True)
        scale = ui_scale(self)
        window.minsize(min(round(520 * scale), self.winfo_screenwidth()-32), round(90 * scale))
        try:
            window.attributes("-topmost", settings["topmost"])
        except Exception:
            pass
        try:
            window.attributes("-alpha", settings["opacity"])
        except Exception:
            pass
        window.protocol("WM_DELETE_WINDOW", self.request_close_chat_head)
        shell = tk.Frame(window, bg=CHAT_HEAD_BG, highlightbackground=CHAT_HEAD_BORDER, highlightthickness=2, bd=0)
        shell.pack(fill="both", expand=True)
        text_shell = tk.Frame(shell, bg=CHAT_HEAD_BG)
        text_shell.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=10)
        tk.Label(
            text_shell,
            textvariable=self.chat_head_strip_status_var,
            bg=CHAT_HEAD_BG,
            fg=CHAT_HEAD_MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(0, 4))
        self.chat_head_strip_text = tk.Text(
            text_shell,
            height=2,
            bg=CHAT_HEAD_FIELD,
            fg=CHAT_HEAD_TEXT,
            insertbackground=CHAT_HEAD_TEXT,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 14),
            highlightthickness=1,
            highlightbackground=CHAT_HEAD_BORDER,
            highlightcolor=CHAT_HEAD_HISTORY_ACCENT,
            bd=0,
        )
        self.chat_head_strip_text.pack(fill="both", expand=True)
        self.chat_head_strip_text.bind("<Return>", self.submit_chat_head_message)
        self.chat_head_strip_text.bind("<KP_Enter>", self.submit_chat_head_message)
        expand_shell = tk.Frame(shell, bg=CHAT_HEAD_BG, width=round(88 * scale))
        expand_shell.pack(side="right", fill="y", padx=(8, 10), pady=10)
        expand_shell.pack_propagate(False)
        self.chat_head_expand_canvas = tk.Canvas(
            expand_shell,
            width=round(84 * scale),
            height=round(84 * scale),
            bg=CHAT_HEAD_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.chat_head_expand_canvas.pack(fill="both", expand=True)
        self.chat_head_expand_canvas.bind("<Button-1>", self.toggle_chat_head_history)
        close_canvas = tk.Canvas(window, width=round(24 * scale), height=round(24 * scale), bg=CHAT_HEAD_BG, highlightthickness=0, bd=0, cursor="hand2")
        close_canvas.place(relx=1.0, x=-8, y=6, anchor="ne")
        close_canvas.create_oval(2, 2, 22, 22, fill=CHAT_HEAD_CLOSE, outline="#7f1d1d", width=2)
        close_canvas.create_line(8, 8, 16, 16, fill="#fee2e2", width=2)
        close_canvas.create_line(16, 8, 8, 16, fill="#fee2e2", width=2)
        close_canvas.scale("all", 0, 0, scale, scale)
        close_canvas.bind("<Button-1>", self.request_close_chat_head)
        window.bind("<Configure>", self.reposition_chat_head_history_window)
        self.chat_head_window_signature = (
            settings["opacity"],
            settings["topmost"],
            settings["strip_width"],
            settings["strip_height"],
        )
        self._position_chat_head_strip()
        self._restore_chat_head_strip_visual()
        self.refresh_chat_head_content()
        try:
            self.chat_head_strip_text.focus_set()
        except Exception:
            pass

    def open_chat_head_history(self):
        if not self._is_chat_head_strip_open():
            self.open_chat_head_strip()
        if self._is_chat_head_history_open():
            self.apply_chat_head_window_settings()
            self.refresh_chat_head_content()
            return
        settings = self.get_panel_chat_head_settings()
        self.chat_head_history_window = tk.Toplevel(self)
        window = self.chat_head_history_window
        window.title("Aurora Chat History")
        window.configure(bg=CHAT_HEAD_BG)
        window.resizable(True, True)
        scale = ui_scale(self)
        window.minsize(min(round(320 * scale), self.winfo_screenwidth()-32), min(round(320 * scale), self.winfo_screenheight()-64))
        try:
            window.attributes("-topmost", settings["topmost"])
        except Exception:
            pass
        try:
            window.attributes("-alpha", settings["opacity"])
        except Exception:
            pass
        window.protocol("WM_DELETE_WINDOW", self.close_chat_head_history)
        shell = tk.Frame(window, bg=CHAT_HEAD_BG, highlightbackground=CHAT_HEAD_BORDER, highlightthickness=2, bd=0)
        shell.pack(fill="both", expand=True)
        left_bar = tk.Frame(shell, bg=CHAT_HEAD_BG, width=round(44 * scale))
        left_bar.pack(side="left", fill="y", padx=(6, 0), pady=6)
        left_bar.pack_propagate(False)
        collapse = tk.Canvas(left_bar, width=round(28 * scale), height=round(60 * scale), bg=CHAT_HEAD_BG, highlightthickness=0, bd=0, cursor="hand2")
        collapse.pack(anchor="n", pady=(8, 0))
        collapse.create_rectangle(2, 2, 26, 58, fill="#0b1120", outline=CHAT_HEAD_BORDER, width=2)
        collapse.create_polygon(22, 10, 8, 30, 22, 50, fill=CHAT_HEAD_HISTORY_ACCENT, outline=CHAT_HEAD_BORDER, width=1)
        collapse.scale("all", 0, 0, scale, scale)
        collapse.bind("<Button-1>", self.close_chat_head_history)
        text_shell = tk.Frame(shell, bg=CHAT_HEAD_BG)
        text_shell.pack(side="left", fill="both", expand=True, padx=(6, 10), pady=10)
        tk.Label(
            text_shell,
            textvariable=self.chat_head_history_status_var,
            bg=CHAT_HEAD_BG,
            fg=CHAT_HEAD_MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(0, 4))
        history_scroll = ttk.Scrollbar(text_shell, orient="vertical")
        history_scroll.pack(side="right", fill="y")
        self.chat_head_history_text = tk.Text(
            text_shell,
            bg=CHAT_HEAD_FIELD,
            fg=CHAT_HEAD_TEXT,
            insertbackground=CHAT_HEAD_TEXT,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 14),
            highlightthickness=1,
            highlightbackground=CHAT_HEAD_BORDER,
            highlightcolor=CHAT_HEAD_HISTORY_ACCENT,
            bd=0,
            yscrollcommand=history_scroll.set,
        )
        self.chat_head_history_text.pack(side="left", fill="both", expand=True)
        history_scroll.configure(command=self.chat_head_history_text.yview)
        self.chat_head_history_signature = (
            settings["opacity"],
            settings["topmost"],
            settings["history_width"],
            settings["history_height"],
        )
        self.reposition_chat_head_history_window()
        self.refresh_chat_head_content()

    def toggle_chat_head_history(self, _event=None):
        if self._is_chat_head_history_open():
            self.close_chat_head_history()
        else:
            self.open_chat_head_history()

    def close_chat_head_history(self, _event=None):
        if self._is_chat_head_history_open():
            self.chat_head_history_window.destroy()
        self.chat_head_history_window = None
        self.chat_head_history_text = None
        self.chat_head_history_signature = None
        self._draw_chat_head_expand_button()

    def close_chat_head_windows(self, local_only=False):
        self.close_chat_head_history()
        if self.chat_head_send_animation_after is not None:
            try:
                self.after_cancel(self.chat_head_send_animation_after)
            except Exception:
                pass
        self.chat_head_send_animation_after = None
        self.chat_head_send_animation_active = False
        self.chat_head_send_animation_pending = False
        if self._is_chat_head_strip_open():
            self.chat_head_strip_window.destroy()
        self.chat_head_strip_window = None
        self.chat_head_strip_text = None
        self.chat_head_expand_canvas = None
        self.chat_head_window_signature = None
        if not local_only:
            self._set_panel_chat_head_requested(False)
        self.chat_head_strip_status_var.set("Strip closed | History closed | Recent messages 0 | Enter sends")
        self.chat_head_history_status_var.set("No recent chat history loaded.")
        self.chat_head_status_var.set(
            f"Strip closed | History closed | Topmost {'on' if self.chat_head_topmost_var.get() else 'off'} | "
            f"Opacity {(self.chat_head_opacity_var.get() or '0.87').strip() or '0.87'}"
        )

    def reposition_chat_head_history_window(self, _event=None):
        if not self._is_chat_head_strip_open() or not self._is_chat_head_history_open():
            self._draw_chat_head_expand_button()
            return
        settings = self.get_panel_chat_head_settings()
        self.chat_head_strip_window.update_idletasks()
        strip_x = self.chat_head_strip_window.winfo_x()
        strip_y = self.chat_head_strip_window.winfo_y()
        strip_width = self.chat_head_strip_window.winfo_width()
        history_width = settings["history_width"]
        history_height = settings["history_height"]
        x = strip_x + strip_width - 6
        y = max(24, strip_y - 20)
        fit_popout_window(self.chat_head_history_window, history_width, history_height,
                          self.chat_head_strip_window, position=(x, y))
        self._draw_chat_head_expand_button()

    def refresh_chat_head_content(self):
        state = self.state_cache or {}
        rows = list(state.get("chat_history_tail", []) or [])
        strip_state = "open" if self._is_chat_head_strip_open() else "closed"
        history_state = "open" if self._is_chat_head_history_open() else "closed"
        self.chat_head_strip_status_var.set(
            f"Strip {strip_state} | History {history_state} | Recent messages {len(rows)} | Enter sends"
        )
        self.chat_head_history_status_var.set(
            f"Recent chat history | Showing {min(len(rows), 20)} of {len(rows)} cached messages"
        )
        self.chat_head_status_var.set(
            f"Strip {strip_state} | History {history_state} | "
            f"Topmost {'on' if self.chat_head_topmost_var.get() else 'off'} | "
            f"Opacity {(self.chat_head_opacity_var.get() or '0.87').strip() or '0.87'}"
        )
        if self.chat_head_history_text is not None:
            self._write_text(self.chat_head_history_text, self._build_chat_head_history_text(state))
        self._draw_chat_head_expand_button()

    def send_command_entry(self, _event=None):
        value = self.command_var.get().strip()
        if value:
            self.send_raw(value)
            self.command_var.set("")
        return "break"

    def send_note_entry(self, _event=None):
        value = self.note_var.get().strip()
        if value:
            record = append_external_message(value, raw=False)
            self.mark_operator_activity(
                f"Queued note | id {short((record or {}).get('message_id', ''), 48)} | {short(value, 120)}"
            )
            self.note_var.set("")
        return "break"

    def _build_episodic_memory_commands(self):
        return [
            f"SET_EPISODIC_MEMORY({'on' if self.episodic_enabled_var.get() else 'off'})",
            f"SET_EPISODIC_MEMORY_INTERVAL({(self.episodic_interval_var.get() or '900').strip()})",
            f"SET_EPISODIC_MEMORY_PERIODIC({'on' if self.episodic_periodic_var.get() else 'off'})",
            f"SET_EPISODIC_MEMORY_SCENE_TRIGGER({'on' if self.episodic_scene_var.get() else 'off'})",
            f"SET_EPISODIC_EMBEDDINGS({(self.episodic_backend_var.get() or 'auto').strip() or 'auto'})",
            f"SET_EPISODIC_PLANNING_ASSIST({(self.episodic_planning_mode_var.get() or 'review_critique').strip() or 'review_critique'})",
            f"SET_EPISODIC_PLANNING_ASSIST_K({(self.episodic_planning_k_var.get() or '2').strip() or '2'})",
            f"SET_EPISODIC_PLANNING_ASSIST_COOLDOWN({(self.episodic_planning_cooldown_var.get() or '12').strip() or '12'})",
            f"SET_EPISODIC_EMBEDDING_MODEL({json.dumps((self.episodic_embedding_model_var.get() or 'text-embedding-3-small').strip() or 'text-embedding-3-small')})",
        ]

    def apply_episodic_memory_settings(self, show_confirmation=False):
        commands = self._build_episodic_memory_commands()
        for command in commands:
            self.send_raw(command)
        self.mark_operator_activity(f"Sent episodic memory settings batch ({len(commands)} commands).")
        self.episodic_control_status_var.set("Episodic settings sent; waiting for Aurora state refresh.")
        self.episodic_tab_planning_status_var.set("Episodic settings sent; planning-assist status will refresh from runtime state.")
        self.after(500, self.refresh_now)
        if show_confirmation:
            messagebox.showinfo("Aurora 2", "Episodic memory settings sent to Aurora.")

    def send_episodic_snapshot(self, _event=None):
        reason = (self.episodic_snapshot_reason_var.get() or "").strip() or "manual snapshot"
        tags = (self.episodic_snapshot_tags_var.get() or "").strip()
        command = f"WRITE_EPISODIC_SNAPSHOT({json.dumps(reason)}"
        if tags:
            command += f", {json.dumps(tags)}"
        command += ")"
        self.send_raw(command)
        self.episodic_retrieval_status_var.set("Manual snapshot requested; recent store will refresh shortly.")
        self.after(500, self.refresh_now)
        return "break"

    def send_episodic_list_recent(self):
        limit = (self.episodic_recent_limit_var.get() or "8").strip() or "8"
        self.send_raw(f"LIST_EPISODIC_SNAPSHOTS({limit})")
        self.episodic_retrieval_status_var.set(f"Requested recent snapshot list with limit {limit}.")
        self.after(500, self.refresh_now)

    def _build_episodic_search_filters(self, parent):
        section = CollapsibleSection(parent, "Search filters • applied before semantic scoring", expanded=True)
        section.pack(fill="x", pady=(0, 8))
        body = section.body
        body.columnconfigure(1, weight=1)
        labels = {"text_filter": "Required text / Boolean expression", "text_mode": "Match mode",
                  "text_field": "Search field", "date_start": "Start date (inclusive)",
                  "date_end": "End date (whole day; time is exclusive)", "timezone": "Timezone",
                  "after": "After (exclude instant / entire day)", "before": "Before (exclude instant / start of day)",
                  "date_period": "Relative period (none keeps explicit dates)", "date_anchor": "Fixed period anchor (ISO date/time; blank = now)",
                  "result_mode": "Retain full results (legacy = preview only)",
                  "argument_policy": "Argument validation (legacy coercion / strict)",
                  "sort": "Sort results", "offset": "Skip results (page offset)",
                  "value_encoding": "Command string encoding", "feedback_mode": "Unhelpful results: off / skip / penalize",
                  "feedback_factor": "Score multiplier per rejection (0–1)", "feedback_session": "Feedback session",
                  "feedback_action": "Feedback action for next search", "feedback_token": "Last result token (reject_last)"}
        feedback_section = CollapsibleSection(parent, "Advanced repeat-search feedback", expanded=False)
        feedback_section.pack(fill="x", pady=(0, 8))
        feedback_section.body.columnconfigure(1, weight=1)
        for row, key in enumerate(SEARCH_DEFAULTS):
            target = feedback_section.body if key.startswith("feedback_") else body
            ttk.Label(target, text=labels[key]).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            variable = self.episodic_search_vars[key]
            if key in SEARCH_CHOICES:
                widget = ttk.Combobox(target, textvariable=variable, values=SEARCH_CHOICES[key], state="readonly", width=25)
            else:
                widget = ttk.Entry(target, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
        feedback_buttons = ttk.Frame(feedback_section.body)
        feedback_buttons.grid(row=len(SEARCH_DEFAULTS)+1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(feedback_buttons, text="Batch unhelpful → search next", command=lambda: self.send_episodic_feedback("reject_last")).pack(side="left")
        ttk.Button(feedback_buttons, text="Reset feedback & search", command=lambda: self.send_episodic_feedback("reset")).pack(side="left", padx=8)
        ttk.Label(feedback_section.body, text="First search with skip/penalize enabled. If its batch was unhelpful, select reject_last and search again. The returned token guards the exact batch. Reset clears this query/session's marks. Off restores ordinary searches. Feedback lives only until runtime restart or bounded eviction. Penalties change ranking scores, not sampling probabilities.", wraplength=1000).grid(row=len(SEARCH_DEFAULTS), column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(body, text='Semantic query above is optional when filters are set. Boolean example: (rocket OR "secret key") AND NOT failed. '
                  'Wildcards * / ? match one whitespace-delimited token; backslash escapes them. '
                  'Dates: YYYY-MM-DD or ISO date/time. UTC, ±HH:MM and available IANA zones are supported. '
                  'After excludes an instant or a whole date; Before excludes the start of that date. '
                  'Relative periods replace explicit bounds; weeks start Monday. Current periods end at the anchor. '
                  'Freeze date_anchor for relative paging/feedback; the resolved UTC anchor appears in results. '
                  'Relevance/newest/oldest bypass curve and jitter and allow paging; Legacy preserves both. '
                  'Person/conversation search awaits the message index.', wraplength=1000, justify="left").grid(
                      row=len(SEARCH_DEFAULTS), column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_episodic_visual_search(self, parent):
        workbench = ttk.LabelFrame(parent, text="Visual retrieval workbench • this query")
        workbench.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(workbench)
        toolbar.pack(fill="x", padx=10, pady=8)
        ttk.Label(toolbar, text="Scorer").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.episodic_score_mode_var, values=["legacy", "weighted"], state="readonly", width=10).pack(side="left", padx=(6, 12))
        for label, key in (("Description only", "description_weight"), ("Keywords only", "keyword_weight"),
                           ("Time only", "recency_weight"), ("Ratings only", "rating_weight"), ("Balanced", None)):
            ttk.Button(toolbar, text=label, command=lambda chosen=key: self._set_episodic_weight_preset(chosen)).pack(side="left", padx=3)
        body = ttk.Frame(workbench)
        body.pack(fill="x", padx=10, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        weights = ttk.Frame(body)
        weights.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        weights.columnconfigure(1, weight=1)
        self.episodic_weight_labels = {}
        labels = ("Description relevance", "Keyword / tag relevance", "Time / recency", "Importance / confidence / outcome")
        colors = ("#60a5fa", "#c084fc", "#34d399", "#fbbf24")
        for row, (key, label, color) in enumerate(zip(RETRIEVAL_WEIGHT_KEYS, labels, colors)):
            ttk.Label(weights, text=label, foreground=color).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Scale(weights, from_=0, to=1, variable=self.episodic_score_weights[key], length=210,
                      command=lambda value, chosen=key: self._change_episodic_weight(chosen, value)).grid(row=row, column=1, sticky="ew", padx=8)
            value_label = ttk.Label(weights, width=6)
            value_label.grid(row=row, column=2, sticky="e")
            self.episodic_weight_labels[key] = value_label
        self.episodic_weight_summary = ttk.Label(weights, wraplength=490)
        self.episodic_weight_summary.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.episodic_curve_canvas = tk.Canvas(body, width=430, height=210, background="#101827", highlightthickness=0)
        self.episodic_curve_canvas.grid(row=0, column=1, sticky="nsew")
        self.episodic_curve_canvas.bind("<Configure>", lambda _event: self._refresh_episodic_visuals())
        ttk.Label(workbench, text="Moving a slider selects Weighted and redistributes the other weights to total 1. Legacy retains the original controls below. The curve previews your draft; result bars show the last completed query. Shape, center, spread and variance update the preview; the shaded band is random jitter, not probability or temperature.", wraplength=1100).pack(anchor="w", padx=10, pady=(0, 8))
        for variable in (self.episodic_score_mode_var, self.episodic_shape_var, self.episodic_center_var,
                         self.episodic_spread_var, self.episodic_variance_var):
            variable.trace_add("write", lambda *_args: self._refresh_episodic_visuals())
        self._refresh_episodic_visuals()

    def _change_episodic_weight(self, key, value):
        if self._episodic_weights_updating:
            return
        # Tk has already set the changed variable; restore the prior vector for redistribution.
        current = getattr(self, "_episodic_last_weights", {name: RETRIEVAL_OPTION_DEFAULTS[name] for name in RETRIEVAL_WEIGHT_KEYS})
        updated = rebalance_score_weights(current, key, value)
        self._episodic_weights_updating = True
        try:
            for name, number in updated.items():
                self.episodic_score_weights[name].set(number)
            self._episodic_last_weights = updated
            self.episodic_score_mode_var.set("weighted")
        finally:
            self._episodic_weights_updating = False
        self._refresh_episodic_visuals()

    def _set_episodic_weight_preset(self, key=None):
        self._episodic_weights_updating = True
        try:
            values = {name: (1.0 if name == key else 0.0) if key else RETRIEVAL_OPTION_DEFAULTS[name] for name in RETRIEVAL_WEIGHT_KEYS}
            for name, value in values.items():
                self.episodic_score_weights[name].set(value)
            self._episodic_last_weights = values
            self.episodic_score_mode_var.set("weighted")
        finally:
            self._episodic_weights_updating = False
        self._refresh_episodic_visuals()

    def _refresh_episodic_visuals(self):
        if not hasattr(self, "episodic_curve_canvas"):
            return
        values = {key: variable.get() for key, variable in self.episodic_score_weights.items()}
        for key, label in self.episodic_weight_labels.items():
            label.configure(text=f"{values[key]:.3f}")
        mode = self.episodic_score_mode_var.get()
        self.episodic_weight_summary.configure(text=f"Total {sum(values.values()):.3f} • " +
            ("Weighted: only the four selected contributions enter the base score. Backend off uses lexical relevance." if mode == "weighted" else "Legacy active: these four dials are a draft. Original weights and rating bonus remain active."))
        center = finite_number(self.episodic_center_var.get())
        spread = finite_number(self.episodic_spread_var.get(), .22)
        if center > 1:
            center /= 100
        if spread > 1:
            spread /= 100
        rows = distribution_preview(self.episodic_shape_var.get(), center, spread, self.episodic_variance_var.get())
        canvas = self.episodic_curve_canvas
        width, height = max(360, canvas.winfo_width()), max(195, canvas.winfo_height())
        canvas.delete("all")
        left, top, right, bottom = 46, 32, width - 18, height - 35
        ymax = max(1.0, max(row["high"] for row in rows))
        def point(row, field):
            return left + row["position"] * (right-left), bottom - row[field] / ymax * (bottom-top)
        band = [coordinate for row in rows for coordinate in point(row, "high")]
        band += [coordinate for row in reversed(rows) for coordinate in point(row, "low")]
        canvas.create_polygon(*band, fill="#203d59", outline="")
        for tick in (0, .5, 1):
            y = bottom - tick / ymax * (bottom-top)
            canvas.create_line(left, y, right, y, fill="#293448")
            canvas.create_text(left-8, y, text=f"{tick:g}", fill="#9caec6", anchor="e")
        canvas.create_line(*[coordinate for row in rows for coordinate in point(row, "weight")], fill="#60a5fa", width=2)
        canvas.create_text(left, 15, anchor="w", text="Rank multiplier + jitter range", fill="#dbeafe")
        canvas.create_text(left, height-15, anchor="w", text="Best base rank", fill="#9caec6")
        canvas.create_text(right, height-15, anchor="e", text="Last base rank", fill="#9caec6")

    def _draw_episodic_score_results(self, results):
        if not hasattr(self, "episodic_score_canvas"):
            return
        self._episodic_visual_results = list(results or [])[:8]
        canvas = self.episodic_score_canvas
        width = max(700, canvas.winfo_width())
        signature = (width, json.dumps(self._episodic_visual_results, sort_keys=True, default=str))
        if getattr(self, "_episodic_score_signature", None) == signature:
            return
        self._episodic_score_signature = signature
        canvas.delete("all")
        canvas.configure(height=max(60, 30 + 34 * len(self._episodic_visual_results)))
        if not results:
            canvas.create_text(14, 25, anchor="w", text="Run Preview or Recall to inspect result contributions.", fill="#9caec6")
            return
        colors = {"description": "#60a5fa", "keyword": "#c084fc", "recency": "#34d399", "rating": "#fbbf24",
                  "semantic": "#60a5fa", "preferred_tags": "#c084fc", "ratings": "#fbbf24"}
        maximum = max(1.0, max(finite_number(row.get("weighted_total")) for row in self._episodic_visual_results))
        for index, row in enumerate(self._episodic_visual_results):
            y = 20 + index * 34
            title = str(row.get("summary_text") or row.get("snapshot_id") or "Memory")
            title = title[:34] + ("…" if len(title) > 34 else "")
            canvas.create_text(12, y+7, anchor="w", text=f"{index+1}. {title}", fill="#dbeafe")
            start = 300.0
            canvas.create_rectangle(start, y, width-175, y+15, fill="#1d293b", outline="")
            for key, value in (row.get("score_contributions") or {"legacy": row.get("weighted_total", 0)}).items():
                length = max(0.0, finite_number(value)) / maximum * (width-475)
                canvas.create_rectangle(start, y, start+length, y+15, fill=colors.get(key, "#94a3b8"), outline="")
                start += length
            canvas.create_text(width-12, y+7, anchor="e", text=f"base {finite_number(row.get('weighted_total')):.3f}  →  {finite_number(row.get('adjusted_score')):.3f}", fill="#dbeafe")

    def _episodic_retrieval_segments(self):
        query = (self.episodic_query_var.get() or "").strip()
        try:
            search = normalize_search_options({key: variable.get() for key, variable in self.episodic_search_vars.items()})
            filters = {**search, "tags_required": self.episodic_tags_required_var.get().strip(),
                       "source_buckets": self.episodic_source_buckets_var.get().strip()}
            if not query and not search_has_filter(filters):
                raise ValueError("Enter semantic query text or a text/date/tag/source filter.")
            if not query and finite_number(self.episodic_min_relevance_var.get()) > 0:
                raise ValueError("Minimum query relevance requires semantic query text; use zero for filter-only search.")
        except ValueError as error:
            messagebox.showerror("Aurora 2 search", str(error))
            return None
        segments = [
            f"query={json.dumps(query)}",
            f"k={(self.episodic_limit_var.get() or '4').strip() or '4'}",
            f"time_weight={(self.episodic_time_weight_var.get() or '0.50').strip() or '0.50'}",
            f"semantic_weight={(self.episodic_semantic_weight_var.get() or '0.50').strip() or '0.50'}",
            f"tag_weight={(self.episodic_tag_weight_var.get() or '0.00').strip() or '0.00'}",
            f"semantic_backend={(self.episodic_backend_var.get() or 'auto').strip() or 'auto'}",
            f"embedding_model={json.dumps((self.episodic_embedding_model_var.get() or 'text-embedding-3-small').strip() or 'text-embedding-3-small')}",
            f"distribution_shape={(self.episodic_shape_var.get() or 'balanced').strip() or 'balanced'}",
            f"distribution_center={(self.episodic_center_var.get() or '0.00').strip() or '0.00'}",
            f"distribution_spread={(self.episodic_spread_var.get() or '0.22').strip() or '0.22'}",
            f"variance_bias={(self.episodic_variance_var.get() or '0.00').strip() or '0.00'}",
        ]
        tags_required = (self.episodic_tags_required_var.get() or "").strip()
        if tags_required:
            segments.append(f"tags_required={json.dumps(tags_required)}")
        tags_preferred = (self.episodic_tags_preferred_var.get() or "").strip()
        if tags_preferred:
            segments.append(f"tags_preferred={json.dumps(tags_preferred)}")
        source_buckets = (self.episodic_source_buckets_var.get() or "").strip()
        if source_buckets:
            segments.append(f"source_buckets={json.dumps(source_buckets)}")
        for key, variable in (("time_mode", self.episodic_time_mode_var),
                              ("age_half_life_hours", self.episodic_age_half_life_hours_var),
                              ("min_relevance", self.episodic_min_relevance_var),
                              ("semantic_tag_weight", self.episodic_semantic_tag_weight_var),
                              ("embedding_fallback", self.episodic_embedding_fallback_var),
                              ("time_anchor", self.episodic_time_anchor_var),
                              ("time_scale", self.episodic_time_scale_var)):
            segments.append(f"{key}={json.dumps(variable.get().strip())}")
        segments.append(f"score_mode={self.episodic_score_mode_var.get()}")
        for key, variable in self.episodic_score_weights.items():
            segments.append(f"{key}={variable.get():.12g}")
        segments.extend(f"{key}={json.dumps(value)}" for key, value in search.items())
        try:
            retrieval_commands.build_retrieval_request(segments)
        except ValueError as error:
            messagebox.showerror("Aurora 2 search", str(error))
            return None
        return segments

    def _update_episodic_feedback_token(self, search_info):
        feedback = search_info.get("feedback", {}) or {}
        token = feedback.get("token", "") if feedback.get("session") == self.episodic_search_vars["feedback_session"].get() else ""
        self.episodic_search_vars["feedback_token"].set(token)

    def send_episodic_feedback(self, action):
        self.episodic_search_vars["feedback_action"].set(action)
        return self.send_episodic_retrieval()

    def send_episodic_retrieval(self, _event=None):
        segments = self._episodic_retrieval_segments()
        if segments is None:
            return "break"
        self.send_raw(f"RETRIEVAL_PULL({', '.join(segments)})")
        self.episodic_search_vars["feedback_action"].set("none")
        self.episodic_retrieval_status_var.set("Retrieval preview requested with the displayed query options; waiting for runtime result.")
        self.after(500, self.refresh_now)
        self.after(1500, self.refresh_now)
        return "break"

    def send_episodic_recall_shorthand(self, _event=None):
        segments = self._episodic_retrieval_segments()
        if segments is None:
            return "break"
        self.send_raw(f"RECALL({', '.join(segments)})")
        self.episodic_search_vars["feedback_action"].set("none")
        self.episodic_retrieval_status_var.set("Recall requested with the same displayed options as Preview; runtime expands RETRIEVAL_PULL.")
        self.after(500, self.refresh_now)
        self.after(1500, self.refresh_now)
        return "break"

    def use_displayed_retrieval_handle(self):
        self.episodic_result_handle_var.set(self._episodic_displayed_result_handle)

    def inspect_retained_retrieval(self):
        handle = self.episodic_result_handle_var.get().strip()
        try:
            parse_retrieval_result_arguments("SHOW_RETRIEVAL_RESULT", [handle, "0", "24"])
        except ValueError as error:
            messagebox.showerror("Aurora 2", str(error))
            return
        self.send_raw(f"SHOW_RETRIEVAL_RESULT({json.dumps(handle)}, 0, 24)")

    def send_episodic_promotion(self, _event=None):
        index_text = (self.episodic_promote_index_var.get() or "1").strip() or "1"
        target = (self.episodic_promote_target_var.get() or "notes").strip() or "notes"
        prefix = (self.episodic_promote_prefix_var.get() or "").strip()
        handle = self.episodic_result_handle_var.get().strip()
        args = [index_text, target, prefix] + ([handle] if handle else [])
        try:
            parse_retrieval_result_arguments("PROMOTE_EPISODIC_MEMORY", args)
        except ValueError as error:
            messagebox.showerror("Aurora 2", str(error))
            return "break"
        command = "PROMOTE_EPISODIC_MEMORY(" + ", ".join(json.dumps(arg) for arg in args) + ")"
        self.send_raw(command)
        self.episodic_promotion_status_var.set(
            f"Promotion requested for retrieval item {index_text} into {target}; waiting for runtime result."
        )
        self.after(500, self.refresh_now)
        self.after(1500, self.refresh_now)
        return "break"

    def set_operator_passcode(self):
        passcode = (self.operator_passcode_var.get() or "").strip()
        if not passcode:
            messagebox.showinfo("Aurora 2", "Enter a passcode first.")
            return
        self.send_raw(f"SET_OPERATOR_PASSCODE({json.dumps(passcode)})")
        self.send_raw(f"SET_OPERATOR_PASSCODE_REQUIRED({'on' if self.security_required_var.get() else 'off'})")
        self.operator_passcode_var.set("")

    def apply_operator_security_requirement(self):
        self.send_raw(f"SET_OPERATOR_PASSCODE_REQUIRED({'on' if self.security_required_var.get() else 'off'})")

    def apply_passcode_command_visibility(self):
        enabled = bool(self.show_passcode_commands_var.get())
        if enabled:
            confirmed = messagebox.askyesno(
                "Aurora 2",
                "Show raw passcode-bearing commands in logs/history?\n\nThis is less safe on a shared screen.",
            )
            if not confirmed:
                self.show_passcode_commands_var.set(False)
                return
        self.send_raw(f"SET_PASSCODE_COMMAND_VISIBILITY({'on' if enabled else 'off'})")

    def authorize_operator_access(self):
        passcode = (self.operator_passcode_var.get() or "").strip()
        if not passcode:
            messagebox.showinfo("Aurora 2", "Enter the current passcode first.")
            return
        self.send_raw(f"AUTHORIZE_OPERATOR({json.dumps(passcode)})")
        self.operator_passcode_var.set("")

    def clear_operator_passcode(self):
        if not messagebox.askyesno("Aurora 2", "Clear the configured external-operator passcode?"):
            return
        self.send_raw("CLEAR_OPERATOR_PASSCODE()")
        self.operator_passcode_var.set("")

    def _on_banner_autoscroll_toggle(self):
        if self.banner_auto_scroll_var.get():
            self.banner_scroll_offset = 0
        self._render_runtime_banner(reset=False)

    def _adjust_banner_offset(self, delta):
        self.banner_auto_scroll_var.set(False)
        if self.banner_overflow <= 0:
            self.banner_scroll_offset = 0
        else:
            self.banner_scroll_offset = max(0, min(self.banner_overflow, self.banner_scroll_offset + int(delta)))
        self._render_runtime_banner(reset=False)

    def _set_runtime_banner_text(self, text):
        text_value = str(text or "").strip()
        if text_value == self.banner_text_value:
            return
        self.banner_text_value = text_value
        self.banner_scroll_offset = 0
        self._render_runtime_banner(reset=True)

    def _render_runtime_banner(self, reset=False):
        if not hasattr(self, "runtime_banner_canvas"):
            return
        canvas = self.runtime_banner_canvas
        canvas.delete("all")
        width = max(120, int(canvas.winfo_width() or 120))
        height = max(24, int(canvas.winfo_height() or 24))
        text_value = self.banner_text_value
        if not text_value:
            self.banner_overflow = 0
            self.banner_text_width = 0
            return
        if reset and self.banner_auto_scroll_var.get():
            self.banner_scroll_offset = 0
        anchor_x = 8 - self.banner_scroll_offset
        primary_id = canvas.create_text(
            anchor_x,
            height // 2,
            anchor="w",
            text=text_value,
            fill=MUTED,
            font=("Segoe UI", 10),
        )
        bbox = canvas.bbox(primary_id)
        self.banner_text_width = max(0, (bbox[2] - bbox[0]) if bbox else 0)
        visible_width = max(0, width - 16)
        self.banner_overflow = max(0, self.banner_text_width - visible_width)
        if self.banner_auto_scroll_var.get() and self.banner_overflow > 0:
            loop_x = 8 + self.banner_text_width + BANNER_GAP_PX - self.banner_scroll_offset
            canvas.create_text(
                loop_x,
                height // 2,
                anchor="w",
                text=text_value,
                fill=MUTED,
                font=("Segoe UI", 10),
            )
        else:
            self.banner_scroll_offset = max(0, min(self.banner_overflow, self.banner_scroll_offset))

    def _banner_tick(self):
        try:
            if self.banner_auto_scroll_var.get() and self.banner_overflow > 0:
                cycle_width = self.banner_overflow + BANNER_GAP_PX
                if cycle_width > 0:
                    self.banner_scroll_offset = (self.banner_scroll_offset + BANNER_STEP_PX) % cycle_width
                    self._render_runtime_banner(reset=False)
        finally:
            self.after(BANNER_TICK_MS, self._banner_tick)

    def open_banner_dialog(self):
        if self.banner_window is not None and self.banner_window.winfo_exists():
            self.banner_window.lift()
            self.banner_window.focus_force()
            return
        self.banner_window = tk.Toplevel(self)
        self.banner_window.title("Aurora Runtime Banner")
        fit_popout_window(self.banner_window, 1200, 180, self)
        self.banner_window.configure(bg=BG)
        def close_banner_window(_event=None):
            if self.banner_window is not None and self.banner_window.winfo_exists():
                self.banner_window.destroy()
            self.banner_window = None
        self.banner_window.protocol("WM_DELETE_WINDOW", close_banner_window)
        self.banner_window.bind("<Escape>", close_banner_window)
        ttk.Label(self.banner_window, text="Runtime Summary", style="CardTitle.TLabel").pack(anchor="w", padx=12, pady=(12, 8))
        text_widget = tk.Text(self.banner_window, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="none", height=5)
        text_widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._write_text(text_widget, self.banner_text_value or "No runtime summary available.")

    def apply_turn_scheduler_profile_to_controls(self, profile_name):
        normalized = (profile_name or "").strip().lower()
        profile = TURN_SCHEDULER_PROFILE_DEFAULTS.get(normalized)
        if not profile:
            return
        self.turn_scheduler_profile_var.set(normalized)
        self.turn_scheduler_mode_var.set(profile["mode"])
        self.turn_heartbeat_var.set(profile["heartbeat_seconds"])
        self.turn_min_gap_var.set(profile["min_gap_seconds"])
        self.turn_capture_wake_var.set(bool(profile["capture_wake_enabled"]))
        self.turn_capture_wake_debounce_var.set(profile["capture_wake_debounce_seconds"])
        self.turn_post_action_settle_var.set(profile["post_action_settle_seconds"])
        self.scheduler_status_var.set(
            f"{normalized.title()} profile: {profile['description']}."
        )

    def on_turn_scheduler_profile_selected(self, _event=None):
        selected = (self.turn_scheduler_profile_var.get() or "").strip().lower()
        if selected == "custom":
            self.scheduler_status_var.set(
                "Custom profile: mix any scheduler settings manually, then Apply Settings."
            )
            return
        self.apply_turn_scheduler_profile_to_controls(selected)

    def on_turn_scheduler_leaf_changed(self, _event=None):
        if (self.turn_scheduler_profile_var.get() or "").strip().lower() != "custom":
            self.turn_scheduler_profile_var.set("custom")
        self.scheduler_status_var.set(
            "Custom profile: scheduler leaf edits will be previewed and applied atomically."
        )

    def apply_model_preset(self, preset_name):
        if self.settings_transaction_pending is not None:
            messagebox.showinfo("Aurora 2", "Wait for the current settings transaction receipt first.", parent=self)
            return
        preset = MODEL_PRESETS.get(preset_name)
        if not preset:
            return
        self.model_transport_var.set(preset.get("transport", "chat_completions"))
        self.text_model_var.set(preset["text"])
        self.vision_model_var.set(preset["vision"])
        self.reasoning_model_var.set(preset["reasoning"])
        self.reasoning_effort_var.set(preset["effort"])
        self.battle_effort_var.set(preset["battle_effort"])
        self.review_effort_var.set("medium")
        self.critique_effort_var.set("high")
        self.model_verbosity_var.set("medium")
        self.review_verbosity_var.set("medium")
        self.battle_verbosity_var.set("low")
        self.critique_verbosity_var.set("high")
        self.reasoning_summary_var.set("auto")
        self.auto_dynamic_var.set(True)
        self.review_turn_interval_var.set("10")
        self.critique_turn_interval_var.set("30")
        self.apply_turn_scheduler_profile_to_controls("balanced")
        self.temperature_var.set(preset["temperature"])
        if hasattr(self, "model_cost_status_var"):
            hint = MODEL_PRESET_HINTS.get(preset_name, "preset applied")
            self.model_cost_status_var.set(f"Preset selected: {preset_name} | {hint}. Settings are being sent.")
        self.apply_settings(
            post_commands=self._build_additional_settings_commands(),
            activity_label=f"model preset {preset_name}",
        )
        self.mark_operator_activity(f"Applied model preset: {preset_name}.")

    def apply_stateful_model_preset(self, profile_name):
        profile = (profile_name or "").strip()
        if not profile:
            return
        self.send_raw(f"SET_STATEFUL_MODEL_PRESET({profile})")
        if hasattr(self, "model_cost_status_var"):
            self.model_cost_status_var.set(
                f"Stateful profile requested: {profile}. Preview metadata only; Transport is selected separately."
            )
        self.after(500, self.refresh_now)
        self.after(1500, self.refresh_now)
        self.mark_operator_activity(f"Requested stateful profile: {profile}.")

    def apply_overlay_preset(self, preset_name, apply_now=True):
        preset = OVERLAY_PRESETS.get(preset_name)
        if not preset:
            return
        self.tile_grid_var.set(bool(preset["tile_grid"]))
        self.cursor_label_var.set(bool(preset["cursor_label"]))
        self.keypoint_grid_var.set(bool(preset["keypoint_grid"]))
        self.status_overlay_var.set(bool(preset["status_overlay"]))
        if apply_now:
            commands = [
                f"SET_TILE_GRID({'on' if self.tile_grid_var.get() else 'off'})",
                f"SET_CURSOR_LABEL({'on' if self.cursor_label_var.get() else 'off'})",
                f"SET_KEYPOINT_GRID({'on' if self.keypoint_grid_var.get() else 'off'})",
                f"SET_STATUS_OVERLAY({'on' if self.status_overlay_var.get() else 'off'})",
            ]
            for command in commands:
                self.send_raw(command)
            self.mark_operator_activity(f"Applied overlay preset: {preset_name} ({len(commands)} independent commands).")

    def apply_operator_profile(self, profile_name):
        if self.settings_transaction_pending is not None:
            messagebox.showinfo("Aurora 2", "Wait for the current settings transaction receipt first.", parent=self)
            return
        profile = OPERATOR_PROFILES.get(profile_name)
        if not profile:
            return
        confirm_message = str(profile.get("confirm", "") or "").strip()
        if confirm_message and not messagebox.askyesno("Aurora 2", confirm_message):
            return

        self.live_var.set(bool(profile.get("live", self.live_var.get())))
        self.exec_var.set(profile.get("execution", self.exec_var.get()))
        self.action_var.set(profile.get("action", self.action_var.get()))

        model_preset = profile.get("model_preset")
        if model_preset in MODEL_PRESETS:
            preset = MODEL_PRESETS[model_preset]
            self.model_transport_var.set(preset.get("transport", "chat_completions"))
            self.text_model_var.set(preset["text"])
            self.vision_model_var.set(preset["vision"])
            self.reasoning_model_var.set(preset["reasoning"])
            self.temperature_var.set(preset["temperature"])
            self.reasoning_effort_var.set(profile.get("reasoning_effort", preset["effort"]))
            self.battle_effort_var.set(profile.get("battle_effort", preset["battle_effort"]))
            self.model_verbosity_var.set(profile.get("verbosity", "medium"))
            self.review_verbosity_var.set(profile.get("review_verbosity", "medium"))
            self.battle_verbosity_var.set(profile.get("battle_verbosity", "low"))
            self.critique_verbosity_var.set(profile.get("critique_verbosity", "high"))
            self.review_effort_var.set(profile.get("review_effort", "medium"))
            self.critique_effort_var.set(profile.get("critique_effort", "high"))
            self.reasoning_summary_var.set(profile.get("summary_mode", "auto"))
            self.auto_dynamic_var.set(bool(profile.get("auto_dynamic_inference", True)))
            self.review_turn_interval_var.set(str(profile.get("review_turn_interval", 10)))
            self.critique_turn_interval_var.set(str(profile.get("critique_turn_interval", 30)))
            scheduler_profile = str(profile.get("turn_scheduler_profile", "balanced"))
            if scheduler_profile in TURN_SCHEDULER_PROFILE_DEFAULTS:
                self.apply_turn_scheduler_profile_to_controls(scheduler_profile)
            self.turn_scheduler_mode_var.set(str(profile.get("turn_scheduler_mode", self.turn_scheduler_mode_var.get() or "hybrid")))
            self.turn_heartbeat_var.set(str(profile.get("turn_heartbeat_seconds", self.turn_heartbeat_var.get() or "2.25")))
            self.turn_min_gap_var.set(str(profile.get("turn_min_gap_seconds", self.turn_min_gap_var.get() or "0.55")))
            self.turn_capture_wake_var.set(bool(profile.get("turn_capture_wake_enabled", self.turn_capture_wake_var.get())))
            self.turn_capture_wake_debounce_var.set(str(profile.get("turn_capture_wake_debounce_seconds", self.turn_capture_wake_debounce_var.get() or "0.90")))
            self.turn_post_action_settle_var.set(str(profile.get("turn_post_action_settle_seconds", self.turn_post_action_settle_var.get() or "0.55")))
            self.demand_capture_var.set(bool(profile.get("demand_capture_enabled", self.demand_capture_var.get())))
        else:
            if "reasoning_effort" in profile:
                self.reasoning_effort_var.set(profile["reasoning_effort"])
            if "battle_effort" in profile:
                self.battle_effort_var.set(profile["battle_effort"])
            if "verbosity" in profile:
                self.model_verbosity_var.set(profile["verbosity"])
            if "review_effort" in profile:
                self.review_effort_var.set(profile["review_effort"])
            if "critique_effort" in profile:
                self.critique_effort_var.set(profile["critique_effort"])
            if "review_verbosity" in profile:
                self.review_verbosity_var.set(profile["review_verbosity"])
            if "battle_verbosity" in profile:
                self.battle_verbosity_var.set(profile["battle_verbosity"])
            if "critique_verbosity" in profile:
                self.critique_verbosity_var.set(profile["critique_verbosity"])
            if "summary_mode" in profile:
                self.reasoning_summary_var.set(profile["summary_mode"])
            if "auto_dynamic_inference" in profile:
                self.auto_dynamic_var.set(bool(profile["auto_dynamic_inference"]))
            if "review_turn_interval" in profile:
                self.review_turn_interval_var.set(str(profile["review_turn_interval"]))
            if "critique_turn_interval" in profile:
                self.critique_turn_interval_var.set(str(profile["critique_turn_interval"]))
            if "turn_scheduler_mode" in profile:
                self.turn_scheduler_mode_var.set(str(profile["turn_scheduler_mode"]))
            if "turn_scheduler_profile" in profile:
                if str(profile["turn_scheduler_profile"]) in TURN_SCHEDULER_PROFILE_DEFAULTS:
                    self.apply_turn_scheduler_profile_to_controls(str(profile["turn_scheduler_profile"]))
                else:
                    self.turn_scheduler_profile_var.set(str(profile["turn_scheduler_profile"]))
            if "turn_heartbeat_seconds" in profile:
                self.turn_heartbeat_var.set(str(profile["turn_heartbeat_seconds"]))
            if "turn_min_gap_seconds" in profile:
                self.turn_min_gap_var.set(str(profile["turn_min_gap_seconds"]))
            if "turn_capture_wake_enabled" in profile:
                self.turn_capture_wake_var.set(bool(profile["turn_capture_wake_enabled"]))
            if "turn_capture_wake_debounce_seconds" in profile:
                self.turn_capture_wake_debounce_var.set(str(profile["turn_capture_wake_debounce_seconds"]))
            if "turn_post_action_settle_seconds" in profile:
                self.turn_post_action_settle_var.set(str(profile["turn_post_action_settle_seconds"]))
            if "demand_capture_enabled" in profile:
                self.demand_capture_var.set(bool(profile["demand_capture_enabled"]))

        if "screenshot_interval" in profile:
            self.interval_var.set(str(profile["screenshot_interval"]))
        if "pending_queue_mode" in profile:
            self.pending_queue_mode_var.set(str(profile["pending_queue_mode"]))
        if "command_drip_retention" in profile:
            self.command_drip_retention_var.set(str(profile["command_drip_retention"]))
        if "command_drip_lookahead" in profile:
            self.command_drip_lookahead_var.set(str(profile["command_drip_lookahead"]))
        if "live_init" in profile:
            self.live_init_var.set(bool(profile["live_init"]))
        if "sound_effects" in profile:
            self.sound_var.set(bool(profile["sound_effects"]))
        if "time_logging" in profile:
            self.time_logging_var.set(bool(profile["time_logging"]))
        if "chat_log_echo" in profile:
            self.chat_log_echo_var.set(bool(profile["chat_log_echo"]))
        advanced_profile_keys = {
            "image_detail",
            "latest_image_detail",
            "high_detail",
            "max_images_in_history",
        }
        if "image_detail" in profile:
            self.image_detail_var.set(str(profile["image_detail"]))
        if "latest_image_detail" in profile:
            self.latest_image_detail_var.set(str(profile["latest_image_detail"]))
        if "high_detail" in profile:
            self.high_detail_var.set(str(profile["high_detail"]))
        if "max_images_in_history" in profile:
            self.max_images_var.set(str(profile["max_images_in_history"]))
        episodic_profile_keys = {
            "episodic_planning_mode",
            "episodic_backend",
            "episodic_planning_k",
            "episodic_planning_cooldown",
        }
        if "episodic_planning_mode" in profile:
            self.episodic_planning_mode_var.set(str(profile["episodic_planning_mode"]))
        if "episodic_backend" in profile:
            self.episodic_backend_var.set(str(profile["episodic_backend"]))
        if "episodic_planning_k" in profile:
            self.episodic_planning_k_var.set(str(profile["episodic_planning_k"]))
        if "episodic_planning_cooldown" in profile:
            self.episodic_planning_cooldown_var.set(str(profile["episodic_planning_cooldown"]))

        overlay_preset = profile.get("overlay_preset")
        if overlay_preset in OVERLAY_PRESETS:
            self.apply_overlay_preset(overlay_preset, apply_now=False)

        post_commands = self._build_additional_settings_commands()
        if any(key in profile for key in advanced_profile_keys):
            post_commands.extend(self._build_advanced_context_commands())
        if any(key in profile for key in episodic_profile_keys):
            post_commands.extend(self._build_episodic_memory_commands())
            self.episodic_control_status_var.set(
                "Episodic profile changes are waiting for the registered settings receipt."
            )
            self.episodic_tab_planning_status_var.set(
                "Episodic profile changes will be sent after the registered settings transaction succeeds."
            )
        post_commands.extend(profile.get("extra_commands", []) or [])
        self.apply_settings(
            post_commands=post_commands,
            activity_label=f"operator profile {profile_name}",
        )
        hint = str(profile.get("hint", "") or "").strip()
        suffix = f" | {hint}" if hint else ""
        self.mark_operator_activity(f"Queued operator profile: {profile_name}.{suffix}")

    def refresh_model_choice_widgets(self, choices=None):
        if choices is None:
            self.current_model_choices = build_model_choices()
        else:
            self.current_model_choices = sorted(set(choices))
        for widget in (
            getattr(self, "text_model_combo", None),
            getattr(self, "vision_model_combo", None),
            getattr(self, "reasoning_model_combo", None),
        ):
            if widget is not None:
                widget.configure(values=self.current_model_choices)
        custom_count = max(0, len(self.current_model_choices) - len(MODELS))
        if hasattr(self, "model_catalog_summary_label"):
            self.model_catalog_summary_label.configure(
                text=f"built-in={len(MODELS)} | custom={custom_count} | total={len(self.current_model_choices)}"
            )

    def refresh_model_catalog(self):
        self.refresh_model_choice_widgets()
        self.refresh_now()

    def _run_model_catalog_cli(self, *args):
        script_path = ROOT / "aurora2.py"
        python_executable = sys.executable
        python_candidate = python_executable.replace("pythonw.exe", "python.exe")
        if python_candidate != python_executable and Path(python_candidate).exists():
            python_executable = python_candidate
        result = subprocess.run(
            [python_executable, str(script_path), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            stderr_text = (result.stderr or "").strip()
            stdout_text = (result.stdout or "").strip()
            raise RuntimeError(stderr_text or stdout_text or f"Model catalog command failed with exit code {result.returncode}.")
        stdout_text = (result.stdout or "").strip()
        if not stdout_text:
            raise RuntimeError("Model catalog command returned no output.")
        for line in reversed(stdout_text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        raise RuntimeError(stdout_text)

    def add_model_dialog(self):
        model_name = simpledialog.askstring("Aurora 2", "Enter the exact model id to validate and add:")
        if not model_name:
            return
        normalized_model = model_name.strip()
        if not normalized_model:
            return
        try:
            result = self._run_model_catalog_cli("--validate-model", normalized_model, "--add-model")
        except Exception as error:
            messagebox.showerror("Aurora 2", f"Model validation failed.\n\n{error}")
            return
        if not result.get("ok"):
            messagebox.showerror("Aurora 2", result.get("error", "Model validation failed."))
            return
        self.refresh_model_choice_widgets()
        for variable in (self.text_model_var, self.vision_model_var, self.reasoning_model_var):
            if not variable.get().strip():
                variable.set(normalized_model)
        messagebox.showinfo(
            "Aurora 2",
            f"Validated and added model '{normalized_model}'.\nAuth path: {result.get('auth_mode', '-')}\nReply: {result.get('reply_preview', 'OK')}",
        )
        self.refresh_now()

    def remove_selected_model_dialog(self):
        candidate = (
            self.reasoning_model_var.get().strip()
            or self.vision_model_var.get().strip()
            or self.text_model_var.get().strip()
        )
        model_name = simpledialog.askstring("Aurora 2", "Enter the custom model id to remove:", initialvalue=candidate)
        if not model_name:
            return
        normalized_model = model_name.strip()
        if not normalized_model:
            return
        if normalized_model in MODELS:
            messagebox.showerror("Aurora 2", "Built-in Aurora models cannot be removed from the catalog.")
            return
        if not messagebox.askyesno("Aurora 2", f"Remove custom model '{normalized_model}' from the Aurora catalog?"):
            return
        try:
            result = self._run_model_catalog_cli("--remove-model", normalized_model)
        except Exception as error:
            messagebox.showerror("Aurora 2", f"Failed to remove model.\n\n{error}")
            return
        if not result.get("ok"):
            messagebox.showerror("Aurora 2", result.get("error", "Failed to remove model."))
            return
        self.refresh_model_choice_widgets()
        messagebox.showinfo("Aurora 2", f"Removed custom model '{normalized_model}'.")
        self.refresh_now()

    def apply_advanced_settings(self, show_confirmation=False):
        return self._submit_settings_transaction(
            "apply",
            changes=[{"key": "vision.image_detail", "value": self.image_detail_var.get() or "low"}],
            post_commands=self._build_advanced_context_commands(),
            show_confirmation=show_confirmation,
            activity_label="advanced settings",
        )

    def apply_chat_head_settings(self, show_confirmation=False):
        commands = [
            f"SET_CHAT_HEAD_OPACITY({(self.chat_head_opacity_var.get() or '0.87').strip()})",
            f"SET_CHAT_HEAD_TOPMOST({'on' if self.chat_head_topmost_var.get() else 'off'})",
            "SET_CHAT_HEAD_STRIP_SIZE("
            f"{(self.chat_head_strip_width_var.get() or '1000').strip()},"
            f"{(self.chat_head_strip_height_var.get() or '100').strip()})",
            "SET_CHAT_HEAD_HISTORY_SIZE("
            f"{(self.chat_head_history_width_var.get() or '420').strip()},"
            f"{(self.chat_head_history_height_var.get() or '620').strip()})",
            f"SET_CHAT_HEAD_SEND_ANIMATION({(self.chat_head_send_animation_var.get() or 'pulse').strip()})",
            f"SET_CHAT_HEAD_SEND_ANIMATION_SECONDS({(self.chat_head_send_animation_seconds_var.get() or '0.75').strip()})",
        ]
        for command in commands:
            self.send_raw(command)
        self.mark_operator_activity(f"Sent chat head settings batch ({len(commands)} commands).")
        if show_confirmation:
            messagebox.showinfo("Aurora 2", "Chat head settings sent to Aurora.")

    def apply_additional_settings(self, show_confirmation=False):
        commands = self._build_additional_settings_commands()
        for command in commands:
            self.send_raw(command)
        self.settings_transaction_status_var.set(
            f"Sent {len(commands)} additional independent command(s); atomic registered settings were unchanged."
        )
        self.mark_operator_activity(f"Sent additional settings batch ({len(commands)} independent commands).")
        if show_confirmation:
            messagebox.showinfo("Aurora 2", self.settings_transaction_status_var.get(), parent=self)
        return commands

    def apply_settings(self, show_confirmation=False, post_commands=None, activity_label="registered settings"):
        return self._submit_settings_transaction(
            "apply",
            post_commands=post_commands,
            show_confirmation=show_confirmation,
            activity_label=activity_label,
        )

    def send_save_handoff(self):
        value = self.handoff_file_var.get().strip()
        if value:
            self.send_raw(f"SAVE_HANDOFF({json.dumps(value)})")
        else:
            self.send_raw("SAVE_HANDOFF()")
        self.mark_operator_activity(f"Requested handoff save: {short(value or 'default', 120)}")

    def send_retrieve_handoff(self):
        value = self.handoff_file_var.get().strip()
        if value:
            self.send_raw(f"RETRIEVE_HANDOFF({json.dumps(value)})")
        else:
            self.send_raw("RETRIEVE_HANDOFF()")
        self.mark_operator_activity(f"Requested handoff retrieval: {short(value or 'default', 120)}")

    def queue_next_inference_plan(self):
        segments = []
        next_reasoning = (self.next_reasoning_var.get() or "").strip()
        if next_reasoning:
            segments.append(f"reasoning_effort={next_reasoning}")
        if (self.next_verbosity_var.get() or "").strip():
            segments.append(f"verbosity={self.next_verbosity_var.get().strip()}")
        if (self.next_summary_var.get() or "").strip():
            segments.append(f"summary_mode={self.next_summary_var.get().strip()}")
        if (self.next_image_detail_var.get() or "").strip():
            segments.append(f"image_detail={self.next_image_detail_var.get().strip()}")
        if (self.next_latest_image_detail_var.get() or "").strip():
            segments.append(f"latest_image_detail={self.next_latest_image_detail_var.get().strip()}")
        if (self.next_temperature_var.get() or "").strip():
            segments.append(f"temperature={self.next_temperature_var.get().strip()}")
        if (self.next_model_var.get() or "").strip():
            segments.append(f"model={self.next_model_var.get().strip()}")
        if (self.next_note_var.get() or "").strip():
            segments.append(f"note={json.dumps(self.next_note_var.get().strip())}")
        if not segments:
            messagebox.showinfo("Aurora 2", "Enter at least one next-turn setting or note.")
            return
        if segments == [f"reasoning_effort={next_reasoning}"]:
            self.send_raw(f"SET_NEXT_REASONING_EFFORT({next_reasoning})")
            self.mark_operator_activity("Queued one-turn reasoning effort override.")
            return
        self.send_raw(f"SET_NEXT_INFERENCE({'; '.join(segments)})")
        self.mark_operator_activity("Queued one-turn inference override.")

    def apply_runtime_locks(self, locks):
        locks = locks or {}
        locked_items = [name for name, enabled in locks.items() if enabled]
        self.lock_summary_label.configure(
            text=("Locks: " + ", ".join(locked_items)) if locked_items else "Locks: none"
        )
        for widget, widget_locks in self.widget_lock_dependencies.items():
            is_locked = any(bool(locks.get(lock_name, False)) for lock_name in widget_locks)
            try:
                if is_locked:
                    widget.state(["disabled"])
                else:
                    widget.state(["!disabled"])
            except Exception:
                pass

    def approve_selected_pending(self):
        selection = self.pending_tree.selection()
        if not selection:
            self.update_pending_selection_status()
            return
        indexes = self.pending_selection_arguments(selection)
        self.pending_selection_status_var.set(
            f"Approval requested for pending item(s): {', '.join(indexes)}. Waiting for runtime feedback."
        )
        self.send_raw(f"APPROVE_PENDING({','.join(indexes)})")

    def clear_selected_pending(self):
        selection = self.pending_tree.selection()
        if not selection:
            self.update_pending_selection_status()
            return
        indexes = self.pending_selection_arguments(selection)
        self.pending_selection_status_var.set(
            f"Clear requested for pending item(s): {', '.join(indexes)}. Waiting for runtime feedback."
        )
        self.send_raw(f"CLEAR_PENDING_COMMANDS({','.join(indexes)})")

    def pending_selection_arguments(self, selection):
        selectors = [getattr(self, "pending_item_selectors", {}).get(
            item, str(self.pending_tree.item(item, "values")[0])) for item in selection]
        version = getattr(self, "pending_snapshot_version", "")
        if version and all(selector.startswith("id:") for selector in selectors):
            selectors.append("version:" + version)
        return selectors

    def reset_pending_filters(self):
        self.pending_risk_var.set("all")
        self.pending_category_var.set("all")
        self.pending_search_var.set("")
        self.render_pending_current()

    def filter_pending_rows(self):
        risk_filter = (self.pending_risk_var.get() or "all").strip().lower()
        category_filter = (self.pending_category_var.get() or "all").strip().lower()
        search_filter = (self.pending_search_var.get() or "").strip().lower()
        filtered = []
        for idx, row in enumerate(self.pending_rows, start=1):
            risk = str(row.get("risk", "")).strip().lower()
            category = str(row.get("category", "")).strip().lower()
            command = str(row.get("command", ""))
            reason = str(row.get("reason", ""))
            if risk_filter != "all" and risk != risk_filter:
                continue
            if category_filter != "all" and category != category_filter:
                continue
            if search_filter and search_filter not in command.lower() and search_filter not in reason.lower():
                continue
            filtered.append((idx, row))
        return filtered

    def render_pending_current(self):
        selected = set(self.pending_tree.selection())
        self.pending_tree.delete(*self.pending_tree.get_children())
        self.pending_item_selectors = {}
        filtered_rows = self.filter_pending_rows()
        for idx, row in filtered_rows:
            score_text = f"{row.get('priority_score', 0)}/{row.get('importance_score', 0)}"
            identity = row.get("pending_id", "")
            item_id = identity or f"index-{idx}"
            self.pending_item_selectors[item_id] = "id:" + identity if identity else str(idx)
            state = row.get("pending_state", "held")
            self.pending_tree.insert("", "end", iid=item_id, values=(
                idx,
                row.get("support_count", 0),
                row.get("queue_mode", "") + (f" / {state}" if state != "held" else ""),
                score_text,
                row.get("risk", ""),
                row.get("turns_until_due", ""),
                row.get("category", ""),
                short(row.get("command", ""), 120),
            ))
        retained = [item for item in selected if item in self.pending_item_selectors and item.startswith("pending-")]
        if retained:
            self.pending_tree.selection_set(retained)
        self.update_pending_selection_status()

    def build_pending_candidate_text(self, agent_suggestions, agent_tasks=None, agent_pending_gate=None, agent_pending_insert_dry_run=None):
        agent_suggestions = agent_suggestions or {}
        if not isinstance(agent_suggestions, dict):
            return "No sub-agent suggestion candidate data exported yet."
        agent_tasks = agent_tasks or {}
        if not isinstance(agent_tasks, dict):
            agent_tasks = {}
        agent_pending_gate = agent_pending_gate or {}
        if not isinstance(agent_pending_gate, dict):
            agent_pending_gate = {}
        agent_pending_insert_dry_run = agent_pending_insert_dry_run or {}
        if not isinstance(agent_pending_insert_dry_run, dict):
            agent_pending_insert_dry_run = {}
        summary = agent_suggestions.get("summary", {}) or {}
        task_summary = agent_tasks.get("summary", {}) or {}
        gate_summary = agent_pending_gate.get("summary", {}) or {}
        dry_run_summary = agent_pending_insert_dry_run.get("summary", {}) or {}
        lines = [
            (
                f"audit_rows={summary.get('suggestion_count', 0)} | "
                f"approved={summary.get('approved_suggestions', 0)} | "
                f"rejected={summary.get('rejected_suggestions', 0)} | "
                f"staged={summary.get('staged_pending_candidates', 0)}"
            ),
            (
                f"candidate_staging={summary.get('pending_command_candidate_staging_enabled', False)} | "
                f"provenance_marks={summary.get('context_mark_linked_suggestions', 0)} | "
                f"pending_insertions={summary.get('pending_command_insertions', 0)} | "
                f"insert_enabled={summary.get('pending_command_insertion_enabled', False)} | "
                f"execute={summary.get('command_execution_enabled', False)}"
            ),
            (
                f"task_packets={task_summary.get('task_count', 0)} | "
                f"active={task_summary.get('active_tasks', 0)} | review={task_summary.get('review_tasks', 0)} | "
                f"parent_visible={task_summary.get('parent_visible_tasks', 0)} | "
                f"task_insertions={task_summary.get('pending_command_insertions', 0)} | "
                f"task_execute={task_summary.get('command_execution_enabled', False)}"
            ),
            (
                f"review_links={gate_summary.get('review_links', 0)} | "
                f"gate_ready={gate_summary.get('metadata_ready_rows', 0)} | "
                f"gate_open={gate_summary.get('pending_gate_open_rows', 0)} | "
                f"gate_insert_enabled={gate_summary.get('pending_command_insertion_enabled', False)} | "
                f"gate_execute={gate_summary.get('command_execution_enabled', False)}"
            ),
            (
                f"dry_run_rows={dry_run_summary.get('rows', 0)} | "
                f"contract_ready={dry_run_summary.get('contract_ready_rows', 0)} | "
                f"dry_run_passed={dry_run_summary.get('dry_run_passed_rows', 0)} | "
                f"queue_unchanged={dry_run_summary.get('pending_queue_unchanged', True)} | "
                f"would_insert={dry_run_summary.get('would_insert_rows', 0)} | "
                f"inserted={dry_run_summary.get('pending_command_insertions', 0)} | "
                f"dry_run_insert_enabled={dry_run_summary.get('pending_command_insertion_enabled', False)}"
            ),
        ]
        staged_rows = [
            row for row in (agent_suggestions.get("recent_suggestions", []) or [])
            if isinstance(row, dict) and row.get("pending_candidate_staged")
        ]
        if not staged_rows:
            lines.append("- no staged sub-agent candidates")
        for row in staged_rows[-8:]:
            lines.append(
                f"- {short(row.get('pending_candidate_id', '-') or '-', 64)} | "
                f"agent={short(row.get('agent_id', '-') or '-', 30)} | "
                f"approval={row.get('approval_state', '-')} | policy={row.get('policy_state', '-')} | "
                f"queue_inserted={row.get('pending_queue_inserted', False)}"
            )
            lines.append(f"  command={short(row.get('command', '') or '-', 180)}")
            context_ids = row.get("context_mark_ids", []) or []
            if context_ids:
                lines.append(
                    f"  context_marks={short(', '.join(context_ids), 160)} | "
                    f"provenance_visible={row.get('prompt_ledger_provenance_visible', False)}"
                )
            link_ids = row.get("linked_task_ids", []) or []
            if link_ids:
                lines.append(
                    f"  task_links={short(', '.join(link_ids), 160)} | "
                    f"gate_ready={row.get('pending_gate_metadata_ready', False)}"
                )
        gate_rows = [
            row for row in (agent_pending_gate.get("rows", []) or [])
            if isinstance(row, dict)
        ]
        if gate_rows:
            lines.append("")
            lines.append("Task/suggestion Pending gate review:")
            for row in gate_rows[-8:]:
                gate = row.get("pending_gate_preview", {}) or {}
                lines.append(
                    f"- {short(row.get('review_link_id', '-') or '-', 54)} | "
                    f"task={short(row.get('task_id', '-') or '-', 42)} | "
                    f"suggestion={short(row.get('suggestion_id', '-') or '-', 42)}"
                )
                lines.append(
                    f"  metadata_ready={gate.get('metadata_ready', False)} | "
                    f"gate_open={gate.get('pending_gate_open', False)} | "
                    f"insert_enabled={gate.get('pending_command_insertion_enabled', False)} | "
                    f"execute={gate.get('command_execution_enabled', False)}"
                )
        dry_run_rows = [
            row for row in (agent_pending_insert_dry_run.get("rows", []) or [])
            if isinstance(row, dict)
        ]
        if dry_run_rows:
            lines.append("")
            lines.append("Pending insert checklist / dry-run:")
            for row in dry_run_rows[-8:]:
                lines.append(
                    f"- {short(row.get('dry_run_id', '-') or '-', 54)} | "
                    f"review={short(row.get('review_link_id', '-') or '-', 42)} | "
                    f"ready={row.get('contract_ready', False)} | passed={row.get('dry_run_passed', False)}"
                )
                lines.append(
                    f"  would_insert={row.get('would_insert', False)} | "
                    f"inserted={row.get('pending_command_inserted', False)} | "
                    f"queue_index={row.get('pending_queue_entry_index', 0) or '-'} | "
                    f"queue_before={row.get('pending_queue_count_before', 0)} | "
                    f"queue_after={row.get('pending_queue_count_after', 0)} | "
                    f"insert_enabled={row.get('pending_command_insertion_enabled', False)}"
                )
                if row.get("would_insert"):
                    lines.append(f"  insert_command={short(row.get('future_insert_command_shape', '') or '-', 180)}")
        task_rows = [
            row for row in (agent_tasks.get("recent_tasks", []) or [])
            if isinstance(row, dict) and row.get("status") in {"active", "review", "blocked"}
        ]
        if task_rows:
            lines.append("")
            lines.append("Sub-agent task packets (metadata only):")
            for row in task_rows[-8:]:
                lines.append(
                    f"- {short(row.get('task_id', '-') or '-', 64)} | "
                    f"agent={short(row.get('agent_id', '-') or '-', 30)} | status={row.get('status', '-')} | "
                    f"visible={row.get('prompt_ledger_visible', False)} | execute={row.get('command_execution_enabled', False)}"
                )
                lines.append(f"  title={short(row.get('title', '') or '-', 180)}")
        return "\n".join(lines)

    def get_pending_scope_summary(self):
        total = len(getattr(self, "pending_rows", []) or [])
        try:
            visible_items = list(self.pending_tree.get_children())
            selection = list(self.pending_tree.selection())
            selected_indexes = [str(self.pending_tree.item(item, "values")[0]) for item in selection]
        except Exception:
            visible_items = []
            selected_indexes = []
        risk_filter = (getattr(self, "pending_risk_var", tk.StringVar(value="all")).get() or "all").strip()
        category_filter = (getattr(self, "pending_category_var", tk.StringVar(value="all")).get() or "all").strip()
        search_filter = (getattr(self, "pending_search_var", tk.StringVar(value="")).get() or "").strip()
        filter_parts = []
        if risk_filter and risk_filter.lower() != "all":
            filter_parts.append(f"risk={risk_filter}")
        if category_filter and category_filter.lower() != "all":
            filter_parts.append(f"category={category_filter}")
        if search_filter:
            filter_parts.append(f"search={short(search_filter, 24)}")
        return {
            "total": total,
            "visible": len(visible_items),
            "selected": len(selected_indexes),
            "selected_indexes": selected_indexes,
            "filter_text": ", ".join(filter_parts) if filter_parts else "no filter",
        }

    def update_pending_selection_status(self, _event=None):
        if not hasattr(self, "pending_selection_status_var") or not hasattr(self, "pending_tree"):
            return
        scope = self.get_pending_scope_summary()
        total = scope["total"]
        visible_count = scope["visible"]
        selected_indexes = scope["selected_indexes"]
        filter_text = scope["filter_text"]
        if selected_indexes:
            selected_text = ", ".join(selected_indexes[:8])
            if len(selected_indexes) > 8:
                selected_text += f", +{len(selected_indexes) - 8} more"
            message = (
                f"{len(selected_indexes)} selected ({selected_text}) | visible {visible_count}/{total} | {filter_text}. "
                "Approve/Clear Selection affects only selected visible rows."
            )
        elif total:
            message = (
                f"0 selected | visible {visible_count}/{total} | {filter_text}. "
                "Select rows before using selection actions, or use risk/all buttons deliberately."
            )
        else:
            message = "No pending commands loaded."
        self.pending_selection_status_var.set(message)

    def _refresh_thumbnail_region(self, _event=None):
        try:
            self.thumbnail_canvas.configure(scrollregion=self.thumbnail_canvas.bbox("all"))
        except Exception:
            pass

    def _resize_thumbnail_window(self, event=None):
        if event is None:
            return
        try:
            self.thumbnail_canvas.itemconfigure(self.thumbnail_window, height=event.height)
        except Exception:
            pass

    def _refresh_memory_thumbnail_region(self, _event=None):
        try:
            self.memory_thumbnail_canvas.configure(scrollregion=self.memory_thumbnail_canvas.bbox("all"))
        except Exception:
            pass

    def _resize_memory_thumbnail_window(self, event=None):
        if event is None:
            return
        try:
            self.memory_thumbnail_canvas.itemconfigure(self.memory_thumbnail_window, height=event.height)
        except Exception:
            pass

    def set_screenshot_index(self, index):
        if index < 0 or index >= len(self.screenshot_files):
            return
        self.follow_latest_var.set(False)
        self.screenshot_index = index
        self.render_screenshot()

    def set_image_memory_index(self, index):
        if index < 0 or index >= len(self.image_memory_rows):
            return
        self.image_memory_index = index
        self.render_image_memory()

    def step_screenshot(self, delta):
        if not self.screenshot_files:
            return
        self.follow_latest_var.set(False)
        self.screenshot_index = max(0, min(len(self.screenshot_files) - 1, self.screenshot_index + delta))
        self.render_screenshot()

    def jump_to_latest_screenshot(self):
        if not self.screenshot_files:
            return
        self.follow_latest_var.set(True)
        self.screenshot_index = self.find_latest_renderable_index(self.screenshot_files)
        self.render_screenshot()

    def pause_screenshot_follow_latest(self):
        self.follow_latest_var.set(False)
        self._last_screenshot_render_signature = None
        self.render_screenshot()

    def step_image_memory(self, delta):
        if not self.image_memory_rows:
            return
        self.image_memory_index = max(0, min(len(self.image_memory_rows) - 1, self.image_memory_index + delta))
        self.render_image_memory()

    def jump_to_latest_image_memory(self):
        if not self.image_memory_rows:
            return
        self.image_memory_index = len(self.image_memory_rows) - 1
        self.render_image_memory()

    def _refresh_runtime_status_strip(self, state):
        snapshot = decorate_state_processes(state)
        processes = snapshot.get("processes", {}) or {}
        runtime = processes.get("runtime", {}) or {}
        control_panel = processes.get("control_panel", {}) or {}
        modes = snapshot.get("modes", {}) or {}
        runtime_active = bool(runtime.get("active", False))
        client_active = bool(modes.get("live", False))
        runtime_pid = int(runtime.get("pid") or 0)
        control_panel_pid = int(control_panel.get("pid") or 0)
        freshness_text = build_state_freshness_text(snapshot)

        self.runtime_status_var.set(f"Runtime: {'Active' if runtime_active else 'Inactive'}")
        self.runtime_client_var.set(f"Client: {'Active' if client_active else 'Inactive'}")
        if runtime_active:
            control_panel_text = "active" if bool(control_panel.get("active", False)) else "inactive"
            note = f"Runtime PID {runtime_pid or '-'} | Control Panel {control_panel_text}"
        else:
            note = "Aurora runtime is inactive."
        if control_panel_pid > 0:
            note += f" | Panel PID {control_panel_pid}"
        note += f" | {freshness_text}"
        self.runtime_orb_note_var.set(note)
        self.runtime_mode_spec_var.set(build_runtime_mode_spec(snapshot))
        self.runtime_model_spec_var.set(build_runtime_model_spec(snapshot))
        activation_plan = get_runtime_activation_plan(snapshot)
        if runtime_active and client_active:
            hint = "Double-click the orb to deactivate Aurora2."
        else:
            hint = f"Double-click the orb to activate with {activation_plan['label']}."
        self.runtime_activation_hint_var.set(hint)
        work = (snapshot.get("work", {}) or {}).get("model_io", {}) or {}
        active_model = str(work.get("requested_model") or "unknown")
        last_model = str((snapshot.get("prompt_materials") or {}).get("model") or "unknown")
        request_label = f"Active request: {active_model}" if work.get("active_network_calls") else f"Last prepared: {last_model}"
        self.compact_status_var.set(
            f"{'Inference enabled' if client_active else 'Inference paused'} · "
            f"Primary: {(snapshot.get('models', {}) or {}).get('text', 'model unknown')} · "
            f"{(snapshot.get('models', {}) or {}).get('reasoning_effort', 'effort unknown')} effort · "
            f"{request_label} · {work.get('state', 'unknown')} · {freshness_text.split('|')[0].strip()} · Model choices ↗"
        )
        primary = (snapshot.get("models", {}) or {}).get("text", "unknown model")
        effort = (snapshot.get("models", {}) or {}).get("reasoning_effort", "unknown")
        self.header_status_var.set(
            f"{'Inference enabled' if client_active else 'Inference paused'} · {primary} · {effort} effort"
            + (f"\nActive request: {active_model}" if work.get("active_network_calls") else "")
            + f" · {freshness_text.split('|')[0].strip()} · Models ↗"
        )
        self.runtime_activate_button.configure(text="Enable inference" if runtime_active else "Start runtime")
        self.runtime_activate_button.state(["disabled"] if runtime_active and client_active else ["!disabled"])
        self.runtime_cancel_button.state(["!disabled"] if runtime_active else ["disabled"])

        if runtime_active and client_active:
            self._start_runtime_orb_animation()
        else:
            self._stop_runtime_orb_animation()

        if self.runtime_deactive_button is not None:
            self.runtime_deactive_button.state(["!disabled"] if runtime_active and client_active else ["disabled"])
        if self.runtime_shutdown_button is not None:
            self.runtime_shutdown_button.state(["!disabled"] if runtime_active else ["disabled"])
        if self.runtime_orb_button is not None:
            if runtime_active and client_active:
                self.runtime_orb_button.state(["!disabled"])
            elif runtime_active:
                self.runtime_orb_button.state(["!disabled"])
            else:
                self.runtime_orb_button.state(["!disabled"])

    def refresh_loop(self):
        if self._closing:
            return
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        started = time.perf_counter()
        try:
            self.refresh_now()
        finally:
            self._last_refresh_perf["last_loop_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            if not self._closing:
                self._refresh_after_id = self.after(REFRESH_INTERVAL_MS, self.refresh_loop)

    def refresh_now(self):
        if self._closing:
            return False
        started = time.perf_counter()
        previous_state = self.state_cache
        state_loaded = False
        signature = self._last_state_signature
        try:
            self._drain_settings_transaction_results()
            if STATE_PATH.exists():
                stat = STATE_PATH.stat()
                candidate_signature = (stat.st_mtime_ns, stat.st_size)
                if candidate_signature != self._last_state_signature:
                    candidate = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
                    if not isinstance(candidate, dict):
                        raise ValueError("Runtime snapshot must be a JSON object")
                    self.state_cache = decorate_state_processes(candidate)
                    signature = candidate_signature
                    state_loaded = True
            elif not self.state_cache:
                self.state_cache = decorate_state_processes({})
                state_loaded = True
            if self.state_cache:
                self.state_cache = decorate_state_processes(self.state_cache)
                self.render_state()
            changed = sum(variable.get() != self._settings_observed_values.get(key)
                          for key, variable in self._settings_variables.items())
            self.settings_edit_status_var.set(
                f"{changed} local edit(s) preserved. Apply when ready, or Reload observed."
                if changed else "Values follow the runtime until edited."
            )
            self.render_logs(active_tab=self._get_active_tab_name())
            self._last_state_signature = signature
            if signature:
                self.last_state_mtime = signature[0] / 1_000_000_000
            had_error = bool(self._last_refresh_perf.get("consecutive_errors"))
            self._last_refresh_perf.update({"consecutive_errors": 0, "last_error": "",
                "state_loaded": state_loaded, "state_mtime": self.last_state_mtime,
                "last_success_at": time.time()})
            if had_error:
                self._last_refresh_perf["recoveries"] = self._last_refresh_perf.get("recoveries", 0) + 1
            self.refresh_health_var.set("Refresh recovered; live updates resumed." if had_error else "")
            return True
        except Exception as error:
            self.state_cache = previous_state
            errors = self._last_refresh_perf.get("consecutive_errors", 0) + 1
            self._last_refresh_perf.update({"consecutive_errors": errors, "last_error": str(error)[:180]})
            self.refresh_health_var.set(f"Refresh delayed; displayed data may be stale. Retrying automatically. {str(error)[:130]}")
            return False
        finally:
            self._last_refresh_perf["last_refresh_ms"] = round((time.perf_counter() - started) * 1000.0, 1)

    def _sync_setting_var(self, variable, observed_value):
        key = str(variable)
        self._settings_variables[key] = variable
        old_observed = self._settings_observed_values.get(key)
        if key not in self._settings_observed_values or variable.get() == old_observed:
            variable.set(observed_value)
        self._settings_observed_values[key] = observed_value

    def reload_observed_settings(self):
        self._settings_observed_values.clear()
        self.refresh_now()

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        for handle in (self._refresh_after_id, self._sash_after_id):
            if handle is not None:
                self.after_cancel(handle)
        self._refresh_after_id = self._sash_after_id = None
        self._remember_sash()
        self.ui_preferences.update({"geometry": self._normal_geometry, "maximized": self.state() == "zoomed",
            "settings_mode": self.settings_mode, "active_view": self._get_active_tab_name(),
            "banner_auto_scroll": self.banner_auto_scroll_var.get(),
            "restore_last_view": self.restore_last_view_var.get(),
            "portal_motion": self.portal_motion_var.get()})
        self.ui_preferences.update({"conversation_time": self.conversation_time_var.get(),
            "conversation_model": self.conversation_model_var.get(), "conversation_edits": self.conversation_edits_var.get()})
        try:
            save_layout_preferences(LAYOUT_PATH, self.ui_preferences)
        except OSError as error:
            print(f"Could not save panel layout: {error}", file=sys.stderr)
        self._cancel_runtime_orb_click()
        self._stop_runtime_orb_animation()
        if getattr(self, "_portal_after", None) is not None:
            self.after_cancel(self._portal_after)
            self._portal_after = None
        remove_pid_file(CONTROL_PANEL_PID_PATH, expected_pid=os.getpid())
        self.destroy()

    def refresh_overview_summary(self, state):
        summary_vars = getattr(self, "overview_summary_vars", None)
        if not summary_vars:
            return

        snapshot = decorate_state_processes(state or {})
        processes = snapshot.get("processes", {}) or {}
        runtime = processes.get("runtime", {}) or {}
        modes = snapshot.get("modes", {}) or {}
        scheduler = snapshot.get("scheduler", {}) or {}
        planning = snapshot.get("planning", {}) or {}
        command_drip = snapshot.get("command_drip", {}) or {}
        episodic = snapshot.get("episodic_memory", {}) or {}
        rehydration = snapshot.get("rehydration", {}) or {}
        rehydration_explain = rehydration.get("explainability", {}) or {}
        monitors = snapshot.get("monitors", {}) or {}
        gameplay = snapshot.get("gameplay", {}) or {}
        state_export = snapshot.get("state_export", {}) or {}
        queue_bridge = snapshot.get("queue_bridge", {}) or {}
        mutation_admission = snapshot.get("mutation_admission", {}) or {}
        security = snapshot.get("security", {}) or {}
        harness = snapshot.get("live_visual_harness", {}) or {}
        responses_shadow = snapshot.get("responses_shadow_transport", {}) or {}
        responses_summary = responses_shadow.get("summary", {}) or {}
        runtime_health = snapshot.get("runtime_health", {}) or {}
        health_rows = [row for row in (runtime_health.get("rows", []) or []) if isinstance(row, dict)]
        health_actions = runtime_health.get("next_actions", []) or []
        image_cost_posture = snapshot.get("image_cost_posture", {}) or {}
        image_cost_counts = image_cost_posture.get("counts", {}) or {}
        image_cost_limits = image_cost_posture.get("limits", {}) or {}
        image_cost_actions = image_cost_posture.get("next_actions", []) or []
        operator_risk = snapshot.get("operator_risk_summary", {}) or {}
        operator_risk_counts = operator_risk.get("counts", {}) or {}
        operator_risk_actions = operator_risk.get("next_actions", []) or []
        prompt_inclusion = snapshot.get("prompt_inclusion_readiness", {}) or {}
        prompt_inclusion_counts = prompt_inclusion.get("counts", {}) or {}
        prompt_inclusion_actions = prompt_inclusion.get("next_actions", []) or []
        prompt_preview = snapshot.get("prompt_inclusion_preview", {}) or {}
        prompt_preview_counts = prompt_preview.get("counts", {}) or {}
        prompt_preview_actions = prompt_preview.get("next_actions", []) or []
        prompt_rehearsal = snapshot.get("prompt_inclusion_rehearsal", {}) or {}
        prompt_rehearsal_counts = prompt_rehearsal.get("counts", {}) or {}
        prompt_activation = snapshot.get("prompt_inclusion_activation_checklist", {}) or {}
        prompt_activation_counts = prompt_activation.get("counts", {}) or {}
        prompt_activation_state = snapshot.get("prompt_inclusion_activation", {}) or {}
        prompt_activation_inner = prompt_activation_state.get("activation", {}) or {}
        prompt_activation_state_counts = prompt_activation_state.get("counts", {}) or {}
        prompt_closure = snapshot.get("prompt_inclusion_closure", {}) or {}
        prompt_closure_counts = prompt_closure.get("status_counts", {}) or {}
        checkpoint = snapshot.get("window_18_21_checkpoint_readiness", {}) or {}
        checkpoint_counts = checkpoint.get("counts", {}) or {}
        checkpoint_status_counts = checkpoint.get("status_counts", {}) or {}
        checkpoint_commit = str(checkpoint.get("checkpoint_commit", "") or "").strip()
        portal_intake = snapshot.get("portal_companion_intake", {}) or {}
        portal_intake_counts = portal_intake.get("counts", {}) or {}
        portal_intake_status_counts = portal_intake.get("status_counts", {}) or {}
        portal_intake_gate_counts = portal_intake.get("stage_gate_counts", {}) or {}
        portal_intake_actions = portal_intake.get("next_actions", []) or []

        runtime_active = bool(runtime.get("active", False))
        client_active = bool(modes.get("live", False))
        auth_summary = short(snapshot.get("auth_summary", ""), 72) or f"auth={modes.get('auth', '-')}"
        freshness_text = build_state_freshness_text(snapshot)
        runtime_lines = [
            f"Runtime {'active' if runtime_active else 'inactive'} | Client {'on' if client_active else 'off'}",
            f"Exec {modes.get('execution', '-')} | Action {modes.get('action', '-')}",
            f"Health {format_monitor_summary(monitors)}",
            f"Export {format_state_export_monitor_summary(monitors, state_export)}",
            f"Game {format_gameplay_monitor_summary(monitors, gameplay)}",
            freshness_text,
            auth_summary,
        ]

        pending_count = len(snapshot.get("pending_commands", []) or [])
        current_turn = command_drip.get("current_turn", 0)
        scheduler_label = f"{scheduler.get('profile', 'balanced')} / {scheduler.get('mode', 'hybrid')}"
        queue_mode = planning.get('pending_queue_mode', command_drip.get('pending_queue_mode', 'normal'))
        next_action_cue = build_queue_next_action_cue(snapshot)
        queue_lines = [
            f"Pending {pending_count} | Queue {queue_mode}",
            next_action_cue,
            short(format_pending_queue_mode_semantics(queue_mode), 72),
            f"Bridge {format_queue_bridge_monitor_summary(monitors, queue_bridge)}",
            f"Mutations {format_mutation_admission_summary(mutation_admission)}",
            f"Turn {current_turn} | Scheduler {scheduler_label}",
            f"Last wake {scheduler.get('last_wake_reason', '-') or '-'}",
        ]

        planning_mode = episodic.get("planning_assist_mode", "review_critique")
        memory_lines = [
            f"Episodic {'on' if episodic.get('enabled', True) else 'off'} | Snapshots {episodic.get('snapshot_count', 0)}",
            f"Planning {planning_mode} | Items {episodic.get('planning_assist_k', 2)} | Cooldown {episodic.get('planning_assist_cooldown_turns', 12)}",
            f"Rehydration {short(rehydration.get('automatic_status', '-') or '-', 78)}",
            f"Outcome {rehydration_explain.get('last_outcome', '-') or '-'} | Sources {format_source_mix(rehydration_explain.get('last_query_source_mix', episodic.get('planning_last_query_source_mix', [])), limit=4, item_limit=22)}",
            f"Backend {episodic.get('embeddings_mode', 'auto')} | Last retrieval {episodic.get('last_retrieval_count', 0)} | Security {'locked' if security.get('has_passcode') and not security.get('authorized', True) else 'open'}",
        ]

        browser_lines = ["Bridge state not found."]
        browser_state = read_json(BROWSER_BRIDGE_STATE_PATH, {}) if BROWSER_BRIDGE_STATE_PATH.exists() else {}
        browser = browser_state.get("browser", {}) if isinstance(browser_state, dict) else {}
        if browser:
            page = browser.get("page", {}) or {}
            aurora = browser.get("aurora", {}) or {}
            browser_lines = [
                f"{browser.get('status', 'unknown')} | {short(page.get('title', ''), 34) or '-'}",
                f"Aurora {'online' if aurora.get('online', False) else 'offline'} | Runtime {'on' if aurora.get('runtimeActive', False) else 'off'}",
                f"Updated {short(browser_state.get('updatedAt', '-'), 34)}",
            ]

        harness_posture = harness.get("current_posture", {}) or {}
        harness_contract = harness.get("expected_observation_contract", {}) or {}
        harness_readiness = harness.get("readiness", {}) or {}
        harness_warnings = harness_readiness.get("warnings", []) or []
        harness_rehearsal = snapshot.get("live_visual_harness_rehearsal", {}) or {}
        harness_probe = snapshot.get("live_visual_harness_probe", {}) or {}
        harness_lines = [
            f"{harness.get('status', 'not exported')} | {harness.get('mode', '-') or '-'}",
            f"Offline {'ready' if harness_readiness.get('ready_for_offline_rehearsal', False) else 'not ready'} | Live {'ready' if harness_readiness.get('ready_for_live', False) else 'blocked'}",
            f"Rehearsal {harness_rehearsal.get('status', 'not run') or 'not run'}",
            f"Probe {harness_probe.get('status', 'not armed') or 'not armed'}",
            f"Live {'on' if harness_posture.get('live_mode', False) else 'off'} | Action {harness_posture.get('action_mode', '-') or '-'}",
            f"Newest {short(Path(str(harness_contract.get('newest_image_path', '') or '')).name or '-', 52)}",
            f"Warnings {len(harness_warnings)}",
        ]
        responses_closure = responses_shadow.get("shadow_closure_readiness", {}) or {}
        closure_counts = responses_closure.get("status_counts", {}) or {}
        responses_lines = [
            f"{responses_shadow.get('status', 'not exported')} | {responses_shadow.get('mode', '-') or '-'}",
            f"Current {responses_summary.get('current_transport', '-') or '-'}",
            f"Shadow {responses_summary.get('shadow_transport', '-') or '-'}",
            f"API {'on' if responses_summary.get('responses_api_call_enabled', False) else 'off'} | Builder {'on' if responses_summary.get('shadow_request_builder_enabled', False) else 'off'}",
            f"Migration {'on' if responses_summary.get('default_migration_enabled', False) else 'off'} | Tools {'on' if responses_summary.get('tool_calls_enabled', False) else 'off'}",
            f"Closure {responses_summary.get('closure_readiness_status', responses_closure.get('status', '-')) or '-'} | Ready {'yes' if responses_summary.get('closure_ready_for_window_close', responses_closure.get('ready_for_window_close', False)) else 'no'}",
            f"Closure ok {closure_counts.get('ok', responses_summary.get('closure_ok_count', 0))} | watch {closure_counts.get('watch', responses_summary.get('closure_watch_count', 0))} | blocked {closure_counts.get('blocked', responses_summary.get('closure_blocked_count', 0))}",
            f"Probe {responses_summary.get('shadow_live_probe_status', '-') or '-'} | {responses_summary.get('shadow_live_probe_model', '-') or '-'}",
            f"Probe send {'on' if responses_summary.get('shadow_live_probe_send_enabled', False) else 'off'} | API {'on' if responses_summary.get('shadow_live_probe_api_call_enabled', False) else 'off'}",
            f"Payload rows {responses_summary.get('shadow_payload_ledger_rows_used', 0)} | Inputs {responses_summary.get('shadow_payload_input_messages', 0)}",
            f"Tokens ~{responses_summary.get('shadow_estimated_input_tokens', 0)} | Cost ~{responses_summary.get('shadow_estimated_total_usd', '-')}",
            f"State risk {responses_summary.get('shadow_state_risk', '-') or '-'}",
            f"Rows {responses_summary.get('comparison_contract_rows', 0)} | Blockers {responses_summary.get('blocker_rows', 0)}",
        ]
        health_lines = [
            f"{runtime_health.get('status', 'not exported')} | {runtime_health.get('summary', '-') or '-'}",
            f"Schema {runtime_health.get('schema_version', '-') or '-'} | {runtime_health.get('window', '-') or '-'} {runtime_health.get('slice', '-') or '-'}",
        ]
        for row in health_rows[:5]:
            health_lines.append(
                f"{row.get('label', row.get('key', 'row'))}: {row.get('status', 'watch')} | {short(row.get('summary', '-') or '-', 82)}"
            )
        if health_actions:
            health_lines.append(f"Next {short(str(health_actions[0]), 96)}")
        image_cost_lines = [
            f"{image_cost_posture.get('status', 'not exported')} | {short(image_cost_posture.get('summary', '-') or '-', 96)}",
            (
                f"Shots {image_cost_counts.get('local_screenshot_count', 0)} | "
                f"Sidecars {image_cost_counts.get('sidecar_count', 0)} | "
                f"Coverage {image_cost_counts.get('sidecar_coverage_percent', 0)}%"
            ),
            (
                f"Backfill max {image_cost_limits.get('image_context_backfill_max_limit', '-')} | "
                f"Search scan {image_cost_limits.get('image_context_search_max_scan', '-')}"
            ),
            f"Next {short(str(image_cost_actions[0]), 96) if image_cost_actions else '-'}",
        ]
        command_risk_row = next(
            (
                row for row in (operator_risk.get("rows", []) or [])
                if isinstance(row, dict) and row.get("key") == "command_insertion_execution"
            ),
            {},
        )
        operator_risk_lines = [
            f"{operator_risk.get('status', 'not exported')} | {short(operator_risk.get('summary', '-') or '-', 96)}",
            (
                f"Cost {operator_risk_counts.get('cost_risk', '-')} | "
                f"Action {operator_risk_counts.get('action_risk', '-')} | "
                f"Context {operator_risk_counts.get('context_risk', '-')}"
            ),
            (
                f"Commands {operator_risk_counts.get('command_risk', '-')} | "
                f"Transport {operator_risk_counts.get('transport_risk', '-')} | "
                f"Access {operator_risk_counts.get('access_risk', '-')}"
            ),
            (
                f"Pending {operator_risk_counts.get('pending_commands', 0)} | "
                f"Agent candidates {operator_risk_counts.get('agent_suggestion_candidates', 0)} | "
                f"Staged {operator_risk_counts.get('agent_suggestion_staged_candidates', 0)}"
            ),
            f"Command gate {short(command_risk_row.get('detail', '-') or '-', 96)}",
            f"Next {short(str(operator_risk_actions[0]), 96) if operator_risk_actions else '-'}",
        ]
        prompt_inclusion_lines = [
            f"{prompt_inclusion.get('status', 'not exported')} | {short(prompt_inclusion.get('summary', '-') or '-', 96)}",
            (
                f"Activation {'on' if prompt_inclusion.get('activation_enabled', False) else 'off'} | "
                f"Review {'ready' if prompt_inclusion.get('ready_for_operator_review', False) else 'blocked'} | "
                f"Flags {prompt_inclusion_counts.get('hard_guardrail_flags', 0)}"
            ),
            (
                f"Pins {prompt_inclusion_counts.get('approved_prompt_pin_candidates', 0)} | "
                f"Drops {prompt_inclusion_counts.get('approved_do_not_include_candidates', 0)} | "
                f"Marks {prompt_inclusion_counts.get('active_context_marks', 0)}"
            ),
            (
                f"History writes {prompt_inclusion_counts.get('enabled_history_write_paths', 0)} | "
                f"Agent staged {prompt_inclusion_counts.get('staged_agent_suggestions', 0)}"
            ),
            (
                f"Preview {prompt_preview.get('status', 'not exported')} | "
                f"Add {prompt_preview_counts.get('proposed_additions', 0)} | "
                f"Omit {prompt_preview_counts.get('proposed_omissions', 0)} | "
                f"Send {'on' if prompt_preview.get('send_enabled', False) else 'off'}"
            ),
            (
                f"Rehearsal {prompt_rehearsal.get('status', 'not run')} | "
                f"Add {prompt_rehearsal_counts.get('rehearsal_additions', 0)} | "
                f"Omit {prompt_rehearsal_counts.get('rehearsal_omissions', 0)} | "
                f"Active after {prompt_rehearsal_counts.get('active_rehearsal_marks_after', 0)}"
            ),
            (
                f"Activation Review {prompt_activation.get('status', 'not exported')} | "
                f"Checks {prompt_activation_counts.get('required_checks_passed', 0)}/{prompt_activation_counts.get('required_checks', 0)} | "
                f"Available {'yes' if prompt_activation.get('activation_control_available', False) else 'no'}"
            ),
            (
                f"Activation State {prompt_activation_state.get('status', 'off')} | "
                f"Enabled {'yes' if prompt_activation_inner.get('enabled', False) else 'no'} | "
                f"Proof {prompt_activation_inner.get('offline_proof_status', 'not_run')}"
            ),
            (
                f"Active pins {prompt_activation_state_counts.get('active_prompt_pins', 0)} | "
                f"Active omissions {prompt_activation_state_counts.get('active_omissions', 0)} | "
                f"Omitted rows {prompt_activation_state_counts.get('omitted_recent_history_rows', 0)}"
            ),
            (
                f"Closure {prompt_closure.get('status', 'not exported')} | "
                f"Ready {'yes' if prompt_closure.get('ready_for_window_close', False) else 'no'} | "
                f"warn {prompt_closure_counts.get('warning', 0)} | blocked {prompt_closure_counts.get('blocked', 0)}"
            ),
            f"Next {short(str(prompt_inclusion_actions[0]), 96) if prompt_inclusion_actions else '-'}",
            f"Preview next {short(str(prompt_preview_actions[0]), 96) if prompt_preview_actions else '-'}",
        ]
        checkpoint_lines = [
            f"{checkpoint.get('status', 'not exported')} | {short(checkpoint.get('summary', '-') or '-', 96)}",
            (
                f"Ready {'yes' if checkpoint.get('checkpoint_ready', checkpoint.get('ready_for_checkpoint', checkpoint.get('ready_for_checkpoint_when_authorized', False))) else 'no'} | "
                f"Auth required {'yes' if checkpoint.get('explicit_authorization_required', True) else 'no'} | "
                f"Checkpointed {'yes' if checkpoint.get('stage_commit_performed', False) else 'no'}"
            ),
            f"Commit {short(checkpoint_commit or '-', 16)} | Message {short(checkpoint.get('checkpoint_message', checkpoint.get('suggested_checkpoint_message', '-')), 82)}",
            (
                f"Prompt {checkpoint_counts.get('prompt_inclusion_ready', False)} | "
                f"Agent {checkpoint_counts.get('agent_helper_ready', False)} | "
                f"Companion {checkpoint_counts.get('companion_contract_ready', False)}"
            ),
            (
                f"Pending {checkpoint_counts.get('pending_queue_total', 0)} | "
                f"Live {'on' if checkpoint_counts.get('live_mode', False) else 'off'} | "
                f"Prompt activation {'on' if checkpoint_counts.get('prompt_activation_enabled', False) else 'off'}"
            ),
            (
                f"Warnings {checkpoint_status_counts.get('warning', 0)} | "
                f"Blocked {checkpoint_status_counts.get('blocked', 0)} | "
                f"Responses migration {'on' if checkpoint_counts.get('companion_responses_migration_enabled', False) else 'off'}"
            ),
        ]
        portal_intake_lines = [
            f"{portal_intake.get('status', 'not exported')} | {short(portal_intake.get('summary', '-') or '-', 96)}",
            (
                f"Mirror {'yes' if portal_intake.get('handoff_mirror_exists', False) else 'no'} | "
                f"Routes {portal_intake_counts.get('routes', 0)} | "
                f"Heavy {portal_intake_counts.get('heavy_routes', 0)} | "
                f"Copy {portal_intake_counts.get('operator_copy_packets', 0)} | "
                f"Drafts {portal_intake_counts.get('receipt_draft_templates', 0)} | "
                f"Review {portal_intake_counts.get('readiness_review_packets', 0)} | "
                f"Registry {portal_intake_counts.get('envelope_registry_rows', 0)} | "
                f"Audit {portal_intake_counts.get('acceptance_audit_rows', 0)} | "
                f"Docket {portal_intake_counts.get('promotion_evidence_rows', 0)} | "
                f"Handoffs {portal_intake_counts.get('external_handoff_packets', 0)} | "
                f"Proof {portal_intake_counts.get('local_proof_rows', 0)}"
            ),
            (
                f"HTTP {'on' if portal_intake_counts.get('portal_http_calls_enabled', False) else 'off'} | "
                f"CLI {'on' if portal_intake_counts.get('portal_cli_calls_enabled', False) else 'off'} | "
                f"Polling {'on' if portal_intake_counts.get('polling_enabled', False) else 'off'} | "
                f"Writer {'on' if portal_intake_counts.get('receipt_writer_enabled', False) else 'off'}"
            ),
            (
                f"Rows ok {portal_intake_status_counts.get('ok', 0)} | "
                f"watch {portal_intake_status_counts.get('watch', 0)} | "
                f"blocked {portal_intake_status_counts.get('blocked', 0)}"
            ),
            (
                f"Gates ok {portal_intake_gate_counts.get('ok', 0)} | "
                f"watch {portal_intake_gate_counts.get('watch', 0)} | "
                f"blocked {portal_intake_gate_counts.get('blocked', 0)}"
            ),
            (
                f"Live reads {'ready' if portal_intake.get('ready_for_live_portal_reads', False) else 'parked'} | "
                f"Proof {'ready' if portal_intake.get('ready_for_cross_client_proof', False) else 'parked'} | "
                f"Receipts {'ready' if portal_intake.get('ready_for_receipt_submission', False) else 'parked'} | "
                f"Mutation {'ready' if portal_intake.get('ready_for_mutation_gates', False) else 'parked'}"
            ),
            (
                f"Audit {'ready' if portal_intake.get('ready_for_acceptance_audit', False) else 'waiting'} | "
                f"proved {portal_intake_counts.get('acceptance_proved', 0)} | "
                f"waiting {portal_intake_counts.get('acceptance_waiting', 0)} | "
                f"missing {portal_intake_counts.get('acceptance_missing', 0)} | "
                f"blocked {portal_intake_counts.get('acceptance_blocked', 0)}"
            ),
            (
                f"Docket {'ready' if portal_intake.get('ready_for_promotion_evidence_review', False) else 'waiting'} | "
                f"proved {portal_intake_counts.get('promotion_proved', 0)} | "
                f"waiting {portal_intake_counts.get('promotion_waiting', 0)} | "
                f"missing {portal_intake_counts.get('promotion_missing', 0)} | "
                f"blocked {portal_intake_counts.get('promotion_blocked', 0)}"
            ),
            (
                f"Handoffs {'ready' if portal_intake.get('ready_for_external_handoff_review', False) else 'waiting'} | "
                f"ready {portal_intake_counts.get('handoff_ready_to_copy', 0)} | "
                f"waiting {portal_intake_counts.get('handoff_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('handoff_blocked', 0)} | "
                f"submit {'on' if portal_intake.get('external_handoff_submit_enabled', False) else 'off'}"
            ),
            (
                f"Proof {'ready' if portal_intake.get('ready_for_local_proof_review', False) else 'waiting'} | "
                f"validated {portal_intake_counts.get('local_proof_validated', 0)} | "
                f"ready {portal_intake_counts.get('local_proof_ready_for_validation', 0)} | "
                f"watch {portal_intake_counts.get('local_proof_watch', 0)} | "
                f"current recorded {'yes' if portal_intake.get('current_slice_validation_recorded', False) else 'no'}"
            ),
            (
                f"Report {'ready' if portal_intake.get('ready_for_operator_report_review', False) else 'waiting'} | "
                f"ready {portal_intake_counts.get('operator_report_ready_to_copy', 0)} | "
                f"waiting {portal_intake_counts.get('operator_report_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('operator_report_blocked', 0)}"
            ),
            (
                f"Unblockers {'ready' if portal_intake.get('ready_for_unblocker_review', False) else 'waiting'} | "
                f"proved {portal_intake_counts.get('unblocker_proved', 0)} | "
                f"waiting {portal_intake_counts.get('unblocker_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('unblocker_blocked', 0)}"
            ),
            (
                f"Waitlist {'ready' if portal_intake.get('ready_for_upstream_waitlist_review', False) else 'waiting'} | "
                f"ready {portal_intake_counts.get('waitlist_ready_to_copy', 0)} | "
                f"waiting {portal_intake_counts.get('waitlist_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('waitlist_blocked', 0)}"
            ),
            (
                f"Parking {'ready' if portal_intake.get('ready_for_parking_review', False) else 'waiting'} | "
                f"ready {portal_intake_counts.get('parking_ready_to_copy', 0)} | "
                f"waiting {portal_intake_counts.get('parking_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('parking_blocked', 0)}"
            ),
            (
                f"Closure {'ready' if portal_intake.get('ready_for_parked_closure_review', False) else 'waiting'} | "
                f"proved {portal_intake_counts.get('closure_proved', 0)} | "
                f"waiting {portal_intake_counts.get('closure_waiting', 0)} | "
                f"blocked {portal_intake_counts.get('closure_blocked', 0)}"
            ),
            f"Perf {short(portal_intake.get('performance_note', '-') or '-', 96)}",
            f"Next {short(str(portal_intake_actions[0]), 96) if portal_intake_actions else '-'}",
        ]

        values = {
            "runtime": "\n".join(runtime_lines),
            "queue": "\n".join(queue_lines),
            "memory": "\n".join(memory_lines),
            "browser": "\n".join(browser_lines),
            "harness": "\n".join(harness_lines),
            "responses": "\n".join(responses_lines),
            "health": "\n".join(health_lines),
            "image_cost": "\n".join(image_cost_lines),
            "operator_risk": "\n".join(operator_risk_lines),
            "prompt_inclusion": "\n".join(prompt_inclusion_lines),
            "checkpoint": "\n".join(checkpoint_lines),
            "portal_intake": "\n".join(portal_intake_lines),
        }
        for key, value in values.items():
            widget_var = summary_vars.get(key)
            if widget_var is not None:
                widget_var.set(value)

    def refresh_workflow_status(self, state):
        workflow_vars = getattr(self, "workflow_status_vars", None)
        if not workflow_vars:
            return

        state = state or {}
        route = state.get("route_state", {}) or {}
        memory_tiers = state.get("memory_tiers", {}) or {}
        episodic = state.get("episodic_memory", {}) or {}
        rehydration = state.get("rehydration", {}) or {}
        rehydration_explain = rehydration.get("explainability", {}) or {}
        command_drip = state.get("command_drip", {}) or {}
        scheduler = state.get("scheduler", {}) or {}
        monitors = state.get("monitors", {}) or {}
        queue_bridge = state.get("queue_bridge", {}) or {}
        mutation_admission = state.get("mutation_admission", {}) or {}
        pending_rows = state.get("pending_commands", []) or []
        image_memory_rows = state.get("image_memory", []) or []
        live_harness = state.get("live_visual_harness", {}) or {}
        responses_shadow = state.get("responses_shadow_transport", {}) or {}
        prompt_ledger = state.get("prompt_context_ledger", {}) or {}
        prompt_summary = prompt_ledger.get("summary", {}) or {}
        context_marks = state.get("context_marks", {}) or {}
        context_summary = context_marks.get("summary", {}) or {}
        prompt_inclusion = state.get("prompt_inclusion_readiness", {}) or {}
        prompt_inclusion_counts = prompt_inclusion.get("counts", {}) or {}
        prompt_preview = state.get("prompt_inclusion_preview", {}) or {}
        prompt_preview_counts = prompt_preview.get("counts", {}) or {}
        prompt_rehearsal = state.get("prompt_inclusion_rehearsal", {}) or {}
        prompt_rehearsal_counts = prompt_rehearsal.get("counts", {}) or {}
        prompt_activation = state.get("prompt_inclusion_activation_checklist", {}) or {}
        prompt_activation_counts = prompt_activation.get("counts", {}) or {}
        prompt_activation_state = state.get("prompt_inclusion_activation", {}) or {}
        prompt_activation_inner = prompt_activation_state.get("activation", {}) or {}
        prompt_activation_state_counts = prompt_activation_state.get("counts", {}) or {}
        prompt_closure = state.get("prompt_inclusion_closure", {}) or {}
        prompt_closure_counts = prompt_closure.get("status_counts", {}) or {}
        image_context_index = state.get("image_context_index", {}) or {}
        image_cost_posture = state.get("image_cost_posture", {}) or {}
        operator_risk = state.get("operator_risk_summary", {}) or {}
        portal_intake = state.get("portal_companion_intake", {}) or {}
        portal_intake_counts = portal_intake.get("counts", {}) or {}
        portal_intake_status_counts = portal_intake.get("status_counts", {}) or {}
        portal_intake_gate_counts = portal_intake.get("stage_gate_counts", {}) or {}

        def set_status(key, *parts):
            value_var = workflow_vars.get(key)
            if value_var is not None:
                value_var.set(" | ".join(str(part) for part in parts if str(part)))

        def format_limit(limit):
            return "all" if limit is None else str(limit)

        chat_tail_count = len(state.get("chat_history_tail", []) or [])
        command_tail_count = len(state.get("recent_executed_actions", []) or [])
        state_keys = len(state.keys()) if isinstance(state, dict) else 0
        on_hand_count = len(memory_tiers.get("on_hand", []) or [])
        retrievable_count = len(memory_tiers.get("retrievable", []) or [])
        screenshot_count = len(getattr(self, "screenshot_files", []) or [])
        screenshot_cache_stats = getattr(self, "_screenshot_list_cache_stats", {}) or {}
        thumbnail_cache_stats = getattr(self, "_thumbnail_cache_stats", {}) or {}
        refresh_perf = getattr(self, "_last_refresh_perf", {}) or {}
        screenshot_scan_text = "List not scanned"
        if screenshot_cache_stats:
            if screenshot_cache_stats.get("cache_hit", False):
                screenshot_scan_text = (
                    f"List cache {screenshot_cache_stats.get('cache_age_seconds', screenshot_cache_stats.get('age_seconds', 0))}s"
                )
            else:
                screenshot_scan_text = (
                    f"List scan {screenshot_cache_stats.get('elapsed_ms', 0)}ms/{screenshot_cache_stats.get('scanned', 0)}"
                )
            if screenshot_cache_stats.get("forced_latest_inserted", False):
                screenshot_scan_text += " +latest"
        thumbnail_cache_text = (
            f"Thumbs {thumbnail_cache_stats.get('entries', 0)} cached/"
            f"{thumbnail_cache_stats.get('hits', 0)} hits"
        )
        panel_refresh_text = f"Panel {refresh_perf.get('last_refresh_ms', '-')}ms"
        latest_screenshot_path = Path(state.get("last_screenshot_path", "") or "")
        latest_screenshot_name = latest_screenshot_path.name if str(latest_screenshot_path) else "-"
        selected_screenshot_path = None
        if 0 <= self.screenshot_index < screenshot_count:
            selected_screenshot_path = self.screenshot_files[self.screenshot_index]
        state_image_count = len(image_memory_rows)
        retained_image_count = len(getattr(self, "image_memory_rows", []) or image_memory_rows)
        selected_image_row = None
        if 0 <= self.image_memory_index < len(getattr(self, "image_memory_rows", []) or []):
            selected_image_row = self.image_memory_rows[self.image_memory_index]
        screenshot_viewer_open = self.popout_window is not None and self.popout_window.winfo_exists()
        image_viewer_open = self.memory_popout_window is not None and self.memory_popout_window.winfo_exists()
        chat_head_open = self._is_chat_head_strip_open()
        chat_history_open = self._is_chat_head_history_open()
        pending_scope = self.get_pending_scope_summary() if hasattr(self, "pending_tree") else {
            "total": len(pending_rows),
            "visible": len(pending_rows),
            "selected": 0,
            "filter_text": "no filter",
        }
        if hasattr(self, "chat_head_status_var"):
            self.chat_head_status_var.set(
                f"Strip {'open' if chat_head_open else 'closed'} | "
                f"History {'open' if chat_history_open else 'closed'} | "
                f"Topmost {'on' if self.chat_head_topmost_var.get() else 'off'} | "
                f"Opacity {(self.chat_head_opacity_var.get() or '0.87').strip() or '0.87'}"
            )

        set_status(
            "chat",
            f"Showing {format_limit(self.chat_log_limit)}",
            f"State tail {chat_tail_count}",
            f"Log {'found' if CHAT_LOG_PATH.exists() else 'missing'}",
            f"Echo {'on' if (state.get('modes', {}) or {}).get('chat_log_echo', False) else 'off'}",
            f"Chat head {'open' if chat_head_open else 'closed'}",
        )
        set_status(
            "commands",
            f"Showing {format_limit(self.command_log_limit)}",
            f"Recent executed {command_tail_count}",
            f"Pending {len(pending_rows)}",
            build_queue_next_action_cue(state),
            f"Bridge {format_queue_bridge_monitor_summary(monitors, queue_bridge)}",
            f"Mutations {format_mutation_admission_summary(mutation_admission)}",
            f"Log {'found' if CMD_LOG_PATH.exists() else 'missing'}",
        )
        set_status(
            "memory",
            f"Goals {len(state.get('goals', []) or [])}",
            f"Notes {len(state.get('notes', []) or [])}",
            f"On-hand {on_hand_count}",
            f"Retrievable {retrievable_count}",
            f"Route {route.get('status', 'unknown') or 'unknown'}",
        )
        set_status(
            "episodic",
            f"{'On' if episodic.get('enabled', True) else 'Off'}",
            f"Snapshots {episodic.get('snapshot_count', 0)}",
            f"Backend {episodic.get('embeddings_mode', 'auto')}",
            f"Planning {episodic.get('planning_assist_mode', 'review_critique')}:{episodic.get('planning_assist_k', 2)}",
            f"Cooldown {episodic.get('planning_assist_cooldown_turns', 12)}",
            f"Last retrieval {episodic.get('last_retrieval_count', 0)}",
            f"Last decision {episodic.get('planning_last_decision', '-') or '-'}",
            f"Rehydration {short(rehydration.get('automatic_status', '-') or '-', 70)}",
            f"Outcome {rehydration_explain.get('last_outcome', '-') or '-'}",
        )
        set_status(
            "pending",
            f"Total {pending_scope['total']}",
            f"Visible {pending_scope['visible']}",
            f"Selected {pending_scope['selected']}",
            f"Filter {pending_scope['filter_text']}",
            f"Queue {(state.get('planning', {}) or {}).get('pending_queue_mode', command_drip.get('pending_queue_mode', 'normal'))}",
            "Approve executes; Clear drops",
            build_queue_next_action_cue(state),
            f"Due {queue_bridge.get('due_pending_count', 0)}",
            f"Stale due {queue_bridge.get('stale_due_count', 0)}",
        )
        set_status(
            "command_drip",
            f"Turn {command_drip.get('current_turn', 0)}",
            f"Turns {len(command_drip.get('turns', []) or [])}",
            f"Retention {command_drip.get('retention_turns', 0)}",
            f"Lookahead {command_drip.get('lookahead_turns', 0)}",
            f"Queue {command_drip.get('pending_queue_mode', 'normal')}",
            "Lookahead forecasts",
            build_queue_next_action_cue(state),
            self._format_command_drip_summary(command_drip),
            f"Variants {'on' if command_drip.get('show_variants', True) else 'off'}",
            f"Dropped {'on' if command_drip.get('show_likely_dropped', True) else 'off'}",
            f"Last wake {scheduler.get('last_wake_reason', '-') or '-'}",
        )
        set_status(
            "prompt_ledger",
            f"Included {prompt_summary.get('included_rows', 0)}",
            f"Omitted {prompt_summary.get('omitted_rows', 0)}",
            f"Pins {prompt_summary.get('prompt_pin_rows', 0)}",
            f"Drops {prompt_summary.get('do_not_include_rows', 0)}",
            f"Marks {context_summary.get('dedicated_mark_store_entries', 0)}",
            f"Inclusion {prompt_inclusion.get('status', 'not exported')}",
            f"Activation {'on' if prompt_inclusion.get('activation_enabled', False) else 'off'}",
            f"Guard flags {prompt_inclusion_counts.get('hard_guardrail_flags', 0)}",
            f"Preview {prompt_preview.get('status', 'not exported')}",
            f"Diff +{prompt_preview_counts.get('proposed_additions', 0)}/-{prompt_preview_counts.get('proposed_omissions', 0)}",
            f"Rehearsal {prompt_rehearsal.get('status', 'not run')}",
            f"Rehearsal +{prompt_rehearsal_counts.get('rehearsal_additions', 0)}/-{prompt_rehearsal_counts.get('rehearsal_omissions', 0)}",
            f"Activation Review {prompt_activation.get('status', 'not exported')}",
            f"Activation checks {prompt_activation_counts.get('required_checks_passed', 0)}/{prompt_activation_counts.get('required_checks', 0)}",
            f"State {prompt_activation_state.get('status', 'off')}",
            f"Proof {prompt_activation_inner.get('offline_proof_status', 'not_run')}",
            f"Active pins {prompt_activation_state_counts.get('active_prompt_pins', 0)}",
            f"Active omissions {prompt_activation_state_counts.get('active_omissions', 0)}",
            f"Closure {prompt_closure.get('status', 'not exported')}",
            f"Closure ready {'yes' if prompt_closure.get('ready_for_window_close', False) else 'no'}",
            f"Closure warnings {prompt_closure_counts.get('warning', 0)}",
        )
        set_status(
            "portal_intake",
            f"{portal_intake.get('status', 'not exported')}",
            f"Mirror {'yes' if portal_intake.get('handoff_mirror_exists', False) else 'no'}",
            f"Routes {portal_intake_counts.get('routes', 0)}",
            f"Heavy {portal_intake_counts.get('heavy_routes', 0)}",
            f"Copy packets {portal_intake_counts.get('operator_copy_packets', 0)}",
            f"Draft templates {portal_intake_counts.get('receipt_draft_templates', 0)}",
            f"Review packets {portal_intake_counts.get('readiness_review_packets', 0)}",
            f"Registry rows {portal_intake_counts.get('envelope_registry_rows', 0)}",
            f"Registry contract {'ready' if portal_intake.get('ready_for_registry_contract_review', False) else 'waiting'}",
            f"Live registry {'ready' if portal_intake.get('ready_for_live_registry_read', False) else 'parked'}",
            f"Audit rows {portal_intake_counts.get('acceptance_audit_rows', 0)}",
            f"Audit proved {portal_intake_counts.get('acceptance_proved', 0)}",
            f"Audit waiting {portal_intake_counts.get('acceptance_waiting', 0)}",
            f"Audit missing {portal_intake_counts.get('acceptance_missing', 0)}",
            f"Audit blocked {portal_intake_counts.get('acceptance_blocked', 0)}",
            f"Local acceptance {'ready' if portal_intake.get('ready_for_local_acceptance', False) else 'waiting'}",
            f"External acceptance {'ready' if portal_intake.get('ready_for_external_acceptance', False) else 'parked'}",
            f"Docket rows {portal_intake_counts.get('promotion_evidence_rows', 0)}",
            f"Docket proved {portal_intake_counts.get('promotion_proved', 0)}",
            f"Docket waiting {portal_intake_counts.get('promotion_waiting', 0)}",
            f"Docket missing {portal_intake_counts.get('promotion_missing', 0)}",
            f"Docket blocked {portal_intake_counts.get('promotion_blocked', 0)}",
            f"Stage promotion {'ready' if portal_intake.get('ready_for_stage_promotion', False) else 'parked'}",
            f"Handoff packets {portal_intake_counts.get('external_handoff_packets', 0)}",
            f"Handoff ready {portal_intake_counts.get('handoff_ready_to_copy', 0)}",
            f"Handoff waiting {portal_intake_counts.get('handoff_waiting', 0)}",
            f"Handoff blocked {portal_intake_counts.get('handoff_blocked', 0)}",
            f"Handoff submit {'on' if portal_intake.get('external_handoff_submit_enabled', False) else 'off'}",
            f"Proof rows {portal_intake_counts.get('local_proof_rows', 0)}",
            f"Proof validated {portal_intake_counts.get('local_proof_validated', 0)}",
            f"Proof ready {portal_intake_counts.get('local_proof_ready_for_validation', 0)}",
            f"Proof watch {portal_intake_counts.get('local_proof_watch', 0)}",
            f"Current proof recorded {'yes' if portal_intake.get('current_slice_validation_recorded', False) else 'no'}",
            f"Report packets {portal_intake_counts.get('operator_report_packets', 0)}",
            f"Report ready {portal_intake_counts.get('operator_report_ready_to_copy', 0)}",
            f"Report waiting {portal_intake_counts.get('operator_report_waiting', 0)}",
            f"Report blocked {portal_intake_counts.get('operator_report_blocked', 0)}",
            f"Unblockers {portal_intake_counts.get('gate_unblocker_rows', 0)}",
            f"Unblocker proved {portal_intake_counts.get('unblocker_proved', 0)}",
            f"Unblocker waiting {portal_intake_counts.get('unblocker_waiting', 0)}",
            f"Unblocker blocked {portal_intake_counts.get('unblocker_blocked', 0)}",
            f"Waitlist packets {portal_intake_counts.get('upstream_waitlist_packets', 0)}",
            f"Waitlist ready {portal_intake_counts.get('waitlist_ready_to_copy', 0)}",
            f"Waitlist waiting {portal_intake_counts.get('waitlist_waiting', 0)}",
            f"Waitlist blocked {portal_intake_counts.get('waitlist_blocked', 0)}",
            f"Parking packets {portal_intake_counts.get('parking_resume_packets', 0)}",
            f"Parking ready {portal_intake_counts.get('parking_ready_to_copy', 0)}",
            f"Parking waiting {portal_intake_counts.get('parking_waiting', 0)}",
            f"Parking blocked {portal_intake_counts.get('parking_blocked', 0)}",
            f"Closure checks {portal_intake_counts.get('intake_closure_checks', 0)}",
            f"Closure proved {portal_intake_counts.get('closure_proved', 0)}",
            f"Closure waiting {portal_intake_counts.get('closure_waiting', 0)}",
            f"Closure blocked {portal_intake_counts.get('closure_blocked', 0)}",
            f"HTTP {'on' if portal_intake_counts.get('portal_http_calls_enabled', False) else 'off'}",
            f"Polling {'on' if portal_intake_counts.get('polling_enabled', False) else 'off'}",
            f"Writer {'on' if portal_intake_counts.get('receipt_writer_enabled', False) else 'off'}",
            f"Submit {'on' if portal_intake_counts.get('submit_receipts_enabled', False) else 'off'}",
            f"Gates ok {portal_intake_gate_counts.get('ok', 0)}",
            f"Gates watch {portal_intake_gate_counts.get('watch', 0)}",
            f"Gates blocked {portal_intake_gate_counts.get('blocked', 0)}",
            f"Live reads {'ready' if portal_intake.get('ready_for_live_portal_reads', False) else 'parked'}",
            f"Proof {'ready' if portal_intake.get('ready_for_cross_client_proof', False) else 'parked'}",
            f"Receipts {'ready' if portal_intake.get('ready_for_receipt_submission', False) else 'parked'}",
            f"Mutation {'ready' if portal_intake.get('ready_for_mutation_gates', False) else 'parked'}",
            f"ok {portal_intake_status_counts.get('ok', 0)}",
            f"watch {portal_intake_status_counts.get('watch', 0)}",
            f"blocked {portal_intake_status_counts.get('blocked', 0)}",
        )
        harness_posture = live_harness.get("current_posture", {}) or {}
        harness_contract = live_harness.get("expected_observation_contract", {}) or {}
        harness_readiness = live_harness.get("readiness", {}) or {}
        harness_warnings = harness_readiness.get("warnings", []) or []
        harness_rehearsal = state.get("live_visual_harness_rehearsal", {}) or {}
        harness_probe = state.get("live_visual_harness_probe", {}) or {}
        set_status(
            "live_harness",
            f"{live_harness.get('status', 'not exported')}",
            f"Offline {'ready' if harness_readiness.get('ready_for_offline_rehearsal', False) else 'not ready'}",
            f"Live {'ready' if harness_readiness.get('ready_for_live', False) else 'blocked'}",
            f"Rehearsal {harness_rehearsal.get('status', 'not run') or 'not run'}",
            f"Probe {harness_probe.get('status', 'not armed') or 'not armed'}",
            f"Mode {'live' if harness_posture.get('live_mode', False) else 'offline'}",
            f"Action {harness_posture.get('action_mode', '-') or '-'}",
            f"Prior cap {harness_contract.get('prior_image_cap', '-')}",
            f"In prompt {harness_contract.get('in_prompt_visual_count', '-')}",
            f"Warnings {len(harness_warnings)}",
        )
        responses_summary = responses_shadow.get("summary", {}) or {}
        responses_closure = responses_shadow.get("shadow_closure_readiness", {}) or {}
        closure_counts = responses_closure.get("status_counts", {}) or {}
        set_status(
            "responses_shadow",
            f"{responses_shadow.get('status', 'not exported')}",
            f"current {responses_summary.get('current_transport', '-') or '-'}",
            f"shadow {responses_summary.get('shadow_transport', '-') or '-'}",
            f"closure {responses_summary.get('closure_readiness_status', responses_closure.get('status', '-')) or '-'}",
            f"ready {'yes' if responses_summary.get('closure_ready_for_window_close', responses_closure.get('ready_for_window_close', False)) else 'no'}",
            f"closure ok {closure_counts.get('ok', responses_summary.get('closure_ok_count', 0))}",
            f"blocked {closure_counts.get('blocked', responses_summary.get('closure_blocked_count', 0))}",
            f"probe {responses_summary.get('shadow_live_probe_status', '-') or '-'}",
            f"probe model {responses_summary.get('shadow_live_probe_model', '-') or '-'}",
            f"probe send {'on' if responses_summary.get('shadow_live_probe_send_enabled', False) else 'off'}",
            f"contract {responses_summary.get('comparison_contract_rows', 0)} rows",
            f"builder {'on' if responses_summary.get('shadow_request_builder_enabled', False) else 'off'}",
            f"payload rows {responses_summary.get('shadow_payload_ledger_rows_used', 0)}",
            f"inputs {responses_summary.get('shadow_payload_input_messages', 0)}",
            f"tokens~{responses_summary.get('shadow_estimated_input_tokens', 0)}",
            f"cost~{responses_summary.get('shadow_estimated_total_usd', '-')}",
            f"state {responses_summary.get('shadow_state_risk', '-') or '-'}",
            f"api {'on' if responses_summary.get('responses_api_call_enabled', False) else 'off'}",
            f"migration {'on' if responses_summary.get('default_migration_enabled', False) else 'off'}",
            f"blockers {responses_summary.get('blocker_rows', 0)}",
        )
        image_index_summary = image_context_index.get("summary", {}) or {}
        image_cost_counts = image_cost_posture.get("counts", {}) or {}
        image_cost_limits = image_cost_posture.get("limits", {}) or {}
        set_status(
            "image_index",
            f"{image_index_summary.get('status', 'not exported')}",
            f"Sidecars {image_index_summary.get('sidecar_count', 0)}",
            f"Recent {image_index_summary.get('recent_count', 0)}",
            f"Cost {image_cost_posture.get('status', 'not exported')}",
            f"Coverage {image_cost_counts.get('sidecar_coverage_percent', 0)}%",
            f"Manifest {'found' if image_index_summary.get('manifest_exists', False) else 'missing'}",
            f"Backfill max {image_cost_limits.get('image_context_backfill_max_limit', '-')}",
            f"Search scan {image_cost_limits.get('image_context_search_max_scan', '-')}",
            f"Latest {short(Path(image_index_summary.get('latest_sidecar_path', '') or '').name or '-', 28)}",
            f"Backfill {short(image_index_summary.get('last_backfill_summary', '') or 'not run', 52)}",
            f"Update {short(image_index_summary.get('last_metadata_update', '') or 'none', 42)}",
            f"Search {short(image_index_summary.get('last_search_summary', '') or 'none', 52)}",
            f"Error {'yes' if image_index_summary.get('latest_error') else 'no'}",
        )
        safety_counts = self.count_settings_safety_classes()
        recovery_diagnostics = self.collect_recovery_diagnostics(state)
        recovery_home = self.build_recovery_home_snapshot(state)
        operator_risk_counts = operator_risk.get("counts", {}) or {}
        recovery_issue_count = len([item for item in recovery_diagnostics if item.get("level") != "ok"])
        set_status(
            "settings_safety",
            f"Home {recovery_home.get('status', 'watch')}",
            f"Risk {operator_risk.get('status', 'not exported')}",
            f"Cost {operator_risk_counts.get('cost_risk', '-')}",
            f"Action {operator_risk_counts.get('action_risk', '-')}",
            f"Commands {operator_risk_counts.get('command_risk', '-')}",
            f"Profile {recovery_home.get('recommended_profile', '-')}",
            f"Mapped {len(SETTING_SAFETY_INVENTORY)}",
            f"Diagnostics {recovery_issue_count}",
            f"Recovery {safety_counts.get('recovery-critical', 0)}",
            f"Risky {safety_counts.get('risky', 0)}",
            f"Hidden candidates {safety_counts.get('hidden-by-default', 0)}",
            f"Live {'on' if (state.get('modes', {}) or {}).get('live', False) else 'off'}",
            f"Exec {(state.get('modes', {}) or {}).get('execution', '-')}",
            f"Locks {sum(1 for value in (state.get('locks', {}) or {}).values() if bool(value))}",
            f"Pending {len(pending_rows)}",
            f"Next-turn {'queued' if has_effective_next_inference_plan((state.get('planning', {}) or {}).get('next_inference', {}) or {}) else 'empty'}",
        )
        set_status(
            "screenshots",
            f"Available {screenshot_count}",
            f"Selected {self.screenshot_index + 1 if self.screenshot_index >= 0 else 0}/{screenshot_count}",
            f"Latest {short(latest_screenshot_name, 28)}",
            format_timestamp_age_text(state.get("last_screenshot_timestamp", ""), "captured"),
            format_file_age_text(selected_screenshot_path, "selected file") if selected_screenshot_path else "selected file -",
            f"Follow latest {'on' if self.follow_latest_var.get() else 'off'}",
            f"Viewer {'open' if screenshot_viewer_open else 'closed'}",
            screenshot_scan_text,
            thumbnail_cache_text,
            panel_refresh_text,
        )
        set_status(
            "image_memory",
            f"State {state_image_count}",
            f"Renderable {retained_image_count}",
            f"Selected {self.image_memory_index + 1 if self.image_memory_index >= 0 else 0}/{retained_image_count}",
            format_timestamp_age_text((selected_image_row or {}).get("timestamp", ""), "selected") if selected_image_row else "selected -",
            f"Max history {(state.get('advanced', {}) or {}).get('max_images_in_history', '-')}",
            f"Viewer {'open' if image_viewer_open else 'closed'}",
        )
        set_status(
            "raw",
            f"State keys {state_keys}",
            f"State file {'found' if STATE_PATH.exists() else 'missing'}",
            f"Monitor {format_monitor_summary(monitors)}",
            f"Export {format_state_export_monitor_summary(monitors, state.get('state_export', {}) or {})}",
            f"Bridge {format_queue_bridge_monitor_summary(monitors, queue_bridge)}",
            build_queue_next_action_cue(state),
            build_state_freshness_text(state),
        )

    def render_state(self):
        self.refresh_conversation_feedback()
        state = self.state_cache or {}
        active_tab = self._get_active_tab_name()
        self._refresh_runtime_status_strip(state)
        self._set_runtime_banner_text(state.get("runtime_summary", ""))
        self.refresh_overview_summary(state)
        self._update_settings_transaction_surface(state)
        if hasattr(self, "agent_controls"):
            self.agent_controls.update_state()
        if hasattr(self, "switchboard") and (active_tab == "The Switchboard" or self.switchboard.pending):
            self.switchboard.update_state()
        models = state.get("models", {})
        model_catalog = state.get("model_catalog", {})
        model_status = state.get("model_status", {})
        modes = state.get("modes", {})
        planning = state.get("planning", {})
        scheduler = state.get("scheduler", {})
        defaults = state.get("defaults", {})
        advanced = state.get("advanced", {})
        continuity = state.get("continuity", {})
        overlay = state.get("overlay", {})
        panel = state.get("panel", {})
        security = state.get("security", {})
        locks = state.get("locks", {})
        choices = sorted(set(model_catalog.get("choices", []) or build_model_choices()))
        self.refresh_model_choice_widgets(choices)
        self._sync_setting_var(self.auth_var, modes.get('auth', 'api_key'))
        self._sync_setting_var(self.exec_var, modes.get('execution', 'assist'))
        self._sync_setting_var(self.action_var, modes.get('action', 'gb'))
        self._sync_setting_var(self.game_profile_var, modes.get('game_profile', 'firered'))
        self._sync_setting_var(self.text_model_var, models.get('text', 'gpt-6.1-sol'))
        self._sync_setting_var(self.model_transport_var, models.get('transport', 'chat_completions'))
        self._sync_setting_var(self.vision_model_var, models.get('vision', 'gpt-6.1-sol'))
        self._sync_setting_var(self.reasoning_model_var, models.get('reasoning', 'gpt-6-astra'))
        self._sync_setting_var(self.model_verbosity_var, models.get('verbosity', 'medium'))
        self._sync_setting_var(self.reasoning_effort_var, models.get('reasoning_effort', ''))
        self._sync_setting_var(self.battle_effort_var, models.get('battle_reasoning_effort', ''))
        self._sync_setting_var(self.review_effort_var, models.get('review_reasoning_effort', ''))
        self._sync_setting_var(self.critique_effort_var, models.get('critique_reasoning_effort', ''))
        self._sync_setting_var(self.reasoning_summary_var, models.get('summary_mode', 'auto'))
        self._sync_setting_var(self.review_verbosity_var, models.get('review_verbosity', 'medium'))
        self._sync_setting_var(self.battle_verbosity_var, models.get('battle_verbosity', 'low'))
        self._sync_setting_var(self.critique_verbosity_var, models.get('critique_verbosity', 'high'))
        self._sync_setting_var(self.temperature_var, str(models.get('temperature', 0.0)))
        self._sync_setting_var(self.interval_var, str(modes.get('screenshot_interval', 0.12)))
        self._sync_setting_var(self.review_turn_interval_var, str(planning.get('review_turn_interval', models.get('review_turn_interval', 10))))
        self._sync_setting_var(self.critique_turn_interval_var, str(planning.get('critique_turn_interval', models.get('critique_turn_interval', 30))))
        self._sync_setting_var(self.turn_scheduler_profile_var, str(scheduler.get('profile', 'balanced')))
        self._sync_setting_var(self.turn_scheduler_mode_var, str(scheduler.get('mode', 'hybrid')))
        self._sync_setting_var(self.turn_heartbeat_var, str(scheduler.get('heartbeat_seconds', 2.25)))
        self._sync_setting_var(self.turn_min_gap_var, str(scheduler.get('min_gap_seconds', 0.55)))
        self._sync_setting_var(self.turn_capture_wake_var, bool(scheduler.get('capture_wake_enabled', True)))
        self._sync_setting_var(self.turn_capture_wake_debounce_var, str(scheduler.get('capture_wake_debounce_seconds', 0.9)))
        self._sync_setting_var(self.turn_post_action_settle_var, str(scheduler.get('post_action_settle_seconds', 0.55)))
        self._sync_setting_var(self.demand_capture_var, bool(scheduler.get('demand_capture_enabled', True)))
        scheduler_description = str(
            scheduler.get("profile_description")
            or scheduler.get("description")
            or "Balanced is recommended: event-driven turns plus a calmer capture-change wake."
        )
        demand_status = "on" if scheduler.get("demand_capture_enabled", True) else "off"
        if scheduler.get("demand_capture_pending", False):
            demand_reason = str(scheduler.get("demand_capture_reason", "") or "capture")
            demand_status = f"pending {demand_reason}"
        scheduler_last_wake = str(scheduler.get("last_wake_reason", "")).strip()
        if scheduler_last_wake:
            scheduler_description = (
                f"profile={self.turn_scheduler_profile_var.get() or 'balanced'} | demand capture {demand_status} | "
                f"{scheduler_description} Last wake: {scheduler_last_wake}."
            )
        else:
            scheduler_description = (
                f"profile={self.turn_scheduler_profile_var.get() or 'balanced'} | demand capture {demand_status} | "
                f"{scheduler_description}"
            )
        self.scheduler_status_var.set(scheduler_description)
        self._sync_setting_var(self.pending_queue_mode_var, str(planning.get('pending_queue_mode', models.get('pending_queue_mode', 'normal'))))
        self._sync_setting_var(self.command_drip_retention_var, str(planning.get('command_drip_retention_turns', 5)))
        self._sync_setting_var(self.command_drip_lookahead_var, str(planning.get('command_drip_lookahead_turns', 3)))
        self._sync_setting_var(self.command_drip_show_variants_var, bool(planning.get('command_drip_show_variants', True)))
        self._sync_setting_var(self.command_drip_show_likely_dropped_var, bool(planning.get('command_drip_show_likely_dropped', True)))
        self._sync_setting_var(self.live_var, bool(modes.get('live', False)))
        self._sync_setting_var(self.live_init_var, bool(modes.get('load_live_init_prompt', False)))
        self._sync_setting_var(self.sound_var, bool(modes.get('sound_effects', False)))
        self._sync_setting_var(self.time_logging_var, bool(modes.get('time_logging', False)))
        self._sync_setting_var(self.chat_log_echo_var, bool(modes.get('chat_log_echo', True)))
        self._sync_setting_var(self.auto_dynamic_var, bool(planning.get('auto_dynamic_inference', models.get('auto_dynamic_inference', True))))
        self.security_required_var.set(bool(security.get("passcode_required", False)))
        self.show_passcode_commands_var.set(bool(security.get("show_passcode_commands", False)))
        if security.get("has_passcode", False):
            status = "authorized" if security.get("authorized", False) else "locked"
            ttl_seconds = security.get("authorized_seconds_remaining", 0)
            self.security_status_var.set(
                f"Operator security: {'required' if security.get('passcode_required', False) else 'configured'}"
                f" | status={status} | ttl={ttl_seconds}s"
                f" | cmds={'raw' if security.get('show_passcode_commands', False) else '*******'}"
            )
        else:
            self.security_status_var.set(
                f"Operator security: off | cmds={'raw' if security.get('show_passcode_commands', False) else '*******'}"
            )
        self._sync_setting_var(self.tile_grid_var, bool(overlay.get('tile_grid', False)))
        self._sync_setting_var(self.cursor_label_var, bool(overlay.get('cursor_label', True)))
        self._sync_setting_var(self.keypoint_grid_var, bool(overlay.get('keypoint_grid', True)))
        self._sync_setting_var(self.status_overlay_var, bool(overlay.get('status_text', True)))
        self._sync_setting_var(self.auto_prompt_var, bool(advanced.get('auto_prompt', False)))
        self._sync_setting_var(self.show_user_text_var, bool(advanced.get('show_user_text', True)))
        self._sync_setting_var(self.show_ai_text_var, bool(advanced.get('show_ai_text', True)))
        self._sync_setting_var(self.show_ai_commands_var, not bool(advanced.get('hide_ai_commands', False)))
        self._sync_setting_var(self.show_user_commands_var, not bool(advanced.get('hide_user_commands', False)))
        self._sync_setting_var(self.enable_unimportant_messages_var, bool(advanced.get('enable_unimportant_messages', True)))
        self._sync_setting_var(self.enable_important_messages_var, bool(advanced.get('enable_important_messages', True)))
        self._sync_setting_var(self.add_umsgs_to_history_var, bool(advanced.get('add_umsgs_to_history', False)))
        self._sync_setting_var(self.add_imsgs_to_history_var, bool(advanced.get('add_imsgs_to_history', False)))
        self._sync_setting_var(self.check_umsgs_decay_var, bool(advanced.get('check_umsgs_decay', False)))
        self._sync_setting_var(self.check_imsgs_decay_var, bool(advanced.get('check_imsgs_decay', False)))
        self._sync_setting_var(self.always_mode_var, 'on' if bool(advanced.get('always_on', False)) else 'off')
        self._sync_setting_var(self.hide_input_pref_var, bool(advanced.get('hide_input', False)))
        self._sync_setting_var(self.image_detail_var, str(advanced.get('image_detail', 'low')))
        self._sync_setting_var(self.latest_image_detail_var, str(advanced.get('latest_image_detail', 'low')))
        self._sync_setting_var(self.high_detail_var, str(advanced.get('high_detail', 0)))
        self._sync_setting_var(self.max_images_var, str(advanced.get('max_images_in_history', 0)))
        self.chat_head_opacity_var.set(str(panel.get("chat_head_opacity", 0.87)))
        self.chat_head_topmost_var.set(bool(panel.get("chat_head_topmost", True)))
        self.chat_head_strip_width_var.set(str(panel.get("chat_head_strip_width", 1000)))
        self.chat_head_strip_height_var.set(str(panel.get("chat_head_strip_height", 100)))
        self.chat_head_history_width_var.set(str(panel.get("chat_head_history_width", 420)))
        self.chat_head_history_height_var.set(str(panel.get("chat_head_history_height", 620)))
        self.chat_head_send_animation_var.set(str(panel.get("chat_head_send_animation", "pulse")))
        self.chat_head_send_animation_seconds_var.set(str(panel.get("chat_head_send_animation_seconds", 0.75)))
        next_plan = planning.get("next_inference", {}) or {}
        self.next_reasoning_var.set(str(next_plan.get("reasoning_effort", "")))
        self.next_verbosity_var.set(str(next_plan.get("verbosity", "")))
        self.next_summary_var.set(str(next_plan.get("summary_mode", "")))
        self.next_image_detail_var.set(str(next_plan.get("image_detail", "")))
        self.next_latest_image_detail_var.set(str(next_plan.get("latest_image_detail", "")))
        self.next_temperature_var.set(str(next_plan.get("temperature", "")))
        next_model = next_plan.get("model") or next_plan.get("text_model") or ""
        self.next_model_var.set(str(next_model))
        self.next_note_var.set(str(next_plan.get("note", "")))
        personal_state = defaults.get("personal_status") or ("available" if defaults.get("personal_available", False) else "not saved")
        self.defaults_status_var.set(
            f"System defaults: {'ready' if defaults.get('system_available', True) else 'missing'} | "
            f"Personal defaults: {personal_state}"
        )
        self.model_cost_status_var.set(self.build_model_cost_status(model_status))
        self.next_turn_status_var.set(self.build_next_turn_status(planning))
        self.advanced_context_status_var.set(self.build_advanced_context_status(advanced))
        self.setting_safety_status_var.set(self.build_settings_safety_summary(state))
        self.refresh_recovery_home_vars(state)
        if not self.handoff_file_var.get().strip():
            self.handoff_file_var.set(str(continuity.get("default_handoff_filename", "")))
        self.apply_runtime_locks(locks)

        self._write_text(self.feedback_text, "\n".join(state.get("latest_feedback", []) or ["No recent feedback."]))
        if active_tab in {"", "Overview"}:
            self._write_text(self.overview_text, self.build_overview_text(state))
        if active_tab == "Dashboard" or self._is_dashboard_popout_open():
            self.refresh_dashboard(state)
        self._write_text(self.model_status_text, self.build_model_status_text(model_status))
        if active_tab == "Command Drip":
            self._write_text(self.command_drip_text, self.build_command_drip_text(state.get("command_drip", {})))
        if active_tab == "Raw State":
            self._write_text(self.raw_text, json.dumps(state, indent=2))
        if active_tab == "Memory":
            self.render_memory(state)
        if active_tab == "Episodic":
            self.render_episodic(state)
        if active_tab == "Pending":
            self.render_pending(
                state.get("pending_commands", []),
                state.get("agent_suggestions", {}),
                state.get("agent_tasks", {}),
                state.get("agent_pending_gate", {}),
                state.get("agent_pending_insert_dry_run", {}),
                pending_queue=state.get("pending_queue", {}),
            )
        if active_tab == "Prompt Ledger":
            self._write_text(
                self.prompt_ledger_text,
                self.build_prompt_ledger_text(
                    state.get("prompt_context_ledger", {}),
                    state.get("context_marks", {}),
                    state.get("prompt_inclusion_readiness", {}),
                    state.get("prompt_inclusion_preview", {}),
                    state.get("prompt_inclusion_rehearsal", {}),
                    state.get("prompt_inclusion_activation_checklist", {}),
                    state.get("prompt_inclusion_activation", {}),
                    state.get("prompt_inclusion_closure", {}),
                ),
            )
        if active_tab == "Agents":
            self._write_text(
                self.agent_registry_text,
                self.build_agent_registry_text(
                    state.get("agent_registry", {}),
                    state.get("agent_suggestions", {}),
                    state.get("agent_tasks", {}),
                    state.get("agent_pending_gate", {}),
                    state.get("agent_pending_insert_dry_run", {}),
                    state.get("agent_helper_closure", {}),
                ),
            )
        if active_tab == "History Context":
            self._write_text(
                self.history_context_text,
                self.build_history_context_text(
                    state.get("history_context_service", {}),
                    state.get("companion_contract_readiness", {}),
                    state.get("companion_protocol_contract", {}),
                    state.get("companion_receipt_audit", {}),
                    state.get("companion_contract_closure", {}),
                ),
            )
        if active_tab == "Portal Intake":
            self._write_text(self.portal_intake_text, self.build_portal_intake_text(state.get("portal_companion_intake", {})))
        if active_tab == "Visual Context":
            self._write_text(self.visual_context_text, self.build_visual_context_text(state.get("visual_context", {})))
        if active_tab == "Image Index":
            self._write_text(
                self.image_context_index_text,
                self.build_image_context_index_text(
                    state.get("image_context_index", {}),
                    state.get("image_cost_posture", {}),
                ),
            )
        if active_tab == "Live Harness":
            self._write_text(
                self.live_harness_text,
                self.build_live_harness_text(
                    state.get("live_visual_harness", {}),
                    state.get("live_visual_harness_rehearsal", {}),
                    state.get("live_visual_harness_probe", {}),
                ),
            )
        if active_tab == "Responses Shadow":
            self._write_text(self.responses_shadow_text, self.build_responses_shadow_text(state.get("responses_shadow_transport", {})))
        if active_tab == "Context Files":
            self._write_text(self.context_files_text, self.build_context_files_text(state.get("context_files", {})))
        if active_tab == "Recovery":
            self._write_text(self.settings_safety_text, self.build_settings_safety_text(state))
        if active_tab == "Screenshots" or self._is_screenshot_popout_open():
            self.refresh_screenshot_list(state)
        if active_tab == "Images In Memory" or self._is_image_memory_popout_open():
            self.refresh_image_memory_list(state)
        self.refresh_workflow_status(state)
        self.sync_chat_head_visibility()

    def render_pending(self, rows, agent_suggestions=None, agent_tasks=None, agent_pending_gate=None, agent_pending_insert_dry_run=None, pending_queue=None):
        snapshot = pending_queue if isinstance(pending_queue, dict) else {}
        self.pending_snapshot_version = snapshot.get("version", "")
        self.pending_rows = list(snapshot.get("entries", rows) or [])
        self.render_pending_current()
        if getattr(self, "pending_candidates_text", None) is not None:
            self._write_text(self.pending_candidates_text, self.build_pending_candidate_text(agent_suggestions, agent_tasks, agent_pending_gate, agent_pending_insert_dry_run))

    def render_memory(self, state):
        self.memory_tree.delete(*self.memory_tree.get_children())
        route = state.get("route_state", {}) or {}
        memory_tiers = state.get("memory_tiers", {}) or {}
        planning = state.get("planning", {}) or {}

        def add_section(title, rows):
            parent = self.memory_tree.insert("", "end", text=title, values=("", ""))
            for item, value in rows:
                value_text = short(value, 260) if isinstance(value, str) else short(json.dumps(value, ensure_ascii=False), 260)
                self.memory_tree.insert(parent, "end", text="", values=(item, value_text))
            self.memory_tree.item(parent, open=True)

        add_section("Goals", [(f"Goal {idx}", value) for idx, value in enumerate(state.get("goals", []), start=1)] or [("-", "-")])
        add_section("Overarching", [(f"Item {idx}", value) for idx, value in enumerate(state.get("overarching_goals", []), start=1)] or [("-", "-")])
        add_section("Apriority", [(f"Item {idx}", value) for idx, value in enumerate(state.get("apriority_goals", []), start=1)] or [("-", "-")])
        add_section("Inventory", [(f"Item {idx}", value) for idx, value in enumerate(state.get("inventory", []), start=1)] or [("-", "-")])
        add_section("Party", [(f"Slot {idx}", value) for idx, value in enumerate(state.get("party_status", []), start=1)] or [("-", "-")])
        add_section("Notes", [(f"Note {idx}", value) for idx, value in enumerate(state.get("notes", []), start=1)] or [("-", "-")])
        add_section("Journal", [(f"Entry {idx}", value) for idx, value in enumerate(state.get("journal_entries", []), start=1)] or [("-", "-")])
        add_section("Active Questions", [(f"Question {idx}", value) for idx, value in enumerate(state.get("active_questions", []), start=1)] or [("-", "-")])
        add_section("Stale Assumptions", [(f"Assumption {idx}", value) for idx, value in enumerate(state.get("stale_assumptions", []), start=1)] or [("-", "-")])
        add_section("Known Failures", [(f"Failure {idx}", value) for idx, value in enumerate(state.get("known_failures", []), start=1)] or [("-", "-")])
        add_section("Candidate Alternatives", [(f"Alternative {idx}", value) for idx, value in enumerate(state.get("candidate_alternatives", []), start=1)] or [("-", "-")])
        add_section(
            "On-Hand Memory",
            [(entry.get("store", "-"), entry.get("role", "")) for entry in (memory_tiers.get("on_hand", []) or [])] or [("-", "-")],
        )
        add_section(
            "Retrievable Memory",
            [(entry.get("store", "-"), entry.get("role", "")) for entry in (memory_tiers.get("retrievable", []) or [])] or [("-", "-")],
        )
        add_section("Immediate", [(f"Action {idx}", value) for idx, value in enumerate(state.get("pinned_immediate_actions", []), start=1)] or [("-", "-")])
        add_section("Short Term", [(f"Action {idx}", value) for idx, value in enumerate(state.get("pinned_short_term_actions", []), start=1)] or [("-", "-")])
        add_section("Mid Term", [(f"Item {idx}", value) for idx, value in enumerate(state.get("mid_term_context", []), start=1)] or [("-", "-")])
        add_section("Long Term", [(f"Item {idx}", value) for idx, value in enumerate(state.get("long_term_context", []), start=1)] or [("-", "-")])
        add_section("Recent Context", [(f"Context {idx}", value) for idx, value in enumerate(state.get("recent_context_events", []), start=1)] or [("-", "-")])
        add_section("Recent Action Intents", [(f"Intent {idx}", value) for idx, value in enumerate(state.get("recent_action_intents", []), start=1)] or [("-", "-")])
        add_section("Recent Command Proposals", [(f"Proposal {idx}", value) for idx, value in enumerate(state.get("recent_command_proposals", []), start=1)] or [("-", "-")])
        add_section("Recent Executed", [(f"Action {idx}", value) for idx, value in enumerate(state.get("recent_executed_actions", []), start=1)] or [("-", "-")])
        add_section(
            "Route State",
            [
                ("Current Area", route.get("current_area", "")),
                ("Target Area", route.get("target_area", "")),
                ("Travel Heading", route.get("travel_heading", "")),
                ("Last Landmark", route.get("last_landmark", "")),
                ("Status", route.get("status", "")),
                ("Stale Reasons", ", ".join(route.get("stale_reasons", []) or [])),
            ],
        )
        add_section("Route Intent", [(f"Intent {idx}", value) for idx, value in enumerate(route.get("route_intent", []), start=1)] or [("-", "-")])
        add_section("Local Path", [(f"Step {idx}", value) for idx, value in enumerate(route.get("local_path_plan", []), start=1)] or [("-", "-")])
        add_section("Route Blockers", [(f"Blocker {idx}", value) for idx, value in enumerate(route.get("route_blockers", []), start=1)] or [("-", "-")])
        add_section("Recent Movement", [(f"Move {idx}", value) for idx, value in enumerate(route.get("recent_movement_results", []), start=1)] or [("-", "-")])
        add_section(
            "Planning Status",
            [
                ("Gameplay Scene", planning.get("gameplay_scene", "unknown")),
                ("Scene Summary", planning.get("gameplay_scene_summary", "")),
                ("Next Inference Source", planning.get("next_inference_source", "default")),
            ],
        )

    def build_episodic_control_status(self, episodic, rehydration=None):
        episodic = episodic or {}
        rehydration = rehydration or {}
        explainability = rehydration.get("explainability", {}) or {}
        mode = episodic.get("planning_assist_mode", "review_critique")
        enabled = bool(episodic.get("enabled", True))
        backend = episodic.get("embeddings_mode", "auto")
        item_count = episodic.get("planning_assist_k", 2)
        cooldown = episodic.get("planning_assist_cooldown_turns", 12)
        cooldown_remaining = int(episodic.get("planning_cooldown_remaining_turns", 0) or 0)
        next_eligible_turn = int(episodic.get("planning_next_eligible_turn", 0) or 0)
        last_reason = episodic.get("planning_last_reason", "-") or "-"
        last_turn = episodic.get("planning_last_turn", 0) or 0
        if mode == "off" or not enabled:
            injection = "no automatic planning injection"
        elif mode == "review_critique":
            injection = "injects on review and critique turns"
        else:
            injection = f"injects on {mode} turns"
        return (
            f"{'On' if enabled else 'Off'} | backend {backend} | {injection} | "
            f"items {item_count} | cooldown {cooldown} turns"
            f"{f' ({cooldown_remaining} remaining)' if cooldown_remaining else ''}"
            f"{f' | next eligible turn {next_eligible_turn}' if next_eligible_turn else ''}"
            f" | last {last_reason} @ turn {last_turn}"
            f" | rehydration {short(rehydration.get('automatic_status', '-') or '-', 90)}"
            f" | outcome {explainability.get('last_outcome', '-') or '-'}"
        )

    def build_episodic_tab_planning_status(self, episodic, rehydration=None):
        episodic = episodic or {}
        rehydration = rehydration or {}
        explainability = rehydration.get("explainability", {}) or {}
        decision = episodic.get("planning_last_decision", "-") or "-"
        decision_turn = episodic.get("planning_last_decision_turn", 0) or 0
        summary = short(episodic.get("planning_last_summary", "") or "-", 140)
        backend = episodic.get("planning_last_backend", "-") or "-"
        error = episodic.get("planning_last_error", "") or ""
        error_part = f" | error {short(error, 90)}" if error else ""
        source_mix = format_source_mix(
            explainability.get("last_query_source_mix", episodic.get("planning_last_query_source_mix", [])),
            limit=8,
            item_limit=28,
        )
        return (
            f"{self.build_episodic_control_status(episodic, rehydration)} | decision {decision} @ turn {decision_turn} | "
            f"backend {backend} | sources {source_mix} | injected memory: {summary}{error_part}"
        )

    def build_episodic_retrieval_status(self, episodic):
        episodic = episodic or {}
        query = episodic.get("last_search_query", "") or "-"
        item_count = len(episodic.get("last_retrieval_items", []) or [])
        returned = episodic.get("last_retrieval_count", item_count)
        backend = episodic.get("last_retrieval_backend", episodic.get("embeddings_mode", "lexical")) or "lexical"
        summary = short(episodic.get("last_retrieval_summary", "") or "-", 160)
        return (
            f"Preview query {short(query, 80)} | showing {item_count} of {returned} returned items | backend {backend} | "
            f"summary {summary} | preview alone does not inject memory until planning assist uses it or you promote an item"
        )

    def build_episodic_promotion_status(self, episodic):
        episodic = episodic or {}
        target = episodic.get("last_promoted_target", "") or "-"
        summary = short(episodic.get("last_promoted_summary", "") or "-", 160)
        cached = len(episodic.get("last_retrieval_items", []) or [])
        return (
            f"Last promoted target {target} | {summary} | cached retrieval items {cached}. "
            "Promote Selected copies the numbered retrieval result into the chosen live memory target."
        )

    def render_episodic(self, state):
        episodic = state.get("episodic_memory", {}) or {}
        rehydration = state.get("rehydration", {}) or {}
        rehydration_explain = rehydration.get("explainability", {}) or {}
        self.episodic_enabled_var.set(bool(episodic.get("enabled", True)))
        self.episodic_interval_var.set(str(episodic.get("interval_seconds", 900)))
        self.episodic_periodic_var.set(bool(episodic.get("periodic_trigger_enabled", True)))
        self.episodic_scene_var.set(bool(episodic.get("scene_trigger_enabled", True)))
        self.episodic_backend_var.set(str(episodic.get("embeddings_mode", "auto") or "auto"))
        self.episodic_planning_mode_var.set(str(episodic.get("planning_assist_mode", "review_critique") or "review_critique"))
        self.episodic_planning_k_var.set(str(episodic.get("planning_assist_k", 2)))
        self.episodic_planning_cooldown_var.set(str(episodic.get("planning_assist_cooldown_turns", 12)))
        self.episodic_embedding_model_var.set(str(episodic.get("embedding_model", "text-embedding-3-small") or "text-embedding-3-small"))
        if not getattr(self, "_episodic_query_initialized", False):
            self._episodic_query_initialized = True
            if not (self.episodic_query_var.get() or "").strip():
                self.episodic_query_var.set(str(episodic.get("last_search_query", "")))

        count = int(episodic.get("snapshot_count", 0) or 0)
        last_timestamp = str(episodic.get("last_snapshot_timestamp", "") or "-")
        last_reason = str(episodic.get("last_snapshot_reason", "") or "-")
        last_summary = str(episodic.get("last_retrieval_summary", "") or "-")
        last_promoted_target = str(episodic.get("last_promoted_target", "") or "")
        last_promoted_summary = str(episodic.get("last_promoted_summary", "") or "")
        self.episodic_status_var.set(
            f"enabled={'on' if episodic.get('enabled', True) else 'off'}"
            f" | count={count}"
            f" | interval={float(episodic.get('interval_seconds', 900) or 900):.0f}s"
            f" | periodic={'on' if episodic.get('periodic_trigger_enabled', True) else 'off'}"
            f" | scene={'on' if episodic.get('scene_trigger_enabled', True) else 'off'}"
            f" | semantic={episodic.get('embeddings_mode', 'auto')}"
            f" | planning={episodic.get('planning_assist_mode', 'review_critique')}:{episodic.get('planning_assist_k', 2)}:cd{episodic.get('planning_assist_cooldown_turns', 12)}"
            f" | model={short(episodic.get('embedding_model', 'text-embedding-3-small'), 28)}"
            f" | cache={int(episodic.get('embedding_cache_entries', 0) or 0)}"
            f" | last={last_timestamp}"
            f" | reason={short(last_reason, 48)}"
            f" | retrieval={short(last_summary, 80)}"
            f" | rehydration={short(rehydration.get('automatic_status', '-') or '-', 80)}"
            f" | promoted={short((last_promoted_target + ':' + last_promoted_summary).strip(':'), 72) or '-'}"
        )
        self.episodic_control_status_var.set(self.build_episodic_control_status(episodic, rehydration))
        self.episodic_tab_planning_status_var.set(self.build_episodic_tab_planning_status(episodic, rehydration))
        self.episodic_retrieval_status_var.set(self.build_episodic_retrieval_status(episodic))
        self.episodic_promotion_status_var.set(self.build_episodic_promotion_status(episodic))

        recent_limit_text = (self.episodic_recent_limit_var.get() or "8").strip()
        try:
            recent_limit = max(1, min(24, int(float(recent_limit_text))))
        except (TypeError, ValueError):
            recent_limit = 8
        local_rows = read_jsonl_records(EPISODIC_MEMORY_PATH, limit=max(recent_limit, 24))
        self.episodic_rows = list(local_rows)
        recent_rows = list(reversed(local_rows[-recent_limit:]))
        query = (self.episodic_query_var.get() or "").strip().lower()
        if query:
            recent_rows = [
                row for row in recent_rows
                if query in json.dumps(
                    {
                        "summary_text": row.get("summary_text", ""),
                        "tags": row.get("tags", []),
                        "trigger": row.get("trigger", ""),
                        "scene": row.get("gameplay_scene", ""),
                        "reason": row.get("reason", ""),
                    },
                    ensure_ascii=False,
                ).lower()
            ]
        recent_lines = [f"Store: {EPISODIC_MEMORY_PATH}"]
        if recent_rows:
            for index, row in enumerate(recent_rows, start=1):
                tags = ", ".join(row.get("tags", [])[:8]) or "-"
                recent_lines.append(
                    f"{index}. [{row.get('timestamp', '?')}] {row.get('trigger', 'unknown')}"
                    f" | importance={row.get('importance_score', 0)}"
                    f" | scene={row.get('gameplay_scene', 'unknown')}"
                )
                recent_lines.append(f"   reason: {short(row.get('reason', ''), 180)}")
                recent_lines.append(f"   tags: {tags}")
                recent_lines.append(f"   summary: {short(row.get('summary_text', ''), 240)}")
        else:
            recent_lines.append("No episodic snapshots match the current local view.")
        self._write_text(self.episodic_recent_text, "\n".join(recent_lines))

        retrieval_items = list(episodic.get("last_retrieval_items", []) or [])
        query_sources = rehydration_explain.get("last_query_source_mix", episodic.get("planning_last_query_source_mix", []))
        live_counts = rehydration.get("live_memory_counts", {}) or {}
        retrieval_lines = [
            "Rehydration explainability:",
            f"Automatic status: {rehydration.get('automatic_status', '-') or '-'}",
            f"Last outcome: {rehydration_explain.get('last_outcome', '-') or '-'} | decision={rehydration_explain.get('last_decision', episodic.get('planning_last_decision', '-')) or '-'} @ turn {rehydration_explain.get('last_decision_turn', episodic.get('planning_last_decision_turn', 0)) or 0}",
            f"Source mix: {format_source_mix(query_sources, limit=16, item_limit=36)}",
            f"Query preview: {rehydration_explain.get('last_query_preview', episodic.get('planning_last_query', '-')) or '-'}",
            f"Operator hint: {rehydration_explain.get('operator_hint', '-') or '-'}",
            (
                "Live source counts: "
                f"route={live_counts.get('route_state_entries', 0)}, notes={live_counts.get('notes', 0)}, "
                f"recent_context={live_counts.get('recent_context', 0)}, blockers={live_counts.get('route_blockers', 0)}, "
                f"goals={live_counts.get('goals', 0)}, questions={live_counts.get('active_questions', 0)}, "
                f"failures={live_counts.get('known_failures', 0)}"
            ),
            "",
            f"Last query: {episodic.get('last_search_query', '-') or '-'}",
            f"Runtime summary: {episodic.get('last_retrieval_summary', '-') or '-'}",
            "Retrieval preview is a candidate set; it is not live turn context until planning assist injects it or you promote an item.",
            f"Backend: {episodic.get('last_retrieval_backend', episodic.get('embeddings_mode', 'lexical')) or 'lexical'} | model={episodic.get('embedding_model', 'text-embedding-3-small')}",
            f"Planning assist: mode={episodic.get('planning_assist_mode', 'review_critique')} | k={episodic.get('planning_assist_k', 2)} | cooldown={episodic.get('planning_assist_cooldown_turns', 12)} | remaining={episodic.get('planning_cooldown_remaining_turns', 0) or 0} | last={episodic.get('planning_last_reason', '-') or '-'} turn {episodic.get('planning_last_turn', 0) or 0}",
            f"Planning decision: {episodic.get('planning_last_decision', '-') or '-'} @ turn {episodic.get('planning_last_decision_turn', 0) or 0}",
            f"Planning retrieval: {episodic.get('planning_last_summary', '-') or '-'}",
            f"Planning backend: {episodic.get('planning_last_backend', '-') or '-'} | error={episodic.get('planning_last_error', '-') or '-'}",
            f"Last promoted: {episodic.get('last_promoted_target', '-') or '-'} | {short(episodic.get('last_promoted_summary', ''), 180) or '-'}",
            "",
        ]
        search_info = episodic.get("last_retrieval_search", {}) or {}
        self._update_episodic_feedback_token(search_info)
        retained = search_info.get("retained_result") or {}
        self._episodic_displayed_result_handle = retained.get("handle", "")
        if search_info:
            feedback = search_info.get("feedback", {})
            retrieval_lines.append("Repeat feedback: " + json.dumps(feedback, ensure_ascii=False))
            retrieval_lines.append(f"Search counts: total={search_info.get('total_records', 0)} | eligible={search_info.get('eligible_records', 0)} | matched={search_info.get('matched_records', 0)} | returned={search_info.get('returned_records', 0)} | offset={search_info.get('offset', 0)} | next={search_info.get('next_offset')}")
            retrieval_lines.append("Effective hard filters: " + json.dumps(search_info.get("options", {}), ensure_ascii=False))
            retrieval_lines.append("Preview shows the first eight. Blank promotion handle uses this legacy preview; retained mode preserves every returned item and its full summary.")
            retrieval_lines.append("Retained result: " + json.dumps(retained, ensure_ascii=False))
            retrieval_lines.append("Use displayed handle explicitly to bind promotion; later refreshes do not change that selection. Handles expire after 30 minutes, eviction or restart.")
        self._draw_episodic_score_results(retrieval_items)
        if retrieval_items:
            if not (self.episodic_promote_index_var.get() or "").strip():
                self.episodic_promote_index_var.set("1")
            for index, row in enumerate(retrieval_items, start=1):
                if row.get("search_matches"):
                    retrieval_lines.append("Matched: " + "; ".join(row["search_matches"]))
                tags = ", ".join(row.get("tags", [])[:8]) or "-"
                retrieval_lines.append(
                    f"{index}. [{row.get('timestamp', '?')}] id={row.get('snapshot_id', '-')}"
                    f" | adjusted={row.get('adjusted_score', 0.0):.3f}"
                    f" | base={row.get('weighted_total', 0.0):.3f}"
                    f" | semantic={row.get('semantic_score', 0.0):.3f}"
                    f" | backend={row.get('semantic_backend_used', 'lexical') or 'lexical'}"
                    f" | time={row.get('time_score', 0.0):.3f}"
                    f" | tag={row.get('tag_score', 0.0):.3f}"
                    f" | recency={row.get('recency_percent', 0.0):.1f}"
                    f" | time_mode={row.get('time_mode', 'ordinal')} | age_hours={row.get('age_hours')}"
                    f" | time_source={row.get('time_source', 'ordinal')} | relevance={row.get('relevance_score', 0.0):.3f}"
                    f" | rank={row.get('rank_weight', 0.0):.3f}"
                    f" | rand={row.get('random_multiplier', 1.0):.3f}"
                    f" | source={row.get('source_bucket', 'unknown') or 'unknown'}"
                )
                retrieval_lines.append(
                    f"   score_parts: lexical_text={row.get('lexical_text_score', 0.0):.3f}"
                    f" | lexical_tag={row.get('lexical_tag_score', 0.0):.3f}"
                    f" | embed_text={row.get('embedding_text_score', 0.0):.3f}"
                    f" | embed_tag={row.get('embedding_tag_score', 0.0):.3f}"
                )
                retrieval_lines.append(f"   tags: {tags}")
                retrieval_lines.append(f"   summary: {short(row.get('summary_text', ''), 240)}")
        else:
            retrieval_lines.append("No retrieval payload is cached yet. Run RETRIEVAL_PULL from this tab or via raw commands.")
        self._write_text(self.episodic_retrieval_text, "\n".join(retrieval_lines))

    def render_logs(self, active_tab=None, force=False):
        active_tab = active_tab or self._get_active_tab_name()
        if force or active_tab == "Conversation" or (getattr(self, "conversation_navigator", None) and self.conversation_navigator.popout is not None) or (self.conversation_popout_window is not None and self.conversation_popout_window.winfo_exists() and self.conversation_popout_window.state() != "withdrawn"):
            self.render_conversation()
        if force or active_tab == "Chat":
            self._render_log_widget("chat", self.chat_text, CHAT_LOG_PATH, self.chat_log_limit)
        if force or active_tab == "Commands":
            self._render_log_widget("commands", self.command_text, CMD_LOG_PATH, self.command_log_limit)

    def _render_log_widget(self, log_name, widget, path, limit):
        try:
            stat = path.stat()
            signature = (str(path), stat.st_mtime_ns, stat.st_size, limit)
        except OSError:
            signature = (str(path), 0, 0, limit)
        if self._last_log_signatures.get(log_name) == signature:
            return
        self._last_log_signatures[log_name] = signature
        self._write_text(widget, "\n".join(tail_lines(path, limit)))

    def set_log_limit(self, log_name, limit):
        if log_name == "chat":
            self.chat_log_limit = limit
        else:
            self.command_log_limit = limit
        self.render_logs(force=True)

    @staticmethod
    def _path_render_signature(path):
        try:
            stat = path.stat()
            return str(path), stat.st_mtime_ns, stat.st_size
        except OSError:
            return str(path), 0, 0

    def _get_thumbnail_photo(self, path, size=THUMBNAIL_SIZE):
        if Image is None:
            return None
        signature = self._path_render_signature(Path(path)) + (tuple(size),)
        cache = self._thumbnail_photo_cache
        cached = cache.get(signature)
        if cached is not None:
            cache.pop(signature, None)
            cache[signature] = cached
            self._thumbnail_cache_stats["hits"] = int(self._thumbnail_cache_stats.get("hits", 0)) + 1
            self._thumbnail_cache_stats["entries"] = len(cache)
            return cached
        with Image.open(path) as opened:
            image = opened.copy()
        image.thumbnail(size)
        photo = ImageTk.PhotoImage(image)
        cache[signature] = photo
        while len(cache) > THUMBNAIL_CACHE_MAX_ENTRIES:
            cache.pop(next(iter(cache)))
        self._thumbnail_cache_stats["misses"] = int(self._thumbnail_cache_stats.get("misses", 0)) + 1
        self._thumbnail_cache_stats["entries"] = len(cache)
        return photo

    def _get_inline_preview_bounds(self, widget):
        notebook_width = self.notebook.winfo_width() if getattr(self, "notebook", None) is not None else 0
        notebook_height = self.notebook.winfo_height() if getattr(self, "notebook", None) is not None else 0
        available_width = notebook_width - 90 if notebook_width > 1 else INLINE_PREVIEW_MAX_WIDTH
        available_height = notebook_height - 280 if notebook_height > 1 else INLINE_PREVIEW_MAX_HEIGHT
        widget_width = widget.winfo_width()
        widget_height = widget.winfo_height()
        if widget_width > 1:
            available_width = min(available_width, widget_width - 16)
        if widget_height > 1:
            available_height = min(available_height, widget_height - 16)
        width = min(INLINE_PREVIEW_MAX_WIDTH, max(INLINE_PREVIEW_MIN_WIDTH, available_width))
        height = min(INLINE_PREVIEW_MAX_HEIGHT, max(INLINE_PREVIEW_MIN_HEIGHT, available_height))
        return int(width), int(height)

    def invalidate_screenshot_preview(self, _event=None):
        self._last_screenshot_render_signature = None
        self.after_idle(self.render_screenshot)

    def invalidate_image_memory_preview(self, _event=None):
        self._last_image_memory_render_signature = None
        self.after_idle(self.render_image_memory)

    def _is_screenshot_popout_open(self):
        try:
            return self.popout_window is not None and self.popout_window.winfo_exists()
        except tk.TclError:
            return False

    def _is_image_memory_popout_open(self):
        try:
            return self.memory_popout_window is not None and self.memory_popout_window.winfo_exists()
        except tk.TclError:
            return False

    def refresh_screenshot_list(self, state):
        screenshots_dir = (state.get("paths") or {}).get("screenshots_dir", "")
        latest_state_path = (state.get("last_screenshot_path", "") or "").strip()
        active_tab = self._get_active_tab_name()
        popout_open = self._is_screenshot_popout_open()
        current_path = None
        if 0 <= self.screenshot_index < len(self.screenshot_files):
            current_path = self.screenshot_files[self.screenshot_index]
        files = safe_list_screenshots(screenshots_dir, force_path=latest_state_path)
        self._screenshot_list_cache_stats = get_screenshot_list_cache_stats(screenshots_dir)
        list_signature = tuple(self._path_render_signature(path) for path in files)
        thumbnail_signature = tuple(str(path) for path in files)
        self.screenshot_files = files
        if list_signature != self._last_screenshot_list_signature:
            self._last_screenshot_list_signature = list_signature
            self._last_screenshot_render_signature = None
        if not self.screenshot_files:
            self.screenshot_index = -1
            self.screenshot_preview.configure(text="No screenshots available.", image="")
            self.screenshot_meta.configure(text="")
            return
        if self.follow_latest_var.get():
            self.screenshot_index = self.find_latest_renderable_index(self.screenshot_files)
        elif current_path in self.screenshot_files:
            self.screenshot_index = self.screenshot_files.index(current_path)
        elif self.screenshot_index < 0 or self.screenshot_index >= len(self.screenshot_files):
            self.screenshot_index = self.find_latest_renderable_index(self.screenshot_files)
        if active_tab == "Screenshots":
            if thumbnail_signature != self._last_thumbnail_signature:
                self._last_thumbnail_signature = thumbnail_signature
                self.render_thumbnail_strip()
            self.render_screenshot()
        elif popout_open:
            self.refresh_popout_image()

    def refresh_image_memory_list(self, state):
        active_tab = self._get_active_tab_name()
        popout_open = self._is_image_memory_popout_open()
        current_path = None
        if 0 <= self.image_memory_index < len(self.image_memory_rows):
            current_path = Path(self.image_memory_rows[self.image_memory_index].get("path", ""))
        self.image_memory_rows = [row for row in state.get("image_memory", []) if Path(row.get("path", "")).exists()]
        memory_signature = tuple(
            (
                str(row.get("path", "")),
                str(row.get("timestamp", "")),
                Path(row.get("path", "")).stat().st_mtime_ns if Path(row.get("path", "")).exists() else 0,
            )
            for row in self.image_memory_rows
        )
        if memory_signature != self._last_image_memory_signature:
            self._last_image_memory_signature = memory_signature
            self._last_image_memory_render_signature = None
        if not self.image_memory_rows:
            self.image_memory_index = -1
            self.image_memory_preview.configure(text="No retained image memory available.", image="")
            self.image_memory_meta.configure(text="")
            return
        if current_path and any(Path(row.get("path", "")) == current_path for row in self.image_memory_rows):
            self.image_memory_index = next(
                index for index, row in enumerate(self.image_memory_rows) if Path(row.get("path", "")) == current_path
            )
        elif self.image_memory_index < 0 or self.image_memory_index >= len(self.image_memory_rows):
            self.image_memory_index = len(self.image_memory_rows) - 1
        if active_tab == "Images In Memory":
            if memory_signature != self._last_memory_thumbnail_signature:
                self._last_memory_thumbnail_signature = memory_signature
                self.render_image_memory_thumbnail_strip()
            self.render_image_memory()
        elif popout_open:
            self.refresh_image_memory_popout()

    def render_screenshot(self):
        if self.screenshot_index < 0 or self.screenshot_index >= len(self.screenshot_files):
            return
        path = self.screenshot_files[self.screenshot_index]
        preview_bounds = self._get_inline_preview_bounds(self.screenshot_preview)
        render_signature = (
            self._path_render_signature(path),
            self.screenshot_index,
            len(self.screenshot_files),
            bool(self.follow_latest_var.get()),
            bool(self._is_screenshot_popout_open()),
            preview_bounds,
        )
        if render_signature == self._last_screenshot_render_signature:
            self.highlight_active_thumbnail()
            return
        self._last_screenshot_render_signature = render_signature
        original_size = self.get_image_size(path)
        dimension_text = f"{original_size[0]}x{original_size[1]}" if original_size else "unknown size"
        self.screenshot_meta.configure(
            text=(
                f"{self.screenshot_index + 1}/{len(self.screenshot_files)} | {path.name} | {dimension_text} | "
                f"Follow latest {'on' if self.follow_latest_var.get() else 'off'} | "
                f"Viewer {'open' if self.popout_window is not None and self.popout_window.winfo_exists() else 'closed'}"
            )
        )
        if Image is None:
            self.screenshot_preview.configure(text=str(path), image="")
            return
        try:
            with Image.open(path) as opened:
                image = opened.copy()
            image.thumbnail(preview_bounds)
            self.preview_image = ImageTk.PhotoImage(image)
            self.screenshot_preview.configure(image=self.preview_image, text="")
        except Exception as error:
            self.screenshot_preview.configure(text=f"Failed to load {path.name}: {error}", image="")
        self.highlight_active_thumbnail()
        self.refresh_popout_image()

    def render_thumbnail_strip(self):
        for child in self.thumbnail_inner.winfo_children():
            child.destroy()
        self.thumbnail_images = []
        if not self.screenshot_files:
            self._refresh_thumbnail_region()
            return
        for index, path in enumerate(self.screenshot_files):
            tile = ttk.Frame(self.thumbnail_inner, style="Card.TFrame", padding=4)
            tile.pack(side="left", padx=(0, 6))
            if Image is not None:
                try:
                    photo = self._get_thumbnail_photo(path)
                    self.thumbnail_images.append(photo)
                    button = tk.Button(
                        tile,
                        image=photo,
                        text="",
                        command=lambda i=index: self.set_screenshot_index(i),
                        bg=PANEL_2,
                        activebackground="#1d4b87",
                        relief="flat",
                        bd=0,
                        highlightthickness=1,
                        highlightbackground=BORDER,
                    )
                    button.pack()
                except Exception:
                    ttk.Button(tile, text=path.name, command=lambda i=index: self.set_screenshot_index(i)).pack()
            else:
                ttk.Button(tile, text=path.name, command=lambda i=index: self.set_screenshot_index(i)).pack()
            ttk.Label(tile, text=short(path.name, 20), style="CardBody.TLabel").pack(anchor="center", pady=(4, 0))
        self._refresh_thumbnail_region()

    def highlight_active_thumbnail(self):
        for index, child in enumerate(self.thumbnail_inner.winfo_children()):
            style_name = "Card.TFrame"
            if index == self.screenshot_index:
                style_name = "SelectedCard.TFrame"
            try:
                child.configure(style=style_name)
            except Exception:
                pass

    def open_screenshot_popout(self):
        if self.screenshot_index < 0 or self.screenshot_index >= len(self.screenshot_files):
            return
        if self.popout_window is not None and self.popout_window.winfo_exists():
            self.popout_window.deiconify()
            self.popout_window.lift()
            self.refresh_popout_image()
            return
        self.popout_window = tk.Toplevel(self)
        self.popout_window.title("Aurora Screenshot Viewer")
        fit_popout_window(self.popout_window, 1380, 920, self)
        self.popout_window.configure(bg=BG)
        self.popout_window.protocol("WM_DELETE_WINDOW", self.close_screenshot_popout)
        self.popout_window.bind("<Escape>", lambda _event: self.close_screenshot_popout())
        self.popout_window.bind("<Control-Key-0>", lambda _event: self.set_screenshot_popout_mode("fit"))
        self.popout_window.bind("<Control-Key-1>", lambda _event: self.set_screenshot_popout_mode("actual"))
        header = ttk.Frame(self.popout_window)
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(header, text="Screenshot Viewer", style="SectionTitle.TLabel").pack(side="left")
        self.popout_meta = ttk.Label(header, text="", style="CardBody.TLabel")
        self.popout_meta.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ttk.Label(header, textvariable=self.popout_status_var, style="Muted.TLabel").pack(side="right", padx=(10, 0))
        viewer_shell = ttk.Frame(self.popout_window)
        viewer_shell.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.popout_canvas = tk.Canvas(viewer_shell, bg=PANEL, highlightthickness=0)
        self.popout_canvas.pack(side="left", fill="both", expand=True)
        popout_y = ttk.Scrollbar(viewer_shell, orient="vertical", command=self.popout_canvas.yview)
        popout_y.pack(side="right", fill="y")
        popout_x = ttk.Scrollbar(self.popout_window, orient="horizontal", command=self.popout_canvas.xview)
        popout_x.pack(fill="x", padx=12)
        self.popout_canvas.configure(xscrollcommand=popout_x.set, yscrollcommand=popout_y.set)
        self.popout_canvas.bind("<Double-Button-1>", lambda _event: self.toggle_screenshot_popout_mode())
        self.popout_canvas.bind("<Configure>", lambda _event: self.refresh_popout_image())
        controls = ttk.Frame(self.popout_window)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(controls, text="Prev", command=lambda: self.step_screenshot(-1)).pack(side="left")
        ttk.Button(controls, text="Latest", command=self.jump_to_latest_screenshot).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Next", command=lambda: self.step_screenshot(1)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Fit", command=lambda: self.set_screenshot_popout_mode("fit")).pack(side="left", padx=(18, 0))
        ttk.Button(controls, text="1:1", command=lambda: self.set_screenshot_popout_mode("actual")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Close", command=self.close_screenshot_popout).pack(side="right")
        self.popout_scale_mode = "fit"
        self.popout_status_var.set("Screenshot viewer open.")
        self._last_popout_render_signature = None
        self.refresh_popout_image()

    def close_screenshot_popout(self):
        if self.popout_window is not None and self.popout_window.winfo_exists():
            self.popout_window.destroy()
        self.popout_window = None
        self.popout_label = None
        self.popout_canvas = None
        self.popout_meta = None
        self.popout_image = None
        self.popout_scale_mode = "fit"
        self._last_popout_render_signature = None
        self.popout_status_var.set("Screenshot viewer closed.")
        self.refresh_workflow_status(self.state_cache or {})

    def set_screenshot_popout_mode(self, mode):
        self.popout_scale_mode = "actual" if mode == "actual" else "fit"
        self.refresh_popout_image(reset_view=True)

    def toggle_screenshot_popout_mode(self):
        self.set_screenshot_popout_mode("actual" if self.popout_scale_mode == "fit" else "fit")

    def refresh_popout_image(self, reset_view=False):
        if self.popout_window is None or not self.popout_window.winfo_exists():
            return
        if self.screenshot_index < 0 or self.screenshot_index >= len(self.screenshot_files):
            return
        path = self.screenshot_files[self.screenshot_index]
        canvas_bounds = self._get_canvas_bounds(self.popout_canvas) if self.popout_canvas is not None else (0, 0)
        render_signature = (
            self._path_render_signature(path),
            self.screenshot_index,
            len(self.screenshot_files),
            self.popout_scale_mode,
            canvas_bounds,
        )
        if not reset_view and render_signature == self._last_popout_render_signature:
            return
        self._last_popout_render_signature = render_signature
        original_size = self.get_image_size(path)
        if self.popout_meta is not None:
            size_text = f"{original_size[0]}x{original_size[1]}" if original_size else "unknown size"
            self.popout_status_var.set(
                f"{self.screenshot_index + 1}/{len(self.screenshot_files)} | {self.popout_scale_mode} | {size_text}"
            )
            self.popout_meta.configure(
                text=f"{path.name} | {path.parent}"
            )
        if self.popout_canvas is None:
            return
        self._render_image_on_canvas(self.popout_canvas, path, "popout_image", self.popout_scale_mode, reset_view=reset_view)

    def open_image_memory_popout(self):
        if self.image_memory_index < 0 or self.image_memory_index >= len(self.image_memory_rows):
            return
        if self.memory_popout_window is not None and self.memory_popout_window.winfo_exists():
            self.memory_popout_window.deiconify()
            self.memory_popout_window.lift()
            self.refresh_image_memory_popout()
            return
        self.memory_popout_window = tk.Toplevel(self)
        self.memory_popout_window.title("Aurora Image Memory Viewer")
        fit_popout_window(self.memory_popout_window, 1380, 920, self)
        self.memory_popout_window.configure(bg=BG)
        self.memory_popout_window.protocol("WM_DELETE_WINDOW", self.close_image_memory_popout)
        self.memory_popout_window.bind("<Escape>", lambda _event: self.close_image_memory_popout())
        self.memory_popout_window.bind("<Control-Key-0>", lambda _event: self.set_image_memory_popout_mode("fit"))
        self.memory_popout_window.bind("<Control-Key-1>", lambda _event: self.set_image_memory_popout_mode("actual"))
        header = ttk.Frame(self.memory_popout_window)
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(header, text="Image Memory Viewer", style="SectionTitle.TLabel").pack(side="left")
        self.memory_popout_meta = ttk.Label(header, text="", style="CardBody.TLabel")
        self.memory_popout_meta.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ttk.Label(header, textvariable=self.memory_popout_status_var, style="Muted.TLabel").pack(side="right", padx=(10, 0))
        viewer_shell = ttk.Frame(self.memory_popout_window)
        viewer_shell.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.memory_popout_canvas = tk.Canvas(viewer_shell, bg=PANEL, highlightthickness=0)
        self.memory_popout_canvas.pack(side="left", fill="both", expand=True)
        memory_y = ttk.Scrollbar(viewer_shell, orient="vertical", command=self.memory_popout_canvas.yview)
        memory_y.pack(side="right", fill="y")
        memory_x = ttk.Scrollbar(self.memory_popout_window, orient="horizontal", command=self.memory_popout_canvas.xview)
        memory_x.pack(fill="x", padx=12)
        self.memory_popout_canvas.configure(xscrollcommand=memory_x.set, yscrollcommand=memory_y.set)
        self.memory_popout_canvas.bind("<Double-Button-1>", lambda _event: self.toggle_image_memory_popout_mode())
        self.memory_popout_canvas.bind("<Configure>", lambda _event: self.refresh_image_memory_popout())
        controls = ttk.Frame(self.memory_popout_window)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(controls, text="Prev", command=lambda: self.step_image_memory(-1)).pack(side="left")
        ttk.Button(controls, text="Latest", command=self.jump_to_latest_image_memory).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Next", command=lambda: self.step_image_memory(1)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Fit", command=lambda: self.set_image_memory_popout_mode("fit")).pack(side="left", padx=(18, 0))
        ttk.Button(controls, text="1:1", command=lambda: self.set_image_memory_popout_mode("actual")).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Close", command=self.close_image_memory_popout).pack(side="right")
        self.memory_popout_scale_mode = "fit"
        self.memory_popout_status_var.set("Image-memory viewer open.")
        self._last_memory_popout_render_signature = None
        self.refresh_image_memory_popout()

    def close_image_memory_popout(self):
        if self.memory_popout_window is not None and self.memory_popout_window.winfo_exists():
            self.memory_popout_window.destroy()
        self.memory_popout_window = None
        self.memory_popout_label = None
        self.memory_popout_canvas = None
        self.memory_popout_meta = None
        self.memory_popout_image = None
        self.memory_popout_scale_mode = "fit"
        self._last_memory_popout_render_signature = None
        self.memory_popout_status_var.set("Image-memory viewer closed.")
        self.refresh_workflow_status(self.state_cache or {})

    def set_image_memory_popout_mode(self, mode):
        self.memory_popout_scale_mode = "actual" if mode == "actual" else "fit"
        self.refresh_image_memory_popout(reset_view=True)

    def toggle_image_memory_popout_mode(self):
        self.set_image_memory_popout_mode("actual" if self.memory_popout_scale_mode == "fit" else "fit")

    def refresh_image_memory_popout(self, reset_view=False):
        if self.memory_popout_window is None or not self.memory_popout_window.winfo_exists():
            return
        if self.image_memory_index < 0 or self.image_memory_index >= len(self.image_memory_rows):
            return
        row = self.image_memory_rows[self.image_memory_index]
        path = Path(row.get("path", ""))
        canvas_bounds = self._get_canvas_bounds(self.memory_popout_canvas) if self.memory_popout_canvas is not None else (0, 0)
        render_signature = (
            self._path_render_signature(path),
            self.image_memory_index,
            len(self.image_memory_rows),
            self.memory_popout_scale_mode,
            canvas_bounds,
            str(row.get("timestamp", "")),
            str(row.get("detail", "")),
            bool(row.get("sticky", False)),
        )
        if not reset_view and render_signature == self._last_memory_popout_render_signature:
            return
        self._last_memory_popout_render_signature = render_signature
        original_size = self.get_image_size(path)
        if self.memory_popout_meta is not None:
            size_text = f"{original_size[0]}x{original_size[1]}" if original_size else "unknown size"
            self.memory_popout_status_var.set(
                f"{self.image_memory_index + 1}/{len(self.image_memory_rows)} | "
                f"{self.memory_popout_scale_mode} | {size_text} | {'sticky' if row.get('sticky', False) else 'normal'}"
            )
            self.memory_popout_meta.configure(
                text=f"{path.name} | detail={row.get('detail', '') or '-'} | {row.get('timestamp', '')}"
            )
        if self.memory_popout_canvas is None:
            return
        self._render_image_on_canvas(self.memory_popout_canvas, path, "memory_popout_image", self.memory_popout_scale_mode, reset_view=reset_view)

    def render_image_memory(self):
        if self.image_memory_index < 0 or self.image_memory_index >= len(self.image_memory_rows):
            return
        row = self.image_memory_rows[self.image_memory_index]
        path = Path(row.get("path", ""))
        preview_bounds = self._get_inline_preview_bounds(self.image_memory_preview)
        render_signature = (
            self._path_render_signature(path),
            self.image_memory_index,
            len(self.image_memory_rows),
            str(row.get("timestamp", "")),
            str(row.get("detail", "")),
            bool(row.get("sticky", False)),
            bool(self._is_image_memory_popout_open()),
            preview_bounds,
        )
        if render_signature == self._last_image_memory_render_signature:
            self.highlight_active_memory_thumbnail()
            return
        self._last_image_memory_render_signature = render_signature
        sticky = "sticky" if row.get("sticky") else "normal"
        original_size = self.get_image_size(path)
        size_text = f"{original_size[0]}x{original_size[1]}" if original_size else "unknown size"
        self.image_memory_meta.configure(
            text=(
                f"{self.image_memory_index + 1}/{len(self.image_memory_rows)} | {path.name} | {size_text} | "
                f"{row.get('detail', '') or '-'} | {sticky} | "
                f"Viewer {'open' if self.memory_popout_window is not None and self.memory_popout_window.winfo_exists() else 'closed'}"
            )
        )
        if Image is None:
            self.image_memory_preview.configure(text=str(path), image="")
            return
        try:
            with Image.open(path) as opened:
                image = opened.copy()
            image.thumbnail(preview_bounds)
            self.memory_preview_image = ImageTk.PhotoImage(image)
            self.image_memory_preview.configure(image=self.memory_preview_image, text="")
        except Exception as error:
            self.image_memory_preview.configure(text=f"Failed to load {path.name}: {error}", image="")
        self.highlight_active_memory_thumbnail()
        self.refresh_image_memory_popout()

    @staticmethod
    def get_image_size(path):
        if Image is None:
            return None
        try:
            with Image.open(path) as image:
                return image.size
        except Exception:
            return None

    def find_latest_renderable_index(self, paths):
        if not paths:
            return -1
        for index in range(len(paths) - 1, -1, -1):
            if self.get_image_size(paths[index]):
                return index
        return len(paths) - 1

    @staticmethod
    def _get_canvas_bounds(canvas, fallback=(1600, 980)):
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            width, height = fallback
        return max(width - 24, 320), max(height - 24, 240)

    def _render_image_on_canvas(self, canvas, path, holder_attr, scale_mode="fit", reset_view=False):
        if Image is None:
            canvas.delete("all")
            canvas.create_text(12, 12, text=str(path), anchor="nw", fill=TEXT)
            return
        try:
            with Image.open(path) as opened:
                image = opened.copy()
            if scale_mode != "actual":
                image.thumbnail(self._get_canvas_bounds(canvas))
            photo = ImageTk.PhotoImage(image)
            setattr(self, holder_attr, photo)
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=photo)
            canvas.configure(scrollregion=(0, 0, image.width, image.height))
            if reset_view or scale_mode != "actual":
                canvas.xview_moveto(0)
                canvas.yview_moveto(0)
        except Exception as error:
            canvas.delete("all")
            canvas.create_text(12, 12, text=f"Failed to load {Path(path).name}: {error}", anchor="nw", fill=TEXT)

    def render_image_memory_thumbnail_strip(self):
        for child in self.memory_thumbnail_inner.winfo_children():
            child.destroy()
        self.memory_thumbnail_images = []
        if not self.image_memory_rows:
            self._refresh_memory_thumbnail_region()
            return
        for index, row in enumerate(self.image_memory_rows):
            path = Path(row.get("path", ""))
            tile = ttk.Frame(self.memory_thumbnail_inner, style="Card.TFrame", padding=4)
            tile.pack(side="left", padx=(0, 6))
            if Image is not None and path.exists():
                try:
                    photo = self._get_thumbnail_photo(path)
                    self.memory_thumbnail_images.append(photo)
                    button = tk.Button(
                        tile,
                        image=photo,
                        text="",
                        command=lambda i=index: self.set_image_memory_index(i),
                        bg=PANEL_2,
                        activebackground="#1d4b87",
                        relief="flat",
                        bd=0,
                        highlightthickness=1,
                        highlightbackground=BORDER,
                    )
                    button.pack()
                except Exception:
                    ttk.Button(tile, text=path.name, command=lambda i=index: self.set_image_memory_index(i)).pack()
            else:
                ttk.Button(tile, text=path.name, command=lambda i=index: self.set_image_memory_index(i)).pack()
            ttk.Label(tile, text=short(path.name, 20), style="CardBody.TLabel").pack(anchor="center", pady=(4, 0))
        self._refresh_memory_thumbnail_region()

    def highlight_active_memory_thumbnail(self):
        for index, child in enumerate(self.memory_thumbnail_inner.winfo_children()):
            style_name = "Card.TFrame"
            if index == self.image_memory_index:
                style_name = "SelectedCard.TFrame"
            try:
                child.configure(style=style_name)
            except Exception:
                pass

    def build_model_cost_status(self, status):
        status = status or {}
        profiles = status.get("profiles", {}) or {}
        stateful_family = status.get("stateful_preset_family", {}) or {}
        rows = []
        names = []
        for role, status_key in (
            ("text", "text_model"),
            ("vision", "vision_model"),
            ("reasoning", "reasoning_model"),
        ):
            profile = profiles.get(role, {}) or {}
            model_name = (profile.get("name") or status.get(status_key) or "-").strip() or "-"
            names.append(model_name)
            rows.append(f"{role} {model_name}: {format_model_pricing_compact(profile.get('pricing_usd_per_1m', {}))}")
        unique_names = {name for name in names if name and name != "-"}
        if len(unique_names) == 1:
            first_profile = next((profiles.get(role, {}) or {} for role in ("text", "vision", "reasoning") if profiles.get(role)), {})
            active = f"Active: {names[0]} for text/vision/reasoning | {format_model_pricing_compact(first_profile.get('pricing_usd_per_1m', {}))}"
        else:
            active = "Active: " + " | ".join(short(row, 88) for row in rows)
        next_source = status.get("next_inference_source", "default")
        stateful_text = (
            f"Stateful: {stateful_family.get('active_profile', 'stateless-default')}"
            f" ({stateful_family.get('status', 'metadata_only')}); "
            f"transport {stateful_family.get('live_transport', 'chat/completions')}."
        )
        return (
            f"{active}. Next-turn source: {next_source}. "
            f"{stateful_text} "
            "Cost rule: mini/nano for smokes, 5.4 for normal hard work, 5.5/pro only when worth it."
        )

    def build_next_turn_status(self, planning):
        next_plan = (planning or {}).get("next_inference", {}) or {}
        if not has_effective_next_inference_plan(next_plan):
            return (
                "Next-turn override: none queued. Queue Next applies one model-turn override, "
                "then Aurora returns to normal routing; it does not approve or reorder pending commands."
            )
        return (
            f"Next-turn override queued: {self._format_next_inference(next_plan)}. "
            "It changes the next model turn only; pending commands remain in the pending lane."
        )

    def build_advanced_context_status(self, advanced):
        advanced = advanced or {}
        view_bits = [
            f"user text {'on' if advanced.get('show_user_text', True) else 'off'}",
            f"AI text {'on' if advanced.get('show_ai_text', True) else 'off'}",
            f"AI cmds {'shown' if not advanced.get('hide_ai_commands', False) else 'hidden'}",
            f"user cmds {'shown' if not advanced.get('hide_user_commands', False) else 'hidden'}",
        ]
        history_bits = [
            f"unimportant {'on' if advanced.get('enable_unimportant_messages', True) else 'off'}",
            f"important {'on' if advanced.get('enable_important_messages', True) else 'off'}",
            f"add UMsgs {'on' if advanced.get('add_umsgs_to_history', False) else 'off'}",
            f"add IMsgs {'on' if advanced.get('add_imsgs_to_history', False) else 'off'}",
            f"UMsg decay {'on' if advanced.get('check_umsgs_decay', False) else 'off'}",
            f"IMsg decay {'on' if advanced.get('check_imsgs_decay', False) else 'off'}",
        ]
        image_bits = [
            f"image {advanced.get('image_detail', 'low')}",
            f"latest {advanced.get('latest_image_detail', 'low')}",
            f"high count {advanced.get('high_detail', 0)}",
            f"max {advanced.get('max_images_in_history', 0)}",
        ]
        return (
            "View: "
            + ", ".join(view_bits)
            + " | History: "
            + ", ".join(history_bits)
            + " | Images: "
            + ", ".join(image_bits)
        )

    @staticmethod
    def get_state_path_value(state, path, default="-"):
        current = state or {}
        for part in path or ():
            if not isinstance(current, dict) or part not in current:
                return default
            current = current.get(part)
        return current

    @staticmethod
    def format_settings_safety_value(value):
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, dict):
            enabled = [str(key) for key, enabled_value in value.items() if bool(enabled_value)]
            if enabled:
                return ", ".join(sorted(enabled))
            return "none" if value else "empty"
        if isinstance(value, list):
            return f"{len(value)} rows" if value else "0 rows"
        if value is None or value == "":
            return "-"
        return short(value, 96)

    def format_settings_safety_item_value(self, state, item):
        paths = item.get("state_paths") or ()
        if paths:
            values = []
            for label, path in paths:
                value = self.get_state_path_value(state, path)
                values.append(f"{label}={self.format_settings_safety_value(value)}")
            return ", ".join(values)
        path = item.get("state_path")
        if not path:
            return str(item.get("value_hint", "-") or "-")
        return self.format_settings_safety_value(self.get_state_path_value(state, path))

    def count_settings_safety_classes(self):
        counts = {key: 0 for key in SETTING_SAFETY_CLASS_ORDER}
        for item in SETTING_SAFETY_INVENTORY:
            item_class = item.get("class", "advanced")
            counts[item_class] = counts.get(item_class, 0) + 1
        return counts

    def get_baseline_diff_totals(self, state):
        state = state or {}
        defaults = state.get("defaults", {}) or {}
        current = self.build_current_preferences_snapshot_from_state(state)

        def count_diffs(baseline, available=True):
            if not available or not isinstance(baseline, dict) or not baseline:
                return None
            _shown, _remaining, total = self.diff_preferences_against_baseline(current, baseline, limit=0)
            return total

        return {
            "system": count_diffs(defaults.get("system_profile", {}) or {}, defaults.get("system_available", True)),
            "personal": count_diffs(defaults.get("personal_profile", {}) or {}, defaults.get("personal_available", False)),
            "personal_available": bool(defaults.get("personal_available", False)),
            "system_available": bool(defaults.get("system_available", True)),
        }

    def build_recovery_home_snapshot(self, state):
        state = state or {}
        diagnostics = self.collect_recovery_diagnostics(state)
        non_ok = [item for item in diagnostics if item.get("level") != "ok"]
        warnings = [item for item in diagnostics if item.get("level") == "warning"]
        watches = [item for item in diagnostics if item.get("level") == "watch"]
        status = "warning" if warnings else "watch" if non_ok else "ok"
        primary = (warnings or watches or diagnostics or [{}])[0]
        primary_title = primary.get("title", "No obvious weird state")
        primary_action = primary.get("action", "Continue with the intended profile/test.")
        modes = state.get("modes", {}) or {}
        advanced = state.get("advanced", {}) or {}
        models = state.get("models", {}) or {}
        image_cost = state.get("image_cost_posture", {}) or {}
        queue_bridge = state.get("queue_bridge", {}) or (state.get("monitors", {}) or {}).get("queue_bridge", {}) or {}
        baseline_diffs = self.get_baseline_diff_totals(state)
        checkpoint = state.get("window_18_21_checkpoint_readiness", {}) or {}
        checkpoint_counts = checkpoint.get("counts", {}) or {}
        checkpoint_status_counts = checkpoint.get("status_counts", {}) or {}

        def read_count(mapping, key):
            try:
                return int(float((mapping or {}).get(key, 0) or 0))
            except Exception:
                return 0

        checkpoint_status = str(checkpoint.get("status", "not exported") or "not exported")
        checkpoint_ready = bool(
            checkpoint.get(
                "checkpoint_ready",
                checkpoint.get("ready_for_checkpoint", checkpoint.get("ready_for_checkpoint_when_authorized", False)),
            )
        )
        checkpoint_blocking = read_count(checkpoint_counts, "blocking_rows")
        checkpoint_warnings = read_count(checkpoint_status_counts, "warning")
        checkpoint_blocked = read_count(checkpoint_status_counts, "blocked")
        checkpoint_pending = read_count(checkpoint_status_counts, "pending")
        checkpoint_watch = read_count(checkpoint_status_counts, "watch")
        if checkpoint:
            checkpoint_summary = (
                f"{checkpoint_status} | ready={checkpoint_ready} | "
                f"warnings={checkpoint_warnings} | blocked={checkpoint_blocked} | pending={checkpoint_pending}"
            )
            if checkpoint_ready:
                if bool(checkpoint.get("stage_commit_performed", False)):
                    checkpoint_action = (
                        f"Window 18-21 checkpoint recorded at {checkpoint.get('checkpoint_commit', '-')}; "
                        "keep parked until a fresh handoff/window is opened."
                    )
                else:
                    checkpoint_action = "Ready for checkpoint only with explicit authorization; keep external validation current."
            else:
                checkpoint_action = "Run SHOW_CHECKPOINT_READINESS() and resolve the named warning rows before parking."
        else:
            checkpoint_summary = "not exported yet"
            checkpoint_action = "Run SHOW_CHECKPOINT_READINESS() after the runtime exports state."
        diagnostic_text = " ".join(
            f"{item.get('title', '')} {item.get('detail', '')} {item.get('action', '')}".lower()
            for item in diagnostics
            if item.get("level") != "ok"
        )

        profile_suggestions = []

        def add_profile(name, reason):
            if name not in RECOVERY_PROFILE_NAMES:
                return
            if any(row.get("name") == name for row in profile_suggestions):
                return
            profile_suggestions.append({"name": name, "reason": reason})

        if warnings:
            add_profile("Safe Offline", f"stabilize first: {warnings[0].get('title', 'warning')}")
        if checkpoint and not checkpoint_ready:
            add_profile("Safe Offline", f"checkpoint needs attention: {checkpoint_status}")
        if (
            "high-cost" in diagnostic_text
            or str(image_cost.get("status", "")).lower() in {"watch", "warning"}
            or str(models.get("text", "")).lower().startswith("gpt-5.5")
            or "pro" in str(models.get("text", "")).lower()
        ):
            add_profile("Minimal Cost", "lower model/image spend while inspecting drift")
        image_detail = str(advanced.get("image_detail", "low") or "low").lower()
        latest_detail = str(advanced.get("latest_image_detail", "low") or "low").lower()
        if image_detail in {"high", "original"} or latest_detail in {"high", "original"} or "image" in diagnostic_text:
            add_profile("Cheap Visual Test", "keep visual checks bounded and cheap")
        game_profile = str(state.get("game_profile") or (state.get("gameplay", {}) or {}).get("profile") or "").strip()
        if str(modes.get("action", "")).lower() == "gb" or game_profile:
            add_profile("Gameplay Test", "use the game-safe baseline before input probes")
        if bool(modes.get("live", False)) and not warnings:
            add_profile("Safe Live Model", "live-mode posture without desktop/game actions")
        if not profile_suggestions:
            add_profile("Safe Offline", "known quiet baseline for recovery")
            if not non_ok:
                add_profile("Safe Live Model", "next normal baseline if you want live observation")

        pending_count = len(state.get("pending_commands", []) or [])
        links = ["Overview", "Raw State"]
        if checkpoint:
            links.insert(0, "Checkpoint Readiness")
        if pending_count or not bool(queue_bridge.get("bridge_caught_up", True)):
            links.insert(0, "Pending")
        if "sub-agent" in diagnostic_text or "agent" in diagnostic_text:
            links.insert(0, "Agents")
            links.insert(1, "Pending")
        if "prompt" in diagnostic_text:
            links.insert(0, "Prompt Ledger")
        if "image" in diagnostic_text or str(image_cost.get("status", "")).lower() in {"watch", "warning"}:
            links.insert(0, "Image Index")
            links.insert(1, "Visual Context")
        if "stateful" in diagnostic_text or "responses" in diagnostic_text:
            links.insert(0, "Responses Shadow")
        links = list(dict.fromkeys(links))

        system_diff = baseline_diffs.get("system")
        personal_diff = baseline_diffs.get("personal")
        if personal_diff is None:
            restore_summary = "personal defaults not saved; system defaults available" if baseline_diffs.get("system_available") else "defaults unavailable"
            restore_action = "Save Personal once the current setup is a good baseline."
        elif personal_diff == 0:
            restore_summary = "current settings match personal defaults"
            restore_action = "Use Apply System only when you want Aurora's built-in baseline."
        elif system_diff == 0:
            restore_summary = "current settings match system defaults"
            restore_action = "Use Save Personal if this should become your baseline."
        else:
            restore_summary = f"system diff {system_diff if system_diff is not None else 'n/a'} | personal diff {personal_diff}"
            restore_action = "Use confirmed Apply System/Personal only after reading the diff."

        return {
            "schema_version": "recovery_home_v1",
            "status": status,
            "issue_count": len(non_ok),
            "warning_count": len(warnings),
            "watch_count": len(watches),
            "primary_title": primary_title,
            "primary_action": primary_action,
            "profile_suggestions": profile_suggestions[:4],
            "recommended_profile": (profile_suggestions[0] or {}).get("name", "-") if profile_suggestions else "-",
            "restore_summary": restore_summary,
            "restore_action": restore_action,
            "baseline_diffs": baseline_diffs,
            "checkpoint_status": checkpoint_status,
            "checkpoint_ready": checkpoint_ready,
            "checkpoint_summary": checkpoint_summary,
            "checkpoint_action": checkpoint_action,
            "checkpoint_counts": {
                "blocking_rows": checkpoint_blocking,
                "warning": checkpoint_warnings,
                "blocked": checkpoint_blocked,
                "pending": checkpoint_pending,
                "watch": checkpoint_watch,
            },
            "diagnostic_links": links[:8],
            "pending_count": pending_count,
        }

    def refresh_recovery_home_vars(self, state):
        if not hasattr(self, "recovery_home_risk_var"):
            return
        home = self.build_recovery_home_snapshot(state)
        suggestions = home.get("profile_suggestions", []) or []
        suggestion_text = "; ".join(
            f"{row.get('name', '-')}: {short(row.get('reason', ''), 74)}"
            for row in suggestions[:3]
        ) or "-"
        self.recovery_home_risk_var.set(
            f"{home.get('status', 'watch')} | issues {home.get('issue_count', 0)} "
            f"(warnings {home.get('warning_count', 0)}, watch {home.get('watch_count', 0)})\n"
            f"Primary: {short(home.get('primary_title', '-'), 96)}"
        )
        self.recovery_home_profile_var.set(suggestion_text)
        self.recovery_home_restore_var.set(
            f"{home.get('restore_summary', '-')}\n{short(home.get('restore_action', '-'), 110)}"
        )
        self.recovery_home_checkpoint_var.set(
            f"{short(home.get('checkpoint_summary', '-'), 110)}\n"
            f"{short(home.get('checkpoint_action', '-'), 110)}"
        )
        self.recovery_home_next_var.set(
            f"Next: {short(home.get('primary_action', '-'), 160)} | "
            f"Links: {', '.join(home.get('diagnostic_links', []) or ['Overview'])}"
        )

    def build_recovery_home_text(self, state):
        home = self.build_recovery_home_snapshot(state)
        lines = [
            "Recovery Home",
            "",
            (
                f"status={home.get('status', 'watch')} | issues={home.get('issue_count', 0)} | "
                f"warnings={home.get('warning_count', 0)} | watch={home.get('watch_count', 0)}"
            ),
            f"primary={home.get('primary_title', '-')}",
            f"next={home.get('primary_action', '-')}",
            "",
            "Suggested profiles:",
        ]
        for row in home.get("profile_suggestions", []) or []:
            lines.append(f"- {row.get('name', '-')}: {row.get('reason', '-')}")
        lines.extend(
            [
                "",
                "Restore confidence:",
                f"- {home.get('restore_summary', '-')}",
                f"- {home.get('restore_action', '-')}",
                "",
                "Checkpoint readiness:",
                f"- {home.get('checkpoint_summary', '-')}",
                f"- {home.get('checkpoint_action', '-')}",
                "",
                "Diagnostic links: " + ", ".join(home.get("diagnostic_links", []) or ["Overview"]),
            ]
        )
        return "\n".join(lines).strip()

    def build_operator_risk_summary_text(self, risk_summary, limit_rows=6):
        risk_summary = risk_summary if isinstance(risk_summary, dict) else {}
        counts = risk_summary.get("counts", {}) or {}
        lines = [
            "Operator Risk Summary",
            "",
            (
                f"status={risk_summary.get('status', 'not exported')} | "
                f"schema={risk_summary.get('schema_version', '-') or '-'} | "
                f"summary={risk_summary.get('summary', '-') or '-'}"
            ),
            (
                f"risks: cost={counts.get('cost_risk', '-')} | action={counts.get('action_risk', '-')} | "
                f"context={counts.get('context_risk', '-')} | commands={counts.get('command_risk', '-')} | "
                f"transport={counts.get('transport_risk', '-')} | access={counts.get('access_risk', '-')}"
            ),
            (
                f"counts: pending={counts.get('pending_commands', 0)} | due={counts.get('due_pending_commands', 0)} | "
                f"stale_due={counts.get('stale_due_pending_commands', 0)} | prompt_watch_rows={counts.get('prompt_watch_rows', 0)} | "
                f"agent_candidates={counts.get('agent_suggestion_candidates', 0)} | staged={counts.get('agent_suggestion_staged_candidates', 0)}"
            ),
            "",
            "Rows:",
        ]
        rows = [row for row in (risk_summary.get("rows", []) or []) if isinstance(row, dict)]
        for row in rows[:limit_rows]:
            lines.append(
                f"- {row.get('label', row.get('key', 'row'))}: {row.get('status', 'watch')} | "
                f"{short(row.get('summary', '-') or '-', 180)}"
            )
            detail = row.get("detail", "")
            if detail:
                lines.append(f"  Detail: {short(detail, 190)}")
            action = row.get("operator_action", "")
            if action:
                lines.append(f"  Try: {short(action, 180)}")
        next_actions = risk_summary.get("next_actions", []) or []
        if next_actions:
            lines.extend(["", "Next actions:"])
            for action in next_actions[:4]:
                lines.append(f"- {short(action, 220)}")
        guardrails = risk_summary.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Guardrails:"])
            for guardrail in guardrails[:4]:
                lines.append(f"- {short(guardrail, 220)}")
        return "\n".join(lines).strip()

    def build_settings_safety_summary(self, state):
        state = state or {}
        counts = self.count_settings_safety_classes()
        diagnostics = self.collect_recovery_diagnostics(state)
        home = self.build_recovery_home_snapshot(state)
        operator_risk = state.get("operator_risk_summary", {}) or {}
        operator_risk_counts = operator_risk.get("counts", {}) or {}
        prompt_inclusion = state.get("prompt_inclusion_readiness", {}) or {}
        prompt_inclusion_counts = prompt_inclusion.get("counts", {}) or {}
        checkpoint = state.get("window_18_21_checkpoint_readiness", {}) or {}
        checkpoint_counts = checkpoint.get("counts", {}) or {}
        issue_count = len([item for item in diagnostics if item.get("level") != "ok"])
        locks = state.get("locks", {}) or {}
        locked_count = sum(1 for value in locks.values() if bool(value))
        pending_count = len(state.get("pending_commands", []) or [])
        next_plan = (state.get("planning", {}) or {}).get("next_inference", {}) or {}
        summary_bits = [
            f"home {home.get('status', 'watch')}",
            f"risk {operator_risk.get('status', 'not exported')}",
            f"prompt inclusion {prompt_inclusion.get('status', 'not exported')}",
            f"prompt flags {prompt_inclusion_counts.get('hard_guardrail_flags', 0)}",
            f"checkpoint {checkpoint.get('status', 'not exported')}",
            f"checkpoint blocks {checkpoint_counts.get('blocking_rows', 0)}",
            f"cost {operator_risk_counts.get('cost_risk', '-')}",
            f"action {operator_risk_counts.get('action_risk', '-')}",
            f"commands {operator_risk_counts.get('command_risk', '-')}",
            f"profile {home.get('recommended_profile', '-')}",
            f"{len(SETTING_SAFETY_INVENTORY)} mapped controls",
            f"diagnostics {issue_count}",
            f"recovery {counts.get('recovery-critical', 0)}",
            f"risky {counts.get('risky', 0)}",
            f"hidden-candidate {counts.get('hidden-by-default', 0)}",
            f"locks {locked_count}",
            f"pending {pending_count}",
            f"next-turn {'queued' if has_effective_next_inference_plan(next_plan) else 'empty'}",
        ]
        return "Settings safety: " + " | ".join(summary_bits)

    def collect_recovery_diagnostics(self, state):
        state = state or {}
        modes = state.get("modes", {}) or {}
        models = state.get("models", {}) or {}
        model_status = state.get("model_status", {}) or {}
        planning = state.get("planning", {}) or {}
        scheduler = state.get("scheduler", {}) or {}
        advanced = state.get("advanced", {}) or {}
        visual_context = state.get("visual_context", {}) or {}
        visual_summary = visual_context.get("summary", {}) or {}
        operator_risk = state.get("operator_risk_summary", {}) or {}
        prompt_ledger = state.get("prompt_context_ledger", {}) or {}
        prompt_summary = prompt_ledger.get("summary", {}) or {}
        prompt_inclusion = state.get("prompt_inclusion_readiness", {}) or {}
        prompt_inclusion_counts = prompt_inclusion.get("counts", {}) or {}
        checkpoint = state.get("window_18_21_checkpoint_readiness", {}) or {}
        checkpoint_counts = checkpoint.get("counts", {}) or {}
        monitors = state.get("monitors", {}) or {}
        queue_bridge = state.get("queue_bridge", {}) or monitors.get("queue_bridge", {}) or {}
        locks = state.get("locks", {}) or {}
        security = state.get("security", {}) or {}
        pending_rows = state.get("pending_commands", []) or []
        next_plan = planning.get("next_inference", {}) or {}
        diagnostics = []

        def add(level, title, detail, action):
            diagnostics.append(
                {
                    "level": level,
                    "title": title,
                    "detail": detail,
                    "action": action,
                }
            )

        def to_int(value, default=0):
            try:
                return int(float(value))
            except Exception:
                return default

        live_on = bool(modes.get("live", False))
        execution_mode = str(modes.get("execution", "") or "").lower()
        action_mode = str(modes.get("action", "") or "").lower()
        auth_summary = str(state.get("auth_summary", "") or "").lower()
        if live_on and ("unresolved" in auth_summary or "missing" in auth_summary):
            add("warning", "Live mode with unresolved auth", state.get("auth_summary", "-"), "Use SHOW_AUTH() or turn Live Off while fixing auth.")
        if live_on and action_mode in {"pyag", "gb"} and execution_mode != "safe":
            add("warning", "Live model can propose executable actions", f"execution={execution_mode}, action={action_mode}", "Use Safe Offline or Safe Live Model when setting up.")
        if execution_mode == "auto":
            add("warning", "Execution mode is auto", "auto reduces operator friction for actions", "Return to safe or assist unless this is an intentional run.")
        if action_mode == "pyag":
            add("watch", "Desktop action mode is PYAG", "desktop automation path is active", "Use action none for observation-only work.")
        if has_effective_next_inference_plan(next_plan):
            add("watch", "Next-turn override queued", self._format_next_inference(next_plan), "Clear it if the test is over.")
        locked = [name for name, enabled in locks.items() if bool(enabled)]
        if locked:
            add("watch", "Runtime locks are active", ", ".join(sorted(locked)), "Use SHOW_LOCKS() before debugging ignored settings.")
        if pending_rows:
            add("watch", "Pending commands exist", f"{len(pending_rows)} pending row(s)", "Review Pending before switching profiles or live mode.")
        command_risk_row = next(
            (
                row for row in (operator_risk.get("rows", []) or [])
                if isinstance(row, dict) and row.get("key") == "command_insertion_execution"
            ),
            {},
        )
        command_risk_status = str(command_risk_row.get("status", "") or "").lower()
        command_risk_detail = str(command_risk_row.get("detail", "") or "")
        if command_risk_status == "warning":
            add(
                "warning",
                "Command insertion / execution risk needs attention",
                command_risk_detail or command_risk_row.get("summary", "-"),
                "Open Agents and Pending before approving any command path.",
            )
        elif command_risk_status == "watch" and "gated=True" in command_risk_detail:
            add(
                "watch",
                "Sub-agent Pending insert is exact-confirm gated",
                command_risk_detail,
                "Use SHOW_AGENT_PENDING_INSERT_CHECKLIST() and Pending before approving anything.",
            )
        if to_int(queue_bridge.get("stale_due_count", 0)) > 0:
            add("warning", "Pending queue has stale due commands", f"stale_due={queue_bridge.get('stale_due_count', 0)}", "Inspect Pending and Queue / Bridge monitor.")
        if not bool(queue_bridge.get("bridge_caught_up", True)):
            add("warning", "Raw bridge is behind", "latest inbox has not fully caught up", "Wait or inspect the bridge log before retrying commands.")
        if not bool(queue_bridge.get("command_result_caught_up", True)):
            add("watch", "Command-result log is behind", "recent command result is not caught up", "Wait for result logging before interpreting state.")
        if bool(scheduler.get("demand_capture_pending", False)):
            add("watch", "Demand capture is pending", str(scheduler.get("demand_capture_reason", "capture") or "capture"), "Let the capture settle before judging visual state.")
        if live_on and not bool(scheduler.get("demand_capture_enabled", True)):
            add("watch", "Demand capture is disabled while live", "live visual turns may rely only on timer capture", "Enable demand capture for controlled visual probes.")
        image_detail = str(advanced.get("image_detail", "low") or "low").lower()
        latest_detail = str(advanced.get("latest_image_detail", "low") or "low").lower()
        if image_detail in {"high", "original"} or latest_detail in {"high", "original"}:
            add("watch", "High-detail image settings", f"image={image_detail}, latest={latest_detail}", "Use low/auto for cheap checks; use Model Status for support.")
        max_images = to_int(advanced.get("max_images_in_history", 0))
        prior_limit = to_int(visual_summary.get("prompt_prior_image_limit", 0))
        if max_images and prior_limit and max_images > prior_limit:
            add(
                "watch",
                "Retained images exceed prompt prior-image limit",
                f"max_images={max_images}, prompt_prior_limit={prior_limit}",
                "Use Visual Context and Prompt Ledger rather than model self-report.",
            )
        active_profile = str((model_status.get("stateful_preset_family", {}) or {}).get("active_profile", "stateless-default") or "")
        if active_profile and active_profile != "stateless-default":
            add("watch", "Stateful preview profile selected", active_profile, "Remember this is metadata-only until a future transport slice.")
        active_models = [
            str(models.get("text", "") or ""),
            str(models.get("vision", "") or ""),
            str(models.get("reasoning", "") or ""),
        ]
        expensive_models = [name for name in active_models if "pro" in name.lower() or name.lower().startswith("gpt-5.5")]
        if expensive_models:
            add("watch", "High-cost model family selected", ", ".join(sorted(set(expensive_models))), "Use Budget/Mini for smoke tests unless this is intentional.")
        if bool(security.get("passcode_required", False)) and not bool(security.get("authorized", False)):
            add("watch", "External operator access is locked", "passcode required but not authorized", "Authorize or use local panel controls.")
        monitor_status = str(monitors.get("overall_status", "ok") or "ok").lower()
        if monitor_status not in {"ok", "green"}:
            add("warning", "Monitor stack is not clean", format_monitor_summary(monitors), "Open Monitor/Raw State before trusting a live test.")
        omitted_rows = to_int(prompt_summary.get("omitted_rows", 0))
        included_rows = to_int(prompt_summary.get("included_rows", 0))
        if omitted_rows > included_rows and included_rows > 0:
            add("watch", "Prompt Ledger is omitting more than it includes", f"included={included_rows}, omitted={omitted_rows}", "Inspect Prompt Ledger before widening context.")
        if int(prompt_inclusion_counts.get("hard_guardrail_flags", 0) or 0) > 0:
            add(
                "warning",
                "Prompt Inclusion guardrail flags are active",
                f"flags={prompt_inclusion_counts.get('hard_guardrail_flags', 0)}",
                "Use SHOW_PROMPT_INCLUSION_READINESS() before any Prompt Pin/drop activation work.",
            )
        checkpoint_ready = bool(
            checkpoint.get(
                "checkpoint_ready",
                checkpoint.get("ready_for_checkpoint", checkpoint.get("ready_for_checkpoint_when_authorized", False)),
            )
        )
        if checkpoint and not checkpoint_ready:
            add(
                "warning",
                "Checkpoint readiness needs attention",
                f"status={checkpoint.get('status', '-')} | blocking={checkpoint_counts.get('blocking_rows', 0)}",
                "Use SHOW_CHECKPOINT_READINESS() before parking or any explicit future checkpoint request.",
            )
        if not diagnostics:
            add("ok", "No obvious weird state", "common recovery checks are quiet", "Continue with the intended profile/test.")
        return diagnostics

    def build_recovery_diagnostics_text(self, state):
        diagnostics = self.collect_recovery_diagnostics(state)
        lines = ["What Looks Weird Right Now", ""]
        for item in diagnostics:
            lines.append(f"[{item.get('level', 'watch').upper()}] {item.get('title', '-')}")
            lines.append(f"  Detail: {item.get('detail', '-')}")
            lines.append(f"  Try: {item.get('action', '-')}")
        return "\n".join(lines).strip()

    @staticmethod
    def normalize_preference_value(value):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return round(float(value), 6)
        if isinstance(value, str):
            text = value.strip()
            lowered = text.lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            try:
                return round(float(text), 6)
            except Exception:
                return lowered
        if isinstance(value, (list, tuple)):
            return tuple(AuroraControlPanel.normalize_preference_value(item) for item in value)
        if isinstance(value, dict):
            return tuple(
                sorted(
                    (str(key), AuroraControlPanel.normalize_preference_value(nested_value))
                    for key, nested_value in value.items()
                )
            )
        return str(value)

    @staticmethod
    def flatten_preferences(payload, prefix=""):
        rows = {}
        if not isinstance(payload, dict):
            return rows
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                rows.update(AuroraControlPanel.flatten_preferences(value, path))
            else:
                rows[path] = value
        return rows

    def build_current_preferences_snapshot_from_state(self, state):
        state = state or {}
        modes = state.get("modes", {}) or {}
        models = state.get("models", {}) or {}
        planning = state.get("planning", {}) or {}
        scheduler = state.get("scheduler", {}) or {}
        overlay = state.get("overlay", {}) or {}
        advanced = state.get("advanced", {}) or {}
        game_profile = (
            state.get("game_profile")
            or (state.get("gameplay", {}) or {}).get("profile")
            or planning.get("game_profile")
            or "-"
        )
        return {
            "auth_mode": modes.get("auth"),
            "execution_mode": modes.get("execution"),
            "action_mode": modes.get("action"),
            "game_profile": game_profile,
            "text_model": models.get("text"),
            "vision_model": models.get("vision"),
            "reasoning_model": models.get("reasoning"),
            "reasoning_effort": models.get("reasoning_effort"),
            "battle_reasoning_effort": models.get("battle_reasoning_effort"),
            "review_reasoning_effort": models.get("review_reasoning_effort"),
            "critique_reasoning_effort": models.get("critique_reasoning_effort"),
            "verbosity": models.get("verbosity"),
            "battle_verbosity": models.get("battle_verbosity"),
            "review_verbosity": models.get("review_verbosity"),
            "critique_verbosity": models.get("critique_verbosity"),
            "summary_mode": models.get("summary_mode"),
            "temperature": models.get("temperature"),
            "screenshot_interval": modes.get("screenshot_interval"),
            "turn_scheduler_profile": scheduler.get("profile"),
            "turn_scheduler_mode": scheduler.get("mode"),
            "turn_heartbeat_seconds": scheduler.get("heartbeat_seconds"),
            "turn_min_gap_seconds": scheduler.get("min_gap_seconds"),
            "turn_capture_wake_enabled": scheduler.get("capture_wake_enabled"),
            "turn_capture_wake_debounce_seconds": scheduler.get("capture_wake_debounce_seconds"),
            "turn_post_action_settle_seconds": scheduler.get("post_action_settle_seconds"),
            "demand_capture_enabled": scheduler.get("demand_capture_enabled"),
            "auto_dynamic_inference": planning.get("auto_dynamic_inference", models.get("auto_dynamic_inference")),
            "review_turn_interval": planning.get("review_turn_interval", models.get("review_turn_interval")),
            "critique_turn_interval": planning.get("critique_turn_interval", models.get("critique_turn_interval")),
            "pending_queue_mode": planning.get("pending_queue_mode", models.get("pending_queue_mode")),
            "command_drip_retention_turns": planning.get("command_drip_retention_turns"),
            "command_drip_lookahead_turns": planning.get("command_drip_lookahead_turns"),
            "command_drip_show_variants": planning.get("command_drip_show_variants"),
            "command_drip_show_likely_dropped": planning.get("command_drip_show_likely_dropped"),
            "load_live_init_prompt": modes.get("load_live_init_prompt"),
            "sound_effects": modes.get("sound_effects"),
            "time_logging": modes.get("time_logging"),
            "chat_log_echo": modes.get("chat_log_echo"),
            "overlay": {
                "tile_grid": overlay.get("tile_grid"),
                "cursor_label": overlay.get("cursor_label"),
                "keypoint_grid": overlay.get("keypoint_grid"),
                "status_text": overlay.get("status_text"),
            },
            "advanced": {
                "auto_prompt": advanced.get("auto_prompt"),
                "always_on": advanced.get("always_on"),
                "hide_input": advanced.get("hide_input"),
                "image_detail": advanced.get("image_detail"),
                "latest_image_detail": advanced.get("latest_image_detail"),
                "high_detail": advanced.get("high_detail"),
                "max_images_in_history": advanced.get("max_images_in_history"),
                "show_user_text": advanced.get("show_user_text"),
                "show_ai_text": advanced.get("show_ai_text"),
                "show_ai_commands": advanced.get("show_ai_commands", not bool(advanced.get("hide_ai_commands", False))),
                "show_user_commands": advanced.get("show_user_commands", not bool(advanced.get("hide_user_commands", False))),
                "enable_unimportant_messages": advanced.get("enable_unimportant_messages"),
                "enable_important_messages": advanced.get("enable_important_messages"),
                "add_umsgs_to_history": advanced.get("add_umsgs_to_history"),
                "add_imsgs_to_history": advanced.get("add_imsgs_to_history"),
                "check_umsgs_decay": advanced.get("check_umsgs_decay"),
                "check_imsgs_decay": advanced.get("check_imsgs_decay"),
            },
        }

    def diff_preferences_against_baseline(self, current, baseline, limit=18):
        current_flat = self.flatten_preferences(current)
        baseline_flat = self.flatten_preferences(baseline)
        diffs = []
        for key in sorted(baseline_flat.keys()):
            current_value = current_flat.get(key)
            baseline_value = baseline_flat.get(key)
            if self.normalize_preference_value(current_value) != self.normalize_preference_value(baseline_value):
                diffs.append((key, current_value, baseline_value))
        return diffs[:limit], max(0, len(diffs) - limit), len(diffs)

    def build_baseline_diff_text(self, state):
        state = state or {}
        defaults = state.get("defaults", {}) or {}
        current = self.build_current_preferences_snapshot_from_state(state)

        def format_baseline(title, baseline, available=True):
            if not available or not isinstance(baseline, dict) or not baseline:
                return [f"{title}: not available"]
            shown, remaining, total = self.diff_preferences_against_baseline(current, baseline)
            lines = [f"{title}: {total} difference(s) from current state"]
            if total == 0:
                lines.append("- current settings match this baseline")
                return lines
            for key, current_value, baseline_value in shown:
                lines.append(
                    f"- {key}: current={short(current_value, 54)} | baseline={short(baseline_value, 54)}"
                )
            if remaining:
                lines.append(f"- ... {remaining} more difference(s)")
            return lines

        lines = [
            "Baseline Diff / Restore",
            "",
            "Apply System, Apply Personal, and Save Personal on this tab use existing Aurora default-profile commands.",
            "The diff below is advisory; runtime command results remain the source of truth after a restore.",
            "",
        ]
        lines.extend(format_baseline("System defaults", defaults.get("system_profile", {}) or {}, defaults.get("system_available", True)))
        lines.append("")
        if defaults.get("personal_error"):
            lines.append("Personal defaults " + str(defaults.get("personal_status", "error")) + ": " + str(defaults["personal_error"]))
        lines.extend(format_baseline("Personal defaults", defaults.get("personal_profile", {}) or {}, defaults.get("personal_available", False)))
        return "\n".join(lines).strip()

    def build_settings_safety_text(self, state):
        state = state or {}
        counts = self.count_settings_safety_classes()
        lines = [
            "Settings Safety Inventory",
            "",
            "This is read-only. It does not hide controls or change defaults yet.",
            "It gives a novice/intermediate/technician map of which knobs are ordinary, which are recovery levers, and which deserve caution.",
            "",
            self.build_settings_safety_summary(state),
            "",
            self.build_recovery_home_text(state),
            "",
            self.build_operator_risk_summary_text(state.get("operator_risk_summary", {}) or {}),
            "",
            self.build_recovery_diagnostics_text(state),
            "",
            self.build_baseline_diff_text(state),
            "",
            "Class counts: "
            + ", ".join(
                f"{SETTING_SAFETY_CLASS_LABELS.get(class_name, class_name)}={counts.get(class_name, 0)}"
                for class_name in SETTING_SAFETY_CLASS_ORDER
            ),
            "",
        ]
        for class_name in SETTING_SAFETY_CLASS_ORDER:
            label = SETTING_SAFETY_CLASS_LABELS.get(class_name, class_name)
            class_items = [item for item in SETTING_SAFETY_INVENTORY if item.get("class") == class_name]
            lines.append(label)
            lines.append("-" * len(label))
            for item in class_items:
                lines.append(f"- {item.get('name', '-')}: {self.format_settings_safety_item_value(state, item)}")
                lines.append(f"  Surface: {item.get('surface', '-')}")
                lines.append(f"  Novice: {item.get('novice', '-')}")
                lines.append(f"  Intermediate: {item.get('intermediate', '-')}")
                lines.append(f"  Technician: {item.get('commands', '-')}")
            lines.append("")
        return "\n".join(lines).strip()

    def build_cadence_status_lines(self, state=None, status=None):
        state = state or self.state_cache or {}
        status = status or state.get("model_status", {}) or {}
        modes = state.get("modes", {}) or {}
        scheduler = state.get("scheduler", {}) or {}

        configured_interval = status.get("screenshot_interval_seconds")
        if configured_interval in {None, ""}:
            configured_interval = modes.get("screenshot_interval")
        effective_interval = status.get("effective_screenshot_interval_seconds")
        if effective_interval in {None, ""}:
            effective_interval = modes.get("effective_screenshot_interval", configured_interval)
        idle_floor = status.get("idle_screenshot_interval_floor_seconds")
        if idle_floor in {None, ""}:
            idle_floor = modes.get("idle_screenshot_interval_floor")
        pending_reasons = ", ".join(scheduler.get("pending_reasons", []) or []) or "-"
        capture_counter = scheduler.get("capture_counter", "-")
        last_wake = scheduler.get("last_wake_reason", "") or "-"
        command_wake = "pending" if scheduler.get("pending_command_result", False) else "clear"
        demand_capture = "off"
        if scheduler.get("demand_capture_enabled", status.get("demand_capture_enabled", True)):
            demand_capture = "pending" if scheduler.get("demand_capture_pending", False) else "on"
        demand_reason = scheduler.get("demand_capture_reason") or scheduler.get("demand_capture_last_reason") or "-"
        return [
            (
                f"capture configured {format_runtime_seconds(configured_interval)} | "
                f"effective {format_runtime_seconds(effective_interval)} | "
                f"idle floor {format_runtime_seconds(idle_floor)}"
            ),
            (
                f"panel refresh {format_runtime_seconds(REFRESH_INTERVAL_MS / 1000.0)} | "
                f"scheduler {scheduler.get('profile', status.get('turn_scheduler_profile', 'balanced'))} / "
                f"{scheduler.get('mode', status.get('turn_scheduler_mode', 'hybrid'))}"
            ),
            (
                f"heartbeat {format_runtime_seconds(scheduler.get('heartbeat_seconds', status.get('turn_heartbeat_seconds')))} | "
                f"min gap {format_runtime_seconds(scheduler.get('min_gap_seconds', status.get('turn_min_gap_seconds')))} | "
                f"capture debounce {format_runtime_seconds(scheduler.get('capture_wake_debounce_seconds', status.get('turn_capture_wake_debounce_seconds')))}"
            ),
            (
                f"capture wake {'on' if scheduler.get('capture_wake_enabled', status.get('turn_capture_wake_enabled', True)) else 'off'} | "
                f"post-action settle {format_runtime_seconds(scheduler.get('post_action_settle_seconds', status.get('turn_post_action_settle_seconds')))} | "
                f"command-result wake {command_wake}"
            ),
            f"observation wake: demand capture {demand_capture} | reason {demand_reason}",
            f"capture counter {capture_counter} | last wake {last_wake} | pending reasons {pending_reasons}",
        ]

    def build_model_status_text(self, status):
        status = status or {}
        profiles = status.get("profiles", {}) or {}
        stateful_family = status.get("stateful_preset_family", {}) or {}
        stateful_profiles = stateful_family.get("profiles", []) or []
        catalog = (self.state_cache or {}).get("model_catalog", {}) or {}
        builtin_names = [entry.get("name", "") for entry in (catalog.get("builtin", []) or []) if entry.get("name")]
        custom_names = [entry.get("name", "") for entry in (catalog.get("custom", []) or []) if entry.get("name")]

        def format_profile(label, profile):
            profile = profile or {}
            badges = []
            supported_efforts = profile.get("supported_reasoning_efforts", []) or []
            if profile.get("supports_reasoning_effort", False):
                effort_text = "effort:" + ",".join(supported_efforts) if supported_efforts else "effort"
                badges.append(effort_text)
            if profile.get("supports_temperature_override", False):
                badges.append("temp")
            if profile.get("supports_verbosity", False):
                badges.append("verbosity")
            if profile.get("supports_original_image_detail", False):
                badges.append("image:original")
            if profile.get("supports_reasoning_summary", False):
                badges.append("summary")
            badge_text = " ".join(f"[{badge}]" for badge in badges) or "[basic]"
            pricing = profile.get("pricing_usd_per_1m", {}) or {}
            price_text = f" | {format_model_pricing_compact(pricing)}" if pricing else ""
            note_text = f" | {profile.get('pricing_note')}" if profile.get("pricing_note") else ""
            return (
                f"{label}: {profile.get('name', '-')}"
                f" | source={profile.get('source', '-')}"
                f" | {badge_text}"
                f"{price_text}"
                f"{note_text}"
            )

        stateful_profile_summary = "; ".join(
            (
                f"{profile.get('name', '-')} "
                f"[{profile.get('state_mode', '-')} | {profile.get('transport_status', '-')}]"
            )
            for profile in stateful_profiles
        ) or "-"
        stateful_notes = stateful_family.get("notes", []) or []
        lines = [
            "Catalog",
            f"- built-in: {len(builtin_names)}",
            f"- custom: {len(custom_names)}",
            f"- built-in models: {', '.join(builtin_names) if builtin_names else '-'}",
            f"- custom models: {', '.join(custom_names) if custom_names else '-'}",
            "",
            "Active models",
            f"- text: {status.get('text_model', '-')}",
            f"- vision: {status.get('vision_model', '-')}",
            f"- reasoning: {status.get('reasoning_model', '-')}",
            f"- temperature: {status.get('temperature', '-')}",
            f"- screenshot interval: {status.get('screenshot_interval_seconds', '-')}s",
            f"- effective screenshot interval: {status.get('effective_screenshot_interval_seconds', status.get('screenshot_interval_seconds', '-'))}s",
            "",
            "Cadence and wake conditions",
            *[f"- {line}" for line in self.build_cadence_status_lines(status=status)],
            "",
            "Reasoning and verbosity",
            f"- transport: {status.get('transport', 'chat_completions')}",
            f"- Responses session: {status.get('responses_reasoning', {}).get('status', '-')} | completed {status.get('responses_reasoning', {}).get('completed_responses', 0)}",
            f"- Responses effort: effective {status.get('responses_reasoning', {}).get('effective_effort') or '-'} | request baseline {status.get('responses_reasoning', {}).get('request_level_effort') or '-'} | API reported {status.get('responses_reasoning', {}).get('api_reported_effort') or '-'}",
            f"- Responses context: {status.get('responses_reasoning', {}).get('last_input_tokens', 0)} / {status.get('responses_reasoning', {}).get('max_input_tokens', '-')} input tokens | cached {status.get('responses_reasoning', {}).get('last_cached_tokens')}",
            f"- Responses block: {status.get('responses_reasoning', {}).get('blocked_reason') or 'none'}",
            f"- session/default: effort {status.get('reasoning_effort', '-')} | verbosity {status.get('verbosity', '-')}",
            f"- review: effort {status.get('review_reasoning_effort', '-')} | verbosity {status.get('review_verbosity', '-')}",
            f"- battle: effort {status.get('battle_reasoning_effort', '-')} | verbosity {status.get('battle_verbosity', '-')}",
            f"- critique: effort {status.get('critique_reasoning_effort', '-')} | verbosity {status.get('critique_verbosity', '-')}",
            f"- summary mode: {status.get('summary_mode', '-')}",
            f"- dynamic inference: {status.get('auto_dynamic_inference', False)}",
            "",
            "Stateful preset family",
            f"- status: {stateful_family.get('status', 'metadata_only')} | active {stateful_family.get('active_profile', 'stateless-default')}",
            f"- mode/path: {stateful_family.get('active_state_mode', 'stateless')} / {stateful_family.get('active_api_path', 'chat/completions')}",
            f"- live transport: {stateful_family.get('live_transport', 'chat/completions')} | changed {stateful_family.get('transport_changed', False)}",
            f"- state ids: conversation {stateful_family.get('conversation_id') or '-'} | previous response {stateful_family.get('previous_response_id') or '-'}",
            f"- recap policy: {stateful_family.get('recap_policy', 'normal stateless recap/history')}",
            f"- profiles: {stateful_profile_summary}",
            "",
            "Planning and scheduler",
            f"- scene: {status.get('gameplay_scene', 'unknown')} | {status.get('gameplay_scene_summary', '-')}",
            f"- next inference source: {status.get('next_inference_source', 'default')}",
            f"- open questions/stale/failures/alternatives: {status.get('active_questions_count', 0)}/{status.get('stale_assumptions_count', 0)}/{status.get('known_failures_count', 0)}/{status.get('candidate_alternatives_count', 0)}",
            f"- scheduler: {status.get('turn_scheduler_profile', 'balanced')} / {status.get('turn_scheduler_mode', 'hybrid')}",
            f"- review/critique intervals: {status.get('review_turn_interval', '-')} / {status.get('critique_turn_interval', '-')}",
            f"- heartbeat/min gap/debounce/settle: {status.get('turn_heartbeat_seconds', '-')} / {status.get('turn_min_gap_seconds', '-')} / {status.get('turn_capture_wake_debounce_seconds', '-')} / {status.get('turn_post_action_settle_seconds', '-')}",
            f"- capture wake: {status.get('turn_capture_wake_enabled', True)}",
            f"- queue: {status.get('pending_queue_mode', 'normal')} | variants {status.get('command_drip_show_variants', True)} | likely dropped {status.get('command_drip_show_likely_dropped', True)}",
            f"- queue meaning: {format_pending_queue_mode_semantics(status.get('pending_queue_mode', 'normal'))}",
            f"- effort multipliers review/battle/critique: {status.get('review_effort_multiplier', '-')} / {status.get('battle_effort_multiplier', '-')} / {status.get('critique_effort_multiplier', '-')}",
            f"- approx cycles review/battle/critique: {status.get('approx_review_cycle_seconds', '-')}s / {status.get('approx_battle_review_cycle_seconds', '-')}s / {status.get('approx_critique_cycle_seconds', '-')}s",
            f"- next inference: {self._format_next_inference(status.get('next_inference', {}))}",
            "",
            "Capability and cost",
            format_profile("text_profile", profiles.get("text")),
            format_profile("vision_profile", profiles.get("vision")),
            format_profile("reasoning_profile", profiles.get("reasoning")),
        ]
        notes = status.get("notes", []) or []
        if stateful_notes:
            lines.append("")
            lines.extend(f"stateful note: {note}" for note in stateful_notes)
        if notes:
            lines.append("")
            lines.extend(f"note: {note}" for note in notes)
        return "\n".join(lines)

    def _format_next_inference(self, next_plan):
        next_plan = next_plan or {}
        if not isinstance(next_plan, dict):
            return "none"
        parts = []
        for key in ("reasoning_effort", "verbosity", "summary_mode", "image_detail", "latest_image_detail", "temperature", "model", "text_model", "vision_model", "reasoning_model"):
            value = short(next_plan.get(key, ""), 40)
            if value:
                parts.append(f"{key}={value}")
        if next_plan.get("note"):
            parts.append(f"note={short(next_plan.get('note', ''), 60)}")
        if next_plan.get("target_turn"):
            parts.append(f"target_turn={next_plan.get('target_turn')}")
        return " | ".join(parts) if parts else "none"

    def build_prompt_inclusion_readiness_text(self, readiness, limit_rows=8):
        readiness = readiness if isinstance(readiness, dict) else {}
        counts = readiness.get("counts", {}) or {}
        lines = [
            "Prompt Inclusion Readiness",
            "",
            (
                f"status={readiness.get('status', 'not exported')} | "
                f"schema={readiness.get('schema_version', '-') or '-'} | "
                f"summary={readiness.get('summary', '-') or '-'}"
            ),
            (
                f"activation_enabled={readiness.get('activation_enabled', False)} | "
                f"ready_for_operator_review={readiness.get('ready_for_operator_review', False)} | "
                f"guardrail_flags={counts.get('hard_guardrail_flags', 0)}"
            ),
            (
                f"approved_prompt_pins={counts.get('approved_prompt_pin_candidates', 0)} | "
                f"approved_do_not_include={counts.get('approved_do_not_include_candidates', 0)} | "
                f"active_marks={counts.get('active_context_marks', 0)} | "
                f"staged_agent_suggestions={counts.get('staged_agent_suggestions', 0)}"
            ),
            "",
            "Readiness rows:",
        ]
        rows = [row for row in (readiness.get("rows", []) or []) if isinstance(row, dict)]
        if not rows:
            lines.append("-")
        for row in rows[:limit_rows]:
            lines.append(
                f"- {row.get('label', row.get('key', 'row'))}: {row.get('status', 'watch')} | "
                f"{short(row.get('summary', '-') or '-', 180)}"
            )
            action = row.get("operator_action", "")
            if action:
                lines.append(f"  next={short(action, 180)}")
        preview = readiness.get("candidate_preview", {}) or {}
        prompt_pins = preview.get("prompt_pins", []) or []
        do_not_include = preview.get("do_not_include", []) or []
        if prompt_pins or do_not_include:
            lines.extend(["", "Approved candidate preview:"])
            for row in prompt_pins[:6]:
                if isinstance(row, dict):
                    lines.append(
                        f"- pin {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"{short(row.get('target', '-') or '-', 150)}"
                    )
            for row in do_not_include[:6]:
                if isinstance(row, dict):
                    lines.append(
                        f"- drop {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"{short(row.get('target', '-') or '-', 150)}"
                    )
        guardrail_flags = readiness.get("hard_guardrail_flags", []) or []
        if guardrail_flags:
            lines.extend(["", "Enabled guardrail flags:"])
            lines.extend(f"- {short(item, 120)}" for item in guardrail_flags[:12])
        guardrails = readiness.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_inclusion_preview_text(self, preview, limit_rows=8):
        preview = preview if isinstance(preview, dict) else {}
        counts = preview.get("counts", {}) or {}
        lines = [
            "Prompt Inclusion No-Send Preview",
            "",
            (
                f"status={preview.get('status', 'not exported')} | "
                f"id={preview.get('preview_id', '-') or '-'} | "
                f"schema={preview.get('schema_version', '-') or '-'} | "
                f"summary={preview.get('summary', '-') or '-'}"
            ),
            (
                f"send_enabled={preview.get('send_enabled', False)} | "
                f"activation_enabled={preview.get('activation_enabled', False)} | "
                f"payload_changed={preview.get('model_payload_changed', False)}"
            ),
            (
                f"current_rows={counts.get('current_payload_rows', 0)} | "
                f"would_add={counts.get('proposed_additions', 0)} | "
                f"would_omit={counts.get('proposed_omissions', 0)} | "
                f"guardrail_flags={counts.get('hard_guardrail_flags', 0)}"
            ),
        ]
        current_rows = preview.get("current_payload_preview", []) or []
        if current_rows:
            lines.extend(["", "Current included rows (unchanged):"])
            for row in current_rows[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('label', '-') or '-', 70)} | "
                        f"count={row.get('count', 0)} | {row.get('status', '-')} | {row.get('source', '-')}"
                    )
        proposed_additions = preview.get("proposed_additions", []) or []
        proposed_omissions = preview.get("proposed_omissions", []) or []
        if proposed_additions:
            lines.extend(["", "Would add if activated:"])
            for row in proposed_additions[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"{row.get('status', '-')} | target={short(row.get('target', '-') or '-', 150)}"
                    )
        if proposed_omissions:
            lines.extend(["", "Would omit if enforcement activated:"])
            for row in proposed_omissions[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"{row.get('status', '-')} | target={short(row.get('target', '-') or '-', 150)}"
                    )
        plan = preview.get("activation_plan", []) or []
        if plan:
            lines.extend(["", "Activation plan:"])
            for row in plan[:6]:
                if isinstance(row, dict):
                    lines.append(f"- {row.get('step', '-')}: {row.get('status', '-')} | {short(row.get('summary', '-') or '-', 170)}")
        guardrails = preview.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Preview guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_inclusion_rehearsal_text(self, rehearsal, limit_rows=8):
        rehearsal = rehearsal if isinstance(rehearsal, dict) else {}
        counts = rehearsal.get("counts", {}) or {}
        checks = rehearsal.get("checks", {}) or {}
        lines = [
            "Prompt Inclusion Rehearsal",
            "",
            (
                f"status={rehearsal.get('status', 'not run')} | "
                f"schema={rehearsal.get('schema_version', '-') or '-'} | "
                f"summary={rehearsal.get('summary', '-') or '-'}"
            ),
            (
                f"send_enabled={rehearsal.get('send_enabled', False)} | "
                f"activation_enabled={rehearsal.get('activation_enabled', False)} | "
                f"payload_changed={rehearsal.get('model_payload_changed', False)}"
            ),
            (
                f"created={counts.get('created_marks', 0)} | "
                f"cleared={counts.get('cleared_marks', 0)} | "
                f"would_add={counts.get('rehearsal_additions', 0)} | "
                f"would_omit={counts.get('rehearsal_omissions', 0)} | "
                f"active_after={counts.get('active_rehearsal_marks_after', 0)}"
            ),
            (
                f"checks diff={checks.get('expected_diff_rows_present', False)} | "
                f"rollback={checks.get('rollback_commands_present', False)} | "
                f"cleared={checks.get('temporary_marks_cleared', False)} | "
                f"no_send={checks.get('no_send_flags_ok', False)}"
            ),
        ]
        error_text = str(rehearsal.get("error", "") or "").strip()
        if error_text:
            lines.append(f"error={short(error_text, 180)}")
        rows = rehearsal.get("rehearsal_diff_rows", []) or []
        if rows:
            lines.extend(["", "Rehearsal diff rows:"])
            for row in rows[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {row.get('change_type', '-')}: {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"{row.get('status', '-')} | target={short(row.get('target', '-') or '-', 150)}"
                    )
        rollback = rehearsal.get("rollback_commands", []) or []
        if rollback:
            lines.extend(["", "Rollback commands observed:"])
            lines.extend(f"- {short(item, 190)}" for item in rollback[:limit_rows])
        guardrails = rehearsal.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Rehearsal guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_inclusion_activation_checklist_text(self, checklist, limit_rows=8):
        checklist = checklist if isinstance(checklist, dict) else {}
        counts = checklist.get("counts", {}) or {}
        lines = [
            "Prompt Inclusion Activation Review",
            "",
            (
                f"status={checklist.get('status', 'not exported')} | "
                f"id={checklist.get('checklist_id', '-') or '-'} | "
                f"preview={checklist.get('preview_id', '-') or '-'} | "
                f"schema={checklist.get('schema_version', '-') or '-'} | "
                f"summary={checklist.get('summary', '-') or '-'}"
            ),
            (
                f"activation_available={checklist.get('activation_control_available', False)} | "
                f"activation_enabled={checklist.get('activation_enabled', False)} | "
                f"ready_for_review={checklist.get('ready_for_activation_review', False)} | "
                f"ready_for_model_visible_activation={checklist.get('ready_for_model_visible_activation', False)}"
            ),
            (
                f"checks={counts.get('required_checks_passed', 0)}/{counts.get('required_checks', 0)} | "
                f"current_diff={counts.get('current_diff_rows', 0)} | "
                f"rehearsal=+{counts.get('rehearsal_additions', 0)}/-{counts.get('rehearsal_omissions', 0)} | "
                f"rollback_commands={counts.get('rollback_commands', 0)}"
            ),
        ]
        rows = checklist.get("rows", []) or []
        if rows:
            lines.extend(["", "Activation review rows:"])
            for row in rows[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {row.get('label', row.get('key', 'row'))}: {row.get('status', 'watch')} | "
                        f"{short(row.get('summary', '-') or '-', 180)}"
                    )
                    action = row.get("operator_action", "")
                    if action:
                        lines.append(f"  next={short(action, 180)}")
        steps = checklist.get("activation_steps", []) or []
        if steps:
            lines.extend(["", "Activation steps:"])
            for row in steps[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(f"- {row.get('step', '-')}: {row.get('status', '-')} | {short(row.get('summary', '-') or '-', 170)}")
        rollback = checklist.get("rollback_commands", []) or []
        if rollback:
            lines.extend(["", "Rollback commands:"])
            lines.extend(f"- {short(item, 190)}" for item in rollback[:limit_rows])
        future = checklist.get("future_activation_command_shape", []) or []
        if future:
            lines.extend(["", "Future command shape:"])
            lines.extend(f"- {short(item, 190)}" for item in future[:limit_rows])
        guardrails = checklist.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Activation review guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_inclusion_activation_text(self, activation_snapshot, limit_rows=8):
        activation_snapshot = activation_snapshot if isinstance(activation_snapshot, dict) else {}
        activation = activation_snapshot.get("activation", {}) or {}
        proof = activation_snapshot.get("offline_proof", {}) or {}
        counts = activation_snapshot.get("counts", {}) or {}
        lines = [
            "Prompt Inclusion Activation State",
            "",
            (
                f"status={activation_snapshot.get('status', 'off')} | "
                f"schema={activation_snapshot.get('schema_version', '-') or '-'} | "
                f"summary={activation_snapshot.get('summary', '-') or '-'}"
            ),
            (
                f"enabled={activation.get('enabled', False)} | "
                f"include_pins={activation.get('include_prompt_pins', False)} | "
                f"enforce_drops={activation.get('enforce_do_not_include', False)} | "
                f"payload_mutation_allowed={activation.get('live_model_payload_mutation_allowed', False)}"
            ),
            (
                f"preview={activation.get('preview_id', '-') or '-'} | "
                f"checklist={activation.get('checklist_id', '-') or '-'} | "
                f"proof={activation.get('offline_proof_id', '-') or '-'}:{activation.get('offline_proof_status', 'not_run')}"
            ),
            (
                f"active_pins={counts.get('active_prompt_pins', 0)} | "
                f"active_omissions={counts.get('active_omissions', 0)} | "
                f"omitted_recent_rows={counts.get('omitted_recent_history_rows', 0)} | "
                f"payload_messages={counts.get('payload_messages_added', 0)}"
            ),
        ]
        additions = proof.get("prompt_pin_additions", []) or []
        if additions:
            lines.extend(["", "Active Prompt Pin additions:"])
            for row in additions[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"target={short(row.get('target', '-') or '-', 110)} | "
                        f"{short(row.get('content', '-') or '-', 170)}"
                    )
        omissions = proof.get("do_not_include_omissions", []) or []
        if omissions:
            lines.extend(["", "Active do-not-include omissions:"])
            for row in omissions[:limit_rows]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('mark_id', '-') or '-', 42)} | "
                        f"target={short(row.get('target', '-') or '-', 110)} | matched={row.get('matched_count', 0)}"
                    )
        rollback = activation_snapshot.get("rollback_commands", []) or []
        if rollback:
            lines.extend(["", "Activation rollback:"])
            lines.extend(f"- {short(item, 190)}" for item in rollback[:limit_rows])
        guardrails = activation_snapshot.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Activation state guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_inclusion_closure_text(self, closure, limit_rows=10):
        closure = closure if isinstance(closure, dict) else {}
        if not closure:
            return "Prompt Inclusion Closure\n- not exported yet"
        counts = closure.get("status_counts", {}) or {}
        proof_counts = closure.get("counts", {}) or {}
        lines = [
            "Prompt Inclusion Closure",
            (
                f"status={closure.get('status', 'not_exported')} | "
                f"ready_for_window_close={closure.get('ready_for_window_close', False)} | "
                f"schema={closure.get('schema_version', '-') or '-'}"
            ),
            (
                f"closure_id={closure.get('closure_id', '-') or '-'} | "
                f"activation={closure.get('activation_status', 'off')} | "
                f"enabled={closure.get('activation_enabled', False)} | "
                f"proof={closure.get('offline_proof_id', '-') or '-'}:{closure.get('offline_proof_status', 'not_run')}"
            ),
            f"evidence_source={closure.get('closure_evidence_source', 'runtime_snapshot')}",
            (
                f"checks ok={counts.get('ok', 0)} | watch={counts.get('watch', 0)} | "
                f"warning={counts.get('warning', 0)} | blocked={counts.get('blocked', 0)} | pending={counts.get('pending', 0)}"
            ),
            (
                f"proof pins={proof_counts.get('active_prompt_pins', 0)} | "
                f"omissions={proof_counts.get('active_omissions', 0)} | "
                f"omitted_rows={proof_counts.get('omitted_recent_history_rows', 0)} | "
                f"payload_messages={proof_counts.get('payload_messages_added', 0)}"
            ),
        ]
        checks = closure.get("checks", []) or []
        if checks:
            lines.extend(["", "Closure checks:"])
            for row in checks[:limit_rows]:
                line = f"- {row.get('label', row.get('key', '-'))}: {row.get('status', 'watch')} | {short(row.get('summary', '-') or '-', 170)}"
                action = row.get("operator_action", "")
                if action:
                    line += f" | action={short(action, 120)}"
                lines.append(line)
        blocking = closure.get("blocking_rows", []) or []
        if blocking:
            lines.extend(["", "Blocking rows:"])
            for row in blocking[:limit_rows]:
                lines.append(f"- {row.get('label', row.get('key', '-'))}: {row.get('status', 'warning')} | {short(row.get('summary', '-') or '-', 170)}")
        evidence = closure.get("operator_evidence_required", []) or []
        if evidence:
            lines.extend(["", "Closure evidence:"])
            lines.extend(f"- {short(item, 190)}" for item in evidence[:7])
        guardrails = closure.get("guardrails", []) or []
        if guardrails:
            lines.extend(["", "Closure guardrails:"])
            lines.extend(f"- {short(item, 190)}" for item in guardrails[:5])
        return "\n".join(lines).strip()

    def build_prompt_ledger_text(self, ledger, context_marks=None, prompt_inclusion_readiness=None, prompt_inclusion_preview=None, prompt_inclusion_rehearsal=None, prompt_inclusion_activation_checklist=None, prompt_inclusion_activation=None, prompt_inclusion_closure=None):
        ledger = ledger or {}
        if not isinstance(ledger, dict):
            return "No prompt ledger exported yet."
        summary = ledger.get("summary", {}) or {}
        caps = ledger.get("caps", {}) or {}
        lines = [
            "[Summary]",
            (
                f"mode={summary.get('mode', 'eligible_now_estimate')} | "
                f"model={summary.get('model', '-') or '-'} | "
                f"messages={summary.get('message_count', 0)}"
            ),
            (
                f"included_rows={summary.get('included_rows', 0)} | "
                f"prompt_pin_rows={summary.get('prompt_pin_rows', 0)} | "
                f"do_not_include_rows={summary.get('do_not_include_rows', 0)} | "
                f"retained_rows={summary.get('retained_rows', 0)} | "
                f"available_rows={summary.get('available_rows', 0)} | "
                f"retrievable_rows={summary.get('retrievable_rows', 0)} | "
                f"omitted_rows={summary.get('omitted_rows', 0)}"
            ),
            (
                f"activation={'on' if summary.get('prompt_inclusion_activation_enabled', False) else 'off'} | "
                f"proof={summary.get('prompt_inclusion_offline_proof_status', 'not_run')} | "
                f"pins_active={summary.get('prompt_pins_active', 0)} | "
                f"pins_visible_next={summary.get('prompt_pin_model_visible_next_turn', 0)} | "
                f"drops_enforced={summary.get('do_not_include_enforcement_enabled', False)} | "
                f"drop_marks_active={summary.get('do_not_include_active_omission_marks', 0)}"
            ),
            (
                f"raw_chat={summary.get('raw_chat_entries', 0)} | "
                f"text={summary.get('raw_text_entries', 0)} | "
                f"images={summary.get('raw_image_entries', 0)} | "
                f"important_text={summary.get('important_text_entries', 0)}"
            ),
            (
                f"agent_registry_sub_agents={summary.get('agent_registry_sub_agents', 0)} | "
                f"agent_registry_active={summary.get('agent_registry_active_sub_agents', 0)} | "
                f"agent_model_visible_next={summary.get('agent_registry_model_visible_next_turn', 0)}"
            ),
            (
                f"agent_history_acl_rows={summary.get('agent_history_acl_rows', 0)} | "
                f"agent_private_history_paths={summary.get('agent_private_history_paths', 0)} | "
                f"agent_private_history_files={summary.get('agent_private_history_files', 0)} | "
                f"history_private={summary.get('agent_private_history_private_events', 0)} | "
                f"history_parent_visible={summary.get('agent_private_history_parent_visible_events', 0)}"
            ),
            (
                f"history_operator_append={summary.get('agent_private_history_operator_append_enabled', False)} | "
                f"history_model_visible={summary.get('agent_private_history_model_visible_events', 0)} | "
                f"parent_history_writes={summary.get('agent_parent_history_writes_enabled', False)}"
            ),
            (
                f"agent_suggestion_routes={summary.get('agent_suggestion_route_rows', 0)} | "
                f"policy_tagged={summary.get('agent_suggestion_policy_tagged_rows', 0)} | "
                f"audit_rows={summary.get('agent_suggestion_audit_rows', 0)} | "
                f"policy_blocked={summary.get('agent_suggestion_policy_blocked', 0)}"
            ),
            (
                f"suggestion_approved={summary.get('agent_suggestion_approved', 0)} | "
                f"suggestion_requested={summary.get('agent_suggestion_requested', 0)} | "
                f"suggestion_rejected={summary.get('agent_suggestion_rejected', 0)} | "
                f"staged_candidates={summary.get('agent_suggestion_staged_candidates', 0)}"
            ),
            (
                f"suggestion_pending_candidates={summary.get('agent_suggestion_pending_candidates', 0)} | "
                f"provenance_rows={summary.get('agent_suggestion_prompt_ledger_provenance_rows', 0)} | "
                f"candidate_staging={summary.get('agent_suggestion_candidate_staging_enabled', False)} | "
                f"pending_insertions={summary.get('agent_suggestion_pending_insertions', 0)} | "
                f"pending_insert={summary.get('agent_suggestion_pending_insert_enabled', False)} | "
                f"suggestion_execution={summary.get('agent_suggestion_execution_enabled', False)}"
            ),
            (
                f"suggestion_context_marks={summary.get('agent_suggestion_context_mark_links', 0)} | "
                f"context_mark_provenance={summary.get('agent_suggestion_provenance_marks', 0)} | "
                f"model_visible_promotion={summary.get('agent_suggestion_model_visible_promotion_enabled', False)}"
            ),
            (
                f"caps: text={caps.get('max_text_context_messages', '-')} | "
                f"prior_images={caps.get('max_image_context_messages', '-')} | "
                f"retained_images={caps.get('max_images_in_history', '-')} | "
                f"state_items={caps.get('max_state_items_per_section', '-')}"
            ),
        ]
        notes = ledger.get("notes", []) or []
        if notes:
            lines.append("")
            lines.append("[Notes]")
            lines.extend(f"- {short(note, 180)}" for note in notes if str(note or "").strip())

        if isinstance(prompt_inclusion_readiness, dict) and prompt_inclusion_readiness:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_readiness_text(prompt_inclusion_readiness, limit_rows=8).splitlines())

        if isinstance(prompt_inclusion_preview, dict) and prompt_inclusion_preview:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_preview_text(prompt_inclusion_preview, limit_rows=8).splitlines())

        if isinstance(prompt_inclusion_rehearsal, dict) and prompt_inclusion_rehearsal:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_rehearsal_text(prompt_inclusion_rehearsal, limit_rows=8).splitlines())

        if isinstance(prompt_inclusion_activation_checklist, dict) and prompt_inclusion_activation_checklist:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_activation_checklist_text(prompt_inclusion_activation_checklist, limit_rows=8).splitlines())

        if isinstance(prompt_inclusion_activation, dict) and prompt_inclusion_activation:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_activation_text(prompt_inclusion_activation, limit_rows=8).splitlines())

        if isinstance(prompt_inclusion_closure, dict) and prompt_inclusion_closure:
            lines.append("")
            lines.extend(self.build_prompt_inclusion_closure_text(prompt_inclusion_closure, limit_rows=10).splitlines())

        lanes = ledger.get("lanes", {}) or {}
        lane_titles = (
            ("included_this_turn", "Included This Turn"),
            ("prompt_pins", "Prompt Pins Preview"),
            ("retained_locally", "Retained Locally"),
            ("available_on_disk", "Available On Disk"),
            ("retrievable", "Retrievable"),
            ("dropped_omitted", "Dropped / Omitted"),
            ("controls", "Controls And Planned Marks"),
        )
        for key, title in lane_titles:
            rows = lanes.get(key, []) or []
            lines.append("")
            lines.append(f"[{title}]")
            if not rows:
                lines.append("-")
                continue
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    continue
                label = row.get("label") or row.get("source") or "-"
                count = row.get("count", 0)
                status = row.get("status", "-") or "-"
                source = row.get("source", "-") or "-"
                reason = short(row.get("reason", ""), 190)
                lines.append(f"{index}. {short(label, 72)} | count={count} | {status} | {source}")
                if reason:
                    lines.append(f"   reason={reason}")
                details = row.get("details", {}) or {}
                if details:
                    try:
                        detail_text = json.dumps(details, ensure_ascii=False, sort_keys=True)
                    except Exception:
                        detail_text = str(details)
                    lines.append(f"   details={short(detail_text, 220)}")

        marks = context_marks or {}
        if isinstance(marks, dict):
            marks_summary = marks.get("summary", {}) or {}
            lines.append("")
            lines.append("[Context Marks Policy]")
            lines.append(
                f"mode={marks_summary.get('mode', 'metadata_policy_scaffold')} | "
                f"writable={marks_summary.get('writable_marks_enabled', False)} | "
                f"model_visible_mutation={marks_summary.get('model_visible_mutation_enabled', False)}"
            )
            lines.append(
                f"prompt_pins_active={marks_summary.get('prompt_pins_active', 0)} | "
                f"prompt_pin_marks={marks_summary.get('prompt_pin_marks', 0)} | "
                f"approved_prompt_pin_marks={marks_summary.get('approved_prompt_pin_marks', 0)} | "
                f"operator_pins_partial={marks_summary.get('operator_pins_partial', 0)} | "
                f"important_text={marks_summary.get('important_text_entries', 0)}"
            )
            lines.append(
                f"active_marks={marks_summary.get('dedicated_mark_store_entries', 0)} | "
                f"do_not_include_marks={marks_summary.get('do_not_include_marks', 0)} | "
                f"model_visible_marks={marks_summary.get('model_visible_marks', 0)}"
            )
            active_marks = marks.get("active_marks", []) or []
            if active_marks:
                lines.append("")
                lines.append("[Writable Marks]")
                for mark_index, mark in enumerate(active_marks[:12], start=1):
                    if not isinstance(mark, dict):
                        continue
                    lines.append(
                        f"{mark_index}. {short(mark.get('mark_id', '-') or '-', 36)} | "
                        f"{short(mark.get('label', mark.get('mark_type', '-')) or '-', 42)} | "
                        f"approval={mark.get('approval_state', 'draft')} | model_visible_next_turn={mark.get('model_visible_next_turn', False)} | "
                        f"omission_active={mark.get('prompt_omission_active', False)}"
                    )
                    lines.append(f"   target={short(mark.get('target', '') or '-', 160)}")
                    if mark.get("value"):
                        lines.append(f"   value={short(mark.get('value', ''), 160)}")
                    if mark.get("note"):
                        lines.append(f"   note={short(mark.get('note', ''), 160)}")
            mark_rows = marks.get("mark_types", []) or []
            if mark_rows:
                lines.append("")
                lines.append("[Mark Types]")
                for row in mark_rows:
                    if not isinstance(row, dict):
                        continue
                    influences = ", ".join(row.get("influences", []) or []) or "-"
                    lines.append(
                        f"- {short(row.get('label', row.get('name', '-')), 48)} | "
                        f"{row.get('status', '-')} | {short(influences, 90)}"
                    )
                    current = short(row.get("current_behavior", ""), 190)
                    if current:
                        lines.append(f"  current={current}")
            control_rows = marks.get("active_controls", []) or []
            if control_rows:
                lines.append("")
                lines.append("[Current Mark-Adjacent Controls]")
                for row in control_rows:
                    if not isinstance(row, dict):
                        continue
                    influences = ", ".join(row.get("influences", []) or []) or "-"
                    lines.append(f"- {short(row.get('label', row.get('name', '-')), 54)} | {row.get('status', '-')} | {short(influences, 100)}")
            guardrails = marks.get("guardrails", []) or []
            if guardrails:
                lines.append("")
                lines.append("[Guardrails]")
                lines.extend(f"- {short(item, 190)}" for item in guardrails if str(item or "").strip())
        return "\n".join(lines).strip()

    def build_agent_registry_text(self, registry, agent_suggestions=None, agent_tasks=None, agent_pending_gate=None, agent_pending_insert_dry_run=None, agent_helper_closure=None):
        registry = registry or {}
        if not isinstance(registry, dict):
            return "No Agent Registry exported yet."
        agent_suggestions = agent_suggestions or {}
        if not isinstance(agent_suggestions, dict):
            agent_suggestions = {}
        agent_tasks = agent_tasks or {}
        if not isinstance(agent_tasks, dict):
            agent_tasks = {}
        agent_pending_gate = agent_pending_gate or {}
        if not isinstance(agent_pending_gate, dict):
            agent_pending_gate = {}
        agent_pending_insert_dry_run = agent_pending_insert_dry_run or {}
        if not isinstance(agent_pending_insert_dry_run, dict):
            agent_pending_insert_dry_run = {}
        agent_helper_closure = agent_helper_closure or {}
        if not isinstance(agent_helper_closure, dict):
            agent_helper_closure = {}
        summary = registry.get("summary", {}) or {}
        suggestions_summary = agent_suggestions.get("summary", {}) or {}
        task_summary = agent_tasks.get("summary", {}) or {}
        gate_summary = agent_pending_gate.get("summary", {}) or {}
        dry_run_summary = agent_pending_insert_dry_run.get("summary", {}) or {}
        closure_counts = agent_helper_closure.get("counts", {}) or {}
        closure_status_counts = agent_helper_closure.get("status_counts", {}) or {}
        private_history = registry.get("private_history", {}) or {}
        private_history_summary = private_history.get("summary", {}) or {}
        private_history_by_agent = {
            row.get("agent_id", ""): row
            for row in (private_history.get("rows", []) or [])
            if isinstance(row, dict)
        }
        lines = [
            "[Summary]",
            (
                f"mode={summary.get('mode', 'metadata_only_registry')} | "
                f"sub_agents={summary.get('sub_agent_count', 0)} | "
                f"active={summary.get('active_sub_agents', 0)} | silenced={summary.get('silenced_sub_agents', 0)}"
            ),
            (
                f"workers_enabled={summary.get('worker_processes_enabled', False)} | "
                f"model_spawn={summary.get('model_worker_spawn_enabled', False)} | "
                f"suggestion_execution={summary.get('suggestion_execution_enabled', False)}"
            ),
            (
                f"requested_model_visible_scopes={summary.get('requested_model_visible_next_turn_scopes', 0)} | "
                f"effective_model_visible_next_turn={summary.get('effective_model_visible_next_turn', 0)} | "
                f"effective_shared_append={summary.get('effective_shared_append', 0)}"
            ),
            (
                f"history_acl_rows={summary.get('history_acl_preview_rows', 0)} | "
                f"private_history_paths={summary.get('private_history_path_rows', 0)} | "
                f"private_history_files={summary.get('private_history_files_existing', 0)} | "
                f"private_history_events={summary.get('private_history_events_scanned', 0)}"
            ),
            (
                f"private_history_parent_visible={private_history_summary.get('parent_visible_event_count', 0)} | "
                f"private_history_private={private_history_summary.get('private_event_count', 0)} | "
                f"operator_append={private_history_summary.get('operator_private_history_append_enabled', False)} | "
                f"parent_history_write={private_history_summary.get('parent_chat_history_write_enabled', False)}"
            ),
            (
                f"parent_history_writes_effective={summary.get('effective_parent_history_writes', 0)} | "
                f"sub_agent_parent_reads_effective={summary.get('effective_sub_agent_parent_reads', 0)}"
            ),
            (
                f"suggestion_routes={summary.get('suggestion_route_rows', 0)} | "
                f"active_routes={summary.get('active_suggestion_route_rows', 0)} | "
                f"policy_tagged={summary.get('suggestion_policy_tagged_rows', 0)} | "
                f"audit_rows={suggestions_summary.get('suggestion_count', 0)} | "
                f"blocked={suggestions_summary.get('policy_blocked_suggestions', 0)}"
            ),
            (
                f"pending_candidates={suggestions_summary.get('pending_command_candidates', 0)} | "
                f"staged_candidates={suggestions_summary.get('staged_pending_candidates', 0)} | "
                f"provenance_links={suggestions_summary.get('context_mark_links', 0)} | "
                f"pending_insertions={suggestions_summary.get('pending_command_insertions', 0)} | "
                f"pending_insert={suggestions_summary.get('pending_command_insertion_enabled', False)} | "
                f"execute={suggestions_summary.get('command_execution_enabled', False)}"
            ),
            (
                f"task_packets={task_summary.get('task_count', 0)} | "
                f"active_tasks={task_summary.get('active_tasks', 0)} | review_tasks={task_summary.get('review_tasks', 0)} | "
                f"parent_visible_tasks={task_summary.get('parent_visible_tasks', 0)} | "
                f"prompt_ledger_visible_tasks={task_summary.get('prompt_ledger_visible_tasks', 0)} | "
                f"task_execute={task_summary.get('command_execution_enabled', False)}"
            ),
            (
                f"review_links={gate_summary.get('review_links', 0)} | "
                f"gate_ready={gate_summary.get('metadata_ready_rows', 0)} | "
                f"gate_open={gate_summary.get('pending_gate_open_rows', 0)} | "
                f"gate_insert_enabled={gate_summary.get('pending_command_insertion_enabled', False)} | "
                f"gate_execute={gate_summary.get('command_execution_enabled', False)}"
            ),
            (
                f"closure={agent_helper_closure.get('status', 'not_exported')} | "
                f"ready={agent_helper_closure.get('ready_for_window_close', False)} | "
                f"ok={closure_status_counts.get('ok', 0)} | watch={closure_status_counts.get('watch', 0)} | "
                f"warning={closure_status_counts.get('warning', 0)} | blocked={closure_status_counts.get('blocked', 0)}"
            ),
            (
                f"closure_pending_total={closure_counts.get('pending_queue_total', 0)} | "
                f"sub_agent_current={closure_counts.get('sub_agent_pending_current', 0)} | "
                f"manual_required={closure_counts.get('manual_approval_current', 0)} | "
                f"execute_enabled={closure_counts.get('command_execution_enabled', False)} | "
                f"model_visible_enabled={closure_counts.get('model_visible_enabled', False)}"
            ),
            f"store={summary.get('store_path', '-') or '-'}",
            f"history_dir={summary.get('history_dir', '-') or '-'}",
            f"suggestion_store={suggestions_summary.get('store_path', '-') or '-'}",
            f"task_store={task_summary.get('store_path', '-') or '-'}",
            "",
        ]
        lines.append("[Closure Readiness]")
        lines.append(
            f"schema={agent_helper_closure.get('schema_version', '-') or '-'} | "
            f"window={agent_helper_closure.get('window', '-') or '-'} | "
            f"slice={agent_helper_closure.get('slice', '-') or '-'} | "
            f"status={agent_helper_closure.get('status', 'not_exported')} | "
            f"ready={agent_helper_closure.get('ready_for_window_close', False)}"
        )
        lines.append(
            f"ok={closure_status_counts.get('ok', 0)} | watch={closure_status_counts.get('watch', 0)} | "
            f"warning={closure_status_counts.get('warning', 0)} | blocked={closure_status_counts.get('blocked', 0)} | "
            f"pending={closure_status_counts.get('pending', 0)}"
        )
        lines.append(
            f"pending_total={closure_counts.get('pending_queue_total', 0)} | "
            f"sub_agent_current={closure_counts.get('sub_agent_pending_current', 0)} | "
            f"manual_required={closure_counts.get('manual_approval_current', 0)} | "
            f"contract_ready={closure_counts.get('contract_ready_rows', 0)} | "
            f"would_insert={closure_counts.get('would_insert_rows', 0)} | "
            f"insertions={closure_counts.get('pending_command_insertions', 0)}"
        )
        lines.append(
            f"execute_enabled={closure_counts.get('command_execution_enabled', False)} | "
            f"model_visible_enabled={closure_counts.get('model_visible_enabled', False)} | "
            f"workers={closure_counts.get('worker_processes_enabled', False)} | "
            f"model_spawn={closure_counts.get('model_worker_spawn_enabled', False)} | "
            f"exact_confirm={closure_counts.get('exact_confirm_pending_insertion_enabled', False)}"
        )
        for row in (agent_helper_closure.get("checks", []) or [])[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 56)} | "
                f"{row.get('status', 'watch')} | {short(row.get('summary', '-') or '-', 150)}"
            )

        lines.append("")
        lines.append("[Parent]")
        parent = registry.get("parent_agent", {}) or {}
        lines.append(
            f"{parent.get('agent_id', 'parent')} | {parent.get('name', 'Aurora Parent')} | "
            f"role={parent.get('role', 'parent_ai')} | status={parent.get('status', 'active')}"
        )
        lines.append(f"history_scopes={', '.join(parent.get('history_scopes', []) or []) or '-'}")

        lines.append("")
        lines.append("[Sub-Agents]")
        agents = registry.get("agents", []) or []
        if not agents:
            lines.append("-")
        for index, agent in enumerate(agents, start=1):
            if not isinstance(agent, dict):
                continue
            acl = agent.get("history_acl", {}) or {}
            lines.append(
                f"{index}. {short(agent.get('agent_id', '-') or '-', 40)} | "
                f"{short(agent.get('name', '-') or '-', 56)} | "
                f"role={short(agent.get('role', '-') or '-', 52)} | "
                f"status={agent.get('status', '-')} | rank={agent.get('rank', 0)} | urgency={agent.get('urgency', 0)}"
            )
            lines.append(f"   history_scopes={', '.join(agent.get('history_scopes', []) or []) or '-'}")
            lines.append(
                f"   parent_read={acl.get('parent_can_read', True)} | "
                f"shared_append_effective={acl.get('effective_shared_append', False)} | "
                f"model_visible_next_turn_effective={acl.get('effective_model_visible_next_turn', False)}"
            )
            lines.append(
                f"   private_history={short(agent.get('private_history_path', '-') or '-', 180)} | "
                f"audit={short(agent.get('audit_log_path', '-') or '-', 180)}"
            )
            history_row = private_history_by_agent.get(agent.get("agent_id", ""))
            if history_row:
                lines.append(
                    f"   history_events={history_row.get('event_count', 0)} | "
                    f"private={history_row.get('private_event_count', 0)} | "
                    f"parent_visible={history_row.get('parent_visible_event_count', 0)} | "
                    f"append_allowed={history_row.get('operator_append_allowed', False)}"
                )
                if history_row.get("latest_summary"):
                    lines.append(f"   latest_history={short(history_row.get('latest_summary', ''), 180)}")
            lines.append(
                f"   allow={short(', '.join(agent.get('command_allow', []) or []) or '-', 160)}"
            )
            lines.append(
                f"   deny={short(', '.join(agent.get('command_deny', []) or []) or '-', 160)}"
            )
            if agent.get("note"):
                lines.append(f"   note={short(agent.get('note', ''), 180)}")

        lines.append("")
        lines.append("[Task Packets]")
        lines.append(
            f"mode={task_summary.get('mode', 'metadata_only_task_packets')} | "
            f"tasks={task_summary.get('task_count', 0)} | active={task_summary.get('active_tasks', 0)} | "
            f"review={task_summary.get('review_tasks', 0)} | blocked={task_summary.get('blocked_tasks', 0)} | "
            f"closed={task_summary.get('closed_tasks', 0)}"
        )
        lines.append(
            f"parent_visible={task_summary.get('parent_visible_tasks', 0)} | "
            f"prompt_ledger_visible={task_summary.get('prompt_ledger_visible_tasks', 0)} | "
            f"suggestion_links={task_summary.get('suggestion_links', 0)} | "
            f"gate_ready={task_summary.get('pending_gate_metadata_ready_rows', 0)} | "
            f"pending_insertions={task_summary.get('pending_command_insertions', 0)} | "
            f"insert_enabled={task_summary.get('pending_command_insertion_enabled', False)} | "
            f"execute={task_summary.get('command_execution_enabled', False)} | "
            f"model_visible={task_summary.get('model_visible_tasks', 0)}"
        )
        for row in (agent_tasks.get("recent_tasks", []) or [])[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('task_id', '-') or '-', 48)} | "
                f"agent={short(row.get('agent_id', '-') or '-', 30)} | "
                f"status={row.get('status', '-')} | priority={row.get('priority', 0)} | "
                f"visible={row.get('prompt_ledger_visible', False)}"
            )
            lines.append(f"  title={short(row.get('title', '') or '-', 180)}")
            objective = row.get("objective", "")
            if objective:
                lines.append(f"  objective={short(objective, 190)}")
            lines.append(
                f"  pending_inserted={row.get('pending_command_inserted', False)} | "
                f"suggestion_links={row.get('suggestion_link_count', 0)} | "
                f"gate_ready={row.get('pending_gate_metadata_ready', False)} | "
                f"execute={row.get('command_execution_enabled', False)} | "
                f"model_visible_now={row.get('model_visible_now', False)} | "
                f"tags={short(', '.join(row.get('policy_tags', []) or []) or '-', 160)}"
            )
            linked = row.get("linked_suggestion_ids", []) or []
            if linked:
                lines.append(f"  linked_suggestions={short(', '.join(linked), 180)}")
        for guardrail in ((agent_tasks.get("policy", {}) or {}).get("guardrails", []) or [])[:4]:
            lines.append(f"- {short(guardrail, 190)}")

        lines.append("")
        lines.append("[Pending Gate Review]")
        lines.append(
            f"mode={gate_summary.get('mode', 'metadata_only_pending_gate_review')} | "
            f"links={gate_summary.get('review_links', 0)} | metadata_ready={gate_summary.get('metadata_ready_rows', 0)} | "
            f"gate_open={gate_summary.get('pending_gate_open_rows', 0)}"
        )
        lines.append(
            f"pending_insertions={gate_summary.get('pending_command_insertions', 0)} | "
            f"insert_enabled={gate_summary.get('pending_command_insertion_enabled', False)} | "
            f"execute={gate_summary.get('command_execution_enabled', False)}"
        )
        for row in (agent_pending_gate.get("rows", []) or [])[:12]:
            if not isinstance(row, dict):
                continue
            gate = row.get("pending_gate_preview", {}) or {}
            lines.append(
                f"- {short(row.get('review_link_id', '-') or '-', 48)} | "
                f"task={short(row.get('task_id', '-') or '-', 40)} | "
                f"suggestion={short(row.get('suggestion_id', '-') or '-', 40)} | "
                f"ready={gate.get('metadata_ready', False)} | gate_open={gate.get('pending_gate_open', False)}"
            )
        for guardrail in ((agent_pending_gate.get("policy", {}) or {}).get("guardrails", []) or [])[:3]:
            lines.append(f"- {short(guardrail, 190)}")

        lines.append("")
        lines.append("[Pending Insert Dry-Run]")
        lines.append(
            f"mode={dry_run_summary.get('mode', 'no_exec_pending_insert_dry_run')} | "
            f"rows={dry_run_summary.get('rows', 0)} | contract_ready={dry_run_summary.get('contract_ready_rows', 0)} | "
            f"passed={dry_run_summary.get('dry_run_passed_rows', 0)}"
        )
        lines.append(
            f"queue={dry_run_summary.get('pending_queue_count', 0)} | "
            f"queue_unchanged={dry_run_summary.get('pending_queue_unchanged', True)} | "
            f"would_insert={dry_run_summary.get('would_insert_rows', 0)} | "
            f"inserted={dry_run_summary.get('pending_command_insertions', 0)} | "
            f"queue_current={dry_run_summary.get('pending_queue_current_rows', 0)} | "
            f"insert_enabled={dry_run_summary.get('pending_command_insertion_enabled', False)} | "
            f"execute={dry_run_summary.get('command_execution_enabled', False)}"
        )
        for row in (agent_pending_insert_dry_run.get("rows", []) or [])[:12]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('dry_run_id', '-') or '-', 48)} | "
                f"review={short(row.get('review_link_id', '-') or '-', 40)} | "
                f"ready={row.get('contract_ready', False)} | passed={row.get('dry_run_passed', False)} | "
                f"would_insert={row.get('would_insert', False)} | inserted={row.get('pending_command_inserted', False)} | "
                f"queue_index={row.get('pending_queue_entry_index', 0) or '-'}"
            )
            if row.get("would_insert"):
                lines.append(f"  insert_command={short(row.get('future_insert_command_shape', '') or '-', 190)}")
        for guardrail in ((agent_pending_insert_dry_run.get("policy", {}) or {}).get("guardrails", []) or [])[:3]:
            lines.append(f"- {short(guardrail, 190)}")

        lines.append("")
        lines.append("[Private History]")
        lines.append(
            f"mode={private_history_summary.get('mode', 'operator_append_private_history_metadata_only')} | "
            f"rows={private_history_summary.get('rows', 0)} | "
            f"events={private_history_summary.get('event_count', 0)} | "
            f"private={private_history_summary.get('private_event_count', 0)} | "
            f"parent_visible={private_history_summary.get('parent_visible_event_count', 0)}"
        )
        lines.append(
            f"operator_append={private_history_summary.get('operator_private_history_append_enabled', False)} | "
            f"parent_visible_append={private_history_summary.get('operator_parent_visible_summary_append_enabled', False)} | "
            f"parent_history_write={private_history_summary.get('parent_chat_history_write_enabled', False)} | "
            f"model_inclusion={private_history_summary.get('model_inclusion_enabled', False)}"
        )
        lines.append(
            f"pending_insertions={private_history_summary.get('pending_command_insertions', 0)} | "
            f"execute_events={private_history_summary.get('command_execution_events', 0)} | "
            f"history_dir={short(private_history_summary.get('history_dir', '-') or '-', 180)}"
        )
        recent_parent = private_history.get("recent_parent_visible_summaries", []) or []
        if recent_parent:
            lines.append("Recent parent-visible summaries:")
            for row in recent_parent[-8:]:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {short(row.get('agent_id', '-') or '-', 30)} | "
                    f"{short(row.get('entry_id', '-') or '-', 48)} | "
                    f"{short(row.get('summary', '-') or '-', 190)}"
                )
        for guardrail in (private_history.get("guardrails", []) or [])[:4]:
            lines.append(f"- {short(guardrail, 190)}")

        preview = registry.get("history_acl_preview", {}) or {}
        preview_summary = preview.get("summary", {}) or {}
        lines.append("")
        lines.append("[History ACL Preview]")
        lines.append(
            f"mode={preview_summary.get('mode', 'metadata_only_history_acl_preview')} | "
            f"rows={preview_summary.get('rows', 0)} | "
            f"existing_files={preview_summary.get('private_history_files_existing', 0)} | "
            f"events={preview_summary.get('private_history_events_scanned', 0)}"
        )
        lines.append(
            f"private_events={preview_summary.get('private_history_private_events', 0)} | "
            f"parent_visible_events={preview_summary.get('private_history_parent_visible_events', 0)} | "
            f"prompt_ledger_visible={preview_summary.get('private_history_prompt_ledger_visible_events', 0)}"
        )
        lines.append(
            f"requested_parent_reads={preview_summary.get('sub_agent_parent_read_requested_rows', 0)} | "
            f"requested_parent_appends={preview_summary.get('sub_agent_parent_append_requested_rows', 0)} | "
            f"requested_model_visible={preview_summary.get('model_visible_requested_rows', 0)}"
        )
        lines.append(
            f"effective_parent_writes={preview_summary.get('effective_parent_history_writes', 0)} | "
            f"effective_sub_agent_reads={preview_summary.get('effective_sub_agent_parent_reads', 0)} | "
            f"effective_model_visible={preview_summary.get('effective_model_visible_rows', 0)}"
        )
        for row in (preview.get("rows", []) or [])[:16]:
            if not isinstance(row, dict):
                continue
            permissions = row.get("permissions", {}) or {}
            visibility = row.get("visibility", {}) or {}
            lines.append(
                f"- {short(row.get('agent_id', '-') or '-', 44)} | "
                f"scopes={short(', '.join(row.get('history_scopes', []) or []) or '-', 110)}"
            )
            lines.append(
                f"  private_history={short(row.get('private_history_path', '-') or '-', 180)} | "
                f"exists={row.get('private_history_exists', False)} | events={row.get('private_history_event_count', 0)} | "
                f"parent_visible={row.get('private_history_parent_visible_event_count', 0)}"
            )
            lines.append(
                f"  parent_read={permissions.get('parent_can_read_private_history', False)} | "
                f"parent_append={permissions.get('parent_can_append_private_history', False)} | "
                f"sub_agent_parent_read_effective={permissions.get('sub_agent_can_read_parent_history_effective', False)} | "
                f"model_visible_now={visibility.get('private_history_visible_to_model_now', False)}"
            )

        route_preview = registry.get("suggestion_route_preview", {}) or {}
        route_summary = route_preview.get("summary", {}) or {}
        lines.append("")
        lines.append("[Suggestion Route Preview]")
        lines.append(
            f"mode={route_summary.get('mode', 'metadata_only_suggestion_route_preview')} | "
            f"routes={route_summary.get('route_rows', 0)} | active={route_summary.get('active_route_rows', 0)} | "
            f"policy_tagged={route_summary.get('policy_tagged_rows', 0)}"
        )
        lines.append(
            f"draft_recording={route_summary.get('suggestion_draft_recording_enabled', False)} | "
            f"pending_insert={route_summary.get('pending_command_insertion_enabled', False)} | "
            f"execute={route_summary.get('command_execution_enabled', False)} | "
            f"auto_approval={route_summary.get('auto_approval_enabled', False)}"
        )
        for row in (route_preview.get("rows", []) or [])[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('agent_id', '-') or '-', 44)} | "
                f"route={short(row.get('route', '-') or '-', 110)} | "
                f"approval_required={row.get('operator_approval_required', True)}"
            )
            lines.append(
                f"  policy_tags={short(', '.join(row.get('policy_tags', []) or []) or '-', 190)}"
            )

        lines.append("")
        lines.append("[Suggestion Audit]")
        lines.append(
            f"mode={suggestions_summary.get('mode', 'metadata_only_suggestion_audit')} | "
            f"rows={suggestions_summary.get('suggestion_count', 0)} | "
            f"prompt_ledger_visible={suggestions_summary.get('prompt_ledger_visible_suggestions', 0)} | "
            f"policy_blocked={suggestions_summary.get('policy_blocked_suggestions', 0)}"
        )
        lines.append(
            f"pending_candidates={suggestions_summary.get('pending_command_candidates', 0)} | "
            f"approved={suggestions_summary.get('approved_suggestions', 0)} | "
            f"rejected={suggestions_summary.get('rejected_suggestions', 0)} | "
            f"staged={suggestions_summary.get('staged_pending_candidates', 0)} | "
            f"context_mark_linked={suggestions_summary.get('context_mark_linked_suggestions', 0)} | "
            f"pending_insertions={suggestions_summary.get('pending_command_insertions', 0)} | "
            f"insert_enabled={suggestions_summary.get('pending_command_insertion_enabled', False)} | "
            f"execute_enabled={suggestions_summary.get('command_execution_enabled', False)}"
        )
        for row in (agent_suggestions.get("recent_suggestions", []) or [])[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('suggestion_id', '-') or '-', 46)} | "
                f"agent={short(row.get('agent_id', '-') or '-', 30)} | "
                f"approval={row.get('approval_state', '-')} | policy={row.get('policy_state', '-')} | risk={row.get('risk', '-')}"
            )
            lines.append(f"  command={short(row.get('command', '') or '-', 180)}")
            lines.append(
                f"  pending_inserted={row.get('pending_command_inserted', False)} | "
                f"candidate_state={row.get('pending_candidate_state', 'not_staged')} | "
                f"model_visible_now={row.get('model_visible_now', False)} | "
                f"tags={short(', '.join(row.get('policy_tags', []) or []) or '-', 160)}"
            )
            if row.get("pending_candidate_id"):
                lines.append(
                    f"  candidate_id={short(row.get('pending_candidate_id', '-') or '-', 100)} | "
                    f"queue_inserted={row.get('pending_queue_inserted', False)}"
                )
            context_ids = row.get("context_mark_ids", []) or []
            if context_ids:
                lines.append(
                    f"  context_marks={short(', '.join(context_ids), 160)} | "
                    f"provenance_visible={row.get('prompt_ledger_provenance_visible', False)}"
                )

        policy = registry.get("policy", {}) or {}
        lines.append("")
        lines.append("[Policy]")
        lines.append(
            f"mode={policy.get('mode', 'metadata_first')} | "
            f"spawns_processes={policy.get('spawns_processes', False)} | "
            f"calls_models={policy.get('calls_models', False)} | "
            f"writes_parent_history={policy.get('writes_parent_history', False)}"
        )
        for guardrail in (policy.get("guardrails", []) or [])[:8]:
            lines.append(f"- {short(guardrail, 190)}")
        return "\n".join(lines).strip()

    def build_portal_intake_text(self, portal_intake):
        portal_intake = portal_intake or {}
        if not isinstance(portal_intake, dict):
            return "No Portal Intake packet exported yet."
        counts = portal_intake.get("counts", {}) or {}
        status_counts = portal_intake.get("status_counts", {}) or {}
        stage_gate_counts = portal_intake.get("stage_gate_counts", {}) or {}
        lines = [
            "[Portal Intake Summary]",
            (
                f"schema={portal_intake.get('schema_version', '-') or '-'} | "
                f"window={portal_intake.get('window', '-') or '-'} | "
                f"slice={portal_intake.get('slice', '-') or '-'} | "
                f"status={portal_intake.get('status', '-') or '-'}"
            ),
            f"summary={portal_intake.get('summary', '-') or '-'}",
            (
                f"ready_for_local_viewer={portal_intake.get('ready_for_local_viewer', False)} | "
                f"live_reads={portal_intake.get('ready_for_live_portal_reads', False)} | "
                f"cross_client_proof={portal_intake.get('ready_for_cross_client_proof', False)} | "
                f"receipt_submission={portal_intake.get('ready_for_receipt_submission', False)} | "
                f"mutation_gates={portal_intake.get('ready_for_mutation_gates', False)}"
            ),
            (
                f"mirror_exists={portal_intake.get('handoff_mirror_exists', False)} | "
                f"mirror_path={portal_intake.get('handoff_mirror_path', '-') or '-'}"
            ),
            (
                f"branch={portal_intake.get('portal_branch', '-') or '-'} | "
                f"head={short(portal_intake.get('portal_head_commit', '-') or '-', 16)} | "
                f"pr={portal_intake.get('portal_pr_url', '-') or '-'}"
            ),
            (
                f"routes={counts.get('routes', 0)} | heavy_routes={counts.get('heavy_routes', 0)} | "
                f"cli={counts.get('cli_commands', 0)} | allowed={counts.get('allowed_intents', 0)} | "
                f"blocked={counts.get('blocked_intents', 0)} | questions={counts.get('open_questions', 0)}"
            ),
            (
                f"copy_packets={counts.get('operator_copy_packets', 0)} | "
                f"draft_templates={counts.get('receipt_draft_templates', 0)} | "
                f"review_packets={counts.get('readiness_review_packets', 0)} | "
                f"registry_rows={counts.get('envelope_registry_rows', 0)} | "
                f"audit_rows={counts.get('acceptance_audit_rows', 0)} | "
                f"docket_rows={counts.get('promotion_evidence_rows', 0)} | "
                f"handoff_packets={counts.get('external_handoff_packets', 0)} | "
                f"proof_rows={counts.get('local_proof_rows', 0)} | "
                f"report_packets={counts.get('operator_report_packets', 0)} | "
                f"unblockers={counts.get('gate_unblocker_rows', 0)} | "
                f"waitlist={counts.get('upstream_waitlist_packets', 0)} | "
                f"parking={counts.get('parking_resume_packets', 0)} | "
                f"closure={counts.get('intake_closure_checks', 0)} | "
                f"rows={counts.get('rows', 0)} | blocking={counts.get('blocking_rows', 0)}"
            ),
            (
                f"stage_gates={counts.get('stage_gates', 0)} | "
                f"gates_ok={stage_gate_counts.get('ok', 0)} | "
                f"gates_watch={stage_gate_counts.get('watch', 0)} | "
                f"gates_blocked={stage_gate_counts.get('blocked', 0)} | "
                f"review_ready={portal_intake.get('ready_for_readiness_review', False)} | "
                f"registry_contract={portal_intake.get('ready_for_registry_contract_review', False)} | "
                f"live_registry={portal_intake.get('ready_for_live_registry_read', False)} | "
                f"acceptance_audit={portal_intake.get('ready_for_acceptance_audit', False)}"
            ),
            (
                f"acceptance_proved={counts.get('acceptance_proved', 0)} | "
                f"acceptance_waiting={counts.get('acceptance_waiting', 0)} | "
                f"acceptance_missing={counts.get('acceptance_missing', 0)} | "
                f"acceptance_blocked={counts.get('acceptance_blocked', 0)} | "
                f"local_acceptance={portal_intake.get('ready_for_local_acceptance', False)} | "
                f"external_acceptance={portal_intake.get('ready_for_external_acceptance', False)}"
            ),
            (
                f"promotion_proved={counts.get('promotion_proved', 0)} | "
                f"promotion_waiting={counts.get('promotion_waiting', 0)} | "
                f"promotion_missing={counts.get('promotion_missing', 0)} | "
                f"promotion_blocked={counts.get('promotion_blocked', 0)} | "
                f"promotion_review={portal_intake.get('ready_for_promotion_evidence_review', False)} | "
                f"stage_promotion={portal_intake.get('ready_for_stage_promotion', False)}"
            ),
            (
                f"handoff_ready_to_copy={counts.get('handoff_ready_to_copy', 0)} | "
                f"handoff_waiting={counts.get('handoff_waiting', 0)} | "
                f"handoff_blocked={counts.get('handoff_blocked', 0)} | "
                f"handoff_review={portal_intake.get('ready_for_external_handoff_review', False)} | "
                f"handoff_submit={portal_intake.get('external_handoff_submit_enabled', False)}"
            ),
            (
                f"proof_validated={counts.get('local_proof_validated', 0)} | "
                f"proof_ready_for_validation={counts.get('local_proof_ready_for_validation', 0)} | "
                f"proof_watch={counts.get('local_proof_watch', 0)} | "
                f"proof_blocked={counts.get('local_proof_blocked', 0)} | "
                f"proof_review={portal_intake.get('ready_for_local_proof_review', False)} | "
                f"current_recorded={portal_intake.get('current_slice_validation_recorded', False)}"
            ),
            (
                f"operator_report_ready_to_copy={counts.get('operator_report_ready_to_copy', 0)} | "
                f"operator_report_waiting={counts.get('operator_report_waiting', 0)} | "
                f"operator_report_blocked={counts.get('operator_report_blocked', 0)} | "
                f"operator_report_review={portal_intake.get('ready_for_operator_report_review', False)}"
            ),
            (
                f"unblocker_proved={counts.get('unblocker_proved', 0)} | "
                f"unblocker_waiting={counts.get('unblocker_waiting', 0)} | "
                f"unblocker_blocked={counts.get('unblocker_blocked', 0)} | "
                f"unblocker_review={portal_intake.get('ready_for_unblocker_review', False)}"
            ),
            (
                f"waitlist_ready_to_copy={counts.get('waitlist_ready_to_copy', 0)} | "
                f"waitlist_waiting={counts.get('waitlist_waiting', 0)} | "
                f"waitlist_blocked={counts.get('waitlist_blocked', 0)} | "
                f"waitlist_review={portal_intake.get('ready_for_upstream_waitlist_review', False)}"
            ),
            (
                f"parking_ready_to_copy={counts.get('parking_ready_to_copy', 0)} | "
                f"parking_waiting={counts.get('parking_waiting', 0)} | "
                f"parking_blocked={counts.get('parking_blocked', 0)} | "
                f"parking_review={portal_intake.get('ready_for_parking_review', False)}"
            ),
            (
                f"closure_proved={counts.get('closure_proved', 0)} | "
                f"closure_waiting={counts.get('closure_waiting', 0)} | "
                f"closure_blocked={counts.get('closure_blocked', 0)} | "
                f"closure_review={portal_intake.get('ready_for_parked_closure_review', False)} | "
                f"parked={portal_intake.get('local_implementation_parked', False)}"
            ),
            (
                f"ok={status_counts.get('ok', 0)} | watch={status_counts.get('watch', 0)} | "
                f"warning={status_counts.get('warning', 0)} | blocked={status_counts.get('blocked', 0)} | "
                f"pending={status_counts.get('pending', 0)}"
            ),
            "",
            "[Authority Flags]",
            (
                f"portal_http={counts.get('portal_http_calls_enabled', False)} | "
                f"portal_cli={counts.get('portal_cli_calls_enabled', False)} | "
                f"polling={counts.get('polling_enabled', False)} | "
                f"request_ingest={counts.get('request_ingest_enabled', False)} | "
                f"receipt_writer={counts.get('receipt_writer_enabled', False)} | "
                f"submit_receipts={counts.get('submit_receipts_enabled', False)}"
            ),
            (
                f"desktop_automation={counts.get('desktop_automation_enabled', False)} | "
                f"browser_automation={counts.get('browser_automation_enabled', False)} | "
                f"source_file_reads={counts.get('source_file_reads_enabled', False)} | "
                f"model_visible_writes={counts.get('model_visible_writes_enabled', False)} | "
                f"mutation_gates={counts.get('mutation_gates_enabled', False)}"
            ),
            f"companion_write_flags={counts.get('companion_write_flags', 0)} | all_portal_write_flags_off={counts.get('all_portal_write_flags_off', False)}",
            "",
            "[Performance]",
            short(portal_intake.get("performance_note", "-") or "-", 320),
            "",
            "[Readiness Rows]",
        ]
        rows = portal_intake.get("rows", []) or []
        if not rows:
            lines.append("-")
        for row in rows[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 74)} | "
                f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 190)}"
            )
            detail = short(row.get("detail", "") or "", 220)
            if detail:
                lines.append(f"  detail={detail}")
            action = short(row.get("operator_action", "") or "", 220)
            if action:
                lines.append(f"  action={action}")

        lines.append("")
        lines.append("[Stage Gates]")
        stage_gates = portal_intake.get("stage_gates", []) or []
        if not stage_gates:
            lines.append("-")
        for gate in stage_gates[:16]:
            if not isinstance(gate, dict):
                continue
            lines.append(
                f"- {short(gate.get('label', gate.get('key', '-')) or '-', 74)} | "
                f"{gate.get('status', '-')} | {short(gate.get('summary', '-') or '-', 190)}"
            )
            detail = short(gate.get("detail", "") or "", 220)
            if detail:
                lines.append(f"  detail={detail}")
            action = short(gate.get("operator_action", "") or "", 220)
            if action:
                lines.append(f"  action={action}")

        lines.append("")
        lines.append("[Thresholds Before Later Stages]")
        thresholds = portal_intake.get("gate_thresholds", []) or []
        if not thresholds:
            lines.append("-")
        for threshold in thresholds[:12]:
            if not isinstance(threshold, dict):
                continue
            lines.append(
                f"- {short(threshold.get('label', threshold.get('key', '-')) or '-', 82)} | "
                f"blocks={threshold.get('blocks', '-') or '-'} | "
                f"ready={threshold.get('ready', False)} | "
                f"{short(threshold.get('summary', '-') or '-', 220)}"
            )

        lines.append("")
        lines.append("[Readiness Review Packets]")
        review_packets = portal_intake.get("readiness_review_packets", []) or []
        if not review_packets:
            lines.append("-")
        for packet in review_packets[:8]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"{packet.get('status', '-')} | audience={short(packet.get('audience', '-') or '-', 110)} | "
                f"submit={packet.get('submit_enabled', False)}"
            )
            summary = short(packet.get("summary", "") or "", 220)
            if summary:
                lines.append(f"  summary={summary}")
            for item in (packet.get("lines", []) or [])[:6]:
                lines.append(f"  {short(item, 220)}")

        lines.append("")
        lines.append("[Review Stop Lines]")
        stop_lines = portal_intake.get("review_stop_lines", []) or []
        if not stop_lines:
            lines.append("-")
        for item in stop_lines[:10]:
            lines.append(f"- {short(item, 240)}")

        lines.append("")
        lines.append("[Review Questions]")
        review_questions = portal_intake.get("review_next_questions", []) or []
        if not review_questions:
            lines.append("-")
        for item in review_questions[:10]:
            lines.append(f"- {short(item, 240)}")

        lines.append("")
        lines.append("[Envelope Registry Contract]")
        contract = portal_intake.get("envelope_registry_contract", {}) or {}
        if not contract:
            lines.append("-")
        else:
            lines.append(
                f"schema={contract.get('schema_version', '-') or '-'} | "
                f"status={contract.get('status', '-') or '-'} | "
                f"source_available={contract.get('source_available', False)} | "
                f"cache_required={contract.get('cache_required', True)} | "
                f"polling_allowed={contract.get('polling_allowed', False)} | "
                f"submit={contract.get('submit_enabled', False)}"
            )
            summary = short(contract.get("summary", "") or "", 260)
            if summary:
                lines.append(f"summary={summary}")
            fields = contract.get("required_fields", []) or []
            if fields:
                lines.append(f"required={short(', '.join(str(item) for item in fields), 320)}")
        registry_rows = portal_intake.get("envelope_registry_rows", []) or []
        if not registry_rows:
            lines.append("-")
        for row in registry_rows[:12]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"{row.get('status', '-')} | use={short(row.get('expected_use', '-') or '-', 90)} | "
                f"source={short(row.get('expected_source', '-') or '-', 90)}"
            )
            lines.append(f"  {short(row.get('summary', '-') or '-', 240)}")
            route_keys = row.get("route_keys", []) or []
            if route_keys:
                lines.append(f"  route_keys={short(', '.join(str(item) for item in route_keys), 220)}")
            required = row.get("required_fields", []) or []
            if required:
                lines.append(f"  required={short(', '.join(str(item) for item in required), 260)}")
        registry_stop_lines = portal_intake.get("registry_contract_stop_lines", []) or []
        if registry_stop_lines:
            lines.append("registry_stop_lines:")
            for item in registry_stop_lines[:8]:
                lines.append(f"- {short(item, 240)}")

        lines.append("")
        lines.append("[Acceptance Audit Matrix]")
        audit_rows = portal_intake.get("acceptance_audit_matrix", []) or []
        if not audit_rows:
            lines.append("-")
        for row in audit_rows[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"verdict={row.get('verdict', '-') or '-'} | "
                f"stage={short(row.get('stage', '-') or '-', 82)}"
            )
            summary = short(row.get("summary", "") or "", 240)
            if summary:
                lines.append(f"  summary={summary}")
            evidence = short(row.get("evidence", "") or "", 260)
            if evidence:
                lines.append(f"  evidence={evidence}")
            next_action = short(row.get("next_action", "") or "", 260)
            if next_action:
                lines.append(f"  next={next_action}")

        lines.append("")
        lines.append("[Promotion Evidence Docket]")
        docket_rows = portal_intake.get("promotion_evidence_docket", []) or []
        if not docket_rows:
            lines.append("-")
        for row in docket_rows[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"status={row.get('status', '-') or '-'} | "
                f"stage={short(row.get('stage', '-') or '-', 82)} | "
                f"owner={short(row.get('owner', '-') or '-', 82)}"
            )
            unlocks = short(row.get("unlocks", "") or "", 220)
            if unlocks:
                lines.append(f"  unlocks={unlocks}")
            current = short(row.get("current_evidence", "") or "", 260)
            if current:
                lines.append(f"  current={current}")
            required = short(row.get("required_evidence", "") or "", 260)
            if required:
                lines.append(f"  required={required}")
            action = short(row.get("operator_action", "") or "", 260)
            if action:
                lines.append(f"  action={action}")

        lines.append("")
        lines.append("[External Handoff Packets]")
        handoff_packets = portal_intake.get("external_handoff_packets", []) or []
        if not handoff_packets:
            lines.append("-")
        for packet in handoff_packets[:12]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"status={packet.get('status', '-') or '-'} | "
                f"audience={short(packet.get('audience', '-') or '-', 100)} | "
                f"submit={packet.get('submit_enabled', False)} | "
                f"automated_send={packet.get('automated_send_enabled', False)}"
            )
            summary = short(packet.get("summary", "") or "", 260)
            if summary:
                lines.append(f"  summary={summary}")
            related = packet.get("related_docket_keys", []) or []
            if related:
                lines.append(f"  docket_keys={short(', '.join(str(item) for item in related), 220)}")
            for item in (packet.get("lines", []) or [])[:8]:
                lines.append(f"  {short(item, 260)}")

        lines.append("")
        lines.append("[Local Proof Ledger]")
        proof_rows = portal_intake.get("local_proof_ledger", []) or []
        if not proof_rows:
            lines.append("-")
        for row in proof_rows[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"status={row.get('status', '-') or '-'} | "
                f"validation={short(row.get('validation_id', '-') or '-', 100)}"
            )
            commands = row.get("commands", []) or []
            if commands:
                lines.append(f"  commands={short(', '.join(str(item) for item in commands), 260)}")
            evidence = short(row.get("evidence", "") or "", 280)
            if evidence:
                lines.append(f"  evidence={evidence}")
            guardrails = row.get("guardrails", []) or []
            if guardrails:
                lines.append(f"  guardrails={short(', '.join(str(item) for item in guardrails), 280)}")

        lines.append("")
        lines.append("[Operator Report Packets]")
        report_packets = portal_intake.get("operator_report_packets", []) or []
        if not report_packets:
            lines.append("-")
        for packet in report_packets[:12]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"status={packet.get('status', '-') or '-'} | "
                f"audience={short(packet.get('audience', '-') or '-', 100)} | "
                f"submit={packet.get('submit_enabled', False)} | "
                f"automated_send={packet.get('automated_send_enabled', False)}"
            )
            summary = short(packet.get("summary", "") or "", 260)
            if summary:
                lines.append(f"  summary={summary}")
            for item in (packet.get("lines", []) or [])[:8]:
                lines.append(f"  {short(item, 260)}")

        lines.append("")
        lines.append("[Gate Unblocker Checklist]")
        unblockers = portal_intake.get("gate_unblocker_checklist", []) or []
        if not unblockers:
            lines.append("-")
        for row in unblockers[:16]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"status={row.get('status', '-') or '-'} | "
                f"unlocks={short(row.get('unlocks', '-') or '-', 120)}"
            )
            current = short(row.get("current_evidence", "") or "", 260)
            if current:
                lines.append(f"  current={current}")
            required = short(row.get("required_evidence", "") or "", 280)
            if required:
                lines.append(f"  required={required}")
            action = short(row.get("next_action", "") or "", 260)
            if action:
                lines.append(f"  next={action}")

        lines.append("")
        lines.append("[Upstream Waitlist]")
        waitlist = portal_intake.get("upstream_waitlist_packets", []) or []
        if not waitlist:
            lines.append("-")
        for packet in waitlist[:14]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"status={packet.get('status', '-') or '-'} | "
                f"audience={short(packet.get('audience', '-') or '-', 100)} | "
                f"timing={short(packet.get('timing', '-') or '-', 80)}"
            )
            ask = short(packet.get("ask", "") or "", 280)
            if ask:
                lines.append(f"  ask={ask}")
            why = short(packet.get("why", "") or "", 260)
            if why:
                lines.append(f"  why={why}")
            keys = packet.get("unblocker_keys", []) or []
            if keys:
                lines.append(f"  unblockers={short(', '.join(str(item) for item in keys), 220)}")

        lines.append("")
        lines.append("[Parking / Resume Packets]")
        parking_packets = portal_intake.get("parking_resume_packets", []) or []
        if not parking_packets:
            lines.append("-")
        for packet in parking_packets[:12]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"status={packet.get('status', '-') or '-'} | "
                f"audience={short(packet.get('audience', '-') or '-', 100)} | "
                f"timing={short(packet.get('timing', '-') or '-', 80)}"
            )
            trigger = short(packet.get("resume_trigger", "") or "", 280)
            if trigger:
                lines.append(f"  resume_trigger={trigger}")
            summary = short(packet.get("summary", "") or "", 280)
            if summary:
                lines.append(f"  summary={summary}")
            current = short(packet.get("current_evidence", "") or "", 300)
            if current:
                lines.append(f"  current={current}")
            action = short(packet.get("next_action", "") or "", 280)
            if action:
                lines.append(f"  next={action}")

        lines.append("")
        lines.append("[Parked Closure Audit]")
        closure_checks = portal_intake.get("intake_closure_checks", []) or []
        if not closure_checks:
            lines.append("-")
        for row in closure_checks[:12]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 82)} | "
                f"status={row.get('status', '-') or '-'} | "
                f"decision={short(row.get('decision', '-') or '-', 110)}"
            )
            evidence = short(row.get("evidence", "") or "", 300)
            if evidence:
                lines.append(f"  evidence={evidence}")
            required = short(row.get("required_to_resume", "") or "", 300)
            if required:
                lines.append(f"  resume_requires={required}")

        lines.append("")
        lines.append("[Routes]")
        routes = portal_intake.get("routes", []) or []
        if not routes:
            lines.append("-")
        for route in routes[:16]:
            if not isinstance(route, dict):
                continue
            estimate = int(route.get("estimated_windows_ms", 0) or 0)
            estimate_text = f" | est_ms={estimate}" if estimate else ""
            lines.append(
                f"- {short(route.get('route', route.get('key', '-')) or '-', 90)} | "
                f"{route.get('status', '-')} | use={route.get('expected_use', '-') or '-'}{estimate_text}"
            )
            lines.append(f"  {short(route.get('summary', '-') or '-', 220)}")

        lines.append("")
        lines.append("[CLI Packets]")
        cli_commands = portal_intake.get("cli_commands", []) or []
        if not cli_commands:
            lines.append("-")
        for command in cli_commands[:12]:
            if not isinstance(command, dict):
                continue
            lines.append(
                f"- {short(command.get('command', command.get('key', '-')) or '-', 84)} | "
                f"{command.get('status', '-')} | {short(command.get('summary', '-') or '-', 220)}"
            )

        lines.append("")
        lines.append("[Allowed Intents]")
        allowed = portal_intake.get("allowed_intents", []) or []
        if not allowed:
            lines.append("-")
        for row in allowed[:12]:
            if isinstance(row, dict):
                lines.append(
                    f"- {short(row.get('label', row.get('key', '-')) or '-', 74)} | "
                    f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 220)}"
                )

        lines.append("")
        lines.append("[Blocked Intents]")
        blocked = portal_intake.get("blocked_intents", []) or []
        if not blocked:
            lines.append("-")
        for item in blocked[:16]:
            lines.append(f"- {short(item, 220)}")

        lines.append("")
        lines.append("[Operator Copy Packets]")
        copy_packets = portal_intake.get("operator_copy_packets", []) or []
        if not copy_packets:
            lines.append("-")
        for packet in copy_packets[:8]:
            if not isinstance(packet, dict):
                continue
            lines.append(
                f"- {short(packet.get('label', packet.get('key', '-')) or '-', 82)} | "
                f"{packet.get('status', '-')} | destination={short(packet.get('destination', '-') or '-', 110)} | "
                f"submit={packet.get('submit_enabled', False)}"
            )
            for item in (packet.get("lines", []) or [])[:6]:
                lines.append(f"  {short(item, 220)}")

        lines.append("")
        lines.append("[Receipt Draft Templates]")
        drafts = portal_intake.get("receipt_draft_templates", []) or []
        if not drafts:
            lines.append("-")
        for draft in drafts[:8]:
            if not isinstance(draft, dict):
                continue
            fields = draft.get("fields", {}) or {}
            lines.append(
                f"- {short(draft.get('label', draft.get('key', '-')) or '-', 82)} | "
                f"{draft.get('status', '-')} | type={fields.get('receipt_type', '-') or '-'} | "
                f"submit={draft.get('submit_enabled', False)}"
            )
            subject = short(fields.get("subject", "") or "", 180)
            if subject:
                lines.append(f"  subject={subject}")
            decision = short(fields.get("decision", "") or "", 180)
            if decision:
                lines.append(f"  decision={decision}")
            for item in (draft.get("lines", []) or [])[:5]:
                lines.append(f"  {short(item, 220)}")

        lines.append("")
        lines.append("[Open Questions]")
        questions = portal_intake.get("open_questions", []) or []
        if not questions:
            lines.append("-")
        for item in questions[:10]:
            lines.append(f"- {short(item, 240)}")

        lines.append("")
        lines.append("[Guardrails]")
        guardrails = portal_intake.get("guardrails", []) or []
        if not guardrails:
            lines.append("-")
        for item in guardrails[:12]:
            lines.append(f"- {short(item, 240)}")

        lines.append("")
        lines.append("[Next Actions]")
        actions = portal_intake.get("next_actions", []) or []
        if not actions:
            lines.append("-")
        for item in actions[:10]:
            lines.append(f"- {short(item, 240)}")
        return "\n".join(lines).strip()

    def build_history_context_text(self, history_context, companion_readiness=None, companion_protocol=None, companion_receipt=None, companion_closure=None):
        history_context = history_context or {}
        if not isinstance(history_context, dict):
            return "No History Context inventory exported yet."
        companion_readiness = companion_readiness or {}
        if not isinstance(companion_readiness, dict):
            companion_readiness = {}
        companion_protocol = companion_protocol or {}
        if not isinstance(companion_protocol, dict):
            companion_protocol = {}
        companion_receipt = companion_receipt or {}
        if not isinstance(companion_receipt, dict):
            companion_receipt = {}
        companion_closure = companion_closure or {}
        if not isinstance(companion_closure, dict):
            companion_closure = {}
        summary = history_context.get("summary", {}) or {}
        store_summary = history_context.get("store_summary", {}) or {}
        policy_snapshot = history_context.get("policy_snapshot", {}) or {}
        service_facade = history_context.get("service_facade", {}) or {}
        companion_counts = companion_readiness.get("counts", {}) or {}
        companion_status_counts = companion_readiness.get("status_counts", {}) or {}
        protocol_counts = companion_protocol.get("counts", {}) or {}
        protocol_route_counts = companion_protocol.get("route_status_counts", {}) or {}
        protocol_gate_counts = companion_protocol.get("gate_status_counts", {}) or {}
        receipt_counts = companion_receipt.get("counts", {}) or {}
        closure_counts = companion_closure.get("counts", {}) or {}
        closure_status_counts = companion_closure.get("status_counts", {}) or {}
        lines = [
            "[Summary]",
            (
                f"mode={summary.get('mode', '-')} | "
                f"status={summary.get('status', '-')} | "
                f"service_extracted={summary.get('service_extracted', False)}"
            ),
            (
                f"service_facade={summary.get('service_facade_enabled', False)} | "
                f"schema={summary.get('service_facade_schema', '-') or '-'} | "
                f"read_methods={summary.get('service_facade_read_methods', 0)} | "
                f"writes_enabled={summary.get('service_facade_write_methods_enabled', False)}"
            ),
            (
                f"centralized_read_helpers={summary.get('centralized_read_helpers_enabled', False)} | "
                f"read_state={summary.get('read_state_schema', '-') or '-'}"
            ),
            (
                f"store_summary={summary.get('centralized_store_summary_enabled', False)} | "
                f"schema={summary.get('store_summary_schema', '-') or '-'} | "
                f"existing={summary.get('store_existing_rows', 0)}/{summary.get('store_rows', 0)} | "
                f"latest={summary.get('latest_store_signal_key', '-') or '-'}"
            ),
            (
                f"policy_snapshot={summary.get('centralized_policy_snapshot_enabled', False)} | "
                f"schema={summary.get('policy_snapshot_schema', '-') or '-'} | "
                f"enabled_write_paths={summary.get('enabled_effective_write_paths', 0)} | "
                f"disabled_write_paths={summary.get('disabled_effective_write_paths', 0)}"
            ),
            (
                f"chat_entries={summary.get('chat_history_entries', 0)} | "
                f"text={summary.get('raw_text_entries', 0)} | "
                f"images={summary.get('raw_image_entries', 0)} | "
                f"important_text={summary.get('important_text_entries', 0)}"
            ),
            (
                f"prompt_ledger={summary.get('prompt_ledger_mode', '-')} | "
                f"included_rows={summary.get('prompt_included_rows', 0)} | "
                f"omitted_rows={summary.get('prompt_omitted_rows', 0)}"
            ),
            (
                f"context_marks={summary.get('context_mark_entries', 0)} | "
                f"image_sidecars={summary.get('image_sidecar_count', 0)} | "
                f"context_files={summary.get('context_file_rows', 0)}"
            ),
            (
                f"agent_rows={summary.get('agent_registry_rows', 0)} | "
                f"private_history_paths={summary.get('agent_private_history_paths', 0)} | "
                f"private_history_events={summary.get('agent_private_history_events', 0)} | "
                f"parent_visible={summary.get('agent_private_history_parent_visible_events', 0)} | "
                f"suggestion_audit_rows={summary.get('agent_suggestion_audit_rows', 0)}"
            ),
            (
                f"prompt_pin_inclusion={summary.get('prompt_pin_inclusion_enabled', False)} | "
                f"drop_enforcement={summary.get('do_not_include_enforcement_enabled', False)} | "
                f"private_history_append={summary.get('agent_private_history_append_enabled', False)} | "
                f"operator_history_append={summary.get('agent_private_history_operator_append_enabled', False)}"
            ),
            (
                f"suggestion_insert={summary.get('agent_suggestion_pending_insert_enabled', False)} | "
                f"suggestion_execute={summary.get('agent_suggestion_execution_enabled', False)} | "
                f"model_visible_promotion={summary.get('agent_suggestion_model_visible_promotion_enabled', False)}"
            ),
            (
                f"agent_task_packets={summary.get('agent_task_packets', 0)} | "
                f"task_prompt_ledger_visible={summary.get('agent_task_prompt_ledger_visible', 0)} | "
                f"task_insert={summary.get('agent_task_pending_insert_enabled', False)} | "
                f"task_execute={summary.get('agent_task_execution_enabled', False)}"
            ),
            (
                f"companion_contract={summary.get('companion_contract_status', '-')} | "
                f"direct_store_write_allowed={summary.get('companion_direct_store_write_allowed', False)} | "
                f"effective_write_paths_disabled={summary.get('all_effective_write_paths_disabled', False)}"
            ),
            "",
            "[Stores]",
        ]
        stores = history_context.get("stores", []) or []
        if not stores:
            lines.append("-")
        for row in stores:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {short(row.get('label', row.get('key', '-')) or '-', 56)} | "
                f"{row.get('kind', '-')} | count={row.get('count', 0)} | "
                f"exists={row.get('exists', False)} | direct_write={row.get('direct_write_allowed', False)}"
            )
            lines.append(
                f"  read={short(row.get('read_surface', '-') or '-', 120)} | "
                f"write={short(row.get('write_surface', '-') or '-', 120)}"
            )
            path = short(row.get("path", "") or "", 180)
            if path:
                lines.append(f"  path={path}")
            note = short(row.get("note", "") or "", 180)
            if note:
                lines.append(f"  note={note}")
            signal = row.get("latest_signal", {}) or {}
            if signal:
                lines.append(
                    f"  latest={signal.get('timestamp', '-') or '-'} | "
                    f"{short(signal.get('event', '-') or '-', 110)} | source={signal.get('source', '-') or '-'}"
                )

        if store_summary:
            latest = store_summary.get("latest_store_signal", {}) or {}
            lines.append("")
            lines.append("[Store Summary]")
            lines.append(
                f"schema={store_summary.get('schema_version', '-') or '-'} | "
                f"stores={store_summary.get('store_rows', 0)} | "
                f"existing={store_summary.get('existing_store_rows', 0)} | "
                f"missing={store_summary.get('missing_store_rows', 0)} | "
                f"event_rows={store_summary.get('total_event_rows', 0)}"
            )
            if latest:
                lines.append(
                    f"latest={latest.get('label', latest.get('key', '-'))} | "
                    f"{latest.get('timestamp', '-') or '-'} | {short(latest.get('event', '-') or '-', 140)}"
                )

        if policy_snapshot:
            lines.append("")
            lines.append("[Policy Snapshot]")
            lines.append(
                f"schema={policy_snapshot.get('schema_version', '-') or '-'} | "
                f"status={policy_snapshot.get('status', '-') or '-'} | "
                f"enabled={policy_snapshot.get('enabled_write_path_count', 0)} | "
                f"disabled={policy_snapshot.get('disabled_write_path_count', 0)}"
            )
            for row in (policy_snapshot.get("rows", []) or [])[:12]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('label', row.get('key', '-')) or '-', 70)} | "
                        f"enabled={row.get('enabled', False)} | source={short(row.get('source', '-') or '-', 80)}"
                    )

        if service_facade:
            prompt_window = service_facade.get("prompt_window", {}) or {}
            lines.append("")
            lines.append("[Service Facade]")
            lines.append(
                f"schema={service_facade.get('schema_version', '-') or '-'} | "
                f"status={service_facade.get('status', '-') or '-'} | "
                f"read_methods={service_facade.get('read_method_count', 0)} | "
                f"write_methods_enabled={service_facade.get('write_methods_enabled', False)} | "
                f"model_visible_mutation={service_facade.get('model_visible_mutation_enabled', False)}"
            )
            if prompt_window:
                lines.append(
                    f"prompt_window text={prompt_window.get('selected_text_count', 0)} | "
                    f"images={prompt_window.get('selected_image_count', 0)} | "
                    f"mode={prompt_window.get('mode', '-') or '-'}"
                )
            for row in (service_facade.get("read_methods", []) or [])[:8]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('name', '-') or '-', 60)} | "
                        f"{short(row.get('scope', '-') or '-', 140)} | "
                        f"write={row.get('write_path', False)} | model_mutation={row.get('model_visible_mutation', False)}"
                    )

        boundaries = history_context.get("boundaries", []) or []
        lines.append("")
        lines.append("[Boundaries]")
        if not boundaries:
            lines.append("-")
        for row in boundaries:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {short(row.get('name', '-') or '-', 60)} | owner={short(row.get('owner', '-') or '-', 90)}")
            lines.append(f"  current={short(row.get('current_shape', '') or '-', 180)}")
            lines.append(f"  future={short(row.get('future_shape', '') or '-', 180)}")
            readers = ", ".join(row.get("readers", []) or []) or "-"
            writers = ", ".join(row.get("writers", []) or []) or "-"
            lines.append(f"  readers={short(readers, 160)}")
            lines.append(f"  writers={short(writers, 160)}")
            companion = short(row.get("companion_contract", "") or "", 180)
            if companion:
                lines.append(f"  companion={companion}")
            risk = short(row.get("risk", "") or "", 180)
            if risk:
                lines.append(f"  risk={risk}")

        contract = history_context.get("companion_contract", {}) or {}
        lines.append("")
        lines.append("[Companion Contract Preview]")
        read_surfaces = contract.get("read_surfaces", []) or []
        write_surfaces = contract.get("write_surfaces", []) or []
        if not read_surfaces and not write_surfaces:
            lines.append("-")
        for row in read_surfaces:
            if isinstance(row, dict):
                lines.append(f"- read {short(row.get('surface', '-') or '-', 70)} | {row.get('status', '-')} | {short(row.get('scope', '-') or '-', 160)}")
                if row.get("path"):
                    lines.append(f"  path={short(row.get('path', ''), 180)}")
        for row in write_surfaces:
            if isinstance(row, dict):
                lines.append(f"- write {short(row.get('surface', '-') or '-', 70)} | {row.get('status', '-')} | {short(row.get('scope', '-') or '-', 160)}")
                if row.get("path"):
                    lines.append(f"  path={short(row.get('path', ''), 180)}")
        parked = contract.get("parked_companions", []) or []
        if parked:
            lines.append("")
            lines.append("[Parked Companions]")
            for row in parked:
                if isinstance(row, dict):
                    lines.append(f"- {row.get('name', '-')} | {row.get('status', '-')}")

        if companion_readiness:
            lines.append("")
            lines.append("[Companion Readiness]")
            lines.append(
                f"schema={companion_readiness.get('schema_version', '-') or '-'} | "
                f"status={companion_readiness.get('status', '-') or '-'} | "
                f"integration_enabled={companion_readiness.get('integration_enabled', False)} | "
                f"contract_review={companion_readiness.get('ready_for_contract_review', False)} | "
                f"live_integration={companion_readiness.get('ready_for_live_companion_integration', False)}"
            )
            lines.append(
                f"apps={companion_counts.get('companion_apps', 0)} | "
                f"local_paths={companion_counts.get('local_companion_paths_existing', 0)} | "
                f"read_contract={companion_counts.get('read_contract_rows', 0)} | "
                f"write_contract={companion_counts.get('write_contract_rows', 0)} | "
                f"requirements={companion_counts.get('protocol_requirements', 0)}"
            )
            lines.append(
                f"ok={companion_status_counts.get('ok', 0)} | "
                f"watch={companion_status_counts.get('watch', 0)} | "
                f"warning={companion_status_counts.get('warning', 0)} | "
                f"blocked={companion_status_counts.get('blocked', 0)} | "
                f"pending_queue={companion_counts.get('pending_queue', 0)} | "
                f"sub_agent_pending={companion_counts.get('sub_agent_pending_current', 0)}"
            )
            lines.append(
                f"direct_store_write={bool(companion_counts.get('direct_store_write_allowed', 0))} | "
                f"parent_history_write={bool(companion_counts.get('parent_history_write_allowed', 0))} | "
                f"model_visible_mutation={bool(companion_counts.get('model_visible_mutation_allowed', 0))}"
            )
            lines.append("")
            lines.append("[Companion Apps]")
            apps = companion_readiness.get("companion_apps", []) or []
            if not apps:
                lines.append("-")
            for row in apps:
                if isinstance(row, dict):
                    lines.append(
                        f"- {short(row.get('label', row.get('key', '-')) or '-', 70)} | "
                        f"{row.get('status', '-')} | integration={row.get('integration_enabled', False)} | "
                        f"exists={row.get('exists', False)}"
                    )
                    scope = short(row.get("scope", "") or "", 180)
                    if scope:
                        lines.append(f"  scope={scope}")
                    path = short(row.get("path", "") or "", 180)
                    if path:
                        lines.append(f"  path={path}")
            rows = companion_readiness.get("rows", []) or []
            if rows:
                lines.append("")
                lines.append("[Companion Gates]")
                for row in rows[:14]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 72)} | "
                            f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                        )
                        action = short(row.get("action", "") or "", 180)
                        if action:
                            lines.append(f"  action={action}")
            requirements = companion_readiness.get("protocol_requirements", []) or []
            if requirements:
                lines.append("")
                lines.append("[Companion Protocol Requirements]")
                for row in requirements[:8]:
                    if isinstance(row, dict):
                        lines.append(f"- {row.get('key', '-')} | {row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}")

        if companion_protocol:
            lines.append("")
            lines.append("[Companion Protocol Contract]")
            lines.append(
                f"schema={companion_protocol.get('schema_version', '-') or '-'} | "
                f"status={companion_protocol.get('status', '-') or '-'} | "
                f"integration_enabled={companion_protocol.get('integration_enabled', False)} | "
                f"request_ingest={companion_protocol.get('request_ingest_enabled', False)} | "
                f"receipt_writer={companion_protocol.get('receipt_writer_enabled', False)}"
            )
            lines.append(
                f"request_fields={protocol_counts.get('request_fields', 0)} | "
                f"receipt_fields={protocol_counts.get('receipt_fields', 0)} | "
                f"routes={protocol_counts.get('route_rows', 0)} | "
                f"allowed_future_intents={protocol_counts.get('allowed_future_intents', 0)} | "
                f"blocked_intents={protocol_counts.get('blocked_intents', 0)}"
            )
            lines.append(
                f"route_ok={protocol_route_counts.get('ok', 0)} | "
                f"route_watch={protocol_route_counts.get('watch', 0)} | "
                f"gate_ok={protocol_gate_counts.get('ok', 0)} | "
                f"gate_blocked={protocol_gate_counts.get('blocked', 0)} | "
                f"live_integration={companion_protocol.get('ready_for_live_companion_integration', False)}"
            )
            lines.append(
                f"direct_store_write={companion_protocol.get('direct_store_write_allowed', False)} | "
                f"parent_history_write={companion_protocol.get('parent_history_write_allowed', False)} | "
                f"model_visible_mutation={companion_protocol.get('model_visible_mutation_allowed', False)} | "
                f"desktop_automation={companion_protocol.get('desktop_automation_enabled', False)}"
            )

            request_fields = companion_protocol.get("request_envelope_fields", []) or []
            if request_fields:
                lines.append("")
                lines.append("[Request Envelope Fields]")
                for row in request_fields[:14]:
                    if isinstance(row, dict):
                        required = "required" if row.get("required", False) else "optional"
                        lines.append(
                            f"- {row.get('key', '-')} | {required} | "
                            f"{short(row.get('summary', '-') or '-', 180)}"
                        )
            receipt_fields = companion_protocol.get("receipt_fields", []) or []
            if receipt_fields:
                lines.append("")
                lines.append("[Receipt Fields]")
                for row in receipt_fields[:14]:
                    if isinstance(row, dict):
                        required = "required" if row.get("required", False) else "optional"
                        lines.append(
                            f"- {row.get('key', '-')} | {required} | "
                            f"{short(row.get('summary', '-') or '-', 180)}"
                        )
            routes = companion_protocol.get("route_contract", []) or []
            if routes:
                lines.append("")
                lines.append("[Route Contract]")
                for row in routes[:8]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 70)} | "
                            f"{row.get('status', '-')} | route={short(row.get('route', '-') or '-', 120)}"
                        )
                        lines.append(f"  {short(row.get('summary', '-') or '-', 180)}")
            gates = companion_protocol.get("gate_rows", []) or []
            if gates:
                lines.append("")
                lines.append("[Protocol Gates]")
                for row in gates[:12]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 72)} | "
                            f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                        )
            blocked = companion_protocol.get("blocked_intents", []) or []
            if blocked:
                lines.append("")
                lines.append("[Blocked Companion Intents]")
                for row in blocked[:10]:
                    if isinstance(row, dict):
                        lines.append(f"- {row.get('key', '-')} | {row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}")

        if companion_receipt:
            store = companion_receipt.get("receipt_store", {}) or {}
            lines.append("")
            lines.append("[Companion Receipt Audit]")
            lines.append(
                f"schema={companion_receipt.get('schema_version', '-') or '-'} | "
                f"status={companion_receipt.get('status', '-') or '-'} | "
                f"request_ingest={companion_receipt.get('request_ingest_enabled', False)} | "
                f"receipt_writer={companion_receipt.get('receipt_writer_enabled', False)} | "
                f"integration={companion_receipt.get('integration_enabled', False)}"
            )
            lines.append(
                f"lifecycle={receipt_counts.get('lifecycle_rows', 0)} | "
                f"statuses={receipt_counts.get('receipt_status_rows', 0)} | "
                f"route_receipts={receipt_counts.get('route_receipts', 0)} | "
                f"blocked_receipts={receipt_counts.get('blocked_receipts', 0)} | "
                f"evidence_sources={receipt_counts.get('evidence_sources', 0)}"
            )
            lines.append(
                f"store_exists={store.get('exists', False)} | "
                f"writer_enabled={store.get('writer_enabled', False)} | "
                f"reader_enabled={store.get('reader_enabled', False)} | "
                f"replay_enabled={store.get('replay_enabled', False)} | "
                f"hard_flags={receipt_counts.get('hard_guardrail_flags', 0)}"
            )
            if store.get("path"):
                lines.append(f"store_path={short(store.get('path', ''), 180)}")
            lines.append(
                f"direct_store_write={companion_receipt.get('direct_store_write_allowed', False)} | "
                f"parent_history_write={companion_receipt.get('parent_history_write_allowed', False)} | "
                f"model_visible_mutation={companion_receipt.get('model_visible_mutation_allowed', False)} | "
                f"desktop_automation={companion_receipt.get('desktop_automation_enabled', False)}"
            )
            lifecycle = companion_receipt.get("lifecycle_rows", []) or []
            if lifecycle:
                lines.append("")
                lines.append("[Receipt Lifecycle]")
                for row in lifecycle[:14]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 72)} | "
                            f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                        )
                        rollback = short(row.get("rollback", "") or "", 160)
                        if rollback:
                            lines.append(f"  rollback={rollback}")
            evidence = companion_receipt.get("evidence_sources", []) or []
            if evidence:
                lines.append("")
                lines.append("[Receipt Evidence Sources]")
                for row in evidence[:10]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 72)} | "
                            f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                        )
                        detail = short(row.get("detail", "") or "", 180)
                        if detail:
                            lines.append(f"  path={detail}")
            route_receipts = companion_receipt.get("route_receipts", []) or []
            if route_receipts:
                lines.append("")
                lines.append("[Future Route Receipts]")
                for row in route_receipts[:10]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('key', '-')} | route={short(row.get('source', '-') or '-', 80)} | "
                            f"rollback={short(row.get('rollback', '-') or '-', 120)}"
                        )
            blocked_receipts = companion_receipt.get("blocked_receipts", []) or []
            if blocked_receipts:
                lines.append("")
                lines.append("[Blocked Intent Receipts]")
                for row in blocked_receipts[:10]:
                    if isinstance(row, dict):
                        lines.append(f"- {row.get('key', '-')} | {short(row.get('summary', '-') or '-', 180)}")

        if companion_closure:
            lines.append("")
            lines.append("[Companion Contract Closure]")
            lines.append(
                f"schema={companion_closure.get('schema_version', '-') or '-'} | "
                f"status={companion_closure.get('status', '-') or '-'} | "
                f"ready={companion_closure.get('ready_for_window_close', False)} | "
                f"checks={closure_counts.get('checks', 0)} | "
                f"blocking_rows={closure_counts.get('blocking_rows', 0)}"
            )
            lines.append(
                f"ok={closure_status_counts.get('ok', 0)} | "
                f"watch={closure_status_counts.get('watch', 0)} | "
                f"warning={closure_status_counts.get('warning', 0)} | "
                f"blocked={closure_status_counts.get('blocked', 0)} | "
                f"pending={closure_status_counts.get('pending', 0)}"
            )
            lines.append(
                f"request_ingest={closure_counts.get('request_ingest_enabled', False)} | "
                f"receipt_writer={closure_counts.get('receipt_writer_enabled', False)} | "
                f"integration={closure_counts.get('integration_enabled', False)} | "
                f"live_integration={closure_counts.get('live_companion_integration_enabled', False)}"
            )
            lines.append(
                f"direct_store_write={closure_counts.get('direct_store_write_allowed', False)} | "
                f"parent_history_write={closure_counts.get('parent_history_write_allowed', False)} | "
                f"model_visible_mutation={closure_counts.get('model_visible_mutation_allowed', False)} | "
                f"desktop_automation={closure_counts.get('desktop_automation_enabled', False)} | "
                f"responses_migration={closure_counts.get('responses_migration_enabled', False)}"
            )
            checks = companion_closure.get("checks", []) or []
            if checks:
                lines.append("")
                lines.append("[Closure Checks]")
                for row in checks[:10]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {short(row.get('label', row.get('key', '-')) or '-', 72)} | "
                            f"{row.get('status', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                        )
                        action = short(row.get("action", "") or "", 180)
                        if action:
                            lines.append(f"  action={action}")
            evidence = companion_closure.get("operator_evidence_required", []) or []
            if evidence:
                lines.append("")
                lines.append("[Closure Evidence Required]")
                lines.extend(f"- {short(item, 190)}" for item in evidence[:8])
            guardrails = companion_closure.get("guardrails", []) or []
            if guardrails:
                lines.append("")
                lines.append("[Closure Guardrails]")
                lines.extend(f"- {short(item, 190)}" for item in guardrails[:8])

        cleanup = history_context.get("cleanup_candidates", []) or []
        if cleanup:
            lines.append("")
            lines.append("[Cleanup Candidates]")
            lines.extend(f"- {short(item, 190)}" for item in cleanup if str(item or "").strip())
        guardrails = history_context.get("guardrails", []) or []
        if guardrails:
            lines.append("")
            lines.append("[Guardrails]")
            lines.extend(f"- {short(item, 190)}" for item in guardrails if str(item or "").strip())
        return "\n".join(lines).strip()

    def build_visual_context_text(self, visual_context):
        visual_context = visual_context or {}
        if not isinstance(visual_context, dict):
            return "No visual context snapshot exported yet."
        summary = visual_context.get("summary", {}) or {}
        lanes = summary.get("lanes", []) or []
        lane_bits = []
        for lane in lanes:
            if isinstance(lane, dict):
                lane_bits.append(f"{lane.get('label', lane.get('name', 'lane'))}={lane.get('count', 0)}")
        lines = [
            "[Summary]",
            " | ".join(lane_bits) if lane_bits else "No visual lanes exported yet.",
            f"prior image prompt limit={summary.get('prompt_prior_image_limit', '-')}",
            f"recent prior image messages={summary.get('prompt_recent_image_messages', 0)}",
            f"current screenshot attached={summary.get('current_image_attached', False)}",
            f"local screenshot files={summary.get('local_screenshot_count', 0)}",
        ]
        notes = visual_context.get("notes", []) or []
        if notes:
            lines.append("")
            lines.append("[Notes]")
            lines.extend(f"- {short(note, 180)}" for note in notes if str(note or "").strip())

        lane_titles = (
            ("in_prompt", "In Prompt"),
            ("retained", "Retained"),
            ("local_only", "Local Only"),
        )
        for key, title in lane_titles:
            rows = visual_context.get(key, []) or []
            lines.append("")
            lines.append(f"[{title}]")
            if not rows:
                lines.append("-")
                continue
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    continue
                name = row.get("name") or Path(str(row.get("path", ""))).name or "-"
                source = row.get("source", "-") or "-"
                exists = "exists" if row.get("exists", False) else "missing"
                sticky = " | sticky" if row.get("sticky", False) else ""
                path = row.get("path", "") or ""
                age = format_file_age_text(path, "file") if path else "file -"
                detail = short(row.get("detail", ""), 160)
                timestamp = short(row.get("timestamp", ""), 24)
                lines.append(f"{index}. {short(name, 72)} | {source} | {exists} | {age}{sticky}")
                if timestamp:
                    lines.append(f"   timestamp={timestamp}")
                if detail:
                    lines.append(f"   detail={detail}")
                image_context = row.get("image_context", {}) or {}
                if image_context:
                    sidecar_state = "sidecar" if image_context.get("sidecar_exists", False) else "no sidecar"
                    capture_reason = short(image_context.get("capture_reason", "") or "-", 100)
                    image_hash = image_context.get("hash", "") or "-"
                    lines.append(f"   index={sidecar_state} | hash={image_hash} | capture={capture_reason}")
                if path:
                    lines.append(f"   path={short(path, 180)}")
        return "\n".join(lines).strip()

    def build_image_context_index_text(self, image_index, image_cost_posture=None):
        image_index = image_index or {}
        if not isinstance(image_index, dict):
            return "No image context index snapshot exported yet."
        image_cost_posture = image_cost_posture if isinstance(image_cost_posture, dict) else {}
        summary = image_index.get("summary", {}) or {}
        lines = [
            "[Summary]",
            f"status={summary.get('status', '-') or '-'} | mode={summary.get('mode', '-') or '-'} | schema={summary.get('schema_version', '-')}",
            f"sidecars={summary.get('sidecar_count', 0)} | recent={summary.get('recent_count', 0)} | local screenshots={summary.get('local_screenshot_count', 0)}",
            f"sidecar dir={'found' if summary.get('sidecar_dir_exists', False) else 'missing'} | manifest={'found' if summary.get('manifest_exists', False) else 'missing'}",
            f"latest sidecar={summary.get('latest_sidecar_path') or '-'}",
        ]
        backfill_summary = summary.get("last_backfill_summary", "") or ""
        if backfill_summary:
            lines.append(f"last backfill={short(backfill_summary, 180)}")
        if summary.get("last_metadata_update"):
            lines.append(f"last metadata update={short(summary.get('last_metadata_update', ''), 180)}")
        if summary.get("last_search_summary"):
            lines.append(f"last search={short(summary.get('last_search_summary', ''), 180)}")
        if summary.get("latest_error"):
            lines.append(f"latest error={short(summary.get('latest_error', ''), 180)}")

        if image_cost_posture:
            cost_counts = image_cost_posture.get("counts", {}) or {}
            cost_limits = image_cost_posture.get("limits", {}) or {}
            lines.append("")
            lines.append("[Window 18 Cost Posture]")
            lines.append(
                f"status={image_cost_posture.get('status', '-') or '-'} | schema={image_cost_posture.get('schema_version', '-') or '-'} | "
                f"summary={short(image_cost_posture.get('summary', '-') or '-', 220)}"
            )
            lines.append(
                f"coverage={cost_counts.get('sidecar_coverage_percent', 0)}% | "
                f"in_prompt={cost_counts.get('in_prompt_count', 0)} | retained={cost_counts.get('retained_count', 0)}"
            )
            lines.append(
                f"backfill default/max={cost_limits.get('image_context_backfill_default_limit', '-')}/"
                f"{cost_limits.get('image_context_backfill_max_limit', '-')} | "
                f"search return/max_scan={cost_limits.get('image_context_search_max_limit', '-')}/"
                f"{cost_limits.get('image_context_search_max_scan', '-')} | "
                f"visual cache ttl={cost_limits.get('visual_context_local_scan_ttl_seconds', '-')}s | "
                f"panel list ttl={cost_limits.get('control_panel_screenshot_list_cache_ttl_seconds', '-')}s"
            )
            cost_rows = image_cost_posture.get("rows", []) or []
            for row in cost_rows[:10]:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {row.get('label', row.get('key', 'row'))}: {row.get('status', 'watch')} | "
                    f"cost={row.get('cost', '-')} | {short(row.get('summary', '-') or '-', 180)}"
                )
                action = short(row.get("operator_action", ""), 180)
                if action:
                    lines.append(f"  action={action}")
            guardrails = image_cost_posture.get("guardrails", []) or []
            if guardrails:
                lines.append("guardrails=" + " | ".join(short(item, 80) for item in guardrails[:4]))

        expected_fields = image_index.get("expected_fields", []) or []
        if expected_fields:
            lines.append("")
            lines.append("[Expected Fields]")
            lines.extend(f"- {field}" for field in expected_fields if str(field or "").strip())

        notes = image_index.get("notes", []) or []
        if notes:
            lines.append("")
            lines.append("[Notes]")
            lines.extend(f"- {short(note, 180)}" for note in notes if str(note or "").strip())

        last_backfill = image_index.get("last_backfill", {}) or {}
        if isinstance(last_backfill, dict) and last_backfill:
            lines.append("")
            lines.append("[Last Backfill]")
            lines.append(
                f"limit={last_backfill.get('limit', '-')} | inspected={last_backfill.get('inspected', 0)} | "
                f"created={last_backfill.get('created', 0)} | existing={last_backfill.get('existing', 0)} | failed={last_backfill.get('failed', 0)}"
            )
            if last_backfill.get("completed_at"):
                lines.append(f"completed={short(last_backfill.get('completed_at', ''), 40)}")

        last_update = image_index.get("last_metadata_update", {}) or {}
        if isinstance(last_update, dict) and last_update:
            lines.append("")
            lines.append("[Last Metadata Update]")
            lines.append(
                f"image={last_update.get('image_id', '-') or '-'} | "
                f"fields={', '.join(last_update.get('updated_fields', []) or []) or '-'}"
            )
            if last_update.get("tags"):
                lines.append(f"tags={short('; '.join(last_update.get('tags', []) or []), 160)}")

        last_search = image_index.get("last_search", {}) or {}
        if isinstance(last_search, dict) and last_search:
            lines.append("")
            lines.append("[Last Search]")
            lines.append(short(last_search.get("summary", ""), 220) or "-")
            items = last_search.get("items", []) or []
            if items:
                for search_index, item in enumerate(items[:6], start=1):
                    if not isinstance(item, dict):
                        continue
                    hits = item.get("hits", {}) or {}
                    hit_text = ", ".join(f"{key}:{value}" for key, value in sorted(hits.items())) or "-"
                    lines.append(
                        f"{search_index}. score={item.get('score', 0)} | "
                        f"image={short(item.get('image_id', '-') or '-', 72)} | hits={short(hit_text, 90)}"
                    )
                    if item.get("caption"):
                        lines.append(f"   caption={short(item.get('caption', ''), 160)}")
                    if item.get("ocr_text"):
                        lines.append(f"   ocr={short(item.get('ocr_text', ''), 160)}")
                    if item.get("screenshot_path"):
                        lines.append(f"   screenshot={short(item.get('screenshot_path', ''), 180)}")
            else:
                lines.append("- no returned matches")

        rows = image_index.get("recent", []) or []
        lines.append("")
        lines.append("[Recent Sidecars]")
        if not rows:
            lines.append("-")
            return "\n".join(lines).strip()
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            image_id = row.get("image_id", "-") or "-"
            exists = "image exists" if row.get("exists", False) else "image missing"
            capture_reason = short(row.get("capture_reason", "") or "-", 130)
            capture_hash = row.get("capture_hash") or row.get("file_sha1_prefix") or "-"
            caption_status = row.get("caption_status", "-") or "-"
            ocr_status = row.get("ocr_status", "-") or "-"
            tags = row.get("tags", []) or []
            embedding_ids = row.get("embedding_ids", []) or []
            lines.append(f"{index}. {short(image_id, 72)} | {exists} | hash={capture_hash}")
            lines.append(f"   capture={capture_reason}")
            lines.append(
                f"   caption={caption_status} | ocr={ocr_status} | tags={len(tags)} | embeddings={len(embedding_ids)} | "
                f"model_visible_now={row.get('visible_to_model_now', False)}"
            )
            if row.get("caption"):
                lines.append(f"   caption={short(row.get('caption', ''), 160)}")
            if row.get("ocr_text"):
                lines.append(f"   ocr={short(row.get('ocr_text', ''), 160)}")
            if row.get("screenshot_path"):
                lines.append(f"   screenshot={short(row.get('screenshot_path', ''), 180)}")
            if row.get("sidecar_path"):
                lines.append(f"   sidecar={short(row.get('sidecar_path', ''), 180)}")
        return "\n".join(lines).strip()

    def build_live_harness_text(self, harness, rehearsal=None, probe=None):
        harness = harness or {}
        if not isinstance(harness, dict) or not harness:
            return "No live visual harness snapshot exported yet. Start or refresh the runtime, then use Show Harness."
        rehearsal = rehearsal or {}
        probe = probe or {}
        posture = harness.get("current_posture", {}) or {}
        contract = harness.get("expected_observation_contract", {}) or {}
        readiness = harness.get("readiness", {}) or {}
        next_inference = posture.get("next_inference", {}) or {}
        lines = [
            "[Summary]",
            f"name={harness.get('name', '-') or '-'}",
            f"status={harness.get('status', '-') or '-'} | mode={harness.get('mode', '-') or '-'} | spends_model_calls={harness.get('spends_model_calls', False)}",
            f"purpose={harness.get('purpose', '-') or '-'}",
            "",
            "[Current Posture]",
            f"live_mode={posture.get('live_mode', False)} | action_mode={posture.get('action_mode', '-') or '-'}",
            f"text_model={posture.get('text_model', '-') or '-'} | vision_model={posture.get('vision_model', '-') or '-'} | reasoning_model={posture.get('reasoning_model', '-') or '-'}",
            f"reasoning_effort={posture.get('reasoning_effort', '-') or '-'} | battle_reasoning_effort={posture.get('battle_reasoning_effort', '-') or '-'}",
            f"image_detail={posture.get('image_detail', '-') or '-'} | latest_image_detail={posture.get('latest_image_detail', '-') or '-'}",
            f"max_images_in_history={posture.get('max_images_in_history', '-') or '-'} | max_image_context_messages={posture.get('max_image_context_messages', '-') or '-'}",
            f"next_inference={self._format_next_inference(next_inference)}",
            "",
            "[Expected Observation Contract]",
            f"newest_image_path={contract.get('newest_image_path') or '-'}",
            f"prior_image_cap={contract.get('prior_image_cap', '-')}",
            f"in_prompt_visual_count={contract.get('in_prompt_visual_count', '-')}",
            f"retained_visual_count={contract.get('retained_visual_count', '-')}",
            f"local_screenshot_count={contract.get('local_screenshot_count', '-')}",
            f"prompt_included_rows={contract.get('prompt_included_rows', '-')}",
            f"setting_state={contract.get('setting_state', '-') or '-'}",
            f"cleanup_state={contract.get('cleanup_state', '-') or '-'}",
            "",
            "[Readiness]",
            f"ready_for_offline_rehearsal={readiness.get('ready_for_offline_rehearsal', False)}",
            f"ready_for_live={readiness.get('ready_for_live', False)}",
        ]
        warnings = readiness.get("warnings", []) or []
        if warnings:
            lines.append("")
            lines.append("[Warnings]")
            lines.extend(f"- {short(item, 190)}" for item in warnings if str(item or "").strip())

        expectations = harness.get("human_observed_expectations", []) or []
        if expectations:
            lines.append("")
            lines.append("[Human Expectations]")
            for row in expectations:
                if not isinstance(row, dict):
                    continue
                lines.append(f"- {row.get('name', '-')}: {short(row.get('expected', '') or '-', 190)}")

        if isinstance(rehearsal, dict) and rehearsal:
            lines.extend([
                "",
                "[Latest Offline Rehearsal]",
                f"status={rehearsal.get('status', '-') or '-'} | passed={rehearsal.get('passed', False)} | spends_model_calls={rehearsal.get('spends_model_calls', False)}",
                f"generated_at={rehearsal.get('generated_at', '-') or '-'}",
                f"summary={rehearsal.get('summary', '-') or '-'}",
                f"next={short(rehearsal.get('next_recommended_action', '') or '-', 190)}",
            ])
            for check in (rehearsal.get("checks", []) or [])[:12]:
                if not isinstance(check, dict):
                    continue
                detail = check.get("detail", "")
                line = f"- {check.get('key', 'check')}: {check.get('status', 'warning')} | {short(check.get('summary', '') or '-', 140)}"
                if detail:
                    line += f" | {short(detail, 120)}"
                lines.append(line)
        else:
            lines.extend([
                "",
                "[Latest Offline Rehearsal]",
                "No rehearsal result recorded yet. Use Run Offline Rehearsal after applying a safe offline posture.",
            ])

        if isinstance(probe, dict) and probe:
            probe_tier = str(probe.get("probe_tier", "custom") or "custom")
            lines.extend([
                "",
                "[Live Probe]",
                f"status={probe.get('status', '-') or '-'} | spends_model_calls_now={probe.get('spends_model_calls', False)}",
                f"probe_tier={probe_tier}",
                f"model={probe.get('model', '-') or '-'} | reasoning={probe.get('reasoning_effort', '-') or '-'} | verbosity={probe.get('verbosity', '-') or '-'}",
                f"image_detail={probe.get('image_detail', '-') or '-'} | latest={probe.get('latest_image_detail', '-') or '-'}",
                f"expected_newest={short(probe.get('expected_newest_image_path', '') or '-', 190)}",
                f"note={short(probe.get('note', '') or '-', 190)}",
                f"prompt={short(probe.get('probe_prompt', '') or '-', 190)}",
            ])
            for check in (probe.get("checks", []) or [])[:8]:
                if not isinstance(check, dict):
                    continue
                detail = check.get("detail", "")
                line = f"- {check.get('key', 'check')}: {check.get('status', 'watch')} | {short(check.get('summary', '') or '-', 140)}"
                if detail:
                    line += f" | {short(detail, 120)}"
                lines.append(line)
            result = probe.get("last_result", {}) or {}
            if result:
                lines.append(f"result={result.get('summary', '-') or '-'}")
                for check in (result.get("checks", []) or [])[:8]:
                    if not isinstance(check, dict):
                        continue
                    detail = check.get("detail", "")
                    line = f"- result {check.get('key', 'check')}: {check.get('status', 'watch')} | {short(check.get('summary', '') or '-', 140)}"
                    if detail:
                        line += f" | {short(detail, 120)}"
                    lines.append(line)
        else:
            lines.extend([
                "",
                "[Live Probe]",
                "No probe armed yet. Arm Cheap or Strong keeps live mode off and queues only the one-turn probe posture.",
            ])

        stages = harness.get("model_escalation", []) or []
        if stages:
            lines.append("")
            lines.append("[Escalation]")
            for row in stages:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {row.get('stage', '-')}: model={row.get('model', '-') or '-'} | "
                    f"goal={short(row.get('goal', '') or '-', 180)}"
                )

        stops = harness.get("bus_stops", []) or []
        if stops:
            lines.append("")
            lines.append("[Bus Stops]")
            lines.extend(f"- {short(item, 180)}" for item in stops if str(item or "").strip())

        notes = harness.get("notes", []) or []
        if notes:
            lines.append("")
            lines.append("[Notes]")
            lines.extend(f"- {short(item, 180)}" for item in notes if str(item or "").strip())
        return "\n".join(lines).strip()

    def build_responses_shadow_text(self, responses_shadow):
        responses_shadow = responses_shadow or {}
        if not isinstance(responses_shadow, dict) or not responses_shadow:
            return "No Responses Shadow snapshot exported yet. Start or refresh the runtime, then use Show Contract."

        summary = responses_shadow.get("summary", {}) or {}
        readiness = responses_shadow.get("readiness", {}) or {}
        closure = responses_shadow.get("shadow_closure_readiness", {}) or {}
        closure_counts = closure.get("status_counts", {}) or {}
        lines = [
            "[Summary]",
            (
                f"window={responses_shadow.get('window', '-') or '-'} | "
                f"slice={responses_shadow.get('slice', '-') or '-'} | "
                f"status={responses_shadow.get('status', '-') or '-'}"
            ),
            f"mode={responses_shadow.get('mode', '-') or '-'} | schema={responses_shadow.get('schema_version', '-') or '-'}",
            (
                f"current_transport={summary.get('current_transport', '-') or '-'} | "
                f"shadow_transport={summary.get('shadow_transport', '-') or '-'} | "
                f"default_migration_enabled={summary.get('default_migration_enabled', False)}"
            ),
            (
                f"responses_api_call_enabled={summary.get('responses_api_call_enabled', False)} | "
                f"shadow_request_builder_enabled={summary.get('shadow_request_builder_enabled', False)} | "
                f"tool_calls_enabled={summary.get('tool_calls_enabled', False)}"
            ),
            (
                f"offline_payload_parity_ready={summary.get('offline_payload_parity_ready', False)} | "
                f"live_comparison_ready={summary.get('live_comparison_ready', False)} | "
                f"blockers={summary.get('blocker_rows', 0)}"
            ),
            (
                f"stateful_profile={summary.get('stateful_active_profile', '-') or '-'} | "
                f"previous_response_id_active={summary.get('previous_response_id_active', False)} | "
                f"conversation_id_active={summary.get('conversation_id_active', False)}"
            ),
            (
                f"prompt_included_rows={summary.get('prompt_included_rows', 0)} | "
                f"prompt_omitted_rows={summary.get('prompt_omitted_rows', 0)} | "
                f"in_prompt_visual_count={summary.get('in_prompt_visual_count', 0)}"
            ),
            (
                f"live_probe={summary.get('shadow_live_probe_status', '-') or '-'} | "
                f"model={summary.get('shadow_live_probe_model', '-') or '-'} | "
                f"send_enabled={summary.get('shadow_live_probe_send_enabled', False)} | "
                f"api_call_enabled={summary.get('shadow_live_probe_api_call_enabled', False)}"
            ),
            (
                f"closure={summary.get('closure_readiness_status', closure.get('status', '-')) or '-'} | "
                f"ready_for_window_close={summary.get('closure_ready_for_window_close', closure.get('ready_for_window_close', False))} | "
                f"closure_blocking_rows={summary.get('closure_blocking_rows', len(closure.get('blocking_rows', []) or []))}"
            ),
        ]

        if closure:
            lines.append("")
            lines.append("[Closure / Fallback Readiness]")
            lines.append(
                f"closure_id={closure.get('closure_id', '-') or '-'} | "
                f"status={closure.get('status', '-') or '-'} | schema={closure.get('schema_version', '-') or '-'}"
            )
            lines.append(
                f"ready={closure.get('ready_for_window_close', False)} | "
                f"current_transport={closure.get('current_transport', '-') or '-'} | "
                f"active_profile={closure.get('active_profile', '-') or '-'} | "
                f"fallback_profile={closure.get('fallback_profile', '-') or '-'}"
            )
            lines.append(
                f"send_enabled={closure.get('send_enabled', False)} | "
                f"api_call_enabled={closure.get('api_call_enabled', False)} | "
                f"default_migration_enabled={closure.get('default_migration_enabled', False)} | "
                f"tool_calls_enabled={closure.get('tool_calls_enabled', False)}"
            )
            lines.append(
                f"counts ok={closure_counts.get('ok', 0)} | watch={closure_counts.get('watch', 0)} | "
                f"warning={closure_counts.get('warning', 0)} | blocked={closure_counts.get('blocked', 0)} | "
                f"pending={closure_counts.get('pending', 0)}"
            )
            checks = closure.get("checks", []) or []
            if checks:
                lines.append("closure_checks:")
                for row in checks[:14]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('label', row.get('key', '-'))}: "
                            f"{row.get('status', '-') or '-'} | {short(row.get('summary', '') or '-', 170)}"
                        )
            blocking = closure.get("blocking_rows", []) or []
            if blocking:
                lines.append("attention:")
                for row in blocking[:8]:
                    if isinstance(row, dict):
                        lines.append(f"- {row.get('label', row.get('key', '-'))}: {row.get('status', '-') or '-'}")
            evidence = closure.get("operator_evidence_required", []) or []
            if evidence:
                lines.append("operator_evidence_required:")
                lines.extend(f"- {short(item, 190)}" for item in evidence[:8] if str(item or "").strip())

        docs_notes = responses_shadow.get("docs_notes", []) or []
        if docs_notes:
            lines.append("")
            lines.append("[Docs Notes]")
            lines.extend(f"- {short(note, 190)}" for note in docs_notes if str(note or "").strip())

        preview = responses_shadow.get("shadow_payload_preview", {}) or {}
        if preview:
            preview_summary = preview.get("summary", {}) or {}
            payload = preview.get("payload", {}) or {}
            lines.append("")
            lines.append("[No-Send Payload Preview]")
            lines.append(
                f"preview_id={preview.get('preview_id', '-') or '-'} | "
                f"status={preview.get('status', '-') or '-'} | schema={preview.get('schema_version', '-') or '-'}"
            )
            lines.append(
                f"endpoint={preview.get('endpoint', '-') or '-'} | "
                f"send_enabled={preview.get('send_enabled', False)} | api_call_enabled={preview.get('api_call_enabled', False)} | "
                f"store={preview_summary.get('store', False)} | tools={preview_summary.get('tools', 0)}"
            )
            lines.append(
                f"model={preview_summary.get('model', payload.get('model', '-')) or '-'} | "
                f"input_messages={preview_summary.get('input_messages', 0)} | "
                f"ledger_rows_used={preview_summary.get('ledger_rows_used', 0)} | "
                f"included_rows_used={preview_summary.get('included_rows_used', 0)}"
            )
            lines.append(
                f"visual_placeholders={preview_summary.get('visual_placeholders', 0)} | "
                f"reasoning={preview_summary.get('reasoning_effort', '-') or '-'} | "
                f"verbosity={preview_summary.get('verbosity', '-') or '-'} | "
                f"completeness={preview.get('payload_completeness', '-') or '-'}"
            )
            omitted_fields = preview.get("omitted_fields", []) or []
            if omitted_fields:
                lines.append("omitted_fields=" + ", ".join(str(item) for item in omitted_fields[:10]))
            send_blockers = preview.get("send_blockers", []) or []
            if send_blockers:
                lines.append("send_blockers:")
                lines.extend(f"- {short(item, 190)}" for item in send_blockers[:8] if str(item or "").strip())
            checks = preview.get("parity_checks", []) or []
            if checks:
                lines.append("parity_checks:")
                for row in checks[:8]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('label', row.get('key', '-'))}: "
                            f"{row.get('status', '-') or '-'} | {short(row.get('summary', '') or '-', 160)}"
                        )
            diff_rows = preview.get("diff_rows", []) or []
            if diff_rows:
                lines.append("diff_preview:")
                for row in diff_rows[:8]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('label', row.get('key', '-'))}: "
                            f"{row.get('status', '-') or '-'} | "
                            f"chat={short(row.get('current_chat_completions', '') or '-', 90)} | "
                            f"responses={short(row.get('responses_shadow_candidate', '') or '-', 90)}"
                        )
            source_rows = preview.get("source_rows", []) or []
            if source_rows:
                lines.append("source_rows:")
                for row in source_rows[:10]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('lane', '-') or '-'} | "
                            f"{short(row.get('summary', row.get('label', '-')) or '-', 180)}"
                        )

        posture = responses_shadow.get("shadow_offline_posture", {}) or {}
        if posture:
            token_estimate = posture.get("token_estimate", {}) or {}
            cost_estimate = posture.get("cost_estimate", {}) or {}
            state_posture = posture.get("state_posture", {}) or {}
            lines.append("")
            lines.append("[Offline Token / Cost / State Posture]")
            lines.append(
                f"posture_id={posture.get('posture_id', '-') or '-'} | "
                f"status={posture.get('status', '-') or '-'} | schema={posture.get('schema_version', '-') or '-'}"
            )
            lines.append(
                f"send_enabled={posture.get('send_enabled', False)} | "
                f"api_call_enabled={posture.get('api_call_enabled', False)} | "
                f"payload_preview={posture.get('payload_preview_id', '-') or '-'}"
            )
            lines.append(
                f"token_method={token_estimate.get('method', '-') or '-'} | "
                f"estimated_input_tokens={token_estimate.get('estimated_input_tokens', 0)} | "
                f"text_parts={token_estimate.get('text_parts', 0)} | "
                f"image_tokens_estimated={token_estimate.get('image_tokens_estimated', False)}"
            )
            lines.append(
                f"model={cost_estimate.get('model', '-') or '-'} | "
                f"pricing_source={cost_estimate.get('pricing_source', '-') or '-'} | "
                f"input_rate={cost_estimate.get('input_usd_per_1m', '-')}/1M | "
                f"output_rate={cost_estimate.get('output_usd_per_1m', '-')}/1M"
            )
            lines.append(
                f"estimated_total_usd={cost_estimate.get('estimated_total_usd', '-')} | "
                f"upper_total_usd={cost_estimate.get('estimated_upper_total_usd', '-')} | "
                f"state_risk={state_posture.get('risk', '-') or '-'}"
            )
            state_rows = state_posture.get("rows", []) or []
            if state_rows:
                lines.append("state_rows:")
                for row in state_rows[:8]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('label', row.get('key', '-'))}: "
                            f"{row.get('status', '-') or '-'} | {short(row.get('summary', '') or '-', 160)}"
                        )
            comparison_rows = posture.get("comparison_rows", []) or []
            if comparison_rows:
                lines.append("offline_comparison:")
                for row in comparison_rows[:8]:
                    if isinstance(row, dict):
                        lines.append(
                            f"- {row.get('label', row.get('key', '-'))}: "
                            f"{row.get('status', '-') or '-'} | {short(row.get('evidence', '') or '-', 160)}"
                        )
            posture_guardrails = posture.get("guardrails", []) or []
            if posture_guardrails:
                lines.append("posture_guardrails:")
                lines.extend(f"- {short(item, 190)}" for item in posture_guardrails[:8] if str(item or "").strip())

        probe = responses_shadow.get("shadow_live_probe", {}) or {}
        if probe:
            lines.append("")
            lines.append("[Operator-Armed Live Probe Scaffold]")
            lines.append(
                f"probe_id={probe.get('probe_id', '-') or '-'} | "
                f"status={probe.get('status', '-') or '-'} | schema={probe.get('schema_version', '-') or '-'}"
            )
            lines.append(
                f"model={probe.get('model', '-') or '-'} | tier={probe.get('probe_tier', '-') or '-'} | "
                f"reasoning={probe.get('reasoning_effort', '-') or '-'} | verbosity={probe.get('verbosity', '-') or '-'}"
            )
            lines.append(
                f"send_enabled={probe.get('send_enabled', False)} | "
                f"api_call_enabled={probe.get('api_call_enabled', False)} | "
                f"default_migration_enabled={probe.get('default_migration_enabled', False)} | "
                f"spends_model_calls={probe.get('spends_model_calls', False)}"
            )
            lines.append(
                f"payload_preview={probe.get('payload_preview_id', '-') or '-'} | "
                f"offline_posture={probe.get('offline_posture_id', '-') or '-'}"
            )
            lines.append(
                f"estimated_input_tokens={probe.get('estimated_input_tokens', 0)} | "
                f"estimated_total_usd={probe.get('estimated_total_usd', '-')} | "
                f"upper_total_usd={probe.get('estimated_upper_total_usd', '-')} | "
                f"state_risk={probe.get('state_risk', '-') or '-'}"
            )
            if probe.get("future_run_command"):
                lines.append(f"future_run={probe.get('future_run_command', '-') or '-'}")
            if probe.get("note"):
                lines.append(f"note={short(probe.get('note', '') or '-', 190)}")
            checks = probe.get("checks", []) or []
            if checks:
                lines.append("probe_checks:")
                for row in checks[:10]:
                    if isinstance(row, dict):
                        detail = row.get("detail", "")
                        line = (
                            f"- {row.get('key', 'check')}: {row.get('status', 'watch')} | "
                            f"{short(row.get('summary', '') or '-', 160)}"
                        )
                        if detail:
                            line += f" | {short(detail, 140)}"
                        lines.append(line)
            probe_guardrails = probe.get("guardrails", []) or []
            if probe_guardrails:
                lines.append("probe_guardrails:")
                lines.extend(f"- {short(item, 190)}" for item in probe_guardrails[:8] if str(item or "").strip())

        contract_rows = responses_shadow.get("comparison_contract", []) or []
        if contract_rows:
            lines.append("")
            lines.append("[Comparison Contract]")
            for row in contract_rows:
                if not isinstance(row, dict):
                    continue
                label = row.get("label", row.get("key", "-")) or "-"
                lines.append(f"- {label}: status={row.get('status', '-') or '-'}")
                lines.append(f"  current={short(row.get('current_chat_completions', '') or '-', 190)}")
                lines.append(f"  shadow={short(row.get('responses_shadow_candidate', '') or '-', 190)}")
                lines.append(f"  guardrail={short(row.get('guardrail', '') or '-', 190)}")
                evidence = row.get("evidence", "")
                if evidence:
                    lines.append(f"  evidence={short(evidence, 160)}")

        readiness_rows = readiness.get("rows", []) or []
        if readiness_rows:
            lines.append("")
            lines.append("[Readiness]")
            for row in readiness_rows:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"- {row.get('label', row.get('key', '-'))}: "
                    f"{row.get('status', '-') or '-'} | {short(row.get('summary', '') or '-', 180)}"
                )
                if row.get("detail"):
                    lines.append(f"  detail={short(row.get('detail', ''), 180)}")

        blockers = readiness.get("blockers", []) or []
        if blockers:
            lines.append("")
            lines.append("[Blockers]")
            for row in blockers:
                if isinstance(row, dict):
                    lines.append(f"- {row.get('label', row.get('key', '-'))}: {row.get('status', '-') or '-'}")

        guardrails = responses_shadow.get("guardrails", []) or []
        if guardrails:
            lines.append("")
            lines.append("[Guardrails]")
            lines.extend(f"- {short(item, 190)}" for item in guardrails if str(item or "").strip())

        bus_stops = responses_shadow.get("bus_stops", []) or []
        if bus_stops:
            lines.append("")
            lines.append("[Bus Stops]")
            lines.extend(f"- {short(item, 190)}" for item in bus_stops if str(item or "").strip())

        docs_sources = responses_shadow.get("docs_sources", []) or []
        if docs_sources:
            lines.append("")
            lines.append("[Docs Sources]")
            lines.extend(f"- {short(item, 190)}" for item in docs_sources if str(item or "").strip())
        return "\n".join(lines).strip()

    def build_context_files_text(self, context_files):
        context_files = context_files or {}
        if not isinstance(context_files, dict):
            return "No context file shelf exported yet."
        summary = context_files.get("summary", {}) or {}
        lines = [
            "[Summary]",
            (
                f"mode={summary.get('mode', 'read_only_inventory')} | "
                f"files={summary.get('existing', 0)}/{summary.get('total', 0)} | "
                f"pinned={summary.get('pinned', 0)} | "
                f"visible_to_model_now={summary.get('visible_to_model_now', 0)} | "
                f"refresh_on_wake={summary.get('refresh_on_wake', 0)}"
            ),
            "This shelf is inventory only; it does not attach files to model context.",
        ]
        notes = context_files.get("notes", []) or []
        if notes:
            lines.append("")
            lines.append("[Notes]")
            lines.extend(f"- {short(note, 180)}" for note in notes if str(note or "").strip())

        groups = {}
        for row in context_files.get("files", []) or []:
            if not isinstance(row, dict):
                continue
            group = row.get("group", "project") or "project"
            groups.setdefault(group, []).append(row)
        for group in sorted(groups):
            lines.append("")
            lines.append(f"[{group}]")
            for index, row in enumerate(groups[group], start=1):
                label = row.get("label") or row.get("key") or row.get("name") or "-"
                path = row.get("path", "") or ""
                exists = "exists" if row.get("exists", False) else "missing"
                flags = []
                if row.get("pinned", False):
                    flags.append("pinned")
                if row.get("visible_to_user", False):
                    flags.append("user-visible")
                if row.get("visible_to_model_now", False):
                    flags.append("model-visible-now")
                else:
                    flags.append("not-model-visible")
                if row.get("refresh_on_wake", False):
                    flags.append("refresh-on-wake")
                kind = row.get("kind", "file") or "file"
                age = format_file_age_text(path, "file") if path else "file -"
                lines.append(f"{index}. {short(label, 72)} | {kind} | {exists} | {', '.join(flags)} | {age}")
                note = short(row.get("note", ""), 160)
                if note:
                    lines.append(f"   note={note}")
                if path:
                    lines.append(f"   path={short(path, 180)}")
        return "\n".join(lines).strip()

    def build_overview_text(self, state):
        route = state.get("route_state", {})
        memory_tiers = state.get("memory_tiers", {}) or {}
        command_drip = state.get("command_drip", {}) or {}
        planning = state.get("planning", {}) or {}
        scheduler = state.get("scheduler", {}) or {}
        visual_context = state.get("visual_context", {}) or {}
        visual_summary = visual_context.get("summary", {}) or {}
        image_cost_posture = state.get("image_cost_posture", {}) or {}
        image_cost_counts = image_cost_posture.get("counts", {}) or {}
        image_cost_limits = image_cost_posture.get("limits", {}) or {}
        image_cost_actions = image_cost_posture.get("next_actions", []) or []
        context_files = state.get("context_files", {}) or {}
        context_file_summary = context_files.get("summary", {}) or {}
        prompt_ledger = state.get("prompt_context_ledger", {}) or {}
        prompt_ledger_summary = prompt_ledger.get("summary", {}) or {}
        context_marks = state.get("context_marks", {}) or {}
        context_marks_summary = context_marks.get("summary", {}) or {}
        history_context = state.get("history_context_service", {}) or {}
        history_context_summary = history_context.get("summary", {}) or {}
        companion_readiness = state.get("companion_contract_readiness", {}) or {}
        companion_readiness_counts = companion_readiness.get("counts", {}) or {}
        companion_readiness_status_counts = companion_readiness.get("status_counts", {}) or {}
        companion_protocol = state.get("companion_protocol_contract", {}) or {}
        companion_protocol_counts = companion_protocol.get("counts", {}) or {}
        companion_protocol_route_counts = companion_protocol.get("route_status_counts", {}) or {}
        companion_protocol_gate_counts = companion_protocol.get("gate_status_counts", {}) or {}
        companion_receipt = state.get("companion_receipt_audit", {}) or {}
        companion_receipt_counts = companion_receipt.get("counts", {}) or {}
        companion_receipt_store = companion_receipt.get("receipt_store", {}) or {}
        companion_closure = state.get("companion_contract_closure", {}) or {}
        companion_closure_counts = companion_closure.get("counts", {}) or {}
        companion_closure_status_counts = companion_closure.get("status_counts", {}) or {}
        portal_intake = state.get("portal_companion_intake", {}) or {}
        portal_intake_counts = portal_intake.get("counts", {}) or {}
        portal_intake_status_counts = portal_intake.get("status_counts", {}) or {}
        portal_intake_gate_counts = portal_intake.get("stage_gate_counts", {}) or {}
        portal_intake_actions = portal_intake.get("next_actions", []) or []
        portal_intake_questions = portal_intake.get("open_questions", []) or []
        agent_registry = state.get("agent_registry", {}) or {}
        agent_registry_summary = agent_registry.get("summary", {}) or {}
        agent_suggestions = state.get("agent_suggestions", {}) or {}
        agent_suggestions_summary = agent_suggestions.get("summary", {}) or {}
        agent_tasks = state.get("agent_tasks", {}) or {}
        agent_tasks_summary = agent_tasks.get("summary", {}) or {}
        agent_pending_gate = state.get("agent_pending_gate", {}) or {}
        agent_pending_gate_summary = agent_pending_gate.get("summary", {}) or {}
        agent_pending_insert_dry_run = state.get("agent_pending_insert_dry_run", {}) or {}
        agent_pending_insert_dry_run_summary = agent_pending_insert_dry_run.get("summary", {}) or {}
        agent_helper_closure = state.get("agent_helper_closure", {}) or {}
        agent_helper_closure_counts = agent_helper_closure.get("counts", {}) or {}
        agent_helper_closure_status_counts = agent_helper_closure.get("status_counts", {}) or {}
        live_harness = state.get("live_visual_harness", {}) or {}
        harness_rehearsal = state.get("live_visual_harness_rehearsal", {}) or {}
        harness_probe = state.get("live_visual_harness_probe", {}) or {}
        harness_posture = live_harness.get("current_posture", {}) or {}
        harness_contract = live_harness.get("expected_observation_contract", {}) or {}
        harness_readiness = live_harness.get("readiness", {}) or {}
        harness_warnings = harness_readiness.get("warnings", []) or []
        responses_shadow = state.get("responses_shadow_transport", {}) or {}
        responses_summary = responses_shadow.get("summary", {}) or {}
        responses_closure = responses_shadow.get("shadow_closure_readiness", {}) or {}
        closure_counts = responses_closure.get("status_counts", {}) or {}
        visual_lane_bits = []
        for lane in visual_summary.get("lanes", []) or []:
            if isinstance(lane, dict):
                visual_lane_bits.append(f"{lane.get('label', lane.get('name', 'lane'))}={lane.get('count', 0)}")
        episodic = state.get("episodic_memory", {}) or {}
        rehydration = state.get("rehydration", {}) or {}
        rehydration_explain = rehydration.get("explainability", {}) or {}
        rehydration_counts = rehydration.get("live_memory_counts", {}) or {}
        monitors = state.get("monitors", {}) or {}
        runtime_health = state.get("runtime_health", {}) or {}
        runtime_health_rows = [row for row in (runtime_health.get("rows", []) or []) if isinstance(row, dict)]
        runtime_health_actions = runtime_health.get("next_actions", []) or []
        operator_risk = state.get("operator_risk_summary", {}) or {}
        operator_risk_counts = operator_risk.get("counts", {}) or {}
        operator_risk_rows = [row for row in (operator_risk.get("rows", []) or []) if isinstance(row, dict)]
        operator_risk_actions = operator_risk.get("next_actions", []) or []
        prompt_inclusion = state.get("prompt_inclusion_readiness", {}) or {}
        prompt_inclusion_counts = prompt_inclusion.get("counts", {}) or {}
        prompt_inclusion_rows = [row for row in (prompt_inclusion.get("rows", []) or []) if isinstance(row, dict)]
        prompt_inclusion_actions = prompt_inclusion.get("next_actions", []) or []
        prompt_preview = state.get("prompt_inclusion_preview", {}) or {}
        prompt_preview_counts = prompt_preview.get("counts", {}) or {}
        prompt_rehearsal = state.get("prompt_inclusion_rehearsal", {}) or {}
        prompt_rehearsal_counts = prompt_rehearsal.get("counts", {}) or {}
        prompt_activation = state.get("prompt_inclusion_activation_checklist", {}) or {}
        prompt_activation_counts = prompt_activation.get("counts", {}) or {}
        prompt_activation_state = state.get("prompt_inclusion_activation", {}) or {}
        prompt_activation_inner = prompt_activation_state.get("activation", {}) or {}
        prompt_activation_state_counts = prompt_activation_state.get("counts", {}) or {}
        prompt_closure = state.get("prompt_inclusion_closure", {}) or {}
        prompt_closure_counts = prompt_closure.get("status_counts", {}) or {}
        state_export_monitor = monitors.get("state_export", {}) or state.get("state_export", {}) or {}
        state_consistency_monitor = monitors.get("runtime_state_consistency", {}) or {}
        queue_bridge_monitor = monitors.get("queue_bridge", {}) or state.get("queue_bridge", {}) or {}
        mutation_admission = state.get("mutation_admission", {}) or {}
        gameplay_monitor = monitors.get("gameplay", {}) or state.get("gameplay", {}) or {}
        monitor_lines = [
            f"overall={monitors.get('overall_status', 'ok')}",
            f"summary={monitors.get('summary', format_monitor_summary(monitors))}",
        ]
        for check in (monitors.get("checks", []) or [])[:8]:
            line = f"{check.get('key', 'check')}={check.get('status', 'watch')} | {check.get('summary', '-')}"
            detail = check.get("detail", "")
            if detail:
                line += f" | {detail}"
            monitor_lines.append(line)
        runtime_health_lines = [
            f"schema={runtime_health.get('schema_version', '-') or '-'} | mode={runtime_health.get('mode', '-') or '-'}",
            f"status={runtime_health.get('status', 'not_exported')} | summary={runtime_health.get('summary', '-') or '-'}",
        ]
        for row in runtime_health_rows[:10]:
            line = f"{row.get('key', 'row')}={row.get('status', 'watch')} | {row.get('summary', '-')}"
            if row.get("operator_action"):
                line += f" | action={row.get('operator_action')}"
            runtime_health_lines.append(line)
        if runtime_health_actions:
            runtime_health_lines.append("next_actions:")
            for action in runtime_health_actions[:6]:
                runtime_health_lines.append(f"- {action}")
        operator_risk_lines = [
            f"schema={operator_risk.get('schema_version', '-') or '-'} | mode={operator_risk.get('mode', '-') or '-'}",
            f"status={operator_risk.get('status', 'not_exported')} | summary={operator_risk.get('summary', '-') or '-'}",
            (
                f"risks cost={operator_risk_counts.get('cost_risk', '-')} | "
                f"action={operator_risk_counts.get('action_risk', '-')} | "
                f"context={operator_risk_counts.get('context_risk', '-')} | "
                f"commands={operator_risk_counts.get('command_risk', '-')} | "
                f"transport={operator_risk_counts.get('transport_risk', '-')} | "
                f"access={operator_risk_counts.get('access_risk', '-')}"
            ),
            (
                f"pending={operator_risk_counts.get('pending_commands', 0)} | "
                f"due={operator_risk_counts.get('due_pending_commands', 0)} | "
                f"stale_due={operator_risk_counts.get('stale_due_pending_commands', 0)} | "
                f"prompt_watch_rows={operator_risk_counts.get('prompt_watch_rows', 0)} | "
                f"agent_candidates={operator_risk_counts.get('agent_suggestion_candidates', 0)} | "
                f"staged={operator_risk_counts.get('agent_suggestion_staged_candidates', 0)}"
            ),
        ]
        for row in operator_risk_rows[:8]:
            line = f"{row.get('key', 'row')}={row.get('status', 'watch')} | {row.get('summary', '-')}"
            if row.get("operator_action"):
                line += f" | action={row.get('operator_action')}"
            operator_risk_lines.append(line)
        if operator_risk_actions:
            operator_risk_lines.append("next_actions:")
            for action in operator_risk_actions[:6]:
                operator_risk_lines.append(f"- {action}")
        prompt_inclusion_lines = [
            f"schema={prompt_inclusion.get('schema_version', '-') or '-'} | mode={prompt_inclusion.get('mode', '-') or '-'}",
            f"status={prompt_inclusion.get('status', 'not_exported')} | summary={prompt_inclusion.get('summary', '-') or '-'}",
            (
                f"activation_enabled={prompt_inclusion.get('activation_enabled', False)} | "
                f"ready_for_operator_review={prompt_inclusion.get('ready_for_operator_review', False)} | "
                f"hard_flags={prompt_inclusion_counts.get('hard_guardrail_flags', 0)}"
            ),
            (
                f"approved_prompt_pins={prompt_inclusion_counts.get('approved_prompt_pin_candidates', 0)} | "
                f"approved_do_not_include={prompt_inclusion_counts.get('approved_do_not_include_candidates', 0)} | "
                f"active_marks={prompt_inclusion_counts.get('active_context_marks', 0)}"
            ),
            (
                f"history_write_paths={prompt_inclusion_counts.get('enabled_history_write_paths', 0)} | "
                f"model_visible_marks={prompt_inclusion_counts.get('model_visible_marks', 0)} | "
                f"staged_agent_suggestions={prompt_inclusion_counts.get('staged_agent_suggestions', 0)}"
            ),
            (
                f"preview={prompt_preview.get('status', 'not_exported')} | "
                f"would_add={prompt_preview_counts.get('proposed_additions', 0)} | "
                f"would_omit={prompt_preview_counts.get('proposed_omissions', 0)} | "
                f"send_enabled={prompt_preview.get('send_enabled', False)}"
            ),
            (
                f"rehearsal={prompt_rehearsal.get('status', 'not_run')} | "
                f"rehearsal_add={prompt_rehearsal_counts.get('rehearsal_additions', 0)} | "
                f"rehearsal_omit={prompt_rehearsal_counts.get('rehearsal_omissions', 0)} | "
                f"active_after={prompt_rehearsal_counts.get('active_rehearsal_marks_after', 0)}"
            ),
            (
                f"activation_review={prompt_activation.get('status', 'not_exported')} | "
                f"checks={prompt_activation_counts.get('required_checks_passed', 0)}/{prompt_activation_counts.get('required_checks', 0)} | "
                f"activation_available={prompt_activation.get('activation_control_available', False)}"
            ),
            (
                f"activation_state={prompt_activation_state.get('status', 'off')} | "
                f"enabled={prompt_activation_inner.get('enabled', False)} | "
                f"proof={prompt_activation_inner.get('offline_proof_status', 'not_run')} | "
                f"pins={prompt_activation_state_counts.get('active_prompt_pins', 0)} | "
                f"omissions={prompt_activation_state_counts.get('active_omissions', 0)}"
            ),
            (
                f"closure={prompt_closure.get('status', 'not_exported')} | "
                f"ready={prompt_closure.get('ready_for_window_close', False)} | "
                f"ok={prompt_closure_counts.get('ok', 0)} | "
                f"watch={prompt_closure_counts.get('watch', 0)} | "
                f"warning={prompt_closure_counts.get('warning', 0)} | "
                f"blocked={prompt_closure_counts.get('blocked', 0)}"
            ),
        ]
        for row in prompt_inclusion_rows[:8]:
            line = f"{row.get('key', 'row')}={row.get('status', 'watch')} | {row.get('summary', '-')}"
            if row.get("operator_action"):
                line += f" | action={row.get('operator_action')}"
            prompt_inclusion_lines.append(line)
        if prompt_inclusion_actions:
            prompt_inclusion_lines.append("next_actions:")
            for action in prompt_inclusion_actions[:6]:
                prompt_inclusion_lines.append(f"- {action}")
        gameplay_monitor_lines = [
            f"summary={format_gameplay_monitor_summary(monitors, state.get('gameplay', {}) or {})}",
            f"foreground={gameplay_monitor.get('foreground_window', '-') or '-'}",
            f"visibility_reason={gameplay_monitor.get('visibility_reason', '-') or '-'}",
            f"last_input={gameplay_monitor.get('last_input_command', '-') or '-'}",
            f"post_input_capture_ready={gameplay_monitor.get('post_input_capture_ready', False)}",
        ]
        state_export_lines = [
            f"summary={format_state_export_monitor_summary(monitors, state.get('state_export', {}) or {})}",
            f"path={state_export_monitor.get('path', '-') or '-'}",
            f"last_success_age={format_age_seconds(state_export_monitor.get('last_success_age_seconds'))}",
            f"file_age={format_age_seconds(state_export_monitor.get('file_age_seconds'))}",
            f"duration_ms={state_export_monitor.get('last_duration_ms', 0)} | size={state_export_monitor.get('last_size_bytes', 0)}",
            f"last_error={state_export_monitor.get('last_error', '') or '-'}",
            f"runtime_state_mismatches={state_consistency_monitor.get('mismatch_count', 0)}",
        ]
        for mismatch in (state_consistency_monitor.get("mismatches", []) or [])[:4]:
            state_export_lines.append(f"mismatch={mismatch}")
        queue_bridge_lines = [
            f"summary={format_queue_bridge_monitor_summary(monitors, state.get('queue_bridge', {}) or {})}",
            build_queue_next_action_cue(state),
            f"pending={queue_bridge_monitor.get('pending_count', 0)} | due={queue_bridge_monitor.get('due_pending_count', 0)} | stale_due={queue_bridge_monitor.get('stale_due_count', 0)}",
            f"queue_mode={planning.get('pending_queue_mode', command_drip.get('pending_queue_mode', 'normal'))} | {format_pending_queue_mode_semantics(planning.get('pending_queue_mode', command_drip.get('pending_queue_mode', 'normal')))}",
            f"oldest_pending={format_age_seconds(queue_bridge_monitor.get('oldest_pending_age_seconds'))} | oldest_due={format_age_seconds(queue_bridge_monitor.get('oldest_due_age_seconds'))}",
            f"latest_raw_inbox={queue_bridge_monitor.get('latest_raw_inbox_message_id', '-') or '-'} | age={format_age_seconds(queue_bridge_monitor.get('latest_raw_inbox_age_seconds'))}",
            f"latest_bridge={queue_bridge_monitor.get('latest_bridge_event', '-') or '-'}:{queue_bridge_monitor.get('latest_bridge_message_id', '-') or '-'} | caught={queue_bridge_monitor.get('bridge_caught_up', True)}",
            f"latest_result={queue_bridge_monitor.get('latest_external_command_result_status', '-') or '-'} | age={format_age_seconds(queue_bridge_monitor.get('latest_external_command_result_age_seconds'))} | caught={queue_bridge_monitor.get('command_result_caught_up', True)}",
        ]
        mutation_admission_lines = [
            f"schema={mutation_admission.get('schema_version', '-') or '-'}",
            f"summary={format_mutation_admission_summary(mutation_admission)}",
            f"admitted={mutation_admission.get('admitted_count', 0)} | rejected={mutation_admission.get('rejected_count', 0)}",
            f"path={mutation_admission.get('path', '-') or '-'}",
            "duplicate policy=known terminal result / uncertain no-replay / changed-payload conflict",
        ]
        blocks = [
            ("Runtime", [state.get("runtime_summary", ""), build_state_freshness_text(state), state.get("auth_summary", "")]),
            ("Window 18 Health", runtime_health_lines),
            ("Operator Risk Summary", operator_risk_lines),
            ("Monitors", monitor_lines),
            ("State Export Monitor", state_export_lines),
            ("Queue / Bridge Monitor", queue_bridge_lines),
            ("Mutation Admission", mutation_admission_lines),
            ("Gameplay Monitor", gameplay_monitor_lines),
            (
                "Security",
                [
                    f"passcode_required={((state.get('security', {}) or {}).get('passcode_required', False))}",
                    f"has_passcode={((state.get('security', {}) or {}).get('has_passcode', False))}",
                    f"show_passcode_commands={((state.get('security', {}) or {}).get('show_passcode_commands', False))}",
                    f"authorized={((state.get('security', {}) or {}).get('authorized', True))}",
                    f"authorized_seconds_remaining={((state.get('security', {}) or {}).get('authorized_seconds_remaining', 0))}",
                ],
            ),
            (
                "Settings Safety",
                [
                    self.build_settings_safety_summary(state),
                    "classification=basic / advanced / risky / recovery-critical / hidden-by-default candidate",
                    "details=see Recovery tab",
                ],
            ),
            ("Model Status", self.build_model_status_text(state.get("model_status", {})).splitlines()),
            ("Cadence / Wake", self.build_cadence_status_lines(state=state)),
            (
                "Live Harness",
                [
                    f"status={live_harness.get('status', 'not exported')} | mode={live_harness.get('mode', '-') or '-'}",
                    f"offline_ready={harness_readiness.get('ready_for_offline_rehearsal', False)} | live_ready={harness_readiness.get('ready_for_live', False)}",
                    f"rehearsal={harness_rehearsal.get('status', 'not run') or 'not run'} | passed={harness_rehearsal.get('passed', False)}",
                    f"probe={harness_probe.get('status', 'not armed') or 'not armed'} | model={harness_probe.get('model', '-') or '-'}",
                    f"live_mode={harness_posture.get('live_mode', False)} | action_mode={harness_posture.get('action_mode', '-') or '-'}",
                    f"newest_image={short(harness_contract.get('newest_image_path', '') or '-', 140)}",
                    f"prior_cap={harness_contract.get('prior_image_cap', '-')} | in_prompt={harness_contract.get('in_prompt_visual_count', '-')} | retained={harness_contract.get('retained_visual_count', '-')}",
                    f"warnings={len(harness_warnings)}",
                    "details=see Live Harness, Visual Context, and Prompt Ledger tabs",
                ],
            ),
            (
                "Responses Shadow",
                [
                    f"status={responses_shadow.get('status', 'not exported')} | mode={responses_shadow.get('mode', '-') or '-'}",
                    f"current_transport={responses_summary.get('current_transport', '-') or '-'} | shadow_transport={responses_summary.get('shadow_transport', '-') or '-'}",
                    f"default_migration_enabled={responses_summary.get('default_migration_enabled', False)} | api_call_enabled={responses_summary.get('responses_api_call_enabled', False)}",
                    f"shadow_request_builder_enabled={responses_summary.get('shadow_request_builder_enabled', False)} | offline_parity_ready={responses_summary.get('offline_payload_parity_ready', False)}",
                    f"closure={responses_summary.get('closure_readiness_status', responses_closure.get('status', '-')) or '-'} | ready={responses_summary.get('closure_ready_for_window_close', responses_closure.get('ready_for_window_close', False))}",
                    f"closure_counts ok={closure_counts.get('ok', responses_summary.get('closure_ok_count', 0))} | watch={closure_counts.get('watch', responses_summary.get('closure_watch_count', 0))} | blocked={closure_counts.get('blocked', responses_summary.get('closure_blocked_count', 0))}",
                    f"live_probe={responses_summary.get('shadow_live_probe_status', '-') or '-'} | model={responses_summary.get('shadow_live_probe_model', '-') or '-'} | tier={responses_summary.get('shadow_live_probe_tier', '-') or '-'}",
                    f"live_probe_send_enabled={responses_summary.get('shadow_live_probe_send_enabled', False)} | live_probe_api_call_enabled={responses_summary.get('shadow_live_probe_api_call_enabled', False)} | estimated_probe_cost={responses_summary.get('shadow_live_probe_estimated_total_usd', '-')}",
                    f"payload_preview={responses_summary.get('shadow_payload_preview_id', '-') or '-'} | schema={responses_summary.get('shadow_payload_schema', '-') or '-'}",
                    f"payload_inputs={responses_summary.get('shadow_payload_input_messages', 0)} | payload_rows={responses_summary.get('shadow_payload_ledger_rows_used', 0)} | visual_placeholders={responses_summary.get('shadow_payload_visual_placeholders', 0)}",
                    f"offline_posture={responses_summary.get('shadow_offline_posture_id', '-') or '-'} | schema={responses_summary.get('shadow_offline_posture_schema', '-') or '-'}",
                    f"estimated_input_tokens={responses_summary.get('shadow_estimated_input_tokens', 0)} | estimated_total_usd={responses_summary.get('shadow_estimated_total_usd', '-')} | state_risk={responses_summary.get('shadow_state_risk', '-') or '-'}",
                    f"stateful_profile={responses_summary.get('stateful_active_profile', '-') or '-'} | previous_response_id_active={responses_summary.get('previous_response_id_active', False)} | conversation_id_active={responses_summary.get('conversation_id_active', False)}",
                    f"contract_rows={responses_summary.get('comparison_contract_rows', 0)} | readiness_rows={responses_summary.get('readiness_rows', 0)} | blockers={responses_summary.get('blocker_rows', 0)}",
                    f"prompt_included={responses_summary.get('prompt_included_rows', 0)} | prompt_omitted={responses_summary.get('prompt_omitted_rows', 0)} | in_prompt_visual={responses_summary.get('in_prompt_visual_count', 0)}",
                    "details=see Responses Shadow tab and SHOW_RESPONSES_SHADOW_TRANSPORT()",
                ],
            ),
            (
                "Visual Context",
                [
                    "lanes=" + (", ".join(visual_lane_bits) if visual_lane_bits else "-"),
                    f"prior_image_limit={visual_summary.get('prompt_prior_image_limit', '-')}",
                    f"current_image_attached={visual_summary.get('current_image_attached', False)}",
                    f"local_screenshot_files={visual_summary.get('local_screenshot_count', 0)}",
                    "details=see Visual Context, Screenshots, and Images In Memory tabs",
                ],
            ),
            (
                "Image Cost Posture",
                [
                    f"status={image_cost_posture.get('status', 'not exported')} | schema={image_cost_posture.get('schema_version', '-') or '-'}",
                    f"summary={image_cost_posture.get('summary', '-') or '-'}",
                    f"local_screenshots={image_cost_counts.get('local_screenshot_count', 0)} | sidecars={image_cost_counts.get('sidecar_count', 0)} | coverage={image_cost_counts.get('sidecar_coverage_percent', 0)}%",
                    f"backfill_default={image_cost_limits.get('image_context_backfill_default_limit', '-')} | backfill_max={image_cost_limits.get('image_context_backfill_max_limit', '-')} | search_max_scan={image_cost_limits.get('image_context_search_max_scan', '-')}",
                    f"visual_cache_ttl={image_cost_limits.get('visual_context_local_scan_ttl_seconds', '-')}s | panel_list_cache_ttl={image_cost_limits.get('control_panel_screenshot_list_cache_ttl_seconds', '-')}s",
                    f"next={short(str(image_cost_actions[0]), 180) if image_cost_actions else '-'}",
                    "details=see Image Index tab and SHOW_IMAGE_COST_POSTURE()",
                ],
            ),
            (
                "Prompt Ledger",
                [
                    f"mode={prompt_ledger_summary.get('mode', 'eligible_now_estimate')}",
                    f"messages={prompt_ledger_summary.get('message_count', 0)} | model={prompt_ledger_summary.get('model', '-') or '-'}",
                    f"included_rows={prompt_ledger_summary.get('included_rows', 0)} | prompt_pin_rows={prompt_ledger_summary.get('prompt_pin_rows', 0)} | do_not_include_rows={prompt_ledger_summary.get('do_not_include_rows', 0)} | retained_rows={prompt_ledger_summary.get('retained_rows', 0)} | omitted_rows={prompt_ledger_summary.get('omitted_rows', 0)}",
                    f"approved_prompt_pin_marks={prompt_ledger_summary.get('approved_prompt_pin_marks', 0)} | prompt_pins_active={prompt_ledger_summary.get('prompt_pins_active', 0)} | pin_model_visible_next={prompt_ledger_summary.get('prompt_pin_model_visible_next_turn', 0)}",
                    f"recent_text={prompt_ledger_summary.get('recent_text_messages', 0)} | recent_images={prompt_ledger_summary.get('recent_image_messages', 0)}",
                    f"important_text={prompt_ledger_summary.get('important_text_entries', 0)} | file_shelf_model_visible={prompt_ledger_summary.get('context_files_visible_to_model_now', 0)}",
                    "details=see Prompt Ledger tab",
                ],
            ),
            ("Prompt Inclusion Readiness", prompt_inclusion_lines),
            (
                "Context Marks",
                [
                    f"mode={context_marks_summary.get('mode', 'metadata_policy_scaffold')}",
                    f"writable={context_marks_summary.get('writable_marks_enabled', False)} | model_visible_mutation={context_marks_summary.get('model_visible_mutation_enabled', False)}",
                    f"mark_types={context_marks_summary.get('mark_types', 0)} | control_groups={context_marks_summary.get('active_control_groups', 0)}",
                    f"active_marks={context_marks_summary.get('dedicated_mark_store_entries', 0)} | prompt_pin_marks={context_marks_summary.get('prompt_pin_marks', 0)} | do_not_include_marks={context_marks_summary.get('do_not_include_marks', 0)} | prompt_pins_active={context_marks_summary.get('prompt_pins_active', 0)}",
                    f"approved_do_not_include={context_marks_summary.get('approved_do_not_include_marks', 0)} | enforcement={context_marks_summary.get('do_not_include_enforcement_enabled', False)}",
                    f"operator_pins_partial={context_marks_summary.get('operator_pins_partial', 0)} | model_visible_marks={context_marks_summary.get('model_visible_marks', 0)}",
                    "details=see Prompt Ledger tab and SHOW_CONTEXT_MARKS()",
                ],
            ),
            (
                "History Context",
                [
                    f"mode={history_context_summary.get('mode', 'not_exported')}",
                    f"service_extracted={history_context_summary.get('service_extracted', False)} | service_facade={history_context_summary.get('service_facade_enabled', False)} | schema={history_context_summary.get('service_facade_schema', '-') or '-'}",
                    f"read_helpers={history_context_summary.get('centralized_read_helpers_enabled', False)} | facade_read_methods={history_context_summary.get('service_facade_read_methods', 0)} | companion_contract={history_context_summary.get('companion_contract_status', '-')}",
                    f"store_summary={history_context_summary.get('centralized_store_summary_enabled', False)} | policy_snapshot={history_context_summary.get('centralized_policy_snapshot_enabled', False)} | enabled_write_paths={history_context_summary.get('enabled_effective_write_paths', 0)}",
                    f"chat_entries={history_context_summary.get('chat_history_entries', 0)} | prompt_included={history_context_summary.get('prompt_included_rows', 0)} | prompt_omitted={history_context_summary.get('prompt_omitted_rows', 0)}",
                    f"stores={history_context_summary.get('store_rows', 0)} | boundaries={history_context_summary.get('boundary_rows', 0)} | cleanup_candidates={history_context_summary.get('cleanup_candidates', 0)}",
                    f"direct_store_write_allowed={history_context_summary.get('companion_direct_store_write_allowed', False)} | effective_write_paths_disabled={history_context_summary.get('all_effective_write_paths_disabled', False)}",
                    "details=see History Context tab and SHOW_HISTORY_CONTEXT_SERVICE()",
                ],
            ),
            (
                "Companion Contracts",
                [
                    f"schema={companion_readiness.get('schema_version', '-') or '-'} | status={companion_readiness.get('status', 'not_exported')} | integration_enabled={companion_readiness.get('integration_enabled', False)}",
                    f"contract_review={companion_readiness.get('ready_for_contract_review', False)} | live_integration={companion_readiness.get('ready_for_live_companion_integration', False)}",
                    f"apps={companion_readiness_counts.get('companion_apps', 0)} | local_paths={companion_readiness_counts.get('local_companion_paths_existing', 0)} | read_contract={companion_readiness_counts.get('read_contract_rows', 0)} | write_contract={companion_readiness_counts.get('write_contract_rows', 0)}",
                    f"ok={companion_readiness_status_counts.get('ok', 0)} | watch={companion_readiness_status_counts.get('watch', 0)} | warning={companion_readiness_status_counts.get('warning', 0)} | blocked={companion_readiness_status_counts.get('blocked', 0)}",
                    f"direct_store_write={bool(companion_readiness_counts.get('direct_store_write_allowed', 0))} | parent_history_write={bool(companion_readiness_counts.get('parent_history_write_allowed', 0))} | model_visible_mutation={bool(companion_readiness_counts.get('model_visible_mutation_allowed', 0))}",
                    f"protocol_schema={companion_protocol.get('schema_version', '-') or '-'} | protocol_status={companion_protocol.get('status', 'not_exported')} | request_ingest={companion_protocol.get('request_ingest_enabled', False)} | receipt_writer={companion_protocol.get('receipt_writer_enabled', False)}",
                    f"request_fields={companion_protocol_counts.get('request_fields', 0)} | receipt_fields={companion_protocol_counts.get('receipt_fields', 0)} | routes={companion_protocol_counts.get('route_rows', 0)} | blocked_intents={companion_protocol_counts.get('blocked_intents', 0)}",
                    f"route_watch={companion_protocol_route_counts.get('watch', 0)} | gate_ok={companion_protocol_gate_counts.get('ok', 0)} | direct_store_write={companion_protocol.get('direct_store_write_allowed', False)} | parent_history_write={companion_protocol.get('parent_history_write_allowed', False)}",
                    f"receipt_schema={companion_receipt.get('schema_version', '-') or '-'} | receipt_status={companion_receipt.get('status', 'not_exported')} | receipt_writer={companion_receipt.get('receipt_writer_enabled', False)} | receipt_store_exists={companion_receipt_store.get('exists', False)}",
                    f"receipt_lifecycle={companion_receipt_counts.get('lifecycle_rows', 0)} | route_receipts={companion_receipt_counts.get('route_receipts', 0)} | blocked_receipts={companion_receipt_counts.get('blocked_receipts', 0)} | evidence_sources={companion_receipt_counts.get('evidence_sources', 0)}",
                    f"closure_schema={companion_closure.get('schema_version', '-') or '-'} | closure_status={companion_closure.get('status', 'not_exported')} | ready={companion_closure.get('ready_for_window_close', False)}",
                    f"closure_checks={companion_closure_counts.get('checks', 0)} | ok={companion_closure_status_counts.get('ok', 0)} | watch={companion_closure_status_counts.get('watch', 0)} | warning={companion_closure_status_counts.get('warning', 0)} | blocked={companion_closure_status_counts.get('blocked', 0)}",
                    f"closure_flags request_ingest={companion_closure_counts.get('request_ingest_enabled', False)} | receipt_writer={companion_closure_counts.get('receipt_writer_enabled', False)} | integration={companion_closure_counts.get('integration_enabled', False)} | live={companion_closure_counts.get('live_companion_integration_enabled', False)}",
                    "details=see History Context tab, SHOW_COMPANION_CONTRACT_READINESS(), SHOW_COMPANION_PROTOCOL_CONTRACT(), SHOW_COMPANION_RECEIPT_AUDIT(), and SHOW_COMPANION_CONTRACT_CLOSURE()",
                ],
            ),
            (
                "Portal Intake",
                [
                    f"schema={portal_intake.get('schema_version', '-') or '-'} | status={portal_intake.get('status', 'not_exported')} | mode={portal_intake.get('mode', '-') or '-'}",
                    f"branch={portal_intake.get('portal_branch', '-') or '-'} | head={short(portal_intake.get('portal_head_commit', '-') or '-', 16)} | pr={portal_intake.get('portal_pr_url', '-') or '-'}",
                    f"mirror_exists={portal_intake.get('handoff_mirror_exists', False)} | mirror_path={portal_intake.get('handoff_mirror_path', '-') or '-'}",
                    f"routes={portal_intake_counts.get('routes', 0)} | heavy_routes={portal_intake_counts.get('heavy_routes', 0)} | cli={portal_intake_counts.get('cli_commands', 0)} | allowed={portal_intake_counts.get('allowed_intents', 0)} | blocked={portal_intake_counts.get('blocked_intents', 0)}",
                    f"copy_packets={portal_intake_counts.get('operator_copy_packets', 0)} | draft_templates={portal_intake_counts.get('receipt_draft_templates', 0)} | questions={portal_intake_counts.get('open_questions', 0)}",
                    f"review_packets={portal_intake_counts.get('readiness_review_packets', 0)} | review_stop_lines={portal_intake_counts.get('review_stop_lines', 0)} | review_questions={portal_intake_counts.get('review_next_questions', 0)} | review_ready={portal_intake.get('ready_for_readiness_review', False)}",
                    f"registry_rows={portal_intake_counts.get('envelope_registry_rows', 0)} | registry_stop_lines={portal_intake_counts.get('registry_contract_stop_lines', 0)} | registry_contract_ready={portal_intake.get('ready_for_registry_contract_review', False)} | live_registry_read={portal_intake.get('ready_for_live_registry_read', False)}",
                    f"audit_rows={portal_intake_counts.get('acceptance_audit_rows', 0)} | audit_proved={portal_intake_counts.get('acceptance_proved', 0)} | audit_waiting={portal_intake_counts.get('acceptance_waiting', 0)} | audit_missing={portal_intake_counts.get('acceptance_missing', 0)} | audit_blocked={portal_intake_counts.get('acceptance_blocked', 0)}",
                    f"acceptance_audit={portal_intake.get('ready_for_acceptance_audit', False)} | local_acceptance={portal_intake.get('ready_for_local_acceptance', False)} | external_acceptance={portal_intake.get('ready_for_external_acceptance', False)}",
                    f"docket_rows={portal_intake_counts.get('promotion_evidence_rows', 0)} | docket_proved={portal_intake_counts.get('promotion_proved', 0)} | docket_waiting={portal_intake_counts.get('promotion_waiting', 0)} | docket_missing={portal_intake_counts.get('promotion_missing', 0)} | docket_blocked={portal_intake_counts.get('promotion_blocked', 0)}",
                    f"promotion_review={portal_intake.get('ready_for_promotion_evidence_review', False)} | stage_promotion={portal_intake.get('ready_for_stage_promotion', False)}",
                    f"handoff_packets={portal_intake_counts.get('external_handoff_packets', 0)} | handoff_ready={portal_intake_counts.get('handoff_ready_to_copy', 0)} | handoff_waiting={portal_intake_counts.get('handoff_waiting', 0)} | handoff_blocked={portal_intake_counts.get('handoff_blocked', 0)}",
                    f"handoff_review={portal_intake.get('ready_for_external_handoff_review', False)} | handoff_submit={portal_intake.get('external_handoff_submit_enabled', False)}",
                    f"proof_rows={portal_intake_counts.get('local_proof_rows', 0)} | proof_validated={portal_intake_counts.get('local_proof_validated', 0)} | proof_ready={portal_intake_counts.get('local_proof_ready_for_validation', 0)} | proof_watch={portal_intake_counts.get('local_proof_watch', 0)} | proof_blocked={portal_intake_counts.get('local_proof_blocked', 0)}",
                    f"proof_review={portal_intake.get('ready_for_local_proof_review', False)} | current_validation_recorded={portal_intake.get('current_slice_validation_recorded', False)}",
                    f"operator_report_packets={portal_intake_counts.get('operator_report_packets', 0)} | report_ready={portal_intake_counts.get('operator_report_ready_to_copy', 0)} | report_waiting={portal_intake_counts.get('operator_report_waiting', 0)} | report_blocked={portal_intake_counts.get('operator_report_blocked', 0)}",
                    f"operator_report_review={portal_intake.get('ready_for_operator_report_review', False)}",
                    f"gate_unblockers={portal_intake_counts.get('gate_unblocker_rows', 0)} | unblocker_proved={portal_intake_counts.get('unblocker_proved', 0)} | unblocker_waiting={portal_intake_counts.get('unblocker_waiting', 0)} | unblocker_blocked={portal_intake_counts.get('unblocker_blocked', 0)}",
                    f"unblocker_review={portal_intake.get('ready_for_unblocker_review', False)}",
                    f"upstream_waitlist_packets={portal_intake_counts.get('upstream_waitlist_packets', 0)} | waitlist_ready={portal_intake_counts.get('waitlist_ready_to_copy', 0)} | waitlist_waiting={portal_intake_counts.get('waitlist_waiting', 0)} | waitlist_blocked={portal_intake_counts.get('waitlist_blocked', 0)}",
                    f"upstream_waitlist_review={portal_intake.get('ready_for_upstream_waitlist_review', False)}",
                    f"parking_packets={portal_intake_counts.get('parking_resume_packets', 0)} | parking_ready={portal_intake_counts.get('parking_ready_to_copy', 0)} | parking_waiting={portal_intake_counts.get('parking_waiting', 0)} | parking_blocked={portal_intake_counts.get('parking_blocked', 0)}",
                    f"parking_review={portal_intake.get('ready_for_parking_review', False)}",
                    f"closure_checks={portal_intake_counts.get('intake_closure_checks', 0)} | closure_proved={portal_intake_counts.get('closure_proved', 0)} | closure_waiting={portal_intake_counts.get('closure_waiting', 0)} | closure_blocked={portal_intake_counts.get('closure_blocked', 0)}",
                    f"closure_review={portal_intake.get('ready_for_parked_closure_review', False)} | parked={portal_intake.get('local_implementation_parked', False)}",
                    f"ok={portal_intake_status_counts.get('ok', 0)} | watch={portal_intake_status_counts.get('watch', 0)} | warning={portal_intake_status_counts.get('warning', 0)} | blocked={portal_intake_status_counts.get('blocked', 0)}",
                    f"stage_gates={portal_intake_counts.get('stage_gates', 0)} | gates_ok={portal_intake_gate_counts.get('ok', 0)} | gates_watch={portal_intake_gate_counts.get('watch', 0)} | gates_blocked={portal_intake_gate_counts.get('blocked', 0)}",
                    f"local_viewer={portal_intake.get('ready_for_local_viewer', False)} | live_reads={portal_intake.get('ready_for_live_portal_reads', False)} | cross_client_proof={portal_intake.get('ready_for_cross_client_proof', False)} | receipt_submission={portal_intake.get('ready_for_receipt_submission', False)} | mutation_gates={portal_intake.get('ready_for_mutation_gates', False)}",
                    f"http_calls={portal_intake_counts.get('portal_http_calls_enabled', False)} | cli_calls={portal_intake_counts.get('portal_cli_calls_enabled', False)} | polling={portal_intake_counts.get('polling_enabled', False)} | receipt_writer={portal_intake_counts.get('receipt_writer_enabled', False)} | submit_receipts={portal_intake_counts.get('submit_receipts_enabled', False)}",
                    f"desktop_automation={portal_intake_counts.get('desktop_automation_enabled', False)} | browser_automation={portal_intake_counts.get('browser_automation_enabled', False)} | source_file_reads={portal_intake_counts.get('source_file_reads_enabled', False)} | model_visible_writes={portal_intake_counts.get('model_visible_writes_enabled', False)}",
                    f"performance={portal_intake.get('performance_note', '-') or '-'}",
                    f"first_question={short(str(portal_intake_questions[0]), 180) if portal_intake_questions else '-'}",
                    f"next={short(str(portal_intake_actions[0]), 180) if portal_intake_actions else '-'}",
                    "details=SHOW_PORTAL_COMPANION_INTAKE(); SHOW_PORTAL_INTAKE_GATES(); SHOW_PORTAL_INTAKE_REVIEW(); SHOW_PORTAL_INTAKE_REGISTRY(); SHOW_PORTAL_INTAKE_AUDIT(); SHOW_PORTAL_INTAKE_DOCKET(); SHOW_PORTAL_INTAKE_HANDOFFS(); SHOW_PORTAL_INTAKE_PROOF(); SHOW_PORTAL_INTAKE_REPORT(); SHOW_PORTAL_INTAKE_UNBLOCKERS(); SHOW_PORTAL_INTAKE_WAITLIST(); SHOW_PORTAL_INTAKE_PARKING(); SHOW_PORTAL_INTAKE_CLOSURE(); no Portal calls or receipt writes",
                ],
            ),
            (
                "Agent Registry",
                [
                    f"mode={agent_registry_summary.get('mode', 'metadata_only_registry')}",
                    f"sub_agents={agent_registry_summary.get('sub_agent_count', 0)} | active={agent_registry_summary.get('active_sub_agents', 0)} | silenced={agent_registry_summary.get('silenced_sub_agents', 0)}",
                    f"workers_enabled={agent_registry_summary.get('worker_processes_enabled', False)} | model_spawn={agent_registry_summary.get('model_worker_spawn_enabled', False)} | suggestion_execution={agent_registry_summary.get('suggestion_execution_enabled', False)}",
                    f"requested_model_visible_scopes={agent_registry_summary.get('requested_model_visible_next_turn_scopes', 0)} | effective_model_visible_next_turn={agent_registry_summary.get('effective_model_visible_next_turn', 0)}",
                    f"history_acl_rows={agent_registry_summary.get('history_acl_preview_rows', 0)} | private_history_paths={agent_registry_summary.get('private_history_path_rows', 0)} | private_history_files={agent_registry_summary.get('private_history_files_existing', 0)}",
                    f"private_history_private={agent_registry_summary.get('private_history_private_events', 0)} | parent_visible={agent_registry_summary.get('private_history_parent_visible_events', 0)} | operator_append={agent_registry_summary.get('operator_private_history_append_enabled', False)}",
                    f"parent_history_writes_effective={agent_registry_summary.get('effective_parent_history_writes', 0)} | sub_agent_parent_reads_effective={agent_registry_summary.get('effective_sub_agent_parent_reads', 0)}",
                    f"suggestion_routes={agent_registry_summary.get('suggestion_route_rows', 0)} | policy_tagged={agent_registry_summary.get('suggestion_policy_tagged_rows', 0)} | audit_rows={agent_suggestions_summary.get('suggestion_count', 0)} | blocked={agent_suggestions_summary.get('policy_blocked_suggestions', 0)}",
                    f"approved={agent_suggestions_summary.get('approved_suggestions', 0)} | rejected={agent_suggestions_summary.get('rejected_suggestions', 0)} | staged={agent_suggestions_summary.get('staged_pending_candidates', 0)} | candidate_staging={agent_suggestions_summary.get('pending_command_candidate_staging_enabled', False)}",
                    f"context_mark_linked={agent_suggestions_summary.get('context_mark_linked_suggestions', 0)} | provenance_links={agent_suggestions_summary.get('context_mark_links', 0)} | provenance_marking={agent_suggestions_summary.get('provenance_marking_enabled', False)}",
                    f"pending_candidates={agent_suggestions_summary.get('pending_command_candidates', 0)} | pending_insertions={agent_suggestions_summary.get('pending_command_insertions', 0)} | insert_enabled={agent_suggestions_summary.get('pending_command_insertion_enabled', False)} | execute={agent_suggestions_summary.get('command_execution_enabled', False)}",
                    f"task_packets={agent_tasks_summary.get('task_count', 0)} | active_tasks={agent_tasks_summary.get('active_tasks', 0)} | review_tasks={agent_tasks_summary.get('review_tasks', 0)} | prompt_ledger_visible_tasks={agent_tasks_summary.get('prompt_ledger_visible_tasks', 0)}",
                    f"task_insertions={agent_tasks_summary.get('pending_command_insertions', 0)} | task_insert_enabled={agent_tasks_summary.get('pending_command_insertion_enabled', False)} | task_execute={agent_tasks_summary.get('command_execution_enabled', False)} | task_model_visible={agent_tasks_summary.get('model_visible_tasks', 0)}",
                    f"review_links={agent_pending_gate_summary.get('review_links', 0)} | gate_ready={agent_pending_gate_summary.get('metadata_ready_rows', 0)} | gate_open={agent_pending_gate_summary.get('pending_gate_open_rows', 0)} | gate_insert_enabled={agent_pending_gate_summary.get('pending_command_insertion_enabled', False)} | gate_execute={agent_pending_gate_summary.get('command_execution_enabled', False)}",
                    f"insert_dry_run_rows={agent_pending_insert_dry_run_summary.get('rows', 0)} | contract_ready={agent_pending_insert_dry_run_summary.get('contract_ready_rows', 0)} | passed={agent_pending_insert_dry_run_summary.get('dry_run_passed_rows', 0)} | would_insert={agent_pending_insert_dry_run_summary.get('would_insert_rows', 0)} | inserted={agent_pending_insert_dry_run_summary.get('pending_command_insertions', 0)} | dry_run_insert_enabled={agent_pending_insert_dry_run_summary.get('pending_command_insertion_enabled', False)}",
                    f"closure={agent_helper_closure.get('status', 'not_exported')} | ready={agent_helper_closure.get('ready_for_window_close', False)} | ok={agent_helper_closure_status_counts.get('ok', 0)} | watch={agent_helper_closure_status_counts.get('watch', 0)} | warning={agent_helper_closure_status_counts.get('warning', 0)} | blocked={agent_helper_closure_status_counts.get('blocked', 0)}",
                    f"closure_pending_total={agent_helper_closure_counts.get('pending_queue_total', 0)} | sub_agent_current={agent_helper_closure_counts.get('sub_agent_pending_current', 0)} | manual_required={agent_helper_closure_counts.get('manual_approval_current', 0)} | execute_enabled={agent_helper_closure_counts.get('command_execution_enabled', False)} | model_visible_enabled={agent_helper_closure_counts.get('model_visible_enabled', False)}",
                    "details=see Agents tab, Insert Ready, Run Closure, SHOW_AGENTS(), SHOW_AGENT_HISTORY_ACLS(), SHOW_AGENT_SUGGESTION_ROUTES(), SHOW_AGENT_SUGGESTIONS(), SHOW_AGENT_TASKS(), SHOW_AGENT_PENDING_GATE(), SHOW_AGENT_PENDING_INSERT_CHECKLIST(), and SHOW_AGENT_HELPER_CLOSURE()",
                ],
            ),
            (
                "Context Files",
                [
                    f"mode={context_file_summary.get('mode', 'read_only_inventory')}",
                    f"files={context_file_summary.get('existing', 0)}/{context_file_summary.get('total', 0)}",
                    f"pinned={context_file_summary.get('pinned', 0)}",
                    f"visible_to_model_now={context_file_summary.get('visible_to_model_now', 0)}",
                    f"refresh_on_wake={context_file_summary.get('refresh_on_wake', 0)}",
                    "details=see Context Files tab",
                ],
            ),
            ("Overlay", [
                f"Tile Grid: {'on' if (state.get('overlay', {}) or {}).get('tile_grid', False) else 'off'}",
                f"Cursor Label: {'on' if (state.get('overlay', {}) or {}).get('cursor_label', True) else 'off'}",
                f"Keypoint Grid: {'on' if (state.get('overlay', {}) or {}).get('keypoint_grid', True) else 'off'}",
                f"Status Text: {'on' if (state.get('overlay', {}) or {}).get('status_text', True) else 'off'}",
            ]),
            ("Goals", state.get("goals", [])),
            ("Overarching", state.get("overarching_goals", [])),
            ("Immediate", state.get("pinned_immediate_actions", [])),
            ("Short Term", state.get("pinned_short_term_actions", [])),
            ("Mid Term", state.get("mid_term_context", [])),
            ("Long Term", state.get("long_term_context", [])),
            (
                "Scene / Planning",
                [
                    f"gameplay_scene={planning.get('gameplay_scene', 'unknown')}",
                    f"scene_summary={planning.get('gameplay_scene_summary', '')}",
                    f"next_inference_source={planning.get('next_inference_source', 'default')}",
                    f"turn_scheduler_profile={scheduler.get('profile', 'balanced')}",
                    f"turn_scheduler_mode={scheduler.get('mode', 'hybrid')}",
                    f"turn_scheduler_last_wake={scheduler.get('last_wake_reason', '-') or '-'}",
                    f"active_questions={len(state.get('active_questions', []) or [])}",
                    f"known_failures={len(state.get('known_failures', []) or [])}",
                    f"candidate_alternatives={len(state.get('candidate_alternatives', []) or [])}",
                ],
            ),
            (
                "Memory Tiers",
                [
                    "On-Hand: " + ", ".join(entry.get("store", "") for entry in (memory_tiers.get("on_hand", []) or [])),
                    "Retrievable: " + ", ".join(entry.get("store", "") for entry in (memory_tiers.get("retrievable", []) or [])),
                ],
            ),
            (
                "Episodic Memory",
                [
                    f"enabled={episodic.get('enabled', True)}",
                    f"snapshot_count={episodic.get('snapshot_count', 0)}",
                    f"interval_seconds={episodic.get('interval_seconds', 900)}",
                    f"last_snapshot={episodic.get('last_snapshot_timestamp', '-')}",
                    f"last_reason={episodic.get('last_snapshot_reason', '-')}",
                    f"last_search_query={episodic.get('last_search_query', '-')}",
                    f"last_retrieval_summary={episodic.get('last_retrieval_summary', '-')}",
                ],
            ),
            (
                "Rehydration",
                [
                    f"automatic_status={rehydration.get('automatic_status', '-')}",
                    f"last_outcome={rehydration_explain.get('last_outcome', '-')}",
                    f"last_decision={rehydration_explain.get('last_decision', episodic.get('planning_last_decision', '-'))} @ turn {rehydration_explain.get('last_decision_turn', episodic.get('planning_last_decision_turn', 0))}",
                    f"query_sources={format_source_mix(rehydration_explain.get('last_query_source_mix', episodic.get('planning_last_query_source_mix', [])), limit=16, item_limit=36)}",
                    f"query_preview={rehydration_explain.get('last_query_preview', episodic.get('planning_last_query', '-'))}",
                    f"operator_hint={rehydration_explain.get('operator_hint', '-')}",
                    (
                        "source_counts="
                        f"route:{rehydration_counts.get('route_state_entries', 0)}, "
                        f"notes:{rehydration_counts.get('notes', 0)}, "
                        f"recent:{rehydration_counts.get('recent_context', 0)}, "
                        f"blockers:{rehydration_counts.get('route_blockers', 0)}, "
                        f"goals:{rehydration_counts.get('goals', 0)}"
                    ),
                ],
            ),
            ("Recent Context", state.get("recent_context_events", [])),
            ("Active Questions", state.get("active_questions", [])),
            ("Known Failures", state.get("known_failures", [])),
            ("Candidate Alternatives", state.get("candidate_alternatives", [])),
            (
                "Route",
                [
                    f"Current Area: {route.get('current_area', '')}",
                    f"Target Area: {route.get('target_area', '')}",
                    f"Travel Heading: {route.get('travel_heading', '')}",
                    f"Last Landmark: {route.get('last_landmark', '')}",
                    f"Status: {route.get('status', '')}",
                    f"Stale Reasons: {', '.join(route.get('stale_reasons', []) or [])}",
                ] + list(route.get("route_intent", [])) + list(route.get("local_path_plan", [])) + list(route.get("route_blockers", [])),
            ),
            ("Recent Executed", state.get("recent_executed_actions", [])),
            (
                "Command Drip",
                [
                    f"queue_mode={command_drip.get('pending_queue_mode', 'normal')}",
                    build_queue_next_action_cue(state),
                    "semantics=pending planning lane; lookahead candidates are not approvals",
                    f"retention_turns={command_drip.get('retention_turns', 0)}",
                    f"lookahead_turns={command_drip.get('lookahead_turns', 0)}",
                    self._format_command_drip_summary(command_drip),
                    f"show_variants={command_drip.get('show_variants', True)}",
                    f"show_likely_dropped={command_drip.get('show_likely_dropped', True)}",
                ] + [
                    self._summarize_command_drip_bucket(bucket)
                    for bucket in (command_drip.get("turns", []) or [])[:6]
                ],
            ),
            ("Chat State Tail", [f"{row.get('role', '')}: {row.get('text', '')}" for row in state.get("chat_history_tail", [])]),
        ]
        parts = []
        for title, lines in blocks:
            clean_lines = [short(line, 280) for line in (lines or []) if str(line).strip()]
            parts.append(f"[{title}]")
            parts.extend(clean_lines or ["-"])
            parts.append("")
        return "\n".join(parts).strip()

    @staticmethod
    def _command_drip_lane_totals(snapshot):
        totals = {
            "turns": 0,
            "selected": 0,
            "executed": 0,
            "failed": 0,
            "rejected": 0,
            "dropped": 0,
            "deferred": 0,
            "primary_candidates": 0,
            "variant_candidates": 0,
            "likely_dropped": 0,
            "notes": 0,
        }
        for bucket in (snapshot or {}).get("turns", []) or []:
            totals["turns"] += 1
            for lane in (
                "selected",
                "executed",
                "failed",
                "rejected",
                "dropped",
                "deferred",
                "primary_candidates",
                "variant_candidates",
                "likely_dropped",
            ):
                totals[lane] += len(bucket.get(lane, []) or [])
            totals["notes"] += len(bucket.get("notes", []) or [])
        return totals

    @classmethod
    def _format_command_drip_summary(cls, snapshot):
        totals = cls._command_drip_lane_totals(snapshot)
        candidate_count = totals["primary_candidates"] + totals["variant_candidates"]
        issue_count = totals["failed"] + totals["rejected"] + totals["dropped"] + totals["likely_dropped"]
        return (
            f"Lane totals selected {totals['selected']}, executed {totals['executed']}, "
            f"candidates {candidate_count}, deferred {totals['deferred']}, issues {issue_count}, notes {totals['notes']}"
        )

    @staticmethod
    def _summarize_command_drip_bucket(bucket):
        label = bucket.get("label") or f"turn {bucket.get('turn', '?')}"
        counts = []
        for lane in ("selected", "executed", "failed", "rejected", "dropped", "deferred", "primary_candidates", "variant_candidates", "likely_dropped"):
            lane_items = bucket.get(lane, []) or []
            if lane_items:
                counts.append(f"{lane}={len(lane_items)}")
        return f"{label}: " + (", ".join(counts) if counts else "empty")

    def build_command_drip_text(self, snapshot):
        if not snapshot:
            return "No command-drip snapshot available."
        lines = [
            "[Command Drip]",
            f"current_turn={snapshot.get('current_turn', 0)} | retention_turns={snapshot.get('retention_turns', 0)} | "
            f"lookahead_turns={snapshot.get('lookahead_turns', 0)} | queue_mode={snapshot.get('pending_queue_mode', 'normal')} | "
            f"show_variants={snapshot.get('show_variants', True)} | show_likely_dropped={snapshot.get('show_likely_dropped', True)}",
            build_queue_next_action_cue(self.state_cache or {}),
            "Semantics: recent turns plus lookahead candidate tree; lookahead buckets are not approved commands.",
            f"Queue meaning: {format_pending_queue_mode_semantics(snapshot.get('pending_queue_mode', 'normal'))}.",
            self._format_command_drip_summary(snapshot),
            "",
        ]
        lane_labels = (
            ("selected", "Selected This Turn"),
            ("executed", "Executed"),
            ("failed", "Failed"),
            ("rejected", "Rejected"),
            ("dropped", "Dropped"),
            ("deferred", "Deferred / Pushed Back"),
            ("primary_candidates", "Primary Candidates"),
            ("variant_candidates", "Close Variants"),
            ("likely_dropped", "Likely Dropped"),
        )
        for bucket in snapshot.get("turns", []) or []:
            bucket_turn = bucket.get("turn", "?")
            label = bucket.get("label") or f"turn {bucket_turn}"
            relative = bucket.get("relative_turn", "")
            timestamp = bucket.get("timestamp") or "-"
            lines.append(f"[{label}] turn={bucket_turn} | relative_turn={relative} | timestamp={timestamp}")
            bucket_had_activity = False
            for lane_key, lane_label in lane_labels:
                lane_items = bucket.get(lane_key, []) or []
                if not lane_items:
                    continue
                bucket_had_activity = True
                lines.append(f"{lane_label}:")
                for item in lane_items:
                    parts = [short(item.get("command", ""), 140)]
                    if item.get("support_count") not in (None, "", 0):
                        parts.append(f"support={item.get('support_count')}")
                    if item.get("queue_mode"):
                        parts.append(f"mode={item.get('queue_mode')}")
                    if item.get("priority_score") not in (None, ""):
                        parts.append(f"priority={item.get('priority_score')}")
                    if item.get("importance_score") not in (None, ""):
                        parts.append(f"importance={item.get('importance_score')}")
                    if item.get("risk"):
                        parts.append(f"risk={item.get('risk')}")
                    if item.get("category"):
                        parts.append(f"category={item.get('category')}")
                    if item.get("execute_by_inference") not in (None, ""):
                        parts.append(f"due={item.get('execute_by_inference')}")
                    if item.get("turns_until_due") not in (None, ""):
                        parts.append(f"in={item.get('turns_until_due')}t")
                    if item.get("superseded_by"):
                        parts.append(f"superseded_by={short(item.get('superseded_by', ''), 90)}")
                    if item.get("contradicted_by"):
                        parts.append(f"contradicted_by={short(item.get('contradicted_by', ''), 90)}")
                    if item.get("reason"):
                        parts.append(f"why={short(item.get('reason', ''), 120)}")
                    elif item.get("note"):
                        parts.append(f"note={short(item.get('note', ''), 120)}")
                    lines.append("- " + " | ".join(parts))
            notes = bucket.get("notes", []) or []
            if notes:
                bucket_had_activity = True
                lines.append("Notes:")
                for note in notes:
                    lines.append("- " + short(note, 160))
            if not bucket_had_activity:
                lines.append("- no lane activity in this retained bucket")
            lines.append("")
        return "\n".join(lines).strip()

    def _write_text(self, widget, content):
        content = "" if content is None else str(content)
        cache_key = str(widget)
        cache = getattr(self, "_text_content_cache", None)
        if cache is None:
            cache = {}
            self._text_content_cache = cache
        if cache.get(cache_key) == content:
            return
        # Frequent status refreshes must not pull a reader back to the start or
        # discard a selection. Replace atomically within this Tk event callback.
        view_y, view_x = widget.yview(), widget.xview()
        selection = widget.tag_ranges("sel")
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state="disabled")
        if view_y:
            widget.yview_moveto(view_y[0])
        if view_x:
            widget.xview_moveto(view_x[0])
        if selection:
            widget.tag_add("sel", *selection)
        cache[cache_key] = content

    def show_tab(self, tab_name):
        try:
            for tab_id in self.notebook.tabs():
                if self.notebook.tab(tab_id, "text") == tab_name:
                    if self.settings_mode == "expanded":
                        self._apply_settings_mode("hidden")
                    self.notebook.select(tab_id)
                    self.page_views[tab_name].reveal_top()
                    self.page_views[tab_name].canvas.focus_set()
                    self._sync_focus_nav_state()
                    return True
        except Exception:
            pass
        return False

    def _sync_focus_nav_state(self, _event=None):
        buttons = getattr(self, "focus_nav_buttons", {}) or {}
        active_tab = self._get_active_tab_name()
        self.focus_combo.configure(values=list(self.focus_tab_by_label))
        focus_label = getattr(self, "focus_label_by_tab", {}).get(active_tab)
        if focus_label:
            try:
                self.focus_tab_var.set(focus_label)
            except Exception:
                pass
        for tab_name, button in buttons.items():
            try:
                button.configure(style="SelectedNav.TButton" if tab_name == active_tab else "Nav.TButton")
            except Exception:
                pass

    def show_help_tab(self):
        self.show_tab("Help")
        try:
            self.help_text.see("1.0")
        except Exception:
            pass

    def show_episodic_tab(self):
        if not self.show_tab("Episodic"):
            return
        try:
            self.episodic_recent_text.see("1.0")
        except Exception:
            pass

    def show_command_list(self):
        self.show_tab("Help")
        try:
            marker = self.help_text.search("[Common Operator Commands]", "1.0", stopindex=tk.END)
            if marker:
                self.help_text.see(marker)
        except Exception:
            pass

    def _bind_navigation_shortcuts(self):
        self.bind("<Control-k>", self._focus_view_selector)
        self.bind("<Control-comma>", self.toggle_settings_pane)
        self.bind("<F11>", self.toggle_maximized)
        self.bind_all("<Left>", lambda event: self._handle_global_navigation(event, -1))
        self.bind_all("<Right>", lambda event: self._handle_global_navigation(event, 1))

    def _handle_global_navigation(self, event, delta):
        if self._focused_widget_blocks_navigation():
            return
        if self.popout_window is not None and self.popout_window.winfo_exists():
            self.step_screenshot(delta)
            return
        if self.memory_popout_window is not None and self.memory_popout_window.winfo_exists():
            self.step_image_memory(delta)
            return
        active_tab = self._get_active_tab_name()
        if active_tab == "Screenshots":
            self.step_screenshot(delta)
        elif active_tab == "Images In Memory":
            self.step_image_memory(delta)

    def _focused_widget_blocks_navigation(self):
        focus_widget = self.focus_get()
        if focus_widget is None:
            return False
        try:
            return focus_widget.winfo_class() in {"Entry", "Text", "TEntry", "TCombobox", "Combobox", "Spinbox"}
        except Exception:
            return False

    def _get_active_tab_name(self):
        try:
            current_tab = self.notebook.select()
            return self.notebook.tab(current_tab, "text")
        except Exception:
            return ""

    def on_screenshot_preview_click(self, event):
        self._handle_preview_edge_navigation(event, "screenshot")

    def on_image_memory_preview_click(self, event):
        self._handle_preview_edge_navigation(event, "image_memory")

    def _handle_preview_edge_navigation(self, event, target):
        width = max(event.widget.winfo_width(), 1)
        if width < 100:
            return
        left_threshold = width * 0.25
        right_threshold = width * 0.75
        if event.x <= left_threshold:
            if target == "screenshot":
                self.step_screenshot(-1)
            else:
                self.step_image_memory(-1)
        elif event.x >= right_threshold:
            if target == "screenshot":
                self.step_screenshot(1)
            else:
                self.step_image_memory(1)


def main():
    instance_mutex = acquire_windows_single_instance_mutex(CONTROL_PANEL_MUTEX_NAME)
    if instance_mutex is None:
        show_duplicate_instance_notice("Aurora 2 Control Panel", "Aurora 2 Control Panel is already running.")
        return
    write_pid_file(CONTROL_PANEL_PID_PATH, os.getpid())
    app = AuroraControlPanel()
    try:
        app.mainloop()
    finally:
        remove_pid_file(CONTROL_PANEL_PID_PATH, expected_pid=os.getpid())
        release_windows_single_instance_mutex(instance_mutex)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
