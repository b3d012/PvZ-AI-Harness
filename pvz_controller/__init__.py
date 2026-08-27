"""Controller v1 semantic input API for Plants vs. Zombies.

Callers supply observed ``GameState`` data and semantic slots or zero-based
board coordinates.  They never need desktop or raw client coordinates:
window targeting and normal Windows mouse input remain internal details.
"""

CONTROLLER_VERSION = 1

from pvz_controller.controller import (
    ActionResult,
    PvZController,
    plant_was_removed,
    plant_was_placed,
    pickup_was_collected,
)

__all__ = [
    "CONTROLLER_VERSION",
    "ActionResult",
    "PvZController",
    "plant_was_removed",
    "plant_was_placed",
    "pickup_was_collected",
]
