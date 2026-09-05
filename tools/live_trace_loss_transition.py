"""Read-only trace from authoritative LOST evidence; sends no retry input."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.outcome import GameOutcome
from pvz_runtime import PvZRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    args = parser.parse_args()
    runtime = PvZRuntime()
    runtime.attach()
    try:
        start = time.monotonic()
        records = []
        first_lost = None
        previous = None
        while time.monotonic() - start <= args.seconds:
            state = runtime.observe()
            outcome = runtime.outcome()
            current = {
                "outcome": outcome.outcome.value, "reason": outcome.reason,
                "board_address": outcome.board_address, "game_scene": outcome.game_scene,
                "board_result": outcome.board_result,
                "loss_cutscene_time": outcome.loss_cutscene_time,
                "loss_screen_ready": outcome.loss_screen_ready,
                "paused": None if state is None else bool(state.paused),
                "game_clock": None if state is None else int(state.game_clock),
            }
            now = time.monotonic() - start
            if outcome.outcome is GameOutcome.LOST and first_lost is None:
                first_lost = now
            if current != previous:
                records.append({"t_seconds": round(now, 4), "evidence": current})
                previous = current
            time.sleep(args.poll_seconds)
        print(json.dumps({"first_lost_t_seconds": first_lost, "changes": records}, indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
