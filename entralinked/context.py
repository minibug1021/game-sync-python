"""The objects shared by every server and handler."""
from dataclasses import dataclass

from .configuration import Configuration
from .model.dlc.dlc import DlcList
from .model.player.player_manager import PlayerManager
from .model.user.user_manager import UserManager


@dataclass(frozen=True)
class Context:
    """Created once at startup and handed to each server."""

    configuration: Configuration
    user_manager: UserManager
    player_manager: PlayerManager
    dlc_list: DlcList
