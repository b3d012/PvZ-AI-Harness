import time

from pvz_reader.process import find_pvz_process
from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


WATCH_OFFSETS = [
    0x4C,
    0x50,
    0x54,
    0x58,
    0x5C,
    0x60,
    0x64,
    0x68,
    0x6C,
    0x70,
    0x71,
    0x72,
    0x73,
    0x74,
    0x75,
    0x76,
    0x77,
]


def read_i32(memory, addr):
    return memory.read_int(addr)


def read_u8(memory, addr):
    return memory.read_byte(addr)


def main():
    process = find_pvz_process()

    if not process:
        print("PvZ is not running.")
        return

    memory = MemoryReader(process["name"])
    o = OFFSETS[PVZ_VERSION]

    lawn = memory.read_pointer(o["lawn"])
    board = memory.read_pointer(lawn + o["board"])

    if board == 0:
        print("No active board.")
        return

    slot_bank = memory.read_pointer(
        board + o["slot"]
    )

    slot_count = memory.read_uint(
        slot_bank + o["slot_count"]
    )

    print(f"Seed slots: {slot_count}")

    slot_number = int(
        input(f"Choose slot (1-{slot_count}): ")
    )

    index = slot_number - 1

    if not 0 <= index < slot_count:
        print("Invalid slot.")
        return

    addr = (
        slot_bank
        + index * o["slot_struct_size"]
    )

    print(f"Watching slot at 0x{addr:08X}")
    print("Ctrl+C to stop.")
    print()

    try:
        while True:
            cd_elapsed = read_i32(
                memory,
                addr + 0x4C
            )

            cd_total = read_i32(
                memory,
                addr + 0x50
            )

            seed_type = read_i32(
                memory,
                addr + 0x5C
            )

            im_type = read_i32(
                memory,
                addr + 0x60
            )

            b70 = read_u8(memory, addr + 0x70)
            b71 = read_u8(memory, addr + 0x71)
            b72 = read_u8(memory, addr + 0x72)
            b73 = read_u8(memory, addr + 0x73)
            b74 = read_u8(memory, addr + 0x74)
            b75 = read_u8(memory, addr + 0x75)

            print(
                "\r"
                f"CD={cd_elapsed:4}/{cd_total:<4} "
                f"type={seed_type:<3} "
                f"im={im_type:<3} | "
                f"70={b70:<3} "
                f"71={b71:<3} "
                f"72={b72:<3} "
                f"73={b73:<3} "
                f"74={b74:<3} "
                f"75={b75:<3}",
                end="",
                flush=True,
            )

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()