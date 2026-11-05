"""Presentation-only geometry, disclosure and scrolling for Aurora's Tk panel."""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk


def ui_scale(widget):
    """Convert 96-DPI design pixels to this Tk display's pixel scale."""
    try:
        override = os.getenv("AURORA_PANEL_SCALE", "").strip()
        value = float(override) if override else float(widget.winfo_fpixels("1i")) / 96.0
        return max(1.0, min(4.0, value)) if math.isfinite(value) else 1.0
    except (ValueError, TypeError, AttributeError, tk.TclError):
        return 1.0


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


def receipt_tree_items(rows):
    """Stable presentation identities, including repeated and unidentified receipts."""
    counts = {}
    items, by_id = [], {}
    for row in rows:
        identity = tuple(row.get(key) for key in ("kind", "request_id", "client_id", "timestamp", "command_name"))
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
        occurrence = counts.get(digest, 0)
        counts[digest] = occurrence + 1
        iid = f"receipt:{digest}:{occurrence}"
        values = tuple(str(row.get(key) or fallback) for key, fallback in (
            ("timestamp", "-"), ("command_name", "UNKNOWN"), ("status", "unknown"),
            ("delivery_status", "unknown"), ("request_id", "-")))
        items.append((iid, values))
        by_id[iid] = row
    return items, by_id


def reconcile_tree_rows(tree, items):
    """Update changed cells in place; retain focus, selection and the reading row."""
    old = list(tree.get_children())
    selected, focused = tree.selection(), tree.focus()
    xview, yview = tree.xview(), tree.yview()
    top = old[min(len(old) - 1, round(yview[0] * len(old)))] if old else None
    wanted = [iid for iid, _values in items]
    wanted_set = set(wanted)
    stale = [iid for iid in old if iid not in wanted_set]
    if stale:
        tree.delete(*stale)
    current = [iid for iid in old if iid in wanted_set]
    for index, (iid, values) in enumerate(items):
        if iid not in current:
            tree.insert("", index, iid=iid, values=values)
            current.insert(index, iid)
        else:
            if tuple(str(value) for value in tree.item(iid, "values")) != values:
                tree.item(iid, values=values)
            if current[index] != iid:
                tree.move(iid, "", index)
                current.remove(iid)
                current.insert(index, iid)
    retained = tuple(iid for iid in selected if iid in wanted_set)
    if tree.selection() != retained:
        tree.selection_set(retained)
    if focused in wanted_set and tree.focus() != focused:
        tree.focus(focused)
    if xview and tree.xview()[0] != xview[0]:
        tree.xview_moveto(xview[0])
    # Stay at the latest row if already at the top; otherwise keep the same
    # receipt at the top when new rows arrive ahead of it.
    target = wanted.index(top) / len(wanted) if top in wanted_set and yview[0] > 0 else yview[0]
    if tree.yview()[0] != target:
        tree.yview_moveto(target)


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


def clamp_window_geometry(saved, work_areas, minimum=(320, 240)):
    """Keep restored windows reachable after monitor removal or resolution changes."""
    areas = work_areas or [(0, 0, 1280, 720)]
    geometry = saved if isinstance(saved, dict) else {}
    def number(key, fallback):
        value = geometry.get(key)
        return value if type(value) is int and abs(value) < 100000 else fallback
    x, y = number("x", areas[0][0] + 40), number("y", areas[0][1] + 40)
    width, height = number("width", 1600), number("height", 980)
    min_width, min_height = minimum
    width, height = max(min_width, width), max(min_height, height)
    def overlap(area):
        left, top, right, bottom = area
        return max(0, min(x + width, right) - max(x, left)) * max(0, min(y + height, bottom) - max(y, top))
    area = max(areas, key=overlap)
    left, top, right, bottom = area
    width = min(width, max(1, right - left - 32))
    height = min(height, max(1, bottom - top - 64))
    return {"width": width, "height": height,
            "x": max(left + 8, min(x, right - width - 16)),
            "y": max(top + 8, min(y, bottom - height - 48))}


def fit_popout_window(window, width, height, parent=None, *, position=None, minimum=(320, 240)):
    """Size to today's monitor work area and place using absolute coordinates."""
    areas = monitor_work_areas((0, 0, window.winfo_screenwidth(), window.winfo_screenheight()))
    saved = {"width": width, "height": height}
    if parent is not None:
        saved.update(x=parent.winfo_x() + 24, y=parent.winfo_y() + 24)
    if position is not None:
        saved.update(x=position[0], y=position[1])
    geometry = clamp_window_geometry(saved, areas, minimum)
    window.geometry(f"{geometry['width']}x{geometry['height']}")

    def place():
        if not window.winfo_exists():
            return
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.UINT]
            handle = user32.GetAncestor(window.winfo_id(), 2)
            if not user32.SetWindowPos(handle, None, geometry['x'], geometry['y'], 0, 0, 0x0015):
                raise OSError("Window placement failed")
        except (AttributeError, OSError):
            # Tk negative offsets mean distance from the right/bottom, not an
            # absolute virtual-desktop origin. Fall back to a reachable monitor.
            fallback = clamp_window_geometry(saved, [a for a in areas if a[0] >= 0 and a[1] >= 0] or [(0, 0, 1280, 720)], minimum)
            window.geometry(f"{fallback['width']}x{fallback['height']}+{max(0, fallback['x'])}+{max(0, fallback['y'])}")
    window.after_idle(place)
    return geometry


def bind_label_wrap(label, *, source=None, inset=4):
    """Wrap to allocated space without repeatedly invalidating unchanged geometry."""
    source = source or label
    def resize(event):
        width = max(24, event.width - inset)
        if int(float(label.cget("wraplength") or 0)) != width:
            label.configure(wraplength=width)
    source.bind("<Configure>", resize, add="+")
    label._aurora_auto_wrap = True
    return label


def wrap_packed_labels(parent):
    """Make fill-width explanatory labels follow their actual pane width."""
    for child in parent.winfo_children():
        if isinstance(child, (ttk.Label, tk.Label)) and not getattr(child, "_aurora_auto_wrap", False):
            try:
                if float(child.cget("wraplength") or 0) and child.winfo_manager() == "pack" and child.pack_info().get("fill") in {"x", "both"}:
                    bind_label_wrap(child)
                    child._aurora_auto_wrap = True
            except (tk.TclError, ValueError):
                pass
        wrap_packed_labels(child)


def bind_settled_repaint(widget):
    """Repair stale Windows child pixels after a resize/dock operation settles.

    Does not change text, selection, focus or scroll position. Set
    AURORA_PANEL_SETTLED_REPAINT=0 to leave native painting untouched.
    """
    if os.getenv("AURORA_PANEL_SETTLED_REPAINT", "1") == "0":
        return
    pending = None
    previous_size = None
    def repaint():
        nonlocal pending
        pending = None
        if not widget.winfo_exists() or not widget.winfo_viewable():
            return
        try:
            from ctypes import wintypes
            redraw = ctypes.windll.user32.RedrawWindow
            redraw.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT]
            redraw.restype = wintypes.BOOL
            handle = int(widget.winfo_id())
            # INVALIDATE | ERASE | ALLCHILDREN | UPDATENOW. Scoped to this
            # widget's client area; never the desktop or another process.
            if not handle or not redraw(handle, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100):
                raise OSError("Widget repaint unavailable")
        except (AttributeError, OSError):
            widget.event_generate("<Expose>", x=0, y=0, width=widget.winfo_width(), height=widget.winfo_height())
        widget._aurora_repaint_count = getattr(widget, "_aurora_repaint_count", 0) + 1
    def resized(event):
        nonlocal pending, previous_size
        if event.widget is not widget:
            return
        size = widget.winfo_width(), widget.winfo_height()
        if size == previous_size and event.type != tk.EventType.Map:
            return
        previous_size = size
        if pending is not None:
            widget.after_cancel(pending)
        pending = widget.after(80, repaint)
    def destroyed(event):
        nonlocal pending
        if event.widget is widget and pending is not None:
            widget.after_cancel(pending)
            pending = None
    widget.bind("<Configure>", resized, add="+")
    widget.bind("<Map>", resized, add="+")
    widget.bind("<Destroy>", destroyed, add="+")


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
        bind_settled_repaint(self.inner)
        self.inner._aurora_scroll_owner = self
        self.canvas._aurora_scroll_owner = self
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._layout_after = None
        self._layout_size = None
        self.inner.bind("<Configure>", self._schedule_layout, add="+")
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
        if self._layout_size != (width, height):
            self._layout_size = (width, height)
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
        self.hidden_items = set()
        self._pending = None
        self.bind("<Configure>", self._schedule)
        self.bind("<Destroy>", self._destroy, add="+")

    def add(self, widget):
        self.items.append(widget)
        widget.place(x=0, y=0)
        self._schedule()
        return widget

    def set_visible(self, widget, visible):
        if visible:
            self.hidden_items.discard(widget)
        else:
            self.hidden_items.add(widget)
            widget.place_forget()
        self._schedule()

    def _schedule(self, _event=None):
        if self._pending is None:
            self._pending = self.after_idle(self._layout)

    def _layout(self):
        self._pending = None
        available = max(1, self.winfo_width())
        x, y, row_height = 0, 0, 0
        for widget in self.items:
            if widget in self.hidden_items:
                continue
            width = widget.winfo_reqwidth() + 6
            height = widget.winfo_reqheight() + 4
            if x and x + width > available:
                x, y, row_height = 0, y + row_height, 0
            if not widget.winfo_manager() or widget.winfo_x() != x or widget.winfo_y() != y:
                widget.place_configure(x=x, y=y)
            x += width
            row_height = max(row_height, height)
        if self.winfo_reqheight() != y + row_height:
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
