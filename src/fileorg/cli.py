"""fileorg command line.

    python -m src.fileorg.cli <command> [options]

or, from the repo root, `bash scripts/fileorg.sh <command>`.

Run the commands in order: icloud-check → scan → dedupe → classify → plan →
apply → verify. Every step is safe to re-run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import (
    apply as apply_mod,
    catalog as catalog_mod,
    classify as classify_mod,
    dedupe as dedupe_mod,
    icloud,
    plan as plan_mod,
    scan as scan_mod,
    search as search_mod,
    settings as settings_mod,
    smartfolders,
    undo as undo_mod,
    verify as verify_mod,
)
from .scan import human


GLOBAL_OPTIONS = (
    ("--config", "path to fileorg.yaml"),
    ("--catalog", "catalog database (default: <workdir>/catalog.db)"),
    ("--library", "override library_root"),
    ("--archive", "override archive_root"),
    ("--workdir", "override where catalogs/plans/journals go"),
    ("--machine", "label for this Mac (default: hostname)"),
)


def _global_options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """Accept the global flags before *or* after the subcommand.

    On the subparser copies the default is SUPPRESS, so an unused flag does not
    clobber the value already parsed off the main parser.
    """
    default = argparse.SUPPRESS if suppress else None
    for flag, help_text in GLOBAL_OPTIONS:
        parser.add_argument(flag, help=help_text if not suppress else argparse.SUPPRESS,
                            default=default)
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=argparse.SUPPRESS if suppress else False,
        help=argparse.SUPPRESS if suppress else "suppress progress output",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileorg",
        description="Consolidate scattered macOS data into one searchable library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Typical run:\n"
            "  fileorg icloud-check --materialize\n"
            "  fileorg scan ~/Desktop ~/Documents ~/Downloads\n"
            "  fileorg dedupe --prefer $(hostname -s)\n"
            "  fileorg classify\n"
            "  fileorg plan\n"
            "  fileorg apply                 # dry run\n"
            "  fileorg apply --execute\n"
            "  fileorg verify --machine <old-mac>\n"
        ),
    )
    _global_options(parser)

    common = argparse.ArgumentParser(add_help=False)
    _global_options(common, suppress=True)

    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, parents=[common])

    p = add("icloud-check", "report evicted iCloud files before anything else")
    p.add_argument("--root", help="tree to inspect (default: iCloud Drive)")
    p.add_argument("--materialize", action="store_true", help="download evicted files now")

    p = add("scan", "catalog files under one or more roots")
    p.add_argument("roots", nargs="+")
    p.add_argument("--allow-unsafe", action="store_true", help="permit guarded system roots")

    p = add("merge", "merge another Mac's catalog into this one")
    p.add_argument("other", help="path to the other catalog.db")

    p = add("dedupe", "find duplicate content across everything catalogued")
    p.add_argument("--prefer", help="machine whose copy should be treated as the keeper")
    p.add_argument("--include-bundles", action="store_true")

    add("junk", "report reclaimable junk (never deletes)")

    p = add("classify", "assign every catalogued file a category")
    p.add_argument("--no-llm", action="store_true", help="rules only; unclear files go to review")
    p.add_argument("--reclassify", action="store_true", help="redo files already classified")

    p = add("plan", "write the move plan")
    p.add_argument("--out", help="plan file (default: <workdir>/plan.jsonl)")
    p.add_argument("--only-machine", help="plan moves for one machine only")

    p = add("apply", "execute a move plan (dry run unless --execute)")
    p.add_argument("--plan", help="plan file (default: <workdir>/plan.jsonl)")
    p.add_argument("--execute", action="store_true", help="actually move files")
    p.add_argument("--categories", help="comma-separated categories to move in this wave")
    p.add_argument("--only-machine", help="move files from one machine only")
    p.add_argument("--limit", type=int, help="stop after N moves")
    p.add_argument("--no-verify", action="store_true", help="skip post-copy hash check")

    p = add("undo", "reverse a journal (dry run unless --execute)")
    p.add_argument("--journal", help="journal file (default: most recent)")
    p.add_argument("--execute", action="store_true")

    p = add("verify", "prove a machine's files all landed in the library")
    p.add_argument("--only-machine", required=True, help="machine label to verify")
    p.add_argument("--journal", action="append", help="journal to check (repeatable)")
    p.add_argument("--fast", action="store_true", help="existence only, skip hashing")
    p.add_argument("--show", type=int, default=20, help="how many problems to list")

    p = add("search", "query the catalog")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--category")
    p.add_argument("--ext")
    p.add_argument("--only-machine")
    p.add_argument("--min-size", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)

    p = add("smartfolders", "write Finder Smart Folders into the library")
    p.add_argument("--overwrite", action="store_true")

    add("status", "summarize the catalog")

    return parser


def load_settings(args) -> settings_mod.Settings:
    overrides = {}
    if args.library:
        overrides["library_root"] = args.library
    if args.archive:
        overrides["archive_root"] = args.archive
    if args.workdir:
        overrides["workdir"] = args.workdir
    if args.machine:
        overrides["machine"] = args.machine
    return settings_mod.load(args.config, **overrides)


def catalog_path(args, settings: settings_mod.Settings) -> Path:
    return Path(args.catalog) if args.catalog else settings.workdir / "catalog.db"


def plan_path(args, settings: settings_mod.Settings) -> Path:
    chosen = getattr(args, "plan", None) or getattr(args, "out", None)
    return Path(chosen) if chosen else settings.workdir / "plan.jsonl"


# -- commands ------------------------------------------------------------


def cmd_icloud_check(args, settings) -> int:
    report = icloud.preflight(args.root)
    print(f"iCloud root: {report.root}")
    if not report.exists:
        print("  not found — is iCloud Drive enabled on this Mac?")
        return 1

    print(f"  files:            {report.file_count}")
    print(f"  total size:       {human(report.total_bytes)}")
    print(f"  local:            {human(report.local_bytes)}")
    print(f"  evicted (cloud):  {report.dataless_count}")
    print(f"  .icloud stubs:    {report.placeholder_count}")
    print(f"  Optimize Storage: {report.optimize_storage}")

    if report.ready:
        print("\nEverything is local. Safe to scan and hash.")
        return 0

    print(
        "\nSome files live only in the cloud. Hashing them would trigger a large,"
        "\nslow download mid-run. Turn off System Settings → Apple Account → iCloud →"
        "\niCloud Drive → 'Optimize Mac Storage', then re-run with --materialize."
    )
    if not args.materialize:
        return 1

    print("\nDownloading evicted files…")
    done = failed = 0
    for path in report.root.rglob("*"):
        try:
            if not path.is_file() or not icloud.is_dataless(path.lstat()):
                continue
        except OSError:
            continue
        if icloud.materialize(path):
            done += 1
        else:
            failed += 1
        print(f"  downloaded {done}, failed {failed}…", end="\r", flush=True)
    print(" " * 60, end="\r")
    print(f"Downloaded {done} files, {failed} failed.")
    return 0 if failed == 0 else 1


def cmd_scan(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    try:
        stats = scan_mod.scan(
            conn, args.roots, settings, allow_unsafe=args.allow_unsafe, progress=not args.quiet
        )
    except scan_mod.RootRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    catalog_mod.set_meta(conn, f"scanned:{settings.machine}", ",".join(stats.roots))
    conn.commit()
    print(f"Scanned as machine '{settings.machine}': {stats.summary()}")
    if stats.dataless:
        print(
            f"  note: {stats.dataless} files are evicted to iCloud. "
            f"Run `fileorg icloud-check --materialize` before dedupe."
        )
    return 0


def cmd_merge(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    other = Path(args.other)
    if not other.exists():
        print(f"error: no such catalog: {other}", file=sys.stderr)
        return 2
    rows = catalog_mod.merge(conn, other)
    print(f"Merged {rows} rows from {other}")
    print(f"Machines now in the catalog: {', '.join(catalog_mod.machines(conn))}")
    return 0


def cmd_dedupe(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    sets, stats = dedupe_mod.find_duplicates(
        conn,
        settings,
        prefer_machine=args.prefer,
        include_bundles=args.include_bundles,
        progress=not args.quiet,
    )
    manifest = dedupe_mod.write_manifest(sets, settings.workdir / "duplicates.jsonl")
    print(stats.summary())
    if stats.unreadable:
        print(f"  {stats.unreadable} files could not be read (skipped)")
    for dup in sets[:10]:
        print(f"\n  keep      {dup.keeper.path}  ({human(dup.keeper.size)})")
        for record in dup.redundant[:4]:
            print(f"  duplicate {record.path}")
        if len(dup.redundant) > 4:
            print(f"            … and {len(dup.redundant) - 4} more")
    if len(sets) > 10:
        print(f"\n  … and {len(sets) - 10} more sets")
    print(f"\nFull manifest: {manifest}")
    print("Nothing was deleted. Duplicates will be quarantined under 90-Duplicates/.")
    return 0


def cmd_junk(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    rows = classify_mod.junk_report(conn, settings)
    if not rows:
        print("No junk matched the rules in config/fileorg.yaml.")
        return 0
    print("Reclaimable by hand (nothing was touched):\n")
    total = 0
    for label, count, size in rows:
        print(f"  {human(size):>10}  {count:>6} files  {label}")
        total += size
    print(f"\n  {human(total):>10}  total")
    print("\nReview these in Finder before deleting. `fileorg` will not delete them for you.")
    return 0


def cmd_classify(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    stats = classify_mod.classify(
        conn,
        settings,
        use_llm=not args.no_llm,
        reclassify=args.reclassify,
        progress=not args.quiet,
    )
    if stats.total == 0:
        print("Nothing to classify. Run `fileorg scan` first, or pass --reclassify.")
        return 0

    if stats.llm_used:
        print("Local LLM: in use (nothing left this Mac).")
    else:
        print(f"Local LLM: not used — {stats.llm_reason}.")
        print("  Content-dependent documents were sent to the review queue instead.")

    print(stats.summary())
    print("\nBy category:")
    for category, count, size in classify_mod.summarize(conn):
        print(f"  {human(size):>10}  {count:>6}  {category}")
    return 0


def cmd_plan(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    ops, stats = plan_mod.build(conn, settings, machine=args.only_machine)
    target = plan_path(args, settings)
    plan_mod.write(ops, target)
    print(stats.summary())
    print(f"\nPlan written to {target}")
    print("Read it, delete any line you disagree with, then run `fileorg apply`.")
    return 0


def cmd_apply(args, settings) -> int:
    target = plan_path(args, settings)
    if not target.exists():
        print(f"error: no plan at {target} — run `fileorg plan` first", file=sys.stderr)
        return 2

    ops = plan_mod.read(target)
    categories = set(args.categories.split(",")) if args.categories else None
    if categories:
        ops = [op for op in ops if op.category in categories]
    if args.only_machine:
        ops = [op for op in ops if op.machine == args.only_machine]
    if args.limit:
        ops = ops[: args.limit]

    if not args.execute:
        total = sum(op.size for op in ops)
        print(f"DRY RUN — {len(ops)} moves ({human(total)}). Nothing has been touched.\n")
        print(apply_mod.preview(ops, settings))
        print("\nRe-run with --execute to carry this out.")
        return 0

    conn = catalog_mod.connect(catalog_path(args, settings))
    stats, journal = apply_mod.execute(
        ops,
        settings,
        conn=conn,
        verify=not args.no_verify,
        progress=not args.quiet,
    )
    print(stats.summary())
    for message in stats.errors[:10]:
        print(f"  error: {message}")
    if len(stats.errors) > 10:
        print(f"  … and {len(stats.errors) - 10} more errors")
    print(f"\nJournal: {journal}")
    print(f"Undo with: fileorg undo --journal {journal} --execute")
    return 0 if not (stats.failed_verify or stats.failed_other) else 1


def cmd_undo(args, settings) -> int:
    journal = Path(args.journal) if args.journal else undo_mod.latest_journal(settings)
    if not journal or not journal.exists():
        print("error: no journal to undo", file=sys.stderr)
        return 2

    moves = undo_mod.read_moves(journal)
    if not args.execute:
        print(f"DRY RUN — would restore {len(moves)} items from {journal}.")
        for entry in moves[:20]:
            print(f"  {entry['dst']}\n    → {entry['src']}")
        if len(moves) > 20:
            print(f"  … and {len(moves) - 20} more")
        print("\nRe-run with --execute to carry this out.")
        return 0

    conn = catalog_mod.connect(catalog_path(args, settings))
    stats, undo_journal = undo_mod.execute(
        journal, settings, conn=conn, progress=not args.quiet
    )
    print(stats.summary())
    for message in stats.errors[:10]:
        print(f"  error: {message}")
    print(f"\nUndo journal: {undo_journal}")
    return 0 if not stats.failed else 1


def cmd_verify(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    journals = [Path(p) for p in args.journal] if args.journal else None
    report = verify_mod.verify(
        conn,
        settings,
        machine=args.only_machine,
        journals=journals,
        deep=not args.fast,
        progress=not args.quiet,
    )
    print(report.summary())

    if report.problems:
        print("\nProblems:")
        for message in report.problems[: args.show]:
            print(f"  {message}")
        if len(report.problems) > args.show:
            print(f"  … and {len(report.problems) - args.show} more")

    if report.residual:
        print(
            f"\nStill on the source disk but never catalogued: {report.residual} files "
            f"({human(report.residual_bytes)}). These were filtered out by "
            f"scanning.exclude in config/fileorg.yaml — check none of them matter:"
        )
        for example in report.residual_examples[: args.show]:
            print(f"  {example}")
        if report.residual > len(report.residual_examples):
            print(f"  … and {report.residual - len(report.residual_examples)} more")

    print()
    if report.clean:
        print(
            f"VERIFIED — every file catalogued on '{report.machine}' is present in the "
            f"library and hashes correctly."
        )
        print(
            "Wait for iCloud to finish syncing (Finder sidebar shows no progress ring), "
            "confirm from the other Mac or iCloud.com, and only then erase."
        )
        return 0

    print(
        f"NOT VERIFIED — {report.unaccounted + report.hash_mismatch + report.destination_missing} "
        f"problem(s). Do not erase '{report.machine}' yet."
    )
    return 1


def cmd_search(args, settings) -> int:
    conn = catalog_mod.connect(catalog_path(args, settings))
    results = search_mod.query(
        conn,
        text=args.text,
        category=args.category,
        ext=args.ext,
        machine=args.only_machine,
        min_size=args.min_size,
        limit=args.limit,
    )
    if not results:
        print("No matches.")
        return 1
    for record in results:
        label = record.category or "unclassified"
        print(f"{human(record.size):>10}  {label:<28}  {record.machine}  {record.path}")
    print(f"\n{len(results)} result(s).")
    return 0


def cmd_smartfolders(args, settings) -> int:
    written = smartfolders.generate(settings, overwrite=args.overwrite)
    if not written:
        print("Nothing written (they already exist — pass --overwrite to replace).")
        return 0
    for path in written:
        print(f"  {path}")
    print(
        f"\n{len(written)} Smart Folders in {settings.library_root / smartfolders.FOLDER_NAME}."
        f"\nDrag them into the Finder sidebar once and they stay there."
    )
    return 0


def cmd_status(args, settings) -> int:
    path = catalog_path(args, settings)
    if not path.exists():
        print(f"No catalog yet at {path}. Start with `fileorg scan`.")
        return 1

    conn = catalog_mod.connect(path)
    print(f"Catalog:      {path}")
    print(f"Library root: {settings.library_root}")
    print(f"Archive root: {settings.archive_root}")
    print(f"Machines:     {', '.join(catalog_mod.machines(conn)) or '(none)'}")
    print(f"Files:        {catalog_mod.count(conn)} ({human(catalog_mod.total_size(conn))})")
    print(f"Classified:   {catalog_mod.count(conn, 'category IS NOT NULL')}")
    print(f"Duplicates:   {catalog_mod.count(conn, 'dup_of IS NOT NULL')}")

    rows = classify_mod.summarize(conn)
    if rows:
        print("\nBy category:")
        for category, count, size in rows:
            print(f"  {human(size):>10}  {count:>6}  {category}")
    return 0


COMMANDS = {
    "icloud-check": cmd_icloud_check,
    "scan": cmd_scan,
    "merge": cmd_merge,
    "dedupe": cmd_dedupe,
    "junk": cmd_junk,
    "classify": cmd_classify,
    "plan": cmd_plan,
    "apply": cmd_apply,
    "undo": cmd_undo,
    "verify": cmd_verify,
    "search": cmd_search,
    "smartfolders": cmd_smartfolders,
    "status": cmd_status,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    settings.workdir.mkdir(parents=True, exist_ok=True)
    return COMMANDS[args.command](args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
