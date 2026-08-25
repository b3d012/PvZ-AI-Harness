from dataclasses import dataclass, asdict
from typing import Optional

from pvz_reader.memory import MemoryReader
from pvz_reader.versions import OFFSETS, PVZ_VERSION


PLANT_NAMES = [
    "Peashooter",
    "Sunflower",
    "Cherry Bomb",
    "Wall-nut",
    "Potato Mine",
    "Snow Pea",
    "Chomper",
    "Repeater",
    "Puff-shroom",
    "Sun-shroom",
    "Fume-shroom",
    "Grave Buster",
    "Hypno-shroom",
    "Scaredy-shroom",
    "Ice-shroom",
    "Doom-shroom",
    "Lily Pad",
    "Squash",
    "Threepeater",
    "Tangle Kelp",
    "Jalapeno",
    "Spikeweed",
    "Torchwood",
    "Tall-nut",
    "Sea-shroom",
    "Plantern",
    "Cactus",
    "Blover",
    "Split Pea",
    "Starfruit",
    "Pumpkin",
    "Magnet-shroom",
    "Cabbage-pult",
    "Flower Pot",
    "Kernel-pult",
    "Coffee Bean",
    "Garlic",
    "Umbrella Leaf",
    "Marigold",
    "Melon-pult",
    "Gatling Pea",
    "Twin Sunflower",
    "Gloom-shroom",
    "Cattail",
    "Winter Melon",
    "Gold Magnet",
    "Spikerock",
    "Cob Cannon",
]

PLANT_COSTS = [
    100,  # Peashooter
    50,   # Sunflower
    150,  # Cherry Bomb
    50,   # Wall-nut
    25,   # Potato Mine
    175,  # Snow Pea
    150,  # Chomper
    200,  # Repeater
    0,    # Puff-shroom
    25,   # Sun-shroom
    75,   # Fume-shroom
    75,   # Grave Buster
    75,   # Hypno-shroom
    25,   # Scaredy-shroom
    75,   # Ice-shroom
    125,  # Doom-shroom
    25,   # Lily Pad
    50,   # Squash
    325,  # Threepeater
    25,   # Tangle Kelp
    125,  # Jalapeno
    100,  # Spikeweed
    175,  # Torchwood
    125,  # Tall-nut
    0,    # Sea-shroom
    25,   # Plantern
    125,  # Cactus
    100,  # Blover
    125,  # Split Pea
    125,  # Starfruit
    125,  # Pumpkin
    100,  # Magnet-shroom
    100,  # Cabbage-pult
    25,   # Flower Pot
    100,  # Kernel-pult
    75,   # Coffee Bean
    50,   # Garlic
    100,  # Umbrella Leaf
    50,   # Marigold
    300,  # Melon-pult
    250,  # Gatling Pea
    150,  # Twin Sunflower
    150,  # Gloom-shroom
    225,  # Cattail
    200,  # Winter Melon
    50,   # Gold Magnet
    125,  # Spikerock
    500,  # Cob Cannon
]

ZOMBIE_NAMES = [
    "Zombie",
    "Flag Zombie",
    "Conehead Zombie",
    "Pole Vaulting Zombie",
    "Buckethead Zombie",
    "Newspaper Zombie",
    "Screen Door Zombie",
    "Football Zombie",
    "Dancing Zombie",
    "Backup Dancer",
    "Ducky Tube Zombie",
    "Snorkel Zombie",
    "Zomboni",
    "Zombie Bobsled Team",
    "Dolphin Rider Zombie",
    "Jack-in-the-Box Zombie",
    "Balloon Zombie",
    "Digger Zombie",
    "Pogo Zombie",
    "Zombie Yeti",
    "Bungee Zombie",
    "Ladder Zombie",
    "Catapult Zombie",
    "Gargantuar",
    "Imp",
    "Dr. Zomboss",
    "Peashooter Zombie",
    "Wall-nut Zombie",
    "Jalapeno Zombie",
    "Gatling Pea Zombie",
    "Squash Zombie",
    "Tall-nut Zombie",
    "Giga Gargantuar",
]


@dataclass
class PlantState:
    slot: int
    type_id: int
    name: str

    row: int
    col: int

    x: int
    y: int

    state: int

    hp: int
    max_hp: int

    asleep: bool
    imitater: int


@dataclass
class ZombieState:
    slot: int
    type_id: int
    name: str

    row: int

    x: float
    y: float

    state: int

    body_hp: int
    body_max_hp: int

    armor_hp: int
    armor_max_hp: int

    biting: bool
    hypnotized: bool

    slow_timer: int
    stun_timer: int
    freeze_timer: int

@dataclass
class SeedPacketState:
    slot: int

    type_id: int
    name: str

    imitater_target_id: Optional[int]

    cost: int

    cooldown_elapsed: int
    cooldown_total: int
    cooldown_ratio: float

    ready: bool
    cooling_down: bool
    selected: bool

    affordable: bool
    actionable: bool

    use_counter: int

@dataclass
class GameState:
    sun: int
    game_clock: int
    scene: int
    adventure_level: int
    paused: bool

    plant_capacity: int
    zombie_capacity: int

    plants: list[PlantState]
    zombies: list[ZombieState]

    seeds: list[SeedPacketState]

    def to_dict(self):
        return asdict(self)


class PvZGameStateReader:
    def __init__(self, memory: MemoryReader):
        self.memory = memory
        self.o = OFFSETS[PVZ_VERSION]

    def get_lawn(self) -> int:
        return self.memory.read_pointer(self.o["lawn"])

    def get_board(self) -> int:
        lawn = self.get_lawn()

        if lawn == 0:
            return 0

        return self.memory.read_pointer(
            lawn + self.o["board"]
        )

    @staticmethod
    def _plant_name(type_id: int) -> str:
        if 0 <= type_id < len(PLANT_NAMES):
            return PLANT_NAMES[type_id]

        return f"UnknownPlant({type_id})"

    @staticmethod
    def _zombie_name(type_id: int) -> str:
        if 0 <= type_id < len(ZOMBIE_NAMES):
            return ZOMBIE_NAMES[type_id]

        return f"UnknownZombie({type_id})"

    def read_plants(self, board: int) -> list[PlantState]:
        plant_array = self.memory.read_pointer(
            board + self.o["plant"]
        )

        capacity = self.memory.read_uint(
            board + self.o["plant_count_max"]
        )

        plants = []

        # Safety guard against garbage offsets.
        if plant_array == 0 or capacity > 1000:
            return plants

        struct_size = self.o["plant_struct_size"]

        for i in range(capacity):
            addr = plant_array + i * struct_size

            dead = self.memory.read_bool(
                addr + self.o["plant_dead"]
            )

            squished = self.memory.read_bool(
                addr + self.o["plant_squished"]
            )

            if dead or squished:
                continue

            type_id = self.memory.read_int(
                addr + self.o["plant_type"]
            )

            row = self.memory.read_int(
                addr + self.o["plant_row"]
            )

            col = self.memory.read_int(
                addr + self.o["plant_col"]
            )

            # Basic sanity checking.
            if not (0 <= type_id <= 47):
                continue

            if not (0 <= row <= 5):
                continue

            if not (0 <= col <= 8):
                continue

            plants.append(
                PlantState(
                    slot=i,
                    type_id=type_id,
                    name=self._plant_name(type_id),

                    row=row,
                    col=col,

                    x=self.memory.read_int(
                        addr + self.o["plant_x"]
                    ),

                    y=self.memory.read_int(
                        addr + self.o["plant_y"]
                    ),

                    state=self.memory.read_int(
                        addr + self.o["plant_state"]
                    ),

                    hp=self.memory.read_int(
                        addr + self.o["plant_hp"]
                    ),

                    max_hp=self.memory.read_int(
                        addr + self.o["plant_max_hp"]
                    ),

                    asleep=self.memory.read_bool(
                        addr + self.o["plant_asleep"]
                    ),

                    imitater=self.memory.read_int(
                        addr + self.o["plant_imitater"]
                    ),
                )
            )

        return plants

    def read_zombies(self, board: int) -> list[ZombieState]:
        zombie_array = self.memory.read_pointer(
            board + self.o["zombie"]
        )

        capacity = self.memory.read_uint(
            board + self.o["zombie_count_max"]
        )

        zombies = []

        if zombie_array == 0 or capacity > 2000:
            return zombies

        struct_size = self.o["zombie_struct_size"]

        for i in range(capacity):
            addr = zombie_array + i * struct_size

            dead = self.memory.read_bool(
                addr + self.o["zombie_dead"]
            )

            if dead:
                continue

            type_id = self.memory.read_int(
                addr + self.o["zombie_type"]
            )

            row = self.memory.read_int(
                addr + self.o["zombie_row"]
            )

            # Strong sanity filters.
            if not (0 <= type_id <= 32):
                continue

            if not (0 <= row <= 5):
                continue

            body_hp = self.memory.read_int(
                addr + self.o["zombie_body_hp"]
            )

            body_max_hp = self.memory.read_int(
                addr + self.o["zombie_body_max_hp"]
            )

            armor_hp = self.memory.read_int(
                addr + self.o["zombie_armor_hp"]
            )

            armor_max_hp = self.memory.read_int(
                addr + self.o["zombie_armor_max_hp"]
            )

            zombies.append(
                ZombieState(
                    slot=i,
                    type_id=type_id,
                    name=self._zombie_name(type_id),

                    row=row,

                    x=self.memory.read_float(
                        addr + self.o["zombie_x"]
                    ),

                    y=self.memory.read_float(
                        addr + self.o["zombie_y"]
                    ),

                    state=self.memory.read_int(
                        addr + self.o["zombie_status"]
                    ),

                    body_hp=body_hp,
                    body_max_hp=body_max_hp,

                    armor_hp=armor_hp,
                    armor_max_hp=armor_max_hp,

                    biting=self.memory.read_bool(
                        addr + self.o["zombie_is_biting"]
                    ),

                    hypnotized=self.memory.read_bool(
                        addr + self.o["zombie_hypnotized"]
                    ),

                    slow_timer=self.memory.read_int(
                        addr + self.o["zombie_slow_timer"]
                    ),

                    stun_timer=self.memory.read_int(
                        addr + self.o["zombie_stun_timer"]
                    ),

                    freeze_timer=self.memory.read_int(
                        addr + self.o["zombie_freeze_timer"]
                    ),
                )
            )

        return zombies

    def read_seed_bank(self, board: int) -> list[SeedPacketState]:
        slot_bank = self.memory.read_pointer(
            board + self.o["slot"]
        )

        if slot_bank == 0:
            return []

        slot_count = self.memory.read_uint(
            slot_bank + self.o["slot_count"]
        )

        # Normal PvZ supports up to 10 seed packets.
        # Guard against corrupt pointers / bad offsets.
        if slot_count > 10:
            return []

        struct_size = self.o["slot_struct_size"]

        seeds = []

        sun = self.memory.read_int(
                board + self.o["sun"]
            )
        
        for i in range(slot_count):
            addr = slot_bank + i * struct_size

            # -------------------------------------------------
            # Seed identity
            # -------------------------------------------------
            type_id = self.memory.read_int(
                addr + self.o["slot_seed_type"]
            )

            imitater_raw = self.memory.read_int(
                addr + self.o["slot_seed_type_im"]
            )
            

            if type_id == 48:
                imitater_target_id = imitater_raw

                if 0 <= imitater_target_id < len(PLANT_NAMES):
                    name = (
                        f"Imitater("
                        f"{PLANT_NAMES[imitater_target_id]}"
                        f")"
                    )
                else:
                    name = (
                        f"Imitater("
                        f"Unknown:{imitater_target_id}"
                        f")"
                    )

            else:
                imitater_target_id = None

                if 0 <= type_id < len(PLANT_NAMES):
                    name = PLANT_NAMES[type_id]
                else:
                    name = f"UnknownSeed({type_id})"

            effective_type_id = (
                imitater_target_id
                if type_id == 48 and imitater_target_id is not None
                else type_id
            )

            if 0 <= effective_type_id < len(PLANT_COSTS):
                cost = PLANT_COSTS[effective_type_id]
            else:
                cost = 0
            # -------------------------------------------------
            # Cooldown
            # -------------------------------------------------
            cooldown_elapsed = self.memory.read_int(
                addr + self.o["slot_seed_cd_past"]
            )

            cooldown_total = self.memory.read_int(
                addr + self.o["slot_seed_cd_total"]
            )

            # -------------------------------------------------
            # Packet state
            #
            # GOTY 1.2.0.1073 live testing:
            #
            # +0x70 = 1, +0x71 = 0 -> READY
            # +0x70 = 0, +0x71 = 1 -> COOLDOWN
            # +0x70 = 0, +0x71 = 0 -> SELECTED
            # -------------------------------------------------
            ready_raw = self.memory.read_byte(
                addr + self.o["slot_seed_ready"]
            )

            cooling_raw = self.memory.read_byte(
                addr + self.o["slot_seed_cooling_down"]
            )

            ready = (
                ready_raw == 1
                and cooling_raw == 0
            )

            cooling_down = (
                ready_raw == 0
                and cooling_raw == 1
            )

            selected = (
                ready_raw == 0
                and cooling_raw == 0
            )

            # -------------------------------------------------
            # Recharge progress
            # -------------------------------------------------
            if cooling_down and cooldown_total > 0:
                cooldown_ratio = (
                    cooldown_elapsed / cooldown_total
                )

                cooldown_ratio = max(
                    0.0,
                    min(1.0, cooldown_ratio)
                )

            elif ready or selected:
                # Once naturally charged, PvZ resets/changes the
                # raw cooldown values, so the packet-state bytes
                # are more reliable than the counters.
                cooldown_ratio = 1.0

            else:
                cooldown_ratio = 0.0

            
            affordable = sun >= cost

            actionable = (
                ready
                and affordable
            )
            # -------------------------------------------------
            # Candidate use counter
            #
            # +0x74 incremented when the packet was planted in
            # our tests. Keep treating this as provisional until
            # we've validated it over more cases.
            # -------------------------------------------------
            use_counter = self.memory.read_byte(
                addr + self.o["slot_seed_use_counter"]
            )

            seeds.append(
                SeedPacketState(
                    slot=i,

                    type_id=type_id,
                    name=name,

                    imitater_target_id=imitater_target_id,

                    cost=cost,

                    cooldown_elapsed=cooldown_elapsed,
                    cooldown_total=cooldown_total,
                    cooldown_ratio=cooldown_ratio,

                    ready=ready,
                    cooling_down=cooling_down,
                    selected=selected,

                    affordable=affordable,
                    actionable=actionable,

                    use_counter=use_counter,
                )
            )

        return seeds


    def read(self) -> Optional[GameState]:
        board = self.get_board()

        if board == 0:
            return None

        plants = self.read_plants(board)
        zombies = self.read_zombies(board)
        seeds = self.read_seed_bank(board)

        return GameState(
            sun=self.memory.read_int(
                board + self.o["sun"]
            ),

            game_clock=self.memory.read_int(
                board + self.o["game_clock"]
            ),

            scene=self.memory.read_int(
                board + self.o["scene"]
            ),

            adventure_level=self.memory.read_int(
                board + self.o["adventure_level"]
            ),

            paused=self.memory.read_bool(
                board + self.o["game_paused"]
            ),

            plant_capacity=self.memory.read_uint(
                board + self.o["plant_count_max"]
            ),

            zombie_capacity=self.memory.read_uint(
                board + self.o["zombie_count_max"]
            ),

            plants=plants,
            zombies=zombies,
            seeds=seeds,
        )