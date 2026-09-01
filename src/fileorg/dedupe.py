"""Duplicate detection across one or both Macs.

Three tiers, cheapest first:

    size  →  head+tail sample hash  →  full content hash

Only files that survive a tier get promoted to the next one, so a library with
few real duplicates is barely hashed at all.

Nothing is deleted here. Duplicates are marked in the catalog and written to a
manifest; the planner later routes them to the quarantine folder so you can
look before anything goes away.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import hashing, icloud
from .catalog import FileRecord, iter_files, update_fields
from .settings import Settings


@dataclass
class DedupeStats:
    candidates: int = 0
    quick_hashed: int = 0
    full_hashed: int = 0
    materialized: int = 0
    unreadable: int = 0
    duplicate_sets: int = 0
    redundant_files: int = 0
    reclaimable_bytes: int = 0

    def summary(self) -> str:
        from .scan import human

        return (
            f"{self.duplicate_sets} duplicate sets, {self.redundant_files} redundant copies, "
            f"{human(self.reclaimable_bytes)} reclaimable "
            f"({self.full_hashed} full hashes, {self.materialized} downloaded from iCloud)"
        )


@dataclass
class DuplicateSet:
    full_hash: str
    keeper: FileRecord
    redundant: list[FileRecord] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        return sum(r.size for r in self.redundant)


def _readable(record: FileRecord, stats: DedupeStats) -> bool:
    """Make sure a catalog row points at content we can actually hash."""
    path = Path(record.path)
    if not path.exists():
        stats.unreadable += 1
        return False
    if record.dataless:
        if not icloud.ensure_local(path):
            stats.unreadable += 1
            return False
        stats.materialized += 1
    return True


def _keeper_rank(record: FileRecord, prefer_machine: str | None) -> tuple:
    """Lower sorts better. Prefer the keeper Mac, then shallow, short, oldest."""
    path = Path(record.path)
    return (
        0 if prefer_machine and record.machine == prefer_machine else 1,
        len(path.parts),
        len(str(path)),
        record.birthtime if record.birthtime is not None else float("inf"),
        str(path),
    )


def find_duplicates(
    conn,
    settings: Settings,
    prefer_machine: str | None = None,
    include_bundles: bool = False,
    progress: bool = True,
) -> tuple[list[DuplicateSet], DedupeStats]:
    stats = DedupeStats()

    bundle_clause = "" if include_bundles else " AND is_bundle = 0"
    sizes = [
        row["size"]
        for row in conn.execute(
            f"SELECT size FROM files WHERE size > 0{bundle_clause} "
            f"GROUP BY size HAVING COUNT(*) > 1"
        )
    ]
    if not sizes:
        return [], stats

    # Tier 1 → 2: same size, so sample-hash them.
    by_quick: dict[tuple[int, str], list[FileRecord]] = defaultdict(list)
    for size in sizes:
        group = list(iter_files(conn, f"size = ?{bundle_clause}", (size,)))
        stats.candidates += len(group)
        for record in group:
            if not _readable(record, stats):
                continue
            try:
                if record.is_bundle:
                    # A bundle has no meaningful head/tail; use its tree hash.
                    quick = hashing.tree_hash(record.path)
                else:
                    quick = hashing.quick_hash(record.path, record.size)
            except OSError:
                stats.unreadable += 1
                continue
            stats.quick_hashed += 1
            record.quick_hash = quick
            update_fields(conn, record.id, quick_hash=quick)
            by_quick[(size, quick)].append(record)
        if progress:
            print(f"  sampled {stats.quick_hashed} candidates…", end="\r", flush=True)
    conn.commit()

    # Tier 2 → 3: same sample, so hash the whole thing.
    by_full: dict[str, list[FileRecord]] = defaultdict(list)
    for (_size, _quick), group in by_quick.items():
        if len(group) < 2:
            continue
        for record in group:
            try:
                full = hashing.hash_any(record.path)
            except OSError:
                stats.unreadable += 1
                continue
            stats.full_hashed += 1
            record.full_hash = full
            update_fields(conn, record.id, full_hash=full)
            by_full[full].append(record)
        if progress:
            print(f"  hashed {stats.full_hashed} candidates…", end="\r", flush=True)
    conn.commit()
    if progress:
        print(" " * 60, end="\r")

    sets: list[DuplicateSet] = []
    for full, group in by_full.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda r: _keeper_rank(r, prefer_machine))
        keeper, redundant = ordered[0], ordered[1:]
        for record in redundant:
            update_fields(conn, record.id, dup_of=keeper.id)
        sets.append(DuplicateSet(full_hash=full, keeper=keeper, redundant=redundant))
        stats.duplicate_sets += 1
        stats.redundant_files += len(redundant)
        stats.reclaimable_bytes += sum(r.size for r in redundant)
    conn.commit()

    sets.sort(key=lambda s: s.wasted_bytes, reverse=True)
    return sets, stats


def write_manifest(sets: Iterable[DuplicateSet], path: Path | str) -> Path:
    """Write a human-readable record of what was matched with what."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for dup in sets:
            handle.write(
                json.dumps(
                    {
                        "full_hash": dup.full_hash,
                        "size": dup.keeper.size,
                        "keep": {"machine": dup.keeper.machine, "path": dup.keeper.path},
                        "redundant": [
                            {"machine": r.machine, "path": r.path} for r in dup.redundant
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path
