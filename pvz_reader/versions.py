PVZ_VERSION = "1.2.0.1073"

OFFSETS = {
    "1.2.0.1073": {
        # -------------------------------------------------
        # Global
        # -------------------------------------------------
        "lawn": 0x729670,

        # LawnApp
        "board": 0x868,

        # -------------------------------------------------
        # Board
        # -------------------------------------------------
        "sun": 0x5578,
        "game_clock": 0x5580,
        "scene": 0x5564,
        "adventure_level": 0x5568,
        "game_paused": 0x17C,

        # -------------------------------------------------
        # Plants
        # -------------------------------------------------
        "plant": 0xC4,
        "plant_count_max": 0xC8,
        "plant_next_pos": 0xD0,

        "plant_struct_size": 0x14C,

        "plant_x": 0x08,
        "plant_y": 0x0C,
        "plant_row": 0x1C,
        "plant_type": 0x24,
        "plant_col": 0x28,

        "plant_state": 0x3C,
        "plant_hp": 0x40,
        "plant_max_hp": 0x44,

        "plant_imitater": 0x138,
        "plant_dead": 0x141,
        "plant_squished": 0x142,
        "plant_asleep": 0x143,

        # -------------------------------------------------
        # Zombies
        # -------------------------------------------------
        "zombie": 0xA8,
        "zombie_count_max": 0xAC,

        "zombie_struct_size": 0x168,

        "zombie_row": 0x1C,
        "zombie_type": 0x24,
        "zombie_status": 0x28,

        "zombie_x": 0x2C,
        "zombie_y": 0x30,

        "zombie_is_biting": 0x51,

        "zombie_slow_timer": 0xAC,
        "zombie_stun_timer": 0xB0,
        "zombie_freeze_timer": 0xB4,

        "zombie_hypnotized": 0xB8,

        # Health / armor
        "zombie_body_hp": 0xC8,
        "zombie_body_max_hp": 0xCC,

        "zombie_armor_hp": 0xD0,
        "zombie_armor_max_hp": 0xD4,

        "zombie_dead": 0xEC,

        # -------------------------------------------------
        # Lawn mowers
        # -------------------------------------------------
        "lawn_mower": 0x118,
        "lawn_mower_dead": 0x30,
        "lawn_mower_count_max": 0x11C,
        "lawn_mower_count": 0x128,

        # -------------------------------------------------
        # Grid objects
        # -------------------------------------------------
        "grid_item": 0x134,
        "grid_item_type": 0x08,
        "grid_item_col": 0x10,
        "grid_item_row": 0x14,
        "grid_item_dead": 0x20,
        "grid_item_count_max": 0x138,

        # -------------------------------------------------
        # Seed bank
        # -------------------------------------------------
        "slot": 0x15C,

        "slot_count": 0x24,
        "slot_struct_size": 0x50,

        "slot_seed_cd_past": 0x4C,
        "slot_seed_cd_total": 0x50,

        "slot_seed_type": 0x5C,
        "slot_seed_type_im": 0x60,

        # Seed packet state
        "slot_seed_ready": 0x70,
        "slot_seed_cooling_down": 0x71,
        "slot_seed_use_counter": 0x74,
    }
}