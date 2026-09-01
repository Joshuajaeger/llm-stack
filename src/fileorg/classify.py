"""Decide which category each catalogued file belongs to.

Cheapest, most certain signal first:

    duplicate  →  path rule  →  file extension  →  local LLM  →  review queue

The model is only consulted for document types whose category genuinely depends
on their contents, and only when the stack is running. Offline, everything it
would have handled goes to the review queue instead — never a guess.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from fnmatch import fnmatch

from . import extract
from .catalog import FileRecord, iter_files, update_fields
from .llm import LocalLLM
from .settings import Settings

SECONDS_PER_YEAR = 365.25 * 24 * 3600


@dataclass
class ClassifyStats:
    total: int = 0
    by_duplicate: int = 0
    by_path_rule: int = 0
    by_extension: int = 0
    by_llm: int = 0
    to_review: int = 0
    archived: int = 0
    llm_used: bool = False
    llm_reason: str = ""
    by_category: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.total} classified — {self.by_path_rule} by path rule, "
            f"{self.by_extension} by extension, {self.by_llm} by local LLM, "
            f"{self.by_duplicate} duplicates, {self.to_review} to review, "
            f"{self.archived} archived"
        )


def match_path_rule(record: FileRecord, settings: Settings) -> str | None:
    """First matching rule wins. Patterns are matched case-insensitively."""
    lowered = record.path.lower()
    for rule in settings.path_rules:
        pattern = str(rule.get("match", "")).lower()
        if pattern and fnmatch(lowered, pattern):
            return rule.get("category")
    return None


def archive_label(record: FileRecord, category: str, settings: Settings) -> str | None:
    """Route long-untouched files to 60-Archive/<year>/<original category>."""
    years = settings.archive_after_years
    if not years or category in (settings.duplicates_category, settings.review_category):
        return None
    if (time.time() - record.mtime) < years * SECONDS_PER_YEAR:
        return None
    year = time.localtime(record.mtime).tm_year
    return f"60-Archive/{year}/{category}"


def classify(
    conn,
    settings: Settings,
    use_llm: bool = True,
    reclassify: bool = False,
    progress: bool = True,
) -> ClassifyStats:
    stats = ClassifyStats()

    where = "" if reclassify else "category IS NULL"
    records = list(iter_files(conn, where))
    if not records:
        return stats

    ambiguous: list[FileRecord] = []

    for record in records:
        if record.dup_of is not None:
            _assign(conn, record, settings.duplicates_category, "dedupe", 1.0, stats, settings)
            stats.by_duplicate += 1
            continue

        category = match_path_rule(record, settings)
        if category:
            _assign(conn, record, category, "path-rule", 1.0, stats, settings)
            stats.by_path_rule += 1
            continue

        category = settings.extensions.get(record.ext)
        if category:
            _assign(conn, record, category, "extension", 1.0, stats, settings)
            stats.by_extension += 1
            continue

        if record.ext in settings.ambiguous_extensions:
            ambiguous.append(record)
            continue

        _assign(conn, record, settings.review_category, "fallback", 0.0, stats, settings)
        stats.to_review += 1

    conn.commit()

    if ambiguous:
        _classify_ambiguous(conn, ambiguous, settings, use_llm, stats, progress)

    conn.commit()
    return stats


def _classify_ambiguous(
    conn,
    records: list[FileRecord],
    settings: Settings,
    use_llm: bool,
    stats: ClassifyStats,
    progress: bool,
) -> None:
    client = LocalLLM(settings.llm)

    if use_llm:
        stats.llm_used, stats.llm_reason = client.available()
    else:
        stats.llm_used, stats.llm_reason = False, "disabled with --no-llm"

    if not stats.llm_used:
        # No model, no guessing. Everything content-dependent goes to review.
        for record in records:
            _assign(conn, record, settings.review_category, "no-llm", 0.0, stats, settings)
            stats.to_review += 1
        return

    categories = [c for c in settings.categories if c != settings.duplicates_category]
    threshold = settings.llm.confidence_threshold
    size = max(settings.llm.batch_size, 1)

    for start in range(0, len(records), size):
        batch = records[start : start + size]
        items = [extract.describe(r.path, settings.llm.snippet_chars) for r in batch]
        verdicts = client.classify(items, categories, settings.review_category)

        for index, record in enumerate(batch):
            verdict = verdicts.get(index)
            if verdict is None or verdict.confidence < threshold:
                reason = "llm-unsure" if verdict else "llm-no-answer"
                confidence = verdict.confidence if verdict else 0.0
                _assign(conn, record, settings.review_category, reason, confidence, stats, settings)
                stats.to_review += 1
                continue
            _assign(conn, record, verdict.category, "llm", verdict.confidence, stats, settings)
            stats.by_llm += 1

        conn.commit()
        if progress:
            done = min(start + size, len(records))
            print(f"  classified {done}/{len(records)} documents…", end="\r", flush=True)

    if progress:
        print(" " * 60, end="\r")


def _assign(
    conn,
    record: FileRecord,
    category: str,
    decided_by: str,
    confidence: float,
    stats: ClassifyStats,
    settings: Settings,
) -> None:
    final = category
    archived = archive_label(record, category, settings)
    if archived:
        final = archived
        stats.archived += 1

    record.category = final
    record.decided_by = decided_by
    record.confidence = confidence
    update_fields(
        conn, record.id, category=final, decided_by=decided_by, confidence=confidence
    )
    stats.total += 1
    stats.by_category[final] = stats.by_category.get(final, 0) + 1


def summarize(conn) -> list[tuple[str, int, int]]:
    """(category, file count, total bytes), largest first."""
    rows = conn.execute(
        "SELECT category, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b "
        "FROM files WHERE category IS NOT NULL GROUP BY category ORDER BY b DESC"
    )
    return [(r["category"], r["n"], r["b"]) for r in rows]


def junk_report(conn, settings: Settings) -> list[tuple[str, int, int]]:
    """Space hogs worth deleting by hand. Reported only, never touched."""
    buckets: dict[str, list[int]] = {}
    for record in iter_files(conn):
        lowered = record.path.lower()
        for rule in settings.junk_rules:
            pattern = str(rule.get("match", "")).lower()
            if pattern and fnmatch(lowered, pattern):
                label = str(rule.get("label", pattern))
                bucket = buckets.setdefault(label, [0, 0])
                bucket[0] += 1
                bucket[1] += record.size
                break
    return sorted(
        ((label, n, b) for label, (n, b) in buckets.items()),
        key=lambda item: item[2],
        reverse=True,
    )
