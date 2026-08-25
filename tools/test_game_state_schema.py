"""No-process smoke test for the frozen GameState v1 observation schema."""

import sys
from dataclasses import fields
from pathlib import Path
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The schema test inspects dataclasses only.  Provide the type used by
# memory.py when the optional live-reader dependency is not installed.
if "pymem" not in sys.modules:
    pymem_stub = ModuleType("pymem")
    pymem_stub.Pymem = object
    sys.modules["pymem"] = pymem_stub

from pvz_reader.game_state import GAME_STATE_SCHEMA_VERSION, GameState


EXPECTED_GAME_STATE_FIELDS = [
    "sun",
    "game_clock",
    "scene",
    "adventure_level",
    "paused",
    "plant_capacity",
    "zombie_capacity",
    "wave",
    "plants",
    "zombies",
    "seeds",
    "mowers",
    "pickups",
    "projectiles",
    "grid_items",
]


class GameStateSchemaTests(unittest.TestCase):
    def test_schema_version(self):
        self.assertEqual(GAME_STATE_SCHEMA_VERSION, 1)

    def test_top_level_fields(self):
        self.assertEqual(
            [field.name for field in fields(GameState)],
            EXPECTED_GAME_STATE_FIELDS,
        )


if __name__ == "__main__":
    unittest.main()
