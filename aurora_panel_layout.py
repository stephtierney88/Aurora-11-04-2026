"""Presentation-only geometry, disclosure and scrolling for Aurora's Tk panel."""
from __future__ import annotations

import ctypes
import json
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk


def load_layout_preferences(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) and value.get("version") == 1 else {}
    except (OSError, ValueError):
        return {}


def save_layout_preferences(path, preferences):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".aurora-panel-layout-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({**preferences, "version": 1}, handle, indent=2)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def monitor_work_areas(fallback=(0, 0, 1280, 720)):
    """Read all monitor work areas; never change desktop display settings."""
    try:
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
        areas = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                          wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        def visit(monitor, _dc, _rect, _data):
            info = MonitorInfo()
            info.size = ctypes.sizeof(info)
            if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.work
                areas.append((bool(info.flags & 1), (r.left, r.top, r.right, r.bottom)))
            return True
        callback = callback_type(visit)
        ctypes.windll.user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
        ctypes.windll.user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
        ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
        if areas:
            return [rect for _, rect in sorted(areas, key=lambda item: not item[0])]
    except (AttributeError, OSError):
        pass
    return [fallback]


def clamp_window_geometry(saved, work_areas):
    """Keep restored windows reachable after monitor removal or resolution changes."""
    areas = work_areas or [(0, 0, 1280, 720)]
    geometry = saved if isinstance(saved, dict) else {}
    def number(key, fallback):
        value = geometry.get(key)
        return value if type(value) is int and abs(value) < 100000 else fallback
    x, y = number("x", areas[0][0] + 40), number("y", areas[0][1] + 40)
    width, height = number("width", 1600), number("height", 980)
    width, height = max(320, width), max(240, height)
    def overlap(area):
        left, top, right, bottom = area
        return max(0, min(x + width, right) - max(x, left)) * max(0, min(y + height, bottom) - max(y, top))
    area = max(areas, key=overlap)
    left, top, right, bottom = area
    width = min(width, max(320, right - left - 32))
    height = min(height, max(240, bottom - top - 64))
    return {"width": width, "height": height,
            "x": max(left + 8, min(x, right - width - 16)),
            "y": max(top + 8, min(y, bottom - height - 48))}


class ScrollablePane(ttk.Frame):
    """An independently scrolling page that never clips its required controls."""
    def __init__(self, parent, *, background, padding=10, fit_width=False, fit_height=False):
        super().__init__(parent)
        self.fit_width = fit_width
        self.fit_height = fit_height
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, bd=0,
                                yscrollincrement=20, xscrollincrement=20, takefocus=True)
        self.vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner = ttk.Frame(self.canvas, padding=padding)
        self.inner._aurora_scroll_owner = self
        self.canvas._aurora_scroll_owner = self
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._layout_after = None
        self.inner.bind("<Configure>", self._schedule_layout)
        self.canvas.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _schedule_layout(self, _event=None):
        if self._layout_after is None:
            self._layout_after = self.after_idle(self._layout)

    def _layout(self):
        self._layout_after = None
        if not self.winfo_exists():
            return
        width = self.canvas.winfo_width() if self.fit_width else max(self.canvas.winfo_width(), self.inner.winfo_reqwidth())
        height = self.canvas.winfo_height() if self.fit_height else max(self.canvas.winfo_height(), self.inner.winfo_reqheight())
        self.canvas.itemconfigure(self.window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _on_destroy(self, event):
        if event.widget is self and self._layout_after is not None:
            self.after_cancel(self._layout_after)
            self._layout_after = None

    def reveal_top(self):
        self.canvas.yview_moveto(0)
        self.canvas.xview_moveto(0)


class FlowBar(ttk.Frame):
    """Wrap controls into another row when a narrow window needs it."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.items = []
        self._pending = None
        self.bind("<Configure>", self._schedule)
        self.bind("<Destroy>", self._destroy, add="+")

    def add(self, widget):
        self.items.append(widget)
        widget.place(x=0, y=0)
        self._schedule()
        return widget

    def _schedule(self, _event=None):
        if self._pending is None:
            self._pending = self.after_idle(self._layout)

    def _layout(self):
        self._pending = None
        available = max(1, self.winfo_width())
        x, y, row_height = 0, 0, 0
        for widget in self.items:
            width = widget.winfo_reqwidth() + 6
            height = widget.winfo_reqheight() + 4
            if x and x + width > available:
                x, y, row_height = 0, y + row_height, 0
            widget.place_configure(x=x, y=y)
            x += width
            row_height = max(row_height, height)
        self.configure(height=y + row_height)

    def _destroy(self, event):
        if event.widget is self and self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None


class CollapsibleSection(ttk.Frame):
    def __init__(self, parent, title, *, expanded=True, on_change=None):
        super().__init__(parent)
        self.title, self.expanded, self.on_change = title, bool(expanded), on_change
        self.heading = ttk.Button(self, command=self.toggle, style="Quiet.TButton")
        self.heading.pack(fill="x", pady=(6, 4))
        self.body = ttk.Frame(self)
        self.set_expanded(self.expanded, remember=False)
        self.search_text = title.casefold()

    def set_expanded(self, expanded, *, remember=True):
        self.expanded = bool(expanded)
        self.heading.configure(text=("▾ " if self.expanded else "▸ ") + self.title)
        if self.expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()
        if remember and self.on_change:
            self.on_change(self.title, self.expanded)

    def toggle(self):
        self.set_expanded(not self.expanded)

    def index_labels(self):
        text = [self.title]
        pending = list(self.body.winfo_children())
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            try:
                text.append(str(widget.cget("text")))
            except tk.TclError:
                pass
        self.search_text = " ".join(text).casefold()
