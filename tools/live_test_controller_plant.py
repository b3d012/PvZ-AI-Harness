"""Explicit two-click live test for semantic Phase 2 plant placement."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import PvZController, plant_was_placed
from pvz_controller.coordinates import tile_to_client
from pvz_controller.windows_input import GameWindowUnavailable, WindowsInputBackend
from pvz_reader.placement import can_plant
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


def _first_legal_tile(state, seed_slot: int):
    for row in range(6):
        for col in range(9):
            if can_plant(state, seed_slot, row, col).valid:
                return row, col
    return None


def _choose_ordinary_placement(state):
    for seed in state.seeds:
        if (
            seed.name in SIMPLE_ORDINARY_PLANTS
            and seed.ready
            and seed.affordable
            and seed.actionable
        ):
            tile = _first_legal_tile(state, seed.slot)
            if tile is not None:
                return seed, tile
    return None


def _print_plant_stage(stage: str) -> None:
    messages = {
        "clicking_seed_packet": "Clicking seed packet...",
        "seed_click_issued": "Seed click issued.",
        "waiting_for_seed_selection": "Waiting for seed selection...",
        "moving_to_target_tile": "Moving to target tile...",
        "clicking_target_tile": "Clicking target tile...",
        "tile_click_issued": "Tile click issued.",
    }
    print(messages[stage])


def main():
    reader = PvZGameStateReader(MemoryReader(PROCESS_NAME))
    state = reader.read()

    if state is None:
        print("No active level. Enter an unpaused level and run this tool again.")
        return
    if state.paused:
        print("ABORTED: the game is paused; resume it and rerun. No clicks issued.")
        return

    print("Seed packets:")
    for seed in state.seeds:
        print(
            f"  slot={seed.slot:2} {seed.name:<16} ready={seed.ready} "
            f"affordable={seed.affordable} actionable={seed.actionable}"
        )

    choice = _choose_ordinary_placement(state)
    if choice is None:
        print(
            "ABORTED: no ready, affordable Peashooter or Sunflower has a legal "
            "empty tile. Adjust the level state and rerun. No clicks issued."
        )
        return

    chosen_seed, (row, col) = choice
    print(
        "\nAbout to plant:\n"
        f"Seed slot: {chosen_seed.slot}\n"
        f"Plant: {chosen_seed.name}\n"
        f"Target: row={row} col={col}"
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

    fresh_seed = next(
        (
            seed
            for seed in fresh_state.seeds
            if seed.slot == chosen_seed.slot
            and seed.type_id == chosen_seed.type_id
            and seed.name in SIMPLE_ORDINARY_PLANTS
            and seed.ready
            and seed.affordable
            and seed.actionable
        ),
        None,
    )
    if fresh_seed is None:
        print("ABORTED: selected seed became stale; no clicks issued. Rerun.")
        return

    placement = can_plant(fresh_state, fresh_seed.slot, row, col)
    if not placement.valid:
        print(
            f"ABORTED: target is no longer legal ({placement.reason}); "
            "no clicks issued. Rerun."
        )
        return

    target_logical = tile_to_client(row, col)
    try:
        target_screen = backend.logical_to_screen(
            *target_logical,
            backend.get_client_area(),
        )
    except GameWindowUnavailable as error:
        print(f"ABORTED: {error}; no clicks issued.")
        return
    print(
        "Target logical client coordinate: "
        f"x={target_logical[0]} y={target_logical[1]}"
    )
    print(f"Target final screen coordinate: x={target_screen[0]} y={target_screen[1]}")
    result = PvZController(backend).plant(
        fresh_state,
        fresh_seed.slot,
        row,
        col,
        stage_callback=_print_plant_stage,
    )
    print(f"ActionResult: {result}")
    if not result.attempted or result.success is False:
        print("Plant action was not fully issued.")
        return

    time.sleep(VERIFY_SETTLE_SECONDS)
    after_state = reader.read()
    verified = plant_was_placed(fresh_seed, row, col, after_state)
    print(f"Expected plant appeared at target tile: {verified}")


if __name__ == "__main__":
    main()
