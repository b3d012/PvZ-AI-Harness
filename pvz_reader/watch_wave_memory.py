import time

from pvz_reader.process import find_pvz_process
from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


# Candidate GOTY 1.2.0.1073 offsets.
# Derived from classic Board layout + known GOTY +0x18 shift.
WAVE_OFFSETS = {
    "wave_count": 0x557C,

    "current_wave": 0x5594,
    "refreshed_wave": 0x5598,

    "refresh_hp": 0x55AC,
    "current_wave_hp": 0x55B0,

    "next_wave_countdown": 0x55B4,
    "next_wave_countdown_initial": 0x55B8,

    "huge_wave_countdown": 0x55BC,
}


def main():
    process = find_pvz_process()

    if not process:
        print("PvZ is not running.")
        return

    memory = MemoryReader(process["name"])
    o = OFFSETS[PVZ_VERSION]

    lawn = memory.read_pointer(o["lawn"])

    if lawn == 0:
        print("LawnApp pointer is null.")
        return

    board = memory.read_pointer(
        lawn + o["board"]
    )

    if board == 0:
        print("No active board.")
        return

    print(f"Board: 0x{board:08X}")
    print("Watching candidate wave fields...")
    print("Ctrl+C to stop.")
    print()

    try:
        while True:
            values = {
                name: memory.read_int(board + offset)
                for name, offset in WAVE_OFFSETS.items()
            }

            print(
                "\r"
                f"waves={values['wave_count']:3} | "
                f"current={values['current_wave']:3} | "
                f"refreshed={values['refreshed_wave']:3} | "
                f"next={values['next_wave_countdown']:5} | "
                f"nextStart={values['next_wave_countdown_initial']:5} | "
                f"huge={values['huge_wave_countdown']:5} | "
                f"refreshHP={values['refresh_hp']:6} | "
                f"waveHP={values['current_wave_hp']:6}",
                end="",
                flush=True,
            )

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()