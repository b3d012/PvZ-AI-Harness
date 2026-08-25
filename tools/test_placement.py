"""Focused checks for Phase 1.3A ordinary-grass placement validity."""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.placement import can_plant


def make_state(
    *,
    scene=0,
    seed_type_id=0,
    ready=True,
    affordable=True,
    plants=None,
    grid_items=None,
):
    """Create only the state fields required by the placement checker."""
    return SimpleNamespace(
        seeds=[
            SimpleNamespace(
                slot=0,
                type_id=seed_type_id,
                imitater_target_id=None,
                ready=ready,
                affordable=affordable,
                actionable=ready and affordable,
            )
        ],
        scene=scene,
        plants=plants or [],
        grid_items=grid_items or [],
    )


class PlacementTests(unittest.TestCase):
    def test_valid_empty_grass_tile(self):
        result = can_plant(make_state(), 0, 2, 4)

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_out_of_bounds_tile(self):
        result = can_plant(make_state(), 0, 6, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "row_out_of_bounds")

    def test_occupied_tile(self):
        result = can_plant(
            make_state(plants=[SimpleNamespace(row=2, col=4)]),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "tile_occupied")

    def test_grave_tile(self):
        result = can_plant(
            make_state(
                grid_items=[
                    SimpleNamespace(row=2, col=4, type_id=1, dead=False)
                ]
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "tile_blocked")

    def test_crater_tile(self):
        result = can_plant(
            make_state(
                grid_items=[
                    SimpleNamespace(row=2, col=4, type_id=2, dead=False)
                ]
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "tile_blocked")

    def test_not_ready_seed(self):
        result = can_plant(make_state(ready=False), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "seed_not_ready")

    def test_unaffordable_seed(self):
        result = can_plant(make_state(affordable=False), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "insufficient_sun")

    def test_ordinary_plant_on_empty_roof_tile(self):
        result = can_plant(make_state(scene=4), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "roof_requires_flower_pot")

    def test_flower_pot_on_empty_roof_tile(self):
        result = can_plant(make_state(scene=4, seed_type_id=33), 0, 2, 4)

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_ordinary_plant_on_roof_tile_with_flower_pot(self):
        result = can_plant(
            make_state(
                scene=4,
                plants=[SimpleNamespace(row=2, col=4, type_id=33)],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_ordinary_plant_on_water_without_lily_pad(self):
        result = can_plant(make_state(scene=2), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "water_requires_lily_pad")

    def test_lily_pad_on_pool_water_tile(self):
        result = can_plant(make_state(scene=2, seed_type_id=16), 0, 2, 4)

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_ordinary_land_plant_on_water_with_lily_pad(self):
        result = can_plant(
            make_state(
                scene=2,
                plants=[SimpleNamespace(row=2, col=4, type_id=16)],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")


if __name__ == "__main__":
    unittest.main()
