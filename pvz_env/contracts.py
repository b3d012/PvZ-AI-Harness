"""Frozen, inspectable Environment v1 public-contract metadata."""

from dataclasses import dataclass

from pvz_env.actions import ACTION_COUNT, ACTION_SCHEMA_VERSION
from pvz_env.logging import TRANSITION_SCHEMA_VERSION
from pvz_env.observation import OBSERVATION_SCHEMA_VERSION, OBSERVATION_SPEC
from pvz_env.rewards import REWARD_SCHEMA_VERSION


ENVIRONMENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EnvironmentContract:
    """Stable schema identifiers for checkpoints, trajectories, and evaluations."""

    observation_schema_version: int
    observation_shape: tuple[int, ...]
    action_schema_version: int
    action_count: int
    environment_schema_version: int
    reward_schema_version: int
    transition_schema_version: int

    def to_dict(self) -> dict[str, int | list[int]]:
        return {
            "observation_schema_version": self.observation_schema_version,
            "observation_shape": list(self.observation_shape),
            "action_schema_version": self.action_schema_version,
            "action_count": self.action_count,
            "environment_schema_version": self.environment_schema_version,
            "reward_schema_version": self.reward_schema_version,
            "transition_schema_version": self.transition_schema_version,
        }


def environment_contract() -> EnvironmentContract:
    """Return deterministic Environment v1 metadata without runtime state."""
    return EnvironmentContract(
        observation_schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_shape=OBSERVATION_SPEC.flat_shape,
        action_schema_version=ACTION_SCHEMA_VERSION,
        action_count=ACTION_COUNT,
        environment_schema_version=ENVIRONMENT_SCHEMA_VERSION,
        reward_schema_version=REWARD_SCHEMA_VERSION,
        transition_schema_version=TRANSITION_SCHEMA_VERSION,
    )
