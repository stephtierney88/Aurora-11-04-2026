"""Compact operator controls; mutations use the existing settings/command authority."""
import json
import datetime
import time
import tkinter as tk
from tkinter import ttk

from aurora_panel_layout import CollapsibleSection, FlowBar, ScrollablePane, ui_scale
from aurora_settings_registry import coerce_setting_value, build_settings_snapshot
from aurora_task_continuation import task_outcome_summary, task_budget_summary


EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
CONTROL_KEYS = ("model.text", "model.vision", "model.reasoning", "inference.reasoning_effort",
                "inference.service_tier", "capture.mode", "scheduler.mode", "scheduler.heartbeat_seconds", "auth.mode", "runtime.assistant_policy", "runtime.execution",
                "task.continuation_mode", "task.max_model_turns", "task.max_seconds", "task.outcome_reporting", "scheduler.readback_wake_enabled", "context.init_delivery")
BUDGET_KEYS = ("task.max_commands", "task.max_reported_tokens", "task.unknown_usage_policy")
CARRY_KEYS = ("task.plan_carry_policy", "task.pending_carry_policy")
CONTROL_KEYS += BUDGET_KEYS + CARRY_KEYS
CONTINUATION_KEYS = ("task.continuation_mode", "task.max_model_turns", "task.max_seconds", "task.outcome_reporting", "scheduler.readback_wake_enabled", "context.init_delivery") + BUDGET_KEYS + CARRY_KEYS


def model_command(model, effort, tier="regular"):
    """Use the reviewed next-inference parser; model IDs cannot inject commands."""
    from aurora_command_contracts import normalize_next_inference_pairs
    plan = normalize_next_inference_pairs({"model": model, "reasoning_effort": effort, "service_tier": tier})
    if not plan:
        raise ValueError("Choose a model or reasoning effort first.")
    return "SET_NEXT_INFERENCE(" + "; ".join(f"{key}={json.dumps(value)}" for key, value in plan.items()) + ")"


class AgentControls(CollapsibleSection):
    def __init__(self, parent, app):
        self.app = app
        super().__init__(parent, "Agent controls", expanded=app.ui_preferences.get("sections", {}).get("Agent controls", False),
                         on_change=app._remember_section)
        self.variables = {key: tk.StringVar() for key in CONTROL_KEYS}
        self.observed, self.dirty, self.selectors = {}, set(), {}
        self._syncing = False
        self.scope = tk.StringVar(value="Next turn only")
        self.summary = tk.StringVar(value="Waiting for observed runtime state.")
        self.feedback = tk.StringVar(value="Choose Next turn only for a temporary override; Hold changes session defaults.")
        self.receipt_summary = tk.StringVar(value="Draft controls; changes require Apply.")
        pane = ScrollablePane(self.body, background="#0b1320", padding=8, fit_width=True)
        pane.configure(height=round(135 * ui_scale(app)))
        pane.pack(fill="x")
        pane.grid_propagate(False)
        self.pane = pane
        content = pane.inner
        summary = ttk.Label(content, textvariable=self.summary, style="Muted.TLabel", justify="left", wraplength=850)
        summary.pack(fill="x", pady=(0, 6))
        summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(120, event.width)))
        models = FlowBar(content)
        models.pack(fill="x")
        self._select(models, "Primary", "model.text", (), 23)
        self._select(models, "Vision", "model.vision", (), 23)
        self._select(models, "Review / on call", "model.reasoning", (), 23)
        self.hold_models_button = models.add(ttk.Button(models, text="Hold model slots", command=self.hold_models))
        reasoning = FlowBar(content)
        reasoning.pack(fill="x", pady=5)
        reasoning.add(ttk.Label(reasoning, text="Primary effort"))
        self.effort_combo = reasoning.add(ttk.Combobox(reasoning, textvariable=self.variables["inference.reasoning_effort"], values=EFFORTS, state="readonly", width=9))
        self.dial = tk.DoubleVar(value=2)
        self.effort_slider = reasoning.add(ttk.Scale(reasoning, from_=0, to=len(EFFORTS)-1, length=round(110*ui_scale(app)), variable=self.dial, command=self.slide_effort))
        reasoning.add(ttk.Combobox(reasoning, textvariable=self.scope, values=("Next turn only", "Hold for session"), state="readonly", width=19))
        self.apply_button = reasoning.add(ttk.Button(reasoning, text="Apply primary + effort", command=self.apply_primary))
        self.clear_button = reasoning.add(ttk.Button(reasoning, text="Clear next turn", command=lambda: self.command("CLEAR_NEXT_INFERENCE()")))
        self._select(reasoning, "Speed", "inference.service_tier", ("regular",), 10)
        reasoning.add(ttk.Button(reasoning, text="Speed info", command=self.speed_info))
        flow = FlowBar(content)
        flow.pack(fill="x", pady=5)
        self._select(flow, "Screenshots", "capture.mode", ("request_only", "heartbeat"), 13)
        self._select(flow, "Turn trigger", "scheduler.mode", ("event", "hybrid", "per_capture"), 11)
        flow.add(ttk.Label(flow, text="Turn seconds (0 = off)"))
        flow.add(ttk.Entry(flow, textvariable=self.variables["scheduler.heartbeat_seconds"], width=7))
        self._select(flow, "Assistant policy", "runtime.assistant_policy", ("legacy", "task_flow"), 11)
        self._select(flow, "Execution", "runtime.execution", ("safe", "assist", "auto"), 8)
        self.flow_button = flow.add(ttk.Button(flow, text="Apply flow", command=self.apply_flow))
        self.demand_button = flow.add(ttk.Button(flow, text="Command-driven preset", command=self.demand_preset))
        self.capture_button = flow.add(ttk.Button(flow, text="Request fresh screenshot", command=lambda: self.command("REQUEST_SCREENSHOT_CAPTURE(agent_controls,0)")))
        task_section = CollapsibleSection(content, "Task continuation & prompt delivery", expanded=False)
        task_section.pack(fill="x", pady=5)
        task_bar = FlowBar(task_section.body)
        task_bar.pack(fill="x")
        self._select(task_bar, "Task mode", "task.continuation_mode", ("legacy", "bounded"), 10)
        for key, label in (("task.max_model_turns", "Model turns"), ("task.max_seconds", "Seconds")):
            task_bar.add(ttk.Label(task_bar, text=label))
            task_bar.add(ttk.Entry(task_bar, textvariable=self.variables[key], width=7))
        self._select(task_bar, "Readback follow-up", "scheduler.readback_wake_enabled", ("true", "false"), 6)
        self._select(task_bar, "Outcome reports", "task.outcome_reporting", ("false", "true"), 6)
        self._select(task_bar, "Init delivery", "context.init_delivery", ("legacy", "system_once"), 12)
        self.task_button = task_bar.add(ttk.Button(task_bar, text="Apply task controls", command=lambda: self.apply_keys(CONTINUATION_KEYS)))
        task_bar.add(ttk.Button(task_bar, text="Inspect task", command=lambda: self.command("SHOW_TASK_STATUS()")))
        carry_bar = FlowBar(task_section.body)
        carry_bar.pack(fill="x", pady=4)
        self._select(carry_bar, "Previous-task plans", "task.plan_carry_policy", ("carry", "discard_previous"), 18)
        self._select(carry_bar, "Previous-task proposals", "task.pending_carry_policy", ("carry", "hold_previous", "discard_previous"), 18)
        carry_bar.add(ttk.Button(carry_bar, text="Apply carry policies", command=lambda: self.apply_keys(CARRY_KEYS)))
        budget_section = CollapsibleSection(task_section.body, "Optional command/token budgets (0 = off)", expanded=False)
        budget_section.pack(fill="x", pady=4)
        budget_bar = FlowBar(budget_section.body)
        budget_bar.pack(fill="x")
        for key, label in (("task.max_commands", "Commands"), ("task.max_reported_tokens", "Reported tokens")):
            budget_bar.add(ttk.Label(budget_bar, text=label))
            budget_bar.add(ttk.Entry(budget_bar, textvariable=self.variables[key], width=10))
        self._select(budget_bar, "Missing usage", "task.unknown_usage_policy", ("continue", "stop"), 10)
        budget_bar.add(ttk.Button(budget_bar, text="Apply budgets", command=lambda: self.apply_keys(BUDGET_KEYS)))
        ttk.Label(budget_section.body, text="Budgets latch at the next task. Commands count reservations, not individual clicks; failures are not refunded.\nThe reported-token threshold can be exceeded by the last request. Missing usage follows the selected policy.", style="Muted.TLabel", wraplength=850).pack(fill="x", pady=4)
        self.task_status = tk.StringVar(value="Task status unknown.")
        ttk.Label(task_section.body, textvariable=self.task_status, style="Muted.TLabel", wraplength=850).pack(fill="x", pady=4)
        ttk.Label(task_section.body, text="Limits latch at task start. After a stop, new operator input starts another task. Readback follow-up requires bounded mode.\nLimits apply between operations; remote requests and already executing actions may finish later. Legacy keeps existing scheduling.", style="Muted.TLabel", wraplength=850).pack(fill="x")
        access = FlowBar(content)
        access.pack(fill="x", pady=5)
        self._select(access, "Billing / auth", "auth.mode", ("api_key", "openai_chatgpt", "codex_oauth", "auto"), 16)
        self.auth_button = access.add(ttk.Button(access, text="Apply route", command=lambda: self.apply_keys(("auth.mode",))))
        access.add(ttk.Button(access, text="Continue with ChatGPT", command=self.open_auth))
        access.add(ttk.Button(access, text="Full Switchboard", command=lambda: app.show_tab("The Switchboard")))
        access.add(ttk.Button(access, text="Reload observed", command=self.reload))
        feedback = ttk.Label(content, textvariable=self.feedback, style="Muted.TLabel", wraplength=850, justify="left")
        feedback.pack(fill="x")
        feedback.bind("<Configure>", lambda event: feedback.configure(wraplength=max(120, event.width)))
        ttk.Label(content, textvariable=self.receipt_summary, style="Muted.TLabel").pack(fill="x")
        for key, var in self.variables.items():
            var.trace_add("write", lambda *_a, key=key: self.edited(key))

    def _select(self, row, label, key, values, width):
        row.add(ttk.Label(row, text=label))
        self.selectors[key] = row.add(ttk.Combobox(row, textvariable=self.variables[key], values=values,
                                                  width=width, state="normal" if key.startswith("model.") else "readonly"))

    def edited(self, key):
        if self._syncing:
            return
        if self.variables[key].get() != self.observed.get(key, ""):
            self.dirty.add(key)
        else:
            self.dirty.discard(key)
        if key == "inference.reasoning_effort" and self.variables[key].get() in EFFORTS:
            self.dial.set(EFFORTS.index(self.variables[key].get()))

    def slide_effort(self, value):
        if not self._syncing:
            self.variables["inference.reasoning_effort"].set(EFFORTS[round(float(value))])

    def apply_keys(self, keys, *, extra=()):
        try:
            changes = [{"key": key, "value": coerce_setting_value(key, self.variables[key].get())} for key in keys]
            return self.app._submit_settings_transaction("apply", changes=changes + list(extra),
                                                        activity_label="Agent controls", inline_results=True)
        except ValueError as error:
            self.feedback.set(str(error))

    def hold_models(self):
        return self.apply_keys(("model.text", "model.vision", "model.reasoning"))

    def apply_primary(self):
        if self.scope.get() == "Hold for session":
            self.feedback.set("Holding primary/effort defaults for this runtime session. Review/dynamic policies can still select another posture; see Full Switchboard.")
            return self.apply_keys(("model.text", "inference.reasoning_effort", "inference.service_tier"))
        try:
            return self.command(model_command(self.variables["model.text"].get(), self.variables["inference.reasoning_effort"].get(), self.variables["inference.service_tier"].get() or "regular"))
        except ValueError as error:
            self.feedback.set(str(error))

    def apply_flow(self):
        return self.apply_keys(("capture.mode", "scheduler.mode", "scheduler.heartbeat_seconds", "runtime.assistant_policy", "runtime.execution"))

    def demand_preset(self):
        self.feedback.set("Command-driven: Task flow policy, requested screenshots, per-capture turns, heartbeat off. Auto execution remains a separate choice; this preset does not enable inference or Auto. Legacy policy/timing remain selectable.")
        return self.app._submit_settings_transaction("apply", changes=[
            {"key": "capture.mode", "value": "request_only"}, {"key": "capture.demand_enabled", "value": True},
            {"key": "scheduler.mode", "value": "per_capture"}, {"key": "scheduler.heartbeat_seconds", "value": 0.0},
            {"key": "runtime.assistant_policy", "value": "task_flow"}],
            activity_label="Command-driven flow", inline_results=True)

    def command(self, text):
        self.app.switchboard.update_state()
        result = self.app.switchboard.run_text(text)
        self.feedback.set(self.app.switchboard.command_status.get())
        return result

    def speed_info(self):
        self.feedback.set("regular = no acceleration; priority = Fast (increased subscription usage); ultrafast only when advertised. Use Continue with ChatGPT → Check models to refresh available tiers. Non-Regular currently requires subscription auth. Effort changes reasoning, not service priority.")

    def open_auth(self):
        from aurora_chatgpt_panel import ChatGPTConnection
        ChatGPTConnection.open(self.app)

    def reload(self):
        self.dirty.clear()
        self.update_state()

    def update_state(self):
        state = self.app.state_cache or {}
        continuation = state.get("continuation") or {}
        task = continuation.get("active_task") or {}
        self.task_status.set(f"Observed: {continuation.get('mode', 'unknown')} · {task.get('status', 'unknown')} · "
                             f"{task.get('turns', 0)}/{task.get('max_turns', '?')} model turns · "
                             f"{task.get('elapsed_seconds', 0)}s elapsed · {task.get('stop_reason') or 'no stop recorded'} · "
                             f"Outcome reports: {task.get('outcome_reporting', 'not latched')} (active task) / {continuation.get('outcome_reporting', 'unknown')} (next task)"
                             + "\n" + task_budget_summary(task)
                             + f"\nActive carry policies: plans {task.get('plan_carry_policy', 'not latched')} / proposals {task.get('pending_carry_policy', 'not latched')}"
                             + ("\n" + task_outcome_summary(task) if task.get("reported_outcome") else ""))
        models, status, modes = (state.get(key) or {} for key in ("models", "model_status", "modes"))
        choices = (state.get("model_catalog") or {}).get("choices", [])
        catalog = getattr(self.app, "chatgpt_catalog", {})
        if self.variables["auth.mode"].get() == "openai_chatgpt" and catalog:
            choices = list(catalog)
        profile = catalog.get(self.variables["model.text"].get(), {}) if self.variables["auth.mode"].get() == "openai_chatgpt" else {}
        tiers = [row["id"] for row in profile.get("service_tiers", []) if row.get("id") in {"priority", "ultrafast"}]
        self.selectors["inference.service_tier"].configure(values=["regular", *tiers])
        for key in ("model.text", "model.vision", "model.reasoning"):
            self.selectors[key].configure(values=choices)
        try:
            # The panel already loaded/decorated this snapshot. Rendering must not
            # rescan journals/processes or reread the large state file each tick.
            exported = datetime.datetime.fromisoformat(str(state.get("timestamp", "")))
            age = max(0, time.time() - exported.timestamp())
            active = bool(((state.get("processes") or {}).get("runtime") or {}).get("active"))
            fresh = active and age <= 10
            snapshot = build_settings_snapshot(state, runtime_active=active, state_age_seconds=age,
                                               state_timestamp=state.get("timestamp", ""))
            self._syncing = True
            for row in snapshot.get("settings", []):
                key = row["key"]
                if key not in self.variables:
                    continue
                shown = str(row.get("value") if row.get("value") is not None else "")
                self.observed[key] = shown
                if key not in self.dirty:
                    self.variables[key].set(shown)
                if self.variables[key].get() == shown:
                    self.dirty.discard(key)
            effort = self.variables["inference.reasoning_effort"].get()
            if effort in EFFORTS:
                self.dial.set(EFFORTS.index(effort))
        except (ValueError, OSError):
            fresh = False
        finally:
            self._syncing = False
        from aurora_switchboard import next_inference_label
        cadence = status.get("review_turn_interval", "unknown")
        cadence = "on call" if cadence == 0 else f"every {cadence} turns"
        last_tier = (status.get("subscription_receipt") or {}).get("provider_service_tier", "unknown")
        next_label = next_inference_label(state)
        plan = (state.get("planning") or {}).get("next_inference") or {}
        if next_label == "queued":
            next_label = " / ".join(str(plan[key]) for key in ("model", "reasoning_effort", "service_tier") if plan.get(key)) + f" (turn {plan.get('target_turn', '?')})"
        self.summary.set(f"Observed: primary {models.get('text', 'unknown')} / {status.get('reasoning_effort', 'unknown')} · review {models.get('reasoning', 'unknown')} ({cadence}) · dynamic {status.get('auto_dynamic_inference', 'unknown')}\n"
                         f"Next: {next_label} · {modes.get('execution', 'unknown')} / {modes.get('assistant_policy', 'unknown')} · auth {modes.get('auth', 'unknown')} · speed {models.get('service_tier', 'unknown')} requested / last provider {last_tier} · {'connected' if fresh else 'inactive / stale'} · {len(self.dirty)} draft edits")
        receipt = self.app.settings_transaction_last_receipt or {}
        self.receipt_summary.set("Waiting for runtime receipt…" if self.app.settings_transaction_pending else
            f"Last settings operation: {receipt.get('operation', 'none')} · {receipt.get('status', 'no receipt')} · Full receipt in Switchboard / Dashboard")
        if self.app.switchboard.pending:
            self.feedback.set(self.app.switchboard.command_status.get())
        available = fresh and self.app.settings_transaction_pending is None
        for button in (self.hold_models_button, self.apply_button, self.clear_button, self.flow_button, self.demand_button, self.capture_button, self.auth_button, self.task_button):
            button.state(["!disabled"] if available else ["disabled"])
