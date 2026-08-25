"""Focused checks for Phase 1.3A ordinary-grass placement validity."""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.placement import can_plant


def make_state(*, ready=True, affordable=True, plants=None, grid_items=None):
    """Create only the state fields required by the placement checker."""
    return SimpleNamespace(
        seeds=[
            SimpleNamespace(
                slot=0,
                ready=ready,
                affordable=affordable,
                actionable=ready and affordable,
            )
        ],
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


if __name__ == "__main__":
    unittest.main()
