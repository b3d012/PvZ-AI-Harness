"""Read-only trace of the supported client's RUNNING-to-Award win lifecycle."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.outcome import GameOutcome
from pvz_runtime import PvZRuntime


def evidence(runtime: PvZRuntime) -> dict:
    state = runtime.observe()
    outcome = runtime.outcome()
    return {
        "outcome": outcome.outcome.value,
        "board_address": outcome.board_address,
        "board_result": outcome.board_result,
        "game_scene": outcome.game_scene,
        "level_complete": outcome.level_complete,
        "state_available": state is not None,
        "paused": None if state is None else bool(state.paused),
        "level": None if state is None else int(state.adventure_level),
        "game_clock": None if state is None else int(state.game_clock),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--poll-seconds", type=float, default=0.04)
    args = parser.parse_args()
    if args.seconds <= 0 or not 0.02 <= args.poll_seconds <= 0.05:
        raise SystemExit("--seconds must be positive and --poll-seconds must be 0.02..0.05")

    runtime = PvZRuntime()
    runtime.attach()
    try:
        initial = evidence(runtime)
        if (initial["outcome"] != GameOutcome.RUNNING.value
                or initial["level"] != args.level):
            print(json.dumps({"status": "refused", "initial": initial}, indent=2, sort_keys=True))
            raise SystemExit("FAIL: expected running configured Adventure level")

        started = time.monotonic()
        first_won_at = None
        previous = None
        changes = []
        while time.monotonic() - started <= args.seconds:
            current = evidence(runtime)
            now = time.monotonic() - started
            if current["outcome"] == GameOutcome.WON.value and first_won_at is None:
                first_won_at = now
            if current != previous:
                changes.append({
                    "t_seconds": round(now, 4),
                    "t_from_first_won_seconds": None if first_won_at is None else round(now - first_won_at, 4),
                    "evidence": current,
                })
                previous = current
            time.sleep(args.poll_seconds)
        print(json.dumps({
            "status": "complete",
            "configured_level": args.level,
            "poll_seconds": args.poll_seconds,
            "duration_seconds": round(time.monotonic() - started, 4),
            "first_won_t_seconds": None if first_won_at is None else round(first_won_at, 4),
            "changes": changes,
        }, indent=2, sort_keys=True))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
