"""Execute a move plan.

Every move is copy → verify → remove, in that order. If the machine loses power
halfway through, the source is still there; the worst case is a stray partial
copy at the destination, which the next run replaces.

Nothing runs without --execute, and every action is appended to a journal so
`fileorg undo` can walk it backwards.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import hashing, icloud
from .catalog import update_fields
from .plan import MoveOp
from .scan import human
from .settings import Settings


@dataclass
class ApplyStats:
    attempted: int = 0
    moved: int = 0
    bytes: int = 0
    skipped_missing: int = 0
    skipped_filtered: int = 0
    failed_verify: int = 0
    failed_other: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.moved}/{self.attempted} moved ({human(self.bytes)}), "
            f"{self.skipped_missing} sources gone, "
            f"{self.failed_verify} failed verification, {self.failed_other} errors"
        )


class Journal:
    """Append-only record of what actually happened, flushed after every op."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a", encoding="utf-8")

    def write(self, **entry) -> None:
        entry.setdefault("at", time.time())
        self._handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _copy(src: Path, dst: Path, is_bundle: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_bundle or src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _discard(path: Path) -> None:
    """Clean up a destination we failed to verify."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    except OSError:
        pass


def execute(
    ops: list[MoveOp],
    settings: Settings,
    conn=None,
    journal_path: Path | None = None,
    verify: bool = True,
    categories: set[str] | None = None,
    machine: str | None = None,
    limit: int | None = None,
    progress: bool = True,
) -> tuple[ApplyStats, Path]:
    """Carry out a plan. Assumes the caller has already confirmed intent."""
    stats = ApplyStats()
    journal_path = journal_path or (
        settings.workdir / f"journal-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    )

    with Journal(journal_path) as journal:
        journal.write(
            event="start",
            library_root=str(settings.library_root),
            archive_root=str(settings.archive_root),
            ops=len(ops),
            verify=verify,
        )

        for op in ops:
            if categories and op.category not in categories:
                stats.skipped_filtered += 1
                continue
            if machine and op.machine != machine:
                stats.skipped_filtered += 1
                continue
            if limit is not None and stats.moved >= limit:
                stats.skipped_filtered += 1
                continue

            stats.attempted += 1
            src, dst = Path(op.src), Path(op.dst)

            if not src.exists():
                stats.skipped_missing += 1
                journal.write(event="skip", reason="source missing", src=op.src, dst=op.dst)
                continue

            # An evicted iCloud file has to come down before it can be copied.
            if not icloud.ensure_local(src):
                stats.failed_other += 1
                message = f"could not download from iCloud: {op.src}"
                stats.errors.append(message)
                journal.write(event="error", reason=message, src=op.src, dst=op.dst)
                continue

            try:
                digest = hashing.hash_any(src) if verify else None
                _copy(src, dst, bool(op.is_bundle))

                if verify:
                    if hashing.hash_any(dst) != digest:
                        _discard(dst)
                        stats.failed_verify += 1
                        message = f"hash mismatch after copy, source kept: {op.src}"
                        stats.errors.append(message)
                        journal.write(
                            event="error", reason=message, src=op.src, dst=op.dst
                        )
                        continue

                _remove(src)
            except OSError as exc:
                stats.failed_other += 1
                message = f"{op.src}: {exc}"
                stats.errors.append(message)
                journal.write(event="error", reason=message, src=op.src, dst=op.dst)
                continue

            journal.write(
                event="move",
                status="ok",
                src=op.src,
                dst=op.dst,
                size=op.size,
                hash=digest,
                category=op.category,
                machine=op.machine,
                file_id=op.file_id,
                is_bundle=op.is_bundle,
            )
            if conn is not None:
                update_fields(conn, op.file_id, path=op.dst, full_hash=digest)

            stats.moved += 1
            stats.bytes += op.size

            if progress and stats.moved % 25 == 0:
                print(
                    f"  moved {stats.moved} items ({human(stats.bytes)})…",
                    end="\r",
                    flush=True,
                )

        journal.write(event="end", moved=stats.moved, bytes=stats.bytes)

    if conn is not None:
        conn.commit()
    if progress:
        print(" " * 60, end="\r")
    return stats, journal_path


def preview(ops: list[MoveOp], settings: Settings, limit: int = 20) -> str:
    """What --execute would do, as text."""
    lines = []
    for op in ops[:limit]:
        lines.append(f"  {op.src}\n    → {op.dst}   [{op.category}, {op.decided_by}]")
    if len(ops) > limit:
        lines.append(f"  … and {len(ops) - limit} more")
    return "\n".join(lines)
