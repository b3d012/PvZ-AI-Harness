"""Operator-driven, read-only validation of natural terminal evidence."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime import GameOutcome, PvZRuntime


def wait_for(runtime, expected, instruction, timeout=900.0):
    input(f"\n{instruction}\nPress Enter when ready to begin observation. ")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runtime.observe()
        evidence = runtime.outcome()
        print(json.dumps(evidence.to_dict(), sort_keys=True), flush=True)
        if evidence.outcome is expected:
            print(f"CONFIRMED {expected.value.upper()}: {evidence.reason}")
            return
        time.sleep(0.25)
    raise SystemExit(f"Timed out waiting for {expected.value}; no validation recorded")


def main():
    runtime = PvZRuntime()
    runtime.attach()
    try:
        wait_for(runtime, GameOutcome.RUNNING, "Prepare the target level in active gameplay.")
        wait_for(runtime, GameOutcome.WON, "Now deliberately win this level; do not dismiss the result immediately.")
        wait_for(runtime, GameOutcome.RUNNING, "Restart/re-enter the same level and leave it actively running.")
        wait_for(runtime, GameOutcome.LOST, "Now deliberately lose; leave the Zombies Won/result screen visible.")
        print("PASS: RUNNING, WON, restarted RUNNING, and LOST were observed in order.")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
