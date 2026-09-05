"""Focused non-live tests for Phase 2 controller coordinates."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.coordinates import (
    pickup_to_client,
    scale_logical_to_client,
    seed_slot_to_client,
    shovel_to_client,
    tile_to_client,
)


class ControllerCoordinateTests(unittest.TestCase):
    def test_normal_five_lane_tile_centers(self):
        self.assertEqual(tile_to_client(0, 0, scene=0), (120, 130))
        self.assertEqual(tile_to_client(4, 8, scene=0), (760, 530))

    def test_pool_and_fog_six_lane_tile_centers(self):
        self.assertEqual(tile_to_client(0, 0, scene=2), (120, 122))
        self.assertEqual(tile_to_client(5, 8, scene=3), (760, 547))

    def test_roof_tile_centers_follow_input_slope(self):
        self.assertEqual(tile_to_client(0, 0, scene=4), (120, 210))
        self.assertEqual(tile_to_client(0, 4, scene=4), (440, 130))

    def test_invalid_tile_rejected(self):
        for row, col in ((-1, 0), (6, 0), (0, -1), (0, 9)):
            with self.subTest(row=row, col=col):
                with self.assertRaises(ValueError):
                    tile_to_client(row, col)

    def test_six_packet_seed_slot_centers(self):
        self.assertEqual(seed_slot_to_client(0, seed_count=6), (110, 43))
        self.assertEqual(seed_slot_to_client(5, seed_count=6), (405, 43))

    def test_seed_packet_positions_depend_on_packet_count(self):
        self.assertEqual(seed_slot_to_client(0, seed_count=8), (106, 43))
        self.assertEqual(seed_slot_to_client(7, seed_count=8), (484, 43))
        self.assertEqual(seed_slot_to_client(9, seed_count=10), (563, 43))

    def test_invalid_seed_slot_rejected(self):
        for slot in (-1, 10):
            with self.subTest(slot=slot):
                with self.assertRaises(ValueError):
                    seed_slot_to_client(slot)

    def test_shovel_center_tracks_seed_bank_width(self):
        self.assertEqual(shovel_to_client(6), (491, 36))
        self.assertEqual(shovel_to_client(7), (551, 36))
        self.assertEqual(shovel_to_client(10), (644, 36))

    def test_invalid_shovel_seed_count_rejected(self):
        for count in (0, 11):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    shovel_to_client(count)

    def test_pickup_position(self):
        self.assertEqual(pickup_to_client(201.4, 310.6), (201, 311))

    def test_invalid_pickup_position_rejected(self):
        for point in ((-1.0, 100.0), (100.0, 600.0), (float("nan"), 0.0)):
            with self.subTest(point=point):
                with self.assertRaises(ValueError):
                    pickup_to_client(*point)

    def test_logical_point_scales_to_actual_client(self):
        self.assertEqual(scale_logical_to_client(400, 300, 1600, 900), (800, 450))


if __name__ == "__main__":
    unittest.main()
