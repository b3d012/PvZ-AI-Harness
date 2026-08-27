"""Focused non-live tests for semantic pickup collection."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.controller import PvZController, pickup_was_collected
from pvz_controller.windows_input import GameWindowUnavailable


def pickup(
    *,
    slot=3,
    type_id=4,
    x=320.4,
    y=240.6,
    collected=False,
    collectible=True,
):
    return SimpleNamespace(
        slot=slot,
        type_id=type_id,
        x=x,
        y=y,
        collected=collected,
        collectible=collectible,
    )


def state(*pickups, paused=False):
    return SimpleNamespace(paused=paused, pickups=list(pickups))


class FakeInputBackend:
    def __init__(self, error=None):
        self.clicks = []
        self.error = error

    def left_click(self, x, y):
        if self.error is not None:
            raise self.error
        self.clicks.append((x, y))


class ControllerPickupTests(unittest.TestCase):
    def test_collects_current_pickup_with_exactly_one_click(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(state(pickup()), 3)

        self.assertTrue(result.attempted)
        self.assertIsNone(result.success)
        self.assertEqual(result.reason, "click_issued")
        self.assertEqual(backend.clicks, [(320, 241)])

    def test_rejects_already_collected_pickup_without_click(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(
            state(pickup(collected=True)),
            3,
        )

        self.assertEqual(result.reason, "pickup_unavailable")
        self.assertFalse(result.attempted)
        self.assertEqual(backend.clicks, [])

    def test_rejects_pickup_missing_from_supplied_state(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(state(), 3)

        self.assertEqual(result.reason, "pickup_not_in_state")
        self.assertEqual(backend.clicks, [])

    def test_rejects_paused_game_without_click(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(
            state(pickup(), paused=True),
            3,
        )

        self.assertEqual(result.reason, "game_paused")
        self.assertEqual(backend.clicks, [])

    def test_rejects_invalid_pickup_coordinate_without_click(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(
            state(pickup(x=float("nan"))),
            3,
        )

        self.assertTrue(result.reason.startswith("coordinate_out_of_bounds:"))
        self.assertEqual(backend.clicks, [])

    def test_missing_window_returns_safe_result(self):
        backend = FakeInputBackend(
            GameWindowUnavailable("Plants vs. Zombies window not found")
        )
        result = PvZController(backend).collect_pickup(state(pickup()), 3)

        self.assertTrue(result.reason.startswith("game_window_unavailable:"))
        self.assertFalse(result.attempted)
        self.assertEqual(backend.clicks, [])

    def test_verification_detects_disappearance(self):
        before = pickup()
        self.assertTrue(pickup_was_collected(before, state()))
        self.assertFalse(pickup_was_collected(before, state(before)))
        self.assertIsNone(pickup_was_collected(before, None))


if __name__ == "__main__":
    unittest.main()
