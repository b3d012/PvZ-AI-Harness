# PvZ runtime infrastructure

`pvz_runtime` is the fail-closed operating layer beneath frozen Environment v1.
It centralizes process ownership, PID-bound window discovery, observation
health, focus policy, semantic pause control, and Controller v1 action gating.
It does not change Observation v1, Action v1, Reward v1, transition schema v2,
or the Environment v1 step/lifecycle contract.

## Ownership and composition

```text
PvZ GOTY process
  ├─ PvZSession ── PID-bound MemoryReader ── PvZGameStateReader
  └─ WindowsInputBackend ── same PID's verified HWND ── Controller v1
                 │
       GamePhaseDetector + EnvironmentHealth
                 │
              PvZRuntime
          ┌──────┴────────┐
   runtime monitor   Environment v1 adapters
```

- `PvZSession` discovers a supported executable, attaches by PID, binds window
  lookup to that PID, owns the memory handle, detects process death, and makes
  one controlled reconnect attempt per `ensure_attached()` call.
- `GamePhaseDetector` conservatively derives semantic phase from process,
  reader, Board, `paused`, and `game_clock` evidence.
- `PvZRuntime` serializes observation, focus, pause, reattach, and action
  operations with one reentrant lock. It owns cached-state age and fail-closed
  action checks.
- `EnvironmentHealth` distinguishes `can_observe` from `can_act` and carries
  machine-readable diagnostic reasons.
- `RuntimeReaderAdapter` and `RuntimePlantControllerAdapter` place these gates
  beneath the existing `pvz_env.PvZEnvironment` without changing its API.

## Session and version confidence

Supported process names are `PlantsVsZombies.exe` and `popcapgame1.exe`.
Process discovery validates the executable basename when an executable path is
available. Window enumeration then requires both a supported process name and
the exact attached PID, preventing a controller from drifting to another
same-named process after a restart.

The reader layout remains pinned to GOTY `1.2.0.1073`. There is no authoritative
binary fingerprint in the repository, so `SessionStatus.version_verified` is
deliberately `False`; the status reports the expected version without claiming
cryptographic verification. Reader failures invalidate and close the current
attachment. A later call may discover a replacement PID.

## Phase semantics

`GamePhase` values are:

- `DISCONNECTED`: no live attached process;
- `MENU_OR_TRANSITION`: process and reader are valid but no Board exists;
- `READY`: a coherent Board exists and `game_clock <= 0`;
- `PLAYING`: a coherent unpaused Board exists and `game_clock > 0`;
- `PAUSED`: frozen GameState v1 reports `paused=True`;
- `LEVEL_WON` / `LEVEL_LOST`: only available through an explicitly supplied,
  independently validated terminal-phase provider;
- `UNKNOWN`: reader evidence is invalid or incomplete.

GameState v1 has no authoritative application-screen, loading, seed-selection,
win, or loss field. The runtime therefore does not pretend to separate menus
from loading/results when the Board is absent. Missing-board display changes
are minimally debounced, while `EnvironmentHealth.board_valid` becomes false
immediately so actions still fail closed.

## Focus and action safety

`FocusMode.MANUAL` requires the verified PID-bound window already to be
foreground. Both the runtime gate and the input backend refuse input if focus
is absent or is lost in the final race before input. `FocusMode.AUTO` may ask
Windows to focus the bound HWND. The backend restores a minimized target,
temporarily attaches the caller to the relevant GUI input threads, raises and
activates the window, always detaches the input queues, and briefly polls for
exact foreground confirmation. Failure prevents Controller v1 from being
called. This follows the constraints documented for
[`SetForegroundWindow`](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setforegroundwindow)
and [`AttachThreadInput`](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-attachthreadinput);
it does not synthesize Alt or click another window.

Clicking the monitor naturally makes the monitor foreground. Consequently,
GUI Pause/Resume in MANUAL mode normally returns `FOCUS_REQUIRED`; the operator
must choose AUTO for GUI-driven transitions. The explicit Focus Game control
is itself an operator-authorized focus request and works in either mode.

`PvZRuntime.execute()` performs this sequence under one lock:

1. ensure the process attachment is current;
2. take a fresh reader observation;
3. validate process, reader, Board, window, PLAYING phase, pause, and state age;
4. satisfy and verify the configured focus policy;
5. re-observe and repeat the state gates after the focus operation;
6. dispatch one semantic Controller v1 action;
7. return `RuntimeActionResult` with a typed status and the original
   `ActionResult`, when Controller v1 was reached.

Observer-only mode keeps observation and snapshots available while refusing
all input with `ACTIONS_DISABLED`.

## Pause and resume

`pause()`, `resume()`, and `set_paused(bool)` are idempotent. They read the
current Board first and do nothing when it already has the requested value.
Otherwise the focus policy is satisfied, exactly one Escape press is sent to
the verified foreground window, and read-only observations poll for the
requested `GameState.paused` value within configurable bounds. Failure is
reported as a typed `PauseResult`; Escape is never repeatedly toggled. Escape
uses a `MapVirtualKeyW`-derived scan code with one `KEYEVENTF_SCANCODE` down/up
pair. A virtual-key fallback is deliberately not sent because two accepted
logical presses would cancel each other.

Snapshots retain the latest focus, pause/resume, and input outcomes separately
from reader errors. The monitor presents `CHANGED`, `ALREADY_SET`,
`FOCUS_REQUIRED`, `FOCUS_FAILED`, `INPUT_FAILED`, and `TRANSITION_TIMEOUT`
directly with their detail strings.

## Environment v1 integration

```python
from pvz_env import EpisodeConfig, PvZEnvironment
from pvz_runtime import FocusMode, PvZRuntime, RuntimeConfig

runtime = PvZRuntime(config=RuntimeConfig(focus_mode=FocusMode.MANUAL))
runtime.attach()

environment = PvZEnvironment(
    runtime.reader_adapter(),
    runtime.controller_adapter(),
)
environment.reset(EpisodeConfig("manual-level", active_rows=(True,) * 5 + (False,)))
```

The adapters intentionally add no alternate reward, observation, action, or
episode semantics. Future Phase 4 code can continue consuming Environment v1.

## Phase 4 training lifecycle support

`GameOutcome` is kept separate from GameState v1. `OutcomeEvidence` reads the
supported layout's application scene, application Board result, level-complete
flag, and `Board::mLevelAwardSpawned` at `+0x5624`. A live reward-pending Board
with that field true is WON; a zombies-won scene is LOST; the application
result preserves a terminal outcome after Board teardown. A retained Board
result alone never makes a live Board terminal. These mappings were live
validated on the GOTY 1.2.0.1073 Adventure 1-7 condition.

`TrainingEpisodeSupport` composes outcome, reset verification, and managed
pickups without ML dependencies. Its default restart driver fails closed; the
version-pinned `NormalUiRestartDriver` is an explicit opt-in. `RESET_OK`
additionally requires a
different Board address, expected Adventure level and optional seed types, an
unpaused near-initial clock, observable health, and normally empty plant and
zombie sets.

`ManagedPickupCollector.collect_once()` is synchronous and calls only
`PvZRuntime.execute(COLLECT_PICKUP)` under `run_serialized()`. Pending pickup
identities suppress duplicates; disappearance confirms collection. Metrics are
diagnostics, not reward terms. No background clicking thread exists.

## Concurrency

The runtime does not start autonomous pollers. Its one reentrant lock prevents
reattach, observation, pause, focus, and action operations from racing. The Tk
monitor owns one worker thread so process reads do not block GUI repainting.
Operator commands enter a bounded FIFO and execute exactly once; automatic
refresh is coalesced rather than queued and only starts while no command is
pending or running. Thus a refresh can delay a button command briefly but can
never discard it. Closing stops new work, clears commands that have not begun,
and schedules runtime detach after the active operation finishes.
