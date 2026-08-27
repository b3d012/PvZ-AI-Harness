"""Explicit one-click live test for the Phase 2 pickup controller."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import PvZController, pickup_was_collected
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader


PROCESS_NAME = "PlantsVsZombies.exe"
VERIFY_SETTLE_SECONDS = 0.15


def _available_pickups(state):
    return [
        pickup
        for pickup in state.pickups
        if pickup.collectible and not pickup.collected
    ]


def main():
    reader = PvZGameStateReader(MemoryReader(PROCESS_NAME))
    state = reader.read()

    if state is None:
        print("No active level. Enter a level and run this tool again.")
        return

    candidates = _available_pickups(state)
    if not candidates:
        print("No collectible pickup is currently visible. Let one appear and rerun.")
        return

    # Prefer sun for a harmless, easy-to-observe validation.
    chosen = min(candidates, key=lambda item: (not item.is_sun, item.slot))
    print("Available pickups:")
    for item in candidates:
        marker = " <- selected" if item.slot == chosen.slot else ""
        print(
            f"  slot={item.slot:3} {item.name:<12} "
            f"x={item.x:7.1f} y={item.y:7.1f}{marker}"
        )

    if state.paused:
        print("\nThe game is paused. Resume it before confirming this test.")

    input(
        "\nPress Enter to reread this pickup and issue exactly one click "
        "(Ctrl+C cancels): "
    )

    # Reread immediately before acting. If the selected pickup expired or its
    # array slot was reused, abort instead of clicking a stale coordinate.
    fresh_state = reader.read()
    if fresh_state is None:
        print("ABORTED: no active level after confirmation; no click issued.")
        return

    fresh_pickup = next(
        (
            item
            for item in fresh_state.pickups
            if item.slot == chosen.slot and item.type_id == chosen.type_id
        ),
        None,
    )
    if fresh_pickup is None:
        print("ABORTED: selected pickup became stale; no click issued. Rerun.")
        return

    controller = PvZController()
    result = controller.collect_pickup(fresh_state, fresh_pickup.slot)
    print(f"ActionResult: {result}")

    if not result.attempted:
        print("No click was issued.")
        return

    time.sleep(VERIFY_SETTLE_SECONDS)
    after_state = reader.read()
    verified = pickup_was_collected(fresh_pickup, after_state)
    print(f"Pickup disappeared or became collected: {verified}")


if __name__ == "__main__":
    main()
