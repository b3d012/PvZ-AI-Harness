"""Offline Phase 3.3 checks using fakes; no live reader or input is used."""

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
    ACTION_COUNT,
    EnvironmentConfig,
    EpisodeConfig,
    EnvironmentStateUnavailable,
    OBSERVATION_SPEC,
    PvZEnvironment,
    ReconciliationStatus,
    StepRejectionReason,
    encode_action,
    ActionType,
    SemanticAction,
)


def seed(slot=0, type_id=0, ready=True, affordable=True, actionable=True):
    return SimpleNamespace(
        slot=slot, type_id=type_id, name="Peashooter", imitater_target_id=None,
        cost=100, cooldown_elapsed=100, cooldown_total=100, cooldown_ratio=1.0,
        ready=ready, cooling_down=False, selected=False, affordable=affordable,
        actionable=actionable, use_counter=0,
    )


def plant(row=2, col=4, type_id=0):
    return SimpleNamespace(
        slot=0, type_id=type_id, name="Peashooter", row=row, col=col, x=320,
        y=295, state=0, hp=300, max_hp=300, asleep=False, imitater=0,
    )


def state(*, paused=False, sun=250, seeds=None, plants=None):
    wave = SimpleNamespace(
        total_waves=10, spawned_waves=0, refreshed_waves=0,
        next_wave_countdown=100, next_wave_countdown_initial=100,
        next_wave_timer_ratio=0.0, huge_wave_countdown=0,
        huge_wave_incoming=False, refresh_hp=0, current_wave_hp=0,
    )
    return SimpleNamespace(
        sun=sun, game_clock=100, scene=0, adventure_level=1, paused=paused,
        plant_capacity=10, zombie_capacity=10, wave=wave, plants=plants or [],
        zombies=[], seeds=seeds if seeds is not None else [seed()], mowers=[],
        pickups=[], projectiles=[], grid_items=[],
    )


class FakeReader:
    def __init__(self, *states):
        self.states = list(states)
        self.calls = 0

    def read(self):
        self.calls += 1
        return self.states.pop(0) if self.states else None


class FakeController:
    def __init__(self, result=ActionResult(True, None, "clicks_issued")):
        self.result = result
        self.calls = []

    def plant(self, current_state, seed_slot, row, col):
        self.calls.append((current_state, seed_slot, row, col))
        return self.result


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        result = self.value
        self.value += 1.0
        return result


class EnvironmentStepTests(unittest.TestCase):
    def make_env(self, *states, controller=None, active_rows=None, interval=0.5, **episode_kwargs):
        self.sleeps = []
        self.reader = FakeReader(states[0], *states)
        self.controller = controller or FakeController()
        env = PvZEnvironment(
            self.reader, self.controller, sleeper=self.sleeps.append,
            clock=FakeClock(),
        )
        env.reset(EpisodeConfig("legacy-test", active_rows=active_rows or (True,) * 6,
            step_interval_seconds=interval, **episode_kwargs))
        return env

    def plant_index(self, row=2, col=4):
        return encode_action(SemanticAction(ActionType.PLANT, 0, row, col))

    def test_configuration_and_observe_flow_have_fixed_shapes(self):
        env = self.make_env(state())
        snapshot = env.observe()

        self.assertEqual(snapshot.observation.shape, OBSERVATION_SPEC.flat_shape)
        self.assertEqual(snapshot.action_mask.shape, (ACTION_COUNT,))
        self.assertEqual(snapshot.action_mask.dtype, np.bool_)
        self.assertTrue(snapshot.action_mask[0])
        self.assertEqual(self.reader.calls, 2)
        with self.assertRaises(ValueError):
            EnvironmentConfig(active_rows=(True,) * 5)
        with self.assertRaises(ValueError):
            EnvironmentConfig(step_interval_seconds=-0.1)

    def test_active_rows_propagate_to_observation_mask(self):
        env = self.make_env(state(), active_rows=(False, True, True, True, False, False))
        mask = env.observe().action_mask

        self.assertFalse(mask[self.plant_index(0, 4)])
        self.assertTrue(mask[self.plant_index(2, 4)])

    def test_wait_advances_once_without_controller_call(self):
        before, after = state(sun=100), state(sun=200)
        env = self.make_env(before, after)

        result = env.step(0)

        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.sleeps, [0.5])
        self.assertEqual(self.reader.calls, 3)
        self.assertIs(result.before.state, before)
        self.assertIs(result.after.state, after)
        self.assertEqual(result.reconciliation, ReconciliationStatus.WAIT_ADVANCED)
        self.assertTrue(result.timing.advancement_invoked)
        self.assertFalse(np.array_equal(result.before.observation, result.after.observation))

    def test_wait_with_missing_postcondition_is_not_reported_as_advanced(self):
        env = self.make_env(state(), None)

        result = env.step(0)

        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.sleeps, [0.5])
        self.assertEqual(result.reconciliation, ReconciliationStatus.POSTCONDITION_UNAVAILABLE)
        self.assertIsNone(result.after)

    def test_legal_plant_calls_controller_and_reconciles_observed_plant(self):
        before, after = state(), state(plants=[plant()])
        env = self.make_env(before, after)

        result = env.step(self.plant_index())

        self.assertEqual(self.controller.calls, [(before, 0, 2, 4)])
        self.assertEqual(self.sleeps, [0.5])
        self.assertEqual(result.reconciliation, ReconciliationStatus.PLANT_OBSERVED)
        self.assertTrue(result.action_legal)
        self.assertIsNotNone(result.controller_result)
        self.assertEqual(result.after.action_mask.shape, (ACTION_COUNT,))

    def test_masked_plant_never_calls_controller_or_advances(self):
        env = self.make_env(state(), active_rows=(False, True, True, True, False, False))

        result = env.step(self.plant_index(0, 4))

        self.assertEqual(result.rejection_reason, StepRejectionReason.ACTION_MASKED)
        self.assertEqual(result.reconciliation, ReconciliationStatus.REJECTED)
        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.reader.calls, 2)

    def test_invalid_action_index_is_rejected_safely(self):
        env = self.make_env(state())

        result = env.step(ACTION_COUNT)

        self.assertEqual(result.rejection_reason, StepRejectionReason.INVALID_ACTION_INDEX)
        self.assertIsNone(result.before)
        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.reader.calls, 1)

    def test_paused_state_rejects_without_controller_or_sleep(self):
        self.sleeps = []
        self.reader = FakeReader(state(paused=True))
        self.controller = FakeController()
        env = PvZEnvironment(self.reader, self.controller, sleeper=self.sleeps.append, clock=FakeClock())
        with self.assertRaises(Exception):
            env.reset(EpisodeConfig("paused"))
        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.sleeps, [])

    def test_missing_plant_postcondition_is_not_controller_failure(self):
        env = self.make_env(state(), state())

        result = env.step(self.plant_index())

        self.assertTrue(result.controller_result.attempted)
        self.assertEqual(result.reconciliation, ReconciliationStatus.PLANT_NOT_OBSERVED)

    def test_controller_failure_remains_distinct_from_postcondition_failure(self):
        controller = FakeController(ActionResult(False, False, "input_failed"))
        env = self.make_env(state(), state(plants=[plant()]), controller=controller)

        result = env.step(self.plant_index())

        self.assertEqual(result.reconciliation, ReconciliationStatus.CONTROLLER_FAILED)
        self.assertEqual(result.controller_result.reason, "input_failed")
        self.assertIsNotNone(result.after)

    def test_reader_unavailable_has_typed_runtime_outcome(self):
        env = PvZEnvironment(FakeReader(None), FakeController())
        with self.assertRaises(Exception):
            env.observe()
        with self.assertRaises(Exception):
            env.step(0)

    def test_postcondition_state_unavailable_is_distinct(self):
        env = self.make_env(state(), None)

        result = env.step(self.plant_index())

        self.assertEqual(result.reconciliation, ReconciliationStatus.POSTCONDITION_UNAVAILABLE)
        self.assertIsNone(result.after)

    def test_step_is_deterministic_and_does_not_mutate_states(self):
        before, after = state(), state(plants=[plant()])
        before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
        first = self.make_env(before, after).step(self.plant_index())
        second = self.make_env(copy.deepcopy(before_copy), copy.deepcopy(after_copy)).step(self.plant_index())

        self.assertEqual(before, before_copy)
        self.assertEqual(after, after_copy)
        self.assertEqual(first.reconciliation, second.reconciliation)
        self.assertTrue(np.array_equal(first.before.observation, second.before.observation))
        self.assertTrue(np.array_equal(first.after.action_mask, second.after.action_mask))


if __name__ == "__main__":
    unittest.main()
