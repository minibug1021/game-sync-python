"""The Game Sync server keeps one Player for each Game Sync ID.

A player is stored in three JSON columns of the shared database, which the Dream World
server reads and writes to:

    player_data       {"member": the Global Link profile, "medals": [...], "favorite_medal": ...,
                       "token": ...}
    game_sync         what the DS gets at the next Game Sync (see Player.game_sync_data)
    sleeping_pokemon  the tucked-in Pokémon (a PkmnInfo)

The field names inside them are the ones the Dream World client uses.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Self

from utils import save_data, text
from utils.constants import PlayerStatus, Rom
from utils.language import game_language

from ...utility import gsid_utility
from ..avenue.avenue_data import AvenueVisitor
from ..pkmn.pkmn_info import PkmnInfo
from .dream_data import DreamEncounter, DreamItem
from .starting_save import starting_decor

# Testing data
STARTING_POINTS = 10_000


def new_player_data(member_id: int, my_interior_ids: list[int]) -> dict:
    """Return the player_data column of a Game Sync ID that was just registered.

    my_interior_ids are the ids for its starting decor.
    """
    return {
        "member": {
            "member_id":            member_id,
            "pgl_name":             None,
            "country_id":           None,
            "trainer_gender":       None,
            "special_flag":         0,
            "bridge_flag":          0,
            "special_disp_flag":    0,
            "member_created_at":    datetime.now().strftime("%Y-%m-%d"),
            "disclosure_flag":      0,    # privacy settings
            "list_disclosure_flag": 0,    # privacy settings
            "member_savedata_id":   member_id,
            "gsid":                 None,
            "sleep_time":           0,
            "sleep_pokemon_count":  0,
            "send_pokemon_count":   0,
            "island_id":            201,
            "shelf_id":             301,
            "disable_flag":         0,
            "wateringpot_id":       1,
            "avator_id":            4,
            "first_flag":           0,    # 0 = never played the DW yet, 1 = has played at least once
            "trial_flag":           1,    # cleared to 0 once a PGL account links this gscd
            "sleeping_flag":        0,
            "rom_id":               None,
            "pokemon_no":           None,
            "form_no":              None,
            "player_badge_num":     None,
            "last_started_at":      None,
            "last_logined_at":      None,
            "deleted_at":           None,
            "pdw_copied_at":        None,
            "pgl_copied_at":        None,
            "item_deleted_flag":    0,
            "world_id":             1,
            "avator_name":          None,
            "gsid_count":           1,
            "point":                0,
            "experiment_point":     STARTING_POINTS,
            "is_initializing":      1,    # 0 once the DS save has been copied into the PDW-side record
            "langcode":             None,
            "player_name":          None,
            "play_status":          PlayerStatus.AWAKE.value,
            "isin_sleep_pokemon":   1,
            "last_up_time":         None,
            "last_up_time_strict":  None,
            "rom_name":             None,
            "alter_rom_name":       None,
            "pokemon_name":         None,
            "type1":                None,
            "type2":                None,
            "gscd":                 None,
            "is_downloaded":        0,
            "nextstart_remaintime": 0,
            "last_started_at_timezone": None,
            "unread_mail_count":    0,
            "my_interior_list":     starting_decor(my_interior_ids),
        },
        "token": None,
    }


# Player attributes stored under the same name in player_data["member"]
MEMBER_FIELDS = ("rom_id", "langcode", "player_name", "trainer_gender", "player_badge_num")
GAME_SYNC_FIELDS = ("levels_gained", "country", "region", "hours_played", "minutes_played", "cgear_skin",
                    "dex_skin", "musical", "encounters", "items", "avenue_visitors", "loblolly_decor")


@dataclass
class Player:
    """The part of a save that a Game Sync reads or changes."""

    gscd: str  # the ten-character Game Sync ID
    play_status: PlayerStatus = PlayerStatus.AWAKE
    rom_id: int | None = None  # a utils.constants.Rom value. None until the first upload
    langcode: int | None = None  # the language of the cartridge (utils.language.LANGCODES)

    # Read from the save file at each tuck-in
    player_name: str | None = None
    trainer_gender: int | None = None  # 0 = male, 1 = female
    country: int | None = None
    region: int | None = None
    player_badge_num: int | None = None
    hours_played: int = 0
    minutes_played: int = 0
    loblolly_decor: int | None = None  # the id of the Loblolly item picked for the player's room
    # Only Black 2 / White 2 have Medals. The pages that show them look up their names
    # in raw_text/<lang>/medal.txt.
    medals: list[int] = field(default_factory=list)  # the obtained Medal ids, newest first
    favorite_medal: int | None = None  # the Medal the player chose to show off
    dreamer_info: PkmnInfo | None = None  # stored in the sleeping_pokemon column

    # Data sent back to the DS when waking up.
    levels_gained: int = 0
    encounters: list[DreamEncounter] = field(default_factory=list)
    items: list[DreamItem] = field(default_factory=list)
    avenue_visitors: list[AvenueVisitor] = field(default_factory=list)
    # The file name of the chosen DLC, or None if none was chosen.
    cgear_skin: str | None = None
    dex_skin: str | None = None
    musical: str | None = None

    @property
    def gsid(self) -> int:
        """The numeric Game Sync ID."""
        return gsid_utility.gscd_to_gsid(self.gscd)

    @classmethod
    def from_saved(cls, gscd: str, player_data: dict, game_sync: dict | None, sleeper: dict | None) -> Self:
        """Rebuilds a player from the three stored columns."""
        member = player_data["member"]
        game_sync = game_sync or {}
        lists = ("encounters", "items", "avenue_visitors")

        return cls(
            gscd=gscd,
            play_status=PlayerStatus(member.get("play_status") or 0),
            **{key: member.get(key) for key in MEMBER_FIELDS},
            **{key: game_sync[key] for key in GAME_SYNC_FIELDS if key in game_sync and key not in lists},
            encounters=[DreamEncounter(**encounter) for encounter in game_sync.get("encounters", [])],
            items=[DreamItem(**item) for item in game_sync.get("items", [])],
            avenue_visitors=[AvenueVisitor(**visitor) for visitor in game_sync.get("avenue_visitors", [])],
            medals=player_data.get("medals", []),
            favorite_medal=player_data.get("favorite_medal"),
            dreamer_info=PkmnInfo(**sleeper) if sleeper else None,
        )

    def member_fields(self) -> dict:
        """Return the fields of player_data["member"]."""
        dreamer = self.dreamer_info

        return {
            **{key: getattr(self, key) for key in MEMBER_FIELDS},
            "gscd":             self.gscd,
            "gsid":             self.gsid,
            "alter_rom_name":   "Shiro*" if self.rom_id in (Rom.WHITE, Rom.WHITE_2) else "Kuro*",
            "play_status":      self.play_status.value,
            "sleeping_flag":    save_data.sleeping_flag(self.play_status),
            "pokemon_no":       dreamer.pokemon_no if dreamer else None,
            "pokemon_name":     (text.lookup_str("pokemon", dreamer.pokemon_no, game_language(self.langcode))
                                 if dreamer else None),
            "form_no":          dreamer.form_no if dreamer else None,
            "type1":            dreamer.type1 if dreamer else None,
            "type2":            dreamer.type2 if dreamer else None,
            "pgl_copied_at":    save_data.now_jst_str(),
        }

    def game_sync_data(self) -> dict:
        """Return the game_sync column."""
        return {key: value for key, value in asdict(self).items() if key in GAME_SYNC_FIELDS}

    def reset_dream_info(self) -> None:
        """Clear the Game Sync data after the player wakes up."""
        self.play_status = PlayerStatus.AWAKE
        self.dreamer_info = None
        self.encounters.clear()
        self.items.clear()
        self.avenue_visitors.clear()
        self.levels_gained = 0
        self.cgear_skin = None
        self.dex_skin = None
        self.musical = None
