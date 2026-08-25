import sys
import time
from pathlib import Path

import pymem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.versions import OFFSETS, PVZ_VERSION


PROCESS_NAME = "PlantsVsZombies.exe"

OFF = OFFSETS[PVZ_VERSION]

# Board / DataArray
PICKUP_ARRAY_OFFSET = 0xFC
PICKUP_COUNT_MAX_OFFSET = 0x100

# FloatingItem
PICKUP_STRUCT_SIZE = 0xD8

PICKUP_X = 0x24
PICKUP_Y = 0x28
PICKUP_COLLECTED = 0x50
PICKUP_TIMER = 0x54
PICKUP_TYPE = 0x58

TYPE_NAMES = {
    0: "NONE",
    1: "SILVER_COIN",
    2: "GOLD_COIN",
    3: "DIAMOND",
    4: "SUN",
    5: "SMALL_SUN",
    6: "LARGE_SUN",
}


def read_ptr(pm, address):
    return pm.read_int(address) & 0xFFFFFFFF


def main():
    pm = pymem.Pymem(PROCESS_NAME)

    lawn = read_ptr(pm, OFF["lawn"])
    board = read_ptr(pm, lawn + OFF["board"])

    if not board:
        raise RuntimeError("Board pointer is null. Enter a level first.")

    print(f"PID   : {pm.process_id}")
    print(f"Lawn  : 0x{lawn:08X}")
    print(f"Board : 0x{board:08X}")
    print()

    while True:
        try:
            array_ptr = read_ptr(pm, board + PICKUP_ARRAY_OFFSET)
            max_count = pm.read_int(board + PICKUP_COUNT_MAX_OFFSET)

            print("\033[2J\033[H", end="")

            print(f"Pickup array : 0x{array_ptr:08X}")
            print(f"Max count    : {max_count}")
            print()

            found = 0

            if array_ptr and 0 < max_count < 4096:
                for i in range(max_count):
                    addr = array_ptr + i * PICKUP_STRUCT_SIZE

                    pickup_type = pm.read_int(addr + PICKUP_TYPE)

                    if pickup_type <= 0 or pickup_type > 50:
                        continue

                    x = pm.read_float(addr + PICKUP_X)
                    y = pm.read_float(addr + PICKUP_Y)

                    collected = pm.read_uchar(addr + PICKUP_COLLECTED)
                    timer = pm.read_int(addr + PICKUP_TIMER)

                    name = TYPE_NAMES.get(
                        pickup_type,
                        f"TYPE_{pickup_type}"
                    )

                    print(
                        f"[{i:03}] "
                        f"addr=0x{addr:08X} "
                        f"type={pickup_type:2} {name:<14} "
                        f"x={x:7.2f} "
                        f"y={y:7.2f} "
                        f"collected={collected} "
                        f"timer={timer}"
                    )

                    found += 1

            if found == 0:
                print("No candidate pickups.")

            time.sleep(0.10)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()