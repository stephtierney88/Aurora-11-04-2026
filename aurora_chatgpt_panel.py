"""Bounded background auth/catalog tasks; authentication belongs to the user."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageTk
from aurora_chatgpt_auth import ChatGPTAuth, ChatGPTAuthError
from aurora_panel_layout import FlowBar, fit_popout_window, ui_scale


class SignInButtons(ttk.Frame):
    """Provider entry points; presentation never changes runtime auth or inference."""
    def __init__(self, parent, app, asset_root):
        super().__init__(parent)
        self.app = app
        scale = ui_scale(app)
        height, width = round(36 * scale), round(108 * scale)
        background = ttk.Style(self).lookup("TFrame", "background") or "#0b1320"
        def artwork(w, h, glyph=False):
            ratio = 3
            image = Image.new("RGBA", (w*ratio, h*ratio))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((ratio, ratio, (w-1)*ratio, (h-1)*ratio), radius=h*ratio/2,
                                   fill="white", outline="#111111", width=max(2, round(scale*ratio)))
            if glyph:
                try:
                    # Retain the supplied reference unchanged; render its black
                    # mark within the circular widget at the current display DPI.
                    with Image.open(Path(asset_root) / "aurora_openai_signin_reference.png") as source:
                        gray = ImageOps.grayscale(source)
                    bounds = gray.point(lambda value: 255 if value < 120 else 0).getbbox()
                    if bounds is None:
                        raise ValueError("Missing OpenAI mark")
                    alpha = ImageOps.invert(gray.crop(bounds))
                    side = round(h * .58 * ratio)
                    factor = side / max(alpha.size)
                    alpha = alpha.resize((round(alpha.width*factor), round(alpha.height*factor)), Image.Resampling.LANCZOS)
                    mark = Image.new("RGBA", alpha.size, "black")
                    mark.putalpha(alpha)
                    image.alpha_composite(mark, ((w*ratio-mark.width)//2, (h*ratio-mark.height)//2))
                except (OSError, ValueError):
                    return None
            return ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS), master=self)
        self.pill_image, self.openai_image = artwork(width, height), artwork(height, height, True)
        common = dict(bg=background, activebackground=background, fg="#111111", activeforeground="#111111",
                      bd=0, relief="flat", cursor="hand2", highlightthickness=2, highlightbackground=background,
                      highlightcolor="#77bbff", padx=0, pady=0, takefocus=True)
        self.sign_in = tk.Button(self, text="Sign in", image=self.pill_image, compound="center",
                                 font=("Segoe UI Semibold", 11), command=self.resume, **common)
        self.sign_in.pack(side="left", padx=(0, round(7*scale)))
        self.openai = tk.Button(self, text="Sign in with OpenAI", image=self.openai_image,
                               command=self.open_openai, **common)
        if self.openai_image is None:
            self.openai.configure(text="OpenAI", fg="white", activeforeground="white")
        self.openai.pack(side="left")
        for button in (self.sign_in, self.openai):
            button.bind("<Return>", lambda _event, target=button: target.invoke())
        self.tip = None
        self.tip_after = None
        for button, label in ((self.sign_in, "Sign in with your last provider (OpenAI by default)"),
                              (self.openai, "Sign in with OpenAI / ChatGPT")):
            button.bind("<Enter>", lambda _event, target=button, text=label: self.queue_tip(target, text))
            button.bind("<Leave>", lambda _event: self.hide_tip())
            button.bind("<FocusOut>", lambda _event: self.hide_tip())
        self.bind("<Destroy>", self.destroyed, add="+")

    def resume(self):
        # Extend only through explicit provider handlers; never evaluate a saved
        # provider name or fall back to API-key billing.
        provider = self.app.ui_preferences.get("last_signin_provider", "openai")
        handlers = {"openai": self.open_openai}
        handlers.get(provider if isinstance(provider, str) else "", self.open_openai)()

    def open_openai(self):
        self.hide_tip()
        return ChatGPTConnection.open(self.app, begin_sign_in=True)

    def queue_tip(self, target, text):
        self.hide_tip()
        def show():
            self.tip_after = None
            self.tip = tk.Toplevel(self)
            self.tip.overrideredirect(True)
            ttk.Label(self.tip, text=text, padding=7).pack()
            self.tip.update_idletasks()
            x = max(0, min(target.winfo_rootx(), self.winfo_screenwidth()-self.tip.winfo_reqwidth()-12))
            self.tip.geometry(f"+{x}+{target.winfo_rooty()+target.winfo_height()+4}")
        self.tip_after = self.after(500, show)

    def hide_tip(self):
        if self.tip_after is not None:
            self.after_cancel(self.tip_after)
            self.tip_after = None
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    def destroyed(self, event):
        if event.widget is self:
            self.hide_tip()


class ChatGPTConnection(tk.Toplevel):
    @classmethod
    def open(cls, app, *, begin_sign_in=False):
        current = getattr(app, "chatgpt_connection", None)
        if current is not None and current.winfo_exists():
            current.closing = False
            current.deiconify(); current.lift()
            if begin_sign_in:
                current.request_sign_in()
            return current
        app.chatgpt_connection = cls(app, begin_sign_in=begin_sign_in)
        return app.chatgpt_connection

    def __init__(self, app, *, begin_sign_in=False):
        super().__init__(app)
        self.title("Aurora — ChatGPT connection")
        self.app, self.auth = app, ChatGPTAuth()
        self.events, self.cancel = queue.Queue(), threading.Event()
        self.worker = None
        self.after_id = None
        self.closing = False
        self.pending_sign_in = begin_sign_in
        self.status_loaded = False
        self.operation = ""
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="ChatGPT subscription connection", style="CardTitle.TLabel").pack(anchor="w")
        explanation = ttk.Label(body, text="Own Aurora registration · no API-key fallback\nSign-in does not enable inference or change the runtime billing route.", wraplength=650)
        explanation.pack(fill="x", pady=8)
        explanation.bind("<Configure>", lambda event: explanation.configure(wraplength=max(150, event.width)))
        self.account = tk.StringVar(value="Add account")
        self.picker = ttk.Combobox(body, textvariable=self.account, state="readonly", width=55)
        self.picker.pack(fill="x")
        self.labels = {}
        buttons = FlowBar(body)
        buttons.pack(fill="x", pady=8)
        self.actions = [buttons.add(ttk.Button(buttons, text=title, command=action)) for title, action in (
            ("Continue with ChatGPT", self.login), ("Use selected account", self.select),
            ("Check models (no inference)", self.models), ("Sign out selected", self.logout))]
        buttons.add(ttk.Button(buttons, text="Cancel sign-in", command=self.cancel_sign_in))
        self.message = tk.StringVar(value="Loading local connection status…")
        label = ttk.Label(body, textvariable=self.message, wraplength=650, justify="left")
        label.pack(fill="x", pady=8)
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(150, event.width)))
        self.output = tk.Text(body, height=9, wrap="word", state="disabled", background="#101827", foreground="#d7e3f4")
        self.output.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self.destroyed, add="+")
        scale = ui_scale(app)
        fit_popout_window(self, round(680*scale), round(390*scale), parent=app)
        self.start(lambda: ("status", self.auth.status()), operation="status")
        self.poll()

    def start(self, action, *, operation="connection"):
        if self.worker and self.worker.is_alive():
            return
        self.operation = operation
        self.cancel.clear()
        for button in self.actions:
            button.state(["disabled"])
        def run():
            try:
                self.events.put(action())
            except ChatGPTAuthError as error:
                self.events.put(("message", str(error)))
            except Exception as error:
                self.events.put(("message", f"Connection operation failed ({type(error).__name__}); no API fallback."))
            finally:
                self.events.put(("done", None))
        self.worker = threading.Thread(target=run, name="aurora-chatgpt-connection", daemon=True)
        self.worker.start()

    def selected(self):
        return self.labels.get(self.account.get())

    def request_sign_in(self):
        if self.worker and self.worker.is_alive():
            # Join the initial status read, but never queue another browser flow
            # behind an already running sign-in/catalog operation.
            if self.operation == "status":
                self.pending_sign_in = True
            return
        self.pending_sign_in = True
        self.status_loaded = False
        self.start(lambda: ("status", self.auth.status()), operation="status")

    def cancel_sign_in(self):
        self.pending_sign_in = False
        self.cancel.set()

    def account_change_ready(self):
        state = self.app.state_cache or {}
        work = ((state.get("work") or {}).get("model_io") or {})
        if (state.get("modes") or {}).get("live") or work.get("active_network_calls"):
            self.message.set("Pause inference and Cancel work first; wait for model I/O to become idle before changing accounts.")
            return False
        return True

    def login(self):
        self.pending_sign_in = False
        if not self.account_change_ready():
            return
        selected = self.selected()
        def run():
            self.auth.login(selected, cancel=self.cancel, notify=lambda message: self.events.put(("message", message)))
            self.events.put(("signed_in", "openai"))
            self.events.put(("message", "Validated sign-in saved. Check models, then explicitly apply openai_chatgpt in Agent controls."))
            return "status", self.auth.status()
        self.start(run, operation="sign_in")

    def select(self):
        if not self.account_change_ready():
            return
        selected = self.selected()
        if selected:
            def run():
                self.auth.select(selected)
                return "status", self.auth.status()
            self.start(run)

    def models(self):
        def run():
            from aurora_chatgpt_transport import account_models
            account, models = account_models(self.auth)
            return "models", (account, models)
        self.message.set("Checking the active account's live catalog; no inference request.")
        self.start(run)

    def logout(self):
        if not self.account_change_ready():
            return
        selected = self.selected()
        if selected:
            def run():
                message = self.auth.logout(selected)
                self.events.put(("message", message))
                return "status", self.auth.status()
            self.start(run)

    def poll(self):
        self.after_id = None
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == "message":
                self.message.set(value)
            elif kind == "status":
                self.status_loaded = True
                self.app.chatgpt_catalog = {}
                self.labels = {f"{row['email'] or 'ChatGPT account'} · {row['id'][:8]}{' · ACTIVE' if row['id'] == value['active'] else ''}": row["id"] for row in value["accounts"]}
                self.picker.configure(values=["Add account", *self.labels])
                self.account.set(next((label for label, key in self.labels.items() if key == value["active"]), "Add account"))
                if self.message.get().startswith("Loading"):
                    self.message.set("Local connection loaded. Check models to verify access without inference.")
                self.show_text("\n".join(f"{row['id'][:8]} · connected {row['connected']} · plan grant {row['plan_enabled']}" for row in value["accounts"]) or "No Aurora ChatGPT account connected. Continue with ChatGPT to register.")
            elif kind == "signed_in":
                self.app.ui_preferences["last_signin_provider"] = value
            elif kind == "models":
                account, models = value
                self.app.chatgpt_catalog = {row["slug"]: row for row in models}
                self.show_text("Account " + account[:8] + "\n" + "\n".join(f"{row.get('display_name', row['slug'])} — {row['slug']}" for row in models))
                self.message.set("Catalog verified. Agent controls now offer these models and advertised speeds; selections stay drafts until applied.")
            elif kind == "done":
                for button in self.actions:
                    button.state(["!disabled"])
        if self.pending_sign_in and not self.closing and not (self.worker and self.worker.is_alive()):
            self.pending_sign_in = False
            if self.status_loaded:
                self.login()
        if self.closing and not (self.worker and self.worker.is_alive()):
            self.destroy()
        else:
            self.after_id = self.after(100, self.poll)

    def show_text(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def close(self):
        self.pending_sign_in = False
        self.cancel.set()
        self.closing = True
        self.message.set("Closing the owned connection operation…")
        self.withdraw()

    def destroyed(self, event):
        if event.widget is self:
            self.cancel.set()
            if self.after_id:
                self.after_cancel(self.after_id)
