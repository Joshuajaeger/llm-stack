"""SQLite catalog: one row per file, from any machine.

This is the index that makes the library searchable, and the ledger the
verification step reads to prove nothing was lost before a Mac is erased.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator, Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY,
    machine     TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    root        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    ext         TEXT    NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL    NOT NULL DEFAULT 0,
    birthtime   REAL,
    is_bundle   INTEGER NOT NULL DEFAULT 0,
    dataless    INTEGER NOT NULL DEFAULT 0,
    quick_hash  TEXT,
    full_hash   TEXT,
    category    TEXT,
    decided_by  TEXT,
    confidence  REAL,
    dup_of      INTEGER,
    scanned_at  REAL NOT NULL,
    UNIQUE(machine, path)
);

CREATE INDEX IF NOT EXISTS idx_files_size      ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_full_hash ON files(full_hash);
CREATE INDEX IF NOT EXISTS idx_files_category  ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_name      ON files(name);
CREATE INDEX IF NOT EXISTS idx_files_ext       ON files(ext);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

COLUMNS = (
    "machine", "path", "root", "name", "ext", "size", "mtime", "birthtime",
    "is_bundle", "dataless", "quick_hash", "full_hash", "category",
    "decided_by", "confidence", "dup_of", "scanned_at",
)

# Facts about the file on disk. A rescan always refreshes these.
FS_COLUMNS = (
    "root", "name", "ext", "size", "mtime", "birthtime",
    "is_bundle", "dataless", "scanned_at",
)

# Conclusions we drew about the file. A rescan keeps these as long as the file
# itself hasn't changed — otherwise re-scanning would silently throw away the
# dedupe and classification work that came before it.
ANALYSIS_COLUMNS = (
    "quick_hash", "full_hash", "category", "decided_by", "confidence", "dup_of",
)

UNCHANGED = "files.size = excluded.size AND files.mtime = excluded.mtime"


@dataclass
class FileRecord:
    machine: str
    path: str
    root: str
    name: str
    ext: str = ""
    size: int = 0
    mtime: float = 0.0
    birthtime: float | None = None
    is_bundle: int = 0
    dataless: int = 0
    quick_hash: str | None = None
    full_hash: str | None = None
    category: str | None = None
    decided_by: str | None = None
    confidence: float | None = None
    dup_of: int | None = None
    scanned_at: float = 0.0
    id: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FileRecord":
        return cls(**{k: row[k] for k in row.keys()})


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) a catalog database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def upsert_many(conn: sqlite3.Connection, records: Iterable[FileRecord]) -> int:
    """Insert or refresh a batch of records, keyed on (machine, path)."""
    now = time.time()
    rows = []
    for rec in records:
        data = asdict(rec)
        data.pop("id", None)
        if not data["scanned_at"]:
            data["scanned_at"] = now
        rows.append(tuple(data[c] for c in COLUMNS))

    if not rows:
        return 0

    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.executemany(
        f"INSERT INTO files ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(machine, path) DO UPDATE SET {_scan_upsert_clause()}",
        rows,
    )
    conn.commit()
    return len(rows)


def _scan_upsert_clause() -> str:
    parts = [f"{c}=excluded.{c}" for c in FS_COLUMNS]
    parts += [
        f"{c} = CASE WHEN {UNCHANGED} THEN files.{c} ELSE NULL END"
        for c in ANALYSIS_COLUMNS
    ]
    return ", ".join(parts)


def update_fields(conn: sqlite3.Connection, file_id: int, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE files SET {assignments} WHERE id = ?",
        (*fields.values(), file_id),
    )


def iter_files(
    conn: sqlite3.Connection,
    where: str = "",
    params: tuple = (),
    order: str = "path",
) -> Iterator[FileRecord]:
    sql = "SELECT * FROM files"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    for row in conn.execute(sql, params):
        yield FileRecord.from_row(row)


def count(conn: sqlite3.Connection, where: str = "", params: tuple = ()) -> int:
    sql = "SELECT COUNT(*) AS n FROM files"
    if where:
        sql += f" WHERE {where}"
    return int(conn.execute(sql, params).fetchone()["n"])


def total_size(conn: sqlite3.Connection, where: str = "", params: tuple = ()) -> int:
    sql = "SELECT COALESCE(SUM(size), 0) AS n FROM files"
    if where:
        sql += f" WHERE {where}"
    return int(conn.execute(sql, params).fetchone()["n"])


def merge(dest: sqlite3.Connection, source_db: Path | str) -> int:
    """Copy every row from another catalog into this one.

    Used to pull the second Mac's catalog onto the keeper for cross-machine
    dedupe. Rows are keyed on (machine, path), so merging is idempotent as long
    as the two machines have distinct labels.
    """
    dest.execute("ATTACH DATABASE ? AS src", (str(source_db),))
    try:
        cols = ", ".join(COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c not in ("machine", "path"))
        cur = dest.execute(
            # The trailing WHERE is required: with INSERT…SELECT, SQLite cannot
            # tell ON CONFLICT from a join constraint without it.
            f"INSERT INTO files ({cols}) SELECT {cols} FROM src.files WHERE true "
            f"ON CONFLICT(machine, path) DO UPDATE SET {updates}"
        )
        dest.commit()
        return cur.rowcount
    finally:
        dest.execute("DETACH DATABASE src")


def machines(conn: sqlite3.Connection) -> list[str]:
    return [r["machine"] for r in conn.execute("SELECT DISTINCT machine FROM files ORDER BY machine")]
