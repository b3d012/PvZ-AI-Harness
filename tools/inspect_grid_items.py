import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


PROCESS_NAME = "PlantsVsZombies.exe"
OFF = OFFSETS[PVZ_VERSION]

# Try the provisional stride first.
GRID_ITEM_STRUCT_SIZE = OFF["grid_item_struct_size"]


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
            grid_array = memory.read_pointer(
                board + OFF["grid_item"]
            )

            capacity = memory.read_uint(
                board + OFF["grid_item_count_max"]
            )

            print("\033[2J\033[H", end="")

            print(f"Board      : 0x{board:08X}")
            print(f"Grid array : 0x{grid_array:08X}")
            print(f"Capacity   : {capacity}")
            print(f"Stride     : 0x{GRID_ITEM_STRUCT_SIZE:X}")
            print()

            found = 0

            if (
                grid_array != 0
                and 0 < capacity < 1000
            ):
                for i in range(capacity):
                    addr = (
                        grid_array
                        + i * GRID_ITEM_STRUCT_SIZE
                    )

                    dead = memory.read_bool(
                        addr + OFF["grid_item_dead"]
                    )

                    type_id = memory.read_int(
                        addr + OFF["grid_item_type"]
                    )

                    row = memory.read_int(
                        addr + OFF["grid_item_row"]
                    )

                    col = memory.read_int(
                        addr + OFF["grid_item_col"]
                    )

                    # Loose sanity filtering while researching.
                    if not (0 <= row <= 5):
                        continue

                    if not (0 <= col <= 8):
                        continue

                    if not (0 <= type_id <= 50):
                        continue

                    print(
                        f"[{i:03}] "
                        f"addr=0x{addr:08X} "
                        f"type={type_id:2} "
                        f"row={row} "
                        f"col={col} "
                        f"dead={dead}"
                    )

                    found += 1

            if found == 0:
                print("No candidate grid items.")

            time.sleep(0.15)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()