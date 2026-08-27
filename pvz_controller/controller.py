"""Semantic PvZ actions built on normal Windows input."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pvz_controller.coordinates import pickup_to_client
from pvz_controller.windows_input import (
    ControllerInputError,
    CoordinateOutOfBounds,
    GameWindowUnavailable,
    WindowsInputBackend,
)

if TYPE_CHECKING:
    from pvz_reader.game_state import GameState, PickupState


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
