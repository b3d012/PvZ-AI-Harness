"""Process, reader, and window ownership for the live PvZ runtime."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol

import psutil

from pvz_controller.windows_input import (
    GameWindowInfo,
    GameWindowUnavailable,
    InputFailed,
    WindowsInputBackend,
)
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader
from pvz_reader.outcome import GameOutcome, OutcomeEvidence, read_outcome
from pvz_reader.process import PVZ_PROCESS_NAMES
from pvz_reader.versions import PVZ_VERSION


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessIdentity:
    """Minimal identity retained for the process to which memory is attached."""

    process_id: int
    name: str
    executable: str | None = None


@dataclass(frozen=True)
class SessionStatus:
    """Serializable connection status without exposing process handles."""

    attached: bool
    process_alive: bool
    process: ProcessIdentity | None
    window: GameWindowInfo | None
    window_valid: bool
    focused: bool
    supported_version: str
    version_verified: bool
    generation: int
    last_error: str | None
    foreground_hwnd: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attached": self.attached,
            "process_alive": self.process_alive,
            "process": None if self.process is None else {
                "process_id": self.process.process_id,
                "name": self.process.name,
            },
            "window": None if self.window is None else {
                "hwnd": self.window.hwnd,
                "process_id": self.window.process_id,
                "title": self.window.title,
                "minimized": self.window.minimized,
                "width": self.window.width,
                "height": self.window.height,
            },
            "window_valid": self.window_valid,
            "focused": self.focused,
            "supported_version": self.supported_version,
            "version_verified": self.version_verified,
            "generation": self.generation,
            "last_error": self.last_error,
            "foreground_hwnd": self.foreground_hwnd,
        }


@dataclass(frozen=True)
class SessionRead:
    """One reader attempt with failure provenance kept explicit."""

    state: Any | None
    reader_valid: bool
    error: str | None = None


class ProcessDiscovery(Protocol):
    def find_process(self) -> ProcessIdentity | None: ...
    def is_alive(self, process_id: int) -> bool: ...


class PsutilProcessDiscovery:
    """Discover supported executable names and validate process lifetime."""

    def find_process(self) -> ProcessIdentity | None:
        matches: list[ProcessIdentity] = []
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = process.info.get("name") or ""
                if name.casefold() not in PVZ_PROCESS_NAMES:
                    continue
                executable = process.info.get("exe")
                if executable and Path(executable).name.casefold() not in PVZ_PROCESS_NAMES:
                    continue
                matches.append(ProcessIdentity(int(process.info["pid"]), name, executable))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return min(matches, key=lambda item: item.process_id) if matches else None

    def is_alive(self, process_id: int) -> bool:
        try:
            process = psutil.Process(process_id)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False


class PvZSession:
    """Own a PID-bound reader and matching PvZ window across restarts.

    Attachment is deliberately controlled: :meth:`ensure_attached` performs at
    most one discovery/attach attempt per call. It never runs an internal retry
    loop. Exact binary version verification is not available, so the supported
    layout is reported but ``version_verified`` remains false.
    """

    def __init__(
        self,
        *,
        process_discovery: ProcessDiscovery | None = None,
        memory_factory: Callable[[int], Any] = MemoryReader,
        reader_factory: Callable[[Any], Any] = PvZGameStateReader,
        input_backend: WindowsInputBackend | None = None,
    ) -> None:
        self.process_discovery = process_discovery or PsutilProcessDiscovery()
        self.memory_factory = memory_factory
        self.reader_factory = reader_factory
        self.input_backend = input_backend or WindowsInputBackend()
        self._lock = RLock()
        self._process: ProcessIdentity | None = None
        self._memory: Any | None = None
        self._reader: Any | None = None
        self._window: GameWindowInfo | None = None
        self._generation = 0
        self._last_error: str | None = None

    @property
    def reader(self) -> Any | None:
        return self._reader

    @property
    def process_id(self) -> int | None:
        return None if self._process is None else self._process.process_id

    def find_process(self) -> ProcessIdentity | None:
        return self.process_discovery.find_process()

    def find_window(self) -> GameWindowInfo | None:
        with self._lock:
            return self._refresh_window()

    def attach(self) -> SessionStatus:
        """Attach once to the currently discoverable supported process."""
        with self._lock:
            if self._process is not None and self._memory is not None and self._is_process_alive():
                self._refresh_window()
                return self.status()
            self._detach_locked()
            process = self.find_process()
            if process is None:
                self._last_error = "process_not_found"
                return self.status()
            if not self.process_discovery.is_alive(process.process_id):
                self._last_error = "process_not_alive"
                return self.status()
            try:
                memory = self.memory_factory(process.process_id)
                reader = self.reader_factory(memory)
            except Exception as error:
                self._last_error = f"reader_attach_failed:{type(error).__name__}:{error}"
                LOGGER.error("Unable to attach PvZ reader to PID %s: %s", process.process_id, error)
                return self.status()
            self._process = process
            self._memory = memory
            self._reader = reader
            self.input_backend.process_name = process.name
            self.input_backend.bind_process(process.process_id)
            self._generation += 1
            self._last_error = None
            self._refresh_window()
            LOGGER.info("Attached to %s PID %s", process.name, process.process_id)
            return self.status()

    def ensure_attached(self) -> SessionStatus:
        """Validate the current PID and reconnect once if it has gone stale."""
        with self._lock:
            if self._reader is not None and self._is_process_alive():
                self._refresh_window()
                return self.status()
            if self._process is not None:
                LOGGER.warning("PvZ process PID %s is no longer alive", self._process.process_id)
            self._detach_locked()
            return self.attach()

    def reattach(self) -> SessionStatus:
        with self._lock:
            self._detach_locked()
            return self.attach()

    def detach(self) -> SessionStatus:
        with self._lock:
            self._detach_locked()
            return self.status()

    def read(self) -> SessionRead:
        """Read once from the current attachment; failures invalidate it."""
        with self._lock:
            status = self.ensure_attached()
            if not status.attached or self._reader is None:
                return SessionRead(None, False, status.last_error or "not_attached")
            try:
                state = self._reader.read()
            except Exception as error:
                message = f"reader_failed:{type(error).__name__}:{error}"
                LOGGER.warning("PvZ reader failed for PID %s: %s", self.process_id, error)
                self._last_error = message
                self._detach_locked(preserve_error=True)
                return SessionRead(None, False, message)
            self._last_error = None
            return SessionRead(state, True)

    def read_outcome(self) -> OutcomeEvidence:
        """Read lifecycle evidence from the PID-bound memory attachment."""
        with self._lock:
            status = self.ensure_attached()
            if not status.attached or self._memory is None:
                return OutcomeEvidence(
                    GameOutcome.UNKNOWN, "not_attached",
                    error=status.last_error or "not_attached",
                )
            return read_outcome(self._memory)

    def is_process_alive(self) -> bool:
        with self._lock:
            return self._is_process_alive()

    def is_window_valid(self) -> bool:
        with self._lock:
            window = self._refresh_window()
            return window is not None and not window.minimized and window.width > 0 and window.height > 0

    def is_focused(self) -> bool:
        with self._lock:
            try:
                return self.input_backend.is_foreground()
            except (GameWindowUnavailable, InputFailed):
                return False

    def focus_window(self) -> bool:
        with self._lock:
            try:
                focused = self.input_backend.focus_game()
            except (GameWindowUnavailable, InputFailed) as error:
                self._last_error = f"focus_failed:{error}"
                LOGGER.warning("Unable to focus PvZ window: %s", error)
                return False
            if not focused:
                self._last_error = "focus_failed:foreground_not_confirmed"
            elif self._last_error and self._last_error.startswith("focus_failed"):
                self._last_error = None
            return focused

    def status(self) -> SessionStatus:
        with self._lock:
            alive = self._is_process_alive()
            window = self._refresh_window() if alive else None
            valid = bool(
                window is not None
                and window.process_id == self.process_id
                and not window.minimized
                and window.width > 0
                and window.height > 0
            )
            focused = self.is_focused() if valid else False
            foreground_hwnd = None
            try:
                foreground_hwnd = self.input_backend.foreground_window()
            except (GameWindowUnavailable, InputFailed, AttributeError):
                pass
            return SessionStatus(
                attached=self._reader is not None and alive,
                process_alive=alive,
                process=self._process,
                window=window,
                window_valid=valid,
                focused=focused,
                supported_version=PVZ_VERSION,
                version_verified=False,
                generation=self._generation,
                last_error=self._last_error,
                foreground_hwnd=foreground_hwnd,
            )

    def _is_process_alive(self) -> bool:
        return bool(
            self._process is not None
            and self.process_discovery.is_alive(self._process.process_id)
        )

    def _refresh_window(self) -> GameWindowInfo | None:
        if self._process is None:
            self._window = None
            return None
        try:
            window = self.input_backend.get_window_info()
        except (GameWindowUnavailable, InputFailed) as error:
            self._window = None
            self._last_error = f"window_unavailable:{error}"
            return None
        if window.process_id != self._process.process_id:
            self._window = None
            self._last_error = "window_process_mismatch"
            return None
        self._window = window
        if self._last_error and self._last_error.startswith("window_"):
            self._last_error = None
        return window

    def _detach_locked(self, *, preserve_error: bool = False) -> None:
        memory = self._memory
        self._process = None
        self._memory = None
        self._reader = None
        self._window = None
        self.input_backend.bind_process(None)
        if not preserve_error:
            self._last_error = None
        if memory is not None:
            close = getattr(memory, "close", None)
            if close is not None:
                try:
                    close()
                except Exception as error:
                    LOGGER.warning("Failed to close PvZ process handle: %s", error)

    def __enter__(self) -> "PvZSession":
        self.attach()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.detach()
