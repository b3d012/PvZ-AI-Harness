"""Monitor scheduling/presentation tests that never open a Tk window."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller.windows_input import GameWindowInfo
from pvz_runtime import (
    EnvironmentHealth, FocusMode, GamePhase, GameStateSummary, PauseResult,
    PauseStatus, ProcessIdentity, RuntimeSnapshot, SessionStatus,
)
from pvz_runtime.monitor import MonitorJobQueue, MonitorJobResult, MonitorViewModel, RuntimeMonitor


def snapshot() -> RuntimeSnapshot:
    session = SessionStatus(
        True, True, ProcessIdentity(42, "PlantsVsZombies.exe"),
        GameWindowInfo(100, 42, "Plants vs. Zombies", False, 800, 600),
        True, True, "1.2.0.1073", False, 1, None, 999,
    )
    health = EnvironmentHealth(
        True, True, True, True, True, True, True, GamePhase.PLAYING,
        12.4, FocusMode.MANUAL, False, (),
    )
    state = GameStateSummary(1, 0, 100, False, 150, 2, 10, 4, 3, 6, 1, 5, 2)
    return RuntimeSnapshot(
        123.0, session, health, GamePhase.PLAYING, state, "plant:ok", None,
        "focused:foreground_confirmed", "changed:state_verified", "escape_sent",
    )


def wait_for_result(queue: MonitorJobQueue, timeout: float = 1.0) -> MonitorJobResult:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = queue.poll()
        if result is not None:
            return result
        time.sleep(0.001)
    raise AssertionError("monitor job did not complete")


class FakeRuntime:
    def __init__(self):
        self.pause_calls = 0
        self.resume_calls = 0
        self.close_calls = 0
        self.closed = Event()

    def pause(self):
        self.pause_calls += 1
        return PauseResult(PauseStatus.CHANGED, True, True, "state_verified")

    def resume(self):
        self.resume_calls += 1
        return PauseResult(PauseStatus.CHANGED, False, False, "state_verified")

    def refresh(self):
        return snapshot()

    def snapshot(self, *, refresh=True):
        return snapshot()

    def close(self):
        self.close_calls += 1
        self.closed.set()


class FakeText:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeRoot:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class MonitorViewModelTests(unittest.TestCase):
    def test_snapshot_formats_operator_and_runtime_result_fields(self):
        completed = MonitorJobResult(snapshot(), "Pause", "CHANGED", "state_verified")
        model = MonitorViewModel.from_snapshot(snapshot(), completed)
        text = RuntimeMonitor._format(model)
        for expected in (
            "Connected", "42", "Plants vs. Zombies", "100", "999", "PLAYING",
            "150", "4", "3", "1", "5", "12 ms", "Pause", "CHANGED",
            "state_verified", "escape_sent", "plant:ok",
        ):
            self.assertIn(expected, text)

    def test_pause_result_presentation_treats_expected_status_normally(self):
        status, detail = RuntimeMonitor._describe_operation(
            "Pause", PauseResult(PauseStatus.ALREADY_SET, True, True, "already_set")
        )
        self.assertEqual(status, "ALREADY_SET")
        self.assertEqual(detail, "already_set")


class MonitorSchedulingTests(unittest.TestCase):
    def make_monitor(self):
        runtime = FakeRuntime()
        monitor = RuntimeMonitor.__new__(RuntimeMonitor)
        monitor.runtime = runtime
        monitor._jobs = MonitorJobQueue(ThreadPoolExecutor(max_workers=1))
        monitor._closing = False
        monitor._text = FakeText()
        monitor.root = FakeRoot()
        return monitor, runtime

    def test_pause_and_resume_pressed_during_refresh_execute_once_each(self):
        monitor, runtime = self.make_monitor()
        refresh_started = Event()
        release_refresh = Event()

        def blocked_refresh():
            refresh_started.set()
            release_refresh.wait(1.0)
            return MonitorJobResult(snapshot())

        self.assertTrue(monitor._jobs.request_refresh(blocked_refresh))
        self.assertTrue(refresh_started.wait(1.0))
        monitor._pause()
        monitor._resume()
        self.assertEqual(monitor._jobs.pending_commands, 2)
        release_refresh.set()

        self.assertIsNone(wait_for_result(monitor._jobs).operation)
        self.assertEqual(wait_for_result(monitor._jobs).operation, "Pause")
        self.assertEqual(wait_for_result(monitor._jobs).operation, "Resume")
        self.assertEqual(runtime.pause_calls, 1)
        self.assertEqual(runtime.resume_calls, 1)
        monitor.close()
        self.assertTrue(runtime.closed.wait(1.0))

    def test_automatic_refresh_is_coalesced_instead_of_queued(self):
        queue = MonitorJobQueue(ThreadPoolExecutor(max_workers=1))
        started = Event()
        release = Event()

        def blocked_refresh():
            started.set()
            release.wait(1.0)
            return MonitorJobResult(snapshot())

        self.assertTrue(queue.request_refresh(blocked_refresh))
        self.assertTrue(started.wait(1.0))
        for _ in range(100):
            self.assertFalse(queue.request_refresh(blocked_refresh))
        self.assertEqual(queue.pending_commands, 0)
        release.set()
        wait_for_result(queue)
        closed = Event()
        queue.close(closed.set)
        self.assertTrue(closed.wait(1.0))

    def test_close_rejects_new_commands_and_finalizes_runtime(self):
        monitor, runtime = self.make_monitor()
        monitor.close()
        self.assertTrue(runtime.closed.wait(1.0))
        self.assertEqual(runtime.close_calls, 1)
        self.assertTrue(monitor.root.destroyed)
        self.assertFalse(
            monitor._jobs.submit_command("Pause", lambda: MonitorJobResult(snapshot()))
        )

    def test_close_waits_for_active_refresh_before_runtime_finalizer(self):
        queue = MonitorJobQueue(ThreadPoolExecutor(max_workers=1))
        started = Event()
        release = Event()
        finalized = Event()

        def blocked_refresh():
            started.set()
            release.wait(1.0)
            return MonitorJobResult(snapshot())

        self.assertTrue(queue.request_refresh(blocked_refresh))
        self.assertTrue(started.wait(1.0))
        queue.close(finalized.set)
        self.assertFalse(finalized.wait(0.01))
        release.set()
        self.assertTrue(finalized.wait(1.0))


if __name__ == "__main__":
    unittest.main()
