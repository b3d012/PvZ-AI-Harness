"""Choose a legal Action v1 index without executing a desktop action."""

from __future__ import annotations

from pvz_env import EpisodeConfig, PvZEnvironment, RandomValidActionPolicy
from pvz_runtime import PvZRuntime


runtime = PvZRuntime()
environment = PvZEnvironment(runtime.reader_adapter(), runtime.controller_adapter())
try:
    reset = environment.reset(EpisodeConfig(episode_id="policy-example"))
    policy = RandomValidActionPolicy(seed=7)
    decision = policy.choose(reset.initial.observation, reset.initial.action_mask)
    print(f"selected Action v1 index: {decision.action_index}; legal={decision.legal}")
    print("No action was executed. Call environment.step(index) only in an explicit live workflow.")
finally:
    runtime.close()
