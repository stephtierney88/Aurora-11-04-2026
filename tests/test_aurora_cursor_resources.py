"""Cursor resource ownership using the production function and fake Win32 calls."""
import ast
import ctypes
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "aurora2.py").read_text(encoding="utf-8-sig"))
CURSOR_FUNCTION = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "get_cursor")


class CursorFixture:
    """Own handles 101/102/103/201/202; all other handles are borrowed."""
    def __init__(self, failure=None, cleanup_failure=None):
        self.failure, self.cleanup_failure = failure, cleanup_failure
        self.owned, self.released, self.messages = set(), [], []
        self.selected = 999
        self.reads = 0
        self.restores = 0
        user = NS(GetCursorInfo=self.cursor_info, GetIconInfo=self.icon_info,
                  GetSystemMetrics=lambda _: 0 if failure == "metrics" else 2,
                  GetDC=lambda _: self.acquire("screen", 101), ReleaseDC=self.release_dc,
                  FillRect=lambda *a: failure != "fill", DrawIconEx=lambda *a: failure != "draw")
        gdi = NS(CreateCompatibleDC=lambda _: self.acquire("memory", 102),
                 CreateCompatibleBitmap=lambda *a: self.acquire("bitmap", 103),
                 SelectObject=self.select, GetStockObject=lambda _: 1000,
                 GetDIBits=self.read, DeleteDC=self.delete_dc, DeleteObject=self.delete)
        def convert(*args):
            if failure == "image":
                raise ValueError("synthetic conversion failure")
            return Image.frombuffer(*args)
        self.scope = {
            "ctypes": NS(windll=NS(user32=user, gdi32=gdi), sizeof=lambda _: 1,
                         byref=lambda value: value, c_byte=ctypes.c_byte, c_void_p=ctypes.c_void_p),
            "CURSORINFO": lambda: NS(cbSize=0, hCursor=0, ptScreenPos=NS(x=0, y=0)),
            "ICONINFO": lambda: NS(hbmColor=0, hbmMask=0, xHotspot=0, yHotspot=0),
            "BITMAPINFO": lambda: NS(bmiHeader=NS()), "BITMAPINFOHEADER": object,
            "RECT": lambda *args: args, "BI_RGB": 0, "DIB_RGB_COLORS": 0,
            "Image": NS(frombuffer=convert), "append_runtime_feedback": self.messages.append,
        }
        exec(compile(ast.Module(body=[CURSOR_FUNCTION], type_ignores=[]), "cursor-fixture", "exec"), self.scope)

    def cursor_info(self, info):
        info.hCursor = 0 if self.failure == "no_cursor" else 55
        info.ptScreenPos = NS(x=500, y=300)
        return self.failure != "cursor_info"

    def icon_info(self, handle, info):
        assert handle == 55
        self.owned.update((201, 202))
        info.hbmColor, info.hbmMask = 201, 202
        info.xHotspot, info.yHotspot = 1, 0
        return self.failure != "icon_info"

    def acquire(self, stage, handle):
        if self.failure == stage:
            return 0
        self.owned.add(handle)
        return handle

    def select(self, dc, handle):
        assert dc == 102 and dc in self.owned
        if handle == 103 and self.failure == "select":
            return ctypes.c_void_p(-1).value
        if handle == 999:
            self.restores += 1
            if self.failure == "restore":
                return ctypes.c_void_p(-1).value
        previous, self.selected = self.selected, handle
        return previous

    def read(self, dc, bitmap, start, rows, buffer, info, flags):
        assert bitmap == 103 and bitmap in self.owned
        assert self.selected != bitmap, "GetDIBits called on selected bitmap"
        assert info.bmiHeader.biHeight == -2
        self.reads += 1
        return 0 if self.failure == "dibits" else 1 if self.failure == "partial" else rows

    def release_dc(self, owner, dc):
        assert owner is None and dc == 101
        return self.delete(dc)

    def delete_dc(self, dc):
        assert dc == 102
        if self.cleanup_failure == "memory":
            raise OSError("synthetic cleanup failure")
        self.selected = None
        return self.delete(dc)

    def delete(self, handle):
        assert handle in self.owned, "double free or deleting a borrowed handle"
        assert handle != self.selected, "deleting a selected bitmap"
        self.owned.remove(handle)
        self.released.append(handle)
        return True

    def run(self):
        return self.scope["get_cursor"]()


class CursorResourceTests(unittest.TestCase):
    def test_success_deselects_before_read_and_releases_owned_handles(self):
        fixture = CursorFixture()
        image, hotspot, position = fixture.run()
        self.assertEqual((image.size, hotspot, position), ((2, 2), (1, 0), (500, 300)))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(fixture.reads, 1)
        self.assertEqual(set(fixture.released), {101, 102, 103, 201, 202})
        self.assertFalse(fixture.owned)
        self.assertFalse(fixture.messages)

    def test_all_acquisition_and_render_failures_release_every_owned_handle(self):
        for stage in ("cursor_info", "no_cursor", "icon_info", "metrics", "screen", "memory",
                      "bitmap", "select", "fill", "draw", "restore", "dibits", "partial"):
            with self.subTest(stage=stage):
                fixture = CursorFixture(stage)
                self.assertIsNone(fixture.run()[0])
                self.assertFalse(fixture.owned, stage)
                self.assertEqual(bool(fixture.messages), stage == "restore")
                if stage == "restore":
                    self.assertEqual(fixture.reads, 0)
                    self.assertEqual(fixture.restores, 2)

    def test_conversion_exception_still_releases_handles(self):
        fixture = CursorFixture("image")
        with self.assertRaisesRegex(ValueError, "synthetic conversion"):
            fixture.run()
        self.assertFalse(fixture.owned)

    def test_cleanup_failure_is_reported_without_skipping_other_releases(self):
        fixture = CursorFixture(cleanup_failure="memory")
        self.assertIsNotNone(fixture.run()[0])
        self.assertEqual(fixture.owned, {102})
        self.assertEqual(set(fixture.released), {101, 103, 201, 202})
        self.assertEqual(fixture.messages, ["Cursor resource cleanup incomplete: memory DC"])


if __name__ == "__main__":
    unittest.main()
