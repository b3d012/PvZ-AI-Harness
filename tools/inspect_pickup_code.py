import pymem


PROCESS_NAME = "PlantsVsZombies.exe"

AUTO_COLLECT_ADDR = 0x004342F2

BEFORE = 0x100
AFTER = 0x180


def main():
    pm = pymem.Pymem(PROCESS_NAME)

    start = AUTO_COLLECT_ADDR - BEFORE
    size = BEFORE + AFTER

    data = pm.read_bytes(start, size)

    print(f"Process PID: {pm.process_id}")
    print(f"Dump start : 0x{start:08X}")
    print(f"Target     : 0x{AUTO_COLLECT_ADDR:08X}")
    print(f"Dump size  : {size} bytes")
    print()

    with open("pickup_code_dump.txt", "w", encoding="utf-8") as f:
        for offset in range(0, len(data), 16):
            address = start + offset
            chunk = data[offset:offset + 16]

            hex_bytes = " ".join(f"{b:02X}" for b in chunk)

            marker = "  <--- AUTO_COLLECT" if (
                address <= AUTO_COLLECT_ADDR < address + 16
            ) else ""

            line = f"{address:08X}: {hex_bytes:<47}{marker}"

            print(line)
            f.write(line + "\n")

    print()
    print("Saved to pickup_code_dump.txt")


if __name__ == "__main__":
    main()