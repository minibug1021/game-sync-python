import math
import struct
from model.pkmn import extra_data
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PKM_STORED_SIZE = 136
PKM_PARTY_SIZE  = 220
PKM_HEADER_SIZE = 8
PKM_MAIN_SIZE   = PKM_STORED_SIZE - PKM_HEADER_SIZE

BLOCK_SIZE  = 32
BLOCK_COUNT = 4

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

BLOCKS_BW = (
    (0x00000, 0x03E0),  # 00 Box Names
    (0x00400, 0x0FF0),  # 01 Box 1
    (0x01400, 0x0FF0),  # 02 Box 2
    (0x02400, 0x0FF0),  # 03 Box 3
    (0x03400, 0x0FF0),  # 04 Box 4
    (0x04400, 0x0FF0),  # 05 Box 5
    (0x05400, 0x0FF0),  # 06 Box 6
    (0x06400, 0x0FF0),  # 07 Box 7
    (0x07400, 0x0FF0),  # 08 Box 8
    (0x08400, 0x0FF0),  # 09 Box 9
    (0x09400, 0x0FF0),  # 10 Box 10
    (0x0A400, 0x0FF0),  # 11 Box 11
    (0x0B400, 0x0FF0),  # 12 Box 12
    (0x0C400, 0x0FF0),  # 13 Box 13
    (0x0D400, 0x0FF0),  # 14 Box 14
    (0x0E400, 0x0FF0),  # 15 Box 15
    (0x0F400, 0x0FF0),  # 16 Box 16
    (0x10400, 0x0FF0),  # 17 Box 17
    (0x11400, 0x0FF0),  # 18 Box 18
    (0x12400, 0x0FF0),  # 19 Box 19
    (0x13400, 0x0FF0),  # 20 Box 20
    (0x14400, 0x0FF0),  # 21 Box 21
    (0x15400, 0x0FF0),  # 22 Box 22
    (0x16400, 0x0FF0),  # 23 Box 23
    (0x17400, 0x0FF0),  # 24 Box 24
    (0x18400, 0x09C0),  # 25 Inventory
    (0x18E00, 0x0534),  # 26 Party Pokémon
    (0x19400, 0x0068),  # 27 Trainer Data
    (0x19500, 0x009C),  # 28 Trainer Position
    (0x19600, 0x1338),  # 29 Unity Tower / survey
    (0x1AA00, 0x07C4),  # 30 Pal Pad Player Data
    (0x1B200, 0x0D54),  # 31 Pal Pad Friend Data
    (0x1C000, 0x002C),  # 32 Skin Info
    (0x1C100, 0x0658),  # 33 Gym badge data
    (0x1C800, 0x0A94),  # 34 Mystery Gift
    (0x1D300, 0x01AC),  # 35 Dream World (Catalog)
    (0x1D500, 0x03EC),  # 36 Chatter
    (0x1D900, 0x005C),  # 37 Adventure Info
    (0x1DA00, 0x01E0),  # 38 Trainer Card Records
    (0x1DC00, 0x00A8),  # 39 ???
    (0x1DD00, 0x0460),  # 40 Mail
    (0x1E200, 0x1400),  # 41 Overworld State
    (0x1F700, 0x02A4),  # 42 Musical
    (0x1FA00, 0x02DC),  # 43 White Forest / Black City
    (0x1FD00, 0x034C),  # 44 IR
    (0x20100, 0x03EC),  # 45 EventWork
    (0x20500, 0x00F8),  # 46 GTS
    (0x20600, 0x02FC),  # 47 Regulation Tournament
    (0x20900, 0x0094),  # 48 Gimmick
    (0x20A00, 0x035C),  # 49 Battle Box
    (0x20E00, 0x01CC),  # 50 Daycare
    (0x21000, 0x0168),  # 51 Strength Boulder Status
    (0x21200, 0x00EC),  # 52 Badge Flags, Money, Trainer Sayings
)

BLOCKS_B2W2 = (
    (0x00000, 0x03e0), # 00 Box Names
    (0x00400, 0x0ff0), # 01 Box 1
    (0x01400, 0x0ff0), # 02 Box 2
    (0x02400, 0x0ff0), # 03 Box 3
    (0x03400, 0x0ff0), # 04 Box 4
    (0x04400, 0x0ff0), # 05 Box 5
    (0x05400, 0x0ff0), # 06 Box 6
    (0x06400, 0x0ff0), # 07 Box 7
    (0x07400, 0x0ff0), # 08 Box 8
    (0x08400, 0x0ff0), # 09 Box 9
    (0x09400, 0x0ff0), # 10 Box 10
    (0x0A400, 0x0ff0), # 11 Box 11
    (0x0B400, 0x0ff0), # 12 Box 12
    (0x0C400, 0x0ff0), # 13 Box 13
    (0x0D400, 0x0ff0), # 14 Box 14
    (0x0E400, 0x0ff0), # 15 Box 15
    (0x0F400, 0x0ff0), # 16 Box 16
    (0x10400, 0x0ff0), # 17 Box 17
    (0x11400, 0x0ff0), # 18 Box 18
    (0x12400, 0x0ff0), # 19 Box 19
    (0x13400, 0x0ff0), # 20 Box 20
    (0x14400, 0x0ff0), # 21 Box 21
    (0x15400, 0x0ff0), # 22 Box 22
    (0x16400, 0x0ff0), # 23 Box 23
    (0x17400, 0x0ff0), # 24 Box 24
    (0x18400, 0x09ec), # 25 Inventory
    (0x18E00, 0x0534), # 26 Party Pokémon
    (0x19400, 0x00b0), # 27 Trainer Data
    (0x19500, 0x00a8), # 28 Trainer Position
    (0x19600, 0x1338), # 29 Unity Tower and survey stuff
    (0x1AA00, 0x07c4), # 30 Pal Pad Player Data
    (0x1B200, 0x0d54), # 31 Pal Pad Friend Data
    (0x1C000, 0x0094), # 32 Options / Skin Info
    (0x1C100, 0x0658), # 33 Trainer Card
    (0x1C800, 0x0a94), # 34 Mystery Gift
    (0x1D300, 0x01ac), # 35 Dream World Stuff (Catalog)
    (0x1D500, 0x03ec), # 36 Chatter
    (0x1D900, 0x005c), # 37 Adventure data
    (0x1DA00, 0x01e0), # 38 Trainer Card Records
    (0x1DC00, 0x00a8), # 39 ???
    (0x1DD00, 0x0460), # 40 Mail
    (0x1E200, 0x1400), # 41 Overworld State
    (0x1F700, 0x02a4), # 42 Musical
    (0x1FA00, 0x00e0), # 43 White Forest + Black City Data, Fused Reshiram/Zekrom Storage
    (0x1FB00, 0x034c), # 44 IR
    (0x1FF00, 0x04e0), # 45 EventWork
    (0x20400, 0x00f8), # 46 GTS
    (0x20500, 0x02fc), # 47 Regulation Tournament
    (0x20800, 0x0094), # 48 Gimmick
    (0x20900, 0x035c), # 49 Battle Box
    (0x20D00, 0x01d4), # 50 Daycare
    (0x20F00, 0x01e0), # 51 Strength Boulder Status
    (0x21100, 0x00f0), # 52 Misc (Badge Flags, Money, Trainer Sayings)
)

# ---------------------------------------------------------------------------
# PokeCrypto
# ---------------------------------------------------------------------------

def _crypt_array(data: bytearray, seed: int) -> None:
    seed &= 0xFFFFFFFF
    view = memoryview(data).cast('H')
    for i in range(len(view)):
        seed = (0x41C64E6D * seed + 0x00006073) & 0xFFFFFFFF
        view[i] ^= (seed >> 16) & 0xFFFF


def _swap_blocks(u: memoryview, a: int, b: int, count: int) -> None:
    for i in range(count):
        u[a + i], u[b + i] = u[b + i], u[a + i]


def _shuffle5(data: bytearray, sv: int) -> None:
    if sv == 0:
        return

    count = BLOCK_SIZE
    perm   = list(range(BLOCK_COUNT))
    slot_of = list(range(BLOCK_COUNT))

    index_start = sv * BLOCK_COUNT
    shuffle = BLOCK_POSITION[index_start : index_start + BLOCK_COUNT]
    u = memoryview(data).cast('B')

    for i in range(BLOCK_COUNT - 1):
        desired = shuffle[i]
        j = slot_of[desired]
        if j == i:
            continue
        _swap_blocks(u, i * count, j * count, count)
        block_at_i   = perm[i]
        perm[j]      = block_at_i
        slot_of[block_at_i] = j


# ---------------------------------------------------------------------------
# Decrypt
# ---------------------------------------------------------------------------

def _decrypt_pkm(raw: bytearray) -> bytearray:
    pkm = bytearray(raw)

    pv       = struct.unpack_from('<I', pkm, 0)[0]
    checksum = struct.unpack_from('<H', pkm, 6)[0]
    sv       = (pv >> 13) & 31

    main_block = pkm[PKM_HEADER_SIZE : PKM_STORED_SIZE]
    _crypt_array(main_block, checksum)
    _shuffle5(main_block, sv)
    pkm[PKM_HEADER_SIZE : PKM_STORED_SIZE] = main_block

    if len(pkm) > PKM_STORED_SIZE:
        party_stats = pkm[PKM_STORED_SIZE:]
        _crypt_array(party_stats, pv)
        pkm[PKM_STORED_SIZE:] = party_stats

    return pkm


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

valid_chars = set()
for char_range in extra_data.valid_char_ranges:
    if isinstance(char_range, int):
        valid_chars.add(char_range)
    else:
        valid_chars.update(range(char_range[0], char_range[1] + 1))

def _sanitize_str(string: str):
    return "".join(ch if ord(ch) in valid_chars else "?" for ch in string)

def _replace_special_chars(string: str):
    return "".join(extra_data.special_chars[ch] if ch in extra_data.special_chars else ch for ch in list(string))

def _get_level(group_id: int, total_exp: int):

    def get_exp_for_level(n):

        if group_id == 0:
            return n**3

        if group_id == 1:
            if n < 50:
                return (n**3 * (100 - n)) // 50
            if n < 68:
                return (n**3 * (150 - n)) // 100
            if n < 98:
                return (n**3 * math.floor((1911 - 10 * n) / 3)) // 500
            return (n**3 * (160 - n)) // 100

        if group_id == 2:
            if n < 15:
                return (n**3 * (math.floor((n + 1) / 3) + 24)) // 50
            if n < 36:
                return (n**3 * (n + 14)) // 50
            return (n**3 * (math.floor(n / 2) + 32)) // 50

        if group_id == 3:
            val = 1.2 * (n**3) - 15 * (n**2) + 100 * n - 140
            return math.floor(max(0, val))

        if group_id == 4:
            return (4 * n**3) // 5

        if group_id == 5:
            return (5 * n**3) // 4


    for level in range(100, 0, -1):
        required_exp = get_exp_for_level(level)
        if total_exp >= required_exp:
            return level

    return 1


# ---------------------------------------------------------------------------
# Base DataReader class
# ---------------------------------------------------------------------------

class DataReader:

    def __init__(self, data: bytearray):
        self._data = data

    def _slice(self, offset: int, length: int) -> bytearray:
        return self._data[offset : offset + length]

    def read_str(self, offset: int, length: int) -> str:
        raw = self._slice(offset, length)

        out_str = b''

        for i in range(0, len(raw) - 1, 2):
            batch = raw[i:i + 2]
            if batch == b'\xff\xff':
                break
            out_str += batch

        out_str = out_str.replace(b'\x00n$', b'\x00@&').replace(b'\x00m$', b'\x00B&').decode('UTF-16-LE')

        return _replace_special_chars(_sanitize_str(out_str))

    def read_int(self, offset: int, length: int, byteorder: str = 'little') -> int:
        return int.from_bytes(self._slice(offset, length), byteorder=byteorder)

    def read_bit(self, offset: int, bit_index: int) -> int:
        return (self._data[offset] >> bit_index) & 1

    def read_bits(self, offset: int, bit_index: int, length: int) -> int:
        return (self._data[offset] >> bit_index) & ((1 << length) - 1)


def _block_data(sav_data: bytearray, block_index: int, version: str) -> bytearray:
    BLOCKS = BLOCKS_BW if version == "BW" else BLOCKS_B2W2

    offset, length = BLOCKS[block_index]
    return bytearray(sav_data[offset : offset + length])


# ---------------------------------------------------------------------------
# High-level managers for data
# ---------------------------------------------------------------------------

class Trainer(DataReader):

    def __init__(self, sav_data: bytearray, version: str):
        super().__init__(_block_data(sav_data, 27, version))

        badge_data = _block_data(sav_data, 52, version)

        country_id = self.read_int(0x1C, 1)
        region_id  = self.read_int(0x1D, 1)

        self.name      : str = self.read_str(0x4, 0x10)
        self.country   : str = extra_data.country[country_id]
        self.region    : str = extra_data.regions[country_id][region_id] if country_id in extra_data.regions else 0
        self.language  : str = self.read_int(0x1E, 1)
        self.game      : str = self.read_int(0x1F, 1)
        self.gender    : str = "Male" if self.read_int(0x21, 1) == 0 else "Female"
        self.num_badges: int = (badge_data[0x4]).bit_count()


DREAMER_BLOCK_OFFSET = 0x1D300

class Pokemon(DataReader):

    def __init__(self, sav_data: bytearray):
        raw = sav_data[DREAMER_BLOCK_OFFSET + 8 : DREAMER_BLOCK_OFFSET + 8 + PKM_STORED_SIZE]
        super().__init__(_decrypt_pkm(raw))

        self.natdex: int = self.read_int(0x08, 2)

        if self.natdex:

            self.gender: int  = (
                1 if self.read_bit(0x40, 1) else
                2 if self.read_bit(0x40, 2) else 0
            )
            self.form          : int = self.read_bits(0x40, 3, 5)
            self.nature        : int = self.read_int(0x41, 1)
            self.nickname      : str = self.read_str(0x48, 20)
            self.trainer_name  : str = self.read_str(0x68, 18)
            self.trainer_gender: str = "Female" if self.read_bit(0x84, 7) else "Male"
            self.trainer_id    : int = self.read_int(0x0C, 2)
            self.trainer_id_secret : int = self.read_int(0x0E, 2)
            self.ball          : int = self.read_int(0x83, 1)

            self.type1, self.type2, self.growth_group = extra_data.personal_data[self.natdex][self.form]

            self.nickname = self.nickname

            self.level = _get_level(self.growth_group, self.exp)

    @property
    def exp(self) -> int:
        return self.read_int(0x10, 4)


# ---------------------------------------------------------------------------
# SaveFile class
# ---------------------------------------------------------------------------

class SaveFile:

    def __init__(self, save_data):
        self._data: bytearray = save_data.getbuffer().tobytes()

        self.game_version = "BW" if self._data[0x1941F] in (20, 21) else "B2W2"

    def trainer(self) -> Trainer:
        return Trainer(self._data, self.game_version)

    def get_dreamer_pokemon(self) -> Pokemon:
        return Pokemon(self._data)