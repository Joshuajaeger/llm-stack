"""Walk a journal backwards and put everything back.

Same copy → verify → remove discipline as the forward direction, so an undo
that gets interrupted is no more dangerous than the move that preceded it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import hashing
from .apply import Journal, _copy, _discard, _remove
from .catalog import update_fields
from .scan import human
from .settings import Settings


@dataclass
class UndoStats:
    entries: int = 0
    restored: int = 0
    bytes: int = 0
    skipped_source_exists: int = 0
    skipped_missing: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.restored}/{self.entries} restored ({human(self.bytes)}), "
            f"{self.skipped_source_exists} left alone (original already back), "
            f"{self.skipped_missing} missing, {self.failed} failed"
        )


def latest_journal(settings: Settings) -> Path | None:
    journals = sorted(settings.workdir.glob("journal-*.jsonl"))
    return journals[-1] if journals else None


def read_moves(journal_path: Path | str) -> list[dict]:
    moves = []
    with open(journal_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("event") == "move" and entry.get("status") == "ok":
                moves.append(entry)
    return moves


def execute(
    journal_path: Path | str,
    settings: Settings,
    conn=None,
    verify: bool = True,
    progress: bool = True,
) -> tuple[UndoStats, Path]:
    stats = UndoStats()
    moves = list(reversed(read_moves(journal_path)))
    stats.entries = len(moves)

    source = Path(journal_path)
    undo_path = source.with_name(f"{source.stem}.undo.jsonl")

    with Journal(undo_path) as journal:
        journal.write(event="start", undoing=str(journal_path), entries=len(moves))

        for entry in moves:
            src, dst = Path(entry["src"]), Path(entry["dst"])

            if src.exists():
                stats.skipped_source_exists += 1
                continue
            if not dst.exists():
                stats.skipped_missing += 1
                journal.write(event="skip", reason="destination missing", src=str(src), dst=str(dst))
                continue

            try:
                digest = hashing.hash_any(dst) if verify else None
                _copy(dst, src, bool(entry.get("is_bundle")))
                if verify and hashing.hash_any(src) != digest:
                    _discard(src)
                    stats.failed += 1
                    message = f"hash mismatch restoring {dst} → {src}"
                    stats.errors.append(message)
                    journal.write(event="error", reason=message, src=str(src), dst=str(dst))
                    continue
                _remove(dst)
            except OSError as exc:
                stats.failed += 1
                message = f"{dst}: {exc}"
                stats.errors.append(message)
                journal.write(event="error", reason=message, src=str(src), dst=str(dst))
                continue

            journal.write(event="restore", status="ok", src=str(src), dst=str(dst))
            # Point the catalog back at the original location, or the next
            # plan/verify would chase files that are no longer there.
            if conn is not None and entry.get("file_id") is not None:
                update_fields(conn, int(entry["file_id"]), path=str(src))
            stats.restored += 1
            stats.bytes += int(entry.get("size") or 0)

            if progress and stats.restored % 25 == 0:
                print(f"  restored {stats.restored} items…", end="\r", flush=True)

        journal.write(event="end", restored=stats.restored)

    if conn is not None:
        conn.commit()

    if progress:
        print(" " * 60, end="\r")
    return stats, undo_path
