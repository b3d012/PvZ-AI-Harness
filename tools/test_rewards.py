"""Offline Phase 3.5 reward/outcome checks; no live game or input is used."""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import ActionResult
from pvz_env import (
    ACTION_COUNT, ActionType, EpisodeConfig, OutcomeReason, PvZEnvironment, RewardModel,
    RewardSpec, SemanticAction, encode_action,
)


def state(*, spawned=0, paused=False, seeds=True):
    return SimpleNamespace(
        sun=250, game_clock=100, scene=0, adventure_level=1, paused=paused,
        plant_capacity=10, zombie_capacity=10,
        wave=SimpleNamespace(total_waves=10, spawned_waves=spawned, refreshed_waves=0,
            next_wave_countdown=100, next_wave_countdown_initial=100, next_wave_timer_ratio=0.0,
            huge_wave_countdown=0, huge_wave_incoming=False, refresh_hp=0, current_wave_hp=0),
        plants=[], zombies=[], seeds=[] if not seeds else [SimpleNamespace(slot=0, type_id=0, name="Peashooter",
            imitater_target_id=None, cost=100, cooldown_elapsed=100, cooldown_total=100,
            cooldown_ratio=1.0, ready=True, cooling_down=False, selected=False, affordable=True,
            actionable=True, use_counter=0)], mowers=[], pickups=[], projectiles=[], grid_items=[])


class Reader:
    def __init__(self, *states): self.states = list(states)
    def read(self): return self.states.pop(0) if self.states else None


class Controller:
    def __init__(self, result=ActionResult(True, None, "clicks_issued")): self.result = result
    def plant(self, *_): return self.result


class Detector:
    def __init__(self, result): self.result = result
    def detect(self, before, after): return self.result


class RewardTests(unittest.TestCase):
    def env(self, *states, **kwargs):
        episode_kwargs = {name: kwargs.pop(name) for name in tuple(kwargs) if name in {
            "reward_spec", "terminal_detector", "max_steps", "max_consecutive_state_unavailable",
            "plant_reconciliation_timeout_seconds", "plant_reconciliation_poll_interval_seconds"}}
        env = PvZEnvironment(Reader(states[0], *states), Controller(kwargs.pop("controller_result", ActionResult(True, None, "ok"))),
            sleeper=lambda _: None, clock=lambda: 1.0, **kwargs)
        env.reset(EpisodeConfig("reward-test", **episode_kwargs))
        return env

    @staticmethod
    def plant_index(): return encode_action(SemanticAction(ActionType.PLANT, 0, 2, 4))

    def test_schema_default_and_deterministic_components(self):
        spec = RewardSpec()
        self.assertEqual((spec.schema_version, spec.name), (1, "reward-v1-default"))
        first = self.env(state(spawned=1), state(spawned=2)).step(0).outcome
        second = self.env(state(spawned=1), state(spawned=2)).step(0).outcome
        self.assertEqual(first, second)
        self.assertAlmostEqual(first.reward, sum(first.components.values()))
        self.assertEqual(first.components["wave_progress"], 0.01)

    def test_wait_and_unchanged_progress_do_not_farm_reward(self):
        env = self.env(state(spawned=2), state(spawned=2), state(spawned=2), state(spawned=2))
        self.assertEqual(env.step(0).outcome.reward, 0.0)
        self.assertEqual(env.step(0).outcome.reward, 0.0)

    def test_successful_plant_and_spending_sun_have_no_positive_activity_reward(self):
        after = state()
        after.plants = [SimpleNamespace(type_id=0, row=2, col=4, hp=300, max_hp=300,
            state=0, asleep=False, imitater=0)]
        result = self.env(state(), after).step(self.plant_index())
        self.assertEqual(result.outcome.reward, 0.0)
        self.assertEqual(result.outcome.components["wave_progress"], 0.0)

    def test_rejection_and_technical_failures_are_small_penalties(self):
        rejected = self.env(state()).step(ACTION_COUNT).outcome
        masked = self.env(state(seeds=False)).step(self.plant_index()).outcome
        controller = self.env(state(), state(), controller_result=ActionResult(False, False, "failed")).step(self.plant_index()).outcome
        missing = self.env(state(), state(), plant_reconciliation_timeout_seconds=0).step(self.plant_index()).outcome
        unavailable_env = PvZEnvironment(Reader(state(), None), Controller(), sleeper=lambda _: None, clock=lambda: 1.0)
        unavailable_env.reset(EpisodeConfig("unavailable"))
        unavailable = unavailable_env.step(0).outcome
        self.assertEqual(rejected.reward, RewardSpec().rejected_action_penalty)
        self.assertEqual(masked.reward, RewardSpec().rejected_action_penalty)
        self.assertEqual(controller.reward, RewardSpec().controller_failure_penalty)
        self.assertEqual(missing.reward, RewardSpec().plant_not_observed_penalty)
        self.assertEqual(unavailable.reward, 0.0)
        self.assertLessEqual(rejected.reward, 0.0)

    def test_terminal_detector_and_truncation_are_distinct(self):
        win = self.env(state(), state(), terminal_detector=Detector(OutcomeReason.WIN), max_steps=1).step(0).outcome
        loss = self.env(state(), state(), terminal_detector=Detector(OutcomeReason.LOSS)).step(0).outcome
        horizon = self.env(state(), state(), max_steps=1).step(0).outcome
        unavailable_env = PvZEnvironment(Reader(state(), None), Controller(), sleeper=lambda _: None, clock=lambda: 1.0)
        unavailable_env.reset(EpisodeConfig("unavailable", max_consecutive_state_unavailable=1))
        unavailable = unavailable_env.step(0).outcome
        self.assertEqual((win.reward, win.terminated, win.truncated, win.reason), (1.0, True, False, OutcomeReason.WIN))
        self.assertEqual((loss.reward, loss.terminated, loss.truncated, loss.reason), (-1.0, True, False, OutcomeReason.LOSS))
        self.assertEqual((horizon.terminated, horizon.truncated, horizon.reason), (False, True, OutcomeReason.MAX_STEPS))
        self.assertEqual((unavailable.terminated, unavailable.truncated, unavailable.reason), (False, True, OutcomeReason.STATE_UNAVAILABLE))

    def test_terminal_dominates_shaping_and_does_not_mutate(self):
        before, after = state(spawned=1), state(spawned=20)
        before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
        outcome = self.env(before, after, terminal_detector=Detector(OutcomeReason.WIN)).step(0).outcome
        self.assertEqual(outcome.reward, 1.0)
        self.assertEqual(outcome.components["wave_progress"], 0.0)
        self.assertEqual(before, before_copy)
        self.assertEqual(after, after_copy)
        with self.assertRaises(ValueError): RewardSpec(win_reward=float("inf"))
        with self.assertRaises(ValueError): RewardModel().evaluate(SimpleNamespace(before=None, after=None, action_legal=False, reconciliation=None, rejection_reason=None), step_index=-1)


if __name__ == "__main__":
    unittest.main()
