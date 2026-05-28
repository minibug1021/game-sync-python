#!/usr/bin/env python3
import json
import logging
from typing import Dict
from pathlib import Path

from paths import ROOT_DIR
from model.pkmn import extra_data
from utility.gsid_utility import GsidUtility
from utility.fix_ownership import fix_ownership
from model.player.player import Player, PlayerStatus

logger = logging.getLogger(__name__)

class PlayerManager:
    def __init__(self):
        self.player_map: Dict[str, Player] = {}
        self.data_directory = ROOT_DIR / "save_data"

        logger.info("Loading player data ...")

        if not (self.data_directory / "game_sync.json").exists():
            return

        self.load_player(self.data_directory)

    def load_player(self, input_folder: Path):
        with open(input_folder / "player_data.json", "r", encoding="UTF-8") as f:
            player_data = json.load(f)

        with open(input_folder / "game_sync.json", "r", encoding="UTF-8") as f:
            game_sync = json.load(f)

        with open(input_folder / "sleeping_pokemon.json", "r", encoding="UTF-8") as f:
            sleeping_pokemon = json.load(f)

        player = Player.from_dict(player_data, game_sync, sleeping_pokemon)

        game_sync_id = player.game_sync_id

        if not GsidUtility.is_valid_gamesync_id(game_sync_id):
            logger.error(f"Invalid Game Sync ID: {game_sync_id}")
            return

        if self.does_player_exist(game_sync_id):
            logger.error(f"Duplicate Game Sync ID: {game_sync_id}")
            return

        self.player_map[game_sync_id] = player

    def save_players(self):
        for player in self.player_map.values():
            self.save_player(player)

    def save_player(self, player: Player, output_folder: Path = None):
        if output_folder is None:
            output_folder = player.data_directory

        try:
            new_player_data, game_sync, sleeper = player.to_dict()

            # ----

            with open(output_folder / "player_data.json", "r", encoding="UTF-8") as f:
                old_player_data = json.load(f)

            old_player_data["member"].update(new_player_data)

            with open(output_folder / "player_data.json", "w", encoding="UTF-8") as f:
                json.dump(old_player_data, f, indent=2, ensure_ascii=False)

            # ----

            with open(output_folder / "game_sync.json", "w", encoding="UTF-8") as f:
                json.dump(game_sync, f, indent=2, ensure_ascii=False)

            fix_ownership(output_folder / "game_sync.json")

            # ----

            with open(output_folder / "sleeping_pokemon.json", "w", encoding="UTF-8") as f:
                json.dump(sleeper, f, indent=2, ensure_ascii=False)

            fix_ownership(output_folder / "sleeping_pokemon.json")

        except Exception as e:
            logger.error(f"Could not save player data for {player.game_sync_id}: {e}")
            return False

        return True

    def register_player(self, game_sync_id: str, rom_code: int, lang_code: int):
        if game_sync_id in self.player_map:
            logger.warning(f"Attempted to register duplicate Game Sync ID: {game_sync_id}")
            return None

        if not GsidUtility.is_valid_gamesync_id(game_sync_id):
            logger.error(f"Attempted to register invalid Game Sync ID: {game_sync_id}")
            return None

        player_data_file = ROOT_DIR / "save_data" / "game_sync.json"

        if player_data_file.exists():
            logger.warning(f"Can't register player {game_sync_id} because the data file already exists!")
            return None

        player = Player(game_sync_id)
        player.status = PlayerStatus.AWAKE
        player.rom_code = rom_code
        player.language_code = lang_code
        player.game_name = extra_data.version[(player.rom_code, player.language_code)]
        player.data_directory = ROOT_DIR / "save_data"

        if not self.save_player(player):
            return None

        self.player_map[game_sync_id] = player
        return player

    def store_player_game_save_file(self, player: Player, save_data: bytearray):
        try:
            player.raw_save_data = save_data
            return True

        except Exception as e:
            logger.error(f"Could not write game save data for player {player.game_sync_id}: {e}")
            return False

    def does_player_exist(self, game_sync_id: str):
        return game_sync_id in self.player_map
