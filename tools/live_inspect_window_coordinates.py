"""Read-only Win32 coordinate evidence for the supported PvZ client."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import WindowsInputBackend


# These are PvZ logical render coordinates, not physical screen coordinates.
KNOWN_UI_POINTS = {"menu_candidate": (739, 13), "restart_candidate": (400, 358)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrate-menu", action="store_true",
                        help="Prompt for a read-only cursor sample over Menu.")
    args = parser.parse_args()

    backend = WindowsInputBackend(auto_focus=False)
    report = backend.coordinate_report()
    area = report.client_area
    mapped = {
        name: {
            "logical": point,
            "screen": backend.logical_to_screen(*point, area),
        }
        for name, point in KNOWN_UI_POINTS.items()
    }
    payload = asdict(report)
    payload["mapped_known_ui_points"] = mapped
    payload["cursor_screen"] = backend.cursor_screen_position()
    payload["cursor_client"] = backend.screen_to_client(*payload["cursor_screen"], area)
    if args.calibrate_menu:
        input("Move the cursor over PvZ's visible Menu control, then press Enter. No click is sent. ")
        cursor = backend.cursor_screen_position()
        payload["operator_menu_cursor_screen"] = cursor
        payload["operator_menu_cursor_client"] = backend.screen_to_client(*cursor, area)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
