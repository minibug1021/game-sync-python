"""Store every uploaded save in a zpaq archive.

This needs zpaq installed (`apt install zpaq`).
"""
import logging
import subprocess
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ARCHIVE_NAME = "saves.zpaq"
ARCHIVE_INTERVAL = 30  # seconds
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


def find_save(saves_dir: Path, gscd: str) -> bytes | None:
    """Return the newest archived save of the game `gscd`, or None if there is none."""
    suffix = f"_{gscd}.sav"
    with _lock:
        if not (saves_dir / ARCHIVE_NAME).is_file():
            return None
        try:
            listing = subprocess.run(["zpaq", "list", ARCHIVE_NAME], cwd=saves_dir, check=True,
                                     capture_output=True, text=True).stdout
            # "- 2026-11-22 21:07:46       524288  0664 IT_B_93T22E2EMB.sav"
            files = sorted((line.split()[1:3], line.split()[-1]) for line in listing.splitlines()
                           if line.startswith("- ") and line.endswith(suffix))
            if not files:
                return None
            name = files[-1][1]
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / name
                subprocess.run(["zpaq", "extract", ARCHIVE_NAME, name, "-to", str(out)], cwd=saves_dir,
                               check=True, capture_output=True)
                return out.read_bytes()
        except (OSError, subprocess.CalledProcessError):
            logger.exception("Could not look up the save of %s in %s", gscd, saves_dir / ARCHIVE_NAME)
            return None
