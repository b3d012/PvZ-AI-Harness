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
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
PM_NOREMOVE = 0
SW_RESTORE = 9
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
FOCUS_TIMEOUT_SECONDS = 0.25
FOCUS_POLL_INTERVAL_SECONDS = 0.01


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


@dataclass(frozen=True)
class WindowRect:
    """Physical screen bounds including the non-client frame/title bar."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class WindowCoordinateReport:
    """Read-only evidence separating window, client, and PvZ logical spaces."""

    hwnd: int
    process_id: int
    window_rect: WindowRect
    client_area: ClientArea
    dpi: int | None
    logical_size: tuple[int, int]
    scale: tuple[float, float]


@dataclass(frozen=True)
class GameWindowInfo:
    """Identity and presentation state of one validated PvZ window."""

    hwnd: int
    process_id: int
    title: str
    minimized: bool
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


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mouse", _MouseInput), ("keyboard", _KeyboardInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", _InputUnion)]


class _Win32Api:
    """Small ctypes wrapper kept behind an injectable test seam."""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def find_main_window(self, process_name: str, process_id: int | None = None) -> int | None:
        matches = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def visit(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True

            window_pid = self.window_process_id(hwnd)
            if ((process_id is None or window_pid == process_id)
                    and self._window_process_name(hwnd).casefold() == process_name.casefold()):
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
        process_id = self.window_process_id(hwnd)
        if not process_id:
            return ""

        process = self.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id,
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

    def window_process_id(self, hwnd: int) -> int:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return int(process_id.value)

    def is_window(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindow(hwnd))

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

    def window_rect(self, hwnd: int) -> WindowRect:
        rect = _Rect()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise GameWindowUnavailable("failed to read PvZ window bounds")
        return WindowRect(int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

    def dpi_for_window(self, hwnd: int) -> int | None:
        """Return per-window DPI when the platform exports GetDpiForWindow."""
        getter = getattr(self.user32, "GetDpiForWindow", None)
        if getter is None:
            return None
        dpi = int(getter(hwnd))
        return dpi if dpi > 0 else None

    def cursor_position(self) -> tuple[int, int]:
        point = _Point()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            raise InputFailed("failed to read cursor position")
        return int(point.x), int(point.y)

    def focus(
        self,
        hwnd: int,
        *,
        timeout_seconds: float = FOCUS_TIMEOUT_SECONDS,
        poll_interval_seconds: float = FOCUS_POLL_INTERVAL_SECONDS,
    ) -> bool:
        """Request foreground activation and verify the exact target HWND.

        Windows restricts foreground activation.  Joining the caller to the
        relevant GUI input queues gives the documented activation calls the
        best legitimate opportunity to succeed; every temporary attachment is
        removed in ``finally`` and success still depends on foreground
        verification.
        """
        if self.foreground_window() == hwnd:
            return True

        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, SW_RESTORE)

        # Worker threads do not necessarily own a Win32 message queue. A
        # non-removing peek creates one before AttachThreadInput is attempted.
        message = wintypes.MSG()
        self.user32.PeekMessageW(ctypes.byref(message), 0, 0, 0, PM_NOREMOVE)
        current_thread = int(self.kernel32.GetCurrentThreadId())
        foreground = self.foreground_window()
        thread_ids = {
            self.window_thread_id(hwnd),
            self.window_thread_id(foreground) if foreground else 0,
        }
        attached_threads: list[int] = []
        try:
            for thread_id in sorted(thread_ids):
                if thread_id and thread_id != current_thread:
                    if self.user32.AttachThreadInput(current_thread, thread_id, True):
                        attached_threads.append(thread_id)

            self.user32.BringWindowToTop(hwnd)
            self.user32.SetForegroundWindow(hwnd)
            self.user32.SetActiveWindow(hwnd)
            self.user32.SetFocus(hwnd)
        finally:
            for thread_id in reversed(attached_threads):
                self.user32.AttachThreadInput(current_thread, thread_id, False)

        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if self.foreground_window() == hwnd:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def foreground_window(self) -> int:
        """Return the HWND currently allowed by Windows to receive input."""
        return int(self.user32.GetForegroundWindow())

    def window_thread_id(self, hwnd: int) -> int:
        """Return the GUI thread owning ``hwnd`` without changing process state."""
        return int(self.user32.GetWindowThreadProcessId(hwnd, None))

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

    def send_key_press(self, virtual_key: int) -> bool:
        inputs = (_Input * 2)(
            _Input(type=INPUT_KEYBOARD, keyboard=_KeyboardInput(virtual_key=virtual_key)),
            _Input(
                type=INPUT_KEYBOARD,
                keyboard=_KeyboardInput(virtual_key=virtual_key, flags=KEYEVENTF_KEYUP),
            ),
        )
        return self.user32.SendInput(2, inputs, ctypes.sizeof(_Input)) == 2

    def send_scan_code_key_press(self, virtual_key: int) -> bool:
        """Send one key down/up pair using a Win32-derived hardware scan code."""
        scan_code = int(self.user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC))
        if not scan_code:
            return False
        inputs = (_Input * 2)(
            _Input(
                type=INPUT_KEYBOARD,
                keyboard=_KeyboardInput(
                    virtual_key=0,
                    scan_code=scan_code,
                    flags=KEYEVENTF_SCANCODE,
                ),
            ),
            _Input(
                type=INPUT_KEYBOARD,
                keyboard=_KeyboardInput(
                    virtual_key=0,
                    scan_code=scan_code,
                    flags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP,
                ),
            ),
        )
        return self.user32.SendInput(2, inputs, ctypes.sizeof(_Input)) == 2


class WindowsInputBackend:
    """Resolve the current PvZ window and issue one safe normal mouse click."""

    def __init__(
        self,
        process_name: str = PROCESS_NAME,
        api=None,
        *,
        expected_process_id: int | None = None,
        auto_focus: bool = True,
    ):
        self.process_name = process_name
        self._api = api if api is not None else _Win32Api()
        self.expected_process_id = expected_process_id
        self.auto_focus = auto_focus

    def bind_process(self, process_id: int | None) -> None:
        """Restrict future window resolution to a specific attached process."""
        self.expected_process_id = process_id

    def set_auto_focus(self, enabled: bool) -> None:
        """Configure whether input may restore foreground focus automatically."""
        self.auto_focus = bool(enabled)

    def _find_window(self) -> int | None:
        if self.expected_process_id is None:
            return self._api.find_main_window(self.process_name)
        return self._api.find_main_window(self.process_name, self.expected_process_id)

    def get_client_area(self) -> ClientArea:
        hwnd = self._find_window()
        if hwnd is None:
            raise GameWindowUnavailable("Plants vs. Zombies window not found")

        if self._api.is_minimized(hwnd):
            raise GameWindowUnavailable("Plants vs. Zombies window is minimized")

        area = self._api.client_area(hwnd)
        if area.width <= 0 or area.height <= 0:
            raise GameWindowUnavailable("Plants vs. Zombies client has no usable area")

        return area

    def get_window_info(self) -> GameWindowInfo:
        """Return identity for the window bound to the current process."""
        hwnd = self._find_window()
        if hwnd is None or not self._api.is_window(hwnd):
            raise GameWindowUnavailable("Plants vs. Zombies window not found")
        area = self._api.client_area(hwnd)
        return GameWindowInfo(
            hwnd=hwnd,
            process_id=self._api.window_process_id(hwnd),
            title=self._api.window_title(hwnd),
            minimized=self._api.is_minimized(hwnd),
            width=area.width,
            height=area.height,
        )

    def coordinate_report(self) -> WindowCoordinateReport:
        """Read-only report; never derives client origin from WindowRect."""
        area = self.get_client_area()
        return WindowCoordinateReport(
            hwnd=area.hwnd,
            process_id=self._api.window_process_id(area.hwnd),
            window_rect=self._api.window_rect(area.hwnd),
            client_area=area,
            dpi=self._api.dpi_for_window(area.hwnd),
            logical_size=(800, 600),
            scale=(area.width / 800.0, area.height / 600.0),
        )

    def cursor_screen_position(self) -> tuple[int, int]:
        """Read the physical cursor location without moving or clicking it."""
        return self._api.cursor_position()

    def screen_to_client(self, screen_x: int, screen_y: int, area: ClientArea | None = None) -> tuple[int, int]:
        """Convert a physical screen point using ClientToScreen's origin only."""
        resolved = area or self.get_client_area()
        return int(screen_x) - resolved.screen_x, int(screen_y) - resolved.screen_y

    def focus_game(self) -> bool:
        """Explicitly focus the validated PvZ window and verify foreground."""
        area = self.get_client_area()
        return bool(self._api.focus(area.hwnd) and self._api.foreground_window() == area.hwnd)

    def foreground_window(self) -> int:
        """Return the current foreground HWND for operator diagnostics."""
        return self._api.foreground_window()

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

        if self._api.foreground_window() != area.hwnd:
            if not self.auto_focus:
                raise InputFailed("Plants vs. Zombies window is not foreground")
            if not self._api.focus(area.hwnd) or self._api.foreground_window() != area.hwnd:
                raise InputFailed("could not focus the Plants vs. Zombies window")

        if not self._api.set_cursor_pos(screen_x, screen_y):
            raise InputFailed("Windows rejected the mouse move")

        if move_settle_delay > 0:
            time.sleep(move_settle_delay)

        if not self._api.send_left_click():
            raise InputFailed("Windows rejected the mouse click")

        return screen_x, screen_y

    def press_escape(self) -> None:
        """Send one verified Escape key press to the bound PvZ window."""
        self._press_key(VK_ESCAPE, "Escape")

    def press_enter(self) -> None:
        """Send one verified Enter key press to the bound PvZ window."""
        self._press_key(VK_RETURN, "Enter")

    def _press_key(self, virtual_key: int, key_name: str) -> None:
        """Send one verified scan-code key press to the bound PvZ window."""
        area = self.get_client_area()
        if self._api.foreground_window() != area.hwnd:
            if not self.auto_focus:
                raise InputFailed("Plants vs. Zombies window is not foreground")
            if not self._api.focus(area.hwnd):
                raise InputFailed("could not focus the Plants vs. Zombies window")
        if self._api.foreground_window() != area.hwnd:
            raise InputFailed("Plants vs. Zombies focus verification failed")
        if not self._api.send_scan_code_key_press(virtual_key):
            raise InputFailed(f"Windows rejected the {key_name} key press")
