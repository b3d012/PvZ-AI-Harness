# Runtime live-validation checklist

These tools require Windows and a legally obtained PvZ GOTY 1.2.0.1073
installation. Offline tests never invoke them or send desktop input. The live
tool never plants, shovels, collects pickups, or navigates menus.

## A — Read only

Start PvZ, prepare a level, and run:

```powershell
conda activate pvz-dl
python tools/live_test_runtime.py --snapshot snapshots/runtime.json
```

Confirm the process and window are correct, `expected_pvz_hwnd` matches the
game window, the Board summary is coherent, and PLAYING/PAUSED follows manual
game changes.

## B–D — Focus, direct Escape, and runtime idempotence

Manually leave the level playing before each requested confirmation, then run:

```powershell
python tools/live_test_runtime.py --focus-mode auto --exercise-focus --exercise-escape --exercise-pause --snapshot snapshots/runtime-controls.json
```

The tool pauses before input. Confirm:

1. Focus identifies the expected HWND, reports the current foreground HWND,
   brings PvZ forward, and finishes with `foreground_matches=True`.
2. Direct Escape press 1 produces `paused=True` in memory before press 2 is
   permitted.
3. Direct Escape press 2 produces `paused=False` in memory.
4. Runtime `pause` returns `changed`, the second pause returns `already_set`,
   `resume` returns `changed`, and the second resume returns `already_set`.
5. No step reports a second press after a failed transition.

## E — GUI controls in AUTO mode

```powershell
python tools/live_monitor_environment.py
```

Select `auto`, wait until **Focus mode** shows `AUTO`, and leave a level
playing. Then validate:

1. Click **Pause** once: the game visibly pauses, phase becomes `PAUSED`,
   Paused becomes `Yes`, Result is `CHANGED`, Detail is `state_verified`.
2. Click **Pause** again: the game remains paused and Result is `ALREADY_SET`.
3. Click **Resume** once: the game visibly resumes, phase becomes `PLAYING`,
   Paused becomes `No`, and Result is `CHANGED`.
4. Click **Resume** again: the game remains running and Result is
   `ALREADY_SET`.
5. Confirm Expected PvZ HWND equals Foreground HWND for input operations and
   Latest input reports `escape_sent` only for actual transitions.

## F — MANUAL safety

Select `manual`, leave the monitor itself foreground, and click **Pause**.
Confirm Result is `FOCUS_REQUIRED`, Detail explains that MANUAL mode requires
PvZ foreground, the game does not pause, and Latest input is `not_sent`.
The explicit **Focus Game** button is allowed to focus PvZ in either mode, but
MANUAL Pause/Resume never steals focus implicitly.

## G — Process restart

With the monitor running, close PvZ and confirm the process, window, reader,
and Board become unavailable. Restart the supported game and use
**Refresh / Reattach**. Confirm a new PID/HWND is adopted, state reading
recovers, and no stale PID or HWND remains.

## Current live-validation status

Environment v1 gameplay execution was previously validated end to end. The
runtime read-only path also discovered the real process, bound the titled
800×600 window to the same PID, read a coherent Board, classified PAUSED, and
reported observation/action health correctly. A first AUTO focus attempt was
denied by Windows and failed closed without sending Escape.

The first real monitor pass subsequently confirmed that the GUI launches,
tracks the correct PID/window/title, reports healthy reader/controller/Board
state, updates sun/entities/wave, follows manual PLAYING ↔ PAUSED transitions,
and visibly focuses PvZ through **Focus Game**. GUI Pause/Resume did not operate
reliably. Review found that button commands were silently discarded whenever a
periodic refresh future existed, while the foreground and virtual-key input
paths also needed hardening for the real client.

The code now queues operator commands ahead of coalesced refreshes, displays
each operation result, retains focus/pause/input diagnostics, uses a bounded
verified foreground-acquisition sequence, and sends one mapped scan-code
Escape down/up pair. These corrections are covered offline but have not yet
passed the B–G real-game retest. Do not mark Phase 3.5 complete or merge PR #12
until the successful results are recorded here.
