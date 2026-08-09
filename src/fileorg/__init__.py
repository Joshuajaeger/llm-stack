"""fileorg — consolidate scattered macOS data into one searchable library.

Scan both Macs, find duplicates, classify with rules plus the local LLM in this
repo, then move everything into a single numbered folder tree with a SQLite
catalog on top for fast search.

Every destructive step is dry-run by default, journaled, and undoable.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
