"""Logical PvZ client-coordinate helpers.

Plants vs. Zombies renders into an 800x600 logical client.  These helpers
return logical client points only; window-relative scaling and screen
translation belong to the Windows input backend.
"""

import math


LOGICAL_CLIENT_WIDTH = 800
LOGICAL_CLIENT_HEIGHT = 600

BOARD_ROWS = 6
BOARD_COLS = 9
MAX_SEED_SLOTS = 10

# Standard lawn column centers.  The six-row Y centers match pool/fog board
# geometry and remain safely inside each normal lawn row.
TILE_FIRST_CENTER_X = 80
TILE_COLUMN_STEP = 80
TILE_FIRST_CENTER_Y = 125
TILE_ROW_STEP = 85

# Seed packets are 50x70 logical pixels.  In the in-level seed bank, the first
# packet begins at x=80 and y=8, so these points target packet centers.
SEED_FIRST_CENTER_X = 105
SEED_CENTER_Y = 43
SEED_SLOT_STEP = 50


def tile_to_client(row: int, col: int) -> tuple[int, int]:
    """Return the logical client center for a zero-based lawn tile."""
    if not 0 <= row < BOARD_ROWS:
        raise ValueError(f"row must be in 0..{BOARD_ROWS - 1}")

    if not 0 <= col < BOARD_COLS:
        raise ValueError(f"col must be in 0..{BOARD_COLS - 1}")

    return (
        TILE_FIRST_CENTER_X + col * TILE_COLUMN_STEP,
        TILE_FIRST_CENTER_Y + row * TILE_ROW_STEP,
    )


def seed_slot_to_client(slot: int) -> tuple[int, int]:
    """Return the logical client center for a zero-based seed-bank slot."""
    if not 0 <= slot < MAX_SEED_SLOTS:
        raise ValueError(f"slot must be in 0..{MAX_SEED_SLOTS - 1}")

    return (
        SEED_FIRST_CENTER_X + slot * SEED_SLOT_STEP,
        SEED_CENTER_Y,
    )


def pickup_to_client(x: float, y: float) -> tuple[int, int]:
    """Convert an observed pickup position to a logical client click point."""
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("pickup coordinates must be finite")

    point = (round(x), round(y))
    _validate_client_point(*point)
    return point


def scale_logical_to_client(
    x: int,
    y: int,
    client_width: int,
    client_height: int,
) -> tuple[int, int]:
    """Scale an 800x600 logical point into an actual client rectangle."""
    _validate_client_point(x, y)

    if client_width <= 0 or client_height <= 0:
        raise ValueError("client dimensions must be positive")

    scaled_x = round(x * client_width / LOGICAL_CLIENT_WIDTH)
    scaled_y = round(y * client_height / LOGICAL_CLIENT_HEIGHT)

    # Rounding near the bottom/right edge must never escape the client.
    return (
        min(scaled_x, client_width - 1),
        min(scaled_y, client_height - 1),
    )


def _validate_client_point(x: int, y: int) -> None:
    if not 0 <= x < LOGICAL_CLIENT_WIDTH:
        raise ValueError("logical x coordinate is outside the client")

    if not 0 <= y < LOGICAL_CLIENT_HEIGHT:
        raise ValueError("logical y coordinate is outside the client")
