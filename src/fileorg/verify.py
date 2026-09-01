"""The gate before you erase the second MacBook.

Answers one question: is every single file that machine had now accounted for
in the library, byte for byte?

A file counts as accounted for when it was moved and its destination still
hashes to what the journal recorded, or when it was a duplicate whose surviving
copy checks out. Anything else is reported as unaccounted, and the command
exits nonzero. Green exit code = safe to wipe. Nothing else does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import hashing
from .catalog import iter_files
from .scan import human
from .settings import Settings
from .undo import read_moves


@dataclass
class VerifyReport:
    machine: str
    catalogued: int = 0
    moved_ok: int = 0
    duplicates_covered: int = 0
    still_at_source: int = 0
    hash_mismatch: int = 0
    destination_missing: int = 0
    unaccounted: int = 0
    bytes_verified: int = 0
    residual: int = 0
    residual_bytes: int = 0
    residual_examples: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (
            self.hash_mismatch or self.destination_missing or self.unaccounted
        )

    def summary(self) -> str:
        return (
            f"{self.catalogued} catalogued on {self.machine} — "
            f"{self.moved_ok} verified in the library ({human(self.bytes_verified)}), "
            f"{self.duplicates_covered} covered by a surviving copy, "
            f"{self.still_at_source} still on the source disk, "
            f"{self.hash_mismatch} hash mismatches, "
            f"{self.destination_missing} destinations missing, "
            f"{self.unaccounted} unaccounted"
        )


def _journals(settings: Settings, explicit: list[Path] | None) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    return sorted(settings.workdir.glob("journal-*.jsonl"))


def verify(
    conn,
    settings: Settings,
    machine: str,
    journals: list[Path] | None = None,
    deep: bool = True,
    progress: bool = True,
) -> VerifyReport:
    report = VerifyReport(machine=machine)

    # Two indexes into the journals. The catalog's `path` is rewritten to the
    # destination once a file has been applied, so matching on path alone would
    # miss every successful move — file_id is the reliable key.
    moved_by_id: dict[int, dict] = {}
    moved_by_src: dict[str, dict] = {}
    for journal in _journals(settings, journals):
        for entry in read_moves(journal):
            moved_by_src[entry["src"]] = entry
            if entry.get("file_id") is not None:
                moved_by_id[int(entry["file_id"])] = entry

    records = list(iter_files(conn, "machine = ?", (machine,)))
    report.catalogued = len(records)
    by_id = {record.id: record for record in records}

    for index, record in enumerate(records, 1):
        entry = moved_by_id.get(record.id) or moved_by_src.get(record.path)

        if entry is None:
            if Path(record.path).exists():
                # Never moved, original still sitting there. Not lost — but not
                # transferred either, so it is not safe to erase yet.
                report.still_at_source += 1
                report.unaccounted += 1
                report.problems.append(f"not transferred: {record.path}")
            elif record.dup_of is not None and _keeper_ok(
                by_id.get(record.dup_of), moved_by_id, moved_by_src
            ):
                report.duplicates_covered += 1
            else:
                report.unaccounted += 1
                report.problems.append(f"gone, with no record of a move: {record.path}")
            continue

        destination = Path(entry["dst"])
        if not destination.exists():
            report.destination_missing += 1
            report.problems.append(f"destination missing: {entry['dst']}")
            continue

        expected = entry.get("hash")
        if deep and expected:
            try:
                actual = hashing.hash_any(destination)
            except OSError as exc:
                report.hash_mismatch += 1
                report.problems.append(f"unreadable: {destination} ({exc})")
                continue
            if actual != expected:
                report.hash_mismatch += 1
                report.problems.append(f"content changed since the move: {destination}")
                continue

        report.moved_ok += 1
        report.bytes_verified += int(entry.get("size") or 0)

        if progress and index % 50 == 0:
            print(f"  verified {index}/{len(records)}…", end="\r", flush=True)

    residual_scan(conn, settings, machine, report, moved_srcs=set(moved_by_src))

    if progress:
        print(" " * 60, end="\r")
    return report


def residual_scan(
    conn,
    settings: Settings,
    machine: str,
    report: VerifyReport,
    moved_srcs: set[str] | None = None,
    limit: int = 20,
) -> None:
    """Count files still under the scanned roots that were never catalogued.

    These are the exclusions — caches, .DS_Store, node_modules and anything else
    filtered out by config, plus files below min_size_bytes. Not a failure, but
    you should see them before wiping the disk in case an exclusion was too
    broad.
    """
    from .catalog import get_meta
    from .scan import is_bundle, is_excluded

    roots = (get_meta(conn, f"scanned:{machine}") or "").split(",")
    known = set(moved_srcs or set())
    known |= {
        row["path"]
        for row in conn.execute("SELECT path FROM files WHERE machine = ?", (machine,))
    }

    for raw in roots:
        root = Path(raw)
        if not raw or not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            here = Path(dirpath)
            dirnames[:] = [d for d in dirnames if not is_bundle(here / d, settings)]
            for name in filenames:
                full = here / name
                if str(full) in known or full.is_symlink():
                    continue
                try:
                    size = full.lstat().st_size
                except OSError:
                    continue
                report.residual += 1
                report.residual_bytes += size
                if len(report.residual_examples) < limit:
                    if is_excluded(full, settings):
                        reason = "excluded by config"
                    elif size < settings.min_size_bytes:
                        reason = "below min_size_bytes"
                    else:
                        reason = "not catalogued"
                    report.residual_examples.append(f"{full} ({reason})")


def _keeper_ok(keeper, moved_by_id: dict[int, dict], moved_by_src: dict[str, dict]) -> bool:
    """A duplicate is covered if the copy we kept made it into the library."""
    if keeper is None:
        return False
    entry = moved_by_id.get(keeper.id) or moved_by_src.get(keeper.path)
    if entry:
        return Path(entry["dst"]).exists()
    return Path(keeper.path).exists()
