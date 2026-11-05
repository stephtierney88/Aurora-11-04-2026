"""Per-frame desktop geometry. Native queries occur only inside explicit calls.

Coordinates describe the captured desktop rectangle, not ownership of every
pixel in it. A foreground-window crop may contain overlapping windows.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import math


def _size(value):
    value = tuple(value)
    if len(value) != 2 or any(not isinstance(n, int) or isinstance(n, bool) or n <= 0 for n in value):
        raise ValueError("Image size must contain two positive integers")
    return value


def _bounds(value):
    value = tuple(value)
    if (len(value) != 4 or any(not isinstance(n, int) or isinstance(n, bool) for n in value)
            or value[2] <= value[0] or value[3] <= value[1]):
        raise ValueError("Capture bounds must be a nonempty integer rectangle")
    return value


@dataclass(frozen=True)
class CaptureTarget:
    kind: str
    bounds: tuple
    desktop_bounds: tuple
    window_bounds: tuple = ()
    hwnd: int = 0
    pid: int = 0
    window_dpi: int = 0

    def __post_init__(self):
        if self.kind not in {"primary", "virtual", "foreground"}:
            raise ValueError("Unknown capture target")
        object.__setattr__(self, "bounds", _bounds(self.bounds))
        object.__setattr__(self, "desktop_bounds", _bounds(self.desktop_bounds))
        object.__setattr__(self, "window_bounds", _bounds(self.window_bounds) if self.window_bounds else ())


@dataclass(frozen=True)
class FrameGeometry:
    acquired_size: tuple
    image_size: tuple
    target: CaptureTarget | None = None
    dpi_context: str = "unknown"
    policy: str = "legacy"
    composition: str = "raw"

    def __post_init__(self):
        object.__setattr__(self, "acquired_size", _size(self.acquired_size))
        object.__setattr__(self, "image_size", _size(self.image_size))
        if self.target and self.dpi_context not in {"per_monitor", "per_monitor_v2"}:
            raise ValueError("Physical coordinate context is required for a capture target")
        if self.target:
            left, top, right, bottom = self.target.bounds
            if self.acquired_size != (right - left, bottom - top):
                raise ValueError("Acquired dimensions must match the physical capture rectangle")

    def resized(self, size, *, composition="resize_and_later_overlays"):
        return replace(self, image_size=_size(size), composition=composition)

    def _transform(self):
        if self.target is None or self.dpi_context not in {"per_monitor_v2", "per_monitor"}:
            raise ValueError("Physical desktop calibration is unknown")
        left, top, right, bottom = self.target.bounds
        width, height = self.image_size
        return left, top, (right - left) / width, (bottom - top) / height

    def image_to_desktop(self, x, y):
        left, top, sx, sy = self._transform()
        if not all(math.isfinite(float(n)) for n in (x, y)):
            raise ValueError("Coordinates must be finite")
        if not (0 <= x < self.image_size[0] and 0 <= y < self.image_size[1]):
            raise ValueError("Point is outside the image")
        return left + x * sx, top + y * sy

    def desktop_to_image(self, x, y):
        left, top, sx, sy = self._transform()
        if not all(math.isfinite(float(n)) for n in (x, y)):
            raise ValueError("Coordinates must be finite")
        # Do not clamp an off-crop cursor into a false visible position.
        return (x - left) / sx, (y - top) / sy

    def to_dict(self):
        result = {"schema_version": 1, "policy": self.policy,
                  "status": "bracketed" if self.target else "unknown",
                  "acquired_size": list(self.acquired_size), "image_size": list(self.image_size),
                  "dpi_context": self.dpi_context, "composition": self.composition,
                  "coordinate_space": "physical_desktop_pixels" if self.target else "unknown",
                  "input_commands": "existing desktop commands remain literal; no automatic conversion"}
        if self.target:
            left, top, sx, sy = self._transform()
            result.update(origin=[left, top], crop_bounds=list(self.target.bounds),
                          desktop_bounds=list(self.target.desktop_bounds),
                          image_to_desktop={"scale_x": sx, "scale_y": sy, "offset_x": left, "offset_y": top},
                          target={"kind": self.target.kind, "hwnd": self.target.hwnd, "pid": self.target.pid,
                                  "window_bounds": list(self.target.window_bounds), "window_dpi": self.target.window_dpi or None,
                                  "validation": "same target/bounds before and after grab; not atomic or occlusion proof"})
        return result


@contextmanager
def physical_pixel_scope():
    """Temporarily opt this thread into physical coordinates, restoring on error."""
    import ctypes
    user32 = ctypes.windll.user32
    setter = user32.SetThreadDpiAwarenessContext
    setter.argtypes, setter.restype = [ctypes.c_void_p], ctypes.c_void_p
    previous = setter(ctypes.c_void_p(-4))
    mode = "per_monitor_v2"
    if not previous:
        previous = setter(ctypes.c_void_p(-3))
        mode = "per_monitor"
    if not previous:
        raise OSError("Cannot establish physical capture coordinates; legacy capture remains selectable")
    try:
        yield mode
    finally:
        if not setter(previous):
            raise OSError("Could not restore the capture thread DPI context")


def query_capture_target(kind):
    """Query inside physical_pixel_scope; no titles or application content retained."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    metrics = user32.GetSystemMetrics
    metrics.argtypes, metrics.restype = [ctypes.c_int], ctypes.c_int
    x, y, width, height = (metrics(index) for index in (76, 77, 78, 79))
    desktop = (x, y, x + width, y + height)
    if width <= 0 or height <= 0:
        raise OSError("Desktop bounds unavailable")
    if kind == "primary":
        bounds = (0, 0, metrics(0), metrics(1))
        return CaptureTarget(kind, bounds, desktop)
    if kind == "virtual":
        return CaptureTarget(kind, desktop, desktop)
    if kind != "foreground":
        raise ValueError("Unknown capture target")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    for name in ("IsWindowVisible", "IsIconic"):
        method = getattr(user32, name)
        method.argtypes, method.restype = [wintypes.HWND], wintypes.BOOL
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        raise OSError("Foreground capture target is absent, hidden or minimized")
    rect, process = wintypes.RECT(), wintypes.DWORD()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("Foreground capture bounds unavailable")
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process)):
        raise OSError("Foreground capture identity unavailable")
    window = (rect.left, rect.top, rect.right, rect.bottom)
    bounds = (max(rect.left, desktop[0]), max(rect.top, desktop[1]),
              min(rect.right, desktop[2]), min(rect.bottom, desktop[3]))
    dpi = 0
    if hasattr(user32, "GetDpiForWindow"):
        user32.GetDpiForWindow.argtypes, user32.GetDpiForWindow.restype = [wintypes.HWND], wintypes.UINT
        dpi = int(user32.GetDpiForWindow(hwnd))
    return CaptureTarget(kind, bounds, desktop, window, int(hwnd), int(process.value), dpi)


def capture_pixels(grab, target, *, scope=None, query=None):
    """Capture one explicit rectangle and reject geometry changes/dimension mismatch."""
    with (scope or physical_pixel_scope)() as dpi:
        inspect = query or query_capture_target
        before = inspect(target)
        left, top, right, bottom = before.bounds
        if right <= left or bottom <= top:
            raise OSError("Capture target has no visible area")
        image = grab(bbox=before.bounds, all_screens=True)
        after = inspect(target)
        if before != after:
            raise OSError("Capture target or geometry changed during acquisition")
        if tuple(image.size) != (right - left, bottom - top):
            raise OSError("Captured dimensions do not match the physical desktop rectangle")
        return image, FrameGeometry(tuple(image.size), tuple(image.size), before, dpi, "verified")


def query_cursor_position():
    """Read inside physical_pixel_scope, without allocating cursor/GDI images."""
    import ctypes
    from ctypes import wintypes
    method = ctypes.windll.user32.GetCursorPos
    method.argtypes, method.restype = [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL
    point = wintypes.POINT()
    return (int(point.x), int(point.y)) if method(ctypes.byref(point)) else None


def frame_geometry_prompt(frame):
    """Describe only the selected image; never imply input calibration for imports."""
    geometry = (frame or {}).get("geometry") or {}
    transform = geometry.get("image_to_desktop")
    if geometry.get("status") != "bracketed" or not transform:
        return "Capture coordinates: origin/DPI mapping unknown. Desktop input commands use literal desktop coordinates."
    target = geometry.get("target") or {}
    return (f"Capture frame {(frame or {}).get('provenance', {}).get('frame_id', 'unknown')}: "
            f"image={geometry.get('image_size')}, acquired={geometry.get('acquired_size')}, "
            f"target={target.get('kind')}, physical crop={geometry.get('crop_bounds')}. "
            f"Desktop x={transform['offset_x']}+image_x*{transform['scale_x']:g}, "
            f"y={transform['offset_y']}+image_y*{transform['scale_y']:g}. "
            "Desktop commands remain literal; this mapping does not verify their backend DPI calibration. "
            "Target identity/bounds matched before and after capture, not atomically. Overlays/cursor are later; occlusion is not verified.")
