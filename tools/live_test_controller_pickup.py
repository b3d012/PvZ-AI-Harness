"""Explicit one-click live test for the Phase 2 pickup controller."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import PvZController, pickup_was_collected
from pvz_controller.windows_input import GameWindowUnavailable, WindowsInputBackend
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader


PROCESS_NAME = "PlantsVsZombies.exe"
VERIFY_SETTLE_SECONDS = 0.15
FOREGROUND_TIMEOUT_SECONDS = 10.0
FOREGROUND_POLL_SECONDS = 0.075


def _available_pickups(state):
    return [
        pickup
        for pickup in state.pickups
        if pickup.collectible and not pickup.collected
    ]


def _wait_for_pvz_foreground(backend: WindowsInputBackend) -> bool:
    """Poll the real gameplay HWND rather than assuming focus after a delay."""
    deadline = time.monotonic() + FOREGROUND_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if backend.is_foreground():
            return True
        time.sleep(FOREGROUND_POLL_SECONDS)
    return backend.is_foreground()


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

    input("\nPress Enter to begin the manual-focus gate (Ctrl+C cancels): ")

    backend = WindowsInputBackend()
    print(
        "Manually click/focus the Plants vs. Zombies window now. "
        "Waiting up to 10 seconds for its real window to become foreground..."
    )
    try:
        is_foreground = _wait_for_pvz_foreground(backend)
    except GameWindowUnavailable as error:
        print(f"ABORTED: {error}; no click issued.")
        return

    if not is_foreground:
        print("ABORTED: PvZ was not foreground within 10 seconds; no click issued.")
        return

    # Reread only after manual foreground confirmation. If the selected pickup
    # expired, was collected, or its array slot was reused, do not click.
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
    if (
        fresh_pickup is None
        or fresh_pickup.collected
        or not fresh_pickup.collectible
    ):
        print("ABORTED: selected pickup became stale; no click issued. Rerun.")
        return

    controller = PvZController(backend)
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
