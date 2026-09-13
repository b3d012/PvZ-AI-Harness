"""Trace one normal current-level reset without strategic gameplay actions."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import time
from typing import Any

from pvz_runtime import (
    FocusMode,
    NormalUiRestartDriver,
    PvZRuntime,
    ResetExpectation,
    RuntimeConfig,
    TrainingEpisodeSupport,
)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class Trace:
    def __init__(self, runtime: Any, *, interval: float) -> None:
        self.runtime = runtime
        self.interval = interval
        self.started = time.monotonic()
        self.last_emitted = -interval
        self.last_signature: tuple[Any, ...] | None = None
        self.events: list[dict[str, Any]] = []

    def snapshot(self, event: str) -> None:
        state = getattr(self, "state", None)
        outcome = getattr(self, "outcome", None)
        health = self.runtime.health
        phase = getattr(self.runtime.phase, "value", self.runtime.phase)
        board = getattr(outcome, "board_address", None)
        signature = (
            board,
            getattr(state, "adventure_level", None),
            getattr(state, "scene", None),
            getattr(state, "game_clock", None),
            phase,
            getattr(state, "paused", None),
            len(getattr(state, "plants", ()) or ()),
            len(getattr(state, "zombies", ()) or ()),
            getattr(outcome, "outcome", None),
        )
        now = time.monotonic() - self.started
        if event == "observe" and now - self.last_emitted < self.interval and signature == self.last_signature:
            return
        self.last_emitted = now
        self.last_signature = signature
        self.events.append({
            "event": event,
            "relative_seconds": round(now, 4),
            "board_address": board,
            "phase": phase,
            "paused": getattr(state, "paused", None),
            "level": getattr(state, "adventure_level", None),
            "scene": getattr(state, "scene", None),
            "game_clock": getattr(state, "game_clock", None),
            "wave": getattr(state, "wave", None),
            "total_waves": getattr(state, "total_waves", None),
            "outcome": _jsonable(getattr(outcome, "outcome", None)),
            "outcome_reason": getattr(outcome, "reason", None),
            "seed_type_ids": [getattr(seed, "type_id", None) for seed in (getattr(state, "seeds", ()) or ())],
            "plant_count": len(getattr(state, "plants", ()) or ()),
            "zombie_count": len(getattr(state, "zombies", ()) or ()),
            "plants": _jsonable(getattr(state, "plants", ()) or ()),
            "zombies": _jsonable(getattr(state, "zombies", ()) or ()),
            "health": _jsonable(health),
        })

    def observe(self) -> Any:
        self.state = self._observe()
        self.snapshot("observe")
        return self.state

    def outcome_read(self) -> Any:
        self.outcome = self._outcome()
        self.snapshot("outcome")
        return self.outcome


class TracingRestartDriver:
    def __init__(self, runtime: Any, trace: Trace) -> None:
        self.driver = NormalUiRestartDriver()
        self.runtime = runtime
        self.trace = trace

    def request_restart(self, runtime: Any) -> Any:
        self.trace.snapshot("restart_requested")
        result = self.driver.request_restart(runtime)
        self.trace.snapshot("restart_result")
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, default=7)
    parser.add_argument("--seed-types", type=int, nargs="*", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode.AUTO))
    runtime.attach()
    trace = Trace(runtime, interval=0.05)
    trace._observe = runtime.observe
    trace._outcome = runtime.outcome
    runtime.observe = trace.observe
    runtime.outcome = trace.outcome_read
    support = TrainingEpisodeSupport(
        runtime,
        restart_driver=TracingRestartDriver(runtime, trace),
        reset_timeout_seconds=args.timeout,
        reset_poll_interval_seconds=0.05,
    )
    try:
        trace.observe()
        trace.outcome_read()
        result = support.reset_current_level(ResetExpectation(args.level, tuple(args.seed_types)))
        trace.snapshot("reset_returned")
        payload = {
            "result": result.to_dict(),
            "events": trace.events,
            "gameplay_actions_sent": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")
        print(json.dumps(_jsonable(payload), indent=2))
        return 0 if result.success else 1
    finally:
        support.shutdown()
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
