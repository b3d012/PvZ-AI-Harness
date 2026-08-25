"""Basic terrain-aware plant-placement checks.

Only ordinary grass, roof Flower Pot support, pool Lily Pad support, and the
small set of explicitly supported special placements are modelled here.
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

GRAVE_BUSTER_TYPE_ID = 11
PUMPKIN_TYPE_ID = 30
COFFEE_BEAN_TYPE_ID = 35

GATLING_PEA_TYPE_ID = 40
TWIN_SUNFLOWER_TYPE_ID = 41
GLOOM_SHROOM_TYPE_ID = 42
CATTAIL_TYPE_ID = 43
WINTER_MELON_TYPE_ID = 44
GOLD_MAGNET_TYPE_ID = 45
SPIKEROCK_TYPE_ID = 46
COB_CANNON_TYPE_ID = 47

# These plants have their own water-placement behavior, which is not modelled
# in this phase.  Rejecting them on water avoids incorrectly approving them.
UNSUPPORTED_WATER_PLANT_TYPE_IDS = frozenset({19, 24})

GRAVE_GRID_ITEM_TYPE_ID = 1
CRATER_GRID_ITEM_TYPE_ID = 2

# All mushroom types already represented in the game_state.py plant table.
MUSHROOM_TYPE_IDS = frozenset({8, 9, 10, 12, 13, 14, 15, 24, 31, 42, 45})

UPGRADE_BASE_TYPE_IDS = {
    GATLING_PEA_TYPE_ID: 7,   # Repeater
    TWIN_SUNFLOWER_TYPE_ID: 1,  # Sunflower
    GLOOM_SHROOM_TYPE_ID: 10,  # Fume-shroom
    CATTAIL_TYPE_ID: LILY_PAD_TYPE_ID,
    WINTER_MELON_TYPE_ID: 39,  # Melon-pult
    GOLD_MAGNET_TYPE_ID: 31,  # Magnet-shroom
    SPIKEROCK_TYPE_ID: 21,  # Spikeweed
}

KERNEL_PULT_TYPE_ID = 34

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


def _tile_has_live_grid_item(
    state: "GameState",
    row: int,
    col: int,
    type_id: int,
) -> bool:
    return any(
        item.row == row
        and item.col == col
        and not item.dead
        and item.type_id == type_id
        for item in state.grid_items
    )


def _terrain_result(
    state: "GameState",
    plant_type_id: int,
    row: int,
    tile_plants,
) -> PlacementResult | None:
    """Return an unmet terrain requirement, if this tile has one."""
    if _is_roof_scene(state.scene):
        if (
            plant_type_id != FLOWER_POT_TYPE_ID
            and not _tile_has_plant_type(tile_plants, FLOWER_POT_TYPE_ID)
        ):
            return PlacementResult(False, "roof_requires_flower_pot")

    elif _is_pool_water_tile(state, row):
        if plant_type_id in UNSUPPORTED_WATER_PLANT_TYPE_IDS:
            return PlacementResult(False, "unsupported_water_plant")

        if (
            plant_type_id != LILY_PAD_TYPE_ID
            and not _tile_has_plant_type(tile_plants, LILY_PAD_TYPE_ID)
        ):
            return PlacementResult(False, "water_requires_lily_pad")

    return None


def _non_support_plants(tile_plants):
    return [
        plant
        for plant in tile_plants
        if plant.type_id not in {FLOWER_POT_TYPE_ID, LILY_PAD_TYPE_ID}
    ]


def _is_mushroom_type(type_id: int) -> bool:
    return type_id in MUSHROOM_TYPE_IDS


def _has_required_upgrade_base(tile_plants, base_type_id: int) -> bool:
    """Check for one base plant, allowing only terrain support alongside it."""
    if base_type_id in {FLOWER_POT_TYPE_ID, LILY_PAD_TYPE_ID}:
        return (
            _tile_has_plant_type(tile_plants, base_type_id)
            and all(plant.type_id == base_type_id for plant in tile_plants)
        )

    plants = _non_support_plants(tile_plants)
    return len(plants) == 1 and plants[0].type_id == base_type_id


def _tile_has_only_base_with_support(
    state: "GameState",
    row: int,
    col: int,
    base_type_id: int,
) -> bool:
    plants = _non_support_plants(_plants_at_tile(state, row, col))
    return len(plants) == 1 and plants[0].type_id == base_type_id


def _has_required_cob_pair(state: "GameState", row: int, col: int) -> bool:
    """Return whether the target is one of two adjacent Kernel-pults."""
    if not _tile_has_only_base_with_support(
        state,
        row,
        col,
        KERNEL_PULT_TYPE_ID,
    ):
        return False

    return any(
        0 <= adjacent_col < BOARD_COLS
        and _tile_has_only_base_with_support(
            state,
            row,
            adjacent_col,
            KERNEL_PULT_TYPE_ID,
        )
        for adjacent_col in (col - 1, col + 1)
    )


def can_plant(
    state: "GameState",
    seed_slot: int,
    row: int,
    col: int,
) -> PlacementResult:
    """Return whether ``seed_slot`` can be planted at a grass-tile location.

    Roof tiles require Flower Pot support for ordinary plants.  Pool/fog water
    rows require Lily Pad support for ordinary land plants.  Only Grave Buster,
    Coffee Bean, Pumpkin, and the listed plant upgrades have special handling.

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

    plant_type_id = _seed_plant_type_id(seed)
    tile_plants = _plants_at_tile(state, row, col)

    if plant_type_id == GRAVE_BUSTER_TYPE_ID:
        if not _tile_has_live_grid_item(
            state,
            row,
            col,
            GRAVE_GRID_ITEM_TYPE_ID,
        ):
            return PlacementResult(False, "grave_buster_requires_grave")
        if _tile_has_live_grid_item(
            state,
            row,
            col,
            CRATER_GRID_ITEM_TYPE_ID,
        ):
            return PlacementResult(False, "tile_blocked")
    elif any(
        item.row == row
        and item.col == col
        and not item.dead
        and item.type_id in BLOCKING_GRID_ITEM_TYPES
        for item in state.grid_items
    ):
        return PlacementResult(False, "tile_blocked")

    terrain_result = _terrain_result(
        state,
        plant_type_id,
        row,
        tile_plants,
    )
    if terrain_result is not None:
        return terrain_result

    if plant_type_id == GRAVE_BUSTER_TYPE_ID:
        if tile_plants:
            return PlacementResult(False, "tile_occupied")

    elif plant_type_id == COFFEE_BEAN_TYPE_ID:
        non_support_plants = _non_support_plants(tile_plants)
        if not non_support_plants:
            return PlacementResult(False, "coffee_requires_sleeping_mushroom")

        if len(non_support_plants) != 1:
            return PlacementResult(False, "coffee_requires_sleeping_mushroom")

        target = non_support_plants[0]
        if not _is_mushroom_type(target.type_id):
            return PlacementResult(False, "coffee_target_not_mushroom")

        if not target.asleep:
            return PlacementResult(False, "coffee_target_awake")

    elif plant_type_id == PUMPKIN_TYPE_ID:
        if _tile_has_plant_type(tile_plants, PUMPKIN_TYPE_ID):
            return PlacementResult(False, "pumpkin_already_present")

        if len(_non_support_plants(tile_plants)) > 1:
            return PlacementResult(False, "tile_occupied")

    elif plant_type_id == COB_CANNON_TYPE_ID:
        if not _has_required_cob_pair(state, row, col):
            return PlacementResult(False, "cob_cannon_requires_kernel_pair")

    elif plant_type_id in UPGRADE_BASE_TYPE_IDS:
        if not _has_required_upgrade_base(
            tile_plants,
            UPGRADE_BASE_TYPE_IDS[plant_type_id],
        ):
            return PlacementResult(False, "upgrade_requires_base")

    elif _is_roof_scene(state.scene):
        if tile_plants and (
            plant_type_id == FLOWER_POT_TYPE_ID
            or _tile_has_non_support_plant(
                tile_plants,
                FLOWER_POT_TYPE_ID,
            )
        ):
            return PlacementResult(False, "tile_occupied")

    elif _is_pool_water_tile(state, row):
        if tile_plants and (
            plant_type_id == LILY_PAD_TYPE_ID
            or _tile_has_non_support_plant(
                tile_plants,
                LILY_PAD_TYPE_ID,
            )
        ):
            return PlacementResult(False, "tile_occupied")

    elif tile_plants:
        return PlacementResult(False, "tile_occupied")

    return PlacementResult(True, "valid")


# Kept as an alias for callers using the initial placement helper name.
check_placement = can_plant
