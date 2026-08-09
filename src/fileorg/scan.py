"""Filesystem scanner.

Walks the roots you point it at and writes one catalog row per file. Read-only:
scan never modifies, moves, or downloads anything. macOS bundles (.app,
.photoslibrary, …) are recorded as single units rather than descended into,
because splitting a bundle apart destroys it.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from . import icloud
from .catalog import FileRecord, upsert_many
from .settings import Settings

# Scanning these is either meaningless (system-managed) or actively harmful
# (multi-terabyte network volumes, Time Machine). Requires --allow-unsafe.
GUARDED_ROOTS = {
    Path("/"),
    Path("/System"),
    Path("/Library"),
    Path("/Volumes"),
    Path("/private"),
    Path.home() / "Library",
}

BATCH = 500


@dataclass
class ScanStats:
    roots: list[str] = field(default_factory=list)
    files: int = 0
    bundles: int = 0
    bytes: int = 0
    skipped_excluded: int = 0
    skipped_symlinks: int = 0
    skipped_small: int = 0
    dataless: int = 0
    placeholders: int = 0
    errors: int = 0

    def summary(self) -> str:
        return (
            f"{self.files} files ({human(self.bytes)}), {self.bundles} bundles, "
            f"{self.dataless} dataless, {self.placeholders} placeholders, "
            f"{self.skipped_excluded} excluded, {self.errors} errors"
        )


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


class RootRefused(Exception):
    """Raised when a scan root is one of the guarded system paths."""


def check_root(root: Path, allow_unsafe: bool = False) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.exists():
        raise RootRefused(f"{resolved} does not exist")
    if not allow_unsafe and resolved in {p.resolve() for p in GUARDED_ROOTS if p.exists()}:
        raise RootRefused(
            f"refusing to scan {resolved} — system-managed or too broad. "
            f"Pass --allow-unsafe if you really mean it."
        )
    return resolved


def is_excluded(path: Path, settings: Settings) -> bool:
    # Any excluded name anywhere in the path excludes the file. The walk
    # already prunes those directories; this makes the answer correct for
    # callers that ask about a path in isolation.
    if settings.exclude_names.intersection(path.parts):
        return True
    text = str(path)
    name = path.name
    return any(fnmatch(text, pattern) or fnmatch(name, pattern) for pattern in settings.exclude)


def is_bundle(path: Path, settings: Settings) -> bool:
    return path.suffix.lower().lstrip(".") in settings.bundle_extensions


def bundle_size(path: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path, onerror=lambda e: None):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue
    return total


def _record(path: Path, root: Path, st: os.stat_result, settings: Settings, bundle: bool) -> FileRecord:
    return FileRecord(
        machine=settings.machine,
        path=str(path),
        root=str(root),
        name=path.name,
        ext=path.suffix.lower().lstrip("."),
        size=bundle_size(path) if bundle else st.st_size,
        mtime=st.st_mtime,
        birthtime=getattr(st, "st_birthtime", None),
        is_bundle=int(bundle),
        dataless=int(icloud.is_dataless(st)),
        scanned_at=time.time(),
    )


def scan(
    conn,
    roots: Iterable[Path | str],
    settings: Settings,
    allow_unsafe: bool = False,
    progress: bool = True,
) -> ScanStats:
    """Catalog every file under `roots`."""
    stats = ScanStats()
    batch: list[FileRecord] = []

    for raw_root in roots:
        root = check_root(Path(raw_root), allow_unsafe)
        stats.roots.append(str(root))

        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=_count_error(stats)):
            here = Path(dirpath)

            keep_dirs = []
            for dirname in dirnames:
                child = here / dirname
                if child.is_symlink():
                    stats.skipped_symlinks += 1
                    continue
                if is_excluded(child, settings):
                    stats.skipped_excluded += 1
                    continue
                if is_bundle(child, settings):
                    # Record the bundle itself, do not walk inside it.
                    try:
                        st = child.lstat()
                    except OSError:
                        stats.errors += 1
                        continue
                    batch.append(_record(child, root, st, settings, bundle=True))
                    stats.bundles += 1
                    stats.bytes += batch[-1].size
                    continue
                keep_dirs.append(dirname)
            dirnames[:] = keep_dirs

            for name in filenames:
                full = here / name

                if icloud.is_placeholder_name(name):
                    stats.placeholders += 1
                    continue
                if full.is_symlink():
                    stats.skipped_symlinks += 1
                    continue
                if is_excluded(full, settings):
                    stats.skipped_excluded += 1
                    continue

                try:
                    st = full.lstat()
                except OSError:
                    stats.errors += 1
                    continue

                if st.st_size < settings.min_size_bytes:
                    stats.skipped_small += 1
                    continue

                record = _record(full, root, st, settings, bundle=False)
                if record.dataless:
                    stats.dataless += 1
                batch.append(record)
                stats.files += 1
                stats.bytes += record.size

            if len(batch) >= BATCH:
                upsert_many(conn, batch)
                batch.clear()
                if progress:
                    print(f"  scanned {stats.files + stats.bundles} items…", end="\r", flush=True)

    if batch:
        upsert_many(conn, batch)
    if progress:
        print(" " * 60, end="\r")
    return stats


def _count_error(stats: ScanStats):
    def handler(_exc: OSError) -> None:
        stats.errors += 1

    return handler
