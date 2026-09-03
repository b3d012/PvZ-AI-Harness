"""Explicit live validation for runtime attachment, focus, pause, and snapshots."""

import argparse
import json
import logging
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import ControllerInputError
from pvz_runtime import FocusMode, PauseStatus, PvZRuntime, RuntimeConfig


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Safely inspect the PvZ runtime; input checks require explicit flags."
    )
    result.add_argument("--focus-mode", choices=("manual", "auto"), default="manual")
    result.add_argument("--exercise-focus", action="store_true", help="explicitly test focusing the PvZ window")
    result.add_argument(
        "--exercise-escape", action="store_true",
        help="send two individually verified backend Escape presses from a manually PLAYING level",
    )
    result.add_argument(
        "--exercise-pause", action="store_true",
        help="exercise runtime pause/resume idempotence from a manually PLAYING level",
    )
    result.add_argument("--snapshot", type=Path, help="write a JSON diagnostic snapshot")
    return result


def print_window_diagnostics(runtime: PvZRuntime) -> None:
    status = runtime.session.status()
    expected = None if status.window is None else status.window.hwnd
    print(f"expected_pvz_hwnd={expected}")
    print(f"foreground_hwnd={status.foreground_hwnd}")
    print(f"foreground_matches={expected is not None and expected == status.foreground_hwnd}")


def wait_for_paused(runtime: PvZRuntime, desired: bool) -> bool:
    deadline = time.monotonic() + runtime.config.pause_timeout_seconds
    while True:
        state = runtime.observe()
        if state is not None and bool(state.paused) is desired:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(runtime.config.pause_poll_interval_seconds)


def exercise_direct_escape(runtime: PvZRuntime) -> bool:
    input(
        "TEST C: Manually leave the level PLAYING, then press Enter. "
        "The tool will focus PvZ and send two separately verified Escape presses: "
    )
    state = runtime.observe()
    if state is None or bool(state.paused):
        print("ABORTED: expected an available PLAYING Board. No Escape input issued.")
        return False
    if not runtime.focus_window():
        print("ABORTED: exact PvZ foreground HWND was not confirmed. No Escape input issued.")
        print_window_diagnostics(runtime)
        return False
    try:
        runtime.session.input_backend.press_escape()
    except ControllerInputError as error:
        print(f"escape_press_1_sent=False detail={error}")
        return False
    print("escape_press_1_sent=True")
    if not wait_for_paused(runtime, True):
        print("escape_press_1_verified=False expected_paused=True; second Escape NOT sent")
        return False
    print("escape_press_1_verified=True paused=True")
    try:
        runtime.session.input_backend.press_escape()
    except ControllerInputError as error:
        print(f"escape_press_2_sent=False detail={error}")
        return False
    print("escape_press_2_sent=True")
    if not wait_for_paused(runtime, False):
        print("escape_press_2_verified=False expected_paused=False")
        return False
    print("escape_press_2_verified=True paused=False")
    return True


def exercise_runtime_idempotence(runtime: PvZRuntime) -> bool:
    input(
        "TEST D: Manually leave the level PLAYING, then press Enter to run "
        "pause/pause/resume/resume through PvZRuntime: "
    )
    state = runtime.observe()
    if state is None or bool(state.paused):
        print("ABORTED: expected an available PLAYING Board. No Escape input issued.")
        return False
    steps = (
        ("pause", runtime.pause, PauseStatus.CHANGED),
        ("pause_again", runtime.pause, PauseStatus.ALREADY_SET),
        ("resume", runtime.resume, PauseStatus.CHANGED),
        ("resume_again", runtime.resume, PauseStatus.ALREADY_SET),
    )
    for name, operation, expected in steps:
        result = operation()
        print(f"{name}={result.status.value} detail={result.reason} observed={result.observed_paused}")
        if result.status is not expected:
            print(f"runtime_idempotence_verified=False stopped_after={name}")
            return False
    print("runtime_idempotence_verified=True")
    return True


def main() -> int:
    arguments = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("pymem").setLevel(logging.WARNING)
    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode(arguments.focus_mode)))
    try:
        status = runtime.attach()
        snapshot = runtime.refresh()
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
        print_window_diagnostics(runtime)
        if not status.attached:
            print("PvZ is not attached. Start the supported game and rerun.")
            return 2

        if arguments.exercise_focus:
            input("Press Enter to explicitly request focus for the verified PvZ window (Ctrl+C cancels): ")
            print(f"focus_result={runtime.focus_window()}")
            print_window_diagnostics(runtime)

        if arguments.exercise_escape and not exercise_direct_escape(runtime):
            return 4

        if arguments.exercise_pause:
            if not exercise_runtime_idempotence(runtime):
                return 5

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
