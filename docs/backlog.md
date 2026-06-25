# Backlog

## Misc notes
- [ ] revisit data structure
- [ ] bypass rate limiting, rotating proxies or VPN
- [ ] OCR needed pages. is there any?

## PDF pipeline

- [ ] **Add `pypdf` to dependency list** — `concat_pages.py` requires it (`pip install pypdf`). Also consider `pypdf` as a drop-in replacement for the deprecated `PyPDF2` used in `mof-convert-txt.py`.
- [ ] **Migrate `PyPDF2` → `pypdf`** in `mof-convert-txt.py` — PyPDF2 is unmaintained. For scanned pages, `extract_text()` returns nothing; the text-conversion roadmap implies `pdfplumber`/`pymupdf` + an OCR pass (e.g. `ocrmypdf`/`tesseract`).
- [ ] **Track downloads in the DB** — add a `downloads` table (`path`, `bytes`, `sha256`, `status`, `fetched_at`) to give real completeness/idempotency guarantees instead of relying on file-existence checks. Structurally fixes the poison-file and resumability problems at the data layer. (Backlog item "log to db? checksum?" in original `fetch_p3+.py`.)
- [ ] **Archive/compact old years** — `data/` is ~38 GB (not ~100 GB as previously estimated). Archiving or gzip-compressing older year folders is a viable space-saving option. `data/html_cache/` (6,892 prettified HTML files) duplicates the DB JSON and isn't byte-faithful (`prettify()`-transformed) — make writing it optional or gzip-compress.

## Text extraction (roadmap)

- [ ] PDF → structured text/HTML — see [pdf2txt.xlsx](https://docs.google.com/spreadsheets/d/1APEmulzWa7PGgDg_mc-7rnY_vbxX2Q6Y)
- [ ] Split into chapters → initial UI
- [ ] NLP, detect entities
