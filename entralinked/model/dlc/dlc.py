"""C-Gear skins, Pokédex skins, and musicals."""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ...paths import CUSTOMIZE_PATH, DLC_DIR

logger = logging.getLogger(__name__)


@dataclass
class Dlc:
    """A downloadable file."""

    path: Path
    name: str
    type: str  # CGEAR, CGEAR2, ZUKAN, or MUSICAL
    language: str  # J, E, F, I, G, S, or K
    index: int
    size: int


class DlcList:
    """Every DLC file found during startup."""

    def __init__(self, data_dir: Path = DLC_DIR, customize_path: Path = CUSTOMIZE_PATH) -> None:
        self.dlc_list: list[Dlc] = []

        customize: dict[str, dict] = json.loads(customize_path.read_text(encoding="utf-8"))
        for key, entry in customize.items():
            for _, rel, _ in entry["data"].values():
                if not rel:
                    continue

                path = data_dir / rel
                if not path.is_file():
                    logger.warning("DLC file in customize.json is missing: %s", path)
                    continue

                dlc_type, language, name = rel.split("/")
                self.dlc_list.append(Dlc(path.absolute(), name, dlc_type, language, int(key[1:4]),
                                         path.stat().st_size))

        logger.info("Loaded %d DLC file(s) from %s", len(self.dlc_list), data_dir)

    def get_dlc_list(self, dlc_type: str, language: str | None = None, index: int | None = None) -> list[Dlc]:
        """Return the DLC of one type, in one language, and with one id."""
        return [dlc for dlc in self.dlc_list
                if dlc.type == dlc_type and language in (None, dlc.language) and index in (None, dlc.index)]

    def get_dlc(self, dlc_type: str, name: str | None, language: str | None = None) -> Dlc | None:
        """Return the DLC with this file name, if there is one."""
        return next((dlc for dlc in self.get_dlc_list(dlc_type, language) if dlc.name == name), None)

    def get_dlc_index(self, dlc_type: str, name: str | None) -> int:
        """Return the id of the DLC with this file name (in any language). Return 0 (nothing) if there is none."""
        dlc = self.get_dlc(dlc_type, name)
        return 0 if dlc is None else dlc.index


def dlc_list_string(dlc_list: list[Dlc]) -> str:
    """Return one tab-separated line per file."""
    return "".join(f"{dlc.name}\t\t{dlc.type}_{dlc.language}\t{dlc.index}\t\t{dlc.size}\r\n"
                   for dlc in dlc_list)
