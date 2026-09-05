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

# Board::PixelToGridX/Y in the supported game maps lawn cells from x=80 in
# 80-pixel columns and y=80 in either 100-pixel (normal) or 85-pixel
# (pool/fog) rows.  These are input-cell centres, not Plant render origins.
TILE_FIRST_CENTER_X = 120
TILE_COLUMN_STEP = 80
NORMAL_TILE_FIRST_CENTER_Y = 130
NORMAL_TILE_ROW_STEP = 100
POOL_TILE_FIRST_CENTER_Y = 122
POOL_TILE_ROW_STEP = 85

# Seed packets are 50x70 logical pixels.  Board::GetSeedPacketPositionX
# supplies an origin that varies with the packet count; click their centres.
SEED_PACKET_WIDTH = 50
SEED_FIRST_PACKET_X_BY_COUNT = {
    **{count: 85 for count in range(1, 8)},
    8: 81,
    9: 80,
    10: 79,
}
SEED_SLOT_STEP_BY_COUNT = {
    **{count: 59 for count in range(1, 8)},
    8: 54,
    9: 52,
    10: 51,
}
SEED_CENTER_Y = 43

POOL_SCENES = frozenset({2, 3})
ROOF_SCENE = 4

# The game's shovel button begins at logical x=456 and is 70x72 pixels.  Its
# seed bank widens for seven or more packets, shifting the whole button right.
SHOVEL_BUTTON_BASE_X = 456
SHOVEL_BUTTON_CENTER_OFFSET_X = 35
SHOVEL_BUTTON_CENTER_Y = 36
SEED_BANK_EXTRA_WIDTHS = {
    7: 60,
    8: 76,
    9: 112,
    10: 153,
}


def tile_to_client(row: int, col: int, *, scene: int | None = None) -> tuple[int, int]:
    """Return a logical input-cell centre for a zero-based lawn tile.

    ``scene`` is optional for source compatibility.  Omitting it preserves the
    v0.2.0 pool/fog mapping; the controller always supplies observed state.
    """
    if not 0 <= row < BOARD_ROWS:
        raise ValueError(f"row must be in 0..{BOARD_ROWS - 1}")

    if not 0 <= col < BOARD_COLS:
        raise ValueError(f"col must be in 0..{BOARD_COLS - 1}")

    if scene is not None and not isinstance(scene, int):
        raise ValueError("scene must be an integer")

    if scene in POOL_SCENES or scene is None:
        first_y, row_step = POOL_TILE_FIRST_CENTER_Y, POOL_TILE_ROW_STEP
    elif scene == ROOF_SCENE:
        # Board::PixelToGridY removes this left-roof slope before resolving a
        # 85-pixel row.  Aim in the centre of that inverse input cell.
        first_y = NORMAL_TILE_FIRST_CENTER_Y + max(4 - col, 0) * 20
        row_step = POOL_TILE_ROW_STEP
    else:
        first_y, row_step = NORMAL_TILE_FIRST_CENTER_Y, NORMAL_TILE_ROW_STEP

    return (TILE_FIRST_CENTER_X + col * TILE_COLUMN_STEP, first_y + row * row_step)


def seed_slot_to_client(slot: int, *, seed_count: int = MAX_SEED_SLOTS) -> tuple[int, int]:
    """Return the logical client centre for a zero-based seed-bank slot.

    ``seed_count`` is read from ``GameState`` by the controller.  The default
    retains a callable two-argument-free helper for existing integrations.
    """
    if not 0 <= slot < MAX_SEED_SLOTS:
        raise ValueError(f"slot must be in 0..{MAX_SEED_SLOTS - 1}")
    if not 1 <= seed_count <= MAX_SEED_SLOTS:
        raise ValueError(f"seed count must be in 1..{MAX_SEED_SLOTS}")
    if slot >= seed_count:
        raise ValueError(f"slot must be in 0..{seed_count - 1}")

    return (
        SEED_FIRST_PACKET_X_BY_COUNT[seed_count]
        + SEED_PACKET_WIDTH // 2
        + slot * SEED_SLOT_STEP_BY_COUNT[seed_count],
        SEED_CENTER_Y,
    )


def shovel_to_client(seed_count: int) -> tuple[int, int]:
    """Return the shovel button center for the current in-level seed bank."""
    if not 1 <= seed_count <= MAX_SEED_SLOTS:
        raise ValueError(f"seed count must be in 1..{MAX_SEED_SLOTS}")

    return (
        SHOVEL_BUTTON_BASE_X
        + SEED_BANK_EXTRA_WIDTHS.get(seed_count, 0)
        + SHOVEL_BUTTON_CENTER_OFFSET_X,
        SHOVEL_BUTTON_CENTER_Y,
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
