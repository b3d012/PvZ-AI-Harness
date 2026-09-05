"""Offline Phase 4 lifecycle tests; no process attachment or input."""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_reader.outcome import BoardResult, GameOutcome, GameScene, OutcomeEvidence, read_outcome
from pvz_reader.versions import OFFSETS, PVZ_VERSION
from pvz_controller.windows_input import InputFailed
from pvz_runtime import (
    ManagedPickupCollector, NormalUiRestartDriver, ResetControlResult, ResetExpectation, ResetStatus,
    TrainingEpisodeSupport, UnsupportedRestartDriver,
)


class AddressMemory:
    def __init__(self, *, lawn=0x1000, board=0x2000, scene=3, result=0, complete=False,
                 award_spawned=False, fade_out_counter=-1, next_survival_stage_counter=0,
                 error=None):
        self.lawn, self.board, self.scene = lawn, board, scene
        self.result, self.complete, self.error = result, complete, error
        self.award_spawned = award_spawned
        self.fade_out_counter = fade_out_counter
        self.next_survival_stage_counter = next_survival_stage_counter
        self.o = OFFSETS[PVZ_VERSION]

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def read_pointer(self, address):
        self._maybe_fail()
        if address == self.o["lawn"]:
            return self.lawn
        if address == self.lawn + self.o["board"]:
            return self.board
        raise AssertionError(hex(address))

    def read_int(self, address):
        self._maybe_fail()
        if address == self.lawn + self.o["game_scene"]:
            return self.scene
        if address == self.lawn + self.o["board_result"]:
            return self.result
        if address == self.board + self.o["board_fade_out_counter"]:
            return self.fade_out_counter
        if address == self.board + self.o["next_survival_stage_counter"]:
            return self.next_survival_stage_counter
        raise AssertionError(hex(address))

    def read_bool(self, address):
        self._maybe_fail()
        if address == self.board + self.o["level_complete"]:
            return self.complete
        if address == self.board + self.o["level_award_spawned"]:
            return self.award_spawned
        raise AssertionError(hex(address))


class OutcomeTests(unittest.TestCase):
    def test_running_ignores_stale_application_result(self):
        evidence = read_outcome(AddressMemory(result=BoardResult.WON))
        self.assertEqual(evidence.outcome, GameOutcome.RUNNING)
        self.assertEqual(evidence.reason, "live_board_playing")

    def test_won_from_live_board_completion(self):
        evidence = read_outcome(AddressMemory(complete=True))
        self.assertEqual(evidence.outcome, GameOutcome.WON)

    def test_reward_pending_live_board_is_won(self):
        evidence = read_outcome(AddressMemory(result=BoardResult.WON, award_spawned=True))
        self.assertEqual(evidence.outcome, GameOutcome.WON)
        self.assertEqual(evidence.reason, "board_level_award_spawned")

    def test_retained_win_result_on_fresh_running_board_is_not_won(self):
        evidence = read_outcome(AddressMemory(result=BoardResult.WON, award_spawned=False))
        self.assertEqual(evidence.outcome, GameOutcome.RUNNING)

    def test_lost_from_zombies_won_scene(self):
        evidence = read_outcome(AddressMemory(scene=GameScene.ZOMBIES_WON))
        self.assertEqual(evidence.outcome, GameOutcome.LOST)

    def test_terminal_result_survives_missing_board(self):
        won = read_outcome(AddressMemory(board=0, scene=GameScene.AWARD, result=BoardResult.WON))
        lost = read_outcome(AddressMemory(board=0, scene=GameScene.ZOMBIES_WON, result=BoardResult.LOST))
        self.assertEqual(won.outcome, GameOutcome.WON)
        self.assertEqual(lost.outcome, GameOutcome.LOST)

    def test_missing_lawn_and_read_failure_are_unknown(self):
        self.assertEqual(read_outcome(AddressMemory(lawn=0)).outcome, GameOutcome.UNKNOWN)
        failed = read_outcome(AddressMemory(error=OSError("gone")))
        self.assertEqual(failed.outcome, GameOutcome.UNKNOWN)
        self.assertIn("OSError", failed.error)

    def test_nonterminal_transition_is_unknown(self):
        evidence = read_outcome(AddressMemory(board=0, scene=GameScene.MENU, result=BoardResult.NONE))
        self.assertEqual(evidence.outcome, GameOutcome.UNKNOWN)


def state(*, level=5, clock=5, pickups=(), plants=(), zombies=(), seeds=(0, 1)):
    return SimpleNamespace(
        adventure_level=level, game_clock=clock, paused=False,
        pickups=list(pickups), plants=list(plants), zombies=list(zombies),
        seeds=[SimpleNamespace(type_id=value) for value in seeds],
    )


def pickup(slot=0, type_id=4, x=100.0, y=200.0):
    return SimpleNamespace(
        slot=slot, type_id=type_id, x=x, y=y, collectible=True,
        is_sun=type_id in (4, 5, 6),
    )


class PickupRuntime:
    def __init__(self, states, *, accepted=True, can_act=True):
        self.states = list(states)
        self.index = 0
        self.health = SimpleNamespace(can_act=can_act)
        self.accepted = accepted
        self.actions = []
        self.serialized_calls = 0

    def run_serialized(self, operation):
        self.serialized_calls += 1
        return operation(self)

    def observe(self):
        value = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return value

    def outcome(self):
        return OutcomeEvidence(GameOutcome.RUNNING, "test", board_address=0x2000)

    def execute(self, action):
        self.actions.append(action)
        return SimpleNamespace(accepted=self.accepted)


class PickupTests(unittest.TestCase):
    def test_pickup_is_serialized_deduplicated_and_confirmed_on_disappearance(self):
        item = pickup()
        runtime = PickupRuntime([state(pickups=[item]), state(pickups=[item]), state(pickups=[])])
        collector = ManagedPickupCollector(runtime)
        collector.collect_once()
        collector.collect_once()
        metrics = collector.collect_once()
        self.assertEqual((metrics.attempts, metrics.successes, metrics.failures), (1, 1, 0))
        self.assertEqual((metrics.pickups_collected, metrics.sun_pickups_collected), (1, 1))
        self.assertEqual(runtime.serialized_calls, 3)
        self.assertEqual(len(runtime.actions), 1)

    def test_failure_is_recorded_and_unhealthy_runtime_does_not_act(self):
        item = pickup()
        failed_runtime = PickupRuntime([state(pickups=[item]), state(pickups=[item])], accepted=False)
        collector = ManagedPickupCollector(failed_runtime)
        metrics = collector.collect_once()
        collector.collect_once()
        self.assertEqual((metrics.attempts, metrics.failures), (1, 1))
        unhealthy = PickupRuntime([state(pickups=[pickup()])], can_act=False)
        ManagedPickupCollector(unhealthy).collect_once()
        self.assertEqual(unhealthy.actions, [])

    def test_shutdown_disables_collection(self):
        runtime = PickupRuntime([state(pickups=[pickup()])])
        collector = ManagedPickupCollector(runtime)
        collector.shutdown()
        collector.collect_once()
        self.assertEqual(runtime.actions, [])


class Driver:
    def __init__(self, requested=True):
        self.requested = requested

    def request_restart(self, runtime):
        return ResetControlResult(self.requested, "test_driver")


class ResetRuntime:
    def __init__(self, states, boards, *, process_alive=True):
        self.states = list(states)
        self.boards = list(boards)
        self.index = -1
        self.process_alive = process_alive

    def run_serialized(self, operation):
        return operation(self)

    def observe(self):
        self.index = min(self.index + 1, len(self.states) - 1)
        return self.states[self.index]

    def outcome(self):
        board = self.boards[max(0, self.index)]
        return OutcomeEvidence(GameOutcome.RUNNING, "test", board_address=board)

    @property
    def health(self):
        return SimpleNamespace(can_observe=self.states[max(0, self.index)] is not None,
                               process_alive=self.process_alive)


class ResetTests(unittest.TestCase):
    def support(self, runtime, driver=None, timeout=0.1):
        return TrainingEpisodeSupport(
            runtime, restart_driver=driver or Driver(), reset_timeout_seconds=timeout,
            reset_poll_interval_seconds=0.05, sleeper=lambda _: None,
        )

    def test_verified_same_level_fresh_board(self):
        runtime = ResetRuntime([state(clock=500, plants=[1]), state(clock=3)], [10, 20])
        result = self.support(runtime).reset_current_level(ResetExpectation(5, (0, 1)))
        self.assertEqual(result.status, ResetStatus.RESET_OK)
        self.assertEqual(result.board_address, 20)

    def test_wrong_level_and_seed_bank_mismatch_fail_closed(self):
        wrong = ResetRuntime([state(clock=500), state(level=6)], [10, 20])
        result = self.support(wrong).reset_current_level(ResetExpectation(5))
        self.assertEqual(result.status, ResetStatus.WRONG_LEVEL)
        seeds = ResetRuntime([state(clock=500), state(seeds=(2, 3))], [10, 20])
        result = self.support(seeds).reset_current_level(ResetExpectation(5, (0, 1)))
        self.assertEqual(result.status, ResetStatus.SEED_BANK_MISMATCH)

    def test_stale_board_times_out_and_unsupported_driver_fails(self):
        runtime = ResetRuntime([state(clock=500), state(clock=0)], [10, 10])
        result = self.support(runtime, timeout=0.0).reset_current_level(ResetExpectation(5))
        self.assertEqual(result.status, ResetStatus.BOARD_NOT_REPLACED)
        runtime = ResetRuntime([state(clock=500)], [10])
        support = self.support(runtime, UnsupportedRestartDriver())
        result = support.reset_current_level(ResetExpectation(5))
        self.assertEqual(result.status, ResetStatus.RESET_CONTROL_FAILED)

    def test_process_failure_and_stale_entities_are_not_success(self):
        gone = ResetRuntime([state(clock=500), state(clock=0)], [10, 20], process_alive=False)
        self.assertEqual(
            self.support(gone).reset_current_level(ResetExpectation(5)).status,
            ResetStatus.NOT_ATTACHED,
        )
        stale = ResetRuntime([state(clock=500), state(clock=0, zombies=[1])], [10, 20])
        self.assertEqual(
            self.support(stale).reset_current_level(ResetExpectation(5)).status,
            ResetStatus.STALE_ENTITIES,
        )


class RestartInput:
    def __init__(self, runtime, *, fail=None, opens_menu=True):
        self.runtime, self.fail, self.opens_menu, self.events = runtime, fail, opens_menu, []

    def get_client_area(self):
        return SimpleNamespace(width=800, height=600)

    def left_click(self, x, y, *, move_settle_delay=0.0):
        self.events.append(("click", x, y, move_settle_delay))
        if self.fail == "click":
            raise InputFailed("input refused")
        if self.opens_menu and (x, y) == NormalUiRestartDriver.MENU_BUTTON:
            self.runtime.paused = True

    def press_enter(self):
        self.events.append(("enter",))
        if self.fail == "enter":
            raise InputFailed("input refused")
        if self.runtime.paused and len(self.events) == 1:
            self.runtime.paused = False


class UiDriverRuntime:
    def __init__(self, outcome=GameOutcome.RUNNING, *, paused=False, fail=None, opens_menu=True):
        self.outcome_value, self.paused = outcome, paused
        self.config = SimpleNamespace(observer_only=False)
        self.health = SimpleNamespace(process_alive=True, window_valid=True)
        self.session = SimpleNamespace(input_backend=RestartInput(self, fail=fail, opens_menu=opens_menu))

    def observe(self):
        return SimpleNamespace(
            adventure_level=5, game_clock=100, paused=self.paused, plants=[], zombies=[], seeds=[]
        )

    def outcome(self):
        return OutcomeEvidence(self.outcome_value, "test", board_address=0x2000)


class NormalUiRestartDriverTests(unittest.TestCase):
    def driver(self):
        return NormalUiRestartDriver(transition_timeout_seconds=0.0, sleeper=lambda _: None)

    def test_playing_uses_one_menu_restart_sequence(self):
        runtime = UiDriverRuntime()
        result = self.driver().request_restart(runtime)
        self.assertTrue(result.requested)
        self.assertEqual(runtime.session.input_backend.events, [
            ("click", 739, 13, 0.10), ("click", 400, 358, 0.10), ("enter",),
        ])

    def test_externally_paused_state_is_refused_without_any_input(self):
        runtime = UiDriverRuntime(paused=True)
        result = NormalUiRestartDriver(sleeper=lambda _: None).request_restart(runtime)
        self.assertFalse(result.requested)
        self.assertEqual(result.reason, "paused_menu_not_verified")
        self.assertEqual(runtime.session.input_backend.events, [])

    def test_explicitly_attested_pause_menu_restarts_without_menu_click(self):
        runtime = UiDriverRuntime(paused=True)
        result = NormalUiRestartDriver(sleeper=lambda _: None, known_pause_menu=True).request_restart(runtime)
        self.assertTrue(result.requested)
        self.assertEqual(runtime.session.input_backend.events, [
            ("click", 400, 358, 0.10), ("enter",),
        ])

    def test_loss_uses_settled_try_again_click_and_live_win_uses_menu_restart(self):
        lost = UiDriverRuntime(GameOutcome.LOST)
        self.assertTrue(self.driver().request_restart(lost).requested)
        self.assertEqual(lost.session.input_backend.events, [("click", 384, 369, 0.10)])
        won = UiDriverRuntime(GameOutcome.WON)
        self.assertTrue(self.driver().request_restart(won).requested)
        self.assertEqual(won.session.input_backend.events, [
            ("click", 739, 13, 0.10), ("click", 400, 358, 0.10), ("enter",),
        ])

    def test_torn_down_win_refuses_without_input(self):
        runtime = UiDriverRuntime(GameOutcome.WON)
        runtime.outcome = lambda: OutcomeEvidence(GameOutcome.WON, "test", board_address=None)
        result = self.driver().request_restart(runtime)
        self.assertFalse(result.requested)
        self.assertEqual(result.reason, "won_board_unavailable")
        self.assertEqual(runtime.session.input_backend.events, [])

    def test_loss_click_failure_refuses_without_enter(self):
        runtime = UiDriverRuntime(GameOutcome.LOST, fail="click")
        result = self.driver().request_restart(runtime)
        self.assertFalse(result.requested)
        self.assertIn("loss_retry_input_failed", result.reason)
        self.assertEqual(runtime.session.input_backend.events, [("click", 384, 369, 0.10)])

    def test_bad_geometry_and_input_failure_refuse_without_restart(self):
        runtime = UiDriverRuntime(fail="click")
        result = self.driver().request_restart(runtime)
        self.assertFalse(result.requested)
        self.assertIn("menu_input_failed", result.reason)
        runtime = UiDriverRuntime()
        runtime.session.input_backend.get_client_area = lambda: SimpleNamespace(width=801, height=600)
        self.assertFalse(self.driver().request_restart(runtime).requested)

    def test_no_restart_click_or_confirmation_after_unverified_menu_transition(self):
        runtime = UiDriverRuntime(opens_menu=False)
        result = self.driver().request_restart(runtime)
        self.assertFalse(result.requested)
        self.assertEqual(result.reason, "menu_transition_not_verified")
        self.assertEqual(runtime.session.input_backend.events, [("click", 739, 13, 0.10)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
