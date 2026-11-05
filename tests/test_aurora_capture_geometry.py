"""Physical-coordinate contracts with synthetic pixels and fake Win32 calls only."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
import ctypes
import pickle
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from aurora_capture_geometry import (
    CaptureTarget, FrameGeometry, capture_pixels, frame_geometry_prompt,
    physical_pixel_scope, query_capture_target, query_cursor_position,
)
from aurora_capture_provenance import CaptureService, CapturedFrame


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.target = CaptureTarget("foreground", (-800, 100, 400, 700), (-1920, 0, 2560, 1440),
                                    (-800, 100, 400, 700), 123, 456, 144)
        self.geometry = FrameGeometry((1200, 600), (1200, 600), self.target, "per_monitor_v2", "verified")

    def test_resize_mapping_negative_origin_and_nonuniform_scale(self):
        output = self.geometry.resized((600, 200))
        self.assertEqual(output.image_to_desktop(300, 100), (-200, 400))
        self.assertEqual(output.desktop_to_image(-200, 400), (300, 100))
        self.assertEqual(output.to_dict()["image_to_desktop"], {
            "scale_x": 2, "scale_y": 3, "offset_x": -800, "offset_y": 100})
        # DPI describes the window, it is not multiplied into physical coordinates.
        self.assertEqual(output.to_dict()["target"]["window_dpi"], 144)
        self.assertEqual(self.geometry.image_size, (1200, 600))

    def test_off_crop_points_are_not_clamped_and_invalid_input_rejected(self):
        self.assertLess(self.geometry.desktop_to_image(-900, 100)[0], 0)
        for point in ((-1, 0), (1200, 0), (0, 600), (float("nan"), 0)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.geometry.image_to_desktop(*point)
        for size in ((0, 2), (True, 2), (1.5, 2), (1,)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.geometry.resized(size)

    def test_unknown_geometry_is_not_upgraded(self):
        geometry = FrameGeometry((30, 20), (15, 10))
        self.assertEqual(geometry.to_dict()["status"], "unknown")
        self.assertNotIn("image_to_desktop", geometry.to_dict())
        with self.assertRaises(ValueError):
            geometry.image_to_desktop(1, 1)
        with self.assertRaises(ValueError):
            FrameGeometry((30, 20), (30, 20), self.target)
        self.assertIn("unknown", frame_geometry_prompt({}))

    def test_immutable_queued_and_detached_published_metadata(self):
        service = CaptureService()
        stamp = service.finish(service.begin("fixture"))
        frame = CapturedFrame(b"pixels", stamp, "hash", self.geometry)
        self.assertEqual(pickle.loads(pickle.dumps(frame)), frame)
        with self.assertRaises(FrozenInstanceError):
            frame.geometry.target = None
        service.publish(stamp, path="fixture.png", timestamp="fixture", capture_hash="hash", counter=1,
                        geometry=self.geometry)
        snapshot = service.snapshot()
        snapshot["latest"]["geometry"]["target"]["kind"] = "altered"
        snapshot["latest"]["geometry"]["crop_bounds"][0] = 9999
        self.assertEqual(service.snapshot()["latest"]["geometry"], self.geometry.to_dict())

    def test_success_and_changed_target_failure_restore_scope(self):
        entries = []
        @contextmanager
        def scope():
            entries.append("enter")
            try:
                yield "per_monitor_v2"
            finally:
                entries.append("restore")
        grab = Mock(return_value=Image.new("RGB", (1200, 600)))
        image, result = capture_pixels(grab, "foreground", scope=scope, query=lambda kind: self.target)
        grab.assert_called_once_with(bbox=self.target.bounds, all_screens=True)
        self.assertEqual(result, self.geometry)
        for changed in (replace(self.target, hwnd=999), replace(self.target, pid=999),
                        replace(self.target, bounds=(-799, 100, 401, 700)),
                        replace(self.target, window_dpi=192)):
            with self.subTest(changed=changed), self.assertRaisesRegex(OSError, "changed"):
                capture_pixels(grab, "foreground", scope=scope, query=Mock(side_effect=[self.target, changed]))
        self.assertEqual(entries, ["enter", "restore"] * 5)

    def test_wrong_pixel_size_and_grab_failure_never_return_a_frame(self):
        @contextmanager
        def scope():
            yield "per_monitor"
        for grab in (Mock(return_value=Image.new("RGB", (800, 400))), Mock(side_effect=OSError("fixture"))):
            with self.assertRaises(OSError):
                capture_pixels(grab, "foreground", scope=scope, query=lambda kind: self.target)

    def test_cursor_position_read_uses_no_image_allocation_and_preserves_unknown(self):
        def cursor(pointer):
            pointer._obj.x, pointer._obj.y = -500, 200
            return 1
        getter = Mock(side_effect=cursor)
        with patch.object(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(GetCursorPos=getter)), create=True):
            self.assertEqual(query_cursor_position(), (-500, 200))
            getter.side_effect = None
            getter.return_value = 0
            self.assertIsNone(query_cursor_position())

    def test_selected_frame_description_is_specific_and_honest(self):
        text = frame_geometry_prompt({"geometry": self.geometry.resized((600, 200)).to_dict(),
                                      "provenance": {"frame_id": "frame-42"}})
        for part in ("frame-42", "x=-800+image_x*2", "y=100+image_y*3", "literal", "occlusion", "later"):
            self.assertIn(part, text)

    def test_thread_dpi_context_restored_after_exception_and_fallback(self):
        for replies, mode in (([77, 1], "per_monitor_v2"), ([0, 77, 1], "per_monitor")):
            setter = Mock(side_effect=replies)
            with patch.object(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(SetThreadDpiAwarenessContext=setter)), create=True):
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    with physical_pixel_scope() as actual:
                        self.assertEqual(actual, mode)
                        raise RuntimeError("fixture failure")
            self.assertEqual(setter.call_args.args, (77,))
        setter = Mock(return_value=0)
        with patch.object(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(SetThreadDpiAwarenessContext=setter)), create=True):
            with self.assertRaises(OSError):
                with physical_pixel_scope():
                    self.fail("Unverified context admitted")

    def test_native_target_adapter_clips_window_and_records_identity(self):
        def rect(hwnd, pointer):
            pointer._obj.left, pointer._obj.top = -2200, -100
            pointer._obj.right, pointer._obj.bottom = -1200, 500
            return 1
        def pid(hwnd, pointer):
            pointer._obj.value = 45
            return 1
        user32 = SimpleNamespace(
            GetSystemMetrics=Mock(side_effect=lambda n: {76:-1920,77:0,78:4480,79:1440,0:2560,1:1440}[n]),
            GetForegroundWindow=Mock(return_value=123), GetWindowRect=Mock(side_effect=rect),
            GetWindowThreadProcessId=Mock(side_effect=pid), IsWindowVisible=Mock(return_value=True),
            IsIconic=Mock(return_value=False), GetDpiForWindow=Mock(return_value=144))
        with patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            self.assertEqual(query_capture_target("primary").bounds, (0,0,2560,1440))
            self.assertEqual(query_capture_target("virtual").bounds, (-1920,0,2560,1440))
            target = query_capture_target("foreground")
            self.assertEqual(target.bounds, (-1920,0,-1200,500))
            self.assertEqual((target.hwnd, target.pid, target.window_dpi), (123,45,144))
            self.assertEqual(target.window_bounds, (-2200,-100,-1200,500))
            user32.IsIconic.return_value = True
            with self.assertRaisesRegex(OSError, "minimized"):
                query_capture_target("foreground")


if __name__ == "__main__":
    unittest.main()
