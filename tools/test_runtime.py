"""Offline runtime/session/phase/watchdog tests; no desktop input is issued."""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import ActionResult
from pvz_controller.windows_input import GameWindowInfo, GameWindowUnavailable, InputFailed
from pvz_runtime import (
    FocusMode, GamePhase, GamePhaseDetector, PauseStatus, PhaseEvidence,
    ProcessIdentity, PvZRuntime, PvZSession, RuntimeAction, RuntimeActionStatus,
    RuntimeConfig,
)


def game_state(*, paused=False, game_clock=100):
    return SimpleNamespace(
        sun=100, game_clock=game_clock, scene=0, adventure_level=1, paused=paused,
        wave=SimpleNamespace(spawned_waves=1, total_waves=10), plants=[], zombies=[],
        seeds=[], mowers=[], pickups=[], projectiles=[], grid_items=[],
    )


class FakeProcessDiscovery:
    def __init__(self, process=None):
        self.process = process
        self.alive = set(() if process is None else (process.process_id,))

    def find_process(self):
        return self.process

    def is_alive(self, process_id):
        return process_id in self.alive


class MutableReader:
    def __init__(self, current=None):
        self.current = current
        self.error = None
        self.calls = 0

    def read(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.current


class FakeMemory:
    def __init__(self, process_id, reader):
        self.process_id = process_id
        self.reader = reader
        self.closed = False

    def close(self):
        self.closed = True


class FakeWindowBackend:
    def __init__(self, *, process_id=10, present=True, focused=True, focus_succeeds=True):
        self.process_id = process_id
        self.present = present
        self.focused = focused
        self.focus_succeeds = focus_succeeds
        self.expected_process_id = None
        self.auto_focus = True
        self.escape_calls = 0
        self.on_escape = None

    def bind_process(self, process_id):
        self.expected_process_id = process_id

    def set_auto_focus(self, enabled):
        self.auto_focus = enabled

    def get_window_info(self):
        if not self.present:
            raise GameWindowUnavailable("missing")
        return GameWindowInfo(100, self.process_id, "Plants vs. Zombies", False, 800, 600)

    def is_foreground(self):
        if not self.present:
            raise GameWindowUnavailable("missing")
        return self.focused

    def focus_game(self):
        if not self.present:
            raise GameWindowUnavailable("missing")
        if self.focus_succeeds:
            self.focused = True
        return self.focused

    def press_escape(self):
        if not self.present:
            raise GameWindowUnavailable("missing")
        if not self.focused and not self.auto_focus:
            raise InputFailed("not foreground")
        if not self.focused and not self.focus_game():
            raise InputFailed("focus failed")
        self.escape_calls += 1
        if self.on_escape:
            self.on_escape()


class FakeController:
    def __init__(self, result=None):
        self.result = result or ActionResult(True, None, "clicks_issued")
        self.calls = []

    def plant(self, state, seed_slot, row, col):
        self.calls.append(("plant", state, seed_slot, row, col))
        return self.result

    def shovel(self, state, row, col):
        self.calls.append(("shovel", state, row, col))
        return self.result

    def collect_pickup(self, state, pickup_slot):
        self.calls.append(("collect", state, pickup_slot))
        return self.result


class MutableClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class SessionTests(unittest.TestCase):
    def make_session(self, process=None, *, present=True, reader=None):
        process = process or ProcessIdentity(10, "PlantsVsZombies.exe", "C:/Games/PlantsVsZombies.exe")
        discovery = FakeProcessDiscovery(process)
        backend = FakeWindowBackend(process_id=process.process_id, present=present)
        reader = reader or MutableReader(game_state())
        memories = []

        def memory_factory(process_id):
            memory = FakeMemory(process_id, reader)
            memories.append(memory)
            return memory

        session = PvZSession(
            process_discovery=discovery, memory_factory=memory_factory,
            reader_factory=lambda memory: memory.reader, input_backend=backend,
        )
        return session, discovery, backend, memories

    def test_process_not_found(self):
        discovery = FakeProcessDiscovery(None)
        session = PvZSession(
            process_discovery=discovery, memory_factory=lambda _: self.fail("must not attach"),
            input_backend=FakeWindowBackend(present=False),
        )
        status = session.attach()
        self.assertFalse(status.attached)
        self.assertEqual(status.last_error, "process_not_found")

    def test_process_reader_and_matching_window_attach_and_detach(self):
        session, _, backend, memories = self.make_session()
        status = session.attach()
        self.assertTrue(status.attached)
        self.assertTrue(status.window_valid)
        self.assertEqual(status.window.process_id, status.process.process_id)
        self.assertEqual(backend.expected_process_id, 10)
        self.assertFalse(status.version_verified)
        self.assertNotIn("executable", status.to_dict()["process"])
        detached = session.detach()
        self.assertFalse(detached.attached)
        self.assertTrue(memories[0].closed)
        self.assertIsNone(backend.expected_process_id)

    def test_window_missing_still_allows_reader_observation(self):
        session, _, _, _ = self.make_session(present=False)
        status = session.attach()
        self.assertTrue(status.attached)
        self.assertFalse(status.window_valid)
        self.assertTrue(session.read().reader_valid)

    def test_process_restart_replaces_stale_attachment(self):
        session, discovery, backend, memories = self.make_session()
        first = session.attach()
        discovery.alive.clear()
        discovery.process = ProcessIdentity(20, "PlantsVsZombies.exe")
        discovery.alive.add(20)
        backend.process_id = 20
        second = session.ensure_attached()
        self.assertEqual(first.generation, 1)
        self.assertEqual(second.generation, 2)
        self.assertEqual(second.process.process_id, 20)
        self.assertTrue(memories[0].closed)
        self.assertEqual(backend.expected_process_id, 20)

    def test_reader_failure_invalidates_stale_attachment(self):
        reader = MutableReader(game_state())
        session, _, _, memories = self.make_session(reader=reader)
        session.attach()
        reader.error = RuntimeError("stale handle")
        result = session.read()
        self.assertFalse(result.reader_valid)
        self.assertIn("reader_failed", result.error)
        self.assertTrue(memories[0].closed)
        self.assertFalse(session.status().attached)


class PhaseDetectorTests(unittest.TestCase):
    def test_supported_phase_evidence(self):
        cases = (
            (PhaseEvidence(False, False, None), GamePhase.DISCONNECTED),
            (PhaseEvidence(True, False, None), GamePhase.UNKNOWN),
            (PhaseEvidence(True, True, None), GamePhase.MENU_OR_TRANSITION),
            (PhaseEvidence(True, True, game_state(game_clock=0)), GamePhase.READY),
            (PhaseEvidence(True, True, game_state()), GamePhase.PLAYING),
            (PhaseEvidence(True, True, game_state(paused=True)), GamePhase.PAUSED),
            (PhaseEvidence(True, True, game_state(), GamePhase.LEVEL_WON), GamePhase.LEVEL_WON),
            (PhaseEvidence(True, True, game_state(), GamePhase.LEVEL_LOST), GamePhase.LEVEL_LOST),
        )
        for evidence, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(GamePhaseDetector().detect(evidence), expected)

    def test_ambiguous_state_is_unknown_and_missing_board_is_debounced(self):
        detector = GamePhaseDetector(transition_confirmations=2)
        self.assertEqual(detector.detect(PhaseEvidence(True, True, object())), GamePhase.UNKNOWN)
        self.assertEqual(detector.detect(PhaseEvidence(True, True, game_state())), GamePhase.PLAYING)
        self.assertEqual(detector.detect(PhaseEvidence(True, True, None)), GamePhase.PLAYING)
        self.assertEqual(detector.detect(PhaseEvidence(True, True, None)), GamePhase.MENU_OR_TRANSITION)


class RuntimeTests(unittest.TestCase):
    def make_runtime(
        self, *, mode=FocusMode.MANUAL, focused=True, focus_succeeds=True,
        present=True, current=None, observer_only=False, controller=None,
        pause_timeout=0.1, terminal_phase_provider=None,
    ):
        process = ProcessIdentity(10, "PlantsVsZombies.exe")
        discovery = FakeProcessDiscovery(process)
        self.reader = MutableReader(game_state() if current is None else current)
        self.backend = FakeWindowBackend(
            process_id=10, present=present, focused=focused, focus_succeeds=focus_succeeds,
        )
        session = PvZSession(
            process_discovery=discovery,
            memory_factory=lambda pid: FakeMemory(pid, self.reader),
            reader_factory=lambda memory: memory.reader,
            input_backend=self.backend,
        )
        self.controller = controller or FakeController()
        self.clock = MutableClock()
        runtime = PvZRuntime(
            session, self.controller,
            config=RuntimeConfig(
                focus_mode=mode, observer_only=observer_only,
                max_state_age_seconds=0.5, pause_timeout_seconds=pause_timeout,
                pause_poll_interval_seconds=0.05,
            ),
            terminal_phase_provider=terminal_phase_provider,
            clock=self.clock, wall_clock=lambda: 123.0, sleeper=self.clock.sleep,
        )
        runtime.attach()
        return runtime

    def test_health_distinguishes_observation_and_action_safety(self):
        runtime = self.make_runtime(focused=False)
        runtime.observe()
        health = runtime.health
        self.assertTrue(health.can_observe)
        self.assertFalse(health.can_act)
        self.assertIn("focus_inactive", health.reasons)
        self.clock.value = 1.0
        self.assertIn("state_stale", runtime.health.reasons)

    def test_manual_focus_allows_focused_and_refuses_unfocused(self):
        focused = self.make_runtime(focused=True)
        accepted = focused.execute(RuntimeAction.plant(0, 2, 4))
        self.assertEqual(accepted.status, RuntimeActionStatus.ACTION_OK)
        self.assertEqual(len(self.controller.calls), 1)

        unfocused = self.make_runtime(focused=False)
        refused = unfocused.execute(RuntimeAction.plant(0, 2, 4))
        self.assertEqual(refused.status, RuntimeActionStatus.FOCUS_REQUIRED)
        self.assertEqual(self.controller.calls, [])

    def test_auto_focus_restores_and_verifies_or_refuses(self):
        runtime = self.make_runtime(mode=FocusMode.AUTO, focused=False, focus_succeeds=True)
        result = runtime.execute(RuntimeAction.shovel(2, 4))
        self.assertEqual(result.status, RuntimeActionStatus.ACTION_OK)
        self.assertTrue(self.backend.focused)

        failed = self.make_runtime(mode=FocusMode.AUTO, focused=False, focus_succeeds=False)
        result = failed.execute(RuntimeAction.shovel(2, 4))
        self.assertEqual(result.status, RuntimeActionStatus.FOCUS_FAILED)
        self.assertEqual(self.controller.calls, [])

    def test_watchdog_refuses_missing_window_board_paused_and_observer_only(self):
        cases = (
            ({"present": False}, RuntimeActionStatus.WINDOW_INVALID),
            ({"current": None}, RuntimeActionStatus.BOARD_INVALID),
            ({"current": game_state(game_clock=0)}, RuntimeActionStatus.NOT_IN_PLAYABLE_PHASE),
            ({"current": game_state(paused=True)}, RuntimeActionStatus.GAME_PAUSED),
            ({"observer_only": True}, RuntimeActionStatus.ACTIONS_DISABLED),
        )
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                runtime = self.make_runtime(**kwargs)
                # ``None`` is the helper's default state, set it explicitly after construction.
                if kwargs.get("current", "sentinel") is None:
                    self.reader.current = None
                result = runtime.execute(RuntimeAction.collect_pickup(0))
                self.assertEqual(result.status, expected)
                self.assertEqual(self.controller.calls, [])

    def test_controller_rejection_is_preserved(self):
        controller = FakeController(ActionResult(False, False, "placement_invalid:occupied"))
        result = self.make_runtime(controller=controller).execute(RuntimeAction.plant(0, 2, 4))
        self.assertEqual(result.status, RuntimeActionStatus.CONTROLLER_REJECTED)
        self.assertEqual(result.controller_result.reason, "placement_invalid:occupied")

    def test_pause_resume_are_idempotent_and_verified(self):
        runtime = self.make_runtime()

        def toggle():
            self.reader.current.paused = not self.reader.current.paused

        self.backend.on_escape = toggle
        paused = runtime.pause()
        paused_again = runtime.pause()
        resumed = runtime.resume()
        resumed_again = runtime.resume()
        self.assertEqual(paused.status, PauseStatus.CHANGED)
        self.assertEqual(paused_again.status, PauseStatus.ALREADY_SET)
        self.assertEqual(resumed.status, PauseStatus.CHANGED)
        self.assertEqual(resumed_again.status, PauseStatus.ALREADY_SET)
        self.assertEqual(self.backend.escape_calls, 2)

    def test_pause_focus_and_transition_failures_are_explicit(self):
        manual = self.make_runtime(focused=False)
        self.assertEqual(manual.pause().status, PauseStatus.FOCUS_REQUIRED)
        self.assertEqual(self.backend.escape_calls, 0)

        auto = self.make_runtime(mode=FocusMode.AUTO, focused=False, focus_succeeds=False)
        self.assertEqual(auto.pause().status, PauseStatus.FOCUS_FAILED)

        timeout = self.make_runtime(pause_timeout=0.1)
        self.assertEqual(timeout.pause().status, PauseStatus.TRANSITION_TIMEOUT)
        self.assertEqual(self.backend.escape_calls, 1)

        unavailable = self.make_runtime()
        self.reader.current = None
        self.assertEqual(unavailable.pause().status, PauseStatus.STATE_UNAVAILABLE)

    def test_snapshot_is_compact_serializable_and_adapters_gate_actions(self):
        runtime = self.make_runtime()
        snapshot = runtime.snapshot()
        document = snapshot.to_dict()
        self.assertEqual(document["timestamp"], 123.0)
        self.assertEqual(document["game_state"]["sun"], 100)
        self.assertNotIn("plants_data", document["game_state"])
        self.assertIs(runtime.reader_adapter().read(), self.reader.current)
        result = runtime.controller_adapter().plant(self.reader.current, 0, 2, 4)
        self.assertTrue(result.attempted)

    def test_validated_terminal_hint_is_exposed_without_changing_game_state(self):
        runtime = self.make_runtime(terminal_phase_provider=lambda _state: GamePhase.LEVEL_WON)
        runtime.observe()
        self.assertTrue(runtime.is_terminal())
        self.assertEqual(runtime.phase, GamePhase.LEVEL_WON)


if __name__ == "__main__":
    unittest.main()
