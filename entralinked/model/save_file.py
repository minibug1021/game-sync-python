"""Read what the Game Sync needs out of an uploaded Gen 5 save file.

That is the Trainer data, the tucked-in Pokémon, and (Black 2 / White 2) the Medals.

Adapted from PKHeX.
"""
import json
import struct
from datetime import date
from enum import IntEnum
from typing import Any

from utils.constants import Rom

from ..paths import DATA_DIR

PKM_STORED_SIZE = 136
PKM_HEADER_SIZE = 8

BLOCK_SIZE = 32
BLOCK_COUNT = 4

# Stored Pokémon are made of four 32-byte blocks, and the shuffle value picks one of 32 orders
# for them. Each group of four entries is one order (PokeCrypto.BlockPosition).
BLOCK_POSITION = [
    0, 1, 2, 3,  0, 1, 3, 2,  0, 2, 1, 3,  0, 3, 1, 2,
    0, 2, 3, 1,  0, 3, 2, 1,  1, 0, 2, 3,  1, 0, 3, 2,
    2, 0, 1, 3,  3, 0, 1, 2,  2, 0, 3, 1,  3, 0, 2, 1,
    1, 2, 0, 3,  1, 3, 0, 2,  2, 1, 0, 3,  3, 1, 0, 2,
    2, 3, 0, 1,  3, 2, 0, 1,  1, 2, 3, 0,  1, 3, 2, 0,
    2, 1, 3, 0,  3, 1, 2, 0,  2, 3, 1, 0,  3, 2, 1, 0,

    0, 1, 2, 3,  0, 1, 3, 2,  0, 2, 1, 3,  0, 3, 1, 2,
    0, 2, 3, 1,  0, 3, 2, 1,  1, 0, 2, 3,  1, 0, 3, 2,
]


class Block(IntEnum):
    """The save blocks with data used by the Game Sync server."""

    TRAINER_DATA = 27
    GLOBAL_LINK = 35  # Dream World data, with the tucked-in Pokémon and the Loblolly items
    MISC = 52  # badges, money
    MEDAL = 68  # Black 2 / White 2 only


# Location of each block in the save file as (offset, length).
BLOCKS_BW = {
    Block.TRAINER_DATA: (0x19400, 0x0068),
    Block.GLOBAL_LINK:  (0x1D300, 0x01AC),
    Block.MISC:         (0x21200, 0x00EC)
}
BLOCKS_B2W2 = {
    Block.TRAINER_DATA: (0x19400, 0x00B0),
    Block.GLOBAL_LINK:  (0x1D300, 0x01AC),
    Block.MISC:         (0x21100, 0x00F0),
    Block.MEDAL:        (0x25300, 0x0498)
}


class SaveFileError(ValueError):
    """The upload isn't a save file this module can read."""


def _load_table(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="UTF-8"))


# Codepoints the Gen5 fonts can render.
VALID_CHARS = frozenset(
    code for first, last in _load_table("valid_char_ranges.json") for code in range(first, last + 1)
)
# National Pokédex number -> form -> (type 1, type 2 or None, experience group)
PERSONAL_DATA: dict[int, dict[int, tuple[int, int | None, int]]] = {
    int(species): {int(form): tuple(data) for form, data in forms.items()}
    for species, forms in _load_table("personal.json").items()
}

STRING_TERMINATOR = 0xFFFF
# Gen5 stores the gender signs as private characters
_GENDER_SIGNS = {0x246D: "♂", 0x246E: "♀"}

MAX_LEVEL = 100


# ----------------------
# Pokémon decryption
# ----------------------

def _crypt_array(data: bytearray, seed: int) -> None:
    """XOR `data` in place with the games' linear congruential generator."""
    seed &= 0xFFFFFFFF
    view = memoryview(data).cast("H")
    for i in range(len(view)):
        seed = (0x41C64E6D * seed + 0x00006073) & 0xFFFFFFFF
        view[i] ^= (seed >> 16) & 0xFFFF


def _unshuffle_blocks(data: bytes | bytearray, shuffle_value: int) -> bytes:
    """Put the four blocks of a stored Pokémon back in order (PokeCrypto.ShuffleArray)."""
    order = BLOCK_POSITION[shuffle_value * BLOCK_COUNT:(shuffle_value + 1) * BLOCK_COUNT]
    return b"".join(data[block * BLOCK_SIZE:(block + 1) * BLOCK_SIZE] for block in order)


def _decrypt_pkm(raw: bytes) -> bytes:
    """Decrypt a stored (136-byte) Pokémon.

    The first 8 bytes aren't encrypted. They hold the personality value, which picks the
    block order, and the checksum.
    """
    personality_value, = struct.unpack_from("<I", raw, 0)
    checksum, = struct.unpack_from("<H", raw, 6)

    main_block = bytearray(raw[PKM_HEADER_SIZE:PKM_STORED_SIZE])
    _crypt_array(main_block, checksum)
    return bytes(raw[:PKM_HEADER_SIZE]) + _unshuffle_blocks(main_block, (personality_value >> 13) & 31)


# -----------------
# Experience
# -----------------

def _exp_for_level(group: int, n: int) -> int:
    """Return the total experience a Pokémon of an experience group has at level `n`."""
    cube = n**3

    if group == 0:  # Medium Fast
        return cube
    if group == 1:  # Erratic
        if n < 50:
            return cube * (100 - n) // 50
        if n < 68:
            return cube * (150 - n) // 100
        if n < 98:
            return cube * ((1911 - 10 * n) // 3) // 500
        return cube * (160 - n) // 100
    if group == 2:  # Fluctuating
        if n < 15:
            return cube * ((n + 1) // 3 + 24) // 50
        if n < 36:
            return cube * (n + 14) // 50
        return cube * (n // 2 + 32) // 50
    if group == 3:  # Medium Slow
        return max(0, 6 * cube // 5 - 15 * n**2 + 100 * n - 140)
    if group == 4:  # Fast
        return 4 * cube // 5
    if group == 5:  # Slow
        return 5 * cube // 4

    raise SaveFileError(f"Unknown experience group {group}")


def level_for_exp(group: int, total_exp: int) -> int:
    """Return the level of a Pokémon with `total_exp` experience."""
    for level in range(MAX_LEVEL, 1, -1):
        if total_exp >= _exp_for_level(group, level):
            return level
    return 1


# -----------------
# Readers
# -----------------

class DataReader:
    """Reads little-endian fields out of a block of bytes."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read_str(self, offset: int, length: int) -> str:
        """Read a UTF-16 string of at most `length` bytes, up to its terminator.

        Characters the DS can't show come back as "?".
        """
        codes = struct.unpack_from(f"<{length // 2}H", self._data, offset)
        if STRING_TERMINATOR in codes:
            codes = codes[:codes.index(STRING_TERMINATOR)]

        text = "".join(_GENDER_SIGNS.get(code) or chr(code) for code in codes)
        return "".join(char if ord(char) in VALID_CHARS else "?" for char in text)

    def read_int(self, offset: int, length: int) -> int:
        """Read an unsigned integer of `length` bytes."""
        return int.from_bytes(self._data[offset:offset + length], "little")

    def read_bits(self, offset: int, bit_index: int, length: int = 1) -> int:
        """`length` bits of the byte at `offset`, starting at bit `bit_index`."""
        return (self._data[offset] >> bit_index) & ((1 << length) - 1)


class MedalBlock(DataReader):
    """The Medal block of a Black 2 / White 2 save."""

    MAX_MEDALS = 255
    MEDAL_SIZE = 4
    EPOCH_YEAR = 2000
    STATE_OBTAINED = 4
    FAVORITE_OFFSET = 0x3FC

    @property
    def favorite_medal(self) -> int:
        """The Medal the player shows off."""
        return self._data[self.FAVORITE_OFFSET]

    @property
    def medal_list(self) -> list[int]:
        """The ids of the obtained Medals, newest first (lowest id first within a day)."""
        medals = []

        for medal_id in range(self.MAX_MEDALS):
            offset = self.MEDAL_SIZE * medal_id

            if self.read_bits(offset + 2, 0, 3) == self.STATE_OBTAINED:
                medals.append((self.parse_date(self.read_int(offset, 2)), -medal_id))

        return [-negated_id for _, negated_id in sorted(medals, reverse=True)]

    @classmethod
    def parse_date(cls, raw_date: int) -> date:
        """Unpack a date stored as 7 bits of year (since 2000), 4 of month, and 5 of day."""
        return date((raw_date & 0x7F) + cls.EPOCH_YEAR, (raw_date >> 7) & 0xF, raw_date >> 11)


class Trainer(DataReader):
    """The player, from the trainer data block."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)

        self.name = self.read_str(0x4, 0x10)
        self.country = self.read_int(0x1C, 1)
        self.region = self.read_int(0x1D, 1)
        self.language = self.read_int(0x1E, 1)
        self.game = self.read_int(0x1F, 1)  # a utils.constants.Rom value
        self.gender = 0 if self.read_int(0x21, 1) == 0 else 1  # 0 = male, 1 = female
        self.played_hours = self.read_int(0x24, 2)
        self.played_minutes = self.read_int(0x26, 1)


class GlobalLink(DataReader):
    """The Dream World block (PKHeX GlobalLink5)."""

    POKEMON_OFFSET = 0x8
    LOBLOLLY_OFFSET = 0x120
    LOBLOLLY_SIZE = 26
    LOBLOLLY_SLOTS = 5
    LOBLOLLY_EMPTY = 0x7E  # the id of a slot that was never filled
    SELECTED_LOBLOLLY_OFFSET = 0x1A6  # low 7 bits indicate the chosen slot (0x7F for none)

    @property
    def loblolly_decor(self) -> int | None:
        """The id of the Loblolly item the player picked for their room, if they picked one."""
        slot = self._data[self.SELECTED_LOBLOLLY_OFFSET] & 0x7F
        if slot >= self.LOBLOLLY_SLOTS:
            return None

        item_id = self.read_int(self.LOBLOLLY_OFFSET + slot * self.LOBLOLLY_SIZE, 2)
        return None if item_id == self.LOBLOLLY_EMPTY else item_id

    @property
    def pokemon(self) -> "Pokemon | None":
        """The tucked-in Pokémon. None if the slot is empty."""
        raw = self._data[self.POKEMON_OFFSET:self.POKEMON_OFFSET + PKM_STORED_SIZE]
        pokemon = Pokemon(_decrypt_pkm(raw))
        return pokemon if pokemon.natdex else None


class Pokemon(DataReader):
    """A decrypted stored Pokémon."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)

        # Outside the encrypted part. Decides shininess together with the trainer ids.
        self.personality_value = self.read_int(0x00, 4)
        self.natdex = self.read_int(0x08, 2)
        self.trainer_id = self.read_int(0x0C, 2)
        self.trainer_id_secret = self.read_int(0x0E, 2)
        self.exp = self.read_int(0x10, 4)
        # 0 = male, 1 = female, 2 = genderless
        self.gender = 1 if self.read_bits(0x40, 1) else 2 if self.read_bits(0x40, 2) else 0
        self.form = self.read_bits(0x40, 3, 5)
        self.nature = self.read_int(0x41, 1)
        self.nickname = self.read_str(0x48, 20)
        self.trainer_name = self.read_str(0x68, 18)
        self.ball = self.read_int(0x83, 1)

    def _personal(self) -> tuple[int, int | None, int]:
        forms = PERSONAL_DATA.get(self.natdex)
        if forms is None:
            raise SaveFileError(f"Unknown Pokémon species {self.natdex}")
        return forms.get(self.form) or forms[0]

    @property
    def types(self) -> tuple[int, int | None]:
        """(type 1, type 2). Type 2 is None for a single-type Pokémon."""
        type1, type2, _ = self._personal()
        return type1, type2

    @property
    def level(self) -> int:
        """Worked out from the experience, as a stored Pokémon has no level field."""
        return level_for_exp(self._personal()[2], self.exp)


class SaveFile:
    """An uploaded save file (Black, White, Black 2, or White 2)."""

    MIN_SIZE = 0x24000  # enough to hold every block of a Black / White save
    BW_GAME_VERSION_OFFSET = BLOCKS_BW[Block.TRAINER_DATA][0] + 0x1F

    def __init__(self, data: bytes) -> None:
        if len(data) < self.MIN_SIZE:
            raise SaveFileError(f"Save data is too short ({len(data)} bytes)")

        self._data = data
        # The Trainer block starts at the same place in every version, so its game field
        # can be read before knowing which block table applies.
        self.is_b2w2 = data[self.BW_GAME_VERSION_OFFSET] not in (Rom.WHITE, Rom.BLACK)

    def _block(self, block: Block) -> bytes:
        offset, length = (BLOCKS_B2W2 if self.is_b2w2 else BLOCKS_BW)[block]
        return self._data[offset:offset + length]

    @property
    def trainer(self) -> Trainer:
        """The player."""
        return Trainer(self._block(Block.TRAINER_DATA))

    @property
    def num_badges(self) -> int:
        """How many Gym Badges the player has."""
        return self._block(Block.MISC)[0x4].bit_count()

    @property
    def global_link(self) -> GlobalLink:
        """The Dream World data."""
        return GlobalLink(self._block(Block.GLOBAL_LINK))

    @property
    def medals(self) -> MedalBlock:
        """The Medals (Black 2 / White 2 only)."""
        if not self.is_b2w2:
            raise SaveFileError("Black and White have no Medals")
        return MedalBlock(self._block(Block.MEDAL))
