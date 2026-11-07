"""Visual operator surface. Runtime commands/settings remain the only write authority."""
from __future__ import annotations

import json
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from aurora_command_catalog import build_command_catalog, load_generated_catalog
from aurora_command_protocol import split_command_batch
from aurora_control_plane import journal_offsets, wait_for_command_receipt
from aurora_conversation import conversation_text
from aurora_panel_layout import CollapsibleSection, FlowBar, ui_scale, wrap_packed_labels
from aurora_settings_registry import SETTING_DEFINITIONS, coerce_setting_value
from aurora_task_continuation import task_outcome_summary, task_budget_summary

BG, CARD, INK, MUTED = "#0b1020", "#131c2b", "#e9eef5", "#a9b8cb"
GREEN, YELLOW, PURPLE = "#8ce0b5", "#f2cd70", "#c2adf5"


def preview_default_changes():
    """Explicit session baseline; credentials, game profile and legacy Advanced stay owned elsewhere."""
    values = {row.key: row.compatibility_default for row in SETTING_DEFINITIONS
              if row.key not in {"auth.mode", "game.profile", "game.scene_policy", "goals.save_format"}}
    values.update({"runtime.live": False, "runtime.execution": "safe", "runtime.action": "none",
                   "model.text": "gpt-6.1-sol", "model.vision": "gpt-6.1-sol", "model.reasoning": "gpt-6-astra",
                   "inference.reasoning_effort": "low", "capture.mode": "request_only",
                   "capture.screenshot_interval": 30.0})
    return [{"key": key, "value": coerce_setting_value(key, value)} for key, value in values.items()]


def next_inference_label(state):
    plan = (state.get("planning") or {}).get("next_inference")
    if not isinstance(plan, dict):
        return "unknown"
    keys = ("reasoning_effort", "service_tier", "verbosity", "summary_mode", "image_detail", "latest_image_detail",
            "temperature", "model", "text_model", "vision_model", "reasoning_model", "note")
    return "queued" if any(plan.get(key) not in (None, "") for key in keys) or plan.get("target_turn", 0) else "none"

CONTEXT_PARTS = (
    ("system", "System text", "Core rules and loaded Init from the last prepared request. Click for text and preparation time."),
    ("init", "Init file", "Loaded persistent Init, its source and clipping. A configured filename alone does not prove it was loaded."),
    ("conversation", "Conversation", "Current eligible user and assistant messages, after context selection. Queued unsent input and old logs are separate."),
    ("current", "Prompt text", "The last prepared user or screenshot-review text. This is distinct from the screenshot image itself."),
    ("memory", "Working memory", "Last prepared goals, notes and state snapshot; retrieval material is separately inspectable."),
    ("screen", "Screenshot", "Latest observed capture path and time. Capturing a frame does not prove it was sent to a model."),
)


def context_teaser(state, kind):
    if kind == "init":
        text = (state.get("init_context") or {}).get("text") or "No loaded Init"
    elif kind == "conversation":
        rows = ((state.get("conversation") or {}).get("current") or {}).get("rows") or []
        text = rows[-1].get("text", "") if rows else "No current messages"
    elif kind == "screen":
        text = state.get("last_screenshot_timestamp") or "No capture reported"
    else:
        text = (((state.get("prompt_materials") or {}).get("sections") or {}).get(kind) or {}).get("text") or "No prepared text yet"
    return " ".join(str(text).split())[:180]


def context_contents(state, kind):
    """Read-only presentation; no prompt rebuilding, retrieval, capture or model calls."""
    if kind == "init":
        item = state.get("init_context") or {}
        return (f"Loaded Init\nSource: {item.get('source', 'unknown')}\nProfile: {item.get('profile', 'unknown')}\n"
                f"Configured next initialization: {item.get('configured_mode', 'unknown')} / {item.get('configured_file', 'unknown')}\n"
                f"Displayed: {item.get('displayed_chars', 0)} of {item.get('total_chars', 0)} characters · truncated: {item.get('truncated', 'unknown')}\n"
                f"{item.get('note', 'Init observation unavailable.')}\n\n{item.get('text') or '[No loaded Init text reported.]'}")
    if kind == "conversation":
        view = (state.get("conversation") or {}).get("current") or {}
        return (f"Current eligible conversation — not the complete provider request\nSource: {view.get('source', 'unknown')}\n"
                f"Rows: {len(view.get('rows', []))} · omitted: {view.get('omitted', 'unknown')} · shortened: {view.get('shortened', 'unknown')}\n"
                "Queued input is not included until the runtime consumes it. Old logs are available in Chat.\n\n" +
                (conversation_text(view) or "[No current conversation reported.]"))
    if kind == "screen":
        return (f"Latest observed screenshot\nFile: {state.get('last_screenshot_path') or 'unknown'}\n"
                f"Captured: {state.get('last_screenshot_timestamp') or 'unknown'}\n\n"
                "This may differ from the image used in the last request. Open Screenshots to view available images.\n\nLast prepared request diagnostics:\n" +
                json.dumps((state.get("planning") or {}).get("prompt_diagnostics") or {}, indent=2))
    evidence = state.get("prompt_materials") or {}
    part = (evidence.get("sections") or {}).get(kind) or {}
    return (f"Last prepared {kind} text\nPrepared: {evidence.get('prepared_at', 'unknown')}\nModel: {evidence.get('model', 'unknown')}\n"
            f"Displayed: {part.get('displayed_chars', 0)} of {part.get('total_chars', 0)} characters · truncated: {part.get('truncated', 'unknown')}\n"
            f"{evidence.get('note', 'No request preparation has been recorded by this runtime.')}\n\n" +
            (part.get("text") or "[No text recorded for this component.]"))


def load_switchboard_catalog(root):
    """Prefer verified generated data; source AST is a safe fallback, never import runtime."""
    try:
        return load_generated_catalog(Path(root) / "aurora_reference_maps/commands/commands.json", root=Path(root))
    except (OSError, ValueError):
        return build_command_catalog(Path(root))["commands"]


def command_draft(row):
    """Make placeholders visibly non-executable, including undocumented signatures."""
    name = row["command"]
    signature = row.get("signature", "")
    if "(" not in signature:
        return name + "(<arguments>)"
    arguments = signature.split("(", 1)[1].rsplit(")", 1)[0].strip()
    return name + ("()" if not arguments else "(<" + arguments + ">)")


def validate_switchboard_batch(text, rows):
    """Framing/name checks only; runtime retains argument, admission and permission checks."""
    if len(text) > 64000:
        raise ValueError("Command draft exceeds 64,000 characters.")
    commands = split_command_batch(text)
    if not commands:
        raise ValueError("Enter a command or prepare one from the browser.")
    names = {row["command"].casefold() for row in rows}
    for command in commands:
        if re.search(r"<[^<>\n]+>", command):
            raise ValueError("Replace the <argument placeholders> before running.")
        name = command.split("(", 1)[0].strip()
        if name.casefold() not in names:
            raise ValueError(f"Unknown command: {name}. Use the browser or the existing Commands view for other syntax.")
    return commands


def switchboard_flow(state, *, fresh=False, level="Groups"):
    """Configured topology, not an execution trace. Missing values stay unknown."""
    modes, scheduler, models = (state.get(key) or {} for key in ("modes", "scheduler", "models"))
    active = bool(((state.get("processes") or {}).get("runtime") or {}).get("active"))
    live = modes.get("live") is True
    enabled = active and fresh
    capture_mode = modes.get("capture_mode", "unknown")
    interval = modes.get("effective_screenshot_interval")
    def seconds(value):
        return f"{value:g}s" if isinstance(value, (int, float)) and not isinstance(value, bool) else "unknown interval"
    heartbeat = isinstance(scheduler.get("heartbeat_seconds"), (int, float)) and scheduler["heartbeat_seconds"] > 0
    if level == "Overview":
        labels = ["Observe", "Think", "Act", "Remember"]
    elif level == "Functions":
        labels = ["screenshot_capture", "evaluate_turn_scheduler", "handle_commands", "HistoryContextService"]
    else:
        labels = ["Screen + requests", "Scheduler + model", "Admission + actions", "Context + receipts"]
    nodes = [
        {"label": labels[0], "detail": f"{capture_mode}\n{seconds(interval)} cadence", "on": enabled},
        {"label": labels[1], "detail": f"{scheduler.get('mode', 'unknown')} | {'inference on' if live else 'inference off'}\n{models.get('text', 'unknown model')}", "on": enabled and live},
        {"label": labels[2], "detail": f"{modes.get('execution', 'unknown')} policy\n{modes.get('action', 'unknown')} input mode", "on": enabled},
        {"label": labels[3], "detail": "Current context + memory\nCorrelated outcomes", "on": enabled},
    ]
    loops = [
        {"from": 0, "label": "Capture " + seconds(interval), "on": enabled and capture_mode == "heartbeat"},
        {"from": 1, "label": "Turn " + seconds(scheduler.get("heartbeat_seconds")), "on": enabled and live and heartbeat},
    ]
    edges = [
        {"from": 0, "to": 1, "label": "fresh observation", "on": enabled and live},
        {"from": 1, "to": 2, "label": "proposed commands", "on": enabled and live},
        {"from": 2, "to": 3, "label": "receipts + outcomes", "on": enabled},
        {"from": 3, "to": 0, "label": "request fresh frame", "on": enabled and scheduler.get("demand_capture_enabled") is True},
    ]
    destinations = ["Screenshots", "Live Harness", "Pending", "History Context"]
    if level == "Overview":
        nodes = [nodes[0], nodes[1], {"label": "Act + remember", "detail": "Policy → actions → receipts\nRetain context for the next turn", "on": enabled}]
        nodes[0]["label"] = "Capture / requests"
        nodes[1]["label"] = "Send to ChatGPT"
        edges = [edges[0], edges[1], {"from": 2, "to": 0, "label": "feedback / new observation", "on": enabled}]
        destinations = ["Screenshots", "Live Harness", "Dashboard"]
    elif level == "Functions":
        specs = [
            ("screenshot_capture", "Due request or heartbeat\nCapture a new frame", "Screenshots", enabled),
            ("persist_runtime_capture", "Frame identity + metadata\nLatest observation", "Image Index", enabled),
            ("evaluate_turn_scheduler", "User input / outcomes / timers\nSpacing and settle gates", "Live Harness", enabled and live),
            ("chatgpt_process", "Build context → model I/O\n" + str(models.get("text", "unknown model")), "Conversation", enabled and live),
            ("handle_commands", "Parse + whole-batch admission\nLocks, policy and pending", "Pending", enabled),
            ("execute_command_entry", "Execute admitted work\nCancellation / held-input owner", "Recovery", enabled),
            ("write_command_execution_log", "Correlated receipt\nSubmitted ≠ visibly verified", "Commands", enabled),
            ("build_control_panel_state_snapshot", "Readback + context export\nPanel / next decision", "Raw State", enabled),
        ]
        nodes = [{"label": name, "detail": detail, "on": on} for name, detail, _dest, on in specs]
        destinations = [row[2] for row in specs]
        edges = [{"from": i, "to": i + 1, "label": "", "on": enabled and (live if i in {1, 2, 3} else True)} for i in range(7)]
        loops[1]["from"] = 2
    for node, destination in zip(nodes, destinations):
        node["destination"] = destination
    return {"nodes": nodes, "loops": loops, "edges": edges,
            "status": "Observed configuration" if enabled else "Runtime inactive" if not active else "Stale / unknown configuration"}


class PortalShortcuts(ttk.Frame):
    """Shared cached clockwise frames; one bounded animation timer per panel."""
    def __init__(self, parent, app, root):
        super().__init__(parent)
        self.app = app
        if not hasattr(app, "_portal_shortcuts"):
            app._portal_shortcuts, app._portal_frames = [], []
            app._portal_index, app._portal_after = 0, None
            app.portal_motion_var = tk.BooleanVar(value=app.ui_preferences.get("portal_motion", True))
            try:
                from PIL import Image, ImageTk
                with Image.open(Path(root) / "aurora_portal_spinner.png") as source:
                    base = source.convert("RGB").resize((36, 36), Image.Resampling.LANCZOS)
                app._portal_frames = [ImageTk.PhotoImage(base.rotate(-i * 15, resample=Image.Resampling.BICUBIC, fillcolor=base.getpixel((0, 0)))) for i in range(24)]
            except (OSError, ImportError):
                pass
        self.portal = ttk.Button(self, text="Conversation", compound="left", command=lambda: app.show_tab("Conversation"))
        self.portal.pack(side="left", padx=(0, 5))
        self.chat = ttk.Button(self, text="Popout chat  ↗", command=app.open_conversation_popout)
        try:
            from PIL import Image, ImageDraw, ImageTk
            icon = Image.new("RGBA", (44, 30))
            drawing = ImageDraw.Draw(icon)
            drawing.rectangle((2, 3, 29, 21), outline=MUTED, width=2)
            drawing.line((9, 21, 15, 27, 20, 21), fill=MUTED, width=2)
            drawing.line((7, 9, 24, 9), fill=MUTED, width=2)
            drawing.line((7, 15, 21, 15), fill=MUTED, width=2)
            drawing.polygon(((34, 6), (43, 15), (34, 23)), fill="#70b5ed")
            self.chat_image = ImageTk.PhotoImage(icon)
            self.chat.configure(image=self.chat_image, compound="left")
        except ImportError:
            pass
        self.chat.pack(side="left")
        app._portal_shortcuts.append(self)
        if app._portal_after is None:
            self.tick()

    def tick(self):
        app = self.app
        if getattr(app, "_closing", False):
            return
        frames = app._portal_frames
        visible = [item for item in app._portal_shortcuts if item.winfo_exists() and item.winfo_ismapped()]
        index = app._portal_index if app.portal_motion_var.get() else 0
        if frames:
            for item in visible:
                item.portal.configure(image=frames[index % len(frames)])
        if visible and app.portal_motion_var.get():
            app._portal_index += 1
        app._portal_after = app.after(125 if visible and app.portal_motion_var.get() else 500, self.tick)


class Switchboard(ttk.Frame):
    """Responsive, scroll-hosted controls with preserved drafts and exact receipts."""
    def __init__(self, parent, app, root):
        super().__init__(parent)
        self.app, self.root = app, Path(root)
        self.rows = load_switchboard_catalog(root)
        self.variables, self.observed, self.readbacks, self.dirty = {}, {}, {}, set()
        self.readback_labels, self._readback_details = {}, {}
        self.sliders = {}
        self.receipts, self.pending = queue.Queue(), None
        self._flow_signature = None
        self._fresh = False
        title = FlowBar(self)
        title.pack(fill="x", pady=(0, 8))
        try:
            from PIL import Image, ImageTk
            with Image.open(self.root / "aurora_flow_emblem.png") as source:
                self.emblem = ImageTk.PhotoImage(source.resize((38, 38), Image.Resampling.LANCZOS))
            title.add(ttk.Label(title, image=self.emblem))
        except (OSError, ImportError):
            pass
        title.add(ttk.Label(title, text="The Switchboard", font=("Segoe UI Semibold", 16)))
        title.add(ttk.Button(title, text="Reset to preview defaults", command=self.open_defaults))
        self.hint = tk.StringVar(value="Start the runtime to read effective controls. Drafting is available offline.")
        ttk.Label(self, textvariable=self.hint, style="Muted.TLabel", wraplength=820).pack(fill="x", pady=(0, 8))
        self.running_summary = tk.StringVar(value="Models and modes: waiting for observed runtime state.")
        ttk.Label(self, textvariable=self.running_summary, foreground=PURPLE, wraplength=950).pack(fill="x", pady=(0, 6))

        self.controls = CollapsibleSection(self, "Switches & timing — edit, preview, apply", expanded=False)
        self.controls.pack(fill="x", pady=(0, 10))
        body = self.controls.body
        main_keys = ("capture.mode", "capture.screenshot_interval", "capture.demand_enabled",
                     "scheduler.mode", "scheduler.heartbeat_seconds", "scheduler.capture_wake_enabled",
                     "runtime.live", "runtime.execution", "runtime.action", "model.text", "inference.reasoning_effort")
        definitions = {row.key: row for row in SETTING_DEFINITIONS}
        inference = None
        for key in main_keys:
            if key == "scheduler.mode":
                inference = CollapsibleSection(body, "Inference, model & turn scheduling", expanded=False)
                inference.pack(fill="x", pady=(6, 0))
            self.add_setting(inference.body if inference is not None else body, definitions[key])
        advanced = CollapsibleSection(body, "More switches — all registered settings", expanded=False)
        advanced.pack(fill="x", pady=(6, 0))
        for definition in SETTING_DEFINITIONS:
            if definition.key not in main_keys:
                self.add_setting(advanced.body, definition)
        ttk.Label(body, text="Capture heartbeat takes screenshots; turn heartbeat may call a paid model. Requests only still allows command-result captures.\nSwitches edit a draft. Apply changes the current session; Save defaults remains an explicit Advanced action.",
                  style="Muted.TLabel", wraplength=800).pack(fill="x", pady=8)
        bar = FlowBar(body)
        bar.pack(fill="x")
        self.preview_button = bar.add(ttk.Button(bar, text="Preview switches", command=lambda: self.submit_settings("preview")))
        self.apply_button = bar.add(ttk.Button(bar, text="Apply switches", style="SwitchRun.TButton", command=lambda: self.submit_settings("apply")))
        self.rollback_button = bar.add(ttk.Button(bar, text="Undo last settings apply", command=self.rollback))
        bar.add(ttk.Button(bar, text="Reload observed", command=self.reload))
        bar.add(ttk.Button(bar, text="Capture now", command=lambda: self.run_text("REQUEST_SCREENSHOT_CAPTURE(switchboard,0)")))
        bar.add(ttk.Button(bar, text="Pause inference", command=lambda: self.run_text("SET_LIVE_MODE(off)")))
        ttk.Label(body, textvariable=app.settings_transaction_status_var, style="Muted.TLabel", wraplength=800).pack(fill="x", pady=6)

        self.model_bar = FlowBar(self)
        self.model_bar.pack(fill="x", before=self.controls, pady=(0, 6))
        self.model_selectors = {}
        self.model_keys = {"model.text", "model.vision", "model.reasoning", "inference.reasoning_effort"}
        for label, key in (("Primary", "model.text"), ("Vision", "model.vision"), ("Review", "model.reasoning")):
            group = self.model_bar.add(ttk.Frame(self.model_bar))
            ttk.Label(group, text=label, foreground=PURPLE).pack(side="left", padx=(0, 5))
            self.model_selectors[key] = ttk.Combobox(group, textvariable=self.variables[key], width=20)
            self.model_selectors[key].pack(side="left")
        effort_group = self.model_bar.add(ttk.Frame(self.model_bar))
        ttk.Label(effort_group, text="Primary effort").pack(side="left", padx=(0, 5))
        ttk.Combobox(effort_group, textvariable=self.variables["inference.reasoning_effort"],
                     values=definitions["inference.reasoning_effort"].allowed_values, state="readonly", width=9).pack(side="left")
        self.model_apply_button = self.model_bar.add(ttk.Button(self.model_bar, text="Apply model choices", style="SwitchRun.TButton",
                                                     command=lambda: self.submit_settings("apply", keys=self.model_keys)))
        self.model_status = ttk.Label(self, text="Model selections are drafts until Apply.", style="Muted.TLabel", wraplength=950)
        self.model_status.pack(fill="x", before=self.controls, pady=(0, 6))

        self.defaults_section = CollapsibleSection(self, "Preview defaults — a known starting point", expanded=False)
        self.defaults_section.pack(fill="x", before=self.controls, pady=(0, 10))
        ttk.Label(self.defaults_section.body, text=f"Resets the {len(preview_default_changes())} registered controls listed below for this session: inference paused, safe execution, action mode none, Sol low / Astra, capture on request.\nAuthentication, game profile, chats, files, saved profiles and unlisted Advanced settings stay as they are. An in-flight request may still finish remotely.\nUse Cancel work for queued/in-flight commands; Recovery has System and Personal profile restoration.",
                  wraplength=950, style="Muted.TLabel").pack(fill="x", pady=5)
        self.defaults_preview = tk.Text(self.defaults_section.body, height=8, wrap="none", bg=CARD, fg=INK, relief="flat")
        defaults_scroll = ttk.Scrollbar(self.defaults_section.body, command=self.defaults_preview.yview)
        self.defaults_preview.configure(yscrollcommand=defaults_scroll.set)
        defaults_scroll.pack(side="right", fill="y")
        self.defaults_preview.pack(fill="x")
        defaults_actions = FlowBar(self.defaults_section.body)
        defaults_actions.pack(fill="x", pady=6)
        defaults_actions.add(ttk.Button(defaults_actions, text="Validate reset", command=lambda: self.submit_defaults("preview")))
        defaults_actions.add(ttk.Button(defaults_actions, text="Apply preview defaults", style="SwitchRun.TButton", command=lambda: self.submit_defaults("apply")))
        defaults_actions.add(ttk.Button(defaults_actions, text="Undo last settings apply", command=self.rollback))
        defaults_actions.add(ttk.Button(defaults_actions, text="Recovery / saved profiles", command=lambda: app.show_tab("Recovery")))

        graph_section = CollapsibleSection(self, "Flow map — observed configuration", expanded=True)
        self.flow_section = graph_section
        graph_section.pack(fill="x", pady=(0, 10))
        graph_bar = FlowBar(graph_section.body)
        graph_bar.pack(fill="x")
        self.level = tk.StringVar(value="Overview")
        level = graph_bar.add(ttk.Combobox(graph_bar, textvariable=self.level, values=("Overview", "Groups", "Functions"), state="readonly", width=14))
        level.bind("<<ComboboxSelected>>", lambda _e: self.draw_flow(force=True))
        graph_bar.add(ttk.Checkbutton(graph_bar, text="Animate Portal icon", variable=app.portal_motion_var))
        graph_bar.add(ttk.Button(graph_bar, text="Dashboard receipts", command=lambda: app.show_tab("Dashboard")))
        ttk.Label(graph_section.body, text="Solid = enabled route · dashed = inactive / unknown. Arrows describe configuration, not a live execution trace.",
                  style="Muted.TLabel", wraplength=800).pack(fill="x", pady=6)
        self.graph = tk.Canvas(graph_section.body, height=340, bg=BG, highlightthickness=0)
        self.graph.pack(fill="x")
        self.graph.bind("<Configure>", lambda _e: self.draw_flow(force=True))
        self.graph.bind("<Button-1>", self.graph_click)
        self.graph.bind("<Motion>", self.graph_hover)
        self.graph.bind("<Leave>", self.hide_init_tip)

        commands = CollapsibleSection(self, "Command desk — prepare in yellow, run in green", expanded=False)
        self.commands_section = commands
        commands.pack(fill="x", pady=(0, 10))
        filters = FlowBar(commands.body)
        filters.pack(fill="x")
        self.query, self.category = tk.StringVar(), tk.StringVar(value="All subsystems")
        filters.add(ttk.Label(filters, text="Find command"))
        filters.add(ttk.Entry(filters, textvariable=self.query, width=27))
        categories = ["All subsystems"] + sorted({row["category"] for row in self.rows})
        filters.add(ttk.Combobox(filters, textvariable=self.category, values=categories, state="readonly", width=25))
        self.count = tk.StringVar()
        filters.add(ttk.Label(filters, textvariable=self.count, style="Muted.TLabel"))
        self.query.trace_add("write", self.filter_commands)
        self.category.trace_add("write", self.filter_commands)
        table = ttk.Frame(commands.body)
        table.pack(fill="x", pady=8)
        self.tree = ttk.Treeview(table, columns=("command", "category"), show="headings", height=7, selectmode="browse")
        self.tree.heading("command", text="Command (select to inspect)")
        self.tree.heading("category", text="Subsystem")
        self.tree.column("command", width=370, minwidth=180)
        self.tree.column("category", width=180, minwidth=100)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_command)
        self.tree.bind("<Double-1>", lambda _e: self.prepare_selected())
        self.command_detail = tk.StringVar(value="Choose a command. Selecting is read-only; double-click prepares it.")
        ttk.Label(commands.body, textvariable=self.command_detail, wraplength=800, foreground=MUTED).pack(fill="x")
        actions = FlowBar(commands.body)
        actions.pack(fill="x", pady=8)
        actions.add(ttk.Button(actions, text="Prepare selected", style="SwitchPrepare.TButton", command=self.prepare_selected))
        self.run_selected_button = actions.add(ttk.Button(actions, text="Run selected", style="SwitchRun.TButton", command=self.run_selected))
        actions.add(ttk.Button(actions, text="Commands help", command=lambda: app.show_tab("Commands")))
        actions.add(ttk.Button(actions, text="Reset to preview defaults", command=self.open_defaults))
        self.editor = tk.Text(commands.body, height=3, wrap="word", bg=CARD, fg=INK, insertbackground=INK,
                              relief="flat", padx=12, pady=10, font=("Consolas", 10), undo=True)
        self.editor.pack(fill="x")
        self.editor.bind("<Control-Return>", lambda _e: self.run_text())
        runbar = FlowBar(commands.body)
        runbar.pack(fill="x", pady=8)
        self.run_button = runbar.add(ttk.Button(runbar, text="Run command draft", style="SwitchRun.TButton", command=self.run_text))
        runbar.add(ttk.Button(runbar, text="Clear draft", command=lambda: self.editor.delete("1.0", "end")))
        runbar.add(ttk.Button(runbar, text="Cancel runtime work", command=lambda: app.send_raw("CANCEL_ACTIVE_WORK()")))
        self.command_status = tk.StringVar(value="Yellow only fills the draft. Green queues immediately through Aurora admission; it does not bypass locks or policy.")
        ttk.Label(commands.body, textvariable=self.command_status, wraplength=800, style="Muted.TLabel").pack(fill="x")
        details = CollapsibleSection(commands.body, "Receipt & output details", expanded=False)
        details.pack(fill="x", pady=8)
        self.output = tk.Text(details.body, height=9, wrap="word", bg=CARD, fg=INK, relief="flat", state="disabled")
        outscroll = ttk.Scrollbar(details.body, command=self.output.yview)
        self.output.configure(yscrollcommand=outscroll.set)
        outscroll.pack(side="right", fill="y")
        self.output.pack(fill="both", expand=True)
        ttk.Label(details.body, text="Receipts show delivery/execution evidence. Read-command prose remains in Chat / terminal; no replay on timeout.",
                  style="Muted.TLabel", wraplength=800).pack(fill="x")
        self.filter_commands()
        graph_section.pack_forget()
        graph_section.pack(fill="x", before=self.controls, pady=(0, 10))
        self.init_section = CollapsibleSection(self, "Contents — inspect model context", expanded=False)
        self.init_section.pack(fill="x", before=self.controls, pady=(0, 10))
        self.init_text = tk.Text(self.init_section.body, height=12, wrap="word", bg=CARD, fg=INK, relief="flat", state="disabled", padx=12, pady=10)
        init_scroll = ttk.Scrollbar(self.init_section.body, command=self.init_text.yview)
        self.init_text.configure(yscrollcommand=init_scroll.set)
        init_scroll.pack(side="right", fill="y")
        self.init_text.pack(fill="both", expand=True)
        self._init_signature = None
        self._contents_kind = "init"
        self._hover_kind = None
        self._settings_receipt_signature = None
        links = FlowBar(self.init_section.body)
        links.pack(fill="x", before=self.init_text, pady=4)
        for kind, label in (("init", "Init"), ("system", "System"), ("memory", "Memory"), ("retrieval", "Retrieval"), ("current", "Last user prompt"), ("conversation", "Current conversation"), ("screen", "Screenshot details")):
            links.add(ttk.Button(links, text=label, command=lambda k=kind: self.show_contents(k)))
        links.add(ttk.Button(links, text="View images ↗", command=lambda: app.show_tab("Screenshots")))
        self._init_tip = None
        jump = FlowBar(self)
        jump.pack(fill="x", before=graph_section, pady=(0, 8))
        for label, section in (("Overview", graph_section), ("Switches", self.controls), ("Commands", commands)):
            jump.add(ttk.Button(jump, text=label, command=lambda s=section: self.jump(s)))
        self.init_button = jump.add(ttk.Button(jump, text="Init · contents", command=lambda: self.show_contents("init")))
        self.init_button.bind("<Enter>", self.show_init_tip)
        self.init_button.bind("<Leave>", self.hide_init_tip)
        self.init_button.bind("<Button-1>", self.hide_init_tip, add="+")
        self.bind("<Destroy>", self.hide_init_tip, add="+")

    def jump(self, section):
        section.set_expanded(True)
        self.update_idletasks()
        page = self.app.page_views["The Switchboard"]
        offset = section.winfo_rooty() - page.inner.winfo_rooty()
        page.canvas.yview_moveto(max(0, offset / max(1, page.inner.winfo_height())))

    def show_init_tip(self, _event=None):
        self.show_tip("init", self.init_button.winfo_rootx(), self.init_button.winfo_rooty() + self.init_button.winfo_height())

    def show_tip(self, kind, x, y):
        self.hide_init_tip()
        self._hover_kind = kind
        description = next((description for key, _label, description in CONTEXT_PARTS if key == kind), "Click to inspect this component.")
        preview = context_contents(self.app.state_cache or {}, kind)[:700]
        window = self._init_tip = tk.Toplevel(self)
        window.overrideredirect(True)
        ttk.Label(window, text=f"{description}\n\n{preview}",
                  wraplength=420, padding=12, background=CARD, foreground=INK).pack()
        window.update_idletasks()
        x = max(0, min(x, self.app.winfo_screenwidth() - window.winfo_reqwidth()))
        y = max(0, min(y, self.app.winfo_screenheight() - window.winfo_reqheight()))
        window.geometry(f"+{x}+{y}")

    def hide_init_tip(self, _event=None):
        self._hover_kind = None
        if self._init_tip is not None:
            self._init_tip.destroy()
            self._init_tip = None

    def show_contents(self, kind):
        self.hide_init_tip()
        self._contents_kind = kind
        self.refresh_contents()
        self.jump(self.init_section)

    def refresh_contents(self):
        text = context_contents(self.app.state_cache or {}, self._contents_kind)
        if text != self._init_signature:
            self._init_signature = text
            position = self.init_text.yview()
            self.init_text.configure(state="normal")
            self.init_text.delete("1.0", "end")
            self.init_text.insert("1.0", text)
            self.init_text.configure(state="disabled")
            self.init_text.yview_moveto(position[0])

    def add_setting(self, parent, definition):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(3, 5))
        var = tk.StringVar(value="")
        self.variables[definition.key] = var
        ttk.Label(row, text=definition.title, foreground=PURPLE).pack(anchor="w")
        if definition.key.startswith("task.") or definition.key in {"context.init_delivery", "scheduler.readback_wake_enabled", "conversation.input_recovery", "execution.recording"}:
            ttk.Label(row, text=definition.description + (" Operator only." if definition.operator_only else ""),
                      style="Muted.TLabel", wraplength=800).pack(fill="x")
        controls = FlowBar(row)
        controls.pack(fill="x")
        if definition.value_type == "boolean":
            controls.add(ttk.Checkbutton(controls, text="Enabled", variable=var, onvalue="true", offvalue="false"))
        elif definition.allowed_values:
            controls.add(ttk.Combobox(controls, textvariable=var, values=definition.allowed_values, state="readonly", width=23))
        else:
            controls.add(ttk.Entry(controls, textvariable=var, width=23))
        if definition.key in {"capture.screenshot_interval", "scheduler.heartbeat_seconds", "scheduler.min_gap_seconds"}:
            minimum = float(definition.minimum or 0)
            dial_value = tk.DoubleVar(value=max(minimum, .1))
            self.sliders[definition.key] = (dial_value, max(minimum, .1))
            slider = ttk.Scale(controls, from_=max(minimum, .1), to=60,
                               variable=dial_value,
                               command=lambda value, v=var: v.set(f"{float(value):.2f}"))
            controls.add(slider)
            # The entry retains the entire supported numeric range, beyond the convenient dial.
            controls.add(ttk.Label(controls, text="seconds (dial 0.1–60; type any valid value)", style="Muted.TLabel"))
        readback = tk.StringVar(value="Observed: unknown")
        self.readbacks[definition.key] = readback
        label = ttk.Label(row, textvariable=readback, style="Muted.TLabel", wraplength=800)
        label.pack(anchor="w")
        self.readback_labels[definition.key] = label
        var.trace_add("write", lambda *_a, key=definition.key: self.mark_dirty(key))

    def mark_dirty(self, key):
        if key in self.sliders:
            dial, minimum = self.sliders[key]
            try:
                dial.set(min(60, max(minimum, float(self.variables[key].get()))))
            except ValueError:
                pass
        if self.variables[key].get() != self.observed.get(key, ""):
            self.dirty.add(key)
        else:
            self.dirty.discard(key)
        self.refresh_setting_feedback(key)
        self.refresh_draft_hint()

    def refresh_setting_feedback(self, key):
        """Show unsubmitted edits beside the control without changing readback authority."""
        observed = self._readback_details.get(key, "Observed: unknown")
        draft = self.variables[key].get()
        dirty = key in self.dirty
        prefix = f"Draft: {draft or '(empty)'} — not applied. " if dirty else ""
        self.readbacks[key].set(prefix + observed)
        self.readback_labels[key].configure(style="Draft.TLabel" if dirty else "Muted.TLabel")

    def refresh_draft_hint(self):
        self.hint.set(f"{'Runtime connected' if self._fresh else 'Inactive / stale — editing drafts only'} · {len(self.dirty)} edited switches · {len(self.rows)} command bindings")

    def reload(self):
        self.dirty.clear()
        self.update_state(force=True)

    def focus_models(self):
        self.app.show_tab("The Switchboard")
        self.app.page_views["The Switchboard"].canvas.yview_moveto(0)
        self.model_selectors["model.text"].focus_set()

    def focus_setting(self, key):
        """Reveal an existing registered switch without editing its draft."""
        self.app.show_tab("The Switchboard")
        row = self.readback_labels[key].master
        parent = row.master
        while parent is not self:
            if isinstance(parent, CollapsibleSection):
                parent.set_expanded(True)
            parent = parent.master
        self.update_idletasks()
        page = self.app.page_views["The Switchboard"]
        offset = row.winfo_rooty() - page.inner.winfo_rooty()
        page.canvas.yview_moveto(max(0, offset / max(1, page.inner.winfo_height())))

    def open_defaults(self):
        self.app.show_tab("The Switchboard")
        self.update_state()
        self.defaults_preview.configure(state="normal")
        self.defaults_preview.delete("1.0", "end")
        self.defaults_preview.insert("1.0", "Observed now → preview default (session only)\n" + "\n".join(
            f"{row['key']}: {self.observed.get(row['key'], 'unknown')} → {row['value']}" for row in preview_default_changes()))
        self.defaults_preview.configure(state="disabled")
        self.jump(self.defaults_section)

    def submit_defaults(self, operation):
        return self.app._submit_settings_transaction(operation, changes=preview_default_changes(),
            activity_label=f"Preview defaults ({len(preview_default_changes())} controls; other Advanced settings retained)", inline_results=True)

    def submit_settings(self, operation, keys=None):
        try:
            selected = self.dirty if keys is None else self.dirty.intersection(keys)
            changes = [{"key": key, "value": coerce_setting_value(key, self.variables[key].get())} for key in sorted(selected)]
            if not changes:
                self.app.settings_transaction_status_var.set("No edited Switchboard values to apply.")
                return
            return self.app._submit_settings_transaction(operation, changes=changes, activity_label="Switchboard", inline_results=True)
        except ValueError as error:
            self.app.settings_transaction_status_var.set(str(error))

    def rollback(self):
        handle = self.app.settings_transaction_last_rollback_handle
        if handle:
            return self.app._submit_settings_transaction("rollback", rollback_handle=handle, activity_label="Switchboard undo", inline_results=True)

    def filter_commands(self, *_args):
        selection = self.tree.selection()
        current = selection[0] if selection else None
        self.tree.delete(*self.tree.get_children())
        query, category = self.query.get().casefold().split(), self.category.get()
        for index, row in enumerate(self.rows):
            haystack = " ".join(str(row.get(key, "")) for key in ("command", "summary", "category", "aliases")).casefold()
            if all(word in haystack for word in query) and (category == "All subsystems" or row["category"] == category):
                self.tree.insert("", "end", iid=str(index), values=(row["command"], row["category"]))
        if current and self.tree.exists(current):
            self.tree.selection_set(current)
        self.count.set(f"{len(self.tree.get_children())} / {len(self.rows)} bindings")

    def selected(self):
        selected = self.tree.selection()
        return self.rows[int(selected[0])] if selected else None

    def select_command(self, _event=None):
        row = self.selected()
        if row:
            self.command_detail.set(f"{row['signature']}\n{row['summary']}\nSource: {row['source']['file']}:{row['source']['line']} · {row['signature_source']}")

    def prepare_selected(self):
        row = self.selected()
        if row:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", command_draft(row))
            self.editor.focus_set()
            self.command_status.set("Prepared only. Replace <placeholders>, then choose Run command draft.")

    def run_selected(self):
        row = self.selected()
        if not row:
            self.command_status.set("Select a command first.")
            return
        draft = command_draft(row)
        if "<" in draft:
            self.prepare_selected()
            self.command_status.set("This command needs arguments. Fill the prepared draft, then run it.")
            return
        self.run_text(draft)

    def run_text(self, text=None):
        text = self.editor.get("1.0", "end-1c").strip() if text is None else text
        try:
            validate_switchboard_batch(text, self.rows)
            if not self._fresh:
                raise ValueError("Runtime inactive or state stale. Start / refresh it before running commands.")
            if self.pending:
                raise ValueError("Waiting for the current receipt. Use the persistent Cancel work button if needed.")
            offsets = journal_offsets(self.root)
            record = self.app.send_raw(text)
            self.pending = record["request_id"]
            self.command_status.set(f"Queued — not yet confirmed. Request {self.pending}")
            threading.Thread(target=self.wait_receipt, args=(record, offsets), daemon=True,
                             name="aurora-switchboard-receipt").start()
        except (OSError, ValueError) as error:
            self.command_status.set(str(error))
        return "break"

    def wait_receipt(self, record, offsets):
        try:
            result = wait_for_command_receipt(self.root, record["request_id"], client_id=record["client_id"],
                                              offsets=offsets, timeout_seconds=20, poll_interval_seconds=.1)
        except Exception as error:
            result = {"status": "unknown", "reason": str(error), "request_id": record["request_id"]}
        self.receipts.put(result)

    def update_state(self, force=False):
        # Full transaction/version evidence remains in expanded switches and
        # Dashboard; long hashes should not dominate the compact model picker.
        self.model_status.configure(text=self.app.settings_transaction_status_var.get().split(" | version ")[0])
        state = self.app.state_cache or {}
        models, model_status, modes = (state.get(key) or {} for key in ("models", "model_status", "modes"))
        review_n = model_status.get("review_turn_interval")
        choices = sorted(set((state.get("model_catalog") or {}).get("choices") or []) | {str(value) for value in (models.get("text"), models.get("vision"), models.get("reasoning")) if value})
        for selector in self.model_selectors.values():
            selector.configure(values=choices)
        review = f"every {review_n} turns" if isinstance(review_n, (int, float)) and review_n > 0 else "on call / no periodic review" if review_n == 0 else "cadence unknown"
        continuation = state.get("continuation") or {}
        task = continuation.get("active_task") or {}
        self.running_summary.set(
            f"Primary: {models.get('text', 'unknown')} · {model_status.get('reasoning_effort', 'unknown')} effort   |   Vision: {models.get('vision', 'unknown')}\n"
            f"Review: {models.get('reasoning', 'unknown')} · {model_status.get('review_reasoning_effort', 'unknown')} effort · {review}   |   Dynamic inference: {model_status.get('auto_dynamic_inference', 'unknown')}\n"
            f"Mode: {modes.get('execution', 'unknown')} / {modes.get('action', 'unknown')} · {models.get('transport', 'unknown')}   |   Screenshot: {modes.get('capture_mode', 'unknown')} · {modes.get('effective_screenshot_interval', 'unknown')}s effective   |   Turn heartbeat: {(state.get('scheduler') or {}).get('heartbeat_seconds', 'unknown')}s\n"
            f"Turn: {(state.get('planning') or {}).get('inference_counter', 'unknown')} · Pending proposals: {len(state.get('pending_commands') or [])} displayed · Next-turn override: {next_inference_label(state)} · Model selectors below are drafts until Apply.\n"
            f"Task: {continuation.get('mode', 'unknown')} · {task.get('status', 'unknown')} · {task.get('turns', 0)}/{task.get('max_turns', '?')} model turns · {task.get('stop_reason') or 'no stop recorded'} · Init: {modes.get('init_delivery', 'unknown')}"
            + ("\n" + task_budget_summary(task) if (task.get("budgets") or {}).get("enabled") else "")
            + ("\n" + task_outcome_summary(task) if task.get("reported_outcome") else ""))
        self.refresh_contents()
        transaction = self.app.settings_transaction_last_receipt
        receipt_signature = json.dumps(transaction, sort_keys=True)
        if transaction and receipt_signature != self._settings_receipt_signature:
            self._settings_receipt_signature = receipt_signature
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.insert("1.0", json.dumps(transaction, indent=2, ensure_ascii=False)[:32000])
            self.output.configure(state="disabled")
        while not self.receipts.empty():
            result = self.receipts.get_nowait()
            self.pending = None
            self.command_status.set(f"Receipt: {result.get('status', result.get('outcome_status', 'unknown'))} · {result.get('reason', '')} · inspect details / Dashboard")
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.insert("1.0", json.dumps(result, indent=2, ensure_ascii=False)[:32000])
            self.output.configure(state="disabled")
        try:
            status, snapshot = self.app._get_control_panel_settings_snapshot()
            active = bool((status.get("runtime") or {}).get("running"))
            age = (status.get("state") or {}).get("age_seconds")
            self._fresh = active and age is not None and age <= 10
            for row in snapshot.get("settings", []):
                key, value = row["key"], row.get("value")
                if key not in self.variables:
                    continue
                shown = ("true" if value else "false") if isinstance(value, bool) else "" if value is None else str(value)
                self.observed[key] = shown
                if key not in self.dirty or force:
                    self.variables[key].set(shown)
                if self.variables[key].get() == shown:
                    self.dirty.discard(key)
                source = row.get("source") or {}
                self._readback_details[key] = f"Observed: {shown or 'unknown'} · {row.get('value_status', 'unknown')} · {source.get('path', 'unknown source')} · session" + (" · LOCKED" if row.get("locked") else "")
                if key == "execution.recording":
                    recording = (self.app.state_cache.get("continuation") or {}).get("recording") or {}
                    feed = recording.get("feed") or {}
                    self._readback_details[key] += (f" · effective {recording.get('effective_mode', 'unknown')} / {recording.get('state', 'unknown')}"
                        f" · committed {recording.get('committed_records', 0)} / queued {feed.get('queued', 0)} / dropped {feed.get('dropped', 0)}"
                        + (f" · {recording['error']}" if recording.get('error') else ""))
                self.refresh_setting_feedback(key)
            self.refresh_draft_hint()
        except (OSError, ValueError) as error:
            self._fresh = False
            self.hint.set(f"Observed settings unavailable: {error}")
        available = self._fresh and self.app.settings_transaction_pending is None
        for button in (self.preview_button, self.apply_button, self.model_apply_button):
            button.state(["!disabled"] if available else ["disabled"])
        self.rollback_button.state(["!disabled"] if available and self.app.settings_transaction_last_rollback_handle else ["disabled"])
        for button in (self.run_button, self.run_selected_button):
            button.state(["!disabled"] if self._fresh and not self.pending else ["disabled"])
        self.draw_flow()

    def draw_flow(self, force=False):
        if not hasattr(self, "graph") or not self.graph.winfo_ismapped():
            return
        model = switchboard_flow(self.app.state_cache or {}, fresh=self._fresh, level=self.level.get())
        width = max(160, self.graph.winfo_width())
        teasers = {kind: context_teaser(self.app.state_cache or {}, kind) for kind, _label, _description in CONTEXT_PARTS}
        signature = json.dumps([model, teasers], sort_keys=True), width
        if signature == self._flow_signature and not force:
            return
        self._flow_signature = signature
        wrap_packed_labels(self)
        canvas = self.graph
        canvas.delete("all")
        px = lambda value: round(value * ui_scale(self))
        self._flow_boxes = []

        def card(x, y, w, title, detail, tag, color, *, preview=False):
            pad = px(12)
            detail = str(detail)
            if preview and len(detail) > 512:
                detail = detail[:512] + "…"
            title_id = canvas.create_text(x+pad, y+pad, text=title, anchor="nw", fill=INK,
                width=max(30, w-2*pad), font=("Segoe UI Semibold", 10), tags=(tag, "flow_text"))
            detail_y = canvas.bbox(title_id)[3] + px(6)
            detail_id = canvas.create_text(x+pad, detail_y, text=detail, anchor="nw", fill=MUTED,
                width=max(30, w-2*pad), font=("Segoe UI", 9), tags=(tag, "flow_text"))
            if preview:
                if canvas.bbox(detail_id)[3]-detail_y > px(40):
                    low, high = 0, len(detail)
                    while low < high:
                        mid = (low + high + 1) // 2
                        canvas.itemconfigure(detail_id, text=detail[:mid]+"…")
                        if canvas.bbox(detail_id)[3]-detail_y <= px(40):
                            low = mid
                        else:
                            high = mid - 1
                    canvas.itemconfigure(detail_id, text=detail[:low]+"…")
            bottom = canvas.bbox(detail_id)[3] + pad
            rect = canvas.create_rectangle(x, y, x+w, bottom, fill=CARD, outline=color, width=2, tags=(tag, "flow_card"))
            canvas.tag_lower(rect)
            self._flow_boxes.append((tag, (x, y, x+w, bottom), (title_id, detail_id)))
            return bottom

        top = px(10)
        if self.level.get() == "Overview":
            columns = min(len(CONTEXT_PARTS), max(1, int(width / px(190))))
            rows = (len(CONTEXT_PARTS) + columns - 1) // columns
            columns = (len(CONTEXT_PARTS) + rows - 1) // rows
            gap = px(10)
            chip_w = (width-gap*(columns+1))/columns
            for start in range(0, len(CONTEXT_PARTS), columns):
                bottom = top
                for col, (kind, label, _description) in enumerate(CONTEXT_PARTS[start:start+columns]):
                    bottom = max(bottom, card(gap+col*(chip_w+gap), top, chip_w, label+" *", teasers[kind], "context:"+kind, PURPLE, preview=True))
                top = bottom + gap
            item = canvas.create_text(width/2, top+px(5), text="Context assembly · hover to preview; click for contents", anchor="n",
                                      width=width-px(24), fill=PURPLE, font=("Segoe UI", 9))
            top = canvas.bbox(item)[3]+px(30)

        horizontal = len(model["nodes"]) == 3 and width >= px(880)
        node_w = (width-px(240))/3 if horizontal else min(px(540), width-px(90))
        boxes = []
        y = top
        for index, node in enumerate(model["nodes"]):
            x = px(15)+index*(node_w+px(100)) if horizontal else (width-node_w)/2
            loop_text = ["↻ " + loop["label"] + ("" if loop["on"] else " · off") for loop in model["loops"] if loop["from"] == index]
            detail = node["detail"] + ("\n"+"\n".join(loop_text) if loop_text else "")
            bottom = card(x, y, node_w, node["label"], detail, f"node{index}", PURPLE if node["on"] else "#465168")
            boxes.append((x, y, x+node_w, bottom))
            if not horizontal:
                y = bottom + px(70)
        bottom = max(box[3] for box in boxes)
        for edge in model["edges"]:
            a, b = boxes[edge["from"]], boxes[edge["to"]]
            color = GREEN if edge["on"] else MUTED
            returning = edge["to"] <= edge["from"]
            if returning:
                if horizontal:
                    coords = [(a[0]+a[2])/2, a[3], (a[0]+a[2])/2, bottom+px(30), (b[0]+b[2])/2, bottom+px(30), (b[0]+b[2])/2, b[3]]
                else:
                    coords = [a[0], (a[1]+a[3])/2, px(14), (a[1]+a[3])/2, px(14), (b[1]+b[3])/2, b[0], (b[1]+b[3])/2]
                tx, ty, anchor = width/2, bottom+px(42), "n"
            elif horizontal:
                yy = min(a[3], b[3])-px(12)
                coords = [a[2], yy, b[0], yy]
                tx, ty, anchor = (a[2]+b[0])/2, yy-px(8), "s"
            else:
                coords = [width/2, a[3], width/2, b[1]]
                tx, ty, anchor = width/2+px(10), (a[3]+b[1])/2, "w"
            canvas.create_line(*coords, arrow="last", width=2, fill=color, dash=() if edge["on"] else (5, 4))
            canvas.create_text(tx, ty, text=edge["label"], fill=color, width=px(96) if horizontal and not returning else node_w/2,
                               font=("Segoe UI", 8), anchor=anchor)
        footer = canvas.create_text(width/2, bottom+px(80), text=model["status"]+" · click a node for details", anchor="n",
                                   width=width-px(24), fill=PURPLE, font=("Segoe UI", 9))
        height = canvas.bbox(footer)[3]+px(14)
        if int(float(canvas.cget("height"))) != height:
            canvas.configure(height=height)

    def graph_click(self, event):
        self.hide_init_tip()
        tags = self.graph.gettags("current")
        model = switchboard_flow(self.app.state_cache or {}, fresh=self._fresh, level=self.level.get())
        for tag in tags:
            if tag.startswith("context:"):
                self.show_contents(tag.split(":", 1)[1])
                return
            if tag.startswith("node") and tag[4:].isdigit():
                self.app.show_tab(model["nodes"][int(tag[4:])]["destination"])
                return

    def graph_hover(self, event):
        tags = self.graph.gettags("current")
        kind = next((tag.split(":", 1)[1] for tag in tags if tag.startswith("context:")), None)
        self.graph.configure(cursor="hand2" if kind or any(tag.startswith("node") for tag in tags) else "")
        if kind == self._hover_kind:
            return
        self.hide_init_tip()
        if kind:
            self.show_tip(kind, event.x_root + 12, event.y_root + 16)
