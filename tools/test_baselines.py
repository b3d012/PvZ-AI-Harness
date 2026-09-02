"""Offline Phase 3.7 policy and evaluation-harness checks."""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import ActionResult
from pvz_env import (
    ACTION_COUNT, EpisodeConfig, EpisodeResult, HeuristicPolicyConfig,
    OutcomeReason, RandomPolicyConfig, RandomValidActionPolicy,
    SemanticAction, SimpleHeuristicPolicy, ActionType, PvZEnvironment,
    encode_action, run_episode, summarize_episodes,
)
from pvz_reader.game_state import GameState, SeedPacketState, WaveState


def state(*, seeds=None, zombies=None):
    return GameState(
        sun=250, game_clock=100, scene=0, adventure_level=1, paused=False,
        plant_capacity=10, zombie_capacity=10,
        wave=WaveState(10, 0, 0, 100, 100, 0.0, 0, False, 0, 0),
        plants=[], zombies=zombies or [], seeds=seeds or [], mowers=[], pickups=[], projectiles=[], grid_items=[])


class Reader:
    def __init__(self, *states): self.states, self.calls = list(states), 0
    def read(self):
        self.calls += 1
        return self.states.pop(0) if self.states else None


class Controller:
    def __init__(self): self.calls = []
    def plant(self, *args): self.calls.append(args); return ActionResult(True, None, "ok")


class Sink:
    def __init__(self): self.records = []
    def write(self, record): self.records.append(record)


class WaitPolicy:
    name = "wait-policy"
    config = None
    def select_action(self, observation, action_mask, *, state=None):
        return SimpleNamespace(action_index=0, reason="test_wait")


class TerminalDetector:
    def detect(self, before, after): return OutcomeReason.WIN


def seed(slot, type_id, name):
    return SimpleNamespace(slot=slot, type_id=type_id, name=name)


class BaselineTests(unittest.TestCase):
    def test_random_policy_is_seeded_and_never_masked(self):
        mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
        mask[[0, 3, 71, 540]] = True
        first = RandomValidActionPolicy(RandomPolicyConfig(seed=12))
        second = RandomValidActionPolicy(RandomPolicyConfig(seed=12))
        third = RandomValidActionPolicy(RandomPolicyConfig(seed=13))
        a = [first.select_action(np.zeros(1), mask).action_index for _ in range(8)]
        b = [second.select_action(np.zeros(1), mask).action_index for _ in range(8)]
        c = [third.select_action(np.zeros(1), mask).action_index for _ in range(8)]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(all(mask[index] for index in a))
        wait_only = np.zeros(ACTION_COUNT, dtype=np.bool_); wait_only[0] = True
        self.assertEqual(first.select_action(np.zeros(1), wait_only).action_index, 0)
        with self.assertRaises(ValueError): first.select_action(np.zeros(1), np.zeros(ACTION_COUNT, dtype=np.bool_))

    def test_heuristic_prefers_economy_then_threatened_lane_and_is_legal(self):
        policy = SimpleHeuristicPolicy(HeuristicPolicyConfig())
        economy = encode_action(SemanticAction(ActionType.PLANT, 1, 2, 0))
        offense = encode_action(SemanticAction(ActionType.PLANT, 0, 4, 2))
        mask = np.zeros(ACTION_COUNT, dtype=np.bool_); mask[[0, economy, offense]] = True
        raw = SimpleNamespace(seeds=[seed(0, 0, "Peashooter"), seed(1, 1, "Sunflower")], plants=[],
            zombies=[SimpleNamespace(row=4)])
        before = copy.deepcopy(raw)
        decision = policy.select_action(np.zeros(5534, dtype=np.float32), mask, state=raw)
        self.assertEqual((decision.action_index, decision.reason), (economy, "economy_plant_back_column"))
        raw.plants = [SimpleNamespace(type_id=1)] * 6
        decision = policy.select_action(np.zeros(5534, dtype=np.float32), mask, state=raw)
        self.assertEqual((decision.action_index, decision.reason), (offense, "offense_threatened_lane"))
        self.assertTrue(mask[decision.action_index])
        self.assertEqual(before.seeds[0].type_id, 0)
        self.assertEqual(policy.select_action(np.zeros(1), np.array([True]), state=None).reason, "no_structured_state_available")

    def test_heuristic_wait_fallback_and_masked_candidates(self):
        policy = SimpleHeuristicPolicy()
        mask = np.zeros(ACTION_COUNT, dtype=np.bool_); mask[0] = True
        raw = SimpleNamespace(seeds=[seed(0, 0, "Peashooter")], plants=[], zombies=[SimpleNamespace(row=2)])
        decision = policy.select_action(np.zeros(1), mask, state=raw)
        self.assertEqual((decision.action_index, decision.reason), (0, "no_preferred_legal_placement"))

    def test_runner_resets_once_collects_metrics_and_preserves_logging(self):
        initial, before, after = state(), state(), state()
        reader, controller, sink = Reader(initial, before, after), Controller(), Sink()
        env = PvZEnvironment(reader, controller, sleeper=lambda _: None, clock=lambda: 1.0, transition_sink=sink)
        result = run_episode(env, WaitPolicy(), EpisodeConfig("run-a", max_steps=1))
        self.assertEqual((reader.calls, result.episode_id, result.steps, result.wait_actions), (3, "run-a", 1, 1))
        self.assertTrue(result.truncated)
        self.assertEqual((result.reward_schema_version, result.reward_spec_name), (1, "reward-v1-default"))
        self.assertEqual([(record.episode_id, record.step_index) for record in sink.records], [("run-a", 0)])

    def test_runner_stops_on_natural_termination_and_summary_is_auditable(self):
        env = PvZEnvironment(Reader(state(), state(), state()), Controller(), sleeper=lambda _: None, clock=lambda: 1.0)
        terminal = run_episode(env, WaitPolicy(), EpisodeConfig("win", terminal_detector=TerminalDetector()))
        truncated = EpisodeResult("cut", "wait-policy", {}, 2, -0.1, False, True, OutcomeReason.MAX_STEPS,
            2, 0, 1, 0, 0, 0, 1, "reward-v1-default")
        summary = summarize_episodes([terminal, truncated])
        self.assertEqual((terminal.steps, terminal.outcome_reason), (1, OutcomeReason.WIN))
        self.assertEqual((summary.episode_count, summary.wins, summary.losses, summary.win_rate), (2, 1, 0, 1.0))
        self.assertEqual((summary.termination_count, summary.truncation_count, summary.rejection_count), (1, 1, 1))
        no_natural = summarize_episodes([truncated])
        self.assertIsNone(no_natural.win_rate)
        with self.assertRaises(ValueError): summarize_episodes([])


if __name__ == "__main__":
    unittest.main()
