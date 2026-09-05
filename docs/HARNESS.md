# PvZ AI Harness integration guide

`pvz-ai-harness` v0.2.0 is the frozen, Windows-focused bridge between a locally
installed PvZ GOTY client and future strategic-learning code. It is not a
game distribution, game launcher, or training framework.

## Install

```powershell
git clone --recurse-submodules https://github.com/b3d012/PvZ-DeepLearning.git
cd PvZ-DeepLearning
python -m pip install -e .
```

The supported Python version is 3.12 or newer. Live interaction requires the
supported Windows game client running locally. No proprietary game content is
included.

## Safe first use

Run the read-only diagnostic first:

```powershell
pvz-runtime-test --pretty
```

It attaches only long enough to produce a JSON snapshot and exits without
sending mouse or keyboard input. A nonzero exit means observation was not
healthy; inspect the JSON rather than bypassing the safety boundary.

Launch the optional monitor with:

```powershell
pvz-monitor
```

The monitor is an explicit operator tool. Its Pause/Resume actions follow the
configured focus policy and fail closed if the expected PvZ window cannot be
verified. It has no autonomous gameplay behavior.

## Runtime and Environment v1

Create one `PvZRuntime`, use its `reader_adapter()` and
`controller_adapter()` to build `PvZEnvironment`, then call `reset()` only
after the operator has manually prepared an available, unpaused level. Supply
the exact immutable `active_rows` configuration for the level. The runtime
does not navigate menus, select seeds, retry levels, collect pickups, or infer
natural win/loss.

See the executable scripts in [`examples/`](../examples) for read-only state
inspection, explicit runtime control, Environment v1 reset, and a policy
selection pattern.

## Contract boundary

These interfaces are frozen in v0.1.0: `GameState v1`, Observation v1, Action
v1, Controller v1, Environment v1, Reward v1, transition JSONL schema v2,
baseline API, and Phase 3.5 runtime/session APIs. Future incompatible changes
require explicit approval, a version/schema update where relevant,
compatibility consideration, tests, and report updates.

Phase 4 may add learning code above this boundary. It must not duplicate
memory addresses, manipulate the game through memory writes, or absorb focus,
window, lifecycle, or deterministic legality rules into model code.
