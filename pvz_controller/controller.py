"""Semantic PvZ actions built on normal Windows input."""

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from pvz_controller.coordinates import (
    pickup_to_client,
    seed_slot_to_client,
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
    from pvz_reader.game_state import GameState, PickupState, SeedPacketState


# PvZ needs a brief moment to enter seed-placement mode after selecting a
# packet.  The target cursor move also settles before its click is sent.
SEED_SELECTION_SETTLE_DELAY = 0.10
TARGET_TILE_MOVE_SETTLE_DELAY = 0.03


@dataclass(frozen=True)
class ActionResult:
    """Outcome known immediately after a semantic controller request."""

    attempted: bool
    success: bool | None
    reason: str


class PvZController:
    """Translate validated semantic actions into normal game input."""

    def __init__(self, input_backend=None):
        self._input = (
            input_backend
            if input_backend is not None
            else WindowsInputBackend()
        )

    def collect_pickup(
        self,
        state: "GameState",
        pickup_slot: int,
    ) -> ActionResult:
        """Click one currently collectible pickup resolved from ``state``.

        A successful input request reports ``success=None`` because collection
        must be confirmed from a subsequent observation.
        """
        if state.paused:
            return ActionResult(False, False, "game_paused")

        pickup = next(
            (
                candidate
                for candidate in state.pickups
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
        invalid request cannot leave the game in seed-selection mode.
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
