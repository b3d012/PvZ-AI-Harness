"""Deterministic Phase 3.2 semantic action indexing and legality masks.

Action v1 deliberately contains only strategic ``WAIT`` and ``PLANT``
decisions.  Pickup collection is environment-managed, while shoveling is
deferred until it is justified by the initial environment contract.  Existing
indices remain unambiguous when later schema versions add action types.

``GameState v1`` has no authoritative early-Adventure active-row field.
Accordingly, callers may pass an explicit six-boolean ``active_rows`` mask.
``None`` means every logical row is active and is appropriate only for a
known full-board episode.  Phase 3.3 reset/lifecycle code must supply the
correct mask for its selected level; no Adventure-progression rule is guessed
here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterable

import numpy as np

from pvz_reader.placement import BOARD_COLS, BOARD_ROWS, can_plant

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState


ACTION_SCHEMA_VERSION = 1
MAX_SEED_SLOTS = 10
WAIT_INDEX = 0
PLANT_INDEX_START = WAIT_INDEX + 1
PLANT_ACTION_COUNT = MAX_SEED_SLOTS * BOARD_ROWS * BOARD_COLS
ACTION_COUNT = PLANT_INDEX_START + PLANT_ACTION_COUNT
DEFERRED_ACTION_TYPES = ("shovel", "collect_pickup")


class ActionType(str, Enum):
    """The semantic action kinds supported by Action v1."""

    WAIT = "wait"
    PLANT = "plant"


@dataclass(frozen=True)
class SemanticAction:
    """A policy decision independent of screen coordinates and clicks."""

    action_type: ActionType
    seed_slot: int | None = None
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True)
class ActionSpec:
    """Inspectable fixed Action v1 dimensions and index ranges."""

    version: int
    action_count: int
    wait_index: int
    plant_index_start: int
    plant_index_stop: int
    max_seed_slots: int
    board_rows: int
    board_cols: int
    deferred_action_types: tuple[str, ...]


ACTION_SPEC = ActionSpec(
    version=ACTION_SCHEMA_VERSION,
    action_count=ACTION_COUNT,
    wait_index=WAIT_INDEX,
    plant_index_start=PLANT_INDEX_START,
    plant_index_stop=ACTION_COUNT,
    max_seed_slots=MAX_SEED_SLOTS,
    board_rows=BOARD_ROWS,
    board_cols=BOARD_COLS,
    deferred_action_types=DEFERRED_ACTION_TYPES,
)


def _validate_plant_target(seed_slot: int, row: int, col: int) -> None:
    if not 0 <= seed_slot < MAX_SEED_SLOTS:
        raise ValueError(f"seed_slot must be in [0, {MAX_SEED_SLOTS}), got {seed_slot}")
    if not 0 <= row < BOARD_ROWS:
        raise ValueError(f"row must be in [0, {BOARD_ROWS}), got {row}")
    if not 0 <= col < BOARD_COLS:
        raise ValueError(f"col must be in [0, {BOARD_COLS}), got {col}")


def encode_action(action: SemanticAction) -> int:
    """Return the fixed Action v1 index for a semantic action.

    Plant indices are seed-slot-major, then row-major, then column-major:
    ``1 + ((seed_slot * 6 + row) * 9 + col)``.
    """
    if action.action_type is ActionType.WAIT:
        if any(value is not None for value in (action.seed_slot, action.row, action.col)):
            raise ValueError("WAIT must not include a seed slot or tile target")
        return WAIT_INDEX
    if action.action_type is ActionType.PLANT:
        if None in (action.seed_slot, action.row, action.col):
            raise ValueError("PLANT requires seed_slot, row, and col")
        _validate_plant_target(action.seed_slot, action.row, action.col)
        return PLANT_INDEX_START + ((action.seed_slot * BOARD_ROWS + action.row) * BOARD_COLS + action.col)
    raise ValueError(f"unsupported action type: {action.action_type!r}")


def decode_action(index: int) -> SemanticAction:
    """Decode one Action v1 index into its stable semantic representation."""
    if not isinstance(index, int) or isinstance(index, bool):
        raise ValueError("action index must be an integer")
    if index == WAIT_INDEX:
        return SemanticAction(ActionType.WAIT)
    if not PLANT_INDEX_START <= index < ACTION_COUNT:
        raise ValueError(f"action index must be in [0, {ACTION_COUNT}), got {index}")

    offset = index - PLANT_INDEX_START
    seed_slot, tile = divmod(offset, BOARD_ROWS * BOARD_COLS)
    row, col = divmod(tile, BOARD_COLS)
    return SemanticAction(ActionType.PLANT, seed_slot, row, col)


def normalize_active_rows(active_rows: Iterable[bool] | None = None) -> tuple[bool, ...]:
    """Return a validated immutable six-row episode legality configuration."""
    if active_rows is None:
        return (True,) * BOARD_ROWS
    normalized = tuple(active_rows)
    if len(normalized) != BOARD_ROWS or not all(isinstance(row, bool) for row in normalized):
        raise ValueError(f"active_rows must contain exactly {BOARD_ROWS} booleans")
    return normalized


def build_action_mask(
    state: "GameState", active_rows: Iterable[bool] | None = None
) -> np.ndarray:
    """Build a fixed ``bool`` Action v1 legality mask without mutating state.

    ``WAIT`` is legal for every unpaused/playable state.  Each plant entry
    delegates all seed, terrain, blocker, and prerequisite decisions to
    :func:`pvz_reader.placement.can_plant`; this layer adds only the explicit
    episode active-row filter.
    """
    if state is None:
        raise ValueError("GameState is required for action masking")

    rows = normalize_active_rows(active_rows)
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    if getattr(state, "paused", False):
        return mask

    mask[WAIT_INDEX] = True
    for seed_slot in range(MAX_SEED_SLOTS):
        for row, row_active in enumerate(rows):
            if not row_active:
                continue
            for col in range(BOARD_COLS):
                index = PLANT_INDEX_START + ((seed_slot * BOARD_ROWS + row) * BOARD_COLS + col)
                mask[index] = can_plant(state, seed_slot, row, col).valid
    return mask
