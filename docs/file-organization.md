# Consolidating Two Macs Into One Library

You have two MacBook Pros and you want to sell one. Your data is spread across
iCloud, Desktop, Documents, Downloads, your home folder and the disk root, with
no structure and unknown overlap between the machines.

This guide takes you from that to a single library in iCloud Drive that you can
search instantly — and, critically, to a **proof** that nothing was left behind
before you erase the second Mac.

The toolkit lives in this repo (`src/fileorg/`, config in
`config/fileorg.yaml`). It uses the local LLM you already run here to sort
documents, so nothing about your files ever leaves your machine.

---

## The short version

```bash
cd ~/llm-stack
source .venv/bin/activate && source .env

make org-check                       # 1. is anything still stranded in iCloud?
make org-scan                        # 2. catalog this Mac
make org-dedupe                      # 3. find duplicate content
make org-junk                        # 4. see what's just wasting space
make up                              # 5. start the local model
make org-classify                    #    sort into categories
make org-plan                        # 6. write the move plan — read it
make org-apply                       # 7. dry run
bash scripts/fileorg.sh apply --execute
make org-verify OLD_MAC=<label>      # 8. the gate before erasing
```

Nothing moves until step 7, and even then only what the plan file says.

---

## Before anything else: back up

Non-negotiable, and it comes before every other step on this page.

- **Time Machine** to an external drive — built in, free, gives you file-level
  rollback.
- **A second, independent copy.** Time Machine failing silently is a real
  thing. Either a bootable clone ([Carbon Copy Cloner][ccc] or
  [SuperDuper!][sd], both paid with working trials) or a plain
  `rsync -aH --delete ~ /Volumes/Backup/home/`.

If you only do one thing from this guide, do this one. Everything below is
reversible; a failed disk is not.

---

## The structure you're aiming for

```text
00-Inbox/          landing zone; nothing stays here
10-Documents/      finance · legal · health · education · work · personal
20-Media/          photos · video · audio · design
30-Projects/       one folder per active project
40-Code/           repos and notebooks, directory layout preserved
50-Reference/      books · papers · manuals · datasets
60-Archive/        YYYY/ — untouched for 5+ years
90-Duplicates/     quarantine; nothing is ever auto-deleted
```

Numbered prefixes keep Finder's sort order stable and make paths fast to type.
Two levels deep, maximum — deeper hierarchies are where filing systems go to
die, because you stop being sure which branch a thing belongs in.

**The folders are not the search layer.** Three things make this a place you
can actually find things in:

1. **Spotlight**, which already full-text indexes iCloud Drive for free.
2. **Smart Folders** — `make org-folders` writes saved searches into
   `_Smart Folders/` in the library. Drag them into the Finder sidebar once.
3. **The catalog** — a SQLite index of every file from *both* Macs.
   `bash scripts/fileorg.sh search rechnung` finds things Finder can't, because
   it also knows about files that only ever existed on the other machine.

Edit `config/fileorg.yaml` if this taxonomy doesn't fit how you think. That
file is the whole design — the code just executes it.

---

## Step by step

### 1. iCloud pre-flight

```bash
make org-check
```

iCloud Drive files can be *dataless*: the name is on disk, the contents are
not. Reading one silently blocks while macOS downloads it — which would turn a
dedupe pass into an unplanned 200 GB restore in the middle of your evening.

If the check reports evicted files:

1. **System Settings → Apple Account → iCloud → iCloud Drive → turn off
   "Optimize Mac Storage".**
2. `bash scripts/fileorg.sh icloud-check --materialize` and let it finish.

Also check your storage tier now. The whole library has to fit, and iCloud will
not warn you gracefully mid-sync. If it won't fit, point cold storage at an
external drive instead — set `archive_root` in `config/fileorg.yaml` to
something like `/Volumes/Archive`. Everything else stays in iCloud.

### 2. Catalog both Macs

```bash
make org-scan                                    # the default roots
make org-scan ROOTS='~/Desktop ~/Documents ~/Downloads ~/Pictures'
```

Scanning is strictly read-only. It skips `~/Library`, caches, `node_modules`,
`.git` and the rest of the exclusion list, and treats app bundles and
`.photoslibrary` as single objects rather than descending into them.

For the second Mac, either connect it and scan its disk directly, or run the
same scan over there and bring the catalog across:

```bash
# on the old Mac
bash scripts/fileorg.sh scan --machine old-mbp ~/Desktop ~/Documents ~/Downloads
# copy .fileorg/catalog.db to the keeper, then:
bash scripts/fileorg.sh merge /path/to/old-catalog.db
```

Machine labels matter — that's how verification knows whose files it's
checking. Set them explicitly with `--machine`.

### 3. Duplicates

```bash
make org-dedupe
```

Groups by size, then a head+tail sample, then a full hash — so files that are
obviously different are never fully read. Works across both Macs at once.

Nothing is deleted. The redundant copies get routed to `90-Duplicates/`, which
keeps their original folder shape so you can see what came from where. Delete
that folder yourself once you've looked.

### 4. Junk

```bash
make org-junk
```

Reports installers, `.dmg`s, incomplete downloads, VM disks, Xcode build
caches. Reported only — you delete them in Finder. This is usually where the
first several gigabytes come from.

For a visual pass over what's eating the disk, use [GrandPerspective][gp] (free)
or [OmniDiskSweeper][ods] (free); `ncdu` if you'd rather stay in the terminal.

### 5. Classify

```bash
make up          # start MLX + router, if not already running
make org-classify
```

Four tiers, cheapest and most certain first:

| Tier | Handles |
|---|---|
| Path rules | Filename and folder keywords — `*rechnung*`, `*/Movies/*`, `*Screenshot*` |
| Extension | Anything unambiguous by type — `.jpg`, `.mov`, `.py`, `.epub` |
| Local LLM | Documents whose category depends on their contents — PDFs, Word, Pages |
| Review queue | Everything else |

Only the third tier touches the model, and it goes to the router on
`127.0.0.1:8000` using the `API_KEY` from your `.env` — the same private path
Open WebUI uses. The model gets the filename, the folder, and a short text
excerpt.

The model is never allowed to invent a folder. Replies are parsed strictly and
every label is checked against the taxonomy; anything unparseable, unknown, or
below the confidence threshold goes to `00-Inbox/_needs-review` instead of
being guessed at. Run `make org-classify` with the stack down and it simply
tells you the model isn't available and routes those files to review.

Tune `llm.confidence_threshold` in the config if too much or too little is
landing in review.

### 6. Read the plan

```bash
make org-plan
less .fileorg/plan.jsonl
```

One JSON object per line: source, destination, category, and which tier
decided. **Delete any line you disagree with** — `apply` does exactly what the
plan says and nothing else.

### 7. Move, in waves

```bash
make org-apply                                          # dry run, always
bash scripts/fileorg.sh apply --execute --categories 10-Documents/finance
bash scripts/fileorg.sh apply --execute                 # the rest
```

Documents first, media last: documents are small and let you sanity-check the
result before committing a photo library's worth of I/O to iCloud.

Every move is **copy → verify hash → remove source**, so an interruption never
loses data; the worst case is a partial copy that the next run replaces. Every
action is appended to a journal in `.fileorg/`.

Changed your mind:

```bash
bash scripts/fileorg.sh undo --journal .fileorg/journal-<timestamp>.jsonl --execute
```

That restores the original paths and rewinds the catalog with them.

### 8. Verify — the gate

```bash
make org-verify OLD_MAC=old-mbp
```

For every file catalogued on that machine, this confirms it now exists in the
library and still hashes to what was recorded at move time. It also lists files
still sitting on the source disk that were never catalogued, so you can check
no exclusion was too broad.

**Exit code 0 is the only thing that means "safe to erase".** Anything else
prints what's wrong and refuses.

Then, before you wipe:

- Let iCloud finish syncing. The Finder sidebar shows a progress ring next to
  iCloud Drive while it's working — wait for it to disappear entirely. On a
  large library this takes days, not hours.
- Confirm from the *other* Mac, or from iCloud.com, that the files are really
  there. A file that exists only on the machine you're about to erase has not
  been backed up, whatever the local folder says.
- Keep your Time Machine backup until the buyer has had the machine for a
  couple of weeks.

The Apple-side handover steps — signing out of iCloud and iMessage, unpairing
your Watch, removing the Mac from Find My and your Apple Account, then Erase
All Content and Settings — are yours to run; Apple documents the current
sequence at [support.apple.com/HT201065][apple].

---

## Keeping it tidy afterwards

The consolidation is one-time. Staying organized is a habit plus one rule
engine:

| Need | Tool |
|---|---|
| Auto-file new downloads | [`organize`][organize] (Python, open source) — the free Hazel alternative. [Hazel][hazel] is paid and better, if you'd rather buy the polish. |
| Simple rules, no install | Finder → Folder Actions, or Shortcuts |
| Launch and find | [Raycast][raycast] or [Alfred][alfred] (both free tiers) |
| Duplicate sweeps later | [Czkawka][czkawka] or [dupeGuru][dupeguru] (GUI), `rmlint` (CLI) |
| Photos library, exported with metadata | [`osxphotos`][osxphotos] |
| Media date/EXIF fixes | `exiftool` |
| Full-text over the archive | Spotlight / `mdfind`, or [Recoll][recoll] |

The single highest-value habit: **`00-Inbox/` gets emptied weekly.** A landing
zone that never empties is just a second Desktop.

---

## Reference

Run `bash scripts/fileorg.sh --help`, or any subcommand with `--help`.

| Command | What it does |
|---|---|
| `icloud-check [--materialize]` | Report and optionally download evicted iCloud files |
| `scan ROOTS…` | Catalog files (read-only) |
| `merge OTHER.db` | Pull in another Mac's catalog |
| `dedupe [--prefer MACHINE]` | Find duplicate content |
| `junk` | Report reclaimable junk |
| `classify [--no-llm]` | Assign categories |
| `plan` | Write the move plan |
| `apply [--execute]` | Execute it; dry run by default |
| `undo [--execute]` | Reverse a journal |
| `verify --only-machine M` | The erase gate; nonzero exit means stop |
| `search TEXT` | Query the catalog |
| `smartfolders` | Generate Finder Smart Folders |
| `status` | Summarize the catalog |

Working files live in `.fileorg/` (catalog, plans, journals, duplicate
manifest). It's gitignored — it lists your personal filenames.

### Safety properties

- `apply` and `undo` do nothing without `--execute`.
- Nothing is ever deleted. Duplicates are quarantined; junk is only reported.
- Copy → verify → remove, never a bare cross-volume move.
- Every action is journaled and reversible.
- `scan` refuses `/`, `/System`, `/Library`, `/Volumes` and `~/Library` unless
  you pass `--allow-unsafe`.
- Re-running any step is safe; a rescan preserves the dedupe and
  classification work already done, unless the file itself changed.

[ccc]: https://bombich.com
[sd]: https://shirtpocket.com/SuperDuper/
[gp]: https://grandperspectiv.sourceforge.net
[ods]: https://www.omnigroup.com/more
[czkawka]: https://github.com/qarmin/czkawka
[dupeguru]: https://dupeguru.voltaicideas.net
[organize]: https://github.com/tfeldmann/organize
[hazel]: https://www.noodlesoft.com
[raycast]: https://www.raycast.com
[alfred]: https://www.alfredapp.com
[osxphotos]: https://github.com/RhetTbull/osxphotos
[recoll]: https://www.lesbonscomptes.com/recoll/
[apple]: https://support.apple.com/HT201065
