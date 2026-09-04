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

## Final operator-verified result — 4 September 2026

Phase 3.5 has passed its final operator-verified validation against the
supported PvZ GOTY client. This record distinguishes those interactive results
from automated tests and CI; no claim is made that the automated suite itself
performed desktop input.

- Read-only attachment found the process and PID-bound titled game window,
  read a coherent Board/live state, and tracked real `PLAYING` / `PAUSED`
  changes correctly.
- AUTO focus acquired and verified the expected PvZ HWND as foreground. The
  runtime remains fail-closed when foreground verification does not succeed.
- One logical scan-code Escape paused the game and one resumed it; memory
  confirmed both transitions and no duplicate key events were required.
- Runtime idempotence passed: playing → `pause()` → `CHANGED`; paused →
  `pause()` → `ALREADY_SET`; paused → `resume()` → `CHANGED`; playing →
  `resume()` → `ALREADY_SET`.
- In AUTO mode the monitor Pause and Resume controls changed the real game,
  updated phase/pause state, and displayed the corresponding operation status.
- In MANUAL mode with the monitor foreground, Pause returned `FOCUS_REQUIRED`,
  issued no Escape input, and left the game unchanged.
- Closing PvZ invalidated the session. After restart, Refresh/Reattach adopted
  the new PID/HWND, resumed live reads, and did not reuse stale identity.

The first monitor pass had exposed dropped GUI commands, missing operation
feedback, insufficiently hardened foreground acquisition, and an unvalidated
virtual-key Escape path. The bounded command FIFO, coalesced refreshes, visible
results, verified focus sequence, and one scan-code Escape pair corrected those
issues before this final validation. Phase 3.5 runtime/harness infrastructure
is therefore complete and frozen as the stable pre-Phase-4 boundary.

## Unreleased Phase 4 training-support validation

These checks are pending and must all pass before merge or release. Prepare the
exact experiment level in active gameplay, then run:

```powershell
conda activate pvz-rl
python tools/live_test_terminal_outcome.py
```

It must display `running`; after a deliberate natural win it must display
`won` with raw evidence. Re-enter the same level and confirm `running`; then
deliberately lose and leave the Zombies Won screen visible until it displays
`lost`. Do not dismiss either result screen early.

Validate reset postconditions at least three times, substituting the prepared
level's observed numeric seed type IDs:

```powershell
python tools/live_test_same_level_reset.py --level 5 --seed-types 0 1
```

Use PvZ's normal Restart Level control only when prompted. Each pass must show
`reset_ok`, a changed nonzero Board address, level 5, and a near-initial game
clock. This validates operator-assisted reset; unattended reset still requires
a separately implemented and live-validated driver.

Leave falling sun visible and run:

```powershell
python tools/live_test_managed_pickups.py --seconds 30 --yes
```

Confirm observed pickups are clicked, sun rises, one stationary pickup is not
spam-clicked, confirmed counts rise after disappearance, and a strategic action
remains usable afterward. `--yes` is mandatory because this tool sends input.
