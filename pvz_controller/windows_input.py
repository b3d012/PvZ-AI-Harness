"""Safe Windows window targeting and normal mouse input for PvZ."""

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

from pvz_controller.coordinates import scale_logical_to_client


PROCESS_NAME = "PlantsVsZombies.exe"
WINDOW_TITLE = "Plants vs. Zombies"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0


class ControllerInputError(RuntimeError):
    """Base error for safe controller input failures."""


class GameWindowUnavailable(ControllerInputError):
    """Raised when the PvZ client cannot be targeted safely."""


class CoordinateOutOfBounds(ControllerInputError):
    """Raised when a calculated point is outside the PvZ client."""


class InputFailed(ControllerInputError):
    """Raised when Windows rejects a requested input operation."""


@dataclass(frozen=True)
class ClientArea:
    hwnd: int
    screen_x: int
    screen_y: int
    width: int
    height: int


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mouse", _MouseInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", _InputUnion)]


class _Win32Api:
    """Small ctypes wrapper kept behind an injectable test seam."""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def find_main_window(self, process_name: str) -> int | None:
        matches = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def visit(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True

            if self._window_process_name(hwnd).casefold() == process_name.casefold():
                matches.append(int(hwnd))
            return True

        callback = callback_type(visit)
        if not self.user32.EnumWindows(callback, 0):
            raise InputFailed("failed to enumerate desktop windows")

        if not matches:
            return None

        # Prefer the expected titled gameplay window when multiple top-level
        # windows belong to the process.
        for hwnd in matches:
            if self.window_title(hwnd) == WINDOW_TITLE:
                return hwnd

        return matches[0]

    def _window_process_name(self, hwnd: int) -> str:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return ""

        process = self.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id.value,
        )
        if not process:
            return ""

        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(
                process,
                0,
                path,
                ctypes.byref(size),
            ):
                return ""
            return os.path.basename(path.value)
        finally:
            self.kernel32.CloseHandle(process)

    def window_title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, title, len(title))
        return title.value

    def is_minimized(self, hwnd: int) -> bool:
        return bool(self.user32.IsIconic(hwnd))

    def client_area(self, hwnd: int) -> ClientArea:
        rect = _Rect()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise GameWindowUnavailable("failed to read PvZ client bounds")

        origin = _Point(0, 0)
        if not self.user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise GameWindowUnavailable("failed to locate the PvZ client")

        return ClientArea(
            hwnd=hwnd,
            screen_x=origin.x,
            screen_y=origin.y,
            width=rect.right - rect.left,
            height=rect.bottom - rect.top,
        )

    def focus(self, hwnd: int) -> bool:
        if self.foreground_window() == hwnd:
            return True

        self.user32.SetForegroundWindow(hwnd)
        return self.foreground_window() == hwnd

    def foreground_window(self) -> int:
        """Return the HWND currently allowed by Windows to receive input."""
        return int(self.user32.GetForegroundWindow())

    def set_cursor_pos(self, x: int, y: int) -> bool:
        return bool(self.user32.SetCursorPos(x, y))

    def send_left_click(self) -> bool:
        inputs = (_Input * 2)(
            _Input(
                type=INPUT_MOUSE,
                mouse=_MouseInput(flags=MOUSEEVENTF_LEFTDOWN),
            ),
            _Input(
                type=INPUT_MOUSE,
                mouse=_MouseInput(flags=MOUSEEVENTF_LEFTUP),
            ),
        )
        return self.user32.SendInput(2, inputs, ctypes.sizeof(_Input)) == 2


class WindowsInputBackend:
    """Resolve the current PvZ window and issue one safe normal mouse click."""

    def __init__(self, process_name: str = PROCESS_NAME, api=None):
        self.process_name = process_name
        self._api = api if api is not None else _Win32Api()

    def get_client_area(self) -> ClientArea:
        hwnd = self._api.find_main_window(self.process_name)
        if hwnd is None:
            raise GameWindowUnavailable("Plants vs. Zombies window not found")

        if self._api.is_minimized(hwnd):
            raise GameWindowUnavailable("Plants vs. Zombies window is minimized")

        area = self._api.client_area(hwnd)
        if area.width <= 0 or area.height <= 0:
            raise GameWindowUnavailable("Plants vs. Zombies client has no usable area")

        return area

    def logical_to_screen(self, x: int, y: int, area: ClientArea) -> tuple[int, int]:
        try:
            client_x, client_y = scale_logical_to_client(
                x,
                y,
                area.width,
                area.height,
            )
        except ValueError as error:
            raise CoordinateOutOfBounds(str(error)) from error

        if not 0 <= client_x < area.width or not 0 <= client_y < area.height:
            raise CoordinateOutOfBounds("scaled point is outside the PvZ client")

        return area.screen_x + client_x, area.screen_y + client_y

    def is_foreground(self) -> bool:
        """Whether the safely resolved PvZ gameplay window is foreground."""
        area = self.get_client_area()
        return self._api.foreground_window() == area.hwnd

    def left_click(
        self,
        logical_x: int,
        logical_y: int,
        *,
        move_settle_delay: float = 0.0,
    ) -> tuple[int, int]:
        """Focus PvZ and issue exactly one click at a logical client point."""
        area = self.get_client_area()
        screen_x, screen_y = self.logical_to_screen(logical_x, logical_y, area)

        if not self._api.focus(area.hwnd):
            raise InputFailed("could not focus the Plants vs. Zombies window")

        if not self._api.set_cursor_pos(screen_x, screen_y):
            raise InputFailed("Windows rejected the mouse move")

        if move_settle_delay > 0:
            time.sleep(move_settle_delay)

        if not self._api.send_left_click():
            raise InputFailed("Windows rejected the mouse click")

        return screen_x, screen_y
