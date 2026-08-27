"""Explicit two-click live test for semantic Phase 2 shoveling."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import PvZController, plant_was_removed
from pvz_controller.windows_input import GameWindowUnavailable, WindowsInputBackend
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader


PROCESS_NAME = "PlantsVsZombies.exe"
VERIFY_SETTLE_SECONDS = 0.25
FOREGROUND_TIMEOUT_SECONDS = 10.0
FOREGROUND_POLL_SECONDS = 0.075
SIMPLE_ORDINARY_PLANTS = {"Peashooter", "Sunflower"}


def _wait_for_pvz_foreground(backend: WindowsInputBackend) -> bool:
    """Poll the resolved PvZ HWND instead of assuming focus after a delay."""
    deadline = time.monotonic() + FOREGROUND_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if backend.is_foreground():
            return True
        time.sleep(FOREGROUND_POLL_SECONDS)
    return backend.is_foreground()


def _choose_simple_plant(state):
    for plant in state.plants:
        if plant.name not in SIMPLE_ORDINARY_PLANTS:
            continue
        plants_at_tile = [
            item
            for item in state.plants
            if item.row == plant.row and item.col == plant.col
        ]
        if len(plants_at_tile) == 1:
            return plant
    return None


def main():
    reader = PvZGameStateReader(MemoryReader(PROCESS_NAME))
    state = reader.read()

    if state is None:
        print("No active level. Enter an unpaused level and run this tool again.")
        return
    if state.paused:
        print("ABORTED: the game is paused; resume it and rerun. No clicks issued.")
        return

    chosen = _choose_simple_plant(state)
    if chosen is None:
        print(
            "ABORTED: no single Peashooter or Sunflower tile is available. "
            "Plant one on an otherwise empty tile and rerun. No clicks issued."
        )
        return

    print(
        "About to shovel:\n"
        f"Plant: {chosen.name}\n"
        f"Target: row={chosen.row} col={chosen.col}"
    )
    input("\nPress Enter to begin the manual-focus gate (Ctrl+C cancels): ")

    backend = WindowsInputBackend()
    print(
        "Manually click/focus the Plants vs. Zombies window now. "
        "Waiting up to 10 seconds for its real window to become foreground..."
    )
    try:
        is_foreground = _wait_for_pvz_foreground(backend)
    except GameWindowUnavailable as error:
        print(f"ABORTED: {error}; no clicks issued.")
        return

    if not is_foreground:
        print("ABORTED: PvZ was not foreground within 10 seconds; no clicks issued.")
        return

    fresh_state = reader.read()
    if fresh_state is None or fresh_state.paused:
        print("ABORTED: level is no longer active and unpaused; no clicks issued.")
        return

    fresh_plant = next(
        (
            plant
            for plant in fresh_state.plants
            if plant.slot == chosen.slot
            and plant.type_id == chosen.type_id
            and plant.row == chosen.row
            and plant.col == chosen.col
        ),
        None,
    )
    if fresh_plant is None:
        print("ABORTED: selected plant became stale; no clicks issued. Rerun.")
        return

    plants_at_tile = [
        plant
        for plant in fresh_state.plants
        if plant.row == fresh_plant.row and plant.col == fresh_plant.col
    ]
    if len(plants_at_tile) != 1:
        print("ABORTED: target tile is no longer unambiguous; no clicks issued. Rerun.")
        return

    result = PvZController(backend).shovel(
        fresh_state,
        fresh_plant.row,
        fresh_plant.col,
    )
    print(f"ActionResult: {result}")
    if not result.attempted or result.success is False:
        print("Shovel action was not fully issued.")
        return

    time.sleep(VERIFY_SETTLE_SECONDS)
    after_state = reader.read()
    verified = plant_was_removed(fresh_plant, after_state)
    print(f"Plant removed from target tile: {verified}")


if __name__ == "__main__":
    main()
