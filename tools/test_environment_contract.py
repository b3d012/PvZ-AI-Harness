"""Frozen Environment v1 metadata regression checks."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_env import (
    ACTION_COUNT, ACTION_SCHEMA_VERSION, ENVIRONMENT_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION, OBSERVATION_SPEC, REWARD_SCHEMA_VERSION,
    TRANSITION_SCHEMA_VERSION, environment_contract,
)


class EnvironmentContractTests(unittest.TestCase):
    def test_environment_v1_metadata_is_complete_and_deterministic(self):
        first = environment_contract()
        second = environment_contract()
        self.assertEqual(first, second)
        self.assertEqual(first.observation_schema_version, OBSERVATION_SCHEMA_VERSION)
        self.assertEqual(first.observation_shape, (5534,))
        self.assertEqual(first.observation_shape, OBSERVATION_SPEC.flat_shape)
        self.assertEqual((first.action_schema_version, first.action_count), (ACTION_SCHEMA_VERSION, ACTION_COUNT))
        self.assertEqual((first.action_count, first.environment_schema_version), (541, ENVIRONMENT_SCHEMA_VERSION))
        self.assertEqual((first.reward_schema_version, first.transition_schema_version),
            (REWARD_SCHEMA_VERSION, TRANSITION_SCHEMA_VERSION))
        self.assertEqual(first.to_dict()["observation_shape"], [5534])


if __name__ == "__main__":
    unittest.main()
