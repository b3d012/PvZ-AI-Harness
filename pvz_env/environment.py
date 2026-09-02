"""Phase 3.3 environment step orchestration for frozen PvZ interfaces.

This module coordinates observation, Action v1 masking, Controller v1 plant
execution, an explicit advancement interval, and a fresh observation. An
optional Phase 3.4 transition sink records completed step results. Phase 3.5
adds versioned reward/outcome evaluation; reset and pickup handling remain deferred.
"""

from dataclasses import dataclass
from enum import Enum
import time
from typing import TYPE_CHECKING, Callable, Protocol

import numpy as np

from pvz_controller import ActionResult, plant_was_placed
from pvz_env.actions import SemanticAction, ActionType, build_action_mask, decode_action, normalize_active_rows
from pvz_env.logging import TransitionLoggingError, TransitionRecord, TransitionSink
from pvz_env.observation import ObservationEncoder
from pvz_env.rewards import RewardModel, RewardOutcome, RewardSpec, TerminalDetector

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState


class StateReader(Protocol):
    """Minimal read-only reader seam required by :class:`PvZEnvironment`."""

    def read(self) -> "GameState | None": ...


class PlantController(Protocol):
    """Frozen Controller v1 subset used by Action v1 plant decisions."""

    def plant(self, state: "GameState", seed_slot: int, row: int, col: int) -> ActionResult: ...


class StepRejectionReason(str, Enum):
    """Stable causes for a step rejected before semantic execution."""

    INVALID_ACTION_INDEX = "invalid_action_index"
    STATE_UNAVAILABLE = "state_unavailable"
    GAME_PAUSED = "game_paused"
    ACTION_MASKED = "action_masked"


class ReconciliationStatus(str, Enum):
    """Post-step distinction between rejection, input, and game observation."""

    REJECTED = "rejected"
    WAIT_ADVANCED = "wait_advanced"
    CONTROLLER_FAILED = "controller_failed"
    PLANT_OBSERVED = "plant_observed"
    PLANT_NOT_OBSERVED = "plant_not_observed"
    POSTCONDITION_UNAVAILABLE = "postcondition_unavailable"


@dataclass(frozen=True)
class EnvironmentConfig:
    """Immutable episode configuration owned by the environment runtime.

    ``active_rows`` is deliberately supplied externally: frozen GameState v1
    cannot authoritatively describe inactive rows in early Adventure levels.
    A full-board episode may use the all-true default; Phase 3.3 callers must
    configure the correct rows for any early-level episode.
    """

    active_rows: tuple[bool, ...] = (True, True, True, True, True, True)
    step_interval_seconds: float = 0.25
    max_steps: int | None = None
    max_consecutive_state_unavailable: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_rows", normalize_active_rows(self.active_rows))
        if self.step_interval_seconds < 0:
            raise ValueError("step_interval_seconds must be non-negative")
        if self.max_steps is not None and self.max_steps <= 0:
            raise ValueError("max_steps must be positive when configured")
        if self.max_consecutive_state_unavailable is not None and self.max_consecutive_state_unavailable <= 0:
            raise ValueError("max_consecutive_state_unavailable must be positive when configured")


@dataclass(frozen=True)
class ObservationSnapshot:
    """One raw GameState paired with frozen encoded observation and mask."""

    state: "GameState"
    observation: np.ndarray
    action_mask: np.ndarray


@dataclass(frozen=True)
class StepTiming:
    """Explicit timing metadata for a strategic action interval."""

    configured_interval_seconds: float
    started_at: float
    finished_at: float
    advancement_invoked: bool


@dataclass(frozen=True)
class StepResult:
    """Typed Phase 3.3 result enriched compatibly with optional Reward v1 outcome."""

    action_index: int
    action: SemanticAction | None
    action_legal: bool
    rejection_reason: StepRejectionReason | None
    controller_result: ActionResult | None
    before: ObservationSnapshot | None
    after: ObservationSnapshot | None
    reconciliation: ReconciliationStatus
    timing: StepTiming
    outcome: RewardOutcome | None = None


class EnvironmentStateUnavailable(RuntimeError):
    """Raised by :meth:`PvZEnvironment.observe` when a reader has no state."""


class PvZEnvironment:
    """Library-independent Phase 3.3 runtime bridge with injectable seams.

    ``WAIT`` and a legal ``PLANT`` each call the supplied sleeper exactly once
    with ``step_interval_seconds`` before the post-step read.  Rejected actions
    never invoke the controller or sleeper.  No desktop interaction occurs
    unless a real Controller v1 instance is explicitly injected. When a
    transition sink is supplied, every call to :meth:`step` emits exactly one
    record after a complete result exists, including rejected actions.
    """

    def __init__(
        self,
        reader: StateReader,
        controller: PlantController,
        *,
        active_rows: tuple[bool, ...] | None = None,
        step_interval_seconds: float = 0.25,
        encoder: ObservationEncoder | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transition_sink: TransitionSink | None = None,
        episode_id: str = "default",
        reward_spec: RewardSpec | None = None,
        terminal_detector: TerminalDetector | None = None,
        max_steps: int | None = None,
        max_consecutive_state_unavailable: int | None = None,
    ) -> None:
        self.reader = reader
        self.controller = controller
        self.config = EnvironmentConfig(
            active_rows=normalize_active_rows(active_rows),
            step_interval_seconds=step_interval_seconds,
            max_steps=max_steps,
            max_consecutive_state_unavailable=max_consecutive_state_unavailable,
        )
        self.encoder = encoder if encoder is not None else ObservationEncoder()
        self._sleeper = sleeper
        self._clock = clock
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("episode_id must be a non-empty string")
        self.episode_id = episode_id
        self._step_index = 0
        self._consecutive_state_unavailable = 0
        self._transition_sink = transition_sink
        self.reward_model = RewardModel(reward_spec, terminal_detector)

    def observe(self) -> ObservationSnapshot:
        """Read once and return the raw state, encoded observation, and mask."""
        snapshot = self._read_snapshot()
        if snapshot is None:
            raise EnvironmentStateUnavailable("reader returned no GameState")
        return snapshot

    def step(self, action_index: int) -> StepResult:
        """Execute one legal Action v1 decision and observe the resulting state."""
        started_at = self._clock()
        try:
            action = decode_action(action_index)
        except ValueError:
            return self._finalize(self._rejected(
                action_index, None, StepRejectionReason.INVALID_ACTION_INDEX, started_at
            ))

        before = self._read_snapshot()
        if before is None:
            return self._finalize(self._rejected(
                action_index, action, StepRejectionReason.STATE_UNAVAILABLE, started_at
            ))
        if before.state.paused:
            return self._finalize(self._rejected(
                action_index, action, StepRejectionReason.GAME_PAUSED, started_at, before
            ))
        if not before.action_mask[action_index]:
            return self._finalize(self._rejected(
                action_index, action, StepRejectionReason.ACTION_MASKED, started_at, before
            ))

        controller_result: ActionResult | None = None
        if action.action_type is ActionType.PLANT:
            controller_result = self.controller.plant(
                before.state, action.seed_slot, action.row, action.col
            )

        self._sleeper(self.config.step_interval_seconds)
        after = self._read_snapshot()
        finished_at = self._clock()
        timing = StepTiming(
            self.config.step_interval_seconds, started_at, finished_at, True
        )
        reconciliation = self._reconcile(action, before.state, after, controller_result)
        return self._finalize(StepResult(
            action_index=action_index,
            action=action,
            action_legal=True,
            rejection_reason=None,
            controller_result=controller_result,
            before=before,
            after=after,
            reconciliation=reconciliation,
            timing=timing,
        ))

    def _finalize(self, result: StepResult) -> StepResult:
        """Assign one deterministic index and emit, if configured, exactly once."""
        step_index = self._step_index
        self._step_index += 1
        unavailable = result.before is None or (result.action_legal and result.after is None)
        self._consecutive_state_unavailable = self._consecutive_state_unavailable + 1 if unavailable else 0
        outcome = self.reward_model.evaluate(
            result, step_index=step_index, max_steps=self.config.max_steps,
            consecutive_state_unavailable=self._consecutive_state_unavailable,
            max_consecutive_state_unavailable=self.config.max_consecutive_state_unavailable,
        )
        result = StepResult(
            action_index=result.action_index, action=result.action, action_legal=result.action_legal,
            rejection_reason=result.rejection_reason, controller_result=result.controller_result,
            before=result.before, after=result.after, reconciliation=result.reconciliation,
            timing=result.timing, outcome=outcome,
        )
        if self._transition_sink is not None:
            record = TransitionRecord.from_step_result(
                result, episode_id=self.episode_id, step_index=step_index
            )
            try:
                self._transition_sink.write(record)
            except Exception as error:
                raise TransitionLoggingError(
                    f"failed to persist transition {self.episode_id}/{step_index}: {error}", result
                ) from error
        return result

    def _read_snapshot(self) -> ObservationSnapshot | None:
        state = self.reader.read()
        if state is None:
            return None
        return ObservationSnapshot(
            state=state,
            observation=self.encoder.encode(state),
            action_mask=build_action_mask(state, active_rows=self.config.active_rows),
        )

    def _rejected(
        self,
        action_index: int,
        action: SemanticAction | None,
        reason: StepRejectionReason,
        started_at: float,
        before: ObservationSnapshot | None = None,
    ) -> StepResult:
        finished_at = self._clock()
        return StepResult(
            action_index=action_index,
            action=action,
            action_legal=False,
            rejection_reason=reason,
            controller_result=None,
            before=before,
            after=None,
            reconciliation=ReconciliationStatus.REJECTED,
            timing=StepTiming(self.config.step_interval_seconds, started_at, finished_at, False),
        )

    @staticmethod
    def _reconcile(
        action: SemanticAction,
        before_state: "GameState",
        after: ObservationSnapshot | None,
        controller_result: ActionResult | None,
    ) -> ReconciliationStatus:
        if action.action_type is ActionType.WAIT:
            if after is None:
                return ReconciliationStatus.POSTCONDITION_UNAVAILABLE
            return ReconciliationStatus.WAIT_ADVANCED
        if controller_result is None or not controller_result.attempted or controller_result.success is False:
            return ReconciliationStatus.CONTROLLER_FAILED
        if after is None:
            return ReconciliationStatus.POSTCONDITION_UNAVAILABLE

        seed = next(seed for seed in before_state.seeds if seed.slot == action.seed_slot)
        if plant_was_placed(seed, action.row, action.col, after.state):
            return ReconciliationStatus.PLANT_OBSERVED
        return ReconciliationStatus.PLANT_NOT_OBSERVED
