"""A small base class for the SQLite databases of both servers."""
import os
import sqlite3
import threading
from pathlib import Path


def fix_ownership(path: Path) -> None:
    """Hand `path` back to the user.

    The Game Sync server needs root for its ports, and without this the files it
    creates couldn't be opened by the Dream World server, which doesn't run as root.
    """
    uid = os.environ.get("SUDO_UID")
    gid = os.environ.get("SUDO_GID")

    if uid and gid:
        os.chown(path, int(uid), int(gid))


class _ThreadConn(threading.local):
    conn: sqlite3.Connection | None = None


class SQLiteStore:
    SCHEMA: tuple[str, ...] = ()

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._local = _ThreadConn()
        self._created = False
        self._create_lock = threading.Lock()

    def _create(self) -> None:
        """Create the database folder, file, and tables."""
        with self._create_lock:
            if self._created:
                return

            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            fix_ownership(self._db_path.parent)

            conn = sqlite3.connect(self._db_path, timeout=10.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                with conn:
                    for statement in self.SCHEMA:
                        conn.execute(statement)
            finally:
                conn.close()

            fix_ownership(self._db_path)
            self._created = True

    def _make_conn(self) -> sqlite3.Connection:
        if not self._created:
            self._create()

        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        if self._local.conn is None:
            self._local.conn = self._make_conn()
        return self._local.conn

    def close(self) -> None:
        """Close this thread's connection."""
        if self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
