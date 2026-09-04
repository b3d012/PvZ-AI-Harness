"""Read-only command-line diagnostics for the managed PvZ runtime."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from pvz_runtime.models import FocusMode, RuntimeConfig
from pvz_runtime.runtime import PvZRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvz-runtime-test", description="Attach to PvZ and print one read-only runtime snapshot.")
    parser.add_argument("--focus-mode", choices=[mode.value for mode in FocusMode], default=FocusMode.MANUAL.value, help="Report the selected focus policy; this diagnostic never sends input.")
    parser.add_argument("--pretty", action="store_true", help="Indent JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode(args.focus_mode), observer_only=True))
    try:
        snapshot = runtime.snapshot(refresh=True)
        print(json.dumps(snapshot.to_dict(), indent=2 if args.pretty else None, sort_keys=True))
        return 0 if snapshot.health.can_observe else 1
    finally:
        runtime.close()


if __name__ == "__main__":  # pragma: no cover - console-script entry point
    raise SystemExit(main())
