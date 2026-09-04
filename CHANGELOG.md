# Changelog

All notable public changes are recorded here. This project follows semantic
versioning for releases; its frozen runtime contracts retain their own explicit
schema versions.

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

[0.1.0]: https://github.com/b3d012/PvZ-DeepLearning/releases/tag/v0.1.0
