"""The options in config.json."""
import json
from dataclasses import dataclass
from pathlib import Path

LOCAL_HOST_NAMES = ("local", "localhost")


@dataclass
class Configuration:
    """Server options: anything missing from config.json will use the default."""

    # The DNS server hands out this address. It is a host name, or "local" for this machine's
    # address on the local network.
    host_name: str = "local"
    # Clear dream info (encounters, items, skins) once the DS has downloaded it.
    clear_player_dream_info_on_wake: bool = True
    # Create a Nintendo WFC account for any unknown user id that tries to log in.
    allow_wfc_registration_through_login: bool = True
    # Copy each uploaded save to the saves folder and archive the copies once an hour.
    copy_saves: bool = False


def load_configuration(path: Path) -> Configuration:
    """Read the configuration at `path`, or return the defaults if there is no such file."""
    if not path.is_file():
        return Configuration()
    return Configuration(**json.loads(path.read_text(encoding="UTF-8")))
