"""No-process smoke test for the frozen Controller v1 public API."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import CONTROLLER_VERSION, PvZController


class ControllerSchemaTests(unittest.TestCase):
    def test_controller_version(self):
        self.assertEqual(CONTROLLER_VERSION, 1)

    def test_public_semantic_actions_exist(self):
        for method in ("collect_pickup", "plant", "shovel"):
            with self.subTest(method=method):
                self.assertTrue(callable(getattr(PvZController, method, None)))


if __name__ == "__main__":
    unittest.main()
