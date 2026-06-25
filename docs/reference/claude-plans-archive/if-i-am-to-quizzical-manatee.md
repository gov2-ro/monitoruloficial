# Plan: VPS Gap-Fill — fetch_pdfs date filter + bootstrap guide

## Context

On VPS: no PDFs will be uploaded (too large). The scraper needs to download only what's missing. Additionally, gaps exist even locally (PI/PII PDFs start from 2011 even though the DB goes back to 2000). The user wants to understand the gap-detection mechanism and whether to commit `mo.db`.

**Short answers:**

- **Gap detection**: `fetch_pdfs.py` already handles gaps perfectly — it checks `os.path.isfile(output_path)` per URL and downloads only missing files. No code changes are needed for idempotent gap-filling. Just run it; it skips existing files and downloads missing ones.
- **mo.db in git**: **No**. The DB is updated twice daily by cron on each machine independently; committing it would create constant binary-file conflicts and pollute history. The right approach is a one-time `rsync` from local to VPS at setup time, then cron keeps it current on the VPS.

---

## What's in the DB vs on disk

- DB: 6,892 dates (2000-01-03 → 2026-06-25). Years 2000–2010 appear to have empty JSON (no PDF URLs served by the server for that era), so `fetch_pdfs.py` silently skips them.
- Disk (local): PI=16,704 PDFs, PII=2,753 PDFs — both starting from 2011.
- On a fresh VPS with an empty `data/`, running `fetch_pdfs.py` would download all ~19,000 PI+PII files (slow but correct).

---

## The one real gap: `fetch_pdfs.py` has no date filter

Unlike `get_index.py` and `fetch_p3+.py`, `fetch_pdfs.py` has no `-start`/`-end` args — it always scans all 6,892 DB rows. On a VPS starting fresh, that's fine. But two scenarios benefit from a filter:

1. **Scoping to years with actual PDFs**: `-start 2011-01-01` skips the silent-no-op 2000–2010 rows and makes progress bars meaningful.
2. **Incremental daily runs**: cron only needs to check recent dates, not scan all 6,892 rows.

---

## Changes

### 1. `fetch_pdfs.py` — add `-start` / `-end` date args

Add the same pattern used in `get_index.py`:

```python
parser.add_argument('-start', '--start_date', help='start date YYYY-MM-DD (default: all)')
parser.add_argument('-end',   '--end_date',   help='end date YYYY-MM-DD (default: today)')
```

Change the DB query (line 70) from:
```python
c.execute(f'SELECT * FROM {TABLE_NAME} ORDER BY date DESC')
```
to:
```python
if args.start_date or args.end_date:
    start = args.start_date or '2000-01-01'
    end   = args.end_date   or datetime.today().strftime('%Y-%m-%d')
    c.execute(f'SELECT * FROM {TABLE_NAME} WHERE date BETWEEN ? AND ? ORDER BY date DESC', (start, end))
else:
    c.execute(f'SELECT * FROM {TABLE_NAME} ORDER BY date DESC')
```

Import `datetime` (already available via stdlib — check the current imports; if not present, add it).

---

### 2. `readme.md` — add VPS bootstrap section

Under the new **Monitoring** section (or adjacent), add a **VPS setup** subsection:

```markdown
## VPS setup

1. Clone the repo on the VPS.
2. Copy the index DB from local (one-time): `rsync -avz data/mo.db user@vps:path/to/repo/data/`
3. Run `fetch_pdfs.py` to download all missing PI/PII PDFs:
   ```bash
   python fetch_pdfs.py -start 2011-01-01   # skip the empty 2000–2010 rows
   ```
   Already-existing files are skipped; re-runnable at any time to fill gaps.
4. Run `fetch_p3+.py` for ephemeral parts (only last ~10 days are online).
5. Set up cron (see crontab entries in `docs/`).

**Do not commit `mo.db` to git** — it is updated twice daily by each machine's cron independently. Use `rsync` for the initial copy and let cron keep it current.
```

---

## What NOT to change

- `fetch_pdfs.py` gap-detection logic: already correct. File existence check = gap detector.
- No new `downloads` table or checksum logic needed for this task (that's a separate backlog item).
- `get_index.py` and `fetch_p3+.py`: already have `-start`/`-end`; no changes.

---

## Verification

1. `python fetch_pdfs.py -start 2026-06-01 -end 2026-06-26` — should only scan June 2026 rows; check log shows correct row count.
2. `python fetch_pdfs.py --help` — confirm new flags appear.
3. `python fetch_pdfs.py -start 2011-01-01` in dry-run mental model: skips all existing 2011–2024 files, downloads any 2025–2026 gaps.
