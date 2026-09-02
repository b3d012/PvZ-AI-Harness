"""Offline Phase 3.6 prepared-state reset and lifecycle checks."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import ActionResult
from pvz_env import (
    ACTION_COUNT, EpisodeConfig, EpisodeMetadata, EnvironmentLifecycleError,
    LifecycleState, OBSERVATION_SPEC, OutcomeReason, PvZEnvironment,
    ResetGamePaused, ResetStateUnavailable,
)
from pvz_reader.game_state import GameState, WaveState


def state(*, paused=False):
    return GameState(
        sun=250, game_clock=100, scene=0, adventure_level=1, paused=paused,
        plant_capacity=10, zombie_capacity=10,
        wave=WaveState(10, 0, 0, 100, 100, 0.0, 0, False, 0, 0),
        plants=[], zombies=[], seeds=[], mowers=[], pickups=[], projectiles=[], grid_items=[])


class Reader:
    def __init__(self, *items): self.items, self.calls = list(items), 0
    def read(self):
        self.calls += 1
        return self.items.pop(0) if self.items else None


class Controller:
    def __init__(self): self.calls = []
    def plant(self, *args): self.calls.append(args); return ActionResult(True, None, "ok")


class Sink:
    def __init__(self): self.records = []
    def write(self, record): self.records.append(record)


class Detector:
    def __init__(self, result): self.result, self.resets = result, []
    def reset(self, config, initial): self.resets.append((config, initial))
    def detect(self, before, after): return self.result


class EpisodeLifecycleTests(unittest.TestCase):
    def env(self, *items, sink=None):
        self.reader, self.controller, self.sleeps = Reader(*items), Controller(), []
        return PvZEnvironment(self.reader, self.controller, transition_sink=sink,
            sleeper=self.sleeps.append, clock=lambda: 1.0)

    def test_uninitialized_step_has_no_gameplay_effect(self):
        env = self.env(state())
        with self.assertRaisesRegex(EnvironmentLifecycleError, "before reset"):
            env.step(0)
        self.assertEqual((self.reader.calls, self.controller.calls, self.sleeps), (0, [], []))
        self.assertEqual(env.lifecycle, LifecycleState.UNINITIALIZED)

    def test_reset_adopts_fixed_initial_snapshot_and_metadata(self):
        initial = state()
        env = self.env(initial)
        config = EpisodeConfig("level-1-1", active_rows=(False, True, True, True, False, False),
            metadata=EpisodeMetadata(label="1-1", adventure_level=1, scene=0))
        result = env.reset(config)
        self.assertEqual((result.episode_id, result.step_index, result.lifecycle), ("level-1-1", 0, LifecycleState.ACTIVE))
        self.assertIs(result.state, initial)
        self.assertEqual(result.observation.shape, OBSERVATION_SPEC.flat_shape)
        self.assertEqual(result.action_mask.shape, (ACTION_COUNT,))
        self.assertFalse(result.action_mask[1])  # seed 0, row 0, col 0
        self.assertEqual(result.metadata.label, "1-1")
        self.assertEqual(env.config.active_rows, (False, True, True, True, False, False))

    def test_reset_failures_and_config_errors_are_distinct(self):
        with self.assertRaises(ResetStateUnavailable): self.env(None).reset(EpisodeConfig("missing"))
        with self.assertRaises(ResetGamePaused): self.env(state(paused=True)).reset(EpisodeConfig("paused"))
        with self.assertRaises(ValueError): EpisodeConfig("", active_rows=(True,) * 6)
        with self.assertRaises(ValueError): EpisodeConfig("bad", active_rows=(True,) * 5)
        with self.assertRaises(ValueError): EpisodeConfig("bad", max_steps=0)

    def test_terminal_and_truncated_states_block_until_reset(self):
        terminal = Detector(OutcomeReason.WIN)
        env = self.env(state(), state(), state())
        env.reset(EpisodeConfig("terminal", terminal_detector=terminal))
        outcome = env.step(0).outcome
        self.assertTrue(outcome.terminated)
        self.assertEqual(env.lifecycle, LifecycleState.TERMINATED)
        self.assertEqual(len(terminal.resets), 1)
        with self.assertRaises(EnvironmentLifecycleError): env.step(0)
        self.assertEqual(self.sleeps, [0.25])

        env = self.env(state(), state(), state())
        env.reset(EpisodeConfig("truncated", max_steps=1))
        self.assertTrue(env.step(0).outcome.truncated)
        self.assertEqual(env.lifecycle, LifecycleState.TRUNCATED)
        with self.assertRaises(EnvironmentLifecycleError): env.step(0)

    def test_reset_reactivates_and_clears_horizon_and_unavailable_counters(self):
        a, b = state(), state()
        env = self.env(a, a, a, b, b, b)
        env.reset(EpisodeConfig("a", max_steps=1))
        self.assertTrue(env.step(0).outcome.truncated)
        result = env.reset(EpisodeConfig("b", max_steps=1))
        self.assertEqual((result.episode_id, result.step_index, env.lifecycle), ("b", 0, LifecycleState.ACTIVE))
        self.assertTrue(env.step(0).outcome.truncated)

        env = self.env(state(), None, state(), state(), state())
        env.reset(EpisodeConfig("unavailable-a", max_consecutive_state_unavailable=1))
        self.assertTrue(env.step(0).outcome.truncated)
        env.reset(EpisodeConfig("unavailable-b", max_consecutive_state_unavailable=1))
        self.assertFalse(env.step(0).outcome.truncated)

    def test_logging_identity_indexes_and_active_rows_are_episode_scoped(self):
        sink = Sink()
        a, b = state(), state()
        before_copy, after_copy = copy.deepcopy(a), copy.deepcopy(b)
        env = self.env(a, a, a, b, b, b, sink=sink)
        env.reset(EpisodeConfig("episode-a", active_rows=(False, True, True, True, False, False)))
        first = env.step(ACTION_COUNT)  # rejected steps are still indexed
        self.assertEqual(first.outcome.reward, -0.01)
        self.assertEqual(env.config.active_rows, (False, True, True, True, False, False))
        env.step(0)
        env.reset(EpisodeConfig("episode-b"))
        env.step(0)
        self.assertEqual([(record.episode_id, record.step_index) for record in sink.records],
            [("episode-a", 0), ("episode-a", 1), ("episode-b", 0)])
        self.assertEqual(a, before_copy)
        self.assertEqual(b, after_copy)


if __name__ == "__main__":
    unittest.main()
