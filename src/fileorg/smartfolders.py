"""Generate Finder Smart Folders for the library.

Spotlight already indexes iCloud Drive, so the fast-search layer costs nothing
to build: a handful of saved searches scoped to the library turn "where did I
put that" into a sidebar click.

Drag the generated .savedSearch files into the Finder sidebar once and they
stay there.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

from .settings import Settings

FOLDER_NAME = "_Smart Folders"

# (filename, raw Spotlight query, scope — None means the whole library)
EXTRA_SEARCHES: list[tuple[str, str, str | None]] = [
    ("Recent — last 30 days", 'kMDItemFSContentChangeDate >= $time.today(-30)', None),
    ("Large — over 100 MB", "kMDItemFSSize > 104857600", None),
    ("PDFs", 'kMDItemContentTypeTree == "com.adobe.pdf"', None),
    ("Images", 'kMDItemContentTypeTree == "public.image"', None),
    ("Spreadsheets", 'kMDItemContentTypeTree == "public.spreadsheet"', None),
]

ALL_FILES = 'kMDItemFSName == "*"cd'


def _saved_search(raw_query: str, scopes: list[str]) -> dict:
    return {
        "CompatibleVersion": 1,
        "RawQuery": raw_query,
        "RawQueryDict": {
            "FinderFilesOnly": True,
            "RawQuery": raw_query,
            "SearchScopes": scopes,
            "UserFilesOnly": False,
        },
        "SearchCriteria": {
            "FXScopeArrayOfPaths": scopes,
        },
    }


def top_level_categories(settings: Settings) -> list[str]:
    """The numbered top-level folders, deduplicated and in order."""
    seen: list[str] = []
    for category in settings.categories:
        top = category.split("/")[0]
        if top not in seen:
            seen.append(top)
    return seen


def generate(settings: Settings, overwrite: bool = False) -> list[Path]:
    """Write the saved searches. Returns the paths created."""
    target = settings.library_root / FOLDER_NAME
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    library = str(settings.library_root)

    for top in top_level_categories(settings):
        # category_dir, not library_root — 60-Archive may sit on another disk.
        scope = settings.category_dir(top)
        if not scope.exists():
            continue
        written.append(
            _write(target / f"{top}.savedSearch", ALL_FILES, [str(scope)], overwrite)
        )

    for name, query, scope in EXTRA_SEARCHES:
        scopes = [scope] if scope else [library]
        written.append(_write(target / f"{name}.savedSearch", query, scopes, overwrite))

    return [path for path in written if path is not None]


def _write(path: Path, query: str, scopes: list[str], overwrite: bool) -> Path | None:
    if path.exists() and not overwrite:
        return None
    with open(path, "wb") as handle:
        plistlib.dump(_saved_search(query, scopes), handle)
    return path
