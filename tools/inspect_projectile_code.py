import pymem


PROCESS_NAME = "PlantsVsZombies.exe"

TARGETS = {
    "projectile_damage": 0x0047169B,
    "lob_motion": 0x00471E59,
}

BEFORE = 0x120
AFTER = 0x180


def dump_region(pm, name, target):
    start = target - BEFORE
    size = BEFORE + AFTER

    data = pm.read_bytes(start, size)

    filename = f"{name}_code_dump.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Target: 0x{target:08X}\n\n")

        for offset in range(0, len(data), 16):
            address = start + offset
            chunk = data[offset:offset + 16]

            hex_bytes = " ".join(
                f"{b:02X}" for b in chunk
            )

            marker = ""

            if address <= target < address + 16:
                marker = "  <--- TARGET"

            line = (
                f"{address:08X}: "
                f"{hex_bytes:<47}"
                f"{marker}"
            )

            print(line)
            f.write(line + "\n")

    print()
    print(f"Saved {filename}")
    print()


def main():
    pm = pymem.Pymem(PROCESS_NAME)

    print(f"PID: {pm.process_id}")
    print()

    for name, target in TARGETS.items():
        print("=" * 70)
        print(name)
        print(f"Target: 0x{target:08X}")
        print("=" * 70)

        dump_region(pm, name, target)


if __name__ == "__main__":
    main()