# Phase 3 Environment v1 validation

## Frozen metadata

`environment_contract().to_dict()` reports:

```text
observation_schema_version: 1
observation_shape: [5534]
action_schema_version: 1
action_count: 541
environment_schema_version: 1
reward_schema_version: 1
transition_schema_version: 2
```

## Offline validation

```powershell
python -m compileall -q pvz_reader pvz_controller pvz_env tools
python -m unittest discover -s tools -p "test_*.py" -v
```

The Windows CI workflow runs the same compilation and offline suite.

## Live finding and required retest

Live random-policy evidence showed a legal Peashooter reduce sun from 100 to
0 while the first 0.25-second post-action snapshot did not yet contain the
plant. This is treated as delayed client observation, not an Action v1 mask or
affordability failure. Environment v1 now advances once for the configured
strategic interval, then gives only issued PLANT actions a bounded read-only
reconciliation window (default 0.75 seconds, polled at 0.05 seconds). WAIT
continues to take exactly one post-step read. `StepTiming` reports poll count
and verification wait separately from the configured strategic interval; one
JSONL transition is still written per strategic step.

A transient inability to focus the PvZ window remains
`CONTROLLER_FAILED`, rather than being reclassified as a timing issue.

## Required manual live validation

Prepare an unpaused compatible PvZ level first. No menus, level selection, or
reset automation is performed. Active rows must be supplied explicitly; they
are 1-based on the command line.

Dry run, which issues no mouse input:

```powershell
python tools/live_run_environment.py --active-rows 2,3,4 --policy heuristic --max-steps 5
```

Explicit all-row dry run:

```powershell
python tools/live_run_environment.py --all-rows --policy random --seed 0 --max-steps 5
```

Execute mode with ignored transition output:

```powershell
python tools/live_run_environment.py --all-rows --execute --policy heuristic --max-steps 10 --log-path trajectories/environment-v1.jsonl
```

Confirm and record the following before merging/tagging the Phase 3 milestone:

- dry run resets successfully, reports `(5534,)` and `(541,)`, selects a legal action, and issues zero clicks;
- WAIT advances, produces a post-step observation/reward/outcome, and logs a transition;
- a legal PLANT is reconciled as `PLANT_OBSERVED` either on the first post-step read or during bounded polling, and JSONL includes the final reconciliation state and Reward v1 fields;
- inactive rows are masked and cannot issue controller input;
- max-step truncation blocks later steps, while reset reactivates and restarts index zero;
- scripted and random policies run only legal actions.

Natural win/loss remains unvalidated because GameState v1 has no authoritative
terminal signal. The live runner therefore uses the bounded max-step
truncation unless a future validated detector is injected.
