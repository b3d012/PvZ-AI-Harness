"""Basic terrain-aware plant-placement checks.

Only ordinary grass, roof Flower Pot support, and pool Lily Pad support are
modelled here.  Plant-specific placement and stacking rules remain out of
scope.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState


BOARD_ROWS = 6
BOARD_COLS = 9

# Board scene values used by Plants vs. Zombies GOTY 1.2.0.1073.
# Fog uses the same water rows as a pool scene.
POOL_SCENES = frozenset({2, 3})
ROOF_SCENE = 4
POOL_WATER_ROWS = frozenset({2, 3})

# These IDs correspond to the existing PLANT_NAMES entries in game_state.py.
LILY_PAD_TYPE_ID = 16
FLOWER_POT_TYPE_ID = 33
IMITATER_TYPE_ID = 48

# These plants have their own water-placement behavior, which is not modelled
# in this phase.  Rejecting them on water avoids incorrectly approving them.
UNSUPPORTED_WATER_PLANT_TYPE_IDS = frozenset({19, 24, 43})

# Graves and craters occupy a tile for normal planting.  Ladders do not:
# they are attached to an existing plant and are not an independent
# obstruction to planting on an otherwise empty tile.
BLOCKING_GRID_ITEM_TYPES = frozenset({1, 2})


@dataclass(frozen=True)
class PlacementResult:
    """The outcome of a basic ordinary-grass placement check."""

    valid: bool
    reason: str


def _is_roof_scene(scene: int) -> bool:
    return scene == ROOF_SCENE


def _is_pool_scene(scene: int) -> bool:
    return scene in POOL_SCENES


def _is_pool_water_tile(state: "GameState", row: int) -> bool:
    return _is_pool_scene(state.scene) and row in POOL_WATER_ROWS


def _seed_plant_type_id(seed) -> int:
    """Return the plant type represented by a normal or Imitater seed."""
    if (
        seed.type_id == IMITATER_TYPE_ID
        and seed.imitater_target_id is not None
    ):
        return seed.imitater_target_id

    return seed.type_id


def _plants_at_tile(state: "GameState", row: int, col: int):
    return [
        plant
        for plant in state.plants
        if plant.row == row and plant.col == col
    ]


def _tile_has_plant_type(plants, type_id: int) -> bool:
    return any(plant.type_id == type_id for plant in plants)


def _tile_has_non_support_plant(plants, support_type_id: int) -> bool:
    return any(plant.type_id != support_type_id for plant in plants)


def can_plant(
    state: "GameState",
    seed_slot: int,
    row: int,
    col: int,
) -> PlacementResult:
    """Return whether ``seed_slot`` can be planted at a grass-tile location.

    Roof tiles require Flower Pot support for ordinary plants.  Pool/fog water
    rows require Lily Pad support for ordinary land plants.  Tangle Kelp,
    Sea-shroom, and Cattail are conservatively rejected on water because their
    special water rules are not implemented.

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

    if any(
        item.row == row
        and item.col == col
        and not item.dead
        and item.type_id in BLOCKING_GRID_ITEM_TYPES
        for item in state.grid_items
    ):
        return PlacementResult(False, "tile_blocked")

    plant_type_id = _seed_plant_type_id(seed)
    tile_plants = _plants_at_tile(state, row, col)

    if _is_roof_scene(state.scene):
        if plant_type_id == FLOWER_POT_TYPE_ID:
            if tile_plants:
                return PlacementResult(False, "tile_occupied")
        else:
            if _tile_has_non_support_plant(
                tile_plants,
                FLOWER_POT_TYPE_ID,
            ):
                return PlacementResult(False, "tile_occupied")

            if not _tile_has_plant_type(tile_plants, FLOWER_POT_TYPE_ID):
                return PlacementResult(False, "roof_requires_flower_pot")

    elif _is_pool_water_tile(state, row):
        if plant_type_id in UNSUPPORTED_WATER_PLANT_TYPE_IDS:
            return PlacementResult(False, "unsupported_water_plant")

        if plant_type_id == LILY_PAD_TYPE_ID:
            if tile_plants:
                return PlacementResult(False, "tile_occupied")
        else:
            if _tile_has_non_support_plant(
                tile_plants,
                LILY_PAD_TYPE_ID,
            ):
                return PlacementResult(False, "tile_occupied")

            if not _tile_has_plant_type(tile_plants, LILY_PAD_TYPE_ID):
                return PlacementResult(False, "water_requires_lily_pad")

    elif tile_plants:
        return PlacementResult(False, "tile_occupied")

    return PlacementResult(True, "valid")


# Kept as an alias for callers using the initial placement helper name.
check_placement = can_plant
