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

## Live finding and reconciliation correction

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

## Completed live validation

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

Dry-run validation reset successfully, produced observation shape `(5534,)`
and action-mask shape `(541,)`, selected a semantic action with `legal=True`,
and issued zero Controller input. JSONL round-trip validation preserved those
observation and mask shapes together with episode, step, reward, and
truncation data. Pre-action logging confirmed that selected random PLANT seeds
were ready, affordable, and actionable.

The heuristic execute run on a normal five-row lawn completed 10 strategic
steps: eight WAIT actions and two PLANT actions. The first PLANT had a
transient Windows focus failure and was correctly classified
`CONTROLLER_FAILED`; the next Sunflower was `PLANT_OBSERVED`. Subsequent WAIT
actions were `WAIT_ADVANCED`; no action was rejected or masked action reached
the Controller. It recorded zero `PLANT_NOT_OBSERVED` outcomes, one controller
failure, one observed plant, cumulative reward `-0.005`, and
`TRUNCATED`/`MAX_STEPS` at the configured horizon.

The seeded random-valid-action execute run likewise completed 10 strategic
steps (eight WAIT and two PLANT). Its first PLANT received the same transient
focus failure classification; the following legal Sunflower was
`PLANT_OBSERVED`. It recorded zero rejected or `PLANT_NOT_OBSERVED` actions,
one controller failure, one observed plant, and cumulative reward `+0.005`.
WAIT actions reconciled normally, including one transition with the `+0.01`
Reward v1 wave-progress component, before `TRUNCATED`/`MAX_STEPS`.

The earlier false-negative `PLANT_NOT_OBSERVED` finding led to bounded
read-only reconciliation polling. Both post-fix live retests recorded zero
`PLANT_NOT_OBSERVED` outcomes. The transient Windows focus failure remains an
explicit Controller/runtime condition (`CONTROLLER_FAILED`), not a policy or
environment correctness failure. Inactive-row blocking is covered by
deterministic offline regression tests rather than artificially forcing live
clicks on inactive rows.

Natural win/loss remains unvalidated because GameState v1 has no authoritative
terminal signal. The live runner therefore uses bounded max-step truncation
unless a future validated detector is injected.
