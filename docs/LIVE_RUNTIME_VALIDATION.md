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

### Partial read-only observation — 4 September 2026

An observer-only attachment to a real paused Adventure level 7 Board read
`game_scene=3`, `board_result=0`, and `level_complete=false` and returned
`RUNNING` with reason `live_board_playing`. PID-bound process/window/Board
health was coherent. No input was sent. This validates only the ordinary live
Board mapping; WON, LOST, automatic reset, and managed pickups remain pending.

### Training lifecycle update — 5 September 2026

The supported controlled condition is Adventure 1-7. Terminal outcome mapping
was live-observed for RUNNING, WON across Board teardown/Award, and LOST with a
live Board/Zombies Won scene. The operator-assisted same-level verifier passed
three times at level 7; managed pickup collection confirmed 11/11 sun pickups
with zero failures.

The initial automatic Menu failure was not a WindowRect, client-origin, DPI,
or focus error. On GOTY 1.2.0.1073 the synthetic cursor must settle briefly
after moving to the visible Menu control before its click is accepted. A
driver-local 100 ms settle delay opened the normal Menu with one click; board
controller and pickup click defaults were not changed. A settled Restart Level
click visibly opened the native ``Restart Level?`` confirmation, and one Enter
created a distinct level-7 Board at clock zero.

Automatic active reset passed three consecutive times with distinct Board
addresses and `RESET_OK` at level 7. An explicitly attested, already-visible
normal Menu also reset successfully. `GameState.paused` alone remains
insufficient evidence of that menu, so the default driver refuses externally
 paused states without input. Native loss retry and same-level win reset remain
 unvalidated; win reset is still refused.

Loss reset calibration subsequently confirmed `GameOutcome.LOST` as
`game_scene=4` and `board_result=2`. Enter did not activate the native Game
Over screen's visible Try Again control. Its measured logical/client center is
`(384, 369)` on the 800 by 600, 96-DPI client; one settled (100 ms) click at
that coordinate restarted the game. The loss driver therefore uses that one
settled click and leaves same-level/fresh-board proof to the reset verifier.

The full loss-reset verifier subsequently passed twice (`425085536` to
`424159288`, then `424159288` to `420324176`, both level 7 at clock zero). A
third loss retry did create a different level-7 Board at clock zero but was
correctly rejected as `stale_entities`; automatic loss reset is therefore not
claimed as 3/3 validated.
