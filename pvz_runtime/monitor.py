"""Dependency-light Tk monitor backed exclusively by :class:`PvZRuntime`."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

from pvz_runtime.runtime import FocusMode, PvZRuntime, RuntimeConfig, RuntimeSnapshot


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitorViewModel:
    """Presentation data kept testable without opening a GUI."""

    connection: str
    pid: str
    window: str
    title: str
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
    last_action: str
    last_error: str

    @classmethod
    def from_snapshot(cls, snapshot: RuntimeSnapshot) -> "MonitorViewModel":
        session = snapshot.session
        health = snapshot.health
        state = snapshot.game_state
        return cls(
            connection="Connected" if session.attached else "Disconnected",
            pid="—" if session.process is None else str(session.process.process_id),
            window="Found" if session.window_valid else "Missing / unusable",
            title="—" if session.window is None else session.window.title,
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
            last_action=snapshot.last_action or "—",
            last_error=snapshot.last_error or "—",
        )


class RuntimeMonitor:
    """Small operator GUI; all behavior delegates to the shared runtime API."""

    REFRESH_MS = 500

    def __init__(self, runtime_factory: Callable[[FocusMode], PvZRuntime] | None = None) -> None:
        self._runtime_factory = runtime_factory or (
            lambda mode: PvZRuntime(config=RuntimeConfig(focus_mode=mode))
        )
        self.runtime = self._runtime_factory(FocusMode.MANUAL)
        self.root = tk.Tk()
        self.root.title("PvZ Deep Learning — Environment Monitor")
        self.root.geometry("700x650")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pvz-monitor")
        self._future: Future | None = None
        self._closing = False
        self._focus_mode = tk.StringVar(value=FocusMode.MANUAL.value)
        self._text = tk.StringVar(value="Starting runtime monitor…")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="PvZ Deep Learning — Environment Monitor", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
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
        ttk.Label(frame, text="Focus mode:").pack(anchor=tk.W, pady=(12, 0))
        selector = ttk.Combobox(
            frame, textvariable=self._focus_mode,
            values=(FocusMode.MANUAL.value, FocusMode.AUTO.value), state="readonly", width=12,
        )
        selector.pack(anchor=tk.W)
        selector.bind("<<ComboboxSelected>>", self._change_focus_mode)

    def run(self) -> None:
        self._future = self._executor.submit(self._attach_and_refresh)
        self._schedule_refresh()
        self.root.mainloop()

    def _attach_and_refresh(self) -> RuntimeSnapshot:
        self.runtime.attach()
        return self.runtime.refresh()

    def _schedule_refresh(self) -> None:
        if self._closing:
            return
        if self._future is None:
            self._future = self._executor.submit(self.runtime.refresh)
        elif self._future.done():
            try:
                model = MonitorViewModel.from_snapshot(self._future.result())
                self._text.set(self._format(model))
            except Exception as error:
                LOGGER.exception("Runtime monitor refresh failed")
                self._text.set(f"Refresh failed: {type(error).__name__}: {error}")
            self._future = None
        self.root.after(self.REFRESH_MS, self._schedule_refresh)

    @staticmethod
    def _format(model: MonitorViewModel) -> str:
        rows = (
            ("Process", model.connection), ("PID", model.pid), ("Window", model.window),
            ("Window title", model.title), ("Focus", model.focus), ("Focus mode", model.focus_mode),
            ("Reader", model.reader), ("Controller", model.controller), ("Board", model.board),
            ("Game phase", model.phase), ("Adventure", model.adventure), ("Wave", model.wave),
            ("Paused", model.paused), ("Sun", model.sun), ("Plants", model.plants),
            ("Zombies", model.zombies), ("Pickups", model.pickups),
            ("Projectiles", model.projectiles), ("State age", model.state_age),
            ("Last action", model.last_action), ("Last warning/error", model.last_error),
        )
        return "\n".join(f"{label:<20} {value}" for label, value in rows)

    def _submit(self, operation: Callable[[], object], *, refresh: bool = True) -> None:
        if self._future is None:
            def task() -> RuntimeSnapshot:
                operation()
                return self.runtime.refresh() if refresh else self.runtime.snapshot(refresh=False)

            self._future = self._executor.submit(task)

    def _focus(self) -> None:
        self._submit(self.runtime.focus_window)

    def _pause(self) -> None:
        self._submit(self.runtime.pause)

    def _resume(self) -> None:
        self._submit(self.runtime.resume)

    def _reattach(self) -> None:
        self._submit(self.runtime.reattach)

    def _detach(self) -> None:
        self._submit(self.runtime.detach, refresh=False)

    def _save_snapshot(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save PvZ runtime snapshot", defaultextension=".json",
            filetypes=(("JSON", "*.json"),),
        )
        if not path:
            return

        def save() -> None:
            snapshot = self.runtime.snapshot()
            Path(path).write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

        self._submit(save)

    def _change_focus_mode(self, _event=None) -> None:
        mode = FocusMode(self._focus_mode.get())

        def change() -> None:
            self.runtime.close()
            self.runtime = self._runtime_factory(mode)
            self.runtime.attach()

        self._submit(change)

    def close(self) -> None:
        self._closing = True
        self.runtime.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def launch_monitor() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    RuntimeMonitor().run()
