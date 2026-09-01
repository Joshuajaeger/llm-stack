"""Turn classifications into a concrete list of moves.

The plan is a plain JSONL file. Read it, edit it, delete lines you disagree
with — `apply` only ever does what the plan says. That separation is the whole
point: you review the decisions before a single byte moves.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .catalog import iter_files
from .scan import human
from .settings import Settings


@dataclass
class MoveOp:
    file_id: int
    machine: str
    src: str
    dst: str
    size: int
    category: str
    decided_by: str
    confidence: float | None
    is_bundle: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def from_json(line: str) -> "MoveOp":
        return MoveOp(**json.loads(line))


@dataclass
class PlanStats:
    ops: int = 0
    bytes: int = 0
    already_in_place: int = 0
    missing_source: int = 0
    renamed_for_collision: int = 0
    by_category: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.ops} moves ({human(self.bytes)}), "
            f"{self.already_in_place} already in place, "
            f"{self.renamed_for_collision} renamed to avoid collisions, "
            f"{self.missing_source} sources missing"
        )


def unique_destination(candidate: Path, claimed: set[str]) -> tuple[Path, bool]:
    """Find a free filename, appending -2, -3, … when needed."""
    key = str(candidate).lower()
    if key not in claimed and not candidate.exists():
        claimed.add(key)
        return candidate, False

    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while True:
        attempt = candidate.with_name(f"{stem}-{counter}{suffix}")
        key = str(attempt).lower()
        if key not in claimed and not attempt.exists():
            claimed.add(key)
            return attempt, True
        counter += 1


def _relative(record) -> Path:
    """Where the file sat inside the root it was scanned from."""
    try:
        return Path(record.path).relative_to(Path(record.root))
    except ValueError:
        return Path(record.name)


def destination_for(record, settings: Settings, claimed: set[str]) -> tuple[Path, bool]:
    """Where a single catalogued file should end up."""
    category = record.category or settings.review_category

    if category == settings.duplicates_category:
        # Quarantine keeps the original shape so you can see what came from
        # where before deciding anything is really redundant.
        base = settings.library_root / category / record.machine / _relative(record)
        return unique_destination(base, claimed)

    directory = settings.category_dir(category)

    if any(category.startswith(prefix) for prefix in settings.preserve_structure):
        # Source trees and project folders keep their layout; flattening them
        # into one directory would destroy the thing that makes them usable.
        return unique_destination(directory / record.machine / _relative(record), claimed)

    if category in settings.date_partitioned:
        stamp = record.birthtime or record.mtime
        directory = directory / str(time.localtime(stamp).tm_year)

    return unique_destination(directory / record.name, claimed)


def build(conn, settings: Settings, machine: str | None = None) -> tuple[list[MoveOp], PlanStats]:
    stats = PlanStats()
    ops: list[MoveOp] = []
    claimed: set[str] = set()

    where = "category IS NOT NULL"
    params: tuple = ()
    if machine:
        where += " AND machine = ?"
        params = (machine,)

    for record in iter_files(conn, where, params):
        source = Path(record.path)
        if not source.exists():
            stats.missing_source += 1
            continue

        destination, renamed = destination_for(record, settings, claimed)
        if renamed:
            stats.renamed_for_collision += 1

        if source == destination:
            stats.already_in_place += 1
            continue

        ops.append(
            MoveOp(
                file_id=record.id,
                machine=record.machine,
                src=str(source),
                dst=str(destination),
                size=record.size,
                category=record.category,
                decided_by=record.decided_by or "",
                confidence=record.confidence,
                is_bundle=record.is_bundle,
            )
        )
        stats.ops += 1
        stats.bytes += record.size
        stats.by_category[record.category] = stats.by_category.get(record.category, 0) + 1

    return ops, stats


def write(ops: list[MoveOp], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for op in ops:
            handle.write(op.to_json() + "\n")
    return path


def read(path: Path | str) -> list[MoveOp]:
    ops = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                ops.append(MoveOp.from_json(line))
    return ops
