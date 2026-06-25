# Audit & hardening — monitoruloficial.ro scraper pipeline

## Context

The user asked for an audit/brainstorm of the code and pipeline to find what could be
**optimised** and made **more robust**. This is a 3-stage scraper (index → PDFs → text) of
~950 LOC across `get_index.py`, `fetch_pdfs.py`, `fetch_p3+.py`, `mof-convert-txt.py`,
`utils/common.py`, plus `main.py` orchestrator and `toolbench/` one-offs. Data store is
SQLite (`data/mo.db`, 6,892 day-rows, 2000→2026) + 38 GB of PDFs under `data/<Px>/<year>/`.

The server **IP-bans aggressive clients**, so the design is deliberately sequential and
heavily paced. The right optimisation axis here is **fewer/safer requests and no silent data
corruption**, NOT parallelism — I'd explicitly avoid adding concurrency.

Below is the full audit. Findings marked ✅ were reproduced/verified this session.

---

## Tier 0 — Correctness bugs (blocking or silent corruption)

1. ✅ **`-start`/`-end` CLI args crash the date pipeline.** In `get_index.py` (lines 49–52)
   and `fetch_p3+.py` (77–80), CLI dates are stored as raw **strings**, but the defaults are
   `datetime` objects and the code does datetime arithmetic on them.
   - `get_index.py:61` → `generate_dates(start_str, end_dt)` does `(end_dt - start_str)` →
     `TypeError`. `get_index.py:72` does `start_str.strftime()` → `AttributeError`.
   - Because `main.py` **always** forwards a `-start` (default = 2 weeks ago), **`python
     main.py` is broken for the entire index step.** Reproduced both crashes this session.
   - Fix: parse all CLI dates with one shared `parse_date()` → `datetime` immediately.

2. ✅ **`--overwrite False` turns overwriting ON.** `overwrite = args.overwrite` stores the
   string `"False"`, which is truthy (`get_index.py:53–54`, `fetch_p3+.py:81–82`). Passing the
   flag to *disable* overwriting silently *enables* it. Fix: `argparse` `BooleanOptionalAction`
   or explicit `str2bool`.

3. **Resumability bug: `.json` marker written before pages → interrupted docs skipped
   forever.** `fetch_p3+.py:212` skips a whole document if its `<name>.json` exists, but the
   `.json` is written (line 225) *before* the page-PDF loop (line 231). A run interrupted
   mid-document leaves the `.json` on disk, so every later run `continue`s past it and the
   missing pages are **never** downloaded. Fix: write a completion marker only *after* all
   pages succeed (or check page-count completeness), not the jsonp.

4. **No validation that a downloaded "PDF" is a PDF → sticky poison files.**
   `fetch_p3+.py:248` writes `response.content` to `<i>.pdf` with no status-code or
   content check. The site returns HTTP 200 with HTML/empty bodies under load; that garbage
   is saved as `.pdf`, and the skip-if-exists check (235) means it's **never re-fetched**.
   Fix: check `status_code == 200`, non-empty, and `%PDF` magic bytes before writing; skip
   (don't write) otherwise. (`fetch_pdfs.py` checks content-type — `fetch_p3+.py` checks
   nothing.)

5. **`breakpoint()` in an exception handler (`fetch_p3+.py:175`).** If the `var fid` regex
   ever raises, an unattended run drops into a **pdb prompt and hangs**. Remove it; log and
   `continue`.

---

## Tier 1 — Robustness hardening

6. **`get_index.py` has no timeout / retry / session.** Bare `requests.post(..., verify=False)`
   (line 93) with **no `timeout`** can hang indefinitely; no retry. `fetch_p3+.py` already has
   a good `make_session()` (Retry total=1, backoff, status_forcelist, timeouts). Reuse it.

7. **Unguarded HTML parse in `get_index.py`.** Only the POST is in `try/except`; the parse
   (`ol.text`, lines 99–104) is not. An empty/changed page → `AttributeError` kills the whole
   multi-day run. Guard per-day and `continue`.

8. **No `status_code` checks anywhere in `fetch_p3+.py`.** 403/429/500 bodies get parsed and
   written. The `consecutive_failures` breaker only counts *network exceptions* — a server
   returning 200-with-garbage under load never trips it (the JSONDecode branch at 205
   `continue`s without incrementing). Count bad bodies toward the breaker too.

9. **`fetch_pdfs.py` logs at `level=CRITICAL` (line 32) → runs essentially silent.** All its
   `logging.info/error/warning` are suppressed. Likely unintended. Also it does a **HEAD then
   GET** for every file (lines 64, 77) — doubles the request count against a rate-limited,
   ban-happy server. Drop the HEAD; GET + validate.

10. **Stale hardcoded `PHPSESSID` cookies** in `utils/common.py:27,48`. Brittle if the server
    starts enforcing sessions; today probably ignored. Drop them or fetch a session cookie.

---

## Tier 2 — Maintainability / DRY / config

11. **Duplicated contracts.** `PART_FOLDER` exists twice with different shapes
    (`fetch_pdfs.py:9` keyed on full names, `fetch_p3+.py:25` keyed on substrings);
    `shy_parts` is duplicated in 3 files; `section_dir()` logic is ad hoc. Centralise
    `PART_FOLDER`, `shy_parts`, paths, base URLs, and pacing in `utils/common.py` (or a small
    `config.py`).

12. **String-interpolated SQL** for date ranges (`get_index.py:80`, `fetch_p3+.py:98`). Local,
    not a security risk, but fragile (and breaks on the date-type bug above). Use
    parameterised queries + `with sqlite3.connect(...)`.

13. **`get_index.py` / `fetch_p3+.py` run at import (no `if __name__ == '__main__'`)** — can't
    be imported or unit-tested. The `-m l-<x>` "last x days" mode is **documented but never
    implemented** (`get_index.py:47`).

14. **Inconsistent logging / no debug flag.** `verbose` booleans gate `tqdm.write`, but
    `logging` is configured in only one script (badly). CLAUDE.md persona explicitly wants a
    **debug mode with verbose logging via a config flag** — add one shared logging setup.

15. **macOS-only `os.system('say …')`** at the end of two scripts (and an unconditional final
    one) — harmless no-op elsewhere but noisy/odd. Guard behind `sys.platform == 'darwin'` +
    a config flag.

---

## Tier 3 — Pipeline / roadmap opportunities (bigger, optional)

16. **Concatenate page PDFs (roadmap item).** Pages are saved as separate single-page PDFs;
    merging with `pypdf` is a quick win to produce one PDF per document.
17. **Migrate `PyPDF2` → `pypdf`** (PyPDF2 is deprecated/unmaintained). For scanned pages
    `extract_text()` returns nothing — the roadmap's OCR need implies `pdfplumber`/`pymupdf` +
    an OCR pass (e.g. `ocrmypdf`/`tesseract`). Flag for the text stage.
18. **Track downloads in the DB (backlog TODO "log to db? checksum?").** A `downloads` table
    (path, bytes, sha256, status, fetched_at) gives real completeness/idempotency instead of
    "file exists on disk", and fixes #3/#4 structurally.
19. **`data/` is 38 GB** (backlog guessed ~100 GB). Archiving/compaction of old years is a
    real option; also `html_cache/` (6,892 prettified files) duplicates DB JSON and isn't
    byte-faithful (it's `prettify()`d) — make optional or gzip.

---

## Implementation spec (handoff)

**Implementation will be done by a separate Sonnet session.** This Opus pass produces the spec
only — no source files are edited here. The spec below is written to be executed directly:
per-file, with concrete function signatures and a tier ordering. Implement in tier order
(Tier 0 → 1 → 2 → concat); each tier is independently shippable. Run everything from repo root.

### Step 1 — Shared foundation: `utils/common.py`

Add the shared primitives the rest of the work depends on:

- `parse_date(value, fmt='%Y-%m-%d') -> datetime` — return `value` unchanged if already a
  `datetime`; else `datetime.strptime(value, fmt)`. **Fixes Tier 0 #1.**
- Adopt `argparse.BooleanOptionalAction` for `--overwrite` in each script (gives
  `--overwrite/--no-overwrite`, real bools). **Fixes Tier 0 #2.** (No `str2bool` needed.)
- `make_session()` — move the existing one from `fetch_p3+.py:50` here verbatim (keep the
  single-retry / ban-aware comment). All scripts import it.
- `is_pdf(content: bytes) -> bool` → `content[:5] == b'%PDF-'`; and
  `pdf_ok(resp) -> bool` → `resp.status_code == 200 and resp.content and is_pdf(resp.content)`.
  **Backs Tier 0 #4.**
- Canonical config constants (single source of truth): `PART_FOLDER` (full-name keyed),
  `SHY_PARTS`, `DATA_ROOT`, `DB_PATH`, `HTML_CACHE`, `URL_BASE`, `URL_GET_MO`, `URL_GIDF`,
  `URL_VIEW`, and pacing tuples. Add `section_dir(sectiune)` covering both full-name and
  shy-substring lookups. **Fixes Tier 2 #11.**
- `setup_logging(debug: bool)` — one shared config (level INFO, or DEBUG when `debug`),
  file + stream handlers. **Fixes Tier 1 #9 / Tier 2 #14.**
- Drop the hardcoded `PHPSESSID` from both header sets. **Fixes Tier 1 #10.**

### Step 2 — Tier 0 correctness (highest priority)

- `get_index.py`: wrap in `if __name__ == '__main__': main()`; `parse_date()` start/end;
  implement `-m l-<x>` (last x days, currently documented-only at line 47); parameterized SQL
  (lines 80, 116); timeout + `make_session()` on the POST; guard the parse (`if ol is None:
  continue`, per-day try/except → log+continue). **#1, #6, #7, plus #13.**
- `fetch_p3+.py`: **remove `breakpoint()` (line 175)** → log+continue (#5); `parse_date()`
  start/end (#1, fixes `-end` crash); add `status_code` checks after each request and count
  bad status/bad-body toward `consecutive_failures` (#8); **only write a page file when
  `pdf_ok(resp)`** — never write poison (#4); **replace the `.json`-exists skip (line 212)**
  with a completion marker written *after* all pages succeed: write `<name>.done` containing
  `page_count`, and gate the skip on `.done` existing AND all `1..page_count` page files
  present+valid (#3). Parameterized SQL (line 98).
- `fetch_pdfs.py`: raise log level off `CRITICAL` via `setup_logging` (#9); **drop the HEAD
  request (line 64)** — single GET with `stream`, validate content-type/magic before save (#9,
  #21); use canonical `PART_FOLDER`/`section_dir`.

### Step 3 — New `concat_pages.py` (the spec'd item, build after #3/#4 land)

- Merge `data/<Px>/<year>/<date>/<name>/{1..N}.pdf` → `data/<Px>/<year>/<date>/<name>.pdf`.
- `pypdf` `PdfWriter`; append pages **in numeric order**:
  `sorted(dir.glob('*.pdf'), key=lambda p: int(p.stem))` (so `10.pdf` ≠ before `2.pdf`).
- **Completeness gate** (depends on Tier 0 #3/#4): read `page_count` from `<name>.json`
  (gidf `p`); only merge if all `1..page_count` exist and each `is_pdf`. Skip+warn otherwise.
- Idempotency: skip if output exists and newer than newest page; `--overwrite` to force.
  `--dry-run`. Keep page dir by default (add `--prune` later). Repo-root-relative, no network,
  tqdm progress, `if __name__ == '__main__'`.

### Step 4 — Docs (every pass)

- `readme.md`: corrected CLI (dates parsed; `--overwrite/--no-overwrite`; `-m l-<x>` works),
  new `concat_pages.py`, shared config now in `utils/common.py`.
- `docs/activity-log.md`: dated entry per CLAUDE.md.
- `docs/backlog.md`: record deferred **Tier 3** items as `- [ ]` — downloads/checksum table
  (#18), `PyPDF2 → pypdf` + OCR for the text stage (#17), archive/gzip old years + optional
  `html_cache` (#19, note actual size **38 GB** not ~100 GB).

### Explicitly out of scope / do NOT do

- **No concurrency / parallelism.** The server IP-bans aggressive clients; the optimisation
  axis is *fewer, validated* requests, not more of them. Adding threads would get the IP banned.

## Verification (for the implementing session)

Per CLAUDE.md: run from repo root, 3-min timeout per command, cap scrape ranges to **2–3 days**.

- **Repro→fixed:** `python main.py -start 2024-06-01` no longer crashes the index step;
  `--overwrite` vs `--no-overwrite` behave correctly; passing `-end` works.
- **Validation:** feed a non-PDF body (or point at a known-bad day) and assert no `.pdf` is
  written and the breaker counts it.
- **Resumability:** delete one page file + the `.done` marker mid-doc, re-run, confirm the
  missing page re-downloads and the doc completes (no more "skip forever").
- **Concat:** on a complete doc dir, `concat_pages.py --dry-run` then real; verify the merged
  PDF opens and page order is correct (page 2 precedes page 10).
- `git diff` review before any commit (commit only if the user asks).
