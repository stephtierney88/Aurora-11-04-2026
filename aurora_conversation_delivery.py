"""Panel-session delivery evidence and a readable conversation popout.

Receipt ingestion is not provider delivery. This module never retries a send,
changes inference permissions or inserts display-only messages into AI context.
"""
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from aurora_control_plane import build_bridge_request, extract_request_identity, read_jsonl_batch
from aurora_delivery_receipts import DELIVERY_SCHEMA, TURN_PHASES, TERMINAL_PHASES
from aurora_panel_layout import FlowBar, ScrollablePane, fit_popout_window, ui_scale
from aurora_task_continuation import task_outcome_summary

PHASES = {"queued": "Queued locally", "received": "Received by runtime",
          "rejected": "Rejected by runtime", "uncertain": "Write unconfirmed",
          "preparing": "Preparing turn", "prepared": "Prepared for model",
          "submitted": "Request started", "responded": "Response received",
          "failed": "Request failed", "cancelled": "Cancelled locally", "not_sent": "Not sent"}
OUTBOX_NOTICE = "Closing this list does not cancel queued input. Cancel work stops active work, not queued messages."


def delivery_note(row):
    if row["phase"] == "responded":
        return "Usable model response received; command results are separate."
    if row["phase"] == "cancelled":
        return "Remote cancellation unconfirmed." if row.get("request_started") else "Cancelled before a request started."
    if row["phase"] in {"failed", "not_sent", "rejected"}:
        return "No successful reply confirmed; inspect before resending."
    return "Model delivery unconfirmed."


def show_main_conversation(app):
    """Bring the main conversation forward from an auxiliary window."""
    app.show_tab("Conversation")
    app.deiconify()
    app.lift()


def enable_readonly_tab_navigation(widget):
    def traverse(backward=False):
        (widget.tk_focusPrev() if backward else widget.tk_focusNext()).focus_set()
        return "break"
    widget.bind("<Tab>", lambda _event: traverse())
    widget.bind("<Shift-Tab>", lambda _event: traverse(True))


class SessionOutbox:
    """Bounded in-memory view of this panel's sends, correlated by all three IDs."""
    def __init__(self, root, *, max_rows=100, max_text=64000):
        self.path = Path(root) / "aurora_external_bridge_log.jsonl"
        self.rows, self.max_rows, self.max_text = OrderedDict(), max_rows, max_text
        self.omitted, self.revision = 0, 0
        self.error, self.discarding = "", False
        try:
            stat = self.path.stat()
            self.offset, self.file_identity = stat.st_size, f"{stat.st_dev}:{stat.st_ino}"
        except OSError:
            self.offset, self.file_identity = 0, ""

    def prepare(self, text):
        return build_bridge_request(text, source="panel_conversation", author="operator",
                                    subject="[AURORA CONVERSATION]", client_id="aurora_control_panel")

    def track(self, record, *, uncertain=False):
        identity = extract_request_identity(record)
        key = identity["request_id"]
        text = record["text"]
        self.rows[key] = {**identity, "text": text[:self.max_text], "shortened": len(text) > self.max_text,
                          "timestamp": record.get("timestamp", ""), "phase": "uncertain" if uncertain else "queued",
                          "receipt_time": "", "reason": "", "inference_request_id": "", "sequence": 0,
                          "requested_model": "", "provider_model": "", "request_started": False}
        while len(self.rows) > self.max_rows:
            self.rows.popitem(last=False)
            self.omitted += 1
        self.revision += 1

    def poll(self):
        if not self.rows:
            return
        try:
            batch = read_jsonl_batch(self.path, self.offset, file_identity=self.file_identity,
                                     discarding_record=self.discarding, max_records=64,
                                     max_bytes=256_000, max_record_bytes=128_000)
        except OSError:
            self.error = "Receipt log unavailable; delivery beyond recorded evidence is unknown."
            return
        self.error = "Receipt log changed; earlier unobserved receipts may be unavailable." if batch["reset"] else ""
        self.offset, self.file_identity, self.discarding = batch["next_offset"], batch["file_identity"], batch["discarding_record"]
        for entry in batch["entries"]:
            if entry["error"]:
                continue
            receipt = entry["record"]
            identity = extract_request_identity(receipt)
            row = self.rows.get(identity["request_id"])
            if not row or any(row[key] != identity[key] for key in ("client_id", "message_id", "request_id")):
                continue
            if receipt.get("event") == "message_model_delivery":
                phase = receipt.get("phase")
                turn_id, sequence = receipt.get("inference_request_id"), receipt.get("sequence")
                if (receipt.get("delivery_schema") != DELIVERY_SCHEMA or phase not in TURN_PHASES
                        or not isinstance(turn_id, str) or not turn_id or len(turn_id) > 512
                        or type(sequence) is not int or sequence <= row["sequence"]
                        or row["phase"] in TERMINAL_PHASES or row["phase"] == "rejected"
                        or (row["inference_request_id"] and row["inference_request_id"] != turn_id)):
                    continue
                row.update(inference_request_id=turn_id, sequence=sequence,
                           requested_model=str(receipt.get("requested_model", ""))[:200],
                           provider_model=str(receipt.get("provider_model", ""))[:200],
                           request_started=row["request_started"] or receipt.get("request_started") is True)
            elif row["phase"] not in {"queued", "uncertain"}:
                # Replayed ingestion and older logs cannot undo later evidence.
                continue
            elif receipt.get("event") == "message_rejected":
                phase = "rejected"
            elif receipt.get("event") == "message_ingested" and receipt.get("delivery_status") == "routed_as_input":
                phase = "received"
            else:
                continue
            row.update(phase=phase, receipt_time=str(receipt.get("timestamp", "")), reason=str(receipt.get("reason", ""))[:500])
            self.revision += 1

    def summary(self, *, include_text=True):
        if not self.rows:
            return ""
        row = next(reversed(self.rows.values()))
        preview = " ".join(row["text"].split())
        preview = preview[:130] + ("…" if len(preview) > 130 else "")
        caution = " Draft kept; inspect before resending." if row["phase"] == "uncertain" else ""
        detail = f": {preview}" if include_text else ""
        return f"{PHASES[row['phase']]}{detail} · {delivery_note(row)}{caution}"

    def awaiting_rows(self):
        return [row for row in self.rows.values() if row["phase"] != "responded"]


def conversation_activity(state, *, fresh=True):
    """Use exported observations; never infer a message's delivery from activity."""
    if not fresh:
        return "Runtime status is stale or unavailable. Last observed data is shown."
    if not ((state.get("processes") or {}).get("runtime") or {}).get("active"):
        return "Runtime stopped · Start runtime to receive queued messages."
    work, modes = state.get("work") or {}, state.get("modes") or {}
    model = work.get("model_io") or {}
    if model.get("active_network_calls"):
        if model.get("state") == "draining":
            return "Cancelling request · waiting for the connection to finish; remote cancellation is unconfirmed."
        return f"Thinking with {model.get('requested_model') or 'model unknown'} · {model.get('elapsed_seconds', 0)}s"
    paused = " · inference paused" if not modes.get("live") else ""
    if (work.get("commands") or {}).get("active_scopes"):
        return "Running commands" + paused
    continuation = state.get("continuation") or {}
    task = continuation.get("active_task") or {}
    if continuation.get("mode") == "bounded" and task.get("status") == "stopped":
        report = task_outcome_summary(task)
        return (report or f"Task stopped: {task.get('stop_reason', 'unknown')}") + " · new operator input starts another bounded task" + paused
    pending = len(state.get("pending_commands") or [])
    if pending:
        return f"{pending} visible command(s) awaiting review · open Pending" + paused
    if (state.get("scheduler") or {}).get("demand_capture_pending"):
        return "Waiting for a requested screenshot" + paused
    info = state.get("conversation_io") or {}
    last = str(info.get("last_model_turn_status") or "")
    if last in {"auth_error", "request_exception", "turn_exception", "skipped_invalid_image"} or last.startswith("api_error_"):
        return f"Last request failed ({last}) · inspect Runtime details" + paused
    if last == "cancelled":
        return "Last turn cancelled locally · inspect Outbox; queued input is not cancelled" + paused
    if not modes.get("live"):
        return "Inference paused · queued messages wait until Enable inference."
    queued = info.get("queued_input_count")
    if isinstance(queued, int) and queued > 0:
        return f"Waiting to process {queued} queued input(s)."
    return "Ready · send a message or request a fresh screenshot."


class AwaitingReply(ttk.Frame):
    """Bounded display-only sends; never merged into the model's conversation."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app, self.revision = app, None
        self.last_message_id = ""
        self.expanded = bool(app.ui_preferences.get("conversation_awaiting_expanded", True))
        self.columnconfigure(0, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.toggle = ttk.Button(bar, command=self.toggle_expanded)
        self.toggle.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="Inspect in Outbox", command=self.inspect_latest).grid(row=0, column=1, sticky="e")
        self.content = ttk.Frame(self)
        self.content.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.text = tk.Text(self.content, height=3, wrap="word", bg="#151f30", fg="#e1e9f5",
                            font=("Segoe UI", 10), padx=10, pady=5, state="disabled", takefocus=True)
        scroll = ttk.Scrollbar(self.content, command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("stage", foreground="#90c5ff", font=("Segoe UI Semibold", 10))
        self.text.tag_configure("attention", foreground="#ffb5aa", font=("Segoe UI Semibold", 10))
        enable_readonly_tab_navigation(self.text)
        self.refresh()

    def toggle_expanded(self):
        self.app.ui_preferences["conversation_awaiting_expanded"] = not self.expanded
        self.app.refresh_conversation_feedback()

    def inspect_latest(self):
        window = self.app.open_conversation_outbox()
        rows = self.app.conversation_outbox.awaiting_rows()
        if rows:
            key = rows[-1]["request_id"]
            window.tree.selection_set(key)
            window.tree.see(key)
            window.show_selected()

    def refresh(self):
        box = self.app.conversation_outbox
        rows = box.awaiting_rows()
        enabled = self.app.ui_preferences.get("conversation_send_feedback", True)
        self.expanded = self.app.ui_preferences.get("conversation_awaiting_expanded", True)
        if not enabled or not rows:
            self.grid_remove()
            return
        self.grid()
        self.toggle.configure(text=("▾" if self.expanded else "▸") + f" Awaiting reply ({len(rows)})")
        self.content.grid() if self.expanded else self.content.grid_remove()
        if self.revision == box.revision:
            return
        bottom, position = self.text.yview()[1] >= .98, self.text.yview()[0]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for index, row in enumerate(rows):
            if index:
                self.text.insert("end", "\n")
            attention = row["phase"] in {"failed", "cancelled", "not_sent", "rejected", "uncertain"}
            self.text.insert("end", PHASES[row["phase"]] + " · ", "attention" if attention else "stage")
            preview = " ".join(row["text"].split())
            self.text.insert("end", preview[:400] + ("…" if len(preview) > 400 else ""))
        self.text.configure(state="disabled")
        latest = rows[-1]["request_id"]
        self.text.see("end") if bottom or latest != self.last_message_id else self.text.yview_moveto(position)
        self.last_message_id = latest
        self.revision = box.revision


class OutboxWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.revision = app, None
        self.title("Aurora · Messages sent this session")
        scale = ui_scale(app)
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        body.rowconfigure(3, weight=1)
        self.info = tk.StringVar()
        label = ttk.Label(body, textvariable=self.info, wraplength=round(640*scale))
        label.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(100, event.width)))
        actions = FlowBar(body)
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        actions.add(ttk.Button(actions, text="Copy selected to main draft", command=self.copy_draft))
        actions.add(ttk.Button(actions, text="Main conversation", command=lambda: show_main_conversation(app)))
        rows = ttk.Frame(body)
        rows.grid(row=2, column=0, sticky="nsew")
        style = ttk.Style(self)
        style.configure("Outbox.Treeview", rowheight=round(25*scale))
        self.tree = ttk.Treeview(rows, columns=("status", "preview"), show="headings", height=5, style="Outbox.Treeview", selectmode="browse")
        self.tree.heading("status", text="Recorded state")
        self.tree.heading("preview", text="Message")
        self.tree.column("status", width=round(160*scale), minwidth=round(100*scale), stretch=False)
        self.tree.column("preview", width=round(400*scale), minwidth=round(100*scale))
        scroll = ttk.Scrollbar(rows, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.show_selected)
        self.details = tk.Text(body, height=8, wrap="word", bg="#151f30", fg="#e1e9f5", font=("Segoe UI", 10), state="disabled", padx=10, pady=8)
        self.details.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        detail_scroll = ttk.Scrollbar(body, command=self.details.yview)
        detail_scroll.grid(row=3, column=1, sticky="ns", pady=(8, 0))
        self.details.configure(yscrollcommand=detail_scroll.set)
        enable_readonly_tab_navigation(self.details)
        self.notice = tk.StringVar(value=OUTBOX_NOTICE)
        notice = ttk.Label(body, textvariable=self.notice, wraplength=round(640*scale))
        notice.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        notice.bind("<Configure>", lambda event: notice.configure(wraplength=max(100, event.width)))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.minsize(round(500*scale), round(360*scale))
        fit_popout_window(self, round(720*scale), round(510*scale), parent=app)
        self.refresh()

    def refresh(self):
        box = self.app.conversation_outbox
        self.info.set(f"This panel session: {len(box.rows)} shown; {box.omitted} earlier entries omitted. Stages track each input's initial turn, not later history reuse. Request started is not proof of a reply.\n" + box.error)
        if self.revision == box.revision:
            return
        selected = self.tree.selection()
        old = set(self.tree.get_children())
        for key, row in box.rows.items():
            values = (PHASES[row["phase"]], " ".join(row["text"].split())[:180])
            self.tree.item(key, values=values) if key in old else self.tree.insert("", "end", iid=key, values=values)
        for key in old - set(box.rows):
            self.tree.delete(key)
        if not selected and box.rows:
            key = next(reversed(box.rows))
            self.tree.selection_set(key)
            self.tree.see(key)
        self.show_selected()
        self.revision = box.revision

    def show_selected(self, _event=None):
        if _event is not None:
            self.notice.set(OUTBOX_NOTICE)
        selected = self.tree.selection()
        row = self.app.conversation_outbox.rows.get(selected[0]) if selected else None
        text = "Select a message to inspect its text and receipt identity."
        if row:
            text = f"{PHASES[row['phase']]} · {row['timestamp']}\nRequest: {row['request_id']}\nMessage: {row['message_id']}\nClient: {row['client_id']}\nReceipt: {row['receipt_time'] or 'not observed'}\n{row['reason']}\n\n{row['text']}"
            text = (f"{delivery_note(row)}\nTurn: {row['inference_request_id'] or 'not observed'}\n"
                    f"Requested model: {row['requested_model'] or 'not observed'} · Provider model: {row['provider_model'] or 'not reported'}\n" + text)
            if row["shortened"]:
                text += "\n[Display shortened; full submitted text remains in the external inbox file.]"
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def copy_draft(self):
        selected = self.tree.selection()
        row = self.app.conversation_outbox.rows.get(selected[0]) if selected else None
        if not row:
            return
        if row["shortened"]:
            self.notice.set("This display is shortened; inspect the full external inbox record before composing a new message.")
        elif self.app.conversation_composer.get("1.0", "end-1c").strip():
            self.notice.set("Your existing main draft was kept. Clear it first or copy selected text manually.")
        else:
            self.app.conversation_composer.insert("1.0", row["text"])
            self.notice.set("Copied to the main draft only. Sending again can duplicate a previously accepted message.")
            show_main_conversation(self.app)


class ConversationPopout(tk.Toplevel):
    """Current view with an independent, retained draft; no legacy-strip mutation."""
    def __init__(self, app):
        super().__init__(app)
        self.app, self.revision = app, None
        self.title("Aurora · Conversation")
        scale = ui_scale(app)
        self.page = ScrollablePane(self, background="#0b1220", padding=14, fit_width=True)
        self.page.pack(fill="both", expand=True)
        body = self.page.inner
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1, minsize=round(120*scale))
        self.caption = tk.StringVar()
        ttk.Label(body, text="Conversation", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        caption = ttk.Label(body, textvariable=self.caption, wraplength=round(740*scale))
        caption.grid(row=1, column=0, sticky="ew", pady=6)
        caption.bind("<Configure>", lambda event: caption.configure(wraplength=max(100, event.width)))
        actions = FlowBar(body)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for label, callback in (("Main view", lambda: show_main_conversation(app)),
                                ("View options", app.conversation_navigator.open_settings),
                                ("Outbox", app.open_conversation_outbox), ("Legacy chat strip", app.toggle_chat_head_request),
                                ("Pause inference", lambda: app.send_raw("SET_LIVE_MODE(off)")),
                                ("Cancel work", lambda: app.send_raw("CANCEL_ACTIVE_WORK()"))):
            actions.add(ttk.Button(actions, text=label, command=callback))
        transcript = ttk.Frame(body)
        transcript.grid(row=3, column=0, sticky="nsew")
        self.text = tk.Text(transcript, wrap="word", bg="#151f30", fg="#e1e9f5", font=("Segoe UI", 11), height=4, state="disabled", padx=12, pady=10)
        scroll = ttk.Scrollbar(transcript, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("user_role", foreground="#77bbff", font=("Segoe UI Semibold", 11))
        self.text.tag_configure("assistant_role", foreground="#83d5b4", font=("Segoe UI Semibold", 11))
        enable_readonly_tab_navigation(self.text)
        status = ttk.Label(body, textvariable=app.conversation_activity_var, wraplength=round(740*scale))
        status.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        status.bind("<Configure>", lambda event: status.configure(wraplength=max(100, event.width)))
        self.composer = tk.Text(body, height=3, wrap="word", bg="#151f30", fg="#e1e9f5", insertbackground="#e1e9f5", font=("Segoe UI", 11), padx=10, pady=8)
        self.awaiting = AwaitingReply(body, app)
        self.awaiting.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        self.composer.grid(row=6, column=0, sticky="ew")
        self.composer.bind("<Control-Return>", lambda event: app.send_conversation_message(event, composer=self.composer))
        self.composer.bind("<FocusIn>", lambda _event: self.page.canvas.yview_moveto(1))
        self.send = ttk.Button(body, text="Send message · Ctrl+Enter", command=lambda: app.send_conversation_message(composer=self.composer))
        self.send.grid(row=7, column=0, sticky="w", pady=6)
        feedback = ttk.Label(body, textvariable=app.conversation_delivery_var, wraplength=round(740*scale))
        feedback.grid(row=8, column=0, sticky="ew")
        feedback.bind("<Configure>", lambda event: feedback.configure(wraplength=max(100, event.width)))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.minsize(round(500*scale), round(420*scale))
        fit_popout_window(self, round(820*scale), round(650*scale), parent=app)

    def refresh(self, content):
        self.awaiting.refresh()
        self.caption.set(self.app.conversation_mode_var.get() + " · " + self.app.conversation_status_var.get())
        if content == self.revision:
            return
        bottom, position = self.text.yview()[1] >= .98, self.text.yview()[0]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        for tag in ("user_role", "assistant_role"):
            ranges = self.app.conversation_text.tag_ranges(tag)
            for start, end in zip(ranges[::2], ranges[1::2]):
                self.text.tag_add(tag, str(start), str(end))
        self.text.configure(state="disabled")
        self.text.see("end") if bottom else self.text.yview_moveto(position)
        self.revision = content
