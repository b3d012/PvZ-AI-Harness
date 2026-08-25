import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.placement import can_plant


PROCESS_NAME = "PlantsVsZombies.exe"


def main():
    memory = MemoryReader(PROCESS_NAME)
    reader = PvZGameStateReader(memory)

    state = reader.read()

    if state is None:
        print("No active level.")
        return

    print("Current sun:", state.sun)
    print()

    for seed in state.seeds:
        print(
            f"Seed slot {seed.slot}: "
            f"{seed.name}, "
            f"ready={seed.ready}, "
            f"affordable={seed.affordable}, "
            f"actionable={seed.actionable}"
        )

    print()
    print("Plants:")
    for plant in state.plants:
        print(
            f"{plant.name} -> row={plant.row}, col={plant.col}"
        )

    print()
    print("Grid items:")
    for item in state.grid_items:
        print(
            f"{item.name} -> row={item.row}, col={item.col}"
        )

    print()

    # CHANGE THESE VALUES MANUALLY FOR EACH TEST
    seed_slot = 0
    row = 3
    col = 1

    result = can_plant(
        state,
        seed_slot=seed_slot,
        row=row,
        col=col,
    )

    print(
        f"can_plant(seed={seed_slot}, row={row}, col={col})"
    )
    print("Valid :", result.valid)
    print("Reason:", result.reason)


if __name__ == "__main__":
    main()