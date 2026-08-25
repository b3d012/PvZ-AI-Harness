import time

from pvz_reader.process import find_pvz_process
from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


def main():
    process = find_pvz_process()

    if not process:
        print("PvZ is not running.")
        return

    print("PvZ detected")
    print(f"PID: {process['pid']}")
    print(f"Process: {process['name']}")
    print(f"Executable: {process['exe']}")
    print(f"Expected version: {PVZ_VERSION}")

    reader = MemoryReader(process["name"])
    offsets = OFFSETS[PVZ_VERSION]

    print()
    print("MemoryReader attached successfully.")

    try:
        lawn_ptr = reader.read_pointer(offsets["lawn"])

        print(f"LawnApp pointer: 0x{lawn_ptr:08X}")

        board_ptr = reader.read_pointer(
            lawn_ptr + offsets["board"]
        )

        print(f"Board pointer:   0x{board_ptr:08X}")

        if lawn_ptr == 0:
            print("LawnApp pointer is NULL.")
            return

        if board_ptr == 0:
            print()
            print("Board pointer is NULL.")
            print("Enter an actual level first, then run this again.")
            return

        print()
        print("Reading live PvZ state...")
        print("Press Ctrl+C to stop.")
        print()

        while True:
            sun = reader.read_int(
                board_ptr + offsets["sun"]
            )

            game_clock = reader.read_int(
                board_ptr + offsets["game_clock"]
            )

            print(
                f"\rSun: {sun:<5} | "
                f"Game clock: {game_clock:<10}",
                end="",
                flush=True,
            )

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped.")

    except Exception as exc:
        print()
        print(f"Memory read failed: {exc}")


if __name__ == "__main__":
    main()