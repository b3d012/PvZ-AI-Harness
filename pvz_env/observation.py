"""Deterministic fixed-size encoding of frozen :class:`GameState` v1.

Observation schema v1 is a flattened ``float32`` vector composed of global,
board, seed-bank, zombie, and mower components.  It deliberately defers
pickups, projectiles, and grid items: they remain in raw ``GameState`` for
future environment versions, while Phase 3.1 concentrates on strategic board
state and imminent lane threats.

Plant types, seed types, imitater targets, and zombie types use fixed one-hot
channels.  Plant stacks aggregate health/state and preserve every known plant
type as a presence channel.  Zombie lanes retain the five zombies closest to
the house, ordered by ``(x, type_id, slot)``; additional zombies are omitted
deterministically.  Scalar values are clipped to documented finite ranges.
"""

from dataclasses import dataclass
from math import prod
from typing import TYPE_CHECKING

import numpy as np

from pvz_reader.placement import BOARD_COLS, BOARD_ROWS

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState


OBSERVATION_SCHEMA_VERSION = 1
MAX_PLANT_TYPE_ID = 48
MAX_ZOMBIE_TYPE_ID = 32
MAX_SEED_SLOTS = 10
MAX_ZOMBIES_PER_LANE = 5
KNOWN_SCENES = 5
PLANT_STATE_CAP = 255.0
STATUS_TIMER_CAP = 600.0
SUN_CAP = 9990.0
GAME_CLOCK_CAP = 1_000_000.0
WAVE_HP_CAP = 100_000.0


def _type_channels(prefix: str, maximum: int) -> tuple[str, ...]:
    return tuple(f"{prefix}_{type_id}" for type_id in range(maximum + 1))


GLOBAL_FEATURE_NAMES = (
    "sun_log_normalized",
    "game_clock_log_normalized",
    *(f"scene_{scene}" for scene in range(KNOWN_SCENES)),
    "paused",
    "spawned_wave_ratio",
    "refreshed_wave_ratio",
    "next_wave_timer_ratio",
    "huge_wave_incoming",
    "huge_wave_countdown_log_normalized",
    "current_wave_hp_log_normalized",
    "refresh_hp_log_normalized",
)
BOARD_CHANNEL_NAMES = (
    "occupied",
    "plant_count_capped",
    "mean_hp_ratio",
    "max_hp_ratio",
    "mean_state_normalized",
    "asleep_fraction",
    "has_lily_pad",
    "has_flower_pot",
    "has_pumpkin",
    *_type_channels("plant_type", MAX_PLANT_TYPE_ID),
)
SEED_CHANNEL_NAMES = (
    "exists",
    *_type_channels("seed_type", MAX_PLANT_TYPE_ID),
    *_type_channels("imitater_target", MAX_PLANT_TYPE_ID),
    "cost_normalized",
    "cooldown_ratio",
    "ready",
    "cooling_down",
    "selected",
    "affordable",
    "actionable",
)
ZOMBIE_CHANNEL_NAMES = (
    "exists",
    *_type_channels("zombie_type", MAX_ZOMBIE_TYPE_ID),
    "body_hp_ratio",
    "armor_hp_ratio",
    "house_progress",
    "biting",
    "hypnotized",
    "slow_timer_normalized",
    "stun_timer_normalized",
    "freeze_timer_normalized",
    "state_normalized",
)
MOWER_CHANNEL_NAMES = ("exists", "available", "visible", "state_normalized")


@dataclass(frozen=True)
class ObservationSpec:
    """Inspectable, frozen-in-code description of EncodedObservation v1."""

    version: int
    global_shape: tuple[int, ...]
    board_shape: tuple[int, ...]
    seed_shape: tuple[int, ...]
    zombie_shape: tuple[int, ...]
    mower_shape: tuple[int, ...]
    global_feature_names: tuple[str, ...]
    board_channel_names: tuple[str, ...]
    seed_channel_names: tuple[str, ...]
    zombie_channel_names: tuple[str, ...]
    mower_channel_names: tuple[str, ...]
    deferred_fields: tuple[str, ...]

    @property
    def component_shapes(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        """Ordered shapes used when flattening an observation."""
        return (
            ("global", self.global_shape),
            ("board", self.board_shape),
            ("seeds", self.seed_shape),
            ("zombies", self.zombie_shape),
            ("mowers", self.mower_shape),
        )

    @property
    def flat_shape(self) -> tuple[int]:
        return (sum(prod(shape) for _, shape in self.component_shapes),)

    def component_slice(self, name: str) -> slice:
        """Return the flattened vector slice for one named component."""
        start = 0
        for component_name, shape in self.component_shapes:
            stop = start + prod(shape)
            if component_name == name:
                return slice(start, stop)
            start = stop
        raise KeyError(f"unknown observation component: {name}")


OBSERVATION_SPEC = ObservationSpec(
    version=OBSERVATION_SCHEMA_VERSION,
    global_shape=(len(GLOBAL_FEATURE_NAMES),),
    board_shape=(BOARD_ROWS, BOARD_COLS, len(BOARD_CHANNEL_NAMES)),
    seed_shape=(MAX_SEED_SLOTS, len(SEED_CHANNEL_NAMES)),
    zombie_shape=(BOARD_ROWS, MAX_ZOMBIES_PER_LANE, len(ZOMBIE_CHANNEL_NAMES)),
    mower_shape=(BOARD_ROWS, len(MOWER_CHANNEL_NAMES)),
    global_feature_names=GLOBAL_FEATURE_NAMES,
    board_channel_names=BOARD_CHANNEL_NAMES,
    seed_channel_names=SEED_CHANNEL_NAMES,
    zombie_channel_names=ZOMBIE_CHANNEL_NAMES,
    mower_channel_names=MOWER_CHANNEL_NAMES,
    deferred_fields=("pickups", "projectiles", "grid_items"),
)


def _bounded(value: float, upper: float) -> np.float32:
    """Normalize a non-negative scalar into the inclusive ``[0, 1]`` range."""
    if not np.isfinite(value) or value <= 0:
        return np.float32(0.0)
    return np.float32(min(value, upper) / upper)


def _log_bounded(value: float, upper: float) -> np.float32:
    """Log-normalize a non-negative scalar into the inclusive ``[0, 1]`` range."""
    if not np.isfinite(value) or value <= 0:
        return np.float32(0.0)
    return np.float32(np.log1p(min(value, upper)) / np.log1p(upper))


def _ratio(value: float, maximum: float) -> np.float32:
    if not np.isfinite(value) or not np.isfinite(maximum) or maximum <= 0:
        return np.float32(0.0)
    return np.float32(np.clip(value / maximum, 0.0, 1.0))


class ObservationEncoder:
    """Encode a valid ``GameState v1`` into a flat model-facing NumPy array."""

    spec = OBSERVATION_SPEC

    def encode(self, state: "GameState") -> np.ndarray:
        """Return a deterministic, C-contiguous ``float32`` vector.

        The input state and its entity lists are only read; the encoder never
        modifies ``GameState`` or any contained object.
        """
        if state is None:
            raise ValueError("GameState is required for observation encoding")

        components = (
            self._encode_global(state),
            self._encode_board(state),
            self._encode_seeds(state),
            self._encode_zombies(state),
            self._encode_mowers(state),
        )
        encoded = np.concatenate([component.reshape(-1) for component in components])
        return np.ascontiguousarray(encoded, dtype=np.float32)

    def _encode_global(self, state: "GameState") -> np.ndarray:
        values = np.zeros(self.spec.global_shape, dtype=np.float32)
        values[0] = _log_bounded(state.sun, SUN_CAP)
        values[1] = _log_bounded(state.game_clock, GAME_CLOCK_CAP)
        if 0 <= state.scene < KNOWN_SCENES:
            values[2 + state.scene] = 1.0
        values[2 + KNOWN_SCENES] = float(bool(state.paused))

        wave_offset = 3 + KNOWN_SCENES
        total_waves = state.wave.total_waves
        values[wave_offset] = _ratio(state.wave.spawned_waves, total_waves)
        values[wave_offset + 1] = _ratio(state.wave.refreshed_waves, total_waves)
        values[wave_offset + 2] = np.float32(
            np.clip(state.wave.next_wave_timer_ratio, 0.0, 1.0)
        )
        values[wave_offset + 3] = float(bool(state.wave.huge_wave_incoming))
        values[wave_offset + 4] = _log_bounded(
            state.wave.huge_wave_countdown,
            GAME_CLOCK_CAP,
        )
        values[wave_offset + 5] = _log_bounded(state.wave.current_wave_hp, WAVE_HP_CAP)
        values[wave_offset + 6] = _log_bounded(state.wave.refresh_hp, WAVE_HP_CAP)
        return values

    def _encode_board(self, state: "GameState") -> np.ndarray:
        board = np.zeros(self.spec.board_shape, dtype=np.float32)
        grouped: dict[tuple[int, int], list] = {}
        for plant in state.plants:
            if 0 <= plant.row < BOARD_ROWS and 0 <= plant.col < BOARD_COLS:
                grouped.setdefault((plant.row, plant.col), []).append(plant)

        for (row, col), plants in grouped.items():
            cell = board[row, col]
            cell[0] = 1.0
            cell[1] = _bounded(len(plants), 3.0)
            hp_ratios = [_ratio(plant.hp, plant.max_hp) for plant in plants]
            cell[2] = np.mean(hp_ratios, dtype=np.float32)
            cell[3] = np.max(hp_ratios)
            cell[4] = np.mean(
                [_bounded(plant.state, PLANT_STATE_CAP) for plant in plants],
                dtype=np.float32,
            )
            cell[5] = np.mean([float(bool(plant.asleep)) for plant in plants])
            cell[6] = float(any(plant.type_id == 16 for plant in plants))
            cell[7] = float(any(plant.type_id == 33 for plant in plants))
            cell[8] = float(any(plant.type_id == 30 for plant in plants))
            for plant in plants:
                if 0 <= plant.type_id <= MAX_PLANT_TYPE_ID:
                    cell[9 + plant.type_id] = 1.0
        return board

    def _encode_seeds(self, state: "GameState") -> np.ndarray:
        seeds = np.zeros(self.spec.seed_shape, dtype=np.float32)
        for seed in state.seeds:
            if not 0 <= seed.slot < MAX_SEED_SLOTS:
                continue
            slot = seeds[seed.slot]
            slot[0] = 1.0
            if 0 <= seed.type_id <= MAX_PLANT_TYPE_ID:
                slot[1 + seed.type_id] = 1.0
            imitater_offset = 1 + MAX_PLANT_TYPE_ID + 1
            if seed.imitater_target_id is not None and 0 <= seed.imitater_target_id <= MAX_PLANT_TYPE_ID:
                slot[imitater_offset + seed.imitater_target_id] = 1.0
            scalar_offset = imitater_offset + MAX_PLANT_TYPE_ID + 1
            slot[scalar_offset] = _bounded(seed.cost, 500.0)
            slot[scalar_offset + 1] = np.float32(np.clip(seed.cooldown_ratio, 0.0, 1.0))
            slot[scalar_offset + 2] = float(bool(seed.ready))
            slot[scalar_offset + 3] = float(bool(seed.cooling_down))
            slot[scalar_offset + 4] = float(bool(seed.selected))
            slot[scalar_offset + 5] = float(bool(seed.affordable))
            slot[scalar_offset + 6] = float(bool(seed.actionable))
        return seeds

    def _encode_zombies(self, state: "GameState") -> np.ndarray:
        zombies = np.zeros(self.spec.zombie_shape, dtype=np.float32)
        rows: list[list] = [[] for _ in range(BOARD_ROWS)]
        for zombie in state.zombies:
            if 0 <= zombie.row < BOARD_ROWS:
                rows[zombie.row].append(zombie)

        for row, lane_zombies in enumerate(rows):
            ordered = sorted(lane_zombies, key=lambda zombie: (zombie.x, zombie.type_id, zombie.slot))
            for index, zombie in enumerate(ordered[:MAX_ZOMBIES_PER_LANE]):
                slot = zombies[row, index]
                slot[0] = 1.0
                if 0 <= zombie.type_id <= MAX_ZOMBIE_TYPE_ID:
                    slot[1 + zombie.type_id] = 1.0
                scalar_offset = 1 + MAX_ZOMBIE_TYPE_ID + 1
                slot[scalar_offset] = _ratio(zombie.body_hp, zombie.body_max_hp)
                slot[scalar_offset + 1] = _ratio(zombie.armor_hp, zombie.armor_max_hp)
                slot[scalar_offset + 2] = np.float32(
                    1.0 - np.clip(zombie.x / 800.0, 0.0, 1.0)
                )
                slot[scalar_offset + 3] = float(bool(zombie.biting))
                slot[scalar_offset + 4] = float(bool(zombie.hypnotized))
                slot[scalar_offset + 5] = _bounded(zombie.slow_timer, STATUS_TIMER_CAP)
                slot[scalar_offset + 6] = _bounded(zombie.stun_timer, STATUS_TIMER_CAP)
                slot[scalar_offset + 7] = _bounded(zombie.freeze_timer, STATUS_TIMER_CAP)
                slot[scalar_offset + 8] = _bounded(zombie.state, PLANT_STATE_CAP)
        return zombies

    def _encode_mowers(self, state: "GameState") -> np.ndarray:
        mowers = np.zeros(self.spec.mower_shape, dtype=np.float32)
        by_row: dict[int, list] = {}
        for mower in state.mowers:
            if 0 <= mower.row < BOARD_ROWS:
                by_row.setdefault(mower.row, []).append(mower)

        for row, row_mowers in by_row.items():
            mower = min(row_mowers, key=lambda item: item.slot)
            values = mowers[row]
            values[0] = 1.0
            values[1] = float(bool(mower.available))
            values[2] = float(bool(mower.visible))
            values[3] = _bounded(mower.state, PLANT_STATE_CAP)
        return mowers
