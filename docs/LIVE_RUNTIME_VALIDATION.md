# Runtime live-validation checklist

These tools require Windows and a legally obtained PvZ GOTY 1.2.0.1073
installation. Offline tests never invoke them or send desktop input.

## Read-only inspection

Start PvZ, then run:

```powershell
python tools/live_test_runtime.py --snapshot snapshots/runtime.json
```

Confirm that the process PID, matching window title, reader status, Board
status, phase, focus, state age, and compact game summary are sensible. Close
PvZ, restart it, rerun or use Refresh/Reattach in the monitor, and confirm the
new PID is adopted rather than the old attachment.

## Explicit focus and pause validation

Prepare an active level. These modes can send focus and Escape input only after
interactive confirmation:

```powershell
python tools/live_test_runtime.py --focus-mode manual --exercise-focus --exercise-pause --snapshot snapshots/runtime-controls.json
python tools/live_test_runtime.py --focus-mode auto --exercise-focus --exercise-pause
```

Validate in order:

1. With MANUAL mode and PvZ unfocused, ordinary runtime actions are refused.
2. `--exercise-focus` targets the detected PID-bound PvZ window.
3. Pause changes running to paused with one Escape press.
4. A second pause returns `ALREADY_SET` and does not toggle.
5. Resume changes paused to running with one Escape press.
6. A second resume returns `ALREADY_SET` and does not toggle.
7. The tool restores the pause state that existed before the exercise.
8. AUTO mode restores and verifies foreground focus when Windows permits it.
9. Switching away or denying focus produces a typed refusal and no gameplay
   click.
10. Closing/reopening PvZ is recovered by a controlled reattach.

The tool does not plant, shovel, collect pickups, navigate menus, or automate
level progression.

## Monitor

```powershell
python tools/live_monitor_environment.py
```

The monitor displays connection, PID, HWND/title, focus mode, reader and
controller readiness, Board validity, phase, level/wave/pause/sun/entity
summary, state age, last action, and last error. Controls use the shared runtime
API for Focus, Pause, Resume, Refresh/Reattach, Snapshot JSON, and Detach.

## Current live-validation status

Environment v1 gameplay execution was previously validated end to end. The new
runtime's read-only path was also run against the real client: it automatically
found the process, bound the matching 800 by 600 titled window to the same PID,
read a coherent Board, classified the observed paused state as `PAUSED`, and
reported `can_observe=True` while correctly keeping `can_act=False` because the
game was paused and unfocused. No input was enabled for this pass.

Process restart, MANUAL/AUTO focus-policy input, idempotent pause/resume, and
monitor controls still require a dedicated successful live pass. An AUTO-mode
control attempt was also run: Windows denied foreground activation, the
runtime returned `focus_result=False`, resume attempts returned
`FOCUS_FAILED`, and no Escape transition was sent. Repeated requests for the
already-paused state returned `ALREADY_SET`, and the original pause state was
preserved. This validates the live fail-closed focus path, not successful
focus or pause-state transitions. Do not mark the remaining items
live-validated until the checklist is recorded with actual results.
