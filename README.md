# Plants vs. Zombies Deep Learning

A reverse-engineering and reinforcement-learning project built around the original Windows release of **Plants vs. Zombies: Game of the Year Edition**.

> **Current milestone: Phase 3 in progress — GameState v1, placement/action masking, and Controller v1 are frozen; Phase 3.1 has added a deterministic observation encoder.**

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
│ Placement / legality │
│ + invalid-action mask│
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
| Phase 3 | 🚧 In progress | 3.1 encoder complete; action space, masks, stepping, logging, rewards remain |
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

`pvz_env/observation.py` converts frozen `GameState v1` data into a deterministic fixed-size NumPy `float32` vector for future learning code. The v1 schema encodes normalized global/wave state, a six-by-nine spatial plant map, ten seed-bank slots, five closest-to-house zombie slots per lane, and mower state per lane. Pickups, projectiles, and grid items remain available in raw `GameState` but are intentionally deferred from this first encoded representation.

## Repository layout

```text
pvz_reader/        GameState reader, version table, legality rules, diagnostics
pvz_controller/    Semantic Controller v1 and Windows input backend
pvz_env/           Environment-facing observation encoding (Phase 3.1)
tools/             Offline tests, live validation and inspection utilities
docs/              Technical development report
references/         pvztoolkit research-reference submodule
```

## Technical report

**[Phase 1–2 Development Report (LaTeX)](docs/phase-1-2-development-report.tex)** documents the research methodology, pvztoolkit work, reverse-engineered structures, placement rules, Controller v1, tests/live validation and the Phase 3 plan.

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

## Next — Phase 3

Phase 3 will preserve the frozen Phase 1/2 contracts and add:

1. ✅ deterministic fixed-size observation encoding;
2. a semantic discrete action space;
3. invalid-action masks from existing placement legality;
4. optional automatic pickup collection between strategic decisions;
5. a `reset()` / `step()` environment contract;
6. post-action reconciliation from the memory reader;
7. transition logging from raw state through reward/next state;
8. terminal/truncation and reward specifications;
9. random/scripted baselines before learned policies.

Only after that environment is stable will the project introduce the first deep-RL baseline.

## References

The repository includes [`lmintlcx/pvztoolkit`](https://github.com/lmintlcx/pvztoolkit) as a Git submodule for reverse-engineering reference. It is not the runtime game engine.

Plants vs. Zombies is the property of its respective rights holders. This is an independent educational/research project and is not affiliated with or endorsed by PopCap or EA.
