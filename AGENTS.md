# AGENTS.md

Repository instructions for coding agents working on **PvZ-DeepLearning**.

These instructions are intended to keep future Codex/agent work consistent with the architecture already validated through Phase 2. Read this file before making substantial changes.

## Project state

- Repository: `b3d012/PvZ-DeepLearning`
- Current milestone: **Phase 3.5 complete — PvZ AI Harness v0.1.0 frozen**
- Next milestone: **Phase 4 — deep reinforcement learning**
- Target game: **Plants vs. Zombies GOTY 1.2.0.1073**
- Target platform: **Windows**

Current architecture:

```text
PvZ GOTY process
    ↓ read-only memory observation
GameState v1
    ↓
deterministic EncodedObservation v1
    ↓
semantic Action v1 / legality masking
    ↓
semantic Controller v1
    ↓ normal Windows mouse input
PvZ GOTY process
```

Runtime ownership is implemented in `pvz_runtime` beneath Environment v1:

```text
PvZSession (PID-bound process, MemoryReader, PvZ window)
    ↓
GamePhaseDetector + EnvironmentHealth
    ↓
PvZRuntime (focus/pause/watchdog/actions/snapshots)
    ↓ reader/controller adapters
frozen pvz_env.PvZEnvironment v1
```

## Frozen public contracts

Treat the following as stable interfaces unless the user explicitly approves a breaking change:

- `GameState v1`
- `pvz_reader` observation semantics
- `pvz_reader/placement.py` as the source of deterministic placement legality/action masks
- `Controller v1` public API
- logical 800×600 controller coordinate model
- `Observation v1` schema, shape `(5534,)`, normalization, and ordering
- `Action v1` schema, 541-index WAIT/PLANT layout, and explicit active-row contract
- Environment v1 reset/lifecycle/step/reconciliation contracts
- Reward v1 schema and default `RewardSpec`
- transition JSONL schema v2
- baseline policy/evaluation API
- `PvZSession`, `PvZRuntime`, `GamePhase`, `FocusMode`, `EnvironmentHealth`,
  public runtime snapshots, and Environment v1 runtime adapters

Do **not** casually redesign or merge these layers together during later phases.

If a Phase 4 task appears to require changing a frozen interface:

1. stop before making the breaking change;
2. explain why the current contract is insufficient;
3. propose the smallest compatible change;
4. bump the applicable schema/version where appropriate and consider compatibility;
5. update tests and the technical report;
6. wait for explicit approval if the change is architectural or breaks existing callers/tests.

## Architectural rules

### Observation

- Game observation is read-only.
- Version-specific memory offsets/layouts belong in `pvz_reader/versions.py`.
- Do not scatter raw target-build offsets through unrelated modules.
- Do not put controller/action state inside `GameState` merely for convenience.
- Preserve raw structured game observation separately from future encoded neural-network observations.

### Placement and action legality

- Use `pvz_reader/placement.py` for deterministic placement rules.
- Do not make a future neural network relearn rules that are already known deterministically.
- Future RL action masks should derive from the existing legality layer where possible.

### Control

- Normal gameplay actions use `pvz_controller` and standard Windows mouse input.
- Do not replace Controller v1 with game-memory writes for ordinary agent actions.
- Maintain the semantic-action abstraction: higher layers request actions such as plant/shovel/collect rather than raw screen clicks whenever practical.
- New high-level live callers should use `PvZRuntime.execute()` so process,
  reader, Board, phase, pause, window, focus, and freshness gates run before
  Controller v1. The Environment v1 adapters use this same path.

### Runtime infrastructure

- `pvz_runtime.session.PvZSession` owns process discovery, PID attachment,
  PID-bound window identity, process-death detection, controlled reattachment,
  and clean detach.
- `pvz_runtime.phase.GamePhaseDetector` is conservative. Frozen GameState v1
  can distinguish Board presence, pause, and clock-derived READY/PLAYING, but
  cannot authoritatively split menu/loading/results or detect natural win/loss.
- `pvz_runtime.runtime.PvZRuntime` owns MANUAL/AUTO focus policy, state age,
  health/watchdog evaluation, idempotent verified pause/resume, semantic action
  gating, snapshots, and Environment v1 adapters.
- MANUAL mode must never restore focus implicitly. AUTO mode may restore focus
  only for the PID-bound window and must verify it is foreground before input.
- Explicit operator Focus may restore a minimized PID-bound window and use
  documented Win32 input-queue attachment/activation calls, but exact
  foreground HWND verification remains mandatory before any input.
- Runtime Escape input uses one `MapVirtualKey`-derived scan-code down/up pair.
  Never send virtual-key plus scan-code fallbacks for one logical pause request;
  a duplicate Escape would undo the requested transition.
- Do not create alternate session/focus/pause logic in tools or UIs. The Tk
  monitor is a frontend to the same runtime API.
- Runtime operations are serialized. Do not add autonomous input loops or
  uncontrolled reconnect polling.
- Monitor user commands must enter its bounded FIFO and execute once. Automatic
  refresh is coalesced, never queued, and must yield to pending commands. Never
  return to a shared-Future design that silently drops button presses.

### Live interaction

- Offline tests must never intentionally click the user's desktop or require a running PvZ process.
- Interactive tests/tools must be clearly named `live_test_*`.
- Do not silently turn an offline test into a live/interactive test.

## Repository rules

Never commit:

- the proprietary Plants vs. Zombies game installation;
- game executables/assets;
- Python caches;
- local virtual environments;
- raw temporary reverse-engineering dumps unless explicitly retained as durable documentation;
- model checkpoints;
- large generated datasets;
- local secrets or `.env` files.

Follow `.gitignore` and extend it when a new generated-artifact category is introduced.

The `references/pvztoolkit` directory is a Git submodule used as a reverse-engineering reference. It is not the runtime game engine for the AI agent.

## Current dependency policy

Phase 1–2 intentionally uses a lean environment defined by:

- `environment.yml`
- `requirements.txt`

Do not add large ML/RL dependencies until the phase that actually uses them.

When adding or changing dependencies:

1. update `environment.yml`;
2. update `requirements.txt` when applicable;
3. update `docs/DEPENDENCIES.md`;
4. verify Windows CI still passes.

## Validation required before completing implementation tasks

Run the complete offline test suite:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

Also compile the Python source tree when practical:

```powershell
python -m compileall -q pvz_reader pvz_controller pvz_env pvz_runtime tools
```

For changes affecting live reader/controller behavior, also identify the relevant `tools/live_test_*` validation that should be run manually against the real game.

Runtime changes use `tools/live_test_runtime.py`; the operator monitor is
`tools/live_monitor_environment.py`. Both are live-only and excluded from CI.

Do not claim a live validation passed unless it was actually run against the game.

## Git workflow

For substantial implementation work:

1. begin from current `main`;
2. create a focused branch;
3. implement one bounded task/subphase;
4. add/update tests;
5. run validation;
6. commit with a descriptive message;
7. summarize the handoff;
8. do not start the next subphase unless requested.

Prefer narrowly scoped branches such as:

```text
feat/phase-3.1-observation-encoder
feat/phase-3.2-action-space
fix/environment-step-timing
```

Avoid giant branches that implement an entire multi-stage phase without checkpoints.

## Phase workflow

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

An unreleased `feat/phase4-training-support` branch contains the narrow
terminal/reset/pickup lifecycle candidate for issue #16. Do not merge or tag it
until the documented real RUNNING/WON/LOST, repeated reset, and falling-sun
pickup protocols pass against GOTY 1.2.0.1073. The default restart driver must
remain fail-closed until an automatic mechanism is live validated.
