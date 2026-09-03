"""Dependency-light Tk monitor backed exclusively by :class:`PvZRuntime`."""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
import time
from typing import Callable

from pvz_runtime.models import FocusMode, PauseResult, RuntimeActionResult, RuntimeConfig, RuntimeSnapshot
from pvz_runtime.runtime import PvZRuntime
from pvz_runtime.session import SessionStatus


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitorJobResult:
    """One completed refresh or named operator command."""

    snapshot: RuntimeSnapshot
    operation: str | None = None
    status: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class _PendingCommand:
    name: str
    task: Callable[[], MonitorJobResult]


class MonitorJobQueue:
    """Serialize commands while coalescing disposable automatic refreshes."""

    def __init__(self, executor=None, *, max_pending_commands: int = 32) -> None:
        if max_pending_commands <= 0:
            raise ValueError("max_pending_commands must be positive")
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pvz-monitor"
        )
        self._max_pending_commands = max_pending_commands
        self._pending: deque[_PendingCommand] = deque()
        self._future: Future | None = None
        self._closing = False

    @property
    def busy(self) -> bool:
        return self._future is not None

    @property
    def pending_commands(self) -> int:
        return len(self._pending)

    def submit_command(self, name: str, task: Callable[[], MonitorJobResult]) -> bool:
        """Accept one user command or visibly reject it via ``False``."""
        if self._closing or len(self._pending) >= self._max_pending_commands:
            return False
        self._pending.append(_PendingCommand(name, task))
        self._start_next_command()
        return True

    def request_refresh(self, task: Callable[[], MonitorJobResult]) -> bool:
        """Start one refresh only when no command is queued or running."""
        if self._closing or self._future is not None or self._pending:
            return False
        self._future = self._executor.submit(task)
        return True

    def poll(self) -> MonitorJobResult | None:
        """Return one completed result and immediately prioritize commands."""
        if self._future is None or not self._future.done():
            return None
        future = self._future
        self._future = None
        try:
            return future.result()
        finally:
            self._start_next_command()

    def close(self, finalizer: Callable[[], object]) -> None:
        """Stop accepting work and close the runtime after active work ends."""
        if self._closing:
            return
        self._closing = True
        self._pending.clear()
        self._executor.submit(finalizer)
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _start_next_command(self) -> None:
        if self._closing or self._future is not None or not self._pending:
            return
        command = self._pending.popleft()
        self._future = self._executor.submit(command.task)


@dataclass(frozen=True)
class MonitorViewModel:
    """Presentation data kept testable without opening a GUI."""

    connection: str
    pid: str
    window: str
    title: str
    expected_hwnd: str
    foreground_hwnd: str
    focus: str
    focus_mode: str
    reader: str
    controller: str
    board: str
    phase: str
    adventure: str
    wave: str
    paused: str
    sun: str
    plants: str
    zombies: str
    pickups: str
    projectiles: str
    state_age: str
    last_operation: str
    operation_result: str
    operation_detail: str
    focus_result: str
    pause_result: str
    input_result: str
    last_action: str
    last_error: str

    @classmethod
    def from_snapshot(
        cls,
        snapshot: RuntimeSnapshot,
        operation: MonitorJobResult | None = None,
    ) -> "MonitorViewModel":
        session = snapshot.session
        health = snapshot.health
        state = snapshot.game_state
        return cls(
            connection="Connected" if session.attached else "Disconnected",
            pid="—" if session.process is None else str(session.process.process_id),
            window="Found" if session.window_valid else "Missing / unusable",
            title="—" if session.window is None else session.window.title,
            expected_hwnd="—" if session.window is None else str(session.window.hwnd),
            foreground_hwnd="—" if session.foreground_hwnd is None else str(session.foreground_hwnd),
            focus="Active" if session.focused else "Inactive",
            focus_mode=health.focus_mode.value.upper(),
            reader="Healthy" if health.reader_valid else "Unhealthy",
            controller="Ready" if health.controller_ready else "Not ready",
            board="Valid" if health.board_valid else "Invalid / unavailable",
            phase=snapshot.phase.value.upper(),
            adventure="—" if state is None else str(state.adventure_level),
            wave="—" if state is None else f"{state.wave}/{state.total_waves}",
            paused="—" if state is None else ("Yes" if state.paused else "No"),
            sun="—" if state is None else str(state.sun),
            plants="—" if state is None else str(state.plants),
            zombies="—" if state is None else str(state.zombies),
            pickups="—" if state is None else str(state.pickups),
            projectiles="—" if state is None else str(state.projectiles),
            state_age="—" if health.state_age_ms is None else f"{health.state_age_ms:.0f} ms",
            last_operation="—" if operation is None or operation.operation is None else operation.operation,
            operation_result="—" if operation is None or operation.status is None else operation.status,
            operation_detail="—" if operation is None or operation.detail is None else operation.detail,
            focus_result=snapshot.last_focus_result or "—",
            pause_result=snapshot.last_pause_result or "—",
            input_result=snapshot.last_input_result or "—",
            last_action=snapshot.last_action or "—",
            last_error=snapshot.last_error or "—",
        )


class RuntimeMonitor:
    """Small operator GUI; all behavior delegates to the shared runtime API."""

    REFRESH_MS = 500
    JOB_POLL_MS = 50

    def __init__(self, runtime_factory: Callable[[FocusMode], PvZRuntime] | None = None) -> None:
        self._runtime_factory = runtime_factory or (
            lambda mode: PvZRuntime(config=RuntimeConfig(focus_mode=mode))
        )
        self.runtime = self._runtime_factory(FocusMode.MANUAL)
        self.root = tk.Tk()
        self.root.title("PvZ Deep Learning — Environment Monitor")
        self.root.geometry("760x820")
        self._jobs = MonitorJobQueue()
        self._closing = False
        self._last_operation: MonitorJobResult | None = None
        self._next_refresh_at = 0.0
        self._focus_mode = tk.StringVar(value=FocusMode.MANUAL.value)
        self._text = tk.StringVar(value="Starting runtime monitor…")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame, text="PvZ Deep Learning — Environment Monitor",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(frame, textvariable=self._text, justify=tk.LEFT, font=("Consolas", 10)).pack(
            anchor=tk.W, fill=tk.BOTH, expand=True, pady=(12, 8)
        )
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)
        for label, command in (
            ("Focus Game", self._focus), ("Pause", self._pause), ("Resume", self._resume),
            ("Refresh / Reattach", self._reattach), ("Snapshot JSON", self._save_snapshot),
            ("Detach", self._detach),
        ):
            ttk.Button(controls, text=label, command=command).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(
            frame,
            text="Focus mode (GUI Pause/Resume normally require AUTO because clicking this window removes PvZ focus):",
        ).pack(anchor=tk.W, pady=(12, 0))
        selector = ttk.Combobox(
            frame, textvariable=self._focus_mode,
            values=(FocusMode.MANUAL.value, FocusMode.AUTO.value), state="readonly", width=12,
        )
        selector.pack(anchor=tk.W)
        selector.bind("<<ComboboxSelected>>", self._change_focus_mode)

    def run(self) -> None:
        self._submit("Attach", lambda: self.runtime.attach())
        self._schedule_refresh()
        self.root.mainloop()

    def _schedule_refresh(self) -> None:
        if self._closing:
            return
        try:
            completed = self._jobs.poll()
            if completed is not None:
                if completed.operation is not None:
                    self._last_operation = completed
                self._render(completed.snapshot)
        except Exception as error:
            LOGGER.exception("Runtime monitor operation failed")
            self._text.set(f"Operation failed: {type(error).__name__}: {error}")
        now = time.monotonic()
        if now >= self._next_refresh_at and self._jobs.request_refresh(self._refresh_job):
            self._next_refresh_at = now + self.REFRESH_MS / 1000.0
        self.root.after(self.JOB_POLL_MS, self._schedule_refresh)

    def _refresh_job(self) -> MonitorJobResult:
        return MonitorJobResult(self.runtime.refresh())

    def _render(self, snapshot: RuntimeSnapshot) -> None:
        model = MonitorViewModel.from_snapshot(snapshot, self._last_operation)
        self._text.set(self._format(model))

    @staticmethod
    def _format(model: MonitorViewModel) -> str:
        rows = (
            ("Process", model.connection), ("PID", model.pid), ("Window", model.window),
            ("Window title", model.title), ("Expected PvZ HWND", model.expected_hwnd),
            ("Foreground HWND", model.foreground_hwnd), ("Focus", model.focus),
            ("Focus mode", model.focus_mode), ("Reader", model.reader),
            ("Controller", model.controller), ("Board", model.board),
            ("Game phase", model.phase), ("Adventure", model.adventure),
            ("Wave", model.wave), ("Paused", model.paused), ("Sun", model.sun),
            ("Plants", model.plants), ("Zombies", model.zombies),
            ("Pickups", model.pickups), ("Projectiles", model.projectiles),
            ("State age", model.state_age), ("Last operation", model.last_operation),
            ("Result", model.operation_result), ("Detail", model.operation_detail),
            ("Latest focus", model.focus_result), ("Latest pause/resume", model.pause_result),
            ("Latest input", model.input_result), ("Last action", model.last_action),
            ("Last warning/error", model.last_error),
        )
        return "\n".join(f"{label:<22} {value}" for label, value in rows)

    @staticmethod
    def _describe_operation(name: str, result: object) -> tuple[str, str]:
        if isinstance(result, PauseResult):
            return result.status.value.upper(), result.reason
        if isinstance(result, RuntimeActionResult):
            return result.status.value.upper(), result.reason
        if isinstance(result, SessionStatus):
            if name == "Detach":
                return "DETACHED", result.last_error or "session_closed"
            return (
                ("ATTACHED", "session_ready") if result.attached
                else ("NOT_ATTACHED", result.last_error or "session_unavailable")
            )
        if isinstance(result, FocusMode):
            return "CHANGED", result.value
        if isinstance(result, bool):
            return ("FOCUSED", "foreground_confirmed") if result else (
                "FOCUS_FAILED", "foreground_not_confirmed"
            )
        if isinstance(result, (str, Path)):
            return "SAVED", str(result)
        return "COMPLETED", "operation_completed"

    def _run_operation(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        refresh: bool,
    ) -> MonitorJobResult:
        try:
            result = operation()
            status, detail = self._describe_operation(name, result)
        except Exception as error:
            LOGGER.exception("Runtime monitor command %s failed", name)
            status = "ERROR"
            detail = f"{type(error).__name__}: {error}"
        snapshot = self.runtime.refresh() if refresh else self.runtime.snapshot(refresh=False)
        return MonitorJobResult(snapshot, name, status, detail)

    def _submit(
        self,
        name: str,
        operation: Callable[[], object],
        *,
        refresh: bool = True,
    ) -> None:
        accepted = self._jobs.submit_command(
            name,
            lambda: self._run_operation(name, operation, refresh=refresh),
        )
        if not accepted and not self._closing:
            self._text.set(f"{name} rejected: command queue is full")

    def _focus(self) -> None:
        self._submit("Focus Game", lambda: self.runtime.focus_window())

    def _pause(self) -> None:
        self._submit("Pause", lambda: self.runtime.pause())

    def _resume(self) -> None:
        self._submit("Resume", lambda: self.runtime.resume())

    def _reattach(self) -> None:
        self._submit("Reattach", lambda: self.runtime.reattach())

    def _detach(self) -> None:
        self._submit("Detach", lambda: self.runtime.detach(), refresh=False)

    def _save_snapshot(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save PvZ runtime snapshot", defaultextension=".json",
            filetypes=(("JSON", "*.json"),),
        )
        if not path:
            return

        def save() -> str:
            snapshot = self.runtime.snapshot()
            Path(path).write_text(
                json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
            )
            return path

        self._submit("Snapshot JSON", save)

    def _change_focus_mode(self, _event=None) -> None:
        mode = FocusMode(self._focus_mode.get())

        def change() -> FocusMode:
            self.runtime.close()
            self.runtime = self._runtime_factory(mode)
            self.runtime.attach()
            return mode

        self._submit("Focus Mode", change)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._jobs.close(lambda: self.runtime.close())
        self.root.destroy()


def launch_monitor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    RuntimeMonitor().run()
