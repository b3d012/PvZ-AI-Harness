"""Non-live safety tests for the Windows controller backend."""

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import (
    ClientArea,
    CoordinateOutOfBounds,
    GameWindowUnavailable,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    KEYEVENTF_KEYUP,
    VK_ESCAPE,
    WindowsInputBackend,
    _Win32Api,
)


class FakeWindowsApi:
    def __init__(self, *, hwnd=100, minimized=False, focus=True, foreground=100):
        self.hwnd = hwnd
        self.minimized = minimized
        self.focus_result = focus
        self.foreground = foreground
        self.cursor_positions = []
        self.click_count = 0
        self.events = []

    def find_main_window(self, _process_name, process_id=None):
        if process_id is not None and process_id != 42:
            return None
        return self.hwnd

    def is_window(self, hwnd):
        return hwnd == self.hwnd

    def window_process_id(self, _hwnd):
        return 42

    def window_title(self, _hwnd):
        return "Plants vs. Zombies"

    def is_minimized(self, _hwnd):
        return self.minimized

    def client_area(self, hwnd):
        return ClientArea(hwnd, 200, 100, 1600, 900)

    def focus(self, _hwnd):
        return self.focus_result

    def foreground_window(self):
        return self.foreground

    def set_cursor_pos(self, x, y):
        self.events.append(("move", x, y))
        self.cursor_positions.append((x, y))
        return True

    def send_left_click(self):
        self.events.append(("click",))
        self.click_count += 1
        return True

    def send_key_press(self, key):
        self.events.append(("key", key))
        return True


class WindowsInputBackendTests(unittest.TestCase):
    def test_scaled_click_targets_resolved_client(self):
        api = FakeWindowsApi()
        backend = WindowsInputBackend(api=api)

        screen_point = backend.left_click(400, 300)

        self.assertEqual(screen_point, (1000, 550))
        self.assertEqual(api.cursor_positions, [(1000, 550)])
        self.assertEqual(api.click_count, 1)

    def test_move_settles_before_click(self):
        api = FakeWindowsApi()
        backend = WindowsInputBackend(api=api)

        with patch("pvz_controller.windows_input.time.sleep") as sleep:
            backend.left_click(400, 300, move_settle_delay=0.03)

        self.assertEqual(api.events, [("move", 1000, 550), ("click",)])
        sleep.assert_called_once_with(0.03)

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

    def test_foreground_check_uses_resolved_pvz_window(self):
        api = FakeWindowsApi(foreground=999)
        backend = WindowsInputBackend(api=api)

        self.assertFalse(backend.is_foreground())
        api.foreground = api.hwnd
        self.assertTrue(backend.is_foreground())

    def test_pid_binding_rejects_window_from_another_process(self):
        backend = WindowsInputBackend(api=FakeWindowsApi(), expected_process_id=99)
        with self.assertRaises(GameWindowUnavailable):
            backend.get_client_area()

    def test_manual_focus_policy_refuses_input_without_moving_cursor(self):
        api = FakeWindowsApi(foreground=999)
        backend = WindowsInputBackend(api=api, auto_focus=False)
        with self.assertRaisesRegex(Exception, "not foreground"):
            backend.left_click(400, 300)
        self.assertEqual(api.cursor_positions, [])
        self.assertEqual(api.click_count, 0)

    def test_escape_is_sent_only_to_verified_foreground_window(self):
        api = FakeWindowsApi()
        backend = WindowsInputBackend(api=api, expected_process_id=42)
        backend.press_escape()
        self.assertEqual(api.events, [("key", 27)])


class Win32FocusTests(unittest.TestCase):
    def test_already_foreground_skips_set_foreground_window(self):
        calls = []

        class User32:
            def GetForegroundWindow(self):
                return 100

            def SetForegroundWindow(self, hwnd):
                calls.append(hwnd)
                return False

        api = _Win32Api.__new__(_Win32Api)
        api.user32 = User32()

        self.assertTrue(api.focus(100))
        self.assertEqual(calls, [])

    def test_focus_rechecks_foreground_after_safe_attempt(self):
        calls = []

        class User32:
            foreground = 999

            def GetForegroundWindow(self):
                return self.foreground

            def SetForegroundWindow(self, hwnd):
                calls.append(hwnd)
                self.foreground = hwnd
                return True

        api = _Win32Api.__new__(_Win32Api)
        api.user32 = User32()

        self.assertTrue(api.focus(100))
        self.assertEqual(calls, [100])


class Win32MouseInputTests(unittest.TestCase):
    def test_click_sends_one_button_down_and_one_button_up(self):
        captured = []

        class User32:
            def SendInput(self, count, inputs, input_size):
                captured.append(
                    (
                        count,
                        [inputs[index].mouse.flags for index in range(count)],
                        input_size,
                    )
                )
                return count

        api = _Win32Api.__new__(_Win32Api)
        api.user32 = User32()

        self.assertTrue(api.send_left_click())
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], 2)
        self.assertEqual(
            captured[0][1],
            [MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP],
        )

    def test_escape_sends_one_key_down_and_one_key_up(self):
        captured = []

        class User32:
            def SendInput(self, count, inputs, input_size):
                captured.append((
                    count,
                    [(inputs[index].keyboard.virtual_key, inputs[index].keyboard.flags)
                     for index in range(count)],
                    input_size,
                ))
                return count

        api = _Win32Api.__new__(_Win32Api)
        api.user32 = User32()
        self.assertTrue(api.send_key_press(VK_ESCAPE))
        self.assertEqual(captured[0][0], 2)
        self.assertEqual(captured[0][1], [(VK_ESCAPE, 0), (VK_ESCAPE, KEYEVENTF_KEYUP)])


if __name__ == "__main__":
    unittest.main()
