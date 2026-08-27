"""Offline checks for the deterministic Phase 3.2 semantic action space."""

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_env import (
    ACTION_COUNT,
    ACTION_SCHEMA_VERSION,
    ACTION_SPEC,
    DEFERRED_ACTION_TYPES,
    PLANT_INDEX_START,
    ActionType,
    SemanticAction,
    build_action_mask,
    decode_action,
    encode_action,
    normalize_active_rows,
)


def seed(slot=0, type_id=0, ready=True, affordable=True, actionable=True):
    return SimpleNamespace(
        slot=slot,
        type_id=type_id,
        imitater_target_id=None,
        ready=ready,
        affordable=affordable,
        actionable=actionable,
    )


def state(*, seeds=None, scene=0, paused=False, plants=None, grid_items=None, zombies=None):
    return SimpleNamespace(
        seeds=seeds if seeds is not None else [seed()],
        scene=scene,
        paused=paused,
        plants=plants or [],
        grid_items=grid_items or [],
        zombies=zombies or [],
    )


def plant(row, col, type_id, asleep=False):
    return SimpleNamespace(row=row, col=col, type_id=type_id, asleep=asleep)


def grid_item(row, col, type_id):
    return SimpleNamespace(row=row, col=col, type_id=type_id, dead=False)


class ActionSpaceTests(unittest.TestCase):
    def index(self, seed_slot, row, col):
        return encode_action(SemanticAction(ActionType.PLANT, seed_slot, row, col))

    def test_schema_metadata_and_fixed_count(self):
        self.assertEqual(ACTION_SCHEMA_VERSION, 1)
        self.assertEqual(ACTION_SPEC.version, 1)
        self.assertEqual(ACTION_COUNT, 541)
        self.assertEqual(ACTION_SPEC.action_count, 541)
        self.assertEqual(ACTION_SPEC.wait_index, 0)
        self.assertEqual(ACTION_SPEC.plant_index_start, 1)
        self.assertEqual(ACTION_SPEC.plant_index_stop, 541)
        self.assertEqual(DEFERRED_ACTION_TYPES, ("shovel", "collect_pickup"))

    def test_wait_and_plant_index_boundaries_round_trip(self):
        self.assertEqual(decode_action(0), SemanticAction(ActionType.WAIT))
        self.assertEqual(encode_action(SemanticAction(ActionType.WAIT)), 0)
        self.assertEqual(decode_action(PLANT_INDEX_START), SemanticAction(ActionType.PLANT, 0, 0, 0))
        self.assertEqual(decode_action(ACTION_COUNT - 1), SemanticAction(ActionType.PLANT, 9, 5, 8))
        for index in (0, 1, 54, 55, 540):
            self.assertEqual(encode_action(decode_action(index)), index)

    def test_invalid_indices_and_actions_are_rejected(self):
        for index in (-1, ACTION_COUNT, True, 1.5):
            with self.subTest(index=index), self.assertRaises(ValueError):
                decode_action(index)
        for action in (
            SemanticAction(ActionType.WAIT, 0, 0, 0),
            SemanticAction(ActionType.PLANT, None, 0, 0),
            SemanticAction(ActionType.PLANT, 10, 0, 0),
            SemanticAction(ActionType.PLANT, 0, 6, 0),
            SemanticAction(ActionType.PLANT, 0, 0, 9),
        ):
            with self.subTest(action=action), self.assertRaises(ValueError):
                encode_action(action)

    def test_active_row_configuration_is_explicit_and_validated(self):
        self.assertEqual(normalize_active_rows(), (True, True, True, True, True, True))
        self.assertEqual(normalize_active_rows((False, True, True, True, False, False)), (False, True, True, True, False, False))
        for rows in ((True,) * 5, (1,) * 6):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                normalize_active_rows(rows)

    def test_wait_is_valid_for_playable_state_and_invalid_when_paused(self):
        self.assertTrue(build_action_mask(state())[0])
        self.assertFalse(build_action_mask(state(paused=True)).any())

    def test_absent_and_unavailable_seed_slots_are_masked(self):
        cases = (
            state(seeds=[]),
            state(seeds=[seed(0, ready=False)]),
            state(seeds=[seed(0, affordable=False)]),
            state(seeds=[seed(0, actionable=False)]),
        )
        for current in cases:
            with self.subTest(current=current):
                mask = build_action_mask(current)
                self.assertTrue(mask[0])
                self.assertFalse(mask[PLANT_INDEX_START:].any())

    def test_ordinary_placement_and_occupied_tile_masking(self):
        valid = build_action_mask(state())
        occupied = build_action_mask(state(plants=[plant(2, 4, 0)]))
        target = self.index(0, 2, 4)
        self.assertTrue(valid[target])
        self.assertFalse(occupied[target])

    def test_pool_roof_grave_and_upgrade_rules_delegate_to_placement(self):
        pool = build_action_mask(state(scene=2))
        pool_supported = build_action_mask(state(scene=2, plants=[plant(2, 4, 16)]))
        roof = build_action_mask(state(scene=4))
        roof_supported = build_action_mask(state(scene=4, plants=[plant(2, 4, 33)]))
        grave_buster = build_action_mask(state(seeds=[seed(type_id=11)], grid_items=[grid_item(2, 4, 1)]))
        blocked = build_action_mask(state(grid_items=[grid_item(2, 4, 1)]))
        upgrade = build_action_mask(state(seeds=[seed(type_id=40)], plants=[plant(2, 4, 7)]))
        no_upgrade = build_action_mask(state(seeds=[seed(type_id=40)], plants=[plant(2, 4, 0)]))
        target = self.index(0, 2, 4)

        self.assertFalse(pool[target])
        self.assertTrue(pool_supported[target])
        self.assertFalse(roof[target])
        self.assertTrue(roof_supported[target])
        self.assertTrue(grave_buster[target])
        self.assertFalse(blocked[target])
        self.assertTrue(upgrade[target])
        self.assertFalse(no_upgrade[target])

    def test_inactive_rows_mask_every_plant_but_not_active_rows(self):
        rows = (False, True, True, True, False, False)
        masked = build_action_mask(state(), active_rows=rows)
        default = build_action_mask(state())
        for row, active in enumerate(rows):
            row_indices = [self.index(0, row, col) for col in range(9)]
            self.assertEqual(masked[row_indices].any(), active)
            if active:
                self.assertTrue(np.array_equal(masked[row_indices], default[row_indices]))

    def test_mask_shape_is_fixed_deterministic_and_state_is_not_mutated(self):
        current = state(seeds=[seed(3)], zombies=[SimpleNamespace(row=1)])
        before = copy.deepcopy(current)
        masks = [
            build_action_mask(current, active_rows=rows)
            for rows in (None, (True,) * 6, (False, True, True, True, False, False))
        ]
        variants = (
            state(seeds=[]),
            state(seeds=[seed(0), seed(9)], zombies=[SimpleNamespace(row=5)]),
            state(scene=2),
            state(scene=4),
        )

        self.assertEqual(current, before)
        self.assertTrue(np.array_equal(masks[0], masks[1]))
        for mask in [*masks, *(build_action_mask(item) for item in variants)]:
            self.assertEqual(mask.shape, (ACTION_COUNT,))
            self.assertEqual(mask.dtype, np.bool_)


if __name__ == "__main__":
    unittest.main()
