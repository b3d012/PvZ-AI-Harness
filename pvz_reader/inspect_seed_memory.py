import time

from pvz_reader.process import find_pvz_process
from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


SCAN_SIZE = 0x80


def snapshot(memory: MemoryReader, address: int) -> bytes:
    return memory.pm.read_bytes(address, SCAN_SIZE)


def print_diff(before: bytes, after: bytes):
    changes = []

    for offset, (old, new) in enumerate(zip(before, after)):
        if old != new:
            changes.append((offset, old, new))

    if not changes:
        print("No bytes changed.")
        return

    print()
    print("Changed bytes:")
    print("-" * 50)

    for offset, old, new in changes:
        print(
            f"+0x{offset:02X}: "
            f"0x{old:02X} ({old:3}) -> "
            f"0x{new:02X} ({new:3})"
        )


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

    slot_bank = memory.read_pointer(board + o["slot"])

    if slot_bank == 0:
        print("No seed bank.")
        return

    slot_count = memory.read_uint(
        slot_bank + o["slot_count"]
    )

    print(f"Seed slots: {slot_count}")

    slot_number = int(
        input(
            f"Choose seed slot to inspect (1-{slot_count}): "
        )
    )

    index = slot_number - 1

    if not 0 <= index < slot_count:
        print("Invalid slot.")
        return

    slot_addr = (
        slot_bank
        + index * o["slot_struct_size"]
    )

    print()
    print(f"Slot address: 0x{slot_addr:08X}")
    print(f"Scanning {SCAN_SIZE:#x} bytes")
    print()

    input(
        "Put the packet into the FIRST state, "
        "then press Enter..."
    )

    before = snapshot(memory, slot_addr)

    print()
    input(
        "Now perform the action/change "
        "(for example select + cancel), "
        "then press Enter..."
    )

    after = snapshot(memory, slot_addr)

    print_diff(before, after)


if __name__ == "__main__":
    main()