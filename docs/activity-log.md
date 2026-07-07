# Activity Log

## Observability / monitoring

### 2026-07-07 — fetch_p3+.py: close out abort-path run records, add request counter

- Found that `fetch_p3+.py`'s consecutive-failure abort (`raise SystemExit(1)` at 5 call sites) never called `log_run_end`, so its own `runs` row was left dangling (`status=NULL`, shown as `?` in `stats.py`). Only `main.py`'s wrapping row correctly showed `status='error'`. Also, the console-only `Stopping: N consecutive failures` message used `tqdm.write()`, which bypasses `logging` entirely — under cron (stdout redirected to `/dev/null` per `crontab.example`), that message was lost from `mof.log` completely.
- Fixed: added a `_abort()` helper that logs the stop reason via `logging.error` (reaches the file) and calls `log_run_end(conn, run_id, 'error', {...})` before `raise SystemExit(1)`, replacing all 5 duplicated abort blocks. `fetch_pdfs.py` already did this correctly — `fetch_p3+.py` was the one-off gap.
- Added a `requests_made` counter (incremented before each of the 4 outbound `session.get`/`.post` calls), included in the stats blob on every run (success, partial, and abort) so future `runs` rows carry real request-volume data.
- Context: user is considering smaller cron batches so runs don't reach the 2-consecutive-failure trip. Checked existing history (~2 weeks since observability shipped) — only 2 failure incidents on record, with different signatures (HTTP 500 after ~30min in `fetch_p3+.py`; SSL EOF/RemoteDisconnected after ~7 docs in `fetch_pdfs.py`, likely from two overlapping manual test runs) and no request counts logged. Not enough data to derive a safe request-count threshold yet — the counter above is meant to build that evidence over the next few weeks of cron cycles rather than guessing a number now.

### 2026-06-26 — Logging, run tracking, stats dashboard

- Added `LOG_DIR` / `LOG_PATH` constants to `utils/common.py`; upgraded `setup_logging()` to use `RotatingFileHandler` (5 MB, 10 backups) when a log file is requested. All scripts now call `setup_logging(logfile=LOG_PATH)` so every cron invocation writes timestamped entries to `data/logs/mof.log`.
- Added `runs` table to `mo.db` with helpers `init_runs_table`, `log_run_start`, `log_run_end` in `common.py`. Each script records started/finished timestamps, duration, status (`ok`/`partial`/`error`), and a JSON stats blob (script-specific counters like `days_saved`, `pages_saved`, `downloaded`, etc.).
- Replaced final `print()` summary calls in `concat_pages.py` and `convert.py` with `logging.info()` so summaries appear in the log file.
- Added `__main__` error wrappers (`try/except SystemExit`) to all scripts so unhandled crashes are logged with a traceback rather than silently eaten by cron.
- New `stats.py`: prints a quick aligned table of recent runs from the DB. `python stats.py --last N --script NAME`.
- Added VPN rotation backlog item (NordVPN/ProtonVPN CLI fallback on consecutive failures).
- Added `-start`/`-end` date-range flags to `fetch_pdfs.py` (previously scanned all 6,892 DB rows unconditionally). Useful for VPS bootstrap (`-start 2011-01-01` skips the pre-2011 rows that have no PDFs on the server) and for scoped daily cron runs.
- Added VPS bootstrap guide to `readme.md`: rsync `mo.db` once, then run `fetch_pdfs.py -start 2011-01-01` to fill in PI/PII. Decision: **do not commit `mo.db`** — each machine's cron updates it independently, committing it produces constant binary merge conflicts.

## Scrapers / data layout

### 2026-06-25 — Per-part PDF output folders (PI, PII, PIII…)
- Replaced flat `data/pdfs/<year>/` (Part I/II) and `data/pdfs/_p3+/<year>/` (Parts III–VII)
  with per-part folders directly under `data/`: `data/PI/`, `data/PII/`, `data/PIII/`, etc.,
  each with year subfolders.
- `fetch_pdfs.py`: added `PART_FOLDER` dict keyed on exact section-name strings (`"Partea I"`,
  `"Partea a II-a"`, …); computes `part_key` per section in the loop, builds
  `data/<Px>/<year>/<file>.pdf`.
- `fetch_p3+.py`: added `PART_FOLDER` dict + `section_dir()` helper (matches `shy_parts` substrings
  `"III-a"`, `"IV-a"`, etc.); computes `part_out` and `part_tmp` per URL using
  `os.path.join(pdfs_root, section_dir(sectiune), …)`.
- Staging tree moves from `data/pdfs/_p3+/tmp/<date>/` to `data/<Px>/tmp/<date>/`.
- Migrated existing data with `toolbench/migrate-pdf-folders.py` (36,068 items, 0 warnings).
  Part code extracted from the `--Pxx--` segment already embedded in every filename.
  Discovered `--PIM--` = "Partea I Maghiară"; added to `PART_FOLDER` in `fetch_pdfs.py`.
  Old `data/pdfs/` tree removed after confirming only `.DS_Store` macOS metadata remained.
- Phase 2: eliminated `tmp/` staging level for ephemeral parts — moved
  `data/<Px>/tmp/<date>/<name>/` → `data/<Px>/<year>/<date>/<name>/` (15,876 doc dirs).
  Updated `fetch_p3+.py` `part_tmp` from `…/tmp/<date>` to `…/<year>/<date>`.
  Path audit confirmed both scripts produce paths matching actual disk structure.

## Text extraction

### 2026-06-25 — convert.py: batch PDF → Markdown converter
- Implemented `convert.py` per the plan in `docs/reference/claude-plans-archive/check-the-fetched-pdfs-transient-russell.md`.
- Uses `pdftotext` (poppler) via subprocess; outputs sibling `.md` files with YAML frontmatter parsed from the filename (`part`, `number`, `year`, `is_bis`, `date`).
- `clean_text()` strips per-page running headers (`MONITORUL OFICIAL AL ROMÂNIEI…`), leading page-number lines, and ISSN/barcode artifacts; rejoins pages with `\n\n---\n\n` for LLM chunking.
- ThreadPoolExecutor with configurable workers; tqdm progress bar; idempotent (skips existing `.md` unless `--overwrite`).
- Smoke-tested on PI (16,704 PDFs dry-run confirmed; 3 real conversions verified correct frontmatter, no headers, Romanian chars intact).
- Found: PV "PDFs" are HTML responses (12 files), not real PDFs — `pdftotext` rejects them. Added backlog item to re-download correctly.
- Deep sections (PIII/PIV/PVI/PVII) have no merged PDFs yet — `convert.py` warns and skips; run `concat_pages.py` first.

## Debugging & fixes

### 2026-06-25 — fix: fetch_p3+.py skips re-download after concat_pages archives to _raw/
- `concat_pages.py` moves `doc_dir` → `data/<Px>_raw/…` after merging, taking the `.done` file
  with it. On the next `fetch_p3+.py` run the `.done` check always missed → full re-download.
- Fix: added a second skip condition — if the merged output PDF
  (`data/<Px>/<year>/<date>/<name>.pdf`) exists and passes the PDF magic-byte check, skip
  without any network I/O. The merged PDF is already the authoritative "done + merged" signal.

### 2026-06-25 — VPS/cron readiness: anchor all paths to __file__
- All paths were cwd-relative (`DATA_ROOT = 'data/'`, `sys.path.append("utils/")`), so cron
  (which sets cwd to `$HOME` or `/`) silently broke every file open and import.
- `utils/common.py`: `DATA_ROOT`, `DB_PATH`, `HTML_CACHE` now derived from
  `Path(__file__).resolve().parent.parent` — absolute regardless of cwd.
- All scripts (`get_index.py`, `fetch_p3+.py`, `fetch_pdfs.py`, `concat_pages.py`,
  `convert.py`): `sys.path.append("utils/")` → `sys.path.insert(0, Path(__file__).resolve().parent / 'utils')`.
- `main.py`: `'python'` → `sys.executable` (avoids Python 2 / missing `python` on Linux);
  script names resolved to absolute paths via `Path(__file__).resolve().parent / name`.
- Smoke-tested all four scripts with `cd /tmp && python3 /abs/path/script.py --help` — all pass.
- Updated `readme.md`: removed the "run from repo root" requirement.



### 2026-06-25 — fix: fetch_p3+.py logging + xmo alias corrected
- Added `tqdm.write` to `fetch_p3+.py` to show each MO name and destination folder at normal log level (was `logging.debug`, invisible unless `--debug`).
- Diagnosed why `xmo` alias was processing 233 days of stale 2025 data instead of the current 10-day window: `--start_date 2025-07-18` had been placed on `fetch_p3+.py` by mistake — it was intended for `fetch_pdfs.py`. Since Parts III–VII are only available for 10 days from publication, running `fetch_p3+.py` with an old start date wastes time hitting the site for unavailable content.
- Fixed `xmo` alias in `~/.zshrc`: removed `--start_date 2025-07-18` from `fetch_p3+.py`. Script now always runs with its default last-10-days window.

## Audit & hardening

### 2026-06-25 — Pipeline audit: correctness fixes, robustness hardening, concat_pages.py

Full audit of the scraper pipeline; implemented Tiers 0–2 of the spec plus new `concat_pages.py`.

**Tier 0 — Correctness bugs fixed:**
- `parse_date()` in `utils/common.py`: CLI `-start`/`-end` args now parsed to `datetime` immediately. Fixes `TypeError`/`AttributeError` that made `python main.py` crash the index step entirely.
- `BooleanOptionalAction` for `--overwrite` in all scripts: `--overwrite/--no-overwrite` now produce real booleans. Previously `"False"` (a truthy string) silently enabled overwriting.
- `fetch_p3+.py`: replaced `.json`-exists skip (line 212) with a `.done` completion marker written **after** all pages succeed. Interrupted downloads are now resumed correctly instead of being skipped forever.
- `fetch_p3+.py`: pages only written when `pdf_ok(resp)` confirms HTTP 200 + PDF magic bytes. Poison HTML/empty bodies no longer persist on disk.
- `fetch_p3+.py`: removed `breakpoint()` in the fid regex exception handler — was silently hanging unattended runs.

**Tier 1 — Robustness hardening:**
- `get_index.py`: now uses `make_session()` with retry+timeout; per-day parse errors caught and logged with `continue` instead of killing the entire run.
- `fetch_p3+.py`: HTTP status code checked after every request; bad status **and** bad body count toward `consecutive_failures` breaker (previously only network exceptions counted).
- `fetch_pdfs.py`: logging raised from `CRITICAL` (silent) to `INFO`; HEAD+GET replaced with single GET — halves request count against the ban-happy server. PDF magic bytes validated before writing.
- Hardcoded stale `PHPSESSID` cookies dropped from `base_headers()` in `utils/common.py`.

**Tier 2 — Shared foundation (`utils/common.py` additions):**
- `parse_date()`, `make_session()` (moved from `fetch_p3+.py`), `is_pdf()`, `pdf_ok()`, `setup_logging()`.
- Canonical constants: `DATA_ROOT`, `DB_PATH`, `HTML_CACHE`, `URL_BASE`, `URL_GET_MO`, `URL_GIDF`, `URL_VIEW`, `PART_FOLDER` (full-name keyed, single source of truth), `SHY_PARTS`, `PACE`, `PACE_PAGE`, `TABLE_NAME`.
- `section_dir(sectiune)` covers both full-name exact match and substring fallback — eliminates duplicate lookup logic across scripts.
- `get_index.py`: implements `-m l-<x>` (last x days), previously documented but not functional.
- All scripts wrapped in `if __name__ == '__main__': main()`.
- macOS `os.system('say ...')` guarded with `sys.platform == 'darwin'`.
- Parameterized SQL everywhere (was string-interpolated).
- `--debug` flag added to all scripts via shared `setup_logging()`.

**New script — `concat_pages.py`:**
- Merges `data/<Px>/<year>/<date>/<name>/{1..N}.pdf` → `data/<Px>/<year>/<date>/<name>.pdf`.
- Completeness gate: reads page count from `<name>.done`; validates each page file exists and starts with PDF magic bytes before merging.
- Idempotent: skips output if it exists and is newer than the newest page; `--overwrite` to force.
- `--dry-run` mode; numeric sort (`key=int(p.stem)`) so page 10 follows page 9, not page 1.
- Requires `pypdf` (not yet in the dep list — see backlog).

## Docs / repo hygiene

### 2026-06-25 — Refresh docs after monorepo extraction
- Rewrote `CLAUDE.md` to hold only the general approach (orientation + the two operational
  footguns: run-from-root, no requirements file) plus persona / coding principles / project
  tracking. Moved all architecture, usage, scripts, data-model, and conventions detail into
  `readme.md`.
- Fixed post-move stale paths in `mof-convert-txt.py` and `toolbench/cleanup-p3folder.py`
  (were `../../data/mo/...`; now repo-root-relative `data/...`).
- Removed cross-project leftovers from the docs (full-stack persona, non-existent
  "site specific readme / config" references, typos).
- Why: repo was extracted from a larger monorepo, so paths and docs no longer matched reality.
