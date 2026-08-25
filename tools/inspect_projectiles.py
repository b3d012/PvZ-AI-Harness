import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


PROCESS_NAME = "PlantsVsZombies.exe"
OFF = OFFSETS[PVZ_VERSION]


PROJECTILE_NAMES = {
    0: "Pea",
    1: "Snow Pea",
    2: "Cabbage",
    3: "Melon",
    4: "Puff",
    5: "Winter Melon",
    6: "Fireball",
    7: "Star",
    8: "Spike",
    9: "Basketball",
    10: "Kernel",
    11: "Cob",
    12: "Butter",
    13: "Zombie Pea",
}


def main():
    memory = MemoryReader(PROCESS_NAME)

    lawn = memory.read_pointer(OFF["lawn"])

    if lawn == 0:
        raise RuntimeError("LawnApp pointer is null.")

    board = memory.read_pointer(
        lawn + OFF["board"]
    )

    if board == 0:
        raise RuntimeError("Board pointer is null. Enter a level first.")

    while True:
        try:
            projectile_array = memory.read_pointer(
                board + OFF["projectile"]
            )

            capacity = memory.read_uint(
                board + OFF["projectile_count_max"]
            )

            print("\033[2J\033[H", end="")

            print(f"Board            : 0x{board:08X}")
            print(f"Projectile array : 0x{projectile_array:08X}")
            print(f"Capacity         : {capacity}")
            print()

            found = 0

            if (
                projectile_array != 0
                and 0 < capacity < 5000
            ):
                for i in range(capacity):
                    addr = (
                        projectile_array
                        + i * OFF["projectile_struct_size"]
                    )

                    type_id = memory.read_int(
                        addr + OFF["projectile_type"]
                    )

                    row = memory.read_int(
                        addr + OFF["projectile_row"]
                    )

                    if not (0 <= type_id <= 20):
                        continue

                    if not (0 <= row <= 5):
                        continue

                    x = memory.read_float(
                        addr + OFF["projectile_x"]
                    )

                    y = memory.read_float(
                        addr + OFF["projectile_y"]
                    )

                    can_collide = memory.read_bool(
                        addr + OFF["projectile_can_collide"]
                    )

                    object_id = memory.read_int(
                        addr + OFF["projectile_id"]
                    )

                    name = PROJECTILE_NAMES.get(
                        type_id,
                        f"TYPE_{type_id}"
                    )

                    print(
                        f"[{i:03}] "
                        f"{name:<14} "
                        f"type={type_id:2} "
                        f"row={row} "
                        f"x={x:7.1f} "
                        f"y={y:7.1f} "
                        f"collide={can_collide} "
                        f"id={object_id}"
                    )

                    found += 1

            if found == 0:
                print("No candidate projectiles.")

            time.sleep(0.05)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()