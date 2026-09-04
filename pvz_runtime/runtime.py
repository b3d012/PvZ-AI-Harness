"""Fail-closed runtime facade above reader, window, and Controller v1."""

from __future__ import annotations

import logging
from threading import RLock
import time
from typing import Any, Callable, TypeVar

from pvz_controller import ActionResult, PvZController
from pvz_controller.windows_input import ControllerInputError, WindowsInputBackend
from pvz_runtime.phase import GamePhase, GamePhaseDetector, PhaseEvidence
from pvz_runtime.models import (
    EnvironmentHealth,
    FocusMode,
    GameStateSummary,
    PauseResult,
    PauseStatus,
    RuntimeAction,
    RuntimeActionResult,
    RuntimeActionStatus,
    RuntimeActionType,
    RuntimeConfig,
    RuntimeSnapshot,
)
from pvz_runtime.session import PvZSession, SessionRead, SessionStatus
from pvz_reader.outcome import GameOutcome, OutcomeEvidence


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class PvZRuntime:
    """Production runtime boundary beneath frozen Environment v1.

    The runtime serializes attach/read/focus/input operations with one reentrant
    lock. It has no background thread and no autonomous input behavior.
    """

    def __init__(
        self,
        session: PvZSession | None = None,
        controller: Any | None = None,
        *,
        config: RuntimeConfig | None = None,
        phase_detector: GamePhaseDetector | None = None,
        terminal_phase_provider: Callable[[Any], GamePhase | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or RuntimeConfig()
        if session is None:
            backend = WindowsInputBackend(auto_focus=self.config.focus_mode is FocusMode.AUTO)
            session = PvZSession(input_backend=backend)
        self.session = session
        self.session.input_backend.set_auto_focus(self.config.focus_mode is FocusMode.AUTO)
        self.controller = controller or PvZController(self.session.input_backend)
        self.phase_detector = phase_detector or GamePhaseDetector()
        self._terminal_phase_provider = terminal_phase_provider
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleeper = sleeper
        self._lock = RLock()
        self._last_state: Any | None = None
        self._last_state_at: float | None = None
        self._last_reader_valid = False
        self._last_error: str | None = None
        self._last_action: str | None = None
        self._last_focus_result: str | None = None
        self._last_pause_result: str | None = None
        self._last_input_result: str | None = None
        self._last_outcome: OutcomeEvidence | None = None

    @property
    def focus_mode(self) -> FocusMode:
        return self.config.focus_mode

    @property
    def phase(self) -> GamePhase:
        return self.phase_detector.phase

    @property
    def health(self) -> EnvironmentHealth:
        with self._lock:
            return self._build_health(self.session.status())

    def attach(self) -> SessionStatus:
        with self._lock:
            return self.session.attach()

    def detach(self) -> SessionStatus:
        with self._lock:
            self._clear_observation()
            self.phase_detector.reset()
            return self.session.detach()

    def reattach(self) -> SessionStatus:
        with self._lock:
            self._clear_observation()
            self.phase_detector.reset()
            return self.session.reattach()

    def observe(self) -> Any | None:
        """Return a fresh GameState or ``None`` while retaining diagnostics."""
        with self._lock:
            read = self.session.read()
            self._record_read(read)
            return read.state

    def outcome(self) -> OutcomeEvidence:
        """Return fresh typed natural-terminal evidence."""
        with self._lock:
            self._last_outcome = self.session.read_outcome()
            return self._last_outcome

    def run_serialized(self, operation: Callable[["PvZRuntime"], T]) -> T:
        """Run a bounded composite operation under the single input lock."""
        with self._lock:
            return operation(self)

    def refresh(self) -> RuntimeSnapshot:
        with self._lock:
            self.observe()
            return self.snapshot(refresh=False)

    def is_playable(self) -> bool:
        return self.health.can_act

    def is_episode_active(self) -> bool:
        return self.phase in (GamePhase.READY, GamePhase.PLAYING, GamePhase.PAUSED)

    def is_terminal(self) -> bool:
        return self.phase.is_terminal

    def focus_window(self) -> bool:
        """Explicit operator request to focus PvZ, regardless of focus mode."""
        with self._lock:
            focused = self.session.focus_window()
            if focused:
                self._last_focus_result = "focused:foreground_confirmed"
                if self._last_error and self._last_error.startswith("focus_failed"):
                    self._last_error = None
            else:
                self._last_focus_result = "focus_failed:foreground_not_confirmed"
                self._last_error = self.session.status().last_error or "focus_failed"
            return focused

    def ensure_focus(self) -> RuntimeActionStatus:
        with self._lock:
            status = self.session.status()
            if not status.window_valid:
                self._last_focus_result = "window_invalid"
                return RuntimeActionStatus.WINDOW_INVALID
            if status.focused:
                self._last_focus_result = "already_focused:foreground_confirmed"
                return RuntimeActionStatus.ACTION_OK
            if self.focus_mode is FocusMode.MANUAL:
                self._last_focus_result = "focus_required:manual_mode"
                return RuntimeActionStatus.FOCUS_REQUIRED
            if self.session.focus_window():
                self._last_focus_result = "focused:foreground_confirmed"
                return RuntimeActionStatus.ACTION_OK
            self._last_focus_result = "focus_failed:foreground_not_confirmed"
            return RuntimeActionStatus.FOCUS_FAILED

    def execute(self, action: RuntimeAction) -> RuntimeActionResult:
        """Execute one semantic Controller v1 action through fail-closed gates."""
        if not isinstance(action, RuntimeAction):
            raise TypeError("action must be a RuntimeAction")
        with self._lock:
            self.observe()
            health = self.health
            rejection = self._action_rejection(health)
            if rejection is not None:
                return self._action_result(rejection, rejection.value, action, None, health)
            focus = self.ensure_focus()
            if focus is not RuntimeActionStatus.ACTION_OK:
                return self._action_result(focus, focus.value, action, None, self.health)

            # Focus changes can race with menus and pause toggles. Re-read and
            # re-run every state gate immediately before Controller v1.
            self.observe()
            health = self.health
            rejection = self._action_rejection(health)
            if rejection is not None:
                return self._action_result(rejection, rejection.value, action, None, health)
            try:
                controller_result = self._dispatch(action, self._last_state)
            except (TypeError, ValueError) as error:
                return self._action_result(
                    RuntimeActionStatus.INVALID_ACTION, str(error), action, None, health
                )
            status = (
                RuntimeActionStatus.ACTION_OK
                if controller_result.attempted and controller_result.success is not False
                else RuntimeActionStatus.CONTROLLER_REJECTED
            )
            return self._action_result(status, controller_result.reason, action, controller_result, health)

    def pause(self) -> PauseResult:
        return self.set_paused(True)

    def resume(self) -> PauseResult:
        return self.set_paused(False)

    def set_paused(self, desired_paused: bool) -> PauseResult:
        """Idempotently set pause state using one verified Escape key press."""
        if not isinstance(desired_paused, bool):
            raise TypeError("desired_paused must be bool")
        with self._lock:
            state = self.observe()
            if not self.session.status().attached:
                return self._pause_result(
                    PauseStatus.NOT_ATTACHED, desired_paused, None, "not_attached", "not_sent"
                )
            if state is None:
                return self._pause_result(
                    PauseStatus.STATE_UNAVAILABLE, desired_paused, None,
                    "board_unavailable", "not_sent",
                )
            current = bool(state.paused)
            if current is desired_paused:
                return self._pause_result(
                    PauseStatus.ALREADY_SET, desired_paused, current, "already_set", "not_sent"
                )
            focus = self.ensure_focus()
            if focus is RuntimeActionStatus.FOCUS_REQUIRED:
                return self._pause_result(
                    PauseStatus.FOCUS_REQUIRED, desired_paused, current,
                    "manual_mode_requires_pvz_foreground", "not_sent",
                )
            if focus is not RuntimeActionStatus.ACTION_OK:
                return self._pause_result(
                    PauseStatus.FOCUS_FAILED, desired_paused, current,
                    "foreground_not_confirmed", "not_sent",
                )
            try:
                self.session.input_backend.press_escape()
            except ControllerInputError as error:
                return self._pause_result(
                    PauseStatus.INPUT_FAILED, desired_paused, current, str(error), "input_failed"
                )
            self._last_input_result = "escape_sent"

            waited = 0.0
            while True:
                state = self.observe()
                if state is not None and bool(state.paused) is desired_paused:
                    return self._pause_result(
                        PauseStatus.CHANGED, desired_paused, desired_paused,
                        "state_verified", "escape_sent",
                    )
                if waited >= self.config.pause_timeout_seconds:
                    observed = None if state is None else bool(state.paused)
                    return self._pause_result(
                        PauseStatus.TRANSITION_TIMEOUT, desired_paused, observed,
                        "pause state did not reach requested value", "escape_sent",
                    )
                interval = min(
                    self.config.pause_poll_interval_seconds,
                    self.config.pause_timeout_seconds - waited,
                )
                self._sleeper(interval)
                waited += interval

    def snapshot(self, *, refresh: bool = True) -> RuntimeSnapshot:
        with self._lock:
            if refresh:
                self.observe()
            session = self.session.status()
            health = self._build_health(session)
            summary = None
            if self._last_state is not None:
                try:
                    summary = GameStateSummary.from_state(self._last_state)
                except (AttributeError, TypeError, ValueError):
                    self._last_error = "invalid_game_state_summary"
            return RuntimeSnapshot(
                timestamp=self._wall_clock(), session=session, health=health,
                phase=self.phase, game_state=summary, last_action=self._last_action,
                last_error=self._last_error or session.last_error,
                last_focus_result=self._last_focus_result,
                last_pause_result=self._last_pause_result,
                last_input_result=self._last_input_result,
                outcome=self._last_outcome,
            )

    def reader_adapter(self) -> "RuntimeReaderAdapter":
        return RuntimeReaderAdapter(self)

    def controller_adapter(self) -> "RuntimePlantControllerAdapter":
        return RuntimePlantControllerAdapter(self)

    def close(self) -> None:
        self.detach()

    def _record_read(self, read: SessionRead) -> None:
        status = self.session.status()
        self._last_reader_valid = read.reader_valid
        self._last_error = read.error
        if read.state is not None:
            self._last_state = read.state
            self._last_state_at = self._clock()
        else:
            self._last_state = None
            self._last_state_at = None
        old = self.phase
        terminal_hint = None
        if read.state is not None and self._terminal_phase_provider is not None:
            terminal_hint = self._terminal_phase_provider(read.state)
        elif status.attached:
            self._last_outcome = self.session.read_outcome()
            if self._last_outcome.outcome is GameOutcome.WON:
                terminal_hint = GamePhase.LEVEL_WON
            elif self._last_outcome.outcome is GameOutcome.LOST:
                terminal_hint = GamePhase.LEVEL_LOST
        new = self.phase_detector.detect(
            PhaseEvidence(status.process_alive, read.reader_valid, read.state, terminal_hint)
        )
        if new is not old:
            LOGGER.info("Game phase changed %s -> %s", old.value, new.value)

    def _build_health(self, session: SessionStatus) -> EnvironmentHealth:
        now = self._clock()
        age_ms = None if self._last_state_at is None else max(0.0, (now - self._last_state_at) * 1000.0)
        reasons: list[str] = []
        if not session.process_alive:
            reasons.append("process_dead")
        if not session.attached:
            reasons.append("reader_not_attached")
        if not self._last_reader_valid:
            reasons.append("reader_invalid")
        if self._last_state is None:
            reasons.append("board_invalid")
        if age_ms is not None and age_ms > self.config.max_state_age_seconds * 1000.0:
            reasons.append("state_stale")
        if not session.window_valid:
            reasons.append("window_invalid")
        if not session.focused:
            reasons.append("focus_inactive")
        if self.phase is GamePhase.PAUSED:
            reasons.append("game_paused")
        elif self.phase not in (GamePhase.READY, GamePhase.PLAYING):
            reasons.append("not_playable")
        if self.config.observer_only:
            reasons.append("observer_only")
        return EnvironmentHealth(
            process_alive=session.process_alive,
            window_valid=session.window_valid,
            focused=session.focused,
            reader_attached=session.attached,
            reader_valid=self._last_reader_valid,
            controller_ready=session.window_valid,
            board_valid=self._last_state is not None,
            phase=self.phase,
            state_age_ms=age_ms,
            focus_mode=self.focus_mode,
            observer_only=self.config.observer_only,
            reasons=tuple(reasons),
        )

    def _action_rejection(self, health: EnvironmentHealth) -> RuntimeActionStatus | None:
        if self.config.observer_only:
            return RuntimeActionStatus.ACTIONS_DISABLED
        if not health.process_alive:
            return RuntimeActionStatus.PROCESS_DEAD
        if not health.reader_attached:
            return RuntimeActionStatus.NOT_ATTACHED
        if not health.reader_valid:
            return RuntimeActionStatus.READER_INVALID
        if not health.board_valid:
            return RuntimeActionStatus.BOARD_INVALID
        if "state_stale" in health.reasons:
            return RuntimeActionStatus.STATE_STALE
        if not health.window_valid:
            return RuntimeActionStatus.WINDOW_INVALID
        if health.phase is GamePhase.PAUSED:
            return RuntimeActionStatus.GAME_PAUSED
        if health.phase is not GamePhase.PLAYING:
            return RuntimeActionStatus.NOT_IN_PLAYABLE_PHASE
        return None

    def _dispatch(self, action: RuntimeAction, state: Any) -> ActionResult:
        if action.action_type is RuntimeActionType.PLANT:
            if action.seed_slot is None or action.row is None or action.col is None:
                raise ValueError("plant requires seed_slot, row, and col")
            return self.controller.plant(state, action.seed_slot, action.row, action.col)
        if action.action_type is RuntimeActionType.SHOVEL:
            if action.row is None or action.col is None:
                raise ValueError("shovel requires row and col")
            return self.controller.shovel(state, action.row, action.col)
        if action.action_type is RuntimeActionType.COLLECT_PICKUP:
            if action.pickup_slot is None:
                raise ValueError("collect_pickup requires pickup_slot")
            return self.controller.collect_pickup(state, action.pickup_slot)
        raise ValueError(f"unsupported action type: {action.action_type!r}")

    def _action_result(
        self,
        status: RuntimeActionStatus,
        reason: str,
        action: RuntimeAction,
        controller_result: ActionResult | None,
        health: EnvironmentHealth,
    ) -> RuntimeActionResult:
        self._last_action = f"{action.action_type.value}:{status.value}:{reason}"
        if status is not RuntimeActionStatus.ACTION_OK:
            self._last_error = self._last_action
            LOGGER.warning("Runtime action refused: %s", self._last_action)
        return RuntimeActionResult(status, reason, action, controller_result, health)

    def _pause_result(
        self,
        status: PauseStatus,
        desired_paused: bool,
        observed_paused: bool | None,
        reason: str,
        input_result: str,
    ) -> PauseResult:
        result = PauseResult(status, desired_paused, observed_paused, reason)
        self._last_pause_result = f"{status.value}:{reason}"
        self._last_input_result = input_result
        if result.success:
            if self._last_error and self._last_error.startswith("pause_"):
                self._last_error = None
        else:
            self._last_error = f"pause_{status.value}:{reason}"
        return result

    def _clear_observation(self) -> None:
        self._last_state = None
        self._last_state_at = None
        self._last_reader_valid = False
        self._last_error = None
        self._last_outcome = None

    def __enter__(self) -> "PvZRuntime":
        self.attach()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


class RuntimeReaderAdapter:
    """StateReader adapter for the frozen ``pvz_env.PvZEnvironment``."""

    def __init__(self, runtime: PvZRuntime) -> None:
        self.runtime = runtime

    def read(self) -> Any | None:
        return self.runtime.observe()


class RuntimePlantControllerAdapter:
    """PlantController adapter that preserves runtime gates beneath Environment v1."""

    def __init__(self, runtime: PvZRuntime) -> None:
        self.runtime = runtime

    def plant(self, state: Any, seed_slot: int, row: int, col: int) -> ActionResult:
        result = self.runtime.execute(RuntimeAction.plant(seed_slot, row, col))
        if result.controller_result is not None:
            return result.controller_result
        return ActionResult(False, False, f"runtime_rejected:{result.status.value}:{result.reason}")
