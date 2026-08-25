import psutil


PVZ_PROCESS_NAMES = {
    "plantsvszombies.exe",
    "popcapgame1.exe",
}


def find_pvz_process():
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (process.info["name"] or "").lower()

            if name in PVZ_PROCESS_NAMES:
                return process.info

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None


if __name__ == "__main__":
    pvz = find_pvz_process()

    if pvz:
        print("PvZ detected!")
        print(f"PID: {pvz['pid']}")
        print(f"Process: {pvz['name']}")
        print(f"Executable: {pvz['exe']}")
    else:
        print("PvZ not running.")