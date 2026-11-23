"""Locations of things on disk.

The Game Sync server is a submodule of the Dream World server.
"""
import os
from pathlib import Path

GAME_SYNC_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = GAME_SYNC_ROOT.parent  # the Dream World server we are a submodule of

CONFIG_PATH = GAME_SYNC_ROOT / "config.json"
DATA_DIR = GAME_SYNC_ROOT / "entralinked" / "data"
SERVER_PEM_PATH = DATA_DIR / "server.pem"

DLC_DIR = DATA_DIR / "dlc_skins"

CUSTOMIZE_PATH = REPO_ROOT / "json_data" / "customize.json"

RAW_TEXT_DIR = REPO_ROOT / "raw_text"  # <language>/medal.txt, loblolly.txt, ...
# Shared with the Dream World server (config.SAVE_DIR)
SAVE_DIR = Path(os.environ.get("DW_SAVE_DIR", REPO_ROOT / "save_data"))
# Each trainer's most recent uploaded save
UPLOADED_SAVES_DIR = Path(os.environ.get("DW_UPLOADED_SAVES_DIR", REPO_ROOT / "saves"))
