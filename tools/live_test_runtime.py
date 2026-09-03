"""Explicit live validation for runtime attachment, focus, pause, and snapshots."""

import argparse
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_runtime import FocusMode, PvZRuntime, RuntimeConfig


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Safely inspect the PvZ runtime; input checks require explicit flags."
    )
    result.add_argument("--focus-mode", choices=("manual", "auto"), default="manual")
    result.add_argument("--exercise-focus", action="store_true", help="explicitly test focusing the PvZ window")
    result.add_argument("--exercise-pause", action="store_true", help="explicitly send verified pause/resume Escape input")
    result.add_argument("--snapshot", type=Path, help="write a JSON diagnostic snapshot")
    return result


def main() -> int:
    arguments = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("pymem").setLevel(logging.WARNING)
    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode(arguments.focus_mode)))
    try:
        status = runtime.attach()
        snapshot = runtime.refresh()
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
        if not status.attached:
            print("PvZ is not attached. Start the supported game and rerun.")
            return 2

        if arguments.exercise_focus:
            input("Press Enter to explicitly request focus for the verified PvZ window (Ctrl+C cancels): ")
            print(f"focus_result={runtime.focus_window()}")

        if arguments.exercise_pause:
            input("Prepare an active level, then press Enter to test idempotent pause/resume (Ctrl+C cancels): ")
            before_pause = runtime.observe()
            if before_pause is None:
                print("ABORTED: pause exercise requires an available Board. No Escape input issued.")
                return 3
            initially_paused = bool(before_pause.paused)
            try:
                if initially_paused:
                    print(f"resume={runtime.resume()}")
                    print(f"resume_again={runtime.resume()}")
                    print(f"pause={runtime.pause()}")
                    print(f"pause_again={runtime.pause()}")
                else:
                    print(f"pause={runtime.pause()}")
                    print(f"pause_again={runtime.pause()}")
                    print(f"resume={runtime.resume()}")
                    print(f"resume_again={runtime.resume()}")
            finally:
                restored = runtime.set_paused(initially_paused)
                print(f"initial_pause_state_restore={restored}")

        final_snapshot = runtime.snapshot()
        if arguments.snapshot:
            arguments.snapshot.parent.mkdir(parents=True, exist_ok=True)
            arguments.snapshot.write_text(
                json.dumps(final_snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
            )
            print(f"snapshot_written={arguments.snapshot}")
        return 0
    except KeyboardInterrupt:
        print("Cancelled; no further input will be sent.")
        return 130
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
