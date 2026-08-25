import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader
from pvz_reader.game_state import PvZGameStateReader


def main():
    memory = MemoryReader("PlantsVsZombies.exe")
    reader = PvZGameStateReader(memory)

    while True:
        state = reader.read()

        if state is None:
            print("No active board.")
            time.sleep(1)
            continue

        print("\033[2J\033[H", end="")

        print(f"Sun bank: {state.sun}")
        print(f"Pickups : {len(state.pickups)}")
        print()

        for pickup in state.pickups:
            print(
                f"[{pickup.slot:03}] "
                f"{pickup.name:<16} "
                f"x={pickup.x:7.1f} "
                f"y={pickup.y:7.1f} "
                f"collected={pickup.collected} "
                f"is_sun={pickup.is_sun} "
                f"timer={pickup.timer}"
            )

        time.sleep(0.1)


if __name__ == "__main__":
    main()