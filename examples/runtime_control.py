"""Explicit, opt-in pause/resume example; default execution is read-only."""

from __future__ import annotations

import argparse
import json

from pvz_runtime import FocusMode, PvZRuntime, RuntimeConfig


parser = argparse.ArgumentParser()
action = parser.add_mutually_exclusive_group()
action.add_argument("--pause", action="store_true", help="Request one pause transition.")
action.add_argument("--resume", action="store_true", help="Request one resume transition.")
parser.add_argument("--focus-mode", choices=("manual", "auto"), default="manual")
args = parser.parse_args()

runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode(args.focus_mode)))
try:
    if args.pause:
        print(runtime.pause())
    elif args.resume:
        print(runtime.resume())
    print(json.dumps(runtime.snapshot().to_dict(), indent=2, sort_keys=True))
finally:
    runtime.close()
