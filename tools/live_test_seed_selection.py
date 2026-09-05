"""Validate one live seed-bank slot without planting or automatic cancellation.

The supported reader exposes ``SeedPacketState.selected``.  This tool sends
exactly one settled packet click, verifies that the requested packet alone is
selected, and then stops.  Before another invocation, the operator must
manually cancel the selection and verify that no packet remains selected.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.coordinates import seed_slot_to_client
from pvz_controller.windows_input import ControllerInputError, WindowsInputBackend
from pvz_runtime import PvZRuntime


SETTLE_SECONDS = 0.10


def selected_slots(state):
    return [seed.slot for seed in state.seeds if seed.selected]


def validate_slot(state, slot):
    seed = next((item for item in state.seeds if item.slot == slot), None)
    if seed is None:
        return None, f"ABORTED: seed slot {slot} is not present. No clicks issued."
    if state.paused:
        return None, "ABORTED: game is paused. No clicks issued."
    if selected_slots(state):
        return None, "ABORTED: a seed is already selected; cancel it manually first. No clicks issued."
    if not (seed.ready and seed.affordable and seed.actionable):
        return None, f"ABORTED: slot {slot} ({seed.name}) is not actionable. No clicks issued."
    return seed, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--yes", action="store_true", help="Authorize the one packet click.")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("--yes is required because this tool sends one PvZ click")

    runtime = PvZRuntime()
    runtime.attach()
    try:
        state = runtime.observe()
        if state is None:
            raise SystemExit("ABORTED: no observable Board. No clicks issued.")
        seed, error = validate_slot(state, args.slot)
        if error:
            raise SystemExit(error)
        point = seed_slot_to_client(seed.slot, seed_count=len(state.seeds))
        backend: WindowsInputBackend = runtime.session.input_backend
        area = backend.get_client_area()
        if (area.width, area.height) != (800, 600):
            raise SystemExit("ABORTED: unsupported client geometry. No clicks issued.")
        print(f"Selecting slot {seed.slot}: {seed.name}; logical point={point}")
        backend.left_click(*point, move_settle_delay=SETTLE_SECONDS)
        time.sleep(SETTLE_SECONDS)
        after = runtime.observe()
        selected = [] if after is None else selected_slots(after)
        passed = selected == [seed.slot]
        print(f"selected_slots={selected}; expected=[{seed.slot}]; {'PASS' if passed else 'FAIL'}")
        if not passed:
            raise SystemExit("FAIL: selected packet does not match requested slot")
        print("No plant was placed. Manually cancel this selection before the next invocation.")
    except ControllerInputError as error:
        raise SystemExit(f"ABORTED: input failed: {error}") from error
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
