"""Presentation-model test for the live monitor without opening Tk."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import GameWindowInfo
from pvz_runtime import (
    EnvironmentHealth, FocusMode, GamePhase, GameStateSummary, ProcessIdentity,
    RuntimeSnapshot, SessionStatus,
)
from pvz_runtime.monitor import MonitorViewModel, RuntimeMonitor


class MonitorViewModelTests(unittest.TestCase):
    def test_snapshot_formats_all_operator_fields(self):
        session = SessionStatus(
            True, True, ProcessIdentity(42, "PlantsVsZombies.exe"),
            GameWindowInfo(100, 42, "Plants vs. Zombies", False, 800, 600),
            True, True, "1.2.0.1073", False, 1, None,
        )
        health = EnvironmentHealth(
            True, True, True, True, True, True, True, GamePhase.PLAYING,
            12.4, FocusMode.MANUAL, False, (),
        )
        state = GameStateSummary(1, 0, 100, False, 150, 2, 10, 4, 3, 6, 1, 5, 2)
        model = MonitorViewModel.from_snapshot(
            RuntimeSnapshot(123.0, session, health, GamePhase.PLAYING, state, "plant:ok", None)
        )
        text = RuntimeMonitor._format(model)
        for expected in (
            "Connected", "42", "Plants vs. Zombies", "PLAYING", "150", "4", "3",
            "1", "5", "12 ms", "plant:ok",
        ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
