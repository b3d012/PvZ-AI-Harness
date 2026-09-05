"""Read-only operator calibration for seed-bank and lawn geometry.

No clicks or keyboard input are sent.  The operator positions the cursor over
the requested visible control/lane/tile and confirms in this console.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.coordinates import seed_slot_to_client, tile_to_client
from pvz_controller.windows_input import WindowsInputBackend
from pvz_runtime import PvZRuntime


def cursor_client(backend, area):
    screen = backend.cursor_screen_position()
    return backend.screen_to_client(*screen, area)


def sample(prompt, backend):
    input(prompt + " Press Enter to record; no input is sent to PvZ. ")
    # The PvZ window can move while the operator is positioning the cursor.
    # Resolve the current client origin for every sample rather than applying
    # stale screen-to-client geometry.
    area = backend.get_client_area()
    if (area.width, area.height) != (800, 600):
        raise SystemExit("FAIL: client geometry changed during calibration")
    measured = cursor_client(backend, area)
    if not (0 <= measured[0] < area.width and 0 <= measured[1] < area.height):
        raise SystemExit("FAIL: measured cursor coordinate is outside the PvZ client")
    return measured


def measurement_record(*, measured, predicted, **fields):
    return {
        **fields,
        "measured_client": measured,
        "predicted_client": predicted,
        "delta": {"x": measured[0] - predicted[0], "y": measured[1] - predicted[1]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-bank", action="store_true")
    parser.add_argument("--rows", action="store_true")
    parser.add_argument("--columns", action="store_true")
    args = parser.parse_args()
    if not any((args.seed_bank, args.rows, args.columns)):
        raise SystemExit("select at least one of --seed-bank, --rows, or --columns")

    runtime = PvZRuntime()
    runtime.attach()
    backend = runtime.session.input_backend
    try:
        state = runtime.observe()
        area = backend.get_client_area()
        if state is None or (area.width, area.height) != (800, 600):
            raise SystemExit("FAIL: requires a supported observable 800x600 Board")
        report = {
            "client_area": {"width": area.width, "height": area.height},
            "level": state.adventure_level,
            "scene": state.scene,
            "seed_count": len(state.seeds),
            "seed_packets": [], "row_centers": [], "column_centers": [],
        }
        if args.seed_bank:
            for seed in state.seeds:
                measured = sample(
                    f"Move cursor to center of slot {seed.slot} ({seed.name}).",
                    backend,
                )
                report["seed_packets"].append(measurement_record(
                    slot=seed.slot, type_id=seed.type_id, name=seed.name,
                    measured=measured, predicted=seed_slot_to_client(
                        seed.slot, seed_count=len(state.seeds),
                    ),
                ))
        if args.rows:
            for row in range(5):
                measured = sample(f"Move cursor to visible lane {row} center at column 4.", backend)
                report["row_centers"].append(measurement_record(
                    row=row, measured=measured,
                    predicted=tile_to_client(row, 4, scene=state.scene),
                ))
        if args.columns:
            for col in (0, 4, 8):
                measured = sample(f"Move cursor to tile center row 2, column {col}.", backend)
                report["column_centers"].append(measurement_record(
                    col=col, measured=measured,
                    predicted=tile_to_client(2, col, scene=state.scene),
                ))
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
