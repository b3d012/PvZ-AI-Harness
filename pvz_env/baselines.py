"""Small, reproducible non-learning policies and EpisodeConfig evaluation.

The policy API is model-library-independent and returns only Action v1 indices.
The scripted policy optionally receives raw GameState for transparent engineering
rules; this privileged structured access is deliberately separate from the
encoded-observation/mask input intended for future learned policies.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from pvz_env.actions import ActionType, SemanticAction, decode_action
from pvz_env.environment import EpisodeConfig, PvZEnvironment, ReconciliationStatus
from pvz_env.rewards import OutcomeReason
from pvz_reader.game_state import PLANT_NAMES


SUNFLOWER_TYPE_ID = PLANT_NAMES.index("Sunflower")
PEASHOOTER_TYPE_ID = PLANT_NAMES.index("Peashooter")


@dataclass(frozen=True)
class PolicyDecision:
    """An Action v1 index and stable human-readable selection rationale."""

    action_index: int
    reason: str


class Policy(Protocol):
    """Canonical policy seam: encoded Observation v1 and Action v1 mask in."""

    name: str

    def select_action(
        self, observation: np.ndarray, action_mask: np.ndarray, *, state: Any | None = None
    ) -> PolicyDecision: ...


@dataclass(frozen=True)
class RandomPolicyConfig:
    seed: int | None = None


class RandomValidActionPolicy:
    """Seeded uniform sampler over legal Action v1 indexes, including WAIT."""

    name = "random-valid-action"

    def __init__(self, config: RandomPolicyConfig | None = None) -> None:
        self.config = config if config is not None else RandomPolicyConfig()
        self._rng = np.random.default_rng(self.config.seed)

    def select_action(self, observation: np.ndarray, action_mask: np.ndarray, *, state: Any | None = None) -> PolicyDecision:
        valid = np.flatnonzero(np.asarray(action_mask, dtype=np.bool_))
        if valid.size == 0:
            raise ValueError("action_mask contains no legal Action v1 index")
        return PolicyDecision(int(self._rng.choice(valid)), "uniform_valid_action")


@dataclass(frozen=True)
class HeuristicPolicyConfig:
    economy_target_per_active_row: int = 1
    economy_columns: tuple[int, ...] = (0, 1, 2)
    offense_columns: tuple[int, ...] = (2, 3, 4)

    def __post_init__(self) -> None:
        if self.economy_target_per_active_row < 0:
            raise ValueError("economy_target_per_active_row must be non-negative")


class SimpleHeuristicPolicy:
    """Compact structured-state baseline: economy first, then threatened lanes.

    It never builds legality itself: every proposed action must already be true
    in the Action v1 mask. It intentionally does not attempt a complete build
    order, wave prediction, search, or level-specific strategy.
    """

    name = "simple-heuristic"

    def __init__(self, config: HeuristicPolicyConfig | None = None) -> None:
        self.config = config if config is not None else HeuristicPolicyConfig()

    def select_action(self, observation: np.ndarray, action_mask: np.ndarray, *, state: Any | None = None) -> PolicyDecision:
        mask = np.asarray(action_mask, dtype=np.bool_)
        if mask.ndim != 1:
            raise ValueError("action_mask must be one-dimensional")
        if not mask.any():
            raise ValueError("action_mask contains no legal Action v1 index")
        if state is None:
            return PolicyDecision(0, "no_structured_state_available")

        legal = [index for index in np.flatnonzero(mask) if index != 0]
        seeds = {seed.slot: seed for seed in state.seeds}
        sunflowers = sum(plant.type_id == SUNFLOWER_TYPE_ID for plant in state.plants)
        active_rows = len({decode_action(int(index)).row for index in legal})
        if sunflowers < self.config.economy_target_per_active_row * active_rows:
            action = self._first_matching(legal, seeds, SUNFLOWER_TYPE_ID, None, self.config.economy_columns)
            if action is not None:
                return PolicyDecision(action, "economy_plant_back_column")

        threatened_rows = {zombie.row for zombie in state.zombies}
        for row in sorted(threatened_rows):
            action = self._first_matching(legal, seeds, PEASHOOTER_TYPE_ID, row, self.config.offense_columns)
            if action is not None:
                return PolicyDecision(action, "offense_threatened_lane")
        return PolicyDecision(0, "no_preferred_legal_placement")

    @staticmethod
    def _first_matching(legal: list[int], seeds: dict[int, Any], type_id: int, row: int | None, columns: tuple[int, ...]) -> int | None:
        for column in columns:
            for index in legal:
                action = decode_action(int(index))
                seed = seeds.get(action.seed_slot)
                if (seed is not None and seed.type_id == type_id and action.col == column
                        and (row is None or action.row == row)):
                    return int(index)
        return None


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    policy_name: str
    policy_config: dict[str, Any]
    steps: int
    cumulative_reward: float
    terminated: bool
    truncated: bool
    outcome_reason: OutcomeReason | None
    wait_actions: int
    plant_actions: int
    rejected_actions: int
    controller_failures: int
    plants_observed: int
    plants_not_observed: int
    reward_schema_version: int
    reward_spec_name: str


@dataclass(frozen=True)
class EpisodeSummary:
    episode_count: int
    mean_cumulative_reward: float
    min_cumulative_reward: float
    max_cumulative_reward: float
    mean_steps: float
    termination_count: int
    termination_rate: float
    truncation_count: int
    truncation_rate: float
    rejection_count: int
    rejection_rate: float
    controller_failure_count: int
    wins: int
    losses: int
    win_rate: float | None


def run_episode(environment: PvZEnvironment, policy: Policy, episode_config: EpisodeConfig) -> EpisodeResult:
    """Reset exactly once, step until an outcome, and return auditable metrics."""
    reset = environment.reset(episode_config)
    snapshot = reset.initial
    steps = wait_actions = plant_actions = rejected = controller_failures = observed = not_observed = 0
    cumulative_reward = 0.0
    final_outcome = None
    while True:
        decision = policy.select_action(snapshot.observation, snapshot.action_mask, state=snapshot.state)
        if not snapshot.action_mask[decision.action_index]:
            raise ValueError(f"policy {policy.name!r} selected masked action {decision.action_index}")
        result = environment.step(decision.action_index)
        steps += 1
        assert result.outcome is not None
        final_outcome = result.outcome
        cumulative_reward += result.outcome.reward
        if result.action is not None and result.action.action_type is ActionType.WAIT:
            wait_actions += 1
        elif result.action is not None and result.action.action_type is ActionType.PLANT:
            plant_actions += 1
        if result.reconciliation is ReconciliationStatus.REJECTED:
            rejected += 1
        elif result.reconciliation is ReconciliationStatus.CONTROLLER_FAILED:
            controller_failures += 1
        elif result.reconciliation is ReconciliationStatus.PLANT_OBSERVED:
            observed += 1
        elif result.reconciliation is ReconciliationStatus.PLANT_NOT_OBSERVED:
            not_observed += 1
        if result.outcome.terminated or result.outcome.truncated:
            break
        if result.after is None:
            raise RuntimeError("active episode has no post-step snapshot for the next policy decision")
        snapshot = result.after
    assert final_outcome is not None
    return EpisodeResult(
        episode_id=reset.episode_id, policy_name=policy.name, policy_config=_policy_config(policy),
        steps=steps, cumulative_reward=cumulative_reward, terminated=final_outcome.terminated,
        truncated=final_outcome.truncated, outcome_reason=final_outcome.reason,
        wait_actions=wait_actions, plant_actions=plant_actions, rejected_actions=rejected,
        controller_failures=controller_failures, plants_observed=observed,
        plants_not_observed=not_observed, reward_schema_version=reset.reward_schema_version,
        reward_spec_name=reset.reward_spec_name,
    )


def summarize_episodes(results: list[EpisodeResult]) -> EpisodeSummary:
    """Deterministically aggregate completed runner results without inferred wins."""
    if not results:
        raise ValueError("at least one EpisodeResult is required")
    count = len(results)
    rewards = [result.cumulative_reward for result in results]
    terminations = sum(result.terminated for result in results)
    truncations = sum(result.truncated for result in results)
    rejections = sum(result.rejected_actions for result in results)
    failures = sum(result.controller_failures for result in results)
    steps = sum(result.steps for result in results)
    wins = sum(result.outcome_reason is OutcomeReason.WIN for result in results)
    losses = sum(result.outcome_reason is OutcomeReason.LOSS for result in results)
    natural = wins + losses
    return EpisodeSummary(
        episode_count=count, mean_cumulative_reward=sum(rewards) / count,
        min_cumulative_reward=min(rewards), max_cumulative_reward=max(rewards), mean_steps=steps / count,
        termination_count=terminations, termination_rate=terminations / count,
        truncation_count=truncations, truncation_rate=truncations / count,
        rejection_count=rejections, rejection_rate=rejections / steps if steps else 0.0,
        controller_failure_count=failures, wins=wins, losses=losses,
        win_rate=None if natural == 0 else wins / natural,
    )


def _policy_config(policy: Policy) -> dict[str, Any]:
    config = getattr(policy, "config", None)
    if config is None:
        return {}
    return {field: getattr(config, field) for field in config.__dataclass_fields__}
