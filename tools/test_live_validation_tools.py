"""Offline checks for the bounded live-validation tool guards."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.live_test_controller_plant import _choose_requested_placement
from tools.live_test_seed_selection import selected_slots, validate_slot


def seed(slot=1, *, ready=True, affordable=True, actionable=True, selected=False):
    return SimpleNamespace(
        slot=slot, type_id=1, name="Sunflower", ready=ready,
        affordable=affordable, actionable=actionable, selected=selected,
    )


def state(*seeds, paused=False):
    return SimpleNamespace(
        paused=paused, seeds=list(seeds), scene=0, plants=[], grid_items=[], sun=500,
    )


class LivePlantTargetTests(unittest.TestCase):
    def test_requested_target_requires_exact_present_actionable_seed(self):
        choice, error = _choose_requested_placement(state(seed()), 2, 0, 4)
        self.assertIsNone(choice)
        self.assertIn("not present", error)
        choice, error = _choose_requested_placement(
            state(seed(1, actionable=False)), 1, 0, 4,
        )
        self.assertIsNone(choice)
        self.assertIn("not ready", error)

    def test_requested_target_returns_exact_legal_row_and_column(self):
        choice, error = _choose_requested_placement(state(seed()), 1, 3, 4)
        self.assertIsNone(error)
        self.assertEqual((choice[0].slot, choice[1]), (1, (3, 4)))


class SeedSelectionToolTests(unittest.TestCase):
    def test_selected_slots_and_preclick_guards(self):
        self.assertEqual(selected_slots(state(seed(0, selected=True), seed(1))), [0])
        choice, error = validate_slot(state(seed(0, selected=True), seed(1)), 1)
        self.assertIsNone(choice)
        self.assertIn("already selected", error)

    def test_selection_requires_exact_actionable_slot_and_unpaused_board(self):
        choice, error = validate_slot(state(seed(0)), 1)
        self.assertIsNone(choice)
        self.assertIn("not present", error)
        choice, error = validate_slot(state(seed(1), paused=True), 1)
        self.assertIsNone(choice)
        self.assertIn("paused", error)
        choice, error = validate_slot(state(seed(1)), 1)
        self.assertIsNone(error)
        self.assertEqual(choice.slot, 1)


if __name__ == "__main__":
    unittest.main()
