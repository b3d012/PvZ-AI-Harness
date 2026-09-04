"""Adopt a manually prepared level and inspect its frozen Environment v1 data."""

from __future__ import annotations

from pvz_env import EpisodeConfig, PvZEnvironment
from pvz_runtime import PvZRuntime


runtime = PvZRuntime()
environment = PvZEnvironment(runtime.reader_adapter(), runtime.controller_adapter())
try:
    result = environment.reset(EpisodeConfig(episode_id="manual-example"))
    print("observation shape:", result.initial.observation.shape)
    print("action-mask shape:", result.initial.action_mask.shape)
finally:
    runtime.close()
