"""Basic plant-placement checks for ordinary grass tiles.

This module intentionally models only the first placement layer: normal
grass tiles with no stacking, terrain, or plant-specific special cases.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState


BOARD_ROWS = 6
BOARD_COLS = 9

# Graves and craters occupy a tile for normal planting.  Ladders do not:
# they are attached to an existing plant and are not an independent
# obstruction to planting on an otherwise empty tile.
BLOCKING_GRID_ITEM_TYPES = frozenset({1, 2})


@dataclass(frozen=True)
class PlacementResult:
    """The outcome of a basic ordinary-grass placement check."""

    valid: bool
    reason: str


def can_plant(
    state: "GameState",
    seed_slot: int,
    row: int,
    col: int,
) -> PlacementResult:
    """Return whether ``seed_slot`` can be planted at a grass-tile location.

    The caller is responsible for using this only for ordinary grass tiles.
    Pool, roof, stacking, upgrades, and all plant-specific placement rules are
    intentionally outside this phase.

    ``reason`` is ``"valid"`` for a permitted placement; otherwise it is a
    stable machine-readable reason code.
    """
    if not 0 <= row < BOARD_ROWS:
        return PlacementResult(False, "row_out_of_bounds")

    if not 0 <= col < BOARD_COLS:
        return PlacementResult(False, "col_out_of_bounds")

    seed = next((seed for seed in state.seeds if seed.slot == seed_slot), None)
    if seed is None:
        return PlacementResult(False, "unknown_seed_slot")

    if not seed.ready:
        return PlacementResult(False, "seed_not_ready")

    if not seed.affordable:
        return PlacementResult(False, "insufficient_sun")

    if not seed.actionable:
        return PlacementResult(False, "seed_not_actionable")

    if any(plant.row == row and plant.col == col for plant in state.plants):
        return PlacementResult(False, "tile_occupied")

    if any(
        item.row == row
        and item.col == col
        and not item.dead
        and item.type_id in BLOCKING_GRID_ITEM_TYPES
        for item in state.grid_items
    ):
        return PlacementResult(False, "tile_blocked")

    return PlacementResult(True, "valid")


# Kept as an alias for callers using the initial placement helper name.
check_placement = can_plant
