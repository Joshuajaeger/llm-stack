"""Content hashing.

Hashing every byte of a few hundred GB is slow and, on iCloud Drive, expensive
(it forces evicted files back down). So dedupe walks a ladder: group by size,
then a cheap head+tail sample, and only fall through to a full hash when the
cheaper tiers actually collide.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SAMPLE_BYTES = 4096
CHUNK = 1024 * 1024


def _digest():
    # BLAKE2b is faster than SHA-256 on Apple Silicon and just as collision
    # resistant for this purpose. 16 bytes keeps the catalog small.
    return hashlib.blake2b(digest_size=16)


def quick_hash(path: Path | str, size: int | None = None) -> str:
    """Cheap fingerprint: size + first and last 4 KiB.

    Two files with different quick hashes are definitely different. Matching
    quick hashes mean "maybe" and get escalated to a full hash.
    """
    path = Path(path)
    if size is None:
        size = path.stat().st_size

    h = _digest()
    h.update(str(size).encode())
    with open(path, "rb") as fh:
        h.update(fh.read(SAMPLE_BYTES))
        if size > SAMPLE_BYTES * 2:
            fh.seek(-SAMPLE_BYTES, 2)
            h.update(fh.read(SAMPLE_BYTES))
    return h.hexdigest()


def full_hash(path: Path | str) -> str:
    """Streamed hash of an entire file."""
    h = _digest()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root: Path | str) -> str:
    """Hash a directory (or macOS bundle) as a single unit.

    Covers relative paths as well as contents, so a renamed file inside a
    bundle changes the result.
    """
    root = Path(root)
    h = _digest()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        h.update(str(path.relative_to(root)).encode("utf-8", "surrogateescape"))
        h.update(full_hash(path).encode())
    return h.hexdigest()


def hash_any(path: Path | str) -> str:
    """Full hash of a file, or a tree hash if the path is a directory."""
    path = Path(path)
    return tree_hash(path) if path.is_dir() else full_hash(path)
