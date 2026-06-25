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
