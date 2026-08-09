"""iCloud Drive helpers.

Files in iCloud Drive can be *dataless*: the name and size are on disk but the
contents live only in the cloud. Reading one silently blocks while macOS
downloads it, which turns a dedupe pass into an unbounded download. So we
detect those up front, materialize deliberately, and never let hashing be the
thing that triggers a 200 GB restore.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# sys/stat.h: SF_DATALESS — "file is a dataless placeholder".
SF_DATALESS = 0x40000000
UF_COMPRESSED = 0x00000020

CLOUDDOCS = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def clouddocs_root() -> Path:
    """Path to iCloud Drive on this Mac (whether or not it exists yet)."""
    return CLOUDDOCS


def in_icloud(path: Path | str) -> bool:
    try:
        Path(path).resolve().relative_to(CLOUDDOCS.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_placeholder_name(name: str) -> bool:
    """Legacy eviction style: `.Report.pdf.icloud` next to a missing file."""
    return name.startswith(".") and name.endswith(".icloud")


def placeholder_real_name(name: str) -> str:
    return name[1:-len(".icloud")] if is_placeholder_name(name) else name


def is_dataless(st: os.stat_result) -> bool:
    flags = getattr(st, "st_flags", 0)
    return bool(flags & SF_DATALESS)


def materialize(path: Path | str, timeout: float = 300.0) -> bool:
    """Pull a dataless file down from iCloud and wait for it to land.

    Returns True once the file has contents locally, False on timeout or if
    brctl is unavailable.
    """
    path = Path(path)
    if not shutil.which("brctl"):
        return not _still_dataless(path)

    try:
        subprocess.run(
            ["brctl", "download", str(path)],
            check=False,
            capture_output=True,
            timeout=min(timeout, 120),
        )
    except (subprocess.SubprocessError, OSError):
        return False

    deadline = time.time() + timeout
    delay = 0.2
    while time.time() < deadline:
        if not _still_dataless(path):
            return True
        time.sleep(delay)
        delay = min(delay * 1.5, 3.0)
    return False


def _still_dataless(path: Path) -> bool:
    try:
        return is_dataless(path.lstat())
    except OSError:
        return False


def ensure_local(path: Path | str, timeout: float = 300.0) -> bool:
    """Make sure a path is readable locally before we hash or copy it."""
    path = Path(path)
    try:
        if not is_dataless(path.lstat()):
            return True
    except OSError:
        return False
    return materialize(path, timeout=timeout)


@dataclass
class PreflightReport:
    root: Path
    exists: bool
    file_count: int = 0
    dataless_count: int = 0
    placeholder_count: int = 0
    local_bytes: int = 0
    total_bytes: int = 0
    optimize_storage: str = "unknown"

    @property
    def ready(self) -> bool:
        return self.exists and self.dataless_count == 0 and self.placeholder_count == 0


def optimize_storage_state() -> str:
    """Best-effort read of the "Optimize Mac Storage" setting.

    Apple does not expose this reliably, so treat the answer as a hint and
    trust the placeholder count as the real signal.
    """
    try:
        out = subprocess.run(
            ["defaults", "read", "com.apple.bird", "optimize-storage"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    value = out.stdout.strip()
    if out.returncode != 0 or not value:
        return "unknown"
    return "on" if value in ("1", "true", "YES") else "off"


def preflight(root: Path | str | None = None) -> PreflightReport:
    """Count how much of a tree is still stranded in the cloud."""
    root = Path(root) if root else clouddocs_root()
    report = PreflightReport(root=root, exists=root.exists())
    report.optimize_storage = optimize_storage_state()
    if not report.exists:
        return report

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if d != ".Trash"]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                st = full.lstat()
            except OSError:
                continue
            if is_placeholder_name(name):
                report.placeholder_count += 1
                continue
            report.file_count += 1
            report.total_bytes += st.st_size
            if is_dataless(st):
                report.dataless_count += 1
            else:
                report.local_bytes += st.st_size
    return report
