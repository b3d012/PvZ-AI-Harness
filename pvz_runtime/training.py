"""Small, dependency-free lifecycle composition for repeated RL episodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import time
from typing import Any, Protocol

from pvz_reader.outcome import GameOutcome, OutcomeEvidence
from pvz_controller.windows_input import ControllerInputError
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


class NormalUiRestartDriver:
    """Version-pinned, fail-closed driver for PvZ's normal restart controls.

    This is deliberately not a menu navigator. It restarts an attached 800x600
    board only through the in-game Menu -> Restart Level -> confirmation
    sequence, or accepts native Try Again after a loss. A live, authoritative
    reward-pending win uses the same normal Menu path; a torn-down Award Board
    is refused without input.
    """

    MENU_BUTTON = (739, 13)
    RESTART_LEVEL_BUTTON = (400, 358)
    TRY_AGAIN_BUTTON = (384, 369)
    CLIENT_SIZE = (800, 600)
    # GOTY 1.2.0.1073 accepted Menu only after cursor relocation had settled
    # for 100 ms. This is deliberately UI-driver-local: board controller
    # actions retain their established immediate-click behavior.
    UI_CONTROL_MOVE_SETTLE_DELAY = 0.10
    # Native CutScene::UpdateZombiesWon creates the Game Over dialog at
    # mCutsceneTime == 11000. This bound is separate from cursor settling.
    LOSS_SCREEN_READY_TIMEOUT_SECONDS = 15.0

    def __init__(self, *, transition_timeout_seconds: float = 1.0,
                 poll_interval_seconds: float = 0.05, sleeper: Any = time.sleep,
                 known_pause_menu: bool = False,
                 loss_screen_ready_timeout_seconds: float = LOSS_SCREEN_READY_TIMEOUT_SECONDS) -> None:
        self.transition_timeout_seconds = transition_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.loss_screen_ready_timeout_seconds = loss_screen_ready_timeout_seconds
        self._sleeper = sleeper
        # Only an explicit caller attestation from a preceding Menu probe may
        # enable this; GameState.paused alone is insufficient UI provenance.
        self.known_pause_menu = known_pause_menu

    def request_restart(self, runtime: Any) -> ResetControlResult:
        before_state = runtime.observe()
        before = runtime.outcome()
        if before_state is None:
            return ResetControlResult(False, "state_unavailable")
        if getattr(runtime.config, "observer_only", False):
            return ResetControlResult(False, "observer_only_runtime")
        if not runtime.health.process_alive or not runtime.health.window_valid:
            return ResetControlResult(False, "runtime_not_input_ready")
        if before.outcome is GameOutcome.WON:
            if before.board_address is None:
                return ResetControlResult(False, "won_board_unavailable")
            if not self._validate_client(runtime):
                return ResetControlResult(False, "unsupported_client_geometry")
            if bool(before_state.paused):
                if not self.known_pause_menu:
                    return ResetControlResult(False, "paused_menu_not_verified")
                return self._restart_open_menu(runtime, before)
            return self._restart_playing(runtime, before)
        if before.outcome is GameOutcome.LOST:
            return self._restart_lost(runtime, before)
        if before.outcome is not GameOutcome.RUNNING:
            return ResetControlResult(False, f"unsupported_outcome:{before.outcome.value}")
        if not self._validate_client(runtime):
            return ResetControlResult(False, "unsupported_client_geometry")
        if bool(before_state.paused):
            # GameState records pause, not the owning modal. Restart Level is
            # safe only when this driver opened the normal Menu itself; an
            # externally paused board could be a different dialog/state.
            if not self.known_pause_menu:
                return ResetControlResult(False, "paused_menu_not_verified")
            return self._restart_open_menu(runtime, before)
        return self._restart_playing(runtime, before)

    def _validate_client(self, runtime: Any) -> bool:
        try:
            area = runtime.session.input_backend.get_client_area()
        except ControllerInputError:
            return False
        return (int(area.width), int(area.height)) == self.CLIENT_SIZE

    def _restart_playing(self, runtime: Any, before: OutcomeEvidence) -> ResetControlResult:
        if not self._is_live_board(runtime, before, paused=False):
            return ResetControlResult(False, "playing_state_not_verified")
        try:
            runtime.session.input_backend.left_click(
                *self.MENU_BUTTON,
                move_settle_delay=self.UI_CONTROL_MOVE_SETTLE_DELAY,
            )
        except ControllerInputError as error:
            return ResetControlResult(False, f"menu_input_failed:{type(error).__name__}:{error}")
        if not self._wait_for(runtime, before, paused=True):
            return ResetControlResult(False, "menu_transition_not_verified")
        return self._restart_open_menu(runtime, before)

    def _restart_open_menu(self, runtime: Any, before: OutcomeEvidence) -> ResetControlResult:
        if not self._is_live_board(runtime, before, paused=True):
            return ResetControlResult(False, "menu_state_not_verified")
        try:
            runtime.session.input_backend.left_click(
                *self.RESTART_LEVEL_BUTTON,
                move_settle_delay=self.UI_CONTROL_MOVE_SETTLE_DELAY,
            )
        except ControllerInputError as error:
            return ResetControlResult(False, f"restart_input_failed:{type(error).__name__}:{error}")
        if not self._wait_for(runtime, before, paused=True):
            return ResetControlResult(False, "restart_control_transition_not_verified")
        try:
            # If the restart control was absent, Enter only closes Options and
            # the unchanged Board is rejected by the outer reset verifier.
            runtime.session.input_backend.press_enter()
        except ControllerInputError as error:
            return ResetControlResult(False, f"confirmation_input_failed:{type(error).__name__}:{error}")
        return ResetControlResult(True, "normal_menu_restart_requested")

    def _restart_lost(self, runtime: Any, before: OutcomeEvidence) -> ResetControlResult:
        if not self._validate_client(runtime):
            return ResetControlResult(False, "unsupported_client_geometry")
        if not self._wait_for_loss_screen(runtime, before):
            return ResetControlResult(False, "loss_screen_not_ready")
        if runtime.outcome().outcome is not GameOutcome.LOST:
            return ResetControlResult(False, "loss_outcome_not_verified")
        try:
            runtime.session.input_backend.left_click(
                *self.TRY_AGAIN_BUTTON,
                move_settle_delay=self.UI_CONTROL_MOVE_SETTLE_DELAY,
            )
        except ControllerInputError as error:
            return ResetControlResult(False, f"loss_retry_input_failed:{type(error).__name__}:{error}")
        return ResetControlResult(True, "loss_try_again_requested")

    def _wait_for_loss_screen(self, runtime: Any, before: OutcomeEvidence) -> bool:
        """Wait read-only for the native Game Over dialog; never retry input."""
        waited = 0.0
        while True:
            current = runtime.outcome()
            if (
                current.outcome is GameOutcome.LOST
                and current.board_address == before.board_address
                and current.loss_screen_ready is True
            ):
                return True
            if waited >= self.loss_screen_ready_timeout_seconds:
                return False
            interval = min(
                self.poll_interval_seconds,
                self.loss_screen_ready_timeout_seconds - waited,
            )
            self._sleeper(interval)
            waited += interval

    def _wait_for(self, runtime: Any, before: OutcomeEvidence, *, paused: bool) -> bool:
        waited = 0.0
        while True:
            if self._is_live_board(runtime, before, paused=paused):
                return True
            if waited >= self.transition_timeout_seconds:
                return False
            interval = min(self.poll_interval_seconds, self.transition_timeout_seconds - waited)
            self._sleeper(interval)
            waited += interval

    @staticmethod
    def _is_live_board(runtime: Any, before: OutcomeEvidence, *, paused: bool) -> bool:
        state = runtime.observe()
        after = runtime.outcome()
        return (
            state is not None
            and after.outcome is before.outcome
            and after.board_address == before.board_address
            and bool(state.paused) is paused
        )


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
