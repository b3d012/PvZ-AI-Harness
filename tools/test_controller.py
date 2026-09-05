"""Focused non-live tests for semantic pickup collection."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from unittest.mock import patch

from pvz_controller.controller import (
    PvZController,
    SEED_SELECTION_SETTLE_DELAY,
    SHOVEL_SELECTION_SETTLE_DELAY,
    TARGET_TILE_MOVE_SETTLE_DELAY,
    plant_was_placed,
    plant_was_removed,
    pickup_was_collected,
)
from pvz_controller.windows_input import (
    ControllerInputError,
    GameWindowUnavailable,
)


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


def seed(
    *,
    slot=1,
    type_id=1,
    name="Sunflower",
    ready=True,
    affordable=True,
    actionable=True,
):
    return SimpleNamespace(
        slot=slot,
        type_id=type_id,
        name=name,
        ready=ready,
        affordable=affordable,
        actionable=actionable,
        imitater_target_id=None,
    )


def plant_state(
    *seeds,
    paused=False,
    scene=0,
    plants=None,
    grid_items=None,
):
    packets = list(seeds)
    if len(packets) == 1:
        packets.extend(
            seed(slot=slot, actionable=False)
            for slot in range(6)
            if slot != packets[0].slot
        )
    return SimpleNamespace(
        paused=paused,
        seeds=packets,
        scene=scene,
        plants=plants or [],
        grid_items=grid_items or [],
    )


def shovel_state(*plants, paused=False, seed_count=6):
    return SimpleNamespace(
        paused=paused,
        scene=0,
        plants=list(plants),
        seeds=[SimpleNamespace(slot=index) for index in range(seed_count)],
    )


class FakeInputBackend:
    def __init__(self, error=None, error_on_click=None):
        self.clicks = []
        self.error = error
        self.error_on_click = error_on_click
        self.move_settle_delays = []
        self.events = []

    def left_click(self, x, y, *, move_settle_delay=0.0):
        if self.error is not None or self.error_on_click == len(self.clicks) + 1:
            error = self.error or ControllerInputError("simulated input failure")
            raise error
        self.clicks.append((x, y))
        self.move_settle_delays.append(move_settle_delay)
        self.events.append(("click", x, y))


class ControllerPickupTests(unittest.TestCase):
    def test_invalid_game_state_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).collect_pickup(None, 3)

        self.assertEqual(result.reason, "invalid_game_state")
        self.assertFalse(result.attempted)
        self.assertEqual(backend.clicks, [])

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


class ControllerPlantTests(unittest.TestCase):
    def test_valid_plant_issues_seed_then_tile_click(self):
        backend = FakeInputBackend()
        with patch(
            "pvz_controller.controller.time.sleep",
            side_effect=lambda delay: backend.events.append(("sleep", delay)),
        ):
            result = PvZController(backend).plant(plant_state(seed()), 1, 2, 3)

        self.assertEqual(result.reason, "clicks_issued")
        self.assertTrue(result.attempted)
        self.assertIsNone(result.success)
        self.assertEqual(backend.clicks, [(169, 43), (360, 330)])
        self.assertEqual(backend.move_settle_delays, [0.0, TARGET_TILE_MOVE_SETTLE_DELAY])
        self.assertEqual(
            backend.events,
            [
                ("click", 169, 43),
                ("sleep", SEED_SELECTION_SETTLE_DELAY),
                ("click", 360, 330),
            ],
        )

    def test_invalid_seed_slot_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).plant(plant_state(seed()), 9, 2, 3)

        self.assertEqual(result.reason, "invalid_seed_slot")
        self.assertEqual(backend.clicks, [])

    def test_invalid_tile_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).plant(plant_state(seed()), 1, 6, 3)

        self.assertTrue(result.reason.startswith("invalid_tile:"))
        self.assertEqual(backend.clicks, [])

    def test_illegal_placement_issues_zero_clicks(self):
        backend = FakeInputBackend()
        occupied = SimpleNamespace(row=2, col=3, type_id=0)
        result = PvZController(backend).plant(
            plant_state(seed(), plants=[occupied]),
            1,
            2,
            3,
        )

        self.assertEqual(result.reason, "placement_invalid:tile_occupied")
        self.assertEqual(backend.clicks, [])

    def test_paused_game_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).plant(plant_state(seed(), paused=True), 1, 2, 3)

        self.assertEqual(result.reason, "game_paused")
        self.assertEqual(backend.clicks, [])

    def test_missing_or_minimized_window_fails_safely(self):
        for message in (
            "Plants vs. Zombies window not found",
            "Plants vs. Zombies window is minimized",
        ):
            with self.subTest(message=message):
                backend = FakeInputBackend(GameWindowUnavailable(message))
                result = PvZController(backend).plant(plant_state(seed()), 1, 2, 3)

                self.assertTrue(result.reason.startswith("game_window_unavailable:"))
                self.assertFalse(result.attempted)
                self.assertEqual(backend.clicks, [])

    def test_coordinate_conversion_failure_issues_zero_clicks(self):
        backend = FakeInputBackend()
        with patch("pvz_controller.controller.tile_to_client", side_effect=ValueError("bad tile")):
            result = PvZController(backend).plant(plant_state(seed()), 1, 2, 3)

        self.assertEqual(result.reason, "invalid_tile:bad tile")
        self.assertEqual(backend.clicks, [])

    def test_input_failure_returns_safe_result(self):
        backend = FakeInputBackend(ControllerInputError("mouse rejected"))
        result = PvZController(backend).plant(plant_state(seed()), 1, 2, 3)

        self.assertEqual(result.reason, "input_failed:mouse rejected")
        self.assertFalse(result.attempted)
        self.assertEqual(backend.clicks, [])

    def test_second_click_failure_reports_partial_attempt(self):
        backend = FakeInputBackend(error_on_click=2)
        result = PvZController(backend).plant(plant_state(seed()), 1, 2, 3)

        self.assertEqual(result.reason, "input_failed:simulated input failure")
        self.assertTrue(result.attempted)
        self.assertFalse(result.success)
        self.assertEqual(backend.clicks, [(169, 43)])

    def test_plant_verification_detects_expected_plant(self):
        expected_seed = seed()
        after = plant_state(
            expected_seed,
            plants=[SimpleNamespace(type_id=1, row=2, col=3)],
        )

        self.assertTrue(plant_was_placed(expected_seed, 2, 3, after))
        self.assertFalse(plant_was_placed(expected_seed, 2, 3, plant_state()))
        self.assertIsNone(plant_was_placed(expected_seed, 2, 3, None))


class ControllerShovelTests(unittest.TestCase):
    def test_valid_shovel_issues_ui_then_tile_click(self):
        backend = FakeInputBackend()
        target = SimpleNamespace(type_id=1, row=2, col=3)
        with patch(
            "pvz_controller.controller.time.sleep",
            side_effect=lambda delay: backend.events.append(("sleep", delay)),
        ):
            result = PvZController(backend).shovel(shovel_state(target), 2, 3)

        self.assertEqual(result.reason, "clicks_issued")
        self.assertTrue(result.attempted)
        self.assertIsNone(result.success)
        self.assertEqual(backend.clicks, [(491, 36), (360, 330)])
        self.assertEqual(
            backend.move_settle_delays,
            [0.0, TARGET_TILE_MOVE_SETTLE_DELAY],
        )
        self.assertEqual(
            backend.events,
            [
                ("click", 491, 36),
                ("sleep", SHOVEL_SELECTION_SETTLE_DELAY),
                ("click", 360, 330),
            ],
        )

    def test_empty_tile_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).shovel(shovel_state(), 2, 3)

        self.assertEqual(result.reason, "no_plant_at_tile")
        self.assertEqual(backend.clicks, [])

    def test_invalid_tile_issues_zero_clicks(self):
        backend = FakeInputBackend()
        result = PvZController(backend).shovel(shovel_state(), 6, 3)

        self.assertTrue(result.reason.startswith("invalid_tile:"))
        self.assertEqual(backend.clicks, [])

    def test_paused_game_issues_zero_clicks(self):
        backend = FakeInputBackend()
        target = SimpleNamespace(type_id=1, row=2, col=3)
        result = PvZController(backend).shovel(shovel_state(target, paused=True), 2, 3)

        self.assertEqual(result.reason, "game_paused")
        self.assertEqual(backend.clicks, [])

    def test_missing_or_minimized_window_fails_safely(self):
        target = SimpleNamespace(type_id=1, row=2, col=3)
        for message in (
            "Plants vs. Zombies window not found",
            "Plants vs. Zombies window is minimized",
        ):
            with self.subTest(message=message):
                backend = FakeInputBackend(GameWindowUnavailable(message))
                result = PvZController(backend).shovel(shovel_state(target), 2, 3)

                self.assertTrue(result.reason.startswith("game_window_unavailable:"))
                self.assertFalse(result.attempted)
                self.assertEqual(backend.clicks, [])

    def test_coordinate_conversion_failure_issues_zero_clicks(self):
        backend = FakeInputBackend()
        target = SimpleNamespace(type_id=1, row=2, col=3)
        with patch("pvz_controller.controller.shovel_to_client", side_effect=ValueError("bad shovel")):
            result = PvZController(backend).shovel(shovel_state(target), 2, 3)

        self.assertEqual(result.reason, "coordinate_out_of_bounds:bad shovel")
        self.assertEqual(backend.clicks, [])

    def test_input_failure_returns_safe_result(self):
        backend = FakeInputBackend(ControllerInputError("mouse rejected"))
        target = SimpleNamespace(type_id=1, row=2, col=3)
        result = PvZController(backend).shovel(shovel_state(target), 2, 3)

        self.assertEqual(result.reason, "input_failed:mouse rejected")
        self.assertFalse(result.attempted)
        self.assertEqual(backend.clicks, [])

    def test_verification_detects_removed_plant(self):
        target = SimpleNamespace(type_id=1, row=2, col=3)
        self.assertTrue(plant_was_removed(target, shovel_state()))
        self.assertFalse(plant_was_removed(target, shovel_state(target)))
        self.assertIsNone(plant_was_removed(target, None))


if __name__ == "__main__":
    unittest.main()
