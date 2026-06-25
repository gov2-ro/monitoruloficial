# Activity Log

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
