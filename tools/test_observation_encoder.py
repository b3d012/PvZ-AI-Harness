"""Offline checks for the deterministic Phase 3.1 observation encoder."""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_env import (
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SPEC,
    ObservationEncoder,
)


def wave(**overrides):
    values = dict(
        total_waves=10,
        spawned_waves=3,
        refreshed_waves=2,
        next_wave_countdown=50,
        next_wave_countdown_initial=100,
        next_wave_timer_ratio=0.5,
        huge_wave_countdown=0,
        huge_wave_incoming=False,
        refresh_hp=400,
        current_wave_hp=800,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def plant(**overrides):
    values = dict(
        slot=0,
        type_id=1,
        name="Sunflower",
        row=2,
        col=3,
        x=320,
        y=295,
        state=10,
        hp=200,
        max_hp=300,
        asleep=False,
        imitater=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def seed(**overrides):
    values = dict(
        slot=2,
        type_id=48,
        name="Imitater(Sunflower)",
        imitater_target_id=1,
        cost=50,
        cooldown_elapsed=0,
        cooldown_total=100,
        cooldown_ratio=0.25,
        ready=True,
        cooling_down=False,
        selected=False,
        affordable=True,
        actionable=True,
        use_counter=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def zombie(**overrides):
    values = dict(
        slot=0,
        type_id=2,
        name="Conehead Zombie",
        row=1,
        x=500.0,
        y=200.0,
        state=4,
        body_hp=270,
        body_max_hp=270,
        armor_hp=370,
        armor_max_hp=370,
        biting=False,
        hypnotized=False,
        slow_timer=0,
        stun_timer=0,
        freeze_timer=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def mower(**overrides):
    values = dict(
        slot=0,
        row=1,
        x=20.0,
        y=200.0,
        state=1,
        type_id=0,
        visible=True,
        dead=False,
        object_id=1,
        available=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def game_state(**overrides):
    values = dict(
        sun=250,
        game_clock=1200,
        scene=0,
        adventure_level=1,
        paused=False,
        plant_capacity=10,
        zombie_capacity=10,
        wave=wave(),
        plants=[],
        zombies=[],
        seeds=[],
        mowers=[],
        pickups=[],
        projectiles=[],
        grid_items=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class ObservationEncoderTests(unittest.TestCase):
    def setUp(self):
        self.encoder = ObservationEncoder()

    def components(self, encoded, name):
        shape = dict(OBSERVATION_SPEC.component_shapes)[name]
        return encoded[OBSERVATION_SPEC.component_slice(name)].reshape(shape)

    def test_schema_metadata_and_flat_shape_are_stable(self):
        self.assertEqual(OBSERVATION_SCHEMA_VERSION, 1)
        self.assertEqual(OBSERVATION_SPEC.version, 1)
        self.assertEqual(OBSERVATION_SPEC.flat_shape, (5534,))
        self.assertEqual(OBSERVATION_SPEC.deferred_fields, ("pickups", "projectiles", "grid_items"))
        self.assertEqual(OBSERVATION_SPEC.component_slice("global"), slice(0, 16))
        self.assertEqual(OBSERVATION_SPEC.zombie_aggregate_shape, (6, 2))
        self.assertEqual(
            OBSERVATION_SPEC.zombie_aggregate_feature_names,
            ("live_count_normalized", "overflow_count_normalized"),
        )
        with self.assertRaises(KeyError):
            OBSERVATION_SPEC.component_slice("pickups")

    def test_identical_state_encodes_deterministically_without_mutation(self):
        state = game_state(plants=[plant()], zombies=[zombie()], seeds=[seed()])
        before = copy.deepcopy(state)

        first = self.encoder.encode(state)
        second = self.encoder.encode(state)

        self.assertTrue(np.array_equal(first, second))
        self.assertEqual(first.dtype, np.float32)
        self.assertTrue(first.flags.c_contiguous)
        self.assertEqual(state, before)

    def test_empty_and_populated_states_have_identical_shape(self):
        empty = self.encoder.encode(game_state())
        populated = self.encoder.encode(
            game_state(
                plants=[plant()],
                zombies=[zombie()],
                seeds=[seed()],
                mowers=[mower()],
            )
        )

        self.assertEqual(empty.shape, OBSERVATION_SPEC.flat_shape)
        self.assertEqual(populated.shape, OBSERVATION_SPEC.flat_shape)
        self.assertTrue(np.all(self.components(empty, "board") == 0.0))

    def test_board_preserves_type_presence_and_stack_features(self):
        state = game_state(
            plants=[
                plant(slot=1, type_id=1, hp=150, max_hp=300),
                plant(slot=2, type_id=16, hp=300, max_hp=300),
                plant(slot=3, type_id=30, hp=0, max_hp=0, asleep=True),
            ]
        )
        board = self.components(self.encoder.encode(state), "board")
        cell = board[2, 3]

        self.assertEqual(cell[0], 1.0)
        self.assertEqual(cell[1], 1.0)
        self.assertAlmostEqual(cell[2], 0.5, places=6)
        self.assertEqual(cell[6], 1.0)
        self.assertEqual(cell[8], 1.0)
        self.assertEqual(cell[9 + 1], 1.0)
        self.assertEqual(cell[9 + 16], 1.0)
        self.assertEqual(cell[9 + 30], 1.0)

    def test_zombies_are_sorted_by_threat_and_aggregate_overflow(self):
        state = game_state(
            zombies=[
                zombie(slot=9, type_id=9, x=700),
                zombie(slot=8, type_id=8, x=100),
                zombie(slot=7, type_id=7, x=300),
                zombie(slot=6, type_id=6, x=200),
                zombie(slot=5, type_id=5, x=400),
                zombie(slot=4, type_id=4, x=500),
            ]
        )
        zombies = self.components(self.encoder.encode(state), "zombies")
        aggregates = self.components(self.encoder.encode(state), "zombie_aggregates")

        self.assertTrue(np.all(zombies[1, :, 0] == 1.0))
        self.assertEqual(zombies[1, 0, 1 + 8], 1.0)
        self.assertEqual(zombies[1, 4, 1 + 4], 1.0)
        self.assertEqual(zombies[1, 0, 36], 0.875)
        self.assertAlmostEqual(aggregates[1, 0], 6 / 50, places=6)
        self.assertAlmostEqual(aggregates[1, 1], 1 / 45, places=6)

    def test_zombie_overflow_distinguishes_matching_nearest_five(self):
        nearest_five = [
            zombie(slot=index, type_id=index, x=100 + index * 100)
            for index in range(5)
        ]
        five = self.encoder.encode(game_state(zombies=nearest_five))
        overflow = self.encoder.encode(
            game_state(zombies=nearest_five + [zombie(slot=5, type_id=9, x=700)])
        )

        self.assertTrue(
            np.array_equal(
                self.components(five, "zombies"), self.components(overflow, "zombies")
            )
        )
        self.assertFalse(np.array_equal(five, overflow))
        self.assertGreater(
            self.components(overflow, "zombie_aggregates")[1, 1], 0.0
        )

    def test_normalized_values_are_bounded(self):
        state = game_state(
            sun=999999,
            game_clock=999999999,
            wave=wave(
                total_waves=1,
                spawned_waves=999,
                refreshed_waves=999,
                next_wave_timer_ratio=99,
                huge_wave_countdown=999999999,
                current_wave_hp=999999999,
                refresh_hp=999999999,
            ),
            plants=[plant(hp=9999, max_hp=1, state=9999)],
            adventure_level=9999,
            zombies=[
                zombie(
                    slot=index,
                    x=-1000,
                    body_hp=9999,
                    body_max_hp=1,
                    slow_timer=9999,
                )
                for index in range(100)
            ],
        )
        encoded = self.encoder.encode(state)

        self.assertTrue(np.all(encoded >= 0.0))
        self.assertTrue(np.all(encoded <= 1.0))

    def test_seed_slots_preserve_existence_type_and_readiness(self):
        seeds = self.components(self.encoder.encode(game_state(seeds=[seed()])), "seeds")
        scalar_offset = 99

        self.assertTrue(np.all(seeds[0] == 0.0))
        self.assertEqual(seeds[2, 0], 1.0)
        self.assertEqual(seeds[2, 1 + 48], 1.0)
        self.assertEqual(seeds[2, 50 + 1], 1.0)
        self.assertEqual(seeds[2, scalar_offset + 2], 1.0)
        self.assertEqual(seeds[2, scalar_offset + 6], 1.0)

    def test_mowers_are_encoded_by_row(self):
        mowers = self.components(
            self.encoder.encode(game_state(mowers=[mower(row=4, available=False, visible=True, state=2)])),
            "mowers",
        )

        self.assertEqual(mowers[4, 0], 1.0)
        self.assertEqual(mowers[4, 1], 0.0)
        self.assertEqual(mowers[4, 2], 1.0)
        self.assertGreater(mowers[4, 3], 0.0)
        self.assertTrue(np.all(mowers[0] == 0.0))

    def test_scene_and_row_count_do_not_change_shape(self):
        for scene in range(5):
            with self.subTest(scene=scene):
                state = game_state(scene=scene, plants=[plant(row=2, col=4)])
                global_values = self.components(self.encoder.encode(state), "global")
                self.assertEqual(global_values[3 + scene], 1.0)
                self.assertEqual(self.encoder.encode(state).shape, OBSERVATION_SPEC.flat_shape)

    def test_adventure_level_is_encoded_and_does_not_change_shape(self):
        low = self.encoder.encode(game_state(adventure_level=1))
        high = self.encoder.encode(game_state(adventure_level=50))
        low_global = self.components(low, "global")
        high_global = self.components(high, "global")

        self.assertEqual(low.shape, high.shape)
        self.assertEqual(low.shape, OBSERVATION_SPEC.flat_shape)
        self.assertAlmostEqual(low_global[2], 1 / 50, places=6)
        self.assertEqual(high_global[2], 1.0)


if __name__ == "__main__":
    unittest.main()
