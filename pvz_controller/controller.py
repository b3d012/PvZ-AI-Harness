"""Semantic PvZ actions built on normal Windows input."""

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from pvz_controller.coordinates import (
    pickup_to_client,
    seed_slot_to_client,
    shovel_to_client,
    tile_to_client,
)
from pvz_reader.placement import can_plant
from pvz_controller.windows_input import (
    ControllerInputError,
    CoordinateOutOfBounds,
    GameWindowUnavailable,
    WindowsInputBackend,
)

if TYPE_CHECKING:
    from pvz_reader.game_state import (
        GameState,
        PickupState,
        PlantState,
        SeedPacketState,
    )


# PvZ needs a brief moment to enter seed-placement mode after selecting a
# packet.  The target cursor move also settles before its click is sent.
SEED_SELECTION_SETTLE_DELAY = 0.10
TARGET_TILE_MOVE_SETTLE_DELAY = 0.03
SHOVEL_SELECTION_SETTLE_DELAY = 0.10


@dataclass(frozen=True)
class ActionResult:
    """Immediate outcome of a semantic action request.

    ``attempted`` is true once input for the requested action was issued.
    ``success`` remains ``None`` when a fresh observation is required to
    confirm the game-side result; ``reason`` is a stable diagnostic code.
    """

    attempted: bool
    success: bool | None
    reason: str


class PvZController:
    """Controller v1 actions backed by safe normal Windows input.

    Public callers use :meth:`collect_pickup`, :meth:`plant`, and
    :meth:`shovel` with observed game state, seed/pickup slots, and zero-based
    board coordinates.  Observation belongs to ``pvz_reader`` and placement
    legality remains in ``pvz_reader.placement``.
    """

    def __init__(self, input_backend=None):
        self._input = (
            input_backend
            if input_backend is not None
            else WindowsInputBackend()
        )

    def collect_pickup(
        self,
        state: "GameState | None",
        pickup_slot: int,
    ) -> ActionResult:
        """Click one currently collectible pickup resolved from ``state``.

        A successful input request reports ``success=None`` because collection
        must be confirmed from a subsequent observation.
        """
        if state is None:
            return ActionResult(False, False, "invalid_game_state")

        try:
            paused = state.paused
            pickups = state.pickups
        except AttributeError:
            return ActionResult(False, False, "invalid_game_state")

        if paused:
            return ActionResult(False, False, "game_paused")

        pickup = next(
            (
                candidate
                for candidate in pickups
                if candidate.slot == pickup_slot
            ),
            None,
        )

        if pickup is None:
            return ActionResult(False, False, "pickup_not_in_state")

        if pickup.collected or not pickup.collectible:
            return ActionResult(False, False, "pickup_unavailable")

        try:
            logical_x, logical_y = pickup_to_client(pickup.x, pickup.y)
            self._input.left_click(logical_x, logical_y)
        except CoordinateOutOfBounds as error:
            return ActionResult(False, False, f"coordinate_out_of_bounds:{error}")
        except GameWindowUnavailable as error:
            return ActionResult(False, False, f"game_window_unavailable:{error}")
        except ControllerInputError as error:
            return ActionResult(False, False, f"input_failed:{error}")
        except ValueError as error:
            return ActionResult(False, False, f"coordinate_out_of_bounds:{error}")

        return ActionResult(True, None, "click_issued")

    def plant(
        self,
        state: "GameState | None",
        seed_slot: int,
        row: int,
        col: int,
        stage_callback=None,
    ) -> ActionResult:
        """Plant ``seed_slot`` at a legal zero-based lawn tile.

        Placement legality is delegated entirely to :func:`can_plant`.  Both
        click points are validated before the seed packet is selected, so an
        invalid request cannot leave the game in seed-selection mode.  The
        optional ``stage_callback`` is for synchronous live-test diagnostics.
        """
        if state is None:
            return ActionResult(False, False, "invalid_game_state")

        try:
            paused = state.paused
            seeds = state.seeds
            state.scene
            state.plants
            state.grid_items
        except AttributeError:
            return ActionResult(False, False, "invalid_game_state")

        if paused:
            return ActionResult(False, False, "game_paused")

        try:
            seed_point = seed_slot_to_client(seed_slot)
        except (TypeError, ValueError) as error:
            return ActionResult(False, False, f"invalid_seed_slot:{error}")

        try:
            tile_point = tile_to_client(row, col)
        except (TypeError, ValueError) as error:
            return ActionResult(False, False, f"invalid_tile:{error}")

        try:
            seed = next((candidate for candidate in seeds if candidate.slot == seed_slot), None)
        except TypeError:
            return ActionResult(False, False, "invalid_game_state")

        if seed is None:
            return ActionResult(False, False, "invalid_seed_slot")

        placement = can_plant(state, seed_slot, row, col)
        if not placement.valid:
            return ActionResult(False, False, f"placement_invalid:{placement.reason}")

        if stage_callback is not None:
            stage_callback("clicking_seed_packet")

        try:
            self._input.left_click(*seed_point)
        except CoordinateOutOfBounds as error:
            return ActionResult(False, False, f"coordinate_out_of_bounds:{error}")
        except GameWindowUnavailable as error:
            return ActionResult(False, False, f"game_window_unavailable:{error}")
        except ControllerInputError as error:
            return ActionResult(False, False, f"input_failed:{error}")

        if stage_callback is not None:
            stage_callback("seed_click_issued")
            stage_callback("waiting_for_seed_selection")
        time.sleep(SEED_SELECTION_SETTLE_DELAY)

        if stage_callback is not None:
            stage_callback("moving_to_target_tile")
            stage_callback("clicking_target_tile")
        try:
            self._input.left_click(
                *tile_point,
                move_settle_delay=TARGET_TILE_MOVE_SETTLE_DELAY,
            )
        except CoordinateOutOfBounds as error:
            return ActionResult(True, False, f"coordinate_out_of_bounds:{error}")
        except GameWindowUnavailable as error:
            return ActionResult(True, False, f"game_window_unavailable:{error}")
        except ControllerInputError as error:
            return ActionResult(True, False, f"input_failed:{error}")

        if stage_callback is not None:
            stage_callback("tile_click_issued")
        return ActionResult(True, None, "clicks_issued")

    def shovel(
        self,
        state: "GameState | None",
        row: int,
        col: int,
    ) -> ActionResult:
        """Remove a currently observed plant from a zero-based lawn tile."""
        if state is None:
            return ActionResult(False, False, "invalid_game_state")

        try:
            paused = state.paused
            plants = state.plants
            seed_count = len(state.seeds)
        except (AttributeError, TypeError):
            return ActionResult(False, False, "invalid_game_state")

        if paused:
            return ActionResult(False, False, "game_paused")

        try:
            shovel_point = shovel_to_client(seed_count)
        except (TypeError, ValueError) as error:
            return ActionResult(False, False, f"coordinate_out_of_bounds:{error}")

        try:
            tile_point = tile_to_client(row, col)
        except (TypeError, ValueError) as error:
            return ActionResult(False, False, f"invalid_tile:{error}")

        if not any(plant.row == row and plant.col == col for plant in plants):
            return ActionResult(False, False, "no_plant_at_tile")

        try:
            self._input.left_click(*shovel_point)
        except CoordinateOutOfBounds as error:
            return ActionResult(False, False, f"coordinate_out_of_bounds:{error}")
        except GameWindowUnavailable as error:
            return ActionResult(False, False, f"game_window_unavailable:{error}")
        except ControllerInputError as error:
            return ActionResult(False, False, f"input_failed:{error}")

        time.sleep(SHOVEL_SELECTION_SETTLE_DELAY)

        try:
            self._input.left_click(
                *tile_point,
                move_settle_delay=TARGET_TILE_MOVE_SETTLE_DELAY,
            )
        except CoordinateOutOfBounds as error:
            return ActionResult(True, False, f"coordinate_out_of_bounds:{error}")
        except GameWindowUnavailable as error:
            return ActionResult(True, False, f"game_window_unavailable:{error}")
        except ControllerInputError as error:
            return ActionResult(True, False, f"input_failed:{error}")

        return ActionResult(True, None, "clicks_issued")


def pickup_was_collected(
    previous: "PickupState",
    current_state: "GameState | None",
) -> bool | None:
    """Check whether a pickup disappeared or became collected after a click."""
    if current_state is None:
        return None

    for current in current_state.pickups:
        if current.slot != previous.slot:
            continue

        # A different type in a reused slot is not the original pickup.
        if current.type_id != previous.type_id:
            return True

        return current.collected

    return True


def plant_was_placed(
    seed: "SeedPacketState",
    row: int,
    col: int,
    current_state: "GameState | None",
) -> bool | None:
    """Check whether a normal plant matching ``seed`` now occupies a tile."""
    if current_state is None:
        return None

    return any(
        plant.type_id == seed.type_id and plant.row == row and plant.col == col
        for plant in current_state.plants
    )


def plant_was_removed(
    previous: "PlantState",
    current_state: "GameState | None",
) -> bool | None:
    """Check whether a previously observed plant is gone from its tile."""
    if current_state is None:
        return None

    return not any(
        plant.type_id == previous.type_id
        and plant.row == previous.row
        and plant.col == previous.col
        for plant in current_state.plants
    )
