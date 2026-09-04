# AGENTS.md

Repository instructions for coding agents working on **PvZ-AI-Harness**.

## Project state

- Repository: `b3d012/PvZ-AI-Harness`
- Release: **v0.1.0**
- Status: **Phase 1–3.5 complete and frozen**
- Downstream learning project: `b3d012/PvZ-DeepLearning`
- Target game: **Plants vs. Zombies GOTY 1.2.0.1073**
- Target platform: **Windows**

This repository is the reusable game-integration harness. Deep-RL models, hyperparameters, tuning, checkpoints, and evaluation research belong in the downstream `PvZ-DeepLearning` repository.

## Frozen architecture

```text
PvZ GOTY process
    ↓ read-only observation
GameState v1
    ↓
Observation v1 + deterministic Action v1 mask
    ↓
Environment v1
    ↓
Controller v1 / PvZRuntime
    ↓ ordinary verified Windows input
PvZ GOTY process
```

Runtime ownership:

```text
PvZSession
    ↓
GamePhaseDetector + EnvironmentHealth
    ↓
PvZRuntime
    ↓ reader/controller adapters
PvZEnvironment v1
```

## Frozen public contracts

Treat these as stable unless the user explicitly approves/version-controls a change:

- `GameState v1` and reader semantics;
- `pvz_reader/placement.py` legality rules;
- Controller v1 public API and logical 800×600 coordinate model;
- Observation v1 schema, shape `(5534,)`, normalization, ordering;
- Action v1 schema, 541 WAIT/PLANT actions, explicit active-row contract;
- Environment v1 reset/lifecycle/step/reconciliation behavior;
- Reward v1 and default `RewardSpec`;
- transition JSONL schema v2;
- baseline policy/evaluation API;
- `PvZSession`, `PvZRuntime`, `GamePhase`, `FocusMode`, `EnvironmentHealth`, runtime snapshots, and Environment v1 runtime adapters.

If an incompatible change is actually required, version it deliberately and preserve compatibility where practical. Do not silently mutate a frozen contract for a downstream model's convenience.

## Harness responsibilities

### Observation

- Memory observation is read-only.
- Version-specific offsets/layouts belong in `pvz_reader/versions.py`.
- Do not scatter raw offsets into unrelated modules.
- Keep raw `GameState` separate from encoded learning observations.

### Legality

- `pvz_reader/placement.py` is the deterministic source of placement truth.
- Do not make downstream agents relearn deterministic rules already known to the harness.

### Control and runtime

- Normal actions use semantic Controller v1 operations and ordinary Windows input.
- High-level live callers should use `PvZRuntime` so process, reader, Board, phase, pause, window, focus, and freshness gates run before input.
- MANUAL focus mode never steals focus implicitly.
- AUTO mode may focus only the exact PID-bound PvZ window and must verify foreground identity before input.
- Pause/resume uses one mapped scan-code Escape down/up pair and verifies the resulting memory state.
- Never create alternate session/focus/pause implementations in tools or UI code.
- Runtime operations remain serialized and fail closed.
- Monitor commands use the bounded FIFO; automatic refresh is coalesced and must never discard operator commands.

### Live interaction

- Offline tests/CI must never click the desktop or require a running game.
- Live tools must be clearly named and require explicit operator intent.
- Do not claim a live validation passed unless it actually ran against the game.

## Downstream relationship

Phase 4+ learning now lives at:

`https://github.com/b3d012/PvZ-DeepLearning`

That project pins a harness release instead of copying this source. If downstream work exposes a genuine harness deficiency:

1. confirm the issue belongs below the learning boundary;
2. implement the smallest compatible fix here;
3. add offline tests and any necessary live validation;
4. update the harness technical report/docs;
5. release a new harness version (`v0.1.x` for compatible fixes, a larger version change for broader contract changes);
6. deliberately upgrade the downstream dependency and record the new harness version in experiment metadata.

Do not add PyTorch, TensorFlow, Stable-Baselines3, Gymnasium, Optuna, W&B, model checkpoints, or training configurations to this harness merely because the downstream project uses them.

## Repository rules

Never commit:

- Plants vs. Zombies executables/assets or a local game installation;
- caches, local environments, temporary reverse-engineering dumps;
- model checkpoints/datasets/training logs;
- secrets or `.env` files.

The `references/pvztoolkit` Git submodule is research/reference material, not the runtime game engine. Preserve its provenance and license notices.

## Dependencies

The harness intentionally remains lean. Current project metadata and environment files are the source of truth. When changing a real harness dependency, update dependency docs and verify Windows CI.

## Validation

For normal source changes run:

```powershell
python -m compileall -q pvz_reader pvz_controller pvz_env pvz_runtime tools examples
python -m unittest discover -s tools -p "test_*.py" -v
```

Relevant live changes also require the appropriate `tools/live_test_*` procedure. Runtime changes use `tools/live_test_runtime.py`; the operator monitor is `pvz-monitor` / `tools/live_monitor_environment.py`.

## Git workflow

For substantive harness fixes:

1. start from current `main`;
2. create a focused branch;
3. change only the harness concern being fixed;
4. add/update tests;
5. run required validation;
6. update docs/report if behavior or a contract changed;
7. open a PR;
8. release/version only after validation.

Avoid mixing Phase 4 experiment work into harness PRs.

## Documentation roles

- `README.md`: public harness overview/setup/status.
- `docs/HARNESS.md`: integration guide for downstream developers.
- `docs/RUNTIME.md`: runtime/session safety contract.
- `docs/LIVE_RUNTIME_VALIDATION.md`: recorded live validation.
- `docs/technical-development-report.tex`: cumulative Phase 1–3.5 engineering report.
- `AGENTS.md`: coding-agent rules and frozen boundaries.

## Current handoff

- Phase 1 Reader/GameState v1: complete/frozen.
- Phase 2 Controller v1: complete/frozen.
- Phase 3 Environment v1: complete/frozen.
- Phase 3.5 Runtime: complete/frozen and operator-live-validated.
- Public harness release: v0.1.0.
- Repository canonical name: `PvZ-AI-Harness`.
- Deep-learning research continues in `b3d012/PvZ-DeepLearning`.
