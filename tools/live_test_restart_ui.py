"""Bounded live probe for the in-game Menu control; never requests restart."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.outcome import GameOutcome
from pvz_runtime import FocusMode, PvZRuntime, RuntimeConfig
from pvz_runtime.training import NormalUiRestartDriver


def snapshot(runtime: PvZRuntime) -> dict:
    state = runtime.observe()
    outcome = runtime.outcome()
    return {
        "state_available": state is not None,
        "paused": None if state is None else bool(state.paused),
        "level": None if state is None else int(state.adventure_level),
        "outcome": outcome.to_dict(),
        "health": runtime.health.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--probe-menu", action="store_true")
    modes.add_argument("--probe-restart", action="store_true")
    parser.add_argument("--level", type=int, default=7)
    parser.add_argument("--yes", action="store_true",
                        help="Required because exactly one Menu click is sent.")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("--probe-menu requires --yes because it sends one live Menu click")

    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode.AUTO))
    runtime.attach()
    try:
        before = snapshot(runtime)
        state = runtime.observe()
        outcome = runtime.outcome()
        if (state is None or int(state.adventure_level) != args.level
                or outcome.outcome is not GameOutcome.RUNNING
                or (args.probe_menu and bool(state.paused))
                or (args.probe_restart and not bool(state.paused))):
            print(json.dumps({"status": "refused", "before": before}, indent=2, sort_keys=True))
            raise SystemExit("FAIL: expected unpaused running configured level")
        driver = NormalUiRestartDriver()
        if not driver._validate_client(runtime):
            raise SystemExit("FAIL: unsupported client geometry")
        if args.probe_restart:
            # A restart probe must begin with an already visible normal menu;
            # do not guess that any paused state represents that dialog.
            if not bool(state.paused):
                raise SystemExit("FAIL: --probe-restart requires an already open PvZ Menu")
            point = driver.RESTART_LEVEL_BUTTON
        else:
            point = driver.MENU_BUTTON
        runtime.session.input_backend.left_click(
            *point, move_settle_delay=driver.UI_CONTROL_MOVE_SETTLE_DELAY,
        )
        deadline = time.monotonic() + driver.transition_timeout_seconds
        after = snapshot(runtime)
        while time.monotonic() < deadline:
            # A modal may make GameState temporarily unreadable; preserve raw
            # outcome evidence rather than treating that as a restart signal.
            if after["state_available"] and after["paused"]:
                break
            time.sleep(driver.poll_interval_seconds)
            after = snapshot(runtime)
        print(json.dumps({
            "status": (
                "menu_open_verified" if args.probe_menu and after["state_available"] and after["paused"]
                else "restart_control_transition_observed" if args.probe_restart
                else "menu_open_unverified"
            ),
            "input": {"logical": point, "move_settle_delay": driver.UI_CONTROL_MOVE_SETTLE_DELAY},
            "before": before,
            "after": after,
            "restart_click_sent": bool(args.probe_restart),
            "confirmation_sent": False,
        }, indent=2, sort_keys=True))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
