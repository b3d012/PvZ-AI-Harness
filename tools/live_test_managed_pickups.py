"""Bounded live validation of serialized managed pickup collection."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime import FocusMode, PvZRuntime, RuntimeConfig, TrainingEpisodeSupport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--yes", action="store_true", help="acknowledge normal mouse input")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("This command clicks observed pickups. Re-run with --yes.")
    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode.AUTO))
    runtime.attach()
    support = TrainingEpisodeSupport(runtime, auto_collect_pickups=True)
    deadline = time.monotonic() + max(0.0, args.seconds)
    try:
        while time.monotonic() < deadline:
            metrics = support.pickups.collect_once()
            print(json.dumps(metrics.to_dict(), sort_keys=True), flush=True)
            time.sleep(0.1)
        print("Final metrics:", json.dumps(support.pickups.metrics.to_dict(), sort_keys=True))
    finally:
        support.shutdown()
        runtime.close()


if __name__ == "__main__":
    main()
