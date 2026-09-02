# Plants vs. Zombies Deep Learning

A reverse-engineering and reinforcement-learning project built around the original Windows release of **Plants vs. Zombies: Game of the Year Edition**.

> **Current milestone: Phase 3.8 Environment v1 freeze candidate — offline validation is complete; required live validation remains pending.**

## Architecture

```text
Plants vs. Zombies GOTY
        │ read-only process memory
        ▼
┌──────────────────────┐
│     GameState v1     │
│ plants / zombies     │
│ seeds / waves / sun  │
│ pickups / mowers ... │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ EncodedObservation v1│
│ fixed NumPy float32  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Semantic Action v1  │
│ + legality mask     │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Controller v1     │
│ semantic actions     │
│ normal Windows input │
└──────────┬───────────┘
           ▼
Plants vs. Zombies GOTY
```

`PvZEnvironment` orchestrates the reader, encoded observation, Action v1 mask,
Controller v1 semantic action, configured advancement interval, and subsequent
read/reconciliation; it does not add direct game input or memory writes.

The long-term goal is to train an AI agent to play the real game strategically rather than using a clone or custom simulator. Reading internal state provides exact HP, cooldown, wave, type, status and coordinate information so the learning problem can focus on strategy. Observation is read-only; normal agent actions are performed through ordinary Windows mouse input.

## Supported build

- **Plants vs. Zombies GOTY 1.2.0.1073**
- Windows 10/11
- version-specific layouts centralized in `pvz_reader/versions.py`

**The game is not included in this repository.** Supply your own legally obtained compatible installation.

## Project phases

| Phase | Status | Deliverable |
| --- | --- | --- |
| Phase 1 | ✅ Complete | External memory reader and frozen `GameState v1` |
| Placement layer | ✅ Complete | Special placement rules and invalid-action masks |
| Phase 2 | ✅ Complete | Controller v1: pickup, plant, shovel, safe Windows input |
| Phase 3 | 🚧 Freeze candidate | Environment v1 contracts, baselines, and offline validation complete; live sign-off pending |
| Phase 4 | Planned | Deep-RL baselines and training |
| Phase 5 | Planned | Evaluation, ablations, strategy analysis and demos |

## Phase 1 — Game-state reader

`pvz_reader/` reconstructs structured state from the live GOTY process, including sun/clock/scene, plants, zombies, seed cooldown/readiness, waves, mowers, pickups, projectiles and grid items. Reverse engineering combined reference-source inspection, small memory-inspection utilities, address watches and repeated live validation. Offsets from other builds were treated as hypotheses and verified against the target executable.

## Placement legality

`pvz_reader/placement.py` converts raw state into deterministic placement decisions and reason codes. It covers ordinary grass placement plus Lily Pads, Flower Pots, water plants, Grave Buster, Pumpkin, Coffee Bean, blockers/craters and upgrade plants such as Gatling Pea, Twin Sunflower, Gloom-shroom, Cattail, Winter Melon, Gold Magnet, Spikerock and Cob Cannon.

This layer will directly power invalid-action masking in Phase 3.

## Phase 2 — Controller v1

`pvz_controller/` translates semantic actions into normal mouse input. Controller v1 supports collecting an observed pickup, planting a seed-bank slot on a board tile and shoveling a tile, with precondition checks and post-observation helpers.

PvZ renders to an 800×600 logical client. Coordinates are defined in that logical space and scaled to the current Windows client rectangle. The Windows backend verifies the target process/window, rejects minimized or unusable clients, checks coordinate bounds, focuses the game and sends ordinary left-click input.

## Phase 3.1 — Observation encoder

`pvz_env/observation.py` converts frozen `GameState v1` data into a deterministic fixed-size NumPy `float32` vector for future learning code. The v1 schema encodes normalized global/wave state including Adventure level, a six-by-nine spatial plant map, ten seed-bank slots, five closest-to-house zombie slots per lane plus bounded live/overflow counts, and mower state per lane. Pickups and projectiles remain deferred. Grid items also remain deferred, although graves, craters, and ladders are strategically relevant candidates for a later observation revision; placement legality continues to use raw `GameState.grid_items`.

`GameState v1` does not authoritatively identify temporarily inactive rows in early Adventure levels. Scene only identifies five- versus six-row terrain, so Phase 3.2 action masking must explicitly solve inactive-row masking rather than infer it from an empty row.

## Phase 3.2 — Semantic action space

`pvz_env.actions` defines Action v1: a fixed 541-index space containing `WAIT` at index 0 followed by `PLANT(seed_slot, row, col)` in seed-slot, row, then column order. Its NumPy boolean mask delegates plant legality to `pvz_reader.placement.can_plant`; absent or unavailable seeds, invalid terrain, blockers, and prerequisite failures are masked without changing the action-space size. The caller supplies an explicit six-boolean `active_rows` episode configuration when a level has inactive lawn rows. Shovel and pickup actions are deferred; pickup handling is deferred from the environment bridge as well.

## Phase 3.3 — Environment step bridge

`pvz_env.environment.PvZEnvironment` provides typed `observe()` and `step(action_index)` operations over injected reader, Controller v1, sleeper, and clock seams. Every legal `WAIT` or `PLANT` advances exactly once for the configured interval, reads a new `GameState`, re-encodes Observation v1, rebuilds the Action v1 mask with the environment-owned active-row configuration, and returns typed reconciliation metadata plus a Reward v1 outcome. Reset automation and pickup management remain deferred.

## Phase 3.4–3.5 — Transition logging and reward outcomes

`pvz_env.logging` records each environment step as a versioned `TransitionRecord`: raw before/after game state, encoded observations, action masks, semantic action, Controller result, reconciliation, timing, and Reward v1 outcome. Schema v2 persists reward, component breakdown, terminal/truncation flags and reason, and reward schema/spec identity.

Reward v1 assigns `+1.0` for a detected win and `-1.0` for a detected loss. A newly spawned wave adds only `+0.01`; rejected actions and technical failures have small diagnostic penalties. WAIT and successful planting receive no activity reward. Because `GameState v1` has no validated win/loss signal, an injected terminal detector is required for natural outcomes and the default detector never guesses. Step horizons and repeated unavailable state are truncations, not losses.

## Phase 3.6 — Episode lifecycle

`PvZEnvironment` starts `UNINITIALIZED`. The caller manually prepares a running level, then calls `reset(EpisodeConfig(...))`; reset validates an available, unpaused state and returns the initial raw state, encoded observation, and action mask in `ResetResult`. The immutable episode configuration owns identity, active rows, timing/truncation limits, Reward v1 configuration, optional terminal detector, and optional caller-provided metadata. A step is permitted only while `ACTIVE`; terminal/truncated outcomes block further gameplay until another explicit reset. Reset never navigates menus, chooses levels, dismisses dialogs, or creates a transition record.

## Phase 3.7 — Baselines and evaluation

`pvz_env.baselines` provides a reproducibly seeded random valid-action policy, a deliberately small scripted economy/threat policy, typed action-decision reasons, and `run_episode`/`summarize_episodes` helpers. Both use Environment v1 reset, Action v1 masks, `step()`, Reward v1, and episode outcomes. The scripted baseline has transparent access to the structured snapshot for its simple rules; it remains an engineering comparison baseline, not a learned-policy input design.

## Environment v1 freeze candidate

`environment_contract()` exposes frozen checkpoint/evaluation metadata: Observation schema v1 and shape `(5534,)`, Action schema v1 and 541 actions, Environment schema v1, Reward schema v1, and transition schema v2. The public Environment v1 contract covers `EpisodeConfig`, `reset()`, lifecycle states, `step()` reconciliation, Reward v1 outcomes, JSONL transitions, and baseline evaluation.

The explicit live validation runner is dry-run by default:

```powershell
python tools/live_run_environment.py --active-rows 2,3,4 --policy heuristic --max-steps 5
```

It never infers active rows. For a known full board, provide `--all-rows`. Real Windows mouse input requires `--execute` and remains bounded by `--max-steps`:

```powershell
python tools/live_run_environment.py --all-rows --execute --policy heuristic --max-steps 10 --log-path trajectories/environment-v1.jsonl
```

Prepare an unpaused level manually; the runner does not navigate menus or dialogs. Natural win/loss remains unavailable without a validated injected terminal detector, so the default live run ends at its configured max-step truncation. See [Phase 3 validation](docs/PHASE_3_VALIDATION.md) for the required live checklist. Phase 4 will begin deep-RL training only after Phase 3 receives this sign-off.

## Repository layout

```text
pvz_reader/        GameState reader, version table, legality rules, diagnostics
pvz_controller/    Semantic Controller v1 and Windows input backend
pvz_env/           Observation, action, step, reward/outcome, logging, lifecycle, baselines, and frozen contract metadata
tools/             Offline tests, live validation and inspection utilities
docs/              Technical development report
references/         pvztoolkit research-reference submodule
```

## Technical report

**[Technical Development Report (LaTeX)](docs/phase-1-2-development-report.tex)** documents the Phase 1--3 architecture, research methodology, validation, Environment v1 contracts, and Phase 4 transition.

## Setup

Requirements: Windows 10/11, Conda/Miniconda, Git, and a compatible legally obtained PvZ GOTY 1.2.0.1073 installation.

```powershell
git clone --recurse-submodules https://github.com/b3d012/PvZ-DeepLearning.git
cd PvZ-DeepLearning
conda env create -f environment.yml
conda activate pvz-dl
```

If cloned without submodules:

```powershell
git submodule update --init --recursive
```

The Phase 1–2 environment is intentionally lean: `pymem`, `psutil`, and `numpy`. RL/deep-learning packages are added only when Phase 3/4 requires them.

## Validation

The offline suite does not require PvZ to be running and does not intentionally click the desktop:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

It also runs automatically on Windows in GitHub Actions.

Files beginning with `tools/live_test_` intentionally interact with a running game and are excluded from CI.

## Safety and repository scope

- game observation is read-only;
- Controller v1 uses ordinary Windows mouse input;
- live tools are separated from offline tests;
- proprietary game files, caches, research dumps, model checkpoints and datasets are ignored;
- this repository does not distribute Plants vs. Zombies executables or assets.

## Next — Phase 4

Phase 3 is pending final live sign-off with the checklist above. Once frozen,
Phase 4 will add deep-RL training while preserving the Phase 1--3 contracts:

1. deep-RL baseline design and implementation;
2. checkpoint/run metadata using the Environment v1 contract helper;
3. evaluation against the frozen random and scripted baselines.

Only after that environment is stable will the project introduce the first deep-RL baseline.

## References

The repository includes [`lmintlcx/pvztoolkit`](https://github.com/lmintlcx/pvztoolkit) as a Git submodule for reverse-engineering reference. It is not the runtime game engine.

Plants vs. Zombies is the property of its respective rights holders. This is an independent educational/research project and is not affiliated with or endorsed by PopCap or EA.
