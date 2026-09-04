"""Small, dependency-free lifecycle composition for repeated RL episodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import time
from typing import Any, Protocol

from pvz_reader.outcome import GameOutcome, OutcomeEvidence
from pvz_runtime.models import RuntimeAction


class ResetStatus(str, Enum):
    RESET_OK = "reset_ok"
    NOT_ATTACHED = "not_attached"
    UNHEALTHY = "unhealthy"
    UNSUPPORTED_STATE = "unsupported_state"
    RESET_CONTROL_FAILED = "reset_control_failed"
    BOARD_NOT_REPLACED = "board_not_replaced"
    WRONG_LEVEL = "wrong_level"
    SEED_BANK_MISMATCH = "seed_bank_mismatch"
    STALE_ENTITIES = "stale_entities"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ResetExpectation:
    adventure_level: int
    seed_type_ids: tuple[int, ...] | None = None
    max_initial_game_clock: int = 250
    require_empty_entities: bool = True


@dataclass(frozen=True)
class ResetControlResult:
    requested: bool
    reason: str


@dataclass(frozen=True)
class ResetResult:
    status: ResetStatus
    reason: str
    previous_board_address: int | None
    board_address: int | None
    observed_level: int | None = None
    observed_game_clock: int | None = None

    @property
    def success(self) -> bool:
        return self.status is ResetStatus.RESET_OK

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class RestartDriver(Protocol):
    """One explicit, state-aware mechanism that requests current-level restart."""

    def request_restart(self, runtime: Any) -> ResetControlResult: ...


class UnsupportedRestartDriver:
    """Fail-closed default until a target-specific driver is live validated."""

    def request_restart(self, runtime: Any) -> ResetControlResult:
        return ResetControlResult(False, "no_live_validated_restart_driver")


class CallbackRestartDriver:
    """Adapter for a tested operator or target-specific restart callback."""

    def __init__(self, callback: Any) -> None:
        self.callback = callback

    def request_restart(self, runtime: Any) -> ResetControlResult:
        try:
            requested = bool(self.callback(runtime))
        except Exception as error:
            return ResetControlResult(False, f"callback_failed:{type(error).__name__}:{error}")
        return ResetControlResult(requested, "restart_requested" if requested else "callback_refused")


@dataclass
class PickupMetrics:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    pickups_collected: int = 0
    sun_pickups_collected: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class ManagedPickupCollector:
    """Synchronous pickup collection through PvZRuntime's action executor."""

    def __init__(self, runtime: Any, *, enabled: bool = True,
                 allowed_type_ids: tuple[int, ...] = (1, 2, 3, 4, 5, 6)) -> None:
        self.runtime = runtime
        self.enabled = enabled
        self.allowed_type_ids = frozenset(allowed_type_ids)
        self.metrics = PickupMetrics()
        self._pending: dict[tuple[Any, ...], bool] = {}
        self._attempted: set[tuple[Any, ...]] = set()

    @staticmethod
    def _identity(board: int | None, pickup: Any) -> tuple[Any, ...]:
        return (board, int(pickup.slot), int(pickup.type_id), round(float(pickup.x)), round(float(pickup.y)))

    def collect_once(self) -> PickupMetrics:
        return self.runtime.run_serialized(self._collect_locked)

    def _collect_locked(self, runtime: Any) -> PickupMetrics:
        if not self.enabled:
            return self.metrics
        state = runtime.observe()
        health = runtime.health
        if state is None or not health.can_act:
            return self.metrics
        evidence = runtime.outcome()
        if evidence.outcome is not GameOutcome.RUNNING:
            return self.metrics
        current = {
            self._identity(evidence.board_address, pickup)
            for pickup in state.pickups if bool(pickup.collectible)
        }
        for identity, is_sun in tuple(self._pending.items()):
            if identity not in current:
                self.metrics.pickups_collected += 1
                if is_sun:
                    self.metrics.sun_pickups_collected += 1
                del self._pending[identity]
        self._attempted.intersection_update(current)
        for pickup in state.pickups:
            identity = self._identity(evidence.board_address, pickup)
            if (
                identity in self._attempted
                or not bool(pickup.collectible)
                or int(pickup.type_id) not in self.allowed_type_ids
            ):
                continue
            self.metrics.attempts += 1
            self._attempted.add(identity)
            result = runtime.execute(RuntimeAction.collect_pickup(int(pickup.slot)))
            if result.accepted:
                self.metrics.successes += 1
                self._pending[identity] = bool(pickup.is_sun)
            else:
                self.metrics.failures += 1
                break
        return self.metrics

    def shutdown(self) -> None:
        self.enabled = False
        self._pending.clear()
        self._attempted.clear()


class TrainingEpisodeSupport:
    """Outcome, verified reset, and managed pickups; no RL dependency."""

    def __init__(self, runtime: Any, *, restart_driver: RestartDriver | None = None,
                 auto_collect_pickups: bool = False, reset_timeout_seconds: float = 10.0,
                 reset_poll_interval_seconds: float = 0.1,
                 sleeper: Any = time.sleep) -> None:
        self.runtime = runtime
        self.restart_driver = restart_driver or UnsupportedRestartDriver()
        self.pickups = ManagedPickupCollector(runtime, enabled=auto_collect_pickups)
        self.reset_timeout_seconds = reset_timeout_seconds
        self.reset_poll_interval_seconds = reset_poll_interval_seconds
        self._sleeper = sleeper

    def outcome(self) -> OutcomeEvidence:
        return self.runtime.outcome()

    def reset_current_level(self, expectation: ResetExpectation) -> ResetResult:
        return self.runtime.run_serialized(lambda runtime: self._reset_locked(runtime, expectation))

    def _reset_locked(self, runtime: Any, expectation: ResetExpectation) -> ResetResult:
        state = runtime.observe()
        before = runtime.outcome()
        if state is None or not runtime.health.can_observe:
            return ResetResult(ResetStatus.NOT_ATTACHED, "state_unavailable", before.board_address, None)
        if before.outcome not in (GameOutcome.RUNNING, GameOutcome.WON, GameOutcome.LOST):
            return ResetResult(ResetStatus.UNSUPPORTED_STATE, before.reason, before.board_address, before.board_address)
        control = self.restart_driver.request_restart(runtime)
        if not control.requested:
            return ResetResult(ResetStatus.RESET_CONTROL_FAILED, control.reason, before.board_address, before.board_address)

        waited = 0.0
        last_board = before.board_address
        while waited <= self.reset_timeout_seconds:
            state = runtime.observe()
            after = runtime.outcome()
            last_board = after.board_address
            if not runtime.health.process_alive:
                return ResetResult(ResetStatus.NOT_ATTACHED, "process_gone", before.board_address, last_board)
            if state is not None and after.board_address not in (None, before.board_address):
                level = int(state.adventure_level)
                clock = int(state.game_clock)
                if level != expectation.adventure_level:
                    return ResetResult(ResetStatus.WRONG_LEVEL, "adventure_level_mismatch", before.board_address, last_board, level, clock)
                if expectation.seed_type_ids is not None:
                    seeds = tuple(int(seed.type_id) for seed in state.seeds)
                    if seeds != expectation.seed_type_ids:
                        return ResetResult(ResetStatus.SEED_BANK_MISMATCH, "seed_bank_mismatch", before.board_address, last_board, level, clock)
                if expectation.require_empty_entities and (state.plants or state.zombies):
                    return ResetResult(ResetStatus.STALE_ENTITIES, "fresh_board_contains_entities", before.board_address, last_board, level, clock)
                if clock <= expectation.max_initial_game_clock and not bool(state.paused) and runtime.health.can_observe:
                    return ResetResult(ResetStatus.RESET_OK, "fresh_same_level_board_verified", before.board_address, last_board, level, clock)
            if waited == self.reset_timeout_seconds:
                break
            interval = min(self.reset_poll_interval_seconds, self.reset_timeout_seconds - waited)
            self._sleeper(interval)
            waited += interval
        status = ResetStatus.BOARD_NOT_REPLACED if last_board == before.board_address else ResetStatus.TIMEOUT
        return ResetResult(status, "reset_verification_timeout", before.board_address, last_board)

    def shutdown(self) -> None:
        self.pickups.shutdown()
