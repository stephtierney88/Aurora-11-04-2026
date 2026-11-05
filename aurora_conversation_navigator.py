"""Presentation-only conversation minimap, metadata controls and context estimates."""
from __future__ import annotations

import tkinter as tk
import time
from tkinter import ttk, font as tkfont

from aurora_conversation import (VIEW_MODES, conversation_text, estimate_model_windows,
                                 select_conversation_rows)
from aurora_panel_layout import FlowBar, ScrollablePane, fit_popout_window, ui_scale, bind_settled_repaint
from aurora_history_controls import build_update_message_command
from aurora_control_plane import journal_offsets, wait_for_command_receipt

BG, CARD, TEXT, MUTED = "#0b1320", "#151f30", "#e1e9f5", "#a0b0c6"
BLUE, RED, GREEN, AMBER = "#77bbff", "#b86570", "#83d5b4", "#d8bb77"


class MessageEditor(tk.Toplevel):
    """One revision-checked mutation; show receipt truth without replaying on timeout."""
    def __init__(self, app, row, *, root, send):
        super().__init__(app)
        self.row, self.root_path, self.send = dict(row), root, send
        self.receipt, self._poll_after = None, None
        self.title("Aurora · Edit / pin message")
        scale = ui_scale(app)
        self.minsize(round(420*scale), round(330*scale))
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(body, text="Edit this retained message", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        details = ttk.Label(body, text="Sent from " + (row.get("model") or row.get("created_by") or row.get("role", "unknown")) + " · " + (row.get("timestamp_iso") or row.get("timestamp", "")), wraplength=500)
        details.grid(row=1, column=0, sticky="ew", pady=8)
        details.bind("<Configure>", lambda e: details.configure(wraplength=max(100,e.width)))
        area = ttk.Frame(body)
        area.grid(row=2, column=0, sticky="nsew")
        self.text = tk.Text(area, wrap="word", bg=CARD, fg=TEXT, insertbackground=TEXT, width=30, height=8, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(area, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", row["text"])
        self.pin = tk.BooleanVar(self, value=bool(row.get("pinned")))
        self.pin_control = ttk.Checkbutton(body, text="Pinned in retained context", variable=self.pin)
        self.pin_control.grid(row=3, column=0, sticky="w", pady=10)
        self.managed = row.get("exemption") not in {None, "", "None", "Pinned"}
        if self.managed:
            self.pin_control.state(["disabled"])
        self.status = tk.StringVar(self, value="Changes affect future context. Pins still follow configured budgets. Author is preserved; applying cancels stale model work.")
        status = ttk.Label(body, textvariable=self.status, wraplength=500)
        status.grid(row=4, column=0, sticky="ew", pady=6)
        status.bind("<Configure>", lambda e: status.configure(wraplength=max(100,e.width)))
        actions = FlowBar(body)
        actions.grid(row=5, column=0, sticky="ew", pady=8)
        self.apply_button = actions.add(ttk.Button(actions, text="Apply edit / pin", command=self.apply))
        actions.add(ttk.Button(actions, text="Close", command=self.destroy))
        self.bind("<Destroy>", self._closed, add="+")
        fit_popout_window(self, round(680*scale), round(560*scale), app)

    def _closed(self, event):
        if event.widget is self and self._poll_after is not None:
            self.after_cancel(self._poll_after)
            self._poll_after = None

    def apply(self):
        if self._poll_after is not None or self.receipt is not None:
            return
        try:
            command = build_update_message_command(self.row, self.text.get("1.0", "end-1c"),
                "keep" if self.managed else "on" if self.pin.get() else "off")
            self.offsets = journal_offsets(self.root_path)
            self.request = self.send(command)
            if not self.request.get("request_id"):
                raise ValueError("No request identity returned")
        except Exception as error:
            self.status.set(f"Submission unconfirmed: {error}. Draft kept; inspect history before retrying.")
            self.apply_button.state(["disabled"])
            return
        self.apply_button.state(["disabled"])
        self.text.configure(state="disabled")
        self.pin_control.state(["disabled"])
        self.status.set("Queued. Waiting for the runtime's edit receipt…")
        self.deadline = time.monotonic() + 20
        self._poll_after = self.after(200, self.poll)

    def poll(self):
        self._poll_after = None
        try:
            receipt = wait_for_command_receipt(self.root_path, self.request["request_id"],
                client_id=self.request.get("client_id", ""), offsets=self.offsets, timeout_seconds=0)
        except Exception as error:
            self.status.set(f"Receipt unavailable: {error}. Outcome unknown; inspect before retrying.")
            return
        if receipt.get("terminal"):
            self.receipt = receipt
            results = receipt.get("history_command_results", [])
            result = results[-1] if results else {}
            self.status.set("Applied. The conversation will refresh; reopen to make another change." if result.get("success") else
                "Not applied: " + str(result.get("reason") or receipt.get("reason") or receipt.get("status", "unknown")))
        elif time.monotonic() >= self.deadline:
            self.status.set("Receipt not received. Outcome unknown; inspect the conversation before retrying. No automatic retry.")
        else:
            self._poll_after = self.after(250, self.poll)


class ConversationNavigator(ttk.Frame):
    """Own one transcript and one mini viewer; detaching never duplicates the transcript."""
    def __init__(self, parent, *, preferences, mode, system, times, models, edits, on_change):
        super().__init__(parent)
        self.scale = ui_scale(self)
        self.px = lambda value: max(1, round(value * self.scale))
        self.map_font = tkfont.Font(self, family="Segoe UI", size=8)
        self.preferences, self.mode, self.system = preferences, mode, system
        self.times, self.models, self.edits, self.on_change = times, models, edits, on_change
        self.metadata = tk.BooleanVar(self, value=preferences.get("conversation_metadata", True))
        self.send_feedback = tk.BooleanVar(self, value=preferences.get("conversation_send_feedback", True))
        self.legacy_popout = tk.BooleanVar(self, value=preferences.get("legacy_chat_popout", False))
        self.commands = tk.BooleanVar(self, value=preferences.get("conversation_commands", False))
        self.mini_mode = tk.StringVar(self, value=preferences.get("conversation_mini_mode", "Overview history"))
        self.mini_style = tk.StringVar(self, value=preferences.get("conversation_mini_style", "Readable text"))
        self.preview_font = tkfont.Font(self, family="Segoe UI", size=10)
        saved_budgets = preferences.get("conversation_model_budgets", {})
        self.budgets = dict(saved_budgets) if isinstance(saved_budgets, dict) else {}
        self.snapshot, self.rows, self.map_rows, self.line_ranges = {}, [], [], {}
        self.selected_message_id = None
        self.popout = self.settings = self.mini = None
        self._draw_after = None
        self.side = preferences.get("conversation_mini_side", "right")
        if self.side not in {"left", "right"}:
            self.side = "right"
        self.collapsed = bool(preferences.get("conversation_mini_collapsed", False))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.main = ttk.Frame(self)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.text = tk.Text(self.main, bg=CARD, fg=TEXT, wrap="word", relief="flat", padx=14, pady=12,
                            height=2, width=20, font=("Segoe UI", 11), state="disabled")
        self.scrollbar = ttk.Scrollbar(self.main, command=self.text.yview)
        self.text.configure(yscrollcommand=self._scrolled)
        self.scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("user_role", foreground=BLUE, font=("Segoe UI Semibold", 11), spacing1=8)
        self.text.tag_configure("assistant_role", foreground=GREEN, font=("Segoe UI Semibold", 11), spacing1=8)
        self.text.bind("<Configure>", lambda _event: self.schedule_draw())
        bind_settled_repaint(self.text)
        self.text.bind("<Button-1>", self.select_message, add="+")
        self.text.tag_configure("selected_message", background="#23364c")
        self._revision = None
        self._build_mini(self)
        self.bind("<Destroy>", self._destroyed, add="+")

    def _destroyed(self, event):
        if event.widget is self:
            if self._draw_after is not None:
                self.after_cancel(self._draw_after)
                self._draw_after = None
            for window in (self.popout, self.settings):
                if window is not None and window.winfo_exists():
                    window.destroy()

    def _scrolled(self, first, last):
        self.scrollbar.set(first, last)
        self.schedule_draw()

    def select_message(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        self.selected_message_id = next((key for key, (start, end) in self.line_ranges.items()
            if self.text.compare(start, "<=", index) and self.text.compare(index, "<=", end)), None)
        self.highlight_selection()

    def highlight_selection(self):
        self.text.tag_remove("selected_message", "1.0", "end")
        if self.selected_message_id in self.line_ranges:
            self.text.tag_add("selected_message", *self.line_ranges[self.selected_message_id])

    def selected_message(self):
        return next((row for row in self.rows if row["message_id"] == self.selected_message_id), None)

    def schedule_draw(self):
        if self._draw_after is None and self.winfo_exists():
            self._draw_after = self.after_idle(self.draw)

    def _build_mini(self, parent):
        if self.mini is not None:
            self.mini.destroy()
        self.mini = ttk.Frame(parent, padding=(4, 0))
        if parent is self:
            self.mini.grid(row=0, column=0 if self.side == "left" else 2,
                           sticky="nw" if self.collapsed and self.side == "left" else "nsew", padx=3)
        else:
            self.mini.pack(fill="both", expand=True)
        if self.collapsed:
            ttk.Button(self.mini, text="↓ Mini viewer" if self.side == "left" else "◀", width=13 if self.side == "left" else 3,
                       command=self.toggle_collapse).pack(anchor="n")
            self.canvas = None
            return
        header = ttk.Frame(self.mini)
        header.pack(fill="x")
        ttk.Label(header, text="Mini viewer", font=("Segoe UI Semibold", 10)).pack(side="left")
        ttk.Button(header, text="⚙", width=3, command=self.open_settings).pack(side="right")
        ttk.Button(header, text="↑" if self.side == "left" else "▶", width=3, command=self.toggle_collapse).pack(side="right")
        bar = FlowBar(self.mini)
        self.mini_actions = bar
        bar.pack(fill="x")
        for label, callback in (("Left", lambda: self.dock("left")), ("Right", lambda: self.dock("right")),
                                ("Pop out", self.detach)):
            bar.add(ttk.Button(bar, text=label, command=callback))
        # Reserve graph space before the optional explanatory footer when the
        # transcript is shortened by expanded controls or a small window.
        self.preview_shell = ttk.Frame(self.mini)
        self.preview_shell.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.preview_shell, width=self.px(280), height=self.px(48), bg=BG, highlightthickness=0, takefocus=True)
        self._preview_visible_ids = None
        self._preview_geometry = None
        self._preview_follow_main = True
        self.mini_scrollbar = ttk.Scrollbar(self.preview_shell, command=self._mini_scroll)
        self.mini_scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.mini_scrollbar.set)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.schedule_draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<MouseWheel>", self._mini_wheel)
        self.canvas.bind("<Home>", lambda _event: self.text.yview_moveto(0))
        self.canvas.bind("<End>", lambda _event: self.text.see("end"))
        self.canvas.bind("<Prior>", lambda _event: self.text.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _event: self.text.yview_scroll(1, "pages"))
        self.hover = tk.StringVar(self, value="Click a message to jump. Hover for details.")
        self.mini_hover_label = tk.Label(self.mini, textvariable=self.hover, wraplength=self.px(230), height=2, anchor="w", justify="left",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.mini_hover_label.pack(fill="x", pady=3)
        self.mini_legend_label = tk.Label(self.mini, text="Blue: on screen · Red: excluded now\nP / V / R: estimates · ? unknown",
                 anchor="w", justify="left", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.mini_legend_label.pack(fill="x")
        self._mini_compact = None
        self.schedule_draw()

    def _remember(self):
        self.preferences.update(conversation_metadata=self.metadata.get(), conversation_commands=self.commands.get(),
            conversation_send_feedback=self.send_feedback.get(), legacy_chat_popout=self.legacy_popout.get(),
            conversation_mini_mode=self.mini_mode.get(), conversation_model_budgets=self.budgets,
            conversation_mini_style=self.mini_style.get(),
            conversation_mini_side=self.side, conversation_mini_collapsed=self.collapsed)

    def toggle_collapse(self):
        if self.popout is not None:
            self.dock("right")
        self.collapsed = not self.collapsed
        self._build_mini(self)
        self._remember()

    def dock(self, side="right"):
        self.side, self.collapsed = side, False
        # Destroy the old child before its top-level; keep the main transcript intact.
        if self.mini is not None:
            self.mini.destroy()
            self.mini = None
        if self.popout is not None:
            self.popout.destroy()
            self.popout = None
        self._build_mini(self)
        self._remember()

    def detach(self):
        if self.popout is not None:
            self.popout.lift()
            return
        self.collapsed = False
        self.popout = tk.Toplevel(self)
        self.popout.title("Aurora · Conversation mini viewer")
        fit_popout_window(self.popout, self.px(330), self.px(650), self.winfo_toplevel())
        self.popout.minsize(self.px(260), self.px(240))
        self.popout.protocol("WM_DELETE_WINDOW", lambda: self.dock("right"))
        self._build_mini(self.popout)
        self._remember()

    def open_settings(self):
        if self.settings is not None and self.settings.winfo_exists():
            self.settings.lift()
            return
        window = self.settings = tk.Toplevel(self)
        window.title("Conversation · View options")
        fit_popout_window(window, self.px(620), self.px(670), self.winfo_toplevel())
        scroll = ScrollablePane(window, background=BG, padding=14, fit_width=True)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        ttk.Label(body, text="Display only — these controls do not edit model context.", wraplength=self.px(540)).pack(anchor="w")
        app = self.winfo_toplevel()
        if hasattr(app, "show_tab"):
            ttk.Button(body, text="Inspect full context", command=lambda: app.show_tab("History Context")).pack(anchor="w", pady=(6, 0))
        positions = FlowBar(body)
        positions.pack(fill="x", pady=(6, 0))
        for label, callback in (("Dock left", lambda: self.dock('left')), ("Dock right", lambda: self.dock('right')), ("Pop out mini", self.detach)):
            positions.add(ttk.Button(positions, text=label, command=callback))
        ttk.Label(body, text="Mini viewer: blue outlines show messages on screen; red means excluded now. Model lanes are estimates; ? means unknown.", wraplength=self.px(540)).pack(anchor="w", pady=6)
        ttk.Label(body, text="Conversation view").pack(anchor="w", pady=(12, 3))
        combo = ttk.Combobox(body, textvariable=self.mode, values=VIEW_MODES, state="readonly", width=32)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda _event: self.on_change())
        for label, variable in (("Include system messages/events", self.system), ("Include commands", self.commands),
                                ("Timestamps", self.times), ("Sent from / model", self.models), ("Edited by (even the same model)", self.edits),
                                ("Pins, decay and retention details", self.metadata),
                                ("Show send status and queued-message preview", self.send_feedback),
                                ("Use legacy chat strip for the Popout chat shortcut", self.legacy_popout)):
            ttk.Checkbutton(body, text=label, variable=variable, command=self.changed).pack(anchor="w", pady=2)
        ttk.Label(body, text="Mini viewer source").pack(anchor="w", pady=(10, 3))
        appearance = ttk.Combobox(body, textvariable=self.mini_style,
                                 values=("Readable text", "Compact map (legacy)"), state="readonly")
        appearance.pack(fill="x", pady=(0, 5))
        appearance.bind("<<ComboboxSelected>>", lambda _event: (self.changed(), self.schedule_draw()))
        mini = ttk.Combobox(body, textvariable=self.mini_mode,
                           values=("Overview history", "Follow conversation") + VIEW_MODES, state="readonly")
        mini.pack(fill="x")
        mini.bind("<<ComboboxSelected>>", lambda _event: self.changed())
        ttk.Label(body, text="Model text budgets (optional)", font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(12, 3))
        ttk.Label(body, text="0 = unknown. Supply a conversation-text budget after reserving system, image/tool and output tokens. These estimates do not enforce a limit or prove what the provider saw.", wraplength=self.px(540)).pack(anchor="w")
        fields = self._budget_fields = {}
        for model in dict.fromkeys(self.snapshot.get("models", {}).values()):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=model).pack(side="left")
            variable = tk.StringVar(window, value=str(self.budgets.get(model, 0)))
            ttk.Entry(row, textvariable=variable, width=12).pack(side="right")
            fields[model] = variable
        status = tk.StringVar(window, value="Model capacities are not inferred from their names.")
        ttk.Label(body, textvariable=status, wraplength=self.px(540)).pack(anchor="w", pady=6)
        def apply():
            try:
                values = {model: int(variable.get()) for model, variable in fields.items()}
                if any(value < 0 or value > 100_000_000 for value in values.values()):
                    raise ValueError()
            except ValueError:
                status.set("Enter whole token counts between 0 and 100,000,000; nothing changed.")
                return
            self.budgets.update(values)
            self.changed()
            status.set("Display estimates updated. Runtime selection is unchanged.")
        ttk.Button(body, text="Apply text budgets", command=apply).pack(anchor="w")
        ttk.Label(body, text="SHOW_ALL: latest observed text, including removed rows.\nSHOW_ALL_IN_ORDER: first-observed text/order, before later edits.\nFULL_TRANSCRIPT: observed session events, subject to archive limits. Older missing text cannot be recovered. Historical log remains separate.", wraplength=self.px(540)).pack(anchor="w", pady=12)
        ttk.Button(body, text="Reset view defaults", command=self.reset_view).pack(anchor="w")

    def reset_view(self):
        self.preferences["conversation_awaiting_expanded"] = True
        self.send_feedback.set(True)
        self.legacy_popout.set(False)
        self.mode.set("Current context")
        self.system.set(False)
        self.commands.set(False)
        for variable in (self.times, self.models, self.edits, self.metadata):
            variable.set(True)
        self.mini_mode.set("Overview history")
        self.mini_style.set("Readable text")
        self.budgets.clear()
        for variable in getattr(self, "_budget_fields", {}).values():
            variable.set("0")
        self.dock("right")
        self.changed()

    def changed(self):
        self._remember()
        self.on_change()

    def render(self, snapshot):
        self.snapshot = snapshot
        self.rows, note = select_conversation_rows(snapshot, self.mode.get(), include_system=self.system.get(), include_commands=self.commands.get())
        blocks = [conversation_text({"rows": [row]}, show_time=self.times.get(), show_model=self.models.get(),
                  show_edits=self.edits.get(), show_metadata=self.metadata.get(), decay=snapshot.get("decay", {})) for row in self.rows]
        content = "\n\n".join(blocks) or "No messages in this view. Start the runtime or choose another view."
        revision = (content, tuple(row["message_id"] for row in self.rows))
        changed = revision != self._revision
        if changed:
            same_rows = self._revision is not None and revision[1] == self._revision[1]
            selection = self.text.tag_ranges("sel")
            at_bottom = self.text.yview()[1] >= .98
            first = self.text.index("@0,0")
            anchor = next((key for key, (start, end) in self.line_ranges.items() if self.text.compare(start, "<=", first) and self.text.compare(end, ">=", first)), None)
            position = self.text.yview()[0]
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("end", content)
            self.line_ranges, line = {}, 1
            for row, block in zip(self.rows, blocks):
                end = line + block.count("\n")
                self.line_ranges[row["message_id"]] = (f"{line}.0", f"{end}.end")
                self.text.tag_add("assistant_role" if row.get("role") == "assistant" else "user_role", f"{line}.0", f"{line}.end")
                line = end + 2
            self.text.configure(state="disabled")
            self.highlight_selection()
            if same_rows and selection:
                self.text.tag_add("sel", *selection)
            if at_bottom:
                self.text.see("end")
            elif same_rows:
                # Age/threshold labels can change without a history mutation.
                # Keep the reader's position inside a long message on refresh.
                self.text.yview_moveto(position)
            elif anchor in self.line_ranges:
                self.text.yview(self.line_ranges[anchor][0])
            else:
                self.text.yview_moveto(position)
            self._revision = revision
        mini_mode = self.mini_mode.get()
        if mini_mode == "Overview history":
            mini_mode = "SHOW_ALL" if snapshot.get("archive", {}).get("enabled") else "Retained messages"
        elif mini_mode == "Follow conversation":
            mini_mode = self.mode.get()
        map_rows, _ = select_conversation_rows(snapshot, mini_mode, include_system=self.system.get(), include_commands=self.commands.get())
        windows = estimate_model_windows(map_rows, snapshot.get("models", {}), self.budgets)
        viewable = bool(self.text.winfo_viewable())
        redraw = changed or map_rows != self.map_rows or windows != getattr(self, "windows", []) or viewable != getattr(self, "_viewable", None)
        self._viewable = viewable
        self.map_rows, self.windows = map_rows, windows
        if redraw:
            self.schedule_draw()
        return f"{len(self.rows)} messages · {note}"


    def draw(self):
        self._draw_after = None
        canvas = self.canvas
        if canvas is None or not canvas.winfo_exists():
            return
        # Keep the graph visible when expanded controls shorten the transcript.
        # All docking/legend controls remain reachable in View options.
        available = self.mini.winfo_height()
        compact = (available < self.px(210), available < self.px(125))
        if compact != self._mini_compact:
            self._mini_compact = compact
            for widget in (self.mini_hover_label, self.mini_legend_label):
                widget.pack_forget()
            if not compact[0]:
                self.mini_hover_label.pack(fill='x', pady=3)
                self.mini_legend_label.pack(fill='x')
            if compact[1]:
                self.mini_actions.pack_forget()
            else:
                self.mini_actions.pack(fill='x', before=self.preview_shell)
        canvas.delete("all")
        width, height = max(self.px(150), canvas.winfo_width()), max(self.px(32), canvas.winfo_height())
        self.hit_rows = []
        top = self.px(7)
        line_height = self.map_font.metrics("linespace") + self.px(3)
        for window in getattr(self, "windows", []) if height >= line_height * len(getattr(self, "windows", [])) + self.px(40) else []:
            label = f"{window['slot']}: {window['model']} · {window['budget'] or '?'}"
            while label and self.map_font.measure(label) > width-self.px(12):
                label = label[:-2] + "…"
            canvas.create_text(self.px(5), top, text=label, anchor="nw", fill=MUTED, font=self.map_font)
            top += line_height
        top += self.px(9)
        if not self.map_rows:
            canvas.configure(scrollregion=(0, 0, width, height))
            canvas.create_text(8, top, text="No retained history yet.", anchor="nw", fill=MUTED, width=width-16)
            return
        visible_start, visible_end = self.text.index("@0,0"), self.text.index(f"@0,{self.text.winfo_height()}")
        visible_ids = set()
        for shown in self.rows:
            bounds = self.line_ranges.get(shown["message_id"])
            if self.text.winfo_viewable() and bounds and self.text.compare(bounds[0], "<=", visible_end) and self.text.compare(bounds[1], ">=", visible_start):
                visible_ids.update((shown["message_id"], shown.get("target_id", shown["message_id"])))
        if self.mini_style.get() != "Compact map (legacy)":
            self._draw_readable(width, height, top, visible_ids)
            return
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.yview_moveto(0)
        self._preview_visible_ids = None
        weights = [max(1, min(12, row.get("text", "").count("\n") + len(row.get("text", "")) // 100 + 1)) for row in self.map_rows]
        scale = max(self.px(12), height-top-self.px(5)) / sum(weights)
        y, lanes = top, min(4, len(getattr(self, "windows", [])))
        for row, weight in zip(self.map_rows, weights):
            bottom = y + weight * scale
            key = row["message_id"]
            visible = key in visible_ids
            color = GREEN if row.get("in_current") else RED if row.get("in_current") is False else "#536073"
            canvas.create_rectangle(self.px(6), y, width-self.px(14+lanes*10), max(y+1, bottom-1), fill=color, outline="")
            # Small text strokes preserve the editor-minimap feel without tiny unreadable glyphs.
            if bottom-y > self.px(7):
                canvas.create_line(self.px(10), y+self.px(3), min(width-self.px(20+lanes*10), self.px(18)+len(row.get("text", "")) % max(20, int(width-self.px(60)))), y+self.px(3), fill=CARD)
            for i, window in enumerate(getattr(self, "windows", [])[:lanes]):
                fits = window["fits"].get(key)
                lane_color = "#536073" if fits is None else GREEN if fits else AMBER
                x = width-self.px(10+(lanes-i)*10)
                canvas.create_rectangle(x, y, x+self.px(6), max(y+1, bottom-1), fill=lane_color, outline="")
            if visible:
                canvas.create_rectangle(self.px(3), y, width-self.px(3), max(y+2, bottom), outline=BLUE, width=self.px(2), tags=("viewport",))
            self.hit_rows.append((y, bottom, row))
            y = bottom

    def _preview_lines(self, text, width, limit=3):
        """Bound a preview by measured glyph width, including long unbroken text."""
        lines, line = [], ""
        for char in " ".join(str(text).split()):
            if line and self.preview_font.measure(line + char) > width:
                split = line.rfind(" ")
                lines.append(line[:split] if split > 0 else line.rstrip())
                line = line[split+1:] if split > 0 else ""
                if len(lines) == limit:
                    while lines[-1] and self.preview_font.measure(lines[-1] + "…") > width:
                        lines[-1] = lines[-1][:-1]
                    lines[-1] += "…"
                    break
            line += char
        else:
            if line:
                lines.append(line)
        return "\n".join(lines) or "[No text]"

    def _draw_readable(self, width, height, top, visible_ids):
        canvas, y = self.canvas, top
        lanes = min(4, len(getattr(self, "windows", [])))
        right = width - self.px(14 + lanes * 8)
        text_width = max(self.px(50), right - self.px(22))
        line_height = self.preview_font.metrics("linespace")
        visible_y = None
        for row in self.map_rows:
            key = row["message_id"]
            excluded = row.get("in_current") is False
            color = RED if excluded else GREEN if row.get("in_current") else MUTED
            label = row.get("role", "unknown").title()
            if row.get("pinned"):
                label += " · Pinned"
            if excluded:
                label += " · outside context"
            label = self._preview_lines(label, text_width, 1)
            preview = self._preview_lines(row.get("text", ""), text_width)
            bottom = y + (preview.count("\n") + 2) * line_height + self.px(16)
            canvas.create_rectangle(self.px(5), y, right, bottom-self.px(3), fill=CARD, outline=color)
            canvas.create_text(self.px(12), y+self.px(5), text=label, anchor="nw", fill=color,
                               font=self.preview_font, tags=("preview_heading",))
            canvas.create_text(self.px(12), y+self.px(7)+line_height, text=preview, anchor="nw", fill=TEXT,
                               font=self.preview_font, tags=("preview_text",))
            for i, window in enumerate(getattr(self, "windows", [])[:lanes]):
                fits = window["fits"].get(key)
                lane_color = MUTED if fits is None else GREEN if fits else AMBER
                x = right+self.px(5+i*8)
                canvas.create_rectangle(x, y, x+self.px(4), bottom-self.px(3), fill=lane_color, outline="")
            if key in visible_ids:
                if visible_y is None:
                    visible_y = y
                canvas.create_rectangle(self.px(2), y, width-self.px(2), bottom-self.px(2),
                                        outline=BLUE, width=self.px(2), tags=("viewport",))
            self.hit_rows.append((y, bottom, row))
            y = bottom + self.px(4)
        extent = max(height, y)
        canvas.configure(scrollregion=(0, 0, width, extent))
        # Follow main-conversation movement, but keep independent mini scrolling
        # stable during refreshes and hover/click redraws.
        visible_changed = visible_ids != getattr(self, "_preview_visible_ids", None)
        geometry_changed = (width, height, extent) != getattr(self, "_preview_geometry", None)
        if visible_changed:
            self._preview_follow_main = True
        # A newly docked canvas can draw once at width/height 1 before Tk settles.
        # Resizing changes card heights and the scroll extent even if the main
        # visible IDs stay the same. Re-anchor until the user scrolls this viewer.
        if visible_y is not None and (visible_changed or (geometry_changed and self._preview_follow_main)):
            canvas.yview_moveto(max(0, visible_y-self.px(4)) / extent)
        self._preview_visible_ids = visible_ids
        self._preview_geometry = (width, height, extent)

    def _mini_scroll(self, *args):
        self._preview_follow_main = False
        self.canvas.yview(*args)

    def _mini_wheel(self, event):
        if self.mini_style.get() != "Compact map (legacy)":
            self._preview_follow_main = False
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

    def _row_at(self, y):
        y = self.canvas.canvasy(y)
        return next((row for top, bottom, row in getattr(self, "hit_rows", []) if top <= y <= bottom), None)

    def _hover(self, event):
        row = self._row_at(event.y)
        if row:
            text = conversation_text({"rows": [row]}, show_metadata=True, decay=self.snapshot.get("decay", {}))
            self.hover.set(text[:280].replace("\n", " "))
        else:
            self.hover.set(" · ".join(f"{w['slot']}: {w['model']} ({w['budget'] or '?'} text tokens)" for w in getattr(self, "windows", [])))

    def _click(self, event):
        row = self._row_at(event.y)
        if not row:
            return
        key = row["message_id"]
        if key not in self.line_ranges:
            self.mode.set("SHOW_ALL_FULL_TRANSCRIPT" if key.startswith("event:") else "SHOW_ALL" if self.snapshot.get("archive", {}).get("enabled") else "Retained messages")
            self.on_change()
        if key in self.line_ranges:
            self.text.see(self.line_ranges[key][0])
            self.text.yview(self.line_ranges[key][0])
            self.schedule_draw()
