"""Typed public configuration, results, health, and diagnostic models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from pvz_controller import ActionResult
from pvz_runtime.phase import GamePhase
from pvz_runtime.session import SessionStatus
from pvz_reader.outcome import OutcomeEvidence


class FocusMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


@dataclass(frozen=True)
class RuntimeConfig:
    focus_mode: FocusMode = FocusMode.MANUAL
    max_state_age_seconds: float = 0.5
    pause_timeout_seconds: float = 1.0
    pause_poll_interval_seconds: float = 0.05
    observer_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.focus_mode, FocusMode):
            object.__setattr__(self, "focus_mode", FocusMode(self.focus_mode))
        if self.max_state_age_seconds <= 0:
            raise ValueError("max_state_age_seconds must be positive")
        if self.pause_timeout_seconds < 0:
            raise ValueError("pause_timeout_seconds must be non-negative")
        if self.pause_poll_interval_seconds <= 0:
            raise ValueError("pause_poll_interval_seconds must be positive")


@dataclass(frozen=True)
class EnvironmentHealth:
    process_alive: bool
    window_valid: bool
    focused: bool
    reader_attached: bool
    reader_valid: bool
    controller_ready: bool
    board_valid: bool
    phase: GamePhase
    state_age_ms: float | None
    focus_mode: FocusMode
    observer_only: bool
    reasons: tuple[str, ...]

    @property
    def can_observe(self) -> bool:
        return (
            self.process_alive
            and self.reader_attached
            and self.reader_valid
            and self.board_valid
            and "state_stale" not in self.reasons
        )

    @property
    def can_act(self) -> bool:
        focus_ready = self.focused or self.focus_mode is FocusMode.AUTO
        return (
            self.can_observe
            and self.window_valid
            and self.controller_ready
            and focus_ready
            and self.phase is GamePhase.PLAYING
            and not self.observer_only
        )

    @property
    def ok(self) -> bool:
        return self.can_observe and (self.can_act or self.observer_only)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["phase"] = self.phase.value
        data["focus_mode"] = self.focus_mode.value
        data["reasons"] = list(self.reasons)
        data["can_observe"] = self.can_observe
        data["can_act"] = self.can_act
        data["ok"] = self.ok
        return data


class RuntimeActionType(str, Enum):
    PLANT = "plant"
    SHOVEL = "shovel"
    COLLECT_PICKUP = "collect_pickup"


@dataclass(frozen=True)
class RuntimeAction:
    action_type: RuntimeActionType
    seed_slot: int | None = None
    row: int | None = None
    col: int | None = None
    pickup_slot: int | None = None

    @classmethod
    def plant(cls, seed_slot: int, row: int, col: int) -> "RuntimeAction":
        return cls(RuntimeActionType.PLANT, seed_slot=seed_slot, row=row, col=col)

    @classmethod
    def shovel(cls, row: int, col: int) -> "RuntimeAction":
        return cls(RuntimeActionType.SHOVEL, row=row, col=col)

    @classmethod
    def collect_pickup(cls, pickup_slot: int) -> "RuntimeAction":
        return cls(RuntimeActionType.COLLECT_PICKUP, pickup_slot=pickup_slot)


class RuntimeActionStatus(str, Enum):
    ACTION_OK = "action_ok"
    ACTIONS_DISABLED = "actions_disabled"
    NOT_ATTACHED = "not_attached"
    PROCESS_DEAD = "process_dead"
    WINDOW_INVALID = "window_invalid"
    READER_INVALID = "reader_invalid"
    BOARD_INVALID = "board_invalid"
    STATE_STALE = "state_stale"
    FOCUS_REQUIRED = "focus_required"
    FOCUS_FAILED = "focus_failed"
    GAME_PAUSED = "game_paused"
    NOT_IN_PLAYABLE_PHASE = "not_in_playable_phase"
    INVALID_ACTION = "invalid_action"
    CONTROLLER_REJECTED = "controller_rejected"


@dataclass(frozen=True)
class RuntimeActionResult:
    status: RuntimeActionStatus
    reason: str
    action: RuntimeAction
    controller_result: ActionResult | None
    health: EnvironmentHealth

    @property
    def attempted(self) -> bool:
        return bool(self.controller_result and self.controller_result.attempted)

    @property
    def accepted(self) -> bool:
        return self.status is RuntimeActionStatus.ACTION_OK


class PauseStatus(str, Enum):
    CHANGED = "changed"
    ALREADY_SET = "already_set"
    NOT_ATTACHED = "not_attached"
    STATE_UNAVAILABLE = "state_unavailable"
    FOCUS_REQUIRED = "focus_required"
    FOCUS_FAILED = "focus_failed"
    INPUT_FAILED = "input_failed"
    TRANSITION_TIMEOUT = "transition_timeout"


@dataclass(frozen=True)
class PauseResult:
    status: PauseStatus
    desired_paused: bool
    observed_paused: bool | None
    reason: str

    @property
    def success(self) -> bool:
        return self.status in (PauseStatus.CHANGED, PauseStatus.ALREADY_SET)


@dataclass(frozen=True)
class GameStateSummary:
    adventure_level: int
    scene: int
    game_clock: int
    paused: bool
    sun: int
    wave: int
    total_waves: int
    plants: int
    zombies: int
    seeds: int
    pickups: int
    projectiles: int
    mowers: int

    @classmethod
    def from_state(cls, state: Any) -> "GameStateSummary":
        return cls(
            adventure_level=int(state.adventure_level), scene=int(state.scene),
            game_clock=int(state.game_clock), paused=bool(state.paused), sun=int(state.sun),
            wave=int(state.wave.spawned_waves), total_waves=int(state.wave.total_waves),
            plants=len(state.plants), zombies=len(state.zombies), seeds=len(state.seeds),
            pickups=len(state.pickups), projectiles=len(state.projectiles), mowers=len(state.mowers),
        )


@dataclass(frozen=True)
class RuntimeSnapshot:
    timestamp: float
    session: SessionStatus
    health: EnvironmentHealth
    phase: GamePhase
    game_state: GameStateSummary | None
    last_action: str | None
    last_error: str | None
    last_focus_result: str | None = None
    last_pause_result: str | None = None
    last_input_result: str | None = None
    outcome: OutcomeEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session": self.session.to_dict(),
            "health": self.health.to_dict(),
            "phase": self.phase.value,
            "game_state": None if self.game_state is None else asdict(self.game_state),
            "last_action": self.last_action,
            "last_error": self.last_error,
            "last_focus_result": self.last_focus_result,
            "last_pause_result": self.last_pause_result,
            "last_input_result": self.last_input_result,
            "outcome": None if self.outcome is None else self.outcome.to_dict(),
        }
