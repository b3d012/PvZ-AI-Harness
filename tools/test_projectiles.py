"""Print projectiles from the integrated GameState reader."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader


PROCESS_NAME = "PlantsVsZombies.exe"


def main():
    reader = PvZGameStateReader(MemoryReader(PROCESS_NAME))
    state = reader.read()

    if state is None:
        print("No active level.")
        return

    if not state.projectiles:
        print("No projectiles.")
        return

    for projectile in state.projectiles:
        print(
            f"[{projectile.slot:03}] "
            f"{projectile.name:<14} "
            f"type={projectile.type_id:2} "
            f"row={projectile.row} "
            f"x={projectile.x:7.1f} "
            f"y={projectile.y:7.1f} "
            f"collide={projectile.can_collide} "
            f"id={projectile.object_id}"
        )


if __name__ == "__main__":
    main()
