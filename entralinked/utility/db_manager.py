"""The database both servers share."""
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import ClassVar

from utils.constants import DreamPalStatus

from ..model.player.starting_save import (
    STARTING_DECOR_IDS,
    STARTING_PLOTS,
    starting_chest,
    starting_decor,
    starting_garden,
)
from ..model.save_file import B2W2_RECORDS, RECORD_COLUMNS
from ..paths import SAVE_DIR
from .sqlite_store import SQLiteStore


def _to_json(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _record_column(name: str) -> str:
    nullable = name in B2W2_RECORDS or name == "first_clear_seconds"
    return f"{name} INTEGER" if nullable else f"{name} INTEGER NOT NULL"

MEMBER_SAVEDATA_ID = "json_extract(player_data, '$.member.member_savedata_id')"
FRIEND_CODE = "json_extract(game_sync, '$.friend_code')"
# footprints and unanswered Dream Pal requests are deleted when they're this old
EXPIRES_AFTER = timedelta(days=7)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class DBManager(SQLiteStore):
    """Reads and writes player saves (keyed by gscd) and Nintendo WFC users."""

    SCHEMA = (
        """
        CREATE TABLE IF NOT EXISTS player_saves (
            gscd TEXT PRIMARY KEY,
            player_data TEXT,
            sleeping_pokemon TEXT,
            game_sync TEXT,
            chest_data TEXT
        )""",
        f"CREATE INDEX IF NOT EXISTS player_saves_member_savedata_id ON player_saves ({MEMBER_SAVEDATA_ID})",
        f"CREATE INDEX IF NOT EXISTS player_saves_friend_code ON player_saves ({FRIEND_CODE})",
        """
        CREATE TABLE IF NOT EXISTS wfc_users (
            user_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            profiles TEXT
        )""",
        """
        CREATE TABLE IF NOT EXISTS id_counters (
            name TEXT PRIMARY KEY,
            last_id INTEGER NOT NULL
        )""",
        # One row per direction.
        """
        CREATE TABLE IF NOT EXISTS dream_pals (
            from_gscd TEXT NOT NULL,
            to_gscd TEXT NOT NULL,
            status INTEGER NOT NULL CHECK (status IN (1, 2, 3)),
            created_at TEXT NOT NULL,
            visit_count INTEGER NOT NULL DEFAULT 0,
            last_visit_date TEXT,
            PRIMARY KEY (from_gscd, to_gscd)
        )""",
        """
        CREATE TABLE IF NOT EXISTS garden_plots (
            my_croft_id INTEGER PRIMARY KEY,
            gscd TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            pokeitem_id INTEGER,
            dirt_hp INTEGER,
            kinomi_state INTEGER,
            planted_at INTEGER,
            updated_at INTEGER,
            watered_at INTEGER,
            berry_hp INTEGER,
            UNIQUE (gscd, x, y)
        )""",
        """
        CREATE TABLE IF NOT EXISTS share_slots (
            material_id INTEGER PRIMARY KEY,
            gscd TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            history_id TEXT,
            old_member_savedata_id INTEGER,
            pokemon_no INTEGER,
            form_no INTEGER,
            pgl_name TEXT,
            nickname TEXT,
            poke_nickname TEXT,
            created_at TEXT,
            old_item_id INTEGER,
            new_item_id,
            UNIQUE (gscd, x, y)
        )""",
        """
        CREATE TABLE IF NOT EXISTS owned_decor (
            my_interior_id INTEGER PRIMARY KEY,
            gscd TEXT NOT NULL,
            interior_id INTEGER NOT NULL,
            x INTEGER,
            y INTEGER
        )""",
        "CREATE INDEX IF NOT EXISTS owned_decor_gscd ON owned_decor (gscd)",
        # One row per player, from their last uploaded save. Older uploads are in saves.zpaq.
        f"""
        CREATE TABLE IF NOT EXISTS record_uploads (
            gscd TEXT NOT NULL,
            uploaded_at INTEGER NOT NULL,
            rom_id INTEGER NOT NULL,
            country INTEGER,
            {", ".join(_record_column(name) for name in RECORD_COLUMNS)},
            PRIMARY KEY (gscd)
        )""",
        # One row per Friend Code on a player's Pal Pad from their last uploaded save.
        """
        CREATE TABLE IF NOT EXISTS pal_pad (
            gscd TEXT NOT NULL,
            friend_code INTEGER NOT NULL,
            PRIMARY KEY (gscd, friend_code)
        )""",
        "CREATE INDEX IF NOT EXISTS pal_pad_friend_code ON pal_pad (friend_code)",
        # One row per Friend Code on a player's Trade Pal list from their last uploaded save.
        """
        CREATE TABLE IF NOT EXISTS trade_pals (
            gscd TEXT NOT NULL,
            friend_code INTEGER NOT NULL,
            PRIMARY KEY (gscd, friend_code)
        )""",
        "CREATE INDEX IF NOT EXISTS trade_pals_friend_code ON trade_pals (friend_code)",
        # One row per player who visited someone's island.
        """
        CREATE TABLE IF NOT EXISTS footprints (
            island_gscd TEXT NOT NULL,
            visitor_gscd TEXT NOT NULL,
            visited_at TEXT NOT NULL,
            watered INTEGER NOT NULL DEFAULT 0,
            swapped INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (island_gscd, visitor_gscd)
        )""",
    )
    COLUMNS = frozenset({"player_data", "sleeping_pokemon", "game_sync", "chest_data"})
    # table -> its id column
    ROW_TABLES: ClassVar[dict[str, str]] = {
        "garden_plots": "my_croft_id", "share_slots": "material_id", "owned_decor": "my_interior_id"
    }

    def _validate_column(self, column: str) -> None:
        if column not in self.COLUMNS:
            raise ValueError(f"Invalid column name: '{column}'")

    def _id_column(self, table: str) -> str:
        if table not in self.ROW_TABLES:
            raise ValueError(f"Invalid table name: '{table}'")
        return self.ROW_TABLES[table]

    # ------------
    # id counters
    # ------------

    def next_id(self, name: str, count: int = 1) -> list[int]:
        """Reserve `count` new ids from the global `name` sequence.

        Ids only ever go up and are never reused. Each name has its own sequence, which
        every player shares.
        """
        with self._conn:
            return self._next_id(self._conn, name, count)

    @staticmethod
    def _next_id(conn: sqlite3.Connection, name: str, count: int) -> list[int]:
        last_id = conn.execute(
            """INSERT INTO id_counters (name, last_id) VALUES (?, ?)
               ON CONFLICT(name) DO UPDATE SET last_id = last_id + excluded.last_id
               RETURNING last_id""",
            (name, count),
        ).fetchone()[0]
        return list(range(last_id - count + 1, last_id + 1))

    # -------------
    # player saves
    # -------------

    def write_gscd(self, gscd: str) -> None:
        """Create the row of a new Game Sync ID, with its starting garden, chest, and decor.

        Do nothing if the row exists.
        """
        conn = self._conn
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM player_saves WHERE gscd = ?", (gscd,)).fetchone():
                return
            conn.execute("INSERT INTO player_saves (gscd, chest_data) VALUES (?, ?)",
                         (gscd, _to_json(starting_chest())))
            for plot in starting_garden(self._next_id(conn, "my_croft_id", STARTING_PLOTS)):
                self._insert_row(conn, "garden_plots", gscd, plot)
            for decor in starting_decor(self._next_id(conn, "my_interior_id", len(STARTING_DECOR_IDS))):
                self._insert_row(conn, "owned_decor", gscd, decor)

    def gscd_exists(self, gscd: str) -> bool:
        """Whether a Game Sync ID has a row."""
        return self._conn.execute("SELECT 1 FROM player_saves WHERE gscd = ?", (gscd,)).fetchone() is not None

    def find_gscd(self, member_savedata_id: int) -> str | None:
        """The Game Sync ID of the save with this member_savedata_id, if there is one."""
        row = self._conn.execute(
            f"SELECT gscd FROM player_saves WHERE {MEMBER_SAVEDATA_ID} = ?", (member_savedata_id,)).fetchone()
        return row["gscd"] if row else None

    def find_gscd_by_friend_code(self, friend_code: int) -> str | None:
        """The Game Sync ID of the save whose last Game Sync had this Friend Code, if there is one."""
        row = self._conn.execute(f"SELECT gscd FROM player_saves WHERE {FRIEND_CODE} = ?", (friend_code,)).fetchone()
        return row["gscd"] if row else None

    def get_all_gscds(self) -> list[str]:
        """Return every Game Sync ID with a row."""
        return [row["gscd"] for row in self._conn.execute("SELECT gscd FROM player_saves")]

    def _upsert(self, conn: sqlite3.Connection, gscd: str, column: str, data: dict | None) -> None:
        query = f"""
            INSERT INTO player_saves (gscd, {column})
            VALUES (?, ?)
            ON CONFLICT(gscd) DO UPDATE SET {column} = excluded.{column};
        """
        conn.execute(query, (gscd, None if data is None else _to_json(data)))

    def read(self, gscd: str, column: str) -> dict | None:
        """One column of a save. None if the row or the column is empty."""
        self._validate_column(column)
        row = self._conn.execute(f"SELECT {column} FROM player_saves WHERE gscd = ?", (gscd,)).fetchone()
        return json.loads(row[column]) if row and row[column] else None

    def update(self, gscd: str, column: str, change: Callable[[dict], None]) -> dict:
        """Read, modify, and write one column in a single write transaction.

        Concurrent updates (other threads, or the other server's process) can't overwrite
        each other. `change` edits the dict in place ({} if the column is empty). The
        dict is returned.
        """
        self._validate_column(column)
        conn = self._conn
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(f"SELECT {column} FROM player_saves WHERE gscd = ?", (gscd,)).fetchone()
            data = json.loads(row[column]) if row and row[column] else {}
            change(data)
            self._upsert(conn, gscd, column, data)
        return data

    def write_full_state(self, gscd: str, player_data: dict, game_sync: dict, sleeping_pokemon: dict | None) -> None:
        """Replace the three columns a Game Sync writes in a single transaction."""
        query = """
            INSERT INTO player_saves (gscd, player_data, game_sync, sleeping_pokemon)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(gscd) DO UPDATE SET
                player_data = excluded.player_data,
                game_sync = excluded.game_sync,
                sleeping_pokemon = excluded.sleeping_pokemon
        """
        with self._conn:
            self._conn.execute(query, (gscd, _to_json(player_data), _to_json(game_sync), _to_json(sleeping_pokemon)))

    def read_full_state(self, gscd: str) -> tuple[dict | None, dict | None, dict | None] | None:
        """(player_data, game_sync, sleeping_pokemon) of a save, or None if it has no row."""
        row = self._conn.execute(
            "SELECT player_data, game_sync, sleeping_pokemon FROM player_saves WHERE gscd = ?", (gscd,)
        ).fetchone()
        if row is None:
            return None
        player_data, game_sync, sleeping_pokemon = (json.loads(column) if column else None for column in row)
        return player_data, game_sync, sleeping_pokemon

    # ------------------------------------------
    # Garden plots, Share Shelf items, and Decor
    # ------------------------------------------

    def read_rows(self, table: str, gscd: str) -> list[dict]:
        """Return the rows `gscd` owns in one of ROW_TABLES, oldest id first, without the gscd column."""
        return self._read_rows(self._conn, table, gscd)

    def _read_rows(self, conn: sqlite3.Connection, table: str, gscd: str) -> list[dict]:
        id_column = self._id_column(table)
        rows = conn.execute(f"SELECT * FROM {table} WHERE gscd = ? ORDER BY {id_column}", (gscd,))
        return [{key: value for key, value in dict(row).items() if key != "gscd"} for row in rows]

    def update_rows(self, table: str, gscd: str, change: Callable[[list[dict]], None]) -> list[dict]:
        """Read, modify, and write the rows `gscd` owns in one of ROW_TABLES.

        `change` edits the list in place. Only the rows that changed are written, and
        nothing is written if `change` raises. The edited rows are returned.
        """
        id_column = self._id_column(table)
        conn = self._conn
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            before = {row[id_column]: row for row in self._read_rows(conn, table, gscd)}
            rows = [dict(row) for row in before.values()]
            change(rows)

            # deleting first frees the positions that the new rows may take
            kept = {row[id_column] for row in rows}
            conn.executemany(f"DELETE FROM {table} WHERE {id_column} = ? AND gscd = ?",
                             [(row_id, gscd) for row_id in before.keys() - kept])
            for row in rows:
                old = before.get(row[id_column])
                if old is None:
                    self._insert_row(conn, table, gscd, row)
                elif row != old:
                    columns = [column for column in row if column != id_column]
                    conn.execute(
                        f"UPDATE {table} SET {', '.join(f'{column} = ?' for column in columns)}"
                        f" WHERE {id_column} = ? AND gscd = ?",
                        [*(row[column] for column in columns), row[id_column], gscd])
        return rows

    @staticmethod
    def _insert_row(conn: sqlite3.Connection, table: str, gscd: str, row: dict) -> None:
        columns = ["gscd", *row]
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                     [gscd, *row.values()])

    # ----------
    # Dream Pals
    # ----------

    def request_dream_pal(self, from_gscd: str, to_gscd: str, now: str) -> bool:
        """Record a Dream Pal request and return whether the two are now Dream Pals.

        If `to_gscd` already requested `from_gscd`, the two become Dream Pals immediately.
        """
        conn = self._conn
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            status = self._dream_pal_status(conn, from_gscd, to_gscd)
            if status == DreamPalStatus.REQUESTED:
                conn.executemany("UPDATE dream_pals SET status = ?, created_at = ? WHERE from_gscd = ? AND to_gscd = ?",
                                 [(DreamPalStatus.PALS, now, from_gscd, to_gscd),
                                  (DreamPalStatus.PALS, now, to_gscd, from_gscd)])
                return True
            if status == DreamPalStatus.NONE:
                conn.executemany("INSERT INTO dream_pals (from_gscd, to_gscd, status, created_at) VALUES (?, ?, ?, ?)",
                                 [(from_gscd, to_gscd, DreamPalStatus.REQUESTING, now),
                                  (to_gscd, from_gscd, DreamPalStatus.REQUESTED, now)])
            return status == DreamPalStatus.PALS

    @staticmethod
    def _dream_pal_status(conn: sqlite3.Connection, gscd: str, other: str) -> DreamPalStatus:
        row = conn.execute("SELECT status FROM dream_pals WHERE from_gscd = ? AND to_gscd = ?",
                           (gscd, other)).fetchone()
        return DreamPalStatus(row[0]) if row else DreamPalStatus.NONE

    def dream_pal_status(self, gscd: str, other: str) -> DreamPalStatus:
        """How `gscd` stands with `other`."""
        return self._dream_pal_status(self._conn, gscd, other)

    def dream_pals(self, gscd: str, status: DreamPalStatus) -> list[str]:
        """Return the relationships `gscd` has with others, oldest first."""
        return [row[0] for row in self._conn.execute(
            "SELECT to_gscd FROM dream_pals WHERE from_gscd = ? AND status = ? ORDER BY created_at, to_gscd",
            (gscd, status))]

    def dream_pal_visit_counts(self, gscd: str) -> dict[str, int]:
        """Return how many days `gscd` has visited each of their Dream Pals."""
        return dict(self._conn.execute(
            "SELECT to_gscd, visit_count FROM dream_pals WHERE from_gscd = ? AND status = ?",
            (gscd, DreamPalStatus.PALS)).fetchall())

    def record_dream_pal_visit(self, gscd: str, other: str, today: str) -> int:
        """Count a visit from `gscd` to Dream Pal `other` and return how many days `gscd` has visited.

        Only the first visit on each day counts. If the two aren't Dream Pals, nothing is
        recorded and the result is 0.
        """
        conn = self._conn
        with conn:
            conn.execute(
                """UPDATE dream_pals SET visit_count = visit_count + 1, last_visit_date = ?
                   WHERE from_gscd = ? AND to_gscd = ? AND status = ? AND last_visit_date IS NOT ?""",
                (today, gscd, other, DreamPalStatus.PALS, today))
            row = conn.execute("SELECT visit_count FROM dream_pals WHERE from_gscd = ? AND to_gscd = ? AND status = ?",
                               (gscd, other, DreamPalStatus.PALS)).fetchone()
        return row[0] if row else 0

    def expire_stale(self, now: str) -> None:
        """Delete the footprints and unanswered Dream Pal requests that are EXPIRES_AFTER old at `now`."""
        cutoff = (datetime.strptime(now, TIME_FORMAT) - EXPIRES_AFTER).strftime(TIME_FORMAT)
        with self._conn:
            self._conn.execute("DELETE FROM footprints WHERE visited_at <= ?", (cutoff,))
            self._conn.execute("DELETE FROM dream_pals WHERE status != ? AND created_at <= ?",
                               (DreamPalStatus.PALS, cutoff))

    def remove_dream_pal(self, gscd: str, other: str) -> None:
        """Delete everything between `gscd` and `other`, which cancels a request or ends a friendship."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM dream_pals WHERE (from_gscd, to_gscd) IN ((?, ?), (?, ?))", (gscd, other, other, gscd))

    # ------------
    # footprints
    # ------------

    def record_footprint(self, island_gscd: str, visitor_gscd: str, now: str) -> None:
        """Record that `visitor_gscd` is visiting `island_gscd`'s island at `now` (a now_jst_str time)."""
        with self._conn:
            self._conn.execute(
                """INSERT INTO footprints (island_gscd, visitor_gscd, visited_at) VALUES (?, ?, ?)
                   ON CONFLICT (island_gscd, visitor_gscd) DO UPDATE SET
                       watered = CASE WHEN substr(visited_at, 1, 10) = substr(excluded.visited_at, 1, 10)
                                      THEN watered ELSE 0 END,
                       swapped = CASE WHEN substr(visited_at, 1, 10) = substr(excluded.visited_at, 1, 10)
                                      THEN swapped ELSE 0 END,
                       visited_at = excluded.visited_at""",
                (island_gscd, visitor_gscd, now))

    def mark_footprint(self, island_gscd: str, visitor_gscd: str, action: str, now: str) -> None:
        """Record that `visitor_gscd` watered (`action` "watered") or swapped ("swapped") on `island_gscd`'s island."""
        if action not in ("watered", "swapped"):
            raise ValueError(f"Unknown footprint action {action!r}")
        self.record_footprint(island_gscd, visitor_gscd, now)
        with self._conn:
            self._conn.execute(f"UPDATE footprints SET {action} = 1 WHERE island_gscd = ? AND visitor_gscd = ?",
                               (island_gscd, visitor_gscd))

    def footprints(self, island_gscd: str) -> list[dict]:
        """Return the visitors to `island_gscd`'s island."""
        rows = self._conn.execute(
            "SELECT * FROM footprints WHERE island_gscd = ? ORDER BY visited_at DESC, visitor_gscd", (island_gscd,))
        return [dict(row) for row in rows]

    # ------------
    # records
    # ------------

    def add_record_upload(self, gscd: str, uploaded_at: int, rom_id: int, country: int | None,
                          records: dict[str, int | None]) -> None:
        """Store the records from a save the player uploaded at `uploaded_at`, replacing their last ones.

        `country` is the PGL country of the account the save is linked to, or None if it
        isn't linked to one yet. `records` is SaveFile.records.
        """
        columns = ["gscd", "uploaded_at", "rom_id", "country", *RECORD_COLUMNS]
        values = [gscd, uploaded_at, rom_id, country, *(records[name] for name in RECORD_COLUMNS)]
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO record_uploads ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                values)

    def read_record_upload(self, gscd: str) -> dict | None:
        """Return the records from a player's last uploaded save, or None if they never uploaded one."""
        row = self._conn.execute("SELECT * FROM record_uploads WHERE gscd = ?", (gscd,)).fetchone()
        return dict(row) if row else None

    # -----------------------
    # Pal Pad and Trade Pals
    # -----------------------

    def _set_friend_codes(self, table: str, gscd: str, friend_codes: list[int]) -> None:
        with self._conn:
            self._conn.execute(f"DELETE FROM {table} WHERE gscd = ?", (gscd,))
            self._conn.executemany(f"INSERT OR IGNORE INTO {table} (gscd, friend_code) VALUES (?, ?)",
                                   [(gscd, code) for code in friend_codes])

    def _read_friend_codes(self, table: str, gscd: str) -> list[int]:
        rows = self._conn.execute(f"SELECT friend_code FROM {table} WHERE gscd = ? ORDER BY rowid", (gscd,))
        return [row["friend_code"] for row in rows]

    def set_pal_pad(self, gscd: str, friend_codes: list[int]) -> None:
        """Replace the Friend Codes on a player's Pal Pad."""
        self._set_friend_codes("pal_pad", gscd, friend_codes)

    def read_pal_pad(self, gscd: str) -> list[int]:
        """Return the Friend Codes on a player's Pal Pad."""
        return self._read_friend_codes("pal_pad", gscd)

    def set_trade_pals(self, gscd: str, friend_codes: list[int]) -> None:
        """Replace the Friend Codes on a player's Trade Pal list."""
        self._set_friend_codes("trade_pals", gscd, friend_codes)

    def read_trade_pals(self, gscd: str) -> list[int]:
        """Return the Friend Codes on a player's Trade Pal list."""
        return self._read_friend_codes("trade_pals", gscd)

    # ------------------
    # Nintendo WFC users
    # ------------------

    def save_wfc_user(self, user_id: str, password: str, profiles: dict) -> None:
        """Create or replace a Nintendo WFC user.

        `profiles` maps a branch code to the fields of a GameProfile.
        """
        query = """
            INSERT INTO wfc_users (user_id, password, profiles)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                password = excluded.password,
                profiles = excluded.profiles
        """
        with self._conn:
            self._conn.execute(query, (user_id, password, json.dumps(profiles, ensure_ascii=False)))

    def get_all_wfc_users(self) -> list[dict]:
        """Every Nintendo WFC user, as {"id", "password", "profiles"}."""
        return [
            {
                "id": row["user_id"],
                "password": row["password"],
                "profiles": json.loads(row["profiles"]) if row["profiles"] else {},
            }
            for row in self._conn.execute("SELECT user_id, password, profiles FROM wfc_users")
        ]


db = DBManager(SAVE_DIR / "pokemon_saves.db")
