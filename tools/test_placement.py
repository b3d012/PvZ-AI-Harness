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

    def test_tangle_kelp_on_water_without_lily_pad(self):
        result = can_plant(make_state(scene=2, seed_type_id=19), 0, 2, 4)

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_tangle_kelp_on_land_tile(self):
        result = can_plant(make_state(scene=2, seed_type_id=19), 0, 1, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "aquatic_requires_water")

    def test_tangle_kelp_on_roof(self):
        result = can_plant(make_state(scene=4, seed_type_id=19), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "aquatic_requires_water")

    def test_sea_shroom_on_water_without_lily_pad(self):
        result = can_plant(make_state(scene=2, seed_type_id=24), 0, 2, 4)

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_sea_shroom_on_land_tile(self):
        result = can_plant(make_state(scene=2, seed_type_id=24), 0, 1, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "aquatic_requires_water")

    def test_sea_shroom_on_roof(self):
        result = can_plant(make_state(scene=4, seed_type_id=24), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "aquatic_requires_water")

    def test_cattail_on_lily_pad(self):
        result = can_plant(
            make_state(
                scene=2,
                seed_type_id=43,
                plants=[SimpleNamespace(row=2, col=4, type_id=16)],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_grave_buster_on_grave(self):
        result = can_plant(
            make_state(
                seed_type_id=11,
                grid_items=[
                    SimpleNamespace(row=2, col=4, type_id=1, dead=False)
                ],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_grave_buster_without_grave(self):
        result = can_plant(make_state(seed_type_id=11), 0, 2, 4)

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "grave_buster_requires_grave")

    def test_coffee_bean_on_sleeping_mushroom(self):
        result = can_plant(
            make_state(
                seed_type_id=35,
                plants=[
                    SimpleNamespace(row=2, col=4, type_id=8, asleep=True)
                ],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_coffee_bean_on_awake_mushroom(self):
        result = can_plant(
            make_state(
                seed_type_id=35,
                plants=[
                    SimpleNamespace(row=2, col=4, type_id=8, asleep=False)
                ],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "coffee_target_awake")

    def test_coffee_bean_on_non_mushroom(self):
        result = can_plant(
            make_state(
                seed_type_id=35,
                plants=[
                    SimpleNamespace(row=2, col=4, type_id=0, asleep=False)
                ],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "coffee_target_not_mushroom")

    def test_pumpkin_over_normal_plant(self):
        result = can_plant(
            make_state(
                seed_type_id=30,
                plants=[SimpleNamespace(row=2, col=4, type_id=0)],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_pumpkin_when_pumpkin_already_present(self):
        result = can_plant(
            make_state(
                seed_type_id=30,
                plants=[SimpleNamespace(row=2, col=4, type_id=30)],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "pumpkin_already_present")

    def test_gatling_pea_on_repeater(self):
        result = can_plant(
            make_state(
                seed_type_id=40,
                plants=[SimpleNamespace(row=2, col=4, type_id=7)],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_gatling_pea_without_repeater(self):
        result = can_plant(
            make_state(
                seed_type_id=40,
                plants=[SimpleNamespace(row=2, col=4, type_id=0)],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "upgrade_requires_base")

    def test_cob_cannon_on_adjacent_kernel_pults(self):
        result = can_plant(
            make_state(
                seed_type_id=47,
                plants=[
                    SimpleNamespace(row=2, col=4, type_id=34),
                    SimpleNamespace(row=2, col=5, type_id=34),
                ],
            ),
            0,
            2,
            4,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "valid")

    def test_cob_cannon_with_one_kernel_pult(self):
        result = can_plant(
            make_state(
                seed_type_id=47,
                plants=[SimpleNamespace(row=2, col=4, type_id=34)],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "cob_cannon_requires_kernel_pair")

    def test_cob_cannon_with_non_adjacent_kernel_pults(self):
        result = can_plant(
            make_state(
                seed_type_id=47,
                plants=[
                    SimpleNamespace(row=2, col=4, type_id=34),
                    SimpleNamespace(row=2, col=6, type_id=34),
                ],
            ),
            0,
            2,
            4,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "cob_cannon_requires_kernel_pair")


if __name__ == "__main__":
    unittest.main()
