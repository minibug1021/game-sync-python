#!/usr/bin/env python3
from typing import List
from enum import Enum, auto
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import asdict

from model.pkmn import extra_data
from model.pkmn.pkmn_info import PkmnInfo
from model.player.dream_data import DreamEncounter, DreamDecor, DreamItem
from model.avenue.avenue_data import AvenueVisitor

class PlayerStatus(Enum):
    AWAKE = 0
    SLEEPING = auto()
    DREAMING = auto()
    WAKE_READY = auto()

class Player:
    def __init__(self, game_sync_id: str):
        self.game_sync_id = game_sync_id
        self.gsid = 0
        self.encounters = []
        self.items = []
        self.avenue_visitors = []
        self.decor = []

        self.name = None
        self.num_badges = None

        self.status = PlayerStatus.AWAKE

        self.rom_code = 0
        self.language_code = 0
        self.game_name = None

        self.dreamer_info = None
        self.levels_gained = 0

        self.cgear_skin = None
        self.dex_skin = None
        self.musical = None
        self.custom_cgear_skin = None
        self.custom_dex_skin = None
        self.custom_musical = None

        self.data_directory = None

    @classmethod
    def from_dict(cls, player_data: dict, game_sync: dict, sleeper: dict):
        player_data = player_data["member"]

        player = cls(player_data["gscd"])

        player.gsid = player_data["gsid"]

        player.rom_code = player_data["rom_id"]
        player.language_code = player_data["langcode"]
        player.dreamer_info = PkmnInfo(**sleeper)
        player.levels_gained = game_sync["levels_gained"]

        player.name = player_data["player_name"]
        player.num_badges = player_data["player_badge_num"]

        player.cgear_skin = game_sync["cgear_skin"]
        player.dex_skin = game_sync["dex_skin"]
        player.musical = game_sync["musical"]
        player.custom_cgear_skin = game_sync["custom_cgear_skin"]
        player.custom_dex_skin = game_sync["custom_dex_skin"]
        player.custom_musical = game_sync["custom_musical"]

        try:
            player.status = PlayerStatus(player_data["play_status"])
        except KeyError:
            player.status = PlayerStatus.AWAKE

        print(player.status)

        player.encounters = [DreamEncounter(**e) for e in game_sync.get("encounters", [])]
        player.items = [DreamItem(**i) for i in game_sync.get("items", [])]
        player.avenue_visitors = [AvenueVisitor(**v) for v in game_sync.get("avenue_visitors", [])]
        player.decor = [DreamDecor(**d) for d in game_sync.get("decor", [])]

        return player

    def to_dict(self):
        now_local = datetime.now().astimezone()
        now_japan = now_local.astimezone(ZoneInfo("Asia/Tokyo"))

        player_data = {
            "country_id": 220,
            "gsid": self.gsid,
            "sleeping_flag": 1,
            "rom_id": self.rom_code,
            "pokemon_no": self.dreamer_info.pokemon_no if self.dreamer_info else None,
            "form_no": self.dreamer_info.form_no if self.dreamer_info else None,
            "player_badge_num": self.num_badges,
            "last_started_at": int(now_japan.timestamp()),
            "last_logined_at": int(now_japan.timestamp()),
            #"pdw_copied_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "pgl_copied_at": now_local.strftime("%Y-%m-%d %H:%M:%S"),
            "langcode": self.language_code,
            "player_name": self.name,
            "play_status": self.status.value,
            #"last_up_time": now_local.strftime("%m/%d/%y %I:%M %p"),
            #"last_up_time_strict": now_japan.strftime("%Y-%m-%d %H:%M:%S"),
            "rom_name": extra_data.version[(self.rom_code, self.language_code)],
            "alter_rom_name": "Shiro*" if self.rom_code in (20, 22) else "Kuro*",
            "pokemon_name": self.dreamer_info.pokemon_name if self.dreamer_info else None,
            "type1": self.dreamer_info.type1 if self.dreamer_info else None,
            "type2": self.dreamer_info.type2 if self.dreamer_info else None,
            "gscd": self.game_sync_id,
            #"last_started_at_timezone": int(now_local.timestamp()),
        }

        game_sync = {
            "levels_gained": self.levels_gained,
            "cgear_skin": self.cgear_skin,
            "dex_skin": self.dex_skin,
            "musical": self.musical,
            "custom_cgear_skin": self.custom_cgear_skin,
            "custom_dex_skin": self.custom_dex_skin,
            "custom_musical": self.custom_musical,
            "encounters": [asdict(encounter) for encounter in self.encounters],
            "items": [asdict(item) for item in self.items],
            "avenue_visitors": [asdict(visitor) for visitor in self.avenue_visitors],
            "decor": [asdict(decor) for decor in self.decor]
        }

        sleeper = asdict(self.dreamer_info) if self.dreamer_info is not None else None

        return (player_data, game_sync, sleeper)

    def reset_dream_info(self):
        self.status = PlayerStatus.AWAKE
        self.dreamer_info = None
        self.encounters.clear()
        self.items.clear()
        self.avenue_visitors.clear()
        self.decor.clear()
        self.decor.extend(DreamDecor.DEFAULT_DECOR)
        self.levels_gained = 0
        self.cgear_skin = None
        self.dex_skin = None
        self.musical = None

    def set_encounters(self, encounters: List[DreamEncounter]):
        if len(encounters) <= 10:
            self.encounters.clear()
            self.encounters.extend(encounters)

    def get_encounters(self):
        return self.encounters.copy()

    def set_items(self, items: List[DreamItem]):
        if len(items) <= 20:
            self.items.clear()
            self.items.extend(items)

    def get_items(self):
        return self.items.copy()

    def set_avenue_visitors(self, avenue_visitors: List[AvenueVisitor]):
        if len(avenue_visitors) <= 12:
            self.avenue_visitors.clear()
            self.avenue_visitors.extend(avenue_visitors)

    def get_avenue_visitors(self):
        return self.avenue_visitors.copy()

    def set_decor(self, decor: List[DreamDecor]):
        if len(decor) <= 5:
            self.decor.clear()
            self.decor.extend(decor)

    def get_file(self, filename: str):
        """Valid files are `data.json`, `save.bin`, `cgear.bin`, `zukan.bin`, and `musical.bin`"""
        return self.data_directory / filename
