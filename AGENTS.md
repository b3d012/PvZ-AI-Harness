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

During a phase:

- research and implementation artifacts may be temporary;
- keep durable conclusions in source, tests and documentation;
- preserve debugging utilities that are likely to be useful for regressions;
- remove obsolete one-off dumps before freezing the phase.

At the end of each **major phase**:

1. run the full offline validation suite;
2. perform required live validations;
3. freeze important public interfaces if appropriate;
4. update `README.md` with the public project status;
5. update the LaTeX technical report with the completed phase;
6. update dependencies/CI/documentation if changed;
7. clean temporary research artifacts;
8. merge the phase work to `main`;
9. create a milestone tag if appropriate.

The technical report should be updated at major phase boundaries rather than after every small experiment.

## Phase 3 plan

Phase 3 is the **RL environment bridge**, not yet the main neural-network training phase.

Recommended sequence:

### Phase 3.1 — Observation specification and encoder

- ✅ Complete: `pvz_env.observation` defines deterministic fixed-size
  `float32` observations from `GameState v1`.
- Raw `GameState` and encoded observations remain separate.
- The schema, normalization, deterministic zombie slotting, metadata, and
  deferred fields are covered by offline tests. Adventure level and per-lane
  zombie live/overflow counts are encoded; inactive-row masking remains a
  Phase 3.2 requirement because frozen `GameState v1` has no authoritative
  active-row field.

### Phase 3.2 — Semantic action space

- ✅ Complete: `pvz_env.actions` defines Action v1's fixed 541-index space:
  `WAIT` plus seed-slot × row × column `PLANT` actions.
- `build_action_mask` returns a fixed NumPy boolean mask and delegates every
  placement decision to `pvz_reader.placement.can_plant`.
- `GameState v1` does not authoritatively expose active lawn rows. The mask
  therefore accepts an explicit immutable six-boolean episode `active_rows`
  configuration; Phase 3.3 reset/lifecycle code must supply it for levels
  with inactive rows. Do not infer it from Adventure progression or empty rows.
- Shovel and pickup actions are intentionally deferred from Action v1.

### Phase 3.3 — Environment step contract

- ✅ Complete: `pvz_env.environment.PvZEnvironment` coordinates reader
  snapshots, Observation v1, Action v1 masks, Controller v1 planting, an
  explicit injected step interval, and a post-interval read.
- `StepResult` provides typed before/after snapshots, semantic action,
  controller result, stable rejection reason, reconciliation status, timing,
  and an optional backwards-compatible Reward v1 outcome. A legal action
  advances once for `step_interval_seconds`; an issued PLANT may then use
  episode-configured bounded read-only polling to verify its postcondition.
  This is not an additional strategic step and never reissues controller input;
  WAIT has no reconciliation polling.
- The environment owns immutable explicit `active_rows` episode configuration
  and passes it into every Action v1 mask build. Pickup collection remains
  deferred; no environment-managed clicks occur in Phase 3.3.

### Phase 3.4 — Transition logging

- ✅ Complete: `pvz_env.logging` defines versioned `TransitionRecord` data,
  deterministic NumPy payload serialization, and append-only UTF-8 JSONL
  persistence with round-trip reading.
- `PvZEnvironment` accepts an optional injected transition sink and emits one
  record for every `step()` call, including rejected attempts. Episode ID is
  externally supplied; step indexes begin at zero and increment for every
  attempted step. Phase 3.6 will own reset/episode rollover.
- Persistence failures raise `TransitionLoggingError` after the gameplay
  `StepResult` exists; they are never reclassified as controller failures.
- Transition schema v2 persists the Reward v1 outcome fields. Generated
  `/logs/` and `/trajectories/` data are ignored.

### Phase 3.5 — Reward and terminal rules

- ✅ Complete: `pvz_env.rewards` defines `REWARD_SCHEMA_VERSION = 1`, frozen
  inspectable `RewardSpec`, deterministic `RewardOutcome`, and a pure
  `RewardModel` evaluator. Terminal +/-1 dominates reward; only spawned-wave
  delta shaping (+0.01 default) and small technical diagnostic penalties are
  enabled. WAIT and successful plants have no activity reward.
- Frozen `GameState v1` has no authoritative natural win/loss signal. The
  explicit injected `TerminalDetector` seam is therefore required to report a
  win/loss; the default detector never guesses. `max_steps` and configured
  repeated unavailable state are truncations, never natural losses.

### Phase 3.6 — Reset / episode lifecycle

- ✅ Complete: `EpisodeConfig` owns immutable episode identity, active rows,
  timing/truncation limits, Reward v1 configuration, optional detector, and
  caller-provided metadata. `reset()` adopts an available, unpaused,
  manually prepared game state and returns a typed `ResetResult`.
- `PvZEnvironment` lifecycle is `UNINITIALIZED`, `ACTIVE`, `TERMINATED`, or
  `TRUNCATED`. Steps are forbidden before reset and after an outcome; reset
  clears the step and unavailable-state counters. The transition sink remains
  caller-owned and records per-episode IDs with indexes restarting at zero.
- Menu navigation, level selection, dialogue/retry automation, and Adventure
  progression remain intentionally out of scope.

### Phase 3.7 — Baselines

- ✅ Complete: `pvz_env.baselines` supplies a seeded `RandomValidActionPolicy`,
  a compact `SimpleHeuristicPolicy`, typed decisions, a reset-aware
  `run_episode` evaluation harness, `EpisodeResult`, and deterministic
  multi-episode summaries. Policies emit Action v1 indexes only.
- The random baseline uses Observation v1 plus the legality mask. The scripted
  engineering baseline may inspect the current structured snapshot for simple
  economy/threat rules, but still relies on the Action v1 mask rather than
  reproducing placement legality; it is not an apples-to-apples neural-policy
  architecture. The explicit live runner completed heuristic and seeded
  random-policy end-to-end validation against the real client.

### Phase 3.8 — Environment v1 freeze

✅ Complete: Environment v1 is frozen after offline validation and recorded
end-to-end live validation against the real client. The frozen public
contracts are Observation v1, Action v1, Environment v1, Reward v1, and
transition JSONL schema v2.

The completed freeze criteria were:

- observation encoding is deterministic;
- invalid actions are masked/rejected correctly;
- action results reconcile with subsequent observations;
- step timing is documented;
- episodes terminate/truncate predictably;
- trajectories round-trip to disk;
- repeated baseline runs do not corrupt the environment interface.

`environment_contract()` exposes the frozen observation, action, environment,
reward, and transition schema identifiers. `tools/live_run_environment.py` is
dry-run by default, requires explicit active rows, and needs `--execute`
before normal mouse input. Its completed validation record is in
`docs/PHASE_3_VALIDATION.md`. Later breaking changes require explicit
versioning and approval under the frozen-contract rules above.

Only after this should the project move into the main deep-reinforcement-learning training phase.

## Deep-learning direction

The intended learning approach is **deep reinforcement learning**: a neural-network policy/value model learns strategic behavior through repeated interaction and reward feedback.

A PPO-family baseline with invalid-action masking is a reasonable initial candidate once Environment v1 exists, but do not lock the project to a training algorithm before Phase 3 establishes the observation/action interface.

The policy should learn strategy rather than deterministic game rules already encoded by the environment.

## Documentation responsibilities

Keep the following roles distinct:

- `README.md` — concise public/portfolio overview, architecture, current status, setup and headline results;
- `docs/technical-development-report.tex` — cumulative LaTeX technical development report;
- `AGENTS.md` — coding-agent rules, frozen contracts, current phase and workflow;
- Git history/tests — implementation-level trace of experiments and changes.

When a major phase completes, update this file's **Project state**, **Next milestone**, frozen contracts if applicable, and the phase roadmap.

## Required handoff format

After a substantial subphase/task, provide a concise handoff containing:

```text
HANDOFF

Completed:
Changed files:
Tests run:
Live validation:
APIs/contracts changed:
Known limitations:
Current branch:
Commit(s):
Recommended next subphase:
```

Be explicit about what was **not** tested or not completed.

## Current handoff state

- Phase 1 reader is complete and `GameState v1` is frozen.
- Placement legality/action masking is implemented and tested.
- Phase 2 Controller v1 is complete and frozen.
- Phase 1–2 technical report exists under `docs/`.
- Proprietary game files were removed from the working tree and rewritten `main` history.
- Portfolio README exists.
- reproducible environment files exist.
- Windows offline CI exists and passes.
- **Phase 3 is complete and its contracts remain frozen.**
- **Phase 3.5 is complete and frozen.** Final operator-verified live validation
  confirmed AUTO focus, scan-code pause/resume, idempotence, MANUAL fail-closed
  behavior, and restart/reattach. Phase 4 builds training above the harness;
  it must not absorb runtime safety, UI monitor, or training configuration into
  frozen reader/controller/environment/runtime layers.

**v0.2.0 training lifecycle support is live validated and preserves v1
contracts.** `Board::mLevelAwardSpawned` at Board `+0x5624` is authoritative
for a live reward-pending win on the supported client; `board_result` alone is
unsafe while a Board exists. Reset postconditions (new Board, same level,
fresh unpaused state, and clean entities) are authoritative. Unknown paused
modals fail closed. The version-pinned UI driver applies only to the 800x600
GOTY client and uses a 100 ms cursor-settle delay for Menu `(739, 13)`, Restart
Level `(400, 358)`, and Try Again `(384, 369)`. The validated research
condition is Adventure 1-7; do not substitute forced earlier levels, which
were unstable on the target installation.
