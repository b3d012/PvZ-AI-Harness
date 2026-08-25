import os
import time

from pvz_reader.process import find_pvz_process
from pvz_reader.memory import MemoryReader
from pvz_reader.game_state import PvZGameStateReader


def clear():
    os.system("cls")


def main():
    process = find_pvz_process()

    if not process:
        print("PvZ is not running.")
        return

    memory = MemoryReader(process["name"])
    game = PvZGameStateReader(memory)

    print(f"Attached to {process['name']} PID={process['pid']}")
    print("Starting live state inspection...")
    time.sleep(1)

    try:
        while True:
            state = game.read()

            clear()

            if state is None:
                print("No active board.")
                time.sleep(0.5)
                continue

            print("=" * 75)
            print("PVZ GOTY LIVE MEMORY STATE")
            print("=" * 75)

            print(
                f"Sun: {state.sun}   "
                f"Clock: {state.game_clock}   "
                f"Scene: {state.scene}   "
                f"Level: {state.adventure_level}   "
                f"Paused: {state.paused}"
            )

            print()
            print(
                f"Plant capacity: {state.plant_capacity}   "
                f"Active plants: {len(state.plants)}"
            )

            print("-" * 75)

            for p in state.plants:
                print(
                    f"P[{p.slot:02}] "
                    f"{p.name:<18} "
                    f"R{p.row + 1} C{p.col + 1} "
                    f"XY=({p.x:4},{p.y:4}) "
                    f"HP={p.hp}/{p.max_hp} "
                    f"state={p.state:<4} "
                    f"asleep={p.asleep}"
                )

            print()
            print(
                f"Zombie capacity: {state.zombie_capacity}   "
                f"Active zombies: {len(state.zombies)}"
            )

            print("-" * 75)

            for z in state.zombies:
                print(
                    f"Z[{z.slot:02}] "
                    f"{z.name:<22} "
                    f"R{z.row + 1} "
                    f"XY=({z.x:7.1f},{z.y:7.1f}) "
                    f"Body={z.body_hp}/{z.body_max_hp} "
                    f"Armor={z.armor_hp}/{z.armor_max_hp} "
                    f"state={z.state:<4} "
                    f"bite={z.biting}"
                )

            print()
            print(f"Seed packets: {len(state.seeds)}")
            print("-" * 75)

            for seed in state.seeds:

                if seed.selected:
                    status = "SELECTED"
                elif seed.actionable:
                    status = "READY"
                elif seed.cooling_down:
                    status = "COOLDOWN"
                elif seed.ready and not seed.affordable:
                    status = "NO SUN"
                else:
                    status = "UNKNOWN"

                print(
                    f"S[{seed.slot + 1:02}] "
                    f"{seed.name:<24} "
                    f"Cost={seed.cost:<3} "
                    f"CD={seed.cooldown_elapsed:4}/"
                    f"{seed.cooldown_total:<4} "
                    f"({seed.cooldown_ratio * 100:6.1f}%) "
                    f"{status:<8}"
                )

            print()
            print("Ctrl+C to stop")

            time.sleep(0.10)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()