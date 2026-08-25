import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.placement import (
    build_placement_mask,
    valid_placements_for_seed,
)


PROCESS_NAME = "PlantsVsZombies.exe"


def main():
    memory = MemoryReader(PROCESS_NAME)
    reader = PvZGameStateReader(memory)

    state = reader.read()

    if state is None:
        print("No active level.")
        return

    print(f"Scene: {state.scene}")
    print(f"Sun:   {state.sun}")
    print()

    for seed in state.seeds:
        print(
            f"[{seed.slot}] {seed.name:<20} "
            f"ready={seed.ready} "
            f"affordable={seed.affordable} "
            f"actionable={seed.actionable}"
        )

    print()

    # Change this to whichever packet you want to inspect.
    seed_slot = 0

    placements = valid_placements_for_seed(
        state,
        seed_slot,
    )

    print(f"Valid placements for seed slot {seed_slot}:")
    print(placements)
    print()

    mask = build_placement_mask(state)

    print("Board mask:")
    print("    " + " ".join(str(c) for c in range(9)))

    for row in range(6):
        cells = []

        for col in range(9):
            cells.append(
                "O" if mask[seed_slot][row][col] else "."
            )

        print(
            f"{row}:  "
            + " ".join(cells)
        )


if __name__ == "__main__":
    main()