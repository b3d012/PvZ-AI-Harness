# Changelog

All notable public changes are recorded here. This project follows semantic
versioning for releases; its frozen runtime contracts retain their own explicit
schema versions.

## [Unreleased]

## [0.2.1]

- Corrected Controller v1's in-level seed-bank targeting with the supported
  packet-count-aware layout. Adventure 1-7's six packets use
  `(120 + 59 * slot, 43)`; all six selections were live verified without
  planting.
- Corrected scene-aware lawn input geometry. Normal five-lane boards use
  `(80 + 80 * col, 130 + 100 * row)`; exact memory-confirmed Adventure 1-7
  placements passed on all five rows. Pool/fog and roof mappings retain their
  separately derived offline regressions.
- Added native loss-dialog readiness evidence from `CutScene.mCutsceneTime`.
  Loss restart waits for `>= 11000`, then sends one settled Try Again click;
  three immediate autonomous loss resets passed.
- Added read-only geometry calibration plus bounded targeted seed-selection
  and placement live-validation tools. Frozen v1 public contracts are
  unchanged.

## [0.2.0]

- Added live-validated natural RUNNING/WON/LOST lifecycle evidence without
  changing GameState v1.
- Added `Board::mLevelAwardSpawned` (`+0x5624`) for a live reward-pending win;
  a retained BoardResult alone remains nonterminal while a Board exists.
- Added verified same-level restart through active, known pause-menu, loss
  Try Again, and live reward-pending win paths.
- Added managed pickup collection under runtime serialization.
- Validated on GOTY 1.2.0.1073 / Adventure 1-7: loss reset 4/4, win reset
  3/3, and managed sun collection 11/11.

- Added typed, memory-backed `RUNNING` / `WON` / `LOST` / `UNKNOWN` outcome
  evidence for the supported GOTY layout without changing GameState v1.
- Added fail-closed same-level reset postcondition verification behind a
  pluggable restart driver.
- Added synchronous managed pickup collection, deduplication, confirmation
  metrics, and composition through `TrainingEpisodeSupport`.
- Added offline lifecycle tests and dedicated terminal/reset/pickup live tools.

## [0.1.0] — 2026-09-04

- First public **PvZ AI Harness** release.
- Frozen `GameState v1`, Observation v1, Action v1, Controller v1,
  Environment v1, Reward v1, transition JSONL schema v2, baseline API, and
  Phase 3.5 runtime/session contracts.
- Added PID-bound runtime attachment, fail-closed focus policy, idempotent
  scan-code pause/resume, health snapshots, runtime adapters, a Tk monitor,
  live diagnostics, examples, and packaging metadata.
- Recorded successful operator-verified end-to-end Environment v1 and runtime
  validation against the supported PvZ GOTY client.

[0.2.0]: https://github.com/b3d012/PvZ-AI-Harness/releases/tag/v0.2.0
[0.2.1]: https://github.com/b3d012/PvZ-AI-Harness/releases/tag/v0.2.1
[0.1.0]: https://github.com/b3d012/PvZ-AI-Harness/releases/tag/v0.1.0
