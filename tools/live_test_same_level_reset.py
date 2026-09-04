"""Operator-assisted validation of fresh same-level reset postconditions."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime import (
    CallbackRestartDriver, FocusMode, NormalUiRestartDriver, PvZRuntime, ResetExpectation,
    RuntimeConfig,
    TrainingEpisodeSupport,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, required=True)
    parser.add_argument("--seed-types", type=int, nargs="*")
    parser.add_argument("--automatic", action="store_true",
                        help="Use the validated normal UI restart path (sends input).")
    parser.add_argument("--known-pause-menu", action="store_true",
                        help="Attest that PvZ's normal Menu is visibly open; only valid with --automatic.")
    parser.add_argument("--yes", action="store_true",
                        help="Required with --automatic to authorize live input.")
    args = parser.parse_args()

    if args.automatic and not args.yes:
        raise SystemExit("--automatic requires --yes because it sends normal PvZ input")
    if args.known_pause_menu and not args.automatic:
        raise SystemExit("--known-pause-menu requires --automatic")

    def operator_restart(_runtime):
        input("Use PvZ's normal Restart Level control now. Press Enter only after confirming it. ")
        return True

    runtime = PvZRuntime(config=RuntimeConfig(
        focus_mode=FocusMode.AUTO if args.automatic else FocusMode.MANUAL,
    ))
    runtime.attach()
    driver = (NormalUiRestartDriver(known_pause_menu=args.known_pause_menu)
              if args.automatic else CallbackRestartDriver(operator_restart))
    support = TrainingEpisodeSupport(runtime, restart_driver=driver)
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
