"""Pull a short text snippet out of a file, for classification only.

Deliberately best-effort and dependency-free. Anything we can't read cheaply
degrades to filename-and-path, which is often enough — `Rechnung_2019_03.pdf`
in `~/Downloads/Steuer` needs no text extraction at all.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "rtf", "csv", "tsv", "json", "jsonl", "yaml", "yml",
    "xml", "html", "htm", "log", "tex", "org", "rst", "ini", "cfg", "conf",
}

_TIMEOUT = 20


def snippet(path: Path | str, limit: int = 900) -> str:
    """Return up to `limit` characters of readable text, or an empty string."""
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")

    try:
        if ext in TEXT_EXTENSIONS:
            text = _read_text(path, limit)
        elif ext == "pdf":
            text = _pdf_text(path, limit) or _spotlight_text(path, limit)
        else:
            text = _spotlight_text(path, limit)
    except (OSError, subprocess.SubprocessError):
        return ""

    return _tidy(text, limit)


def _read_text(path: Path, limit: int) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit * 4)


def _pdf_text(path: Path, limit: int) -> str:
    """First two pages via pdftotext, if poppler is installed."""
    if not shutil.which("pdftotext"):
        return ""
    result = subprocess.run(
        ["pdftotext", "-l", "2", "-nopgbrk", "-q", str(path), "-"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        errors="replace",
    )
    return result.stdout[: limit * 4] if result.returncode == 0 else ""


def _spotlight_text(path: Path, limit: int) -> str:
    """Reuse the text Spotlight already indexed — free, and covers Office docs."""
    result = subprocess.run(
        ["mdls", "-raw", "-name", "kMDItemTextContent", str(path)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        errors="replace",
    )
    text = result.stdout
    if result.returncode != 0 or text.strip() in ("", "(null)"):
        return ""
    return text[: limit * 4]


def _tidy(text: str, limit: int) -> str:
    """Collapse whitespace so the snippet spends its budget on words."""
    if not text:
        return ""
    return " ".join(text.split())[:limit]


def describe(path: Path | str, snippet_chars: int = 900) -> dict:
    """Everything the classifier gets to see about one file."""
    path = Path(path)
    parent = path.parent
    return {
        "name": path.name,
        # Two levels of parent directory carry most of the human intent.
        "folder": "/".join(parent.parts[-2:]) if len(parent.parts) > 1 else str(parent),
        "text": snippet(path, snippet_chars),
    }
