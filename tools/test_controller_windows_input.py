"""Non-live safety tests for the Windows controller backend."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import (
    ClientArea,
    CoordinateOutOfBounds,
    GameWindowUnavailable,
    WindowsInputBackend,
)


class FakeWindowsApi:
    def __init__(self, *, hwnd=100, minimized=False, focus=True):
        self.hwnd = hwnd
        self.minimized = minimized
        self.focus_result = focus
        self.cursor_positions = []
        self.click_count = 0

    def find_main_window(self, _process_name):
        return self.hwnd

    def is_minimized(self, _hwnd):
        return self.minimized

    def client_area(self, hwnd):
        return ClientArea(hwnd, 200, 100, 1600, 900)

    def focus(self, _hwnd):
        return self.focus_result

    def set_cursor_pos(self, x, y):
        self.cursor_positions.append((x, y))
        return True

    def send_left_click(self):
        self.click_count += 1
        return True


class WindowsInputBackendTests(unittest.TestCase):
    def test_scaled_click_targets_resolved_client(self):
        api = FakeWindowsApi()
        backend = WindowsInputBackend(api=api)

        screen_point = backend.left_click(400, 300)

        self.assertEqual(screen_point, (1000, 550))
        self.assertEqual(api.cursor_positions, [(1000, 550)])
        self.assertEqual(api.click_count, 1)

    def test_missing_window_fails_without_click(self):
        api = FakeWindowsApi(hwnd=None)
        backend = WindowsInputBackend(api=api)

        with self.assertRaises(GameWindowUnavailable):
            backend.left_click(400, 300)

        self.assertEqual(api.cursor_positions, [])
        self.assertEqual(api.click_count, 0)

    def test_minimized_window_fails_without_click(self):
        api = FakeWindowsApi(minimized=True)
        backend = WindowsInputBackend(api=api)

        with self.assertRaises(GameWindowUnavailable):
            backend.left_click(400, 300)

        self.assertEqual(api.click_count, 0)

    def test_out_of_bounds_point_fails_without_click(self):
        api = FakeWindowsApi()
        backend = WindowsInputBackend(api=api)

        with self.assertRaises(CoordinateOutOfBounds):
            backend.left_click(800, 300)

        self.assertEqual(api.click_count, 0)


if __name__ == "__main__":
    unittest.main()
