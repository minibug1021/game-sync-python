#!/usr/bin/env python3
"""Start the Game Sync server with `python server.py` (as root on Linux, for ports 53, 80, and 443)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game_sync_server.entralinked.app import main  # needs the path set up above

if __name__ == "__main__":
    sys.exit(main())
