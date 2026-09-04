"""Operator-assisted validation of fresh same-level reset postconditions."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime import CallbackRestartDriver, PvZRuntime, ResetExpectation, TrainingEpisodeSupport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, required=True)
    parser.add_argument("--seed-types", type=int, nargs="*")
    args = parser.parse_args()

    def operator_restart(_runtime):
        input("Use PvZ's normal Restart Level control now. Press Enter only after confirming it. ")
        return True

    runtime = PvZRuntime()
    runtime.attach()
    support = TrainingEpisodeSupport(runtime, restart_driver=CallbackRestartDriver(operator_restart))
    try:
        result = support.reset_current_level(ResetExpectation(
            args.level,
            None if args.seed_types is None else tuple(args.seed_types),
        ))
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        if not result.success:
            raise SystemExit("FAIL: reset postconditions were not verified")
        print("PASS: a distinct Board with the same level and fresh-state conditions was verified.")
    finally:
        support.shutdown()
        runtime.close()


if __name__ == "__main__":
    main()
