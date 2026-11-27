"""Read what the Game Sync needs out of an uploaded Gen 5 save file.

That is the Trainer data, the tucked-in Pokémon, the records, the Pal Pad, the Trade Pals, and
(Black 2 / White 2) the Medals.

Adapted from PKHeX.
"""
import hashlib
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
    PAL_PAD = 30  # the player's Nintendo WFC profile and the friends registered on the Pal Pad
    TRADE_PALS = 31  # the last 100 players the player traded Pokémon with
    GLOBAL_LINK = 35  # Dream World data, with the tucked-in Pokémon and the Loblolly items
    RECORDS = 38  # the counters behind the Trainer Card and the Game Sync rankings
    MISC = 52  # badges, money
    MEDAL = 68  # Black 2 / White 2 only


# Location of each block in the save file as (offset, length).
BLOCKS_BW = {
    Block.TRAINER_DATA: (0x19400, 0x0068),
    Block.PAL_PAD:      (0x1AA00, 0x07C4),
    Block.TRADE_PALS:   (0x1B200, 0x0D54),
    Block.GLOBAL_LINK:  (0x1D300, 0x01AC),
    Block.RECORDS:      (0x1DA00, 0x01E0),
    Block.MISC:         (0x21200, 0x00EC)
}
BLOCKS_B2W2 = {
    Block.TRAINER_DATA: (0x19400, 0x00B0),
    Block.PAL_PAD:      (0x1AA00, 0x07C4),
    Block.TRADE_PALS:   (0x1B200, 0x0D54),
    Block.GLOBAL_LINK:  (0x1D300, 0x01AC),
    Block.RECORDS:      (0x1DA00, 0x01E0),
    Block.MISC:         (0x21100, 0x00F0),
    Block.MEDAL:        (0x25300, 0x0498)
}

MEMORY_LINK_BLOCKS_BW = (
    (0x19400, 108),   # player data
    (0x1F700, 680),   # musical props
    (0x20100, 1008),  # event data
    (0x21200, 240),   # misc
    (0x23B00, 368),   # first HoF Pokémon
)
MEMORY_LINK_SIZE_BW = 0x23B00 + 368


def memory_link_save(save: bytes) -> bytes:
    """Return a Black / White save with only the blocks read by Memory Link."""
    out = bytearray(MEMORY_LINK_SIZE_BW)
    for offset, length in MEMORY_LINK_BLOCKS_BW:
        out[offset:offset + length] = save[offset:offset + length]
    return bytes(out)


# Ids below FIRST_SMALL_RECORD are 4-byte counters.
FIRST_SMALL_RECORD = 71
RECORDS: dict[str, int] = {
    "steps_walked":                  0,
    "times_saved":                   1,
    "first_clear_seconds":           2,  # play time when the game was first beaten, None before that
    "bike_rides":                    3,
    "battles":                       4,
    "wild_battles":                  5,
    "trainer_battles":               6,
    "pokemon_caught":                7,
    "pokemon_fished":                8,
    "eggs_hatched":                  9,
    "pokemon_evolved":               10,
    "pokemon_center_rests":          11,
    "wireless_trades":               12,
    "wireless_battles":              13,
    "wireless_battle_wins":          14,
    "wireless_battle_losses":        15,
    "wifi_trades":                   16,
    "wifi_battles":                  17,
    "wifi_battle_wins":              18,
    "wifi_battle_losses":            19,
    "wifi_battle_draws":             20,
    "purchases":                     21,
    "money_spent":                   22,
    "tv_watched":                    23,
    "day_care_deposits":             24,
    "pokemon_defeated":              25,
    "best_day_exp":                  26,
    "today_exp":                     27,
    "gts_deposits":                  28,
    "mail_written":                  29,
    "nicknames_given":               30,
    "premier_balls_received":        31,
    "stadium_battles":               32,
    "bp_earned":                     33,
    "bp_spent":                      34,
    "infrared_trades":               36,
    "infrared_battles":              37,
    "infrared_battle_wins":          38,
    "infrared_battle_losses":        39,
    "fly_uses":                      42,
    "trash_cans_checked":            43,
    "dowsing_items_found":           44,
    "pass_powers_used":              45,
    "entralink_pokemon_caught":      46,
    "super_effective_hits":          47,  # against wild Pokémon and Trainers
    "battle_subway_challenges":      48,
    "unovas_challenge_trainers_defeated": 49,  # in the Black Tower and White Treehollow
    "xtransceiver_game_points":      50,
    "best_pokestar_box_office":      51,
    "total_pokestar_box_office":     52,
    "random_match_disconnects":      53,
    "hall_of_fame_entries":          71,
    "home_rests":                    72,
    "splash_uses":                   73,
    "struggle_uses":                 74,
    "no_effect_moves":               75,
    "pokemon_fainted":               76,
    "allies_hit":                    77,
    "failed_escapes":                78,
    "pokemon_fled":                  79,
    "fishing_failed":                80,
    "best_day_pokemon_defeated":     81,
    "today_pokemon_defeated":        82,
    "best_day_pokemon_caught":       83,
    "today_pokemon_caught":          84,
    "best_day_trainer_battles":      85,
    "today_trainer_battles":         86,
    "best_day_pokemon_evolved":      87,
    "today_pokemon_evolved":         88,
    "fossils_restored":              89,
    "spin_trades":                   90,
    "wonder_launcher_uses":          111,
    "phenomenon_encounters":         112,
    "feeling_checks":                113,
    "musicals_played":               114,
    "musicals_won":                  115,
    "link_musicals_played":          116,
    "link_musicals_won":             117,
    "musical_points":                118,
    "pokemon_tucked_in":             119,
    "poke_transfers":                120,
    "trial_house_battles":           121,
    "trial_house_best_rank":         123,
    "trial_house_best_score":        124,
    "vending_machine_drinks":        125,
    "royal_unova_rides":             126,
    "join_avenue_visitors_guided":   127,
    "join_avenue_shops_opened":      128,
    "xtransceiver_games_played":     129,
    "join_avenue_gifts_received":    130,
    "pokestar_films_shot":           131,
}
# Records only Black 2 and White 2 have.
B2W2_RECORDS = frozenset({
    "fly_uses", "trash_cans_checked", "dowsing_items_found", "pass_powers_used", "entralink_pokemon_caught",
    "super_effective_hits", "battle_subway_challenges", "unovas_challenge_trainers_defeated",
    "xtransceiver_game_points", "best_pokestar_box_office", "total_pokestar_box_office",
    "random_match_disconnects", "vending_machine_drinks", "royal_unova_rides", "join_avenue_visitors_guided",
    "join_avenue_shops_opened", "xtransceiver_games_played", "join_avenue_gifts_received", "pokestar_films_shot",
})

TAG_MODE_COUNTS: dict[str, int] = {"tag_mode_thanks_received": 0x18, "tag_mode_people_met": 0x1C}
B2W2_TAG_MODE_SHIFT = 4
RECORD_COLUMNS = (*RECORDS, *TAG_MODE_COUNTS)


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


class RecordBlock(DataReader):
    """The records block."""

    LARGE_SIZE = 4
    SMALL_SIZE = 2
    SEED_SIZE = 4

    def __init__(self, data: bytes) -> None:
        seed = int.from_bytes(data[-self.SEED_SIZE:], "little")
        decrypted = bytearray(data[self.LARGE_SIZE:-self.SEED_SIZE])
        _crypt_array(decrypted, seed)
        if sum(decrypted) & 0xFFFF != seed & 0xFFFF:
            raise SaveFileError("The records don't match their checksum")
        super().__init__(data[:self.LARGE_SIZE] + bytes(decrypted))

    def get(self, record_id: int) -> int:
        """Return the value of the record with this id."""
        if record_id < FIRST_SMALL_RECORD:
            return self.read_int(record_id * self.LARGE_SIZE, self.LARGE_SIZE)
        offset = FIRST_SMALL_RECORD * self.LARGE_SIZE + (record_id - FIRST_SMALL_RECORD) * self.SMALL_SIZE
        return self.read_int(offset, self.SMALL_SIZE)


def _clear_time_seconds(clear_time: int) -> int | None:
    """Convert a time stored as hours * 10000 + minutes * 100 + seconds.

    Returns None if it's 0.
    """
    if clear_time == 0:
        return None
    hours, rest = divmod(clear_time, 10000)
    minutes, seconds = divmod(rest, 100)
    return hours * 3600 + minutes * 60 + seconds


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


# Every Gen 5 game stores this game code in its Nintendo WFC user data.
FRIEND_CODE_GAME_CODE = b"JARI"


def friend_code(profile_id: int) -> int:
    """Return the 12-digit Friend Code for a Nintendo WFC profile."""
    checksum = hashlib.md5(struct.pack("<I", profile_id) + FRIEND_CODE_GAME_CODE).digest()[0] >> 1
    return checksum << 32 | profile_id


class PalPad(DataReader):
    """The Pal Pad block."""

    PROFILE_ID_OFFSET = 0x1C
    FRIENDS_OFFSET = 0x40
    FRIEND_SIZE = 12
    FRIEND_SLOTS = 32
    FRIEND_KEY = 2  # a Friend Code typed in on the Pal Pad
    GS_PROFILE_ID = 3  # a friend whose Friend Code was confirmed online

    @property
    def friend_code(self) -> int | None:
        """The player's Friend Code.

        None if the game has never connected to Nintendo WFC.
        """
        profile_id = self.read_int(self.PROFILE_ID_OFFSET, 4)
        return friend_code(profile_id) if profile_id else None

    @property
    def friend_codes(self) -> list[int]:
        """The Friend Codes on the Pal Pad."""
        codes = []
        for slot in range(self.FRIEND_SLOTS):
            offset = self.FRIENDS_OFFSET + slot * self.FRIEND_SIZE
            friend_type = (self.read_int(offset, 4) >> 11) & 0b11
            profile_id = self.read_int(offset + 4, 4)
            if friend_type in (self.FRIEND_KEY, self.GS_PROFILE_ID) and profile_id:
                codes.append(friend_code(profile_id))
        return list(dict.fromkeys(codes))


class TradePals(DataReader):
    """The Trade Pals block."""

    ENTRY_SIZE = 32
    ENTRIES = 100
    PROFILE_ID_OFFSET = 0x14
    GAME_OFFSET = 0x1B
    GEN_5_GAMES = frozenset({Rom.WHITE, Rom.BLACK, Rom.WHITE_2, Rom.BLACK_2})

    @property
    def friend_codes(self) -> list[int]:
        """The Friend Codes of the players on the Trade Pal list."""
        codes = []
        for entry in range(self.ENTRIES):
            offset = entry * self.ENTRY_SIZE
            profile_id = self.read_int(offset + self.PROFILE_ID_OFFSET, 4)
            if profile_id and self._data[offset + self.GAME_OFFSET] in self.GEN_5_GAMES:
                codes.append(friend_code(profile_id))
        return list(dict.fromkeys(codes))


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
    MAIN_SAVE_SIZE_BW = 0x24000
    MAIN_SAVE_SIZE_B2W2 = 0x26000
    FULL_SAVE_SIZE = 0x80000  # 512 KiB
    BW_GAME_VERSION_OFFSET = BLOCKS_BW[Block.TRAINER_DATA][0] + 0x1F

    def __init__(self, data: bytes) -> None:
        if len(data) < self.MIN_SIZE:
            raise SaveFileError(f"Save data is too short ({len(data)} bytes)")

        self._data = data
        # The Trainer block starts at the same place in every version, so its game field
        # can be read before knowing which block table applies.
        self.is_b2w2 = data[self.BW_GAME_VERSION_OFFSET] not in (Rom.WHITE, Rom.BLACK)

    def main_save(self) -> bytes:
        """Return the main save data."""
        return self._data[:self.MAIN_SAVE_SIZE_B2W2 if self.is_b2w2 else self.MAIN_SAVE_SIZE_BW]

    def _block(self, block: Block) -> bytes:
        offset, length = (BLOCKS_B2W2 if self.is_b2w2 else BLOCKS_BW)[block]
        return self._data[offset:offset + length]

    @property
    def trainer(self) -> Trainer:
        """The player."""
        return Trainer(self._block(Block.TRAINER_DATA))

    @property
    def pal_pad(self) -> PalPad:
        """The player's Friend Code and the Friend Codes on their Pal Pad."""
        return PalPad(self._block(Block.PAL_PAD))

    @property
    def trade_pals(self) -> TradePals:
        """The Friend Codes of the players the player has traded with."""
        return TradePals(self._block(Block.TRADE_PALS))

    @property
    def num_badges(self) -> int:
        """How many Gym Badges the player has."""
        return self._block(Block.MISC)[0x4].bit_count()

    @property
    def global_link(self) -> GlobalLink:
        """The Dream World data."""
        return GlobalLink(self._block(Block.GLOBAL_LINK))

    @property
    def records(self) -> dict[str, int | None]:
        """Every value in RECORD_COLUMNS. B2W2_RECORDS are None for a Black or White save.

        Raise SaveFileError if the records block doesn't decrypt to a matching checksum.
        """
        block = RecordBlock(self._block(Block.RECORDS))
        records: dict[str, int | None] = {
            name: None if name in B2W2_RECORDS and not self.is_b2w2 else block.get(record_id)
            for name, record_id in RECORDS.items()
        }
        records["first_clear_seconds"] = _clear_time_seconds(block.get(RECORDS["first_clear_seconds"]))

        misc = DataReader(self._block(Block.MISC))
        shift = B2W2_TAG_MODE_SHIFT if self.is_b2w2 else 0
        for name, offset in TAG_MODE_COUNTS.items():
            records[name] = misc.read_int(offset + shift, 4)
        return records

    @property
    def medals(self) -> MedalBlock:
        """The Medals (Black 2 / White 2 only)."""
        if not self.is_b2w2:
            raise SaveFileError("Black and White have no Medals")
        return MedalBlock(self._block(Block.MEDAL))
