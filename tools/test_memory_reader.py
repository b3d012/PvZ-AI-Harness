"""Backward-compatible PID/name ownership checks for MemoryReader."""

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader


class FakePymem:
    def __init__(self, process):
        self.process = process
        self.process_id = 42
        self.process_handle = 100
        self.closed = False

    def close_process(self):
        self.closed = True


class MemoryReaderOwnershipTests(unittest.TestCase):
    def test_name_and_pid_attachment_are_backward_compatible(self):
        with patch("pvz_reader.memory.pymem.Pymem", FakePymem):
            named = MemoryReader("PlantsVsZombies.exe")
            pid_bound = MemoryReader(42)
        self.assertEqual(named.pm.process, "PlantsVsZombies.exe")
        self.assertEqual(pid_bound.pm.process, 42)
        self.assertEqual(pid_bound.process_id, 42)
        pid_bound.close()
        self.assertTrue(pid_bound.pm.closed)


if __name__ == "__main__":
    unittest.main()
