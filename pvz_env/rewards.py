"""Versioned, deterministic Phase 3.5 reward and episode-outcome rules.

GameState v1 has no validated natural win/loss flag.  Natural terminal
outcomes consequently come only from the explicitly injected detector seam;
the default detector deliberately reports no terminal outcome.
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Protocol


REWARD_SCHEMA_VERSION = 1


class OutcomeReason(str, Enum):
    """Natural terminal and external truncation reasons understood by Reward v1."""

    WIN = "win"
    LOSS = "loss"
    MAX_STEPS = "max_steps"
    STATE_UNAVAILABLE = "state_unavailable"


class TerminalDetector(Protocol):
    """Injectable seam for a future validated PvZ natural-outcome signal."""

    def detect(self, before: Any | None, after: Any | None) -> OutcomeReason | None: ...


class NoTerminalDetector:
    """Conservative default until GameState has a validated terminal signal."""

    def detect(self, before: Any | None, after: Any | None) -> OutcomeReason | None:
        return None


@dataclass(frozen=True)
class RewardSpec:
    """Inspectable Reward v1 configuration with stable experiment identity."""

    name: str = "reward-v1-default"
    schema_version: int = REWARD_SCHEMA_VERSION
    win_reward: float = 1.0
    loss_reward: float = -1.0
    wave_progress_weight: float = 0.01
    rejected_action_penalty: float = -0.01
    controller_failure_penalty: float = -0.005
    plant_not_observed_penalty: float = -0.0025
    state_unavailable_penalty: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("reward spec name must be non-empty")
        if self.schema_version != REWARD_SCHEMA_VERSION:
            raise ValueError(f"Reward v1 requires schema version {REWARD_SCHEMA_VERSION}")
        for field_name in (
            "win_reward", "loss_reward", "wave_progress_weight", "rejected_action_penalty",
            "controller_failure_penalty", "plant_not_observed_penalty", "state_unavailable_penalty",
        ):
            if not math.isfinite(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be finite")
        if self.win_reward <= 0 or self.loss_reward >= 0:
            raise ValueError("win_reward must be positive and loss_reward must be negative")


@dataclass(frozen=True)
class RewardOutcome:
    """Auditable reward plus Gym-style episode outcome flags for one step."""

    reward: float
    terminated: bool
    truncated: bool
    reason: OutcomeReason | None
    components: dict[str, float]
    reward_schema_version: int
    reward_spec_name: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.reward) or any(not math.isfinite(value) for value in self.components.values()):
            raise ValueError("reward outcome values must be finite")
        if self.terminated and self.truncated:
            raise ValueError("an outcome cannot be both terminated and truncated")
        if (self.terminated or self.truncated) != (self.reason is not None):
            raise ValueError("terminal/truncated outcomes require exactly one reason")
        if not math.isclose(self.reward, sum(self.components.values()), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("reward must equal the sum of reward components")


class RewardModel:
    """Pure Reward v1 evaluator; it does not mutate states or step results."""

    def __init__(self, spec: RewardSpec | None = None, terminal_detector: TerminalDetector | None = None) -> None:
        self.spec = spec if spec is not None else RewardSpec()
        self.terminal_detector = terminal_detector if terminal_detector is not None else NoTerminalDetector()

    def evaluate(
        self,
        step_result: Any,
        *,
        step_index: int,
        max_steps: int | None = None,
        consecutive_state_unavailable: int = 0,
        max_consecutive_state_unavailable: int | None = None,
    ) -> RewardOutcome:
        """Evaluate one completed Phase 3.3 step result deterministically."""
        if step_index < 0:
            raise ValueError("step_index must be non-negative")
        if max_steps is not None and max_steps <= 0:
            raise ValueError("max_steps must be positive when configured")
        if max_consecutive_state_unavailable is not None and max_consecutive_state_unavailable <= 0:
            raise ValueError("max_consecutive_state_unavailable must be positive when configured")

        before = getattr(step_result, "before", None)
        after = getattr(step_result, "after", None)
        before_state = None if before is None else before.state
        after_state = None if after is None else after.state
        reconciliation = _enum_value(getattr(step_result, "reconciliation", None))
        rejection = _enum_value(getattr(step_result, "rejection_reason", None))
        unavailable = before_state is None or (bool(getattr(step_result, "action_legal", False)) and after_state is None)
        components = {
            "terminal": 0.0,
            "wave_progress": 0.0,
            "rejected_action": 0.0,
            "controller_failure": 0.0,
            "plant_not_observed": 0.0,
            "state_unavailable": 0.0,
        }

        natural = self.terminal_detector.detect(before_state, after_state)
        if natural not in (None, OutcomeReason.WIN, OutcomeReason.LOSS):
            raise ValueError("terminal detector may return only WIN, LOSS, or None")
        if natural is OutcomeReason.WIN:
            components["terminal"] = self.spec.win_reward
            return self._outcome(components, True, False, OutcomeReason.WIN)
        if natural is OutcomeReason.LOSS:
            components["terminal"] = self.spec.loss_reward
            return self._outcome(components, True, False, OutcomeReason.LOSS)

        if before_state is not None and after_state is not None:
            progress_delta = max(0, after_state.wave.spawned_waves - before_state.wave.spawned_waves)
            components["wave_progress"] = progress_delta * self.spec.wave_progress_weight
        if rejection is not None and rejection != "state_unavailable":
            components["rejected_action"] = self.spec.rejected_action_penalty
        if reconciliation == "controller_failed":
            components["controller_failure"] = self.spec.controller_failure_penalty
        if reconciliation == "plant_not_observed":
            components["plant_not_observed"] = self.spec.plant_not_observed_penalty
        if unavailable:
            components["state_unavailable"] = self.spec.state_unavailable_penalty

        if max_consecutive_state_unavailable is not None and consecutive_state_unavailable >= max_consecutive_state_unavailable:
            return self._outcome(components, False, True, OutcomeReason.STATE_UNAVAILABLE)
        if max_steps is not None and step_index + 1 >= max_steps:
            return self._outcome(components, False, True, OutcomeReason.MAX_STEPS)
        return self._outcome(components, False, False, None)

    def _outcome(self, components: dict[str, float], terminated: bool, truncated: bool, reason: OutcomeReason | None) -> RewardOutcome:
        return RewardOutcome(
            reward=sum(components.values()), terminated=terminated, truncated=truncated,
            reason=reason, components=components, reward_schema_version=self.spec.schema_version,
            reward_spec_name=self.spec.name,
        )


def _enum_value(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value))
