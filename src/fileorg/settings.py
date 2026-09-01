"""Configuration loading for fileorg.

Everything tunable lives in config/fileorg.yaml. This module reads it, expands
paths, and hands back a Settings object the rest of the package uses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "fileorg.yaml"

# Working files (catalogs, plans, journals) never belong in the library itself.
DEFAULT_WORKDIR = REPO_ROOT / ".fileorg"


def expand(value: str) -> Path:
    """Expand ~ and $VARS in a configured path."""
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


@dataclass
class LLMSettings:
    enabled: bool = True
    url: str = "http://127.0.0.1:8000/chat"
    health_url: str = "http://127.0.0.1:8000/"
    api_key: str = ""
    batch_size: int = 8
    max_prompt_chars: int = 16000
    snippet_chars: int = 900
    max_tokens: int = 512
    timeout: float = 120.0
    confidence_threshold: float = 0.55

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMSettings":
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        obj = cls(**kwargs)
        # The router key is a secret: it comes from the environment, never the
        # YAML file (config/ is committed, .env is not).
        obj.api_key = os.environ.get("API_KEY", "")
        # Stay inside whatever ceiling the router enforces.
        router_cap = int(os.environ.get("MAX_PROMPT_CHARS", "20000"))
        obj.max_prompt_chars = min(obj.max_prompt_chars, router_cap - 1000)
        return obj


@dataclass
class Settings:
    library_root: Path
    archive_root: Path
    workdir: Path
    machine: str
    categories: list[str] = field(default_factory=list)
    review_category: str = "00-Inbox/_needs-review"
    duplicates_category: str = "90-Duplicates"
    extensions: dict[str, str] = field(default_factory=dict)
    path_rules: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_extensions: set[str] = field(default_factory=set)
    exclude: list[str] = field(default_factory=list)
    exclude_names: set[str] = field(default_factory=set)
    bundle_extensions: set[str] = field(default_factory=set)
    date_partitioned: set[str] = field(default_factory=set)
    preserve_structure: set[str] = field(default_factory=set)
    archive_after_years: int = 0
    min_size_bytes: int = 0
    junk_rules: list[dict[str, Any]] = field(default_factory=list)
    llm: LLMSettings = field(default_factory=LLMSettings)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def default_category(self) -> str:
        return self.review_category

    def category_dir(self, category: str) -> Path:
        """Absolute directory for a category label.

        Archive lives under its own root so cold data can be pointed at an
        external drive without touching the rest of the layout.
        """
        root = self.archive_root if category.startswith("60-Archive") else self.library_root
        return root / category


def default_machine_name() -> str:
    name = os.environ.get("FILEORG_MACHINE")
    if name:
        return name
    try:
        return os.uname().nodename.split(".")[0]
    except AttributeError:  # pragma: no cover - non-POSIX
        return "unknown"


def load(config_path: Path | str | None = None, **overrides: Any) -> Settings:
    """Load settings from YAML, applying CLI overrides on top."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"fileorg config not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    library = overrides.get("library_root") or data.get("library_root")
    if not library:
        raise ValueError("library_root must be set in config or passed with --library")
    library_root = expand(library)

    archive = overrides.get("archive_root") or data.get("archive_root") or library
    archive_root = expand(archive)

    workdir = expand(overrides.get("workdir") or data.get("workdir") or DEFAULT_WORKDIR)

    taxonomy = data.get("taxonomy") or {}
    rules = data.get("rules") or {}
    scanning = data.get("scanning") or {}

    extensions: dict[str, str] = {}
    for category, exts in (rules.get("extensions") or {}).items():
        for ext in exts or []:
            extensions[str(ext).lower().lstrip(".")] = category

    return Settings(
        library_root=library_root,
        archive_root=archive_root,
        workdir=workdir,
        machine=overrides.get("machine") or default_machine_name(),
        categories=list(taxonomy.get("categories") or []),
        review_category=taxonomy.get("review_category", "00-Inbox/_needs-review"),
        duplicates_category=taxonomy.get("duplicates_category", "90-Duplicates"),
        extensions=extensions,
        path_rules=list(rules.get("path_rules") or []),
        ambiguous_extensions={
            str(e).lower().lstrip(".") for e in (rules.get("ambiguous_extensions") or [])
        },
        exclude=list(scanning.get("exclude") or []),
        exclude_names={str(n) for n in (scanning.get("exclude_names") or [])},
        bundle_extensions={
            str(e).lower().lstrip(".") for e in (scanning.get("bundle_extensions") or [])
        },
        date_partitioned=set(taxonomy.get("date_partitioned") or []),
        preserve_structure=set(taxonomy.get("preserve_structure") or []),
        archive_after_years=int(rules.get("archive_after_years") or 0),
        min_size_bytes=int(scanning.get("min_size_bytes") or 0),
        junk_rules=list(rules.get("junk") or []),
        llm=LLMSettings.from_dict(data.get("llm") or {}),
        raw=data,
    )
