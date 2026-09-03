"""Launch the interactive PvZ runtime monitor (Windows, live process)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime.monitor import launch_monitor


if __name__ == "__main__":
    launch_monitor()
