"""Offline Phase 3.4 transition record and JSONL persistence checks."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import ActionResult
from pvz_env import (
    ACTION_COUNT,
    TRANSITION_SCHEMA_VERSION,
    ActionType,
    ArrayPayload,
    JsonlTransitionSink,
    EpisodeConfig,
    PvZEnvironment,
    ReconciliationStatus,
    SemanticAction,
    StepRejectionReason,
    TransitionLogFormatError,
    TransitionLoggingError,
    TransitionRecord,
    encode_action,
    read_transition_jsonl,
)
from pvz_reader.game_state import GameState, PlantState, SeedPacketState, WaveState


def game_state(*, sun=250, paused=False, plants=None, seeds=None):
    return GameState(
        sun=sun, game_clock=100, scene=0, adventure_level=1, paused=paused,
        plant_capacity=10, zombie_capacity=10,
        wave=WaveState(10, 0, 0, 100, 100, 0.0, 0, False, 0, 0),
        plants=plants or [], zombies=[],
        seeds=seeds if seeds is not None else [SeedPacketState(0, 0, "Peashooter", None, 100, 100, 100, 1.0, True, False, False, True, True, 0)],
        mowers=[], pickups=[], projectiles=[], grid_items=[],
    )


def plant():
    return PlantState(0, 0, "Peashooter", 2, 4, 320, 295, 0, 300, 300, False, 0)


class FakeReader:
    def __init__(self, *states):
        self.states = list(states)

    def read(self):
        return self.states.pop(0) if self.states else None


class FakeController:
    def __init__(self, result=ActionResult(True, None, "clicks_issued")):
        self.result = result
        self.calls = []

    def plant(self, state, seed_slot, row, col):
        self.calls.append((state, seed_slot, row, col))
        return self.result


class CaptureSink:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)


class FailingSink:
    def write(self, record):
        raise OSError("disk full")


class TransitionLoggingTests(unittest.TestCase):
    def make_env(self, *states, sink=None, episode_id="episode-a", controller=None):
        env = PvZEnvironment(
            FakeReader(states[0], *states), controller or FakeController(),
            transition_sink=sink, sleeper=lambda interval: None, clock=lambda: 1.0,
        )
        env.reset(EpisodeConfig(episode_id))
        return env

    @staticmethod
    def plant_index():
        return encode_action(SemanticAction(ActionType.PLANT, 0, 2, 4))

    def test_schema_and_array_payload_round_trip(self):
        array = np.array([1.0, 2.5], dtype=np.float32)
        payload = ArrayPayload.from_array(array)

        self.assertEqual(TRANSITION_SCHEMA_VERSION, 2)
        self.assertEqual(payload.dtype, "float32")
        self.assertTrue(np.array_equal(payload.to_array(), array))
        self.assertTrue(np.array_equal(ArrayPayload.from_dict(payload.to_dict()).to_array(), array))

    def test_wait_record_contains_before_after_and_one_emission(self):
        sink = CaptureSink()
        before, after = game_state(sun=100), game_state(sun=200)
        result = self.make_env(before, after, sink=sink).step(0)

        self.assertEqual(len(sink.records), 1)
        record = sink.records[0]
        self.assertEqual(record.episode_id, "episode-a")
        self.assertEqual(record.step_index, 0)
        self.assertEqual(record.reconciliation, ReconciliationStatus.WAIT_ADVANCED.value)
        self.assertEqual(record.before_state, before.to_dict())
        self.assertEqual(record.after_state, after.to_dict())
        self.assertEqual(record.reward, result.outcome.reward)
        self.assertEqual(record.reward_schema_version, 1)
        self.assertEqual(record.reward_spec_name, "reward-v1-default")
        self.assertEqual(record.reward_components, result.outcome.components)
        self.assertTrue(np.array_equal(record.before_observation.to_array(), result.before.observation))
        self.assertEqual(record.before_action_mask.dtype, "bool")

    def test_plant_controller_failure_and_missing_postcondition_records(self):
        sink = CaptureSink()
        self.make_env(game_state(), game_state(plants=[plant()]), sink=sink).step(self.plant_index())
        self.make_env(game_state(), game_state(), sink=sink).step(self.plant_index())
        controller = FakeController(ActionResult(False, False, "input_failed"))
        self.make_env(game_state(), game_state(), sink=sink, controller=controller).step(self.plant_index())

        observed, missing, failed = sink.records
        self.assertEqual(observed.reconciliation, ReconciliationStatus.PLANT_OBSERVED.value)
        self.assertEqual(missing.reconciliation, ReconciliationStatus.POSTCONDITION_UNAVAILABLE.value)
        self.assertEqual(failed.reconciliation, ReconciliationStatus.CONTROLLER_FAILED.value)
        self.assertEqual(failed.controller_result, {"attempted": False, "reason": "input_failed", "success": False})
        self.assertEqual(observed.action["action_type"], "plant")

    def test_polled_plant_writes_one_record_with_confirming_after_state(self):
        sink = CaptureSink()
        before, initial_after, confirmed = game_state(), game_state(), game_state(plants=[plant()])
        result = self.make_env(before, initial_after, confirmed, sink=sink).step(self.plant_index())

        self.assertEqual(len(sink.records), 1)
        self.assertEqual(result.reconciliation, ReconciliationStatus.PLANT_OBSERVED)
        self.assertEqual(sink.records[0].after_state, confirmed.to_dict())
        self.assertGreaterEqual(sink.records[0].timing["reconciliation_poll_count"], 0)

    def test_rejected_invalid_and_unavailable_records_are_preserved(self):
        sink = CaptureSink()
        env = self.make_env(game_state(seeds=[]), sink=sink)
        env.step(ACTION_COUNT)
        env.step(self.plant_index())
        unavailable_env = PvZEnvironment(FakeReader(game_state(), None), FakeController(), transition_sink=sink,
            sleeper=lambda interval: None, clock=lambda: 1.0)
        unavailable_env.reset(EpisodeConfig("episode-a"))
        unavailable = unavailable_env.step(0)

        invalid, masked, unavailable_record = sink.records
        self.assertEqual(invalid.rejection_reason, StepRejectionReason.INVALID_ACTION_INDEX.value)
        self.assertEqual(masked.rejection_reason, StepRejectionReason.ACTION_MASKED.value)
        self.assertEqual(unavailable.rejection_reason, StepRejectionReason.STATE_UNAVAILABLE)
        self.assertIsNone(unavailable_record.before_state)
        self.assertEqual(unavailable_record.rejection_reason, StepRejectionReason.STATE_UNAVAILABLE.value)

    def test_step_indexes_increment_for_rejected_and_executed_steps(self):
        sink = CaptureSink()
        env = self.make_env(game_state(), game_state(sun=400), sink=sink, episode_id="manual-level")
        env.step(ACTION_COUNT)
        env.step(0)

        self.assertEqual([(record.episode_id, record.step_index) for record in sink.records], [("manual-level", 0), ("manual-level", 1)])

    def test_unavailable_after_state_is_logged_without_losing_before(self):
        sink = CaptureSink()
        result = self.make_env(game_state(), None, sink=sink).step(0)

        self.assertEqual(result.reconciliation, ReconciliationStatus.POSTCONDITION_UNAVAILABLE)
        self.assertIsNotNone(sink.records[0].before_state)
        self.assertIsNone(sink.records[0].after_state)

    def test_logging_disabled_preserves_environment_behavior(self):
        result = self.make_env(game_state(), game_state(sun=300)).step(0)

        self.assertEqual(result.reconciliation, ReconciliationStatus.WAIT_ADVANCED)
        self.assertIsNotNone(result.after)

    def test_jsonl_appends_independent_lines_and_round_trips(self):
        sink = CaptureSink()
        self.make_env(game_state(), game_state(sun=260), sink=sink).step(0)
        self.make_env(game_state(), game_state(plants=[plant()]), sink=sink).step(self.plant_index())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "transitions.jsonl"
            with JsonlTransitionSink(path) as jsonl:
                for record in sink.records:
                    jsonl.write(record)
            lines = path.read_text(encoding="utf-8").splitlines()
            loaded = read_transition_jsonl(path)

        self.assertEqual(len(lines), 2)
        self.assertEqual(loaded, sink.records)
        self.assertTrue(np.array_equal(loaded[0].after_action_mask.to_array(), sink.records[0].after_action_mask.to_array()))

    def test_malformed_jsonl_and_sink_failure_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaises(TransitionLogFormatError):
                read_transition_jsonl(path)

        env = self.make_env(game_state(), game_state(sun=350), sink=FailingSink())
        with self.assertRaises(TransitionLoggingError) as caught:
            env.step(0)
        self.assertEqual(caught.exception.step_result.reconciliation, ReconciliationStatus.WAIT_ADVANCED)

    def test_schema_v1_documents_are_explicitly_unsupported(self):
        sink = CaptureSink()
        self.make_env(game_state(), game_state(), sink=sink).step(0)
        old_document = sink.records[0].to_dict()
        old_document["schema_version"] = 1
        for field in ("reward", "terminated", "truncated", "outcome_reason", "reward_components", "reward_schema_version", "reward_spec_name"):
            del old_document[field]
        with self.assertRaisesRegex(TransitionLogFormatError, "schema v2"):
            TransitionRecord.from_dict(old_document)

    def test_raw_state_and_record_serialization_do_not_mutate_state(self):
        before, after = game_state(), game_state(plants=[plant()])
        before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
        sink = CaptureSink()
        result = self.make_env(before, after, sink=sink).step(self.plant_index())
        document = sink.records[0].to_dict()

        self.assertEqual(before, before_copy)
        self.assertEqual(after, after_copy)
        self.assertEqual(TransitionRecord.from_dict(json.loads(json.dumps(document))), sink.records[0])
        self.assertEqual(result.controller_result, ActionResult(True, None, "clicks_issued"))


if __name__ == "__main__":
    unittest.main()
