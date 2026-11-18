"""Loads and saves players."""
import logging
from dataclasses import asdict

from utils.constants import is_b2w2

from ...utility import gsid_utility
from ...utility.db_manager import db
from .player import Player, new_player_data
from .starting_save import STARTING_DECOR_IDS

logger = logging.getLogger(__name__)


class PlayerManager:
    """Load and save players.

    Players are read from the database for every request.
    """

    def load_player(self, gscd: str | None) -> Player | None:
        """Return the player with this Game Sync ID. Returns None if it is invalid or not registered."""
        if gscd is None or not gsid_utility.is_valid_gscd(gscd):
            logger.error("Invalid Game Sync ID: %s", gscd)
            return None

        player_data, game_sync, sleeping_pokemon = db.read_full_state(gscd) or (None, None, None)

        if player_data is None:
            logger.info("Game Sync ID %s is not registered", gscd)
            return None

        return Player.from_saved(gscd, player_data, game_sync, sleeping_pokemon)

    def save_player(self, player: Player) -> None:
        """Write the player's save data."""
        db.write_gscd(player.gscd)  # the starting garden and debug chest data

        player_data = db.read(player.gscd, "player_data")
        if player_data is None:
            player_data = new_player_data(db.next_id("member_id")[0],
                                          db.next_id("my_interior_id", len(STARTING_DECOR_IDS)))

        member = player_data["member"]
        member.update(player.member_fields())
        member["member_savedata_id"] = member["member_id"]

        if is_b2w2(player.rom_id):
            player_data["medals"] = player.medals
            player_data["favorite_medal"] = player.favorite_medal

        sleeper = asdict(player.dreamer_info) if player.dreamer_info is not None else None
        db.write_full_state(player.gscd, player_data, player.game_sync_data(), sleeper)

    def register_player(self, gscd: str, rom_id: int | None, langcode: int | None) -> None:
        """Create the player of a new Game Sync ID, which must be valid and not registered yet."""
        self.save_player(Player(gscd, rom_id=rom_id, langcode=langcode))
