"""Phase 3.6 environment orchestration and explicit prepared-state episodes.

This module coordinates observation, Action v1 masking, Controller v1 plant
execution, an explicit advancement interval, and a fresh observation. An
optional Phase 3.4 transition sink records completed step results. Phase 3.5
adds versioned reward/outcome evaluation. A caller prepares PvZ at a playable
level, then :meth:`reset` adopts that state; menu and level automation remain deferred.
"""

from dataclasses import dataclass, field
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
    """Immutable execution settings owned by one active episode.

    ``active_rows`` is deliberately supplied externally: frozen GameState v1
    cannot authoritatively describe inactive rows in early Adventure levels.
    A full-board episode may use the all-true default; Phase 3.3 callers must
    configure the correct rows for any early-level episode.
    """

    active_rows: tuple[bool, ...] = (True, True, True, True, True, True)
    step_interval_seconds: float = 0.25
    plant_reconciliation_timeout_seconds: float = 0.75
    plant_reconciliation_poll_interval_seconds: float = 0.05
    max_steps: int | None = None
    max_consecutive_state_unavailable: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_rows", normalize_active_rows(self.active_rows))
        if self.step_interval_seconds < 0:
            raise ValueError("step_interval_seconds must be non-negative")
        if self.plant_reconciliation_timeout_seconds < 0:
            raise ValueError("plant_reconciliation_timeout_seconds must be non-negative")
        if self.plant_reconciliation_poll_interval_seconds <= 0:
            raise ValueError("plant_reconciliation_poll_interval_seconds must be positive")
        if self.max_steps is not None and self.max_steps <= 0:
            raise ValueError("max_steps must be positive when configured")
        if self.max_consecutive_state_unavailable is not None and self.max_consecutive_state_unavailable <= 0:
            raise ValueError("max_consecutive_state_unavailable must be positive when configured")


@dataclass(frozen=True)
class EpisodeMetadata:
    """Optional caller-provided annotation; it is not inferred or validated from PvZ."""

    label: str | None = None
    adventure_level: int | None = None
    scene: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class EpisodeConfig:
    """All deterministic configuration that becomes fixed on successful reset."""

    episode_id: str
    active_rows: tuple[bool, ...] = (True, True, True, True, True, True)
    step_interval_seconds: float = 0.25
    plant_reconciliation_timeout_seconds: float = 0.75
    plant_reconciliation_poll_interval_seconds: float = 0.05
    max_steps: int | None = None
    max_consecutive_state_unavailable: int | None = None
    reward_spec: RewardSpec = field(default_factory=RewardSpec)
    terminal_detector: TerminalDetector | None = None
    metadata: EpisodeMetadata | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id:
            raise ValueError("episode_id must be a non-empty string")
        object.__setattr__(self, "active_rows", normalize_active_rows(self.active_rows))
        EnvironmentConfig(
            active_rows=self.active_rows,
            step_interval_seconds=self.step_interval_seconds,
            plant_reconciliation_timeout_seconds=self.plant_reconciliation_timeout_seconds,
            plant_reconciliation_poll_interval_seconds=self.plant_reconciliation_poll_interval_seconds,
            max_steps=self.max_steps,
            max_consecutive_state_unavailable=self.max_consecutive_state_unavailable,
        )
        if not isinstance(self.reward_spec, RewardSpec):
            raise TypeError("reward_spec must be a RewardSpec")
        if self.metadata is not None and not isinstance(self.metadata, EpisodeMetadata):
            raise TypeError("metadata must be EpisodeMetadata or None")


class LifecycleState(str, Enum):
    UNINITIALIZED = "uninitialized"
    ACTIVE = "active"
    TERMINATED = "terminated"
    TRUNCATED = "truncated"


@dataclass(frozen=True)
class ObservationSnapshot:
    """One raw GameState paired with frozen encoded observation and mask."""

    state: "GameState"
    observation: np.ndarray
    action_mask: np.ndarray


@dataclass(frozen=True)
class StepTiming:
    """Timing for one strategic interval and any plant verification reads.

    ``configured_interval_seconds`` is solely the agent-selected strategic
    advancement.  Reconciliation fields describe bounded read-only verification
    after a plant action; they do not represent extra agent steps.
    """

    configured_interval_seconds: float
    started_at: float
    finished_at: float
    advancement_invoked: bool
    reconciliation_poll_count: int = 0
    reconciliation_wait_seconds: float = 0.0


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


@dataclass(frozen=True)
class ResetResult:
    """Deterministic initial observation adopted from a manually prepared game."""

    episode_id: str
    initial: ObservationSnapshot
    active_rows: tuple[bool, ...]
    step_index: int
    lifecycle: LifecycleState
    reward_schema_version: int
    reward_spec_name: str
    metadata: EpisodeMetadata | None

    @property
    def state(self) -> "GameState":
        return self.initial.state

    @property
    def observation(self) -> np.ndarray:
        return self.initial.observation

    @property
    def action_mask(self) -> np.ndarray:
        return self.initial.action_mask


class EnvironmentStateUnavailable(RuntimeError):
    """Raised by :meth:`PvZEnvironment.observe` when a reader has no state."""


class EnvironmentLifecycleError(RuntimeError):
    """Raised when an operation is invalid for the explicit episode lifecycle."""


class ResetStateUnavailable(EnvironmentLifecycleError):
    """Raised when reset cannot obtain a game state from the read-only reader."""


class ResetGamePaused(EnvironmentLifecycleError):
    """Raised when reset observes a paused game rather than playable gameplay."""


class PvZEnvironment:
    """Library-independent bridge with explicit Phase 3.6 episode lifecycle.

    ``WAIT`` and a legal ``PLANT`` each advance once with
    ``step_interval_seconds`` before the post-step read.  A plant that was
    issued successfully may then use bounded read-only polling to verify its
    postcondition; it never issues another controller action. Rejected actions
    never invoke the controller or sleeper.  No desktop interaction occurs
    unless a real Controller v1 instance is explicitly injected. When a
    transition sink is supplied, every active :meth:`step` emits exactly one
    record after a complete result exists, including rejected actions. The
    caller must manually prepare the live level before calling :meth:`reset`.
    """

    def __init__(
        self,
        reader: StateReader,
        controller: PlantController,
        *,
        encoder: ObservationEncoder | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transition_sink: TransitionSink | None = None,
    ) -> None:
        self.reader = reader
        self.controller = controller
        self.config: EnvironmentConfig | None = None
        self.episode_config: EpisodeConfig | None = None
        self.encoder = encoder if encoder is not None else ObservationEncoder()
        self._sleeper = sleeper
        self._clock = clock
        self.episode_id: str | None = None
        self._step_index = 0
        self._consecutive_state_unavailable = 0
        self._transition_sink = transition_sink
        self.reward_model: RewardModel | None = None
        self.lifecycle = LifecycleState.UNINITIALIZED

    def reset(self, episode_config: EpisodeConfig) -> ResetResult:
        """Adopt a manually prepared, unpaused live state as a new episode."""
        if not isinstance(episode_config, EpisodeConfig):
            raise TypeError("episode_config must be an EpisodeConfig")
        config = EnvironmentConfig(
            active_rows=episode_config.active_rows,
            step_interval_seconds=episode_config.step_interval_seconds,
            plant_reconciliation_timeout_seconds=episode_config.plant_reconciliation_timeout_seconds,
            plant_reconciliation_poll_interval_seconds=episode_config.plant_reconciliation_poll_interval_seconds,
            max_steps=episode_config.max_steps,
            max_consecutive_state_unavailable=episode_config.max_consecutive_state_unavailable,
        )
        initial = self._read_snapshot(config)
        if initial is None:
            raise ResetStateUnavailable("reader returned no GameState during reset")
        if initial.state.paused:
            raise ResetGamePaused("cannot reset while the game is paused")
        detector = episode_config.terminal_detector
        reset_detector = getattr(detector, "reset", None)
        if reset_detector is not None:
            reset_detector(episode_config, initial.state)
        self.config = config
        self.episode_config = episode_config
        self.episode_id = episode_config.episode_id
        self._step_index = 0
        self._consecutive_state_unavailable = 0
        self.reward_model = RewardModel(episode_config.reward_spec, detector)
        self.lifecycle = LifecycleState.ACTIVE
        return ResetResult(
            episode_id=self.episode_id, initial=initial, active_rows=config.active_rows,
            step_index=0, lifecycle=self.lifecycle,
            reward_schema_version=episode_config.reward_spec.schema_version,
            reward_spec_name=episode_config.reward_spec.name,
            metadata=episode_config.metadata,
        )

    def observe(self) -> ObservationSnapshot:
        """Read once and return the raw state, encoded observation, and mask."""
        self._require_active("observe")
        snapshot = self._read_snapshot(self.config)
        if snapshot is None:
            raise EnvironmentStateUnavailable("reader returned no GameState")
        return snapshot

    def step(self, action_index: int) -> StepResult:
        """Execute one legal Action v1 decision and observe the resulting state."""
        self._require_active("step")
        assert self.config is not None
        started_at = self._clock()
        try:
            action = decode_action(action_index)
        except ValueError:
            return self._finalize(self._rejected(
                action_index, None, StepRejectionReason.INVALID_ACTION_INDEX, started_at
            ))

        before = self._read_snapshot(self.config)
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
        after = self._read_snapshot(self.config)
        poll_count = 0
        reconciliation_wait_seconds = 0.0
        if self._should_poll_plant(action, before.state, after, controller_result):
            after, poll_count, reconciliation_wait_seconds = self._poll_plant_postcondition(
                action, before.state, after
            )
        finished_at = self._clock()
        timing = StepTiming(
            self.config.step_interval_seconds, started_at, finished_at, True,
            poll_count, reconciliation_wait_seconds,
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
        assert self.config is not None and self.reward_model is not None and self.episode_id is not None
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
        if outcome.terminated:
            self.lifecycle = LifecycleState.TERMINATED
        elif outcome.truncated:
            self.lifecycle = LifecycleState.TRUNCATED
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

    def _read_snapshot(self, config: EnvironmentConfig) -> ObservationSnapshot | None:
        state = self.reader.read()
        if state is None:
            return None
        return ObservationSnapshot(
            state=state,
            observation=self.encoder.encode(state),
            action_mask=build_action_mask(state, active_rows=config.active_rows),
        )

    def _should_poll_plant(
        self,
        action: SemanticAction,
        before_state: "GameState",
        after: ObservationSnapshot | None,
        controller_result: ActionResult | None,
    ) -> bool:
        """Return whether an issued plant has an unobserved, available result."""
        if action.action_type is not ActionType.PLANT or after is None:
            return False
        if controller_result is None or not controller_result.attempted or controller_result.success is False:
            return False
        return not self._plant_is_observed(action, before_state, after)

    def _poll_plant_postcondition(
        self,
        action: SemanticAction,
        before_state: "GameState",
        after: ObservationSnapshot,
    ) -> tuple[ObservationSnapshot | None, int, float]:
        """Read only until the plant appears, state disappears, or time expires."""
        assert self.config is not None
        poll_count = 0
        wait_seconds = 0.0
        while wait_seconds < self.config.plant_reconciliation_timeout_seconds:
            remaining = self.config.plant_reconciliation_timeout_seconds - wait_seconds
            wait = min(self.config.plant_reconciliation_poll_interval_seconds, remaining)
            self._sleeper(wait)
            wait_seconds += wait
            poll_count += 1
            after = self._read_snapshot(self.config)
            if after is None or self._plant_is_observed(action, before_state, after):
                return after, poll_count, wait_seconds
        return after, poll_count, wait_seconds

    def _require_active(self, operation: str) -> None:
        if self.lifecycle is LifecycleState.UNINITIALIZED:
            raise EnvironmentLifecycleError(f"cannot {operation} before reset")
        if self.lifecycle in (LifecycleState.TERMINATED, LifecycleState.TRUNCATED):
            raise EnvironmentLifecycleError(f"cannot {operation} after episode is {self.lifecycle.value}; call reset")

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
    def _plant_is_observed(
        action: SemanticAction, before_state: "GameState", after: ObservationSnapshot
    ) -> bool:
        seed = next(seed for seed in before_state.seeds if seed.slot == action.seed_slot)
        return plant_was_placed(seed, action.row, action.col, after.state)

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

        if PvZEnvironment._plant_is_observed(action, before_state, after):
            return ReconciliationStatus.PLANT_OBSERVED
        return ReconciliationStatus.PLANT_NOT_OBSERVED
