"""Store every uploaded save in a zpaq archive.

This needs zpaq installed (`apt install zpaq`).
"""
import subprocess
import threading
from pathlib import Path

ARCHIVE_NAME = "saves.zpaq"
ARCHIVE_INTERVAL = 60 * 60  # seconds
ZPAQ_METHOD = "4"
ZPAQ_FRAGMENT = "0"

# Held while saves are written or archived.
_lock = threading.Lock()


def store_save(saves_dir: Path, name: str, data: bytes) -> None:
    """Write `data` to `saves_dir` as the save `name`."""
    with _lock:
        saves_dir.mkdir(parents=True, exist_ok=True)
        (saves_dir / name).write_bytes(data)


def archive_loose_saves(saves_dir: Path) -> int:
    """Add the saves in `saves_dir` to its saves.zpaq, delete them, and return how many there were."""
    with _lock:
        names = sorted(path.name for path in saves_dir.glob("*.sav"))
        if not names:
            return 0
        subprocess.run(["zpaq", "add", ARCHIVE_NAME, *names, "-method", ZPAQ_METHOD, "-fragment", ZPAQ_FRAGMENT, "-force"],
                       cwd=saves_dir, check=True, capture_output=True)
        for name in names:
            (saves_dir / name).unlink()
    return len(names)
