"""Query the catalog.

Spotlight searches content; this searches the ledger — including files that
have been moved, and files that live on the *other* Mac and were never
transferred. That is the part Finder cannot tell you.
"""

from __future__ import annotations

from .catalog import FileRecord, iter_files


def query(
    conn,
    text: str = "",
    category: str | None = None,
    ext: str | None = None,
    machine: str | None = None,
    min_size: int = 0,
    limit: int = 50,
) -> list[FileRecord]:
    clauses: list[str] = []
    params: list = []

    if text:
        clauses.append("(name LIKE ? OR path LIKE ?)")
        params += [f"%{text}%", f"%{text}%"]
    if category:
        clauses.append("category LIKE ?")
        params.append(f"{category}%")
    if ext:
        clauses.append("ext = ?")
        params.append(ext.lower().lstrip("."))
    if machine:
        clauses.append("machine = ?")
        params.append(machine)
    if min_size:
        clauses.append("size >= ?")
        params.append(min_size)

    where = " AND ".join(clauses)
    results = iter_files(conn, where, tuple(params), order="size DESC")

    out = []
    for record in results:
        out.append(record)
        if len(out) >= limit:
            break
    return out
