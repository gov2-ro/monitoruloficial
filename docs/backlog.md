# Backlog

## Misc notes
- [ ] revisit data structure
- [ ] bypass rate limiting, rotating proxies or VPN
- [ ] OCR needed pages. is there any?

## Orchestration

- [ ] **`main.py` — single-command pipeline** — update `main.py` to orchestrate the full workflow in sequence: `fetch_p3+.py` (download per-page PDFs) → `concat_pages.py` (merge + archive to `_raw/`) → `convert.py` (PDF → Markdown). Should accept the same date-range flags as the individual scripts and short-circuit cleanly if a step produces no new files.
- [ ] **run on VPS** - prepare for cron
- [ ] **VPN rotation on rate-limit** — when consecutive request failures exceed a threshold, reconnect via NordVPN or ProtonVPN CLI to get a new egress IP before retrying. ProtonVPN: `protonvpn-cli c --sc`; NordVPN: `nordvpn connect`. Hook into the per-script failure breaker in `fetch_p3+.py` or a shared wrapper in `common.py`.

## PDF pipeline

- [ ] **Add `pypdf` to dependency list** — `concat_pages.py` requires it (`pip install pypdf`). Also consider `pypdf` as a drop-in replacement for the deprecated `PyPDF2` used in `mof-convert-txt.py`.
- [ ] **Migrate `PyPDF2` → `pypdf`** in `mof-convert-txt.py` — PyPDF2 is unmaintained. For scanned pages, `extract_text()` returns nothing; the text-conversion roadmap implies `pdfplumber`/`pymupdf` + an OCR pass (e.g. `ocrmypdf`/`tesseract`).
- [ ] **`fetch_p3+.py` re-downloads after `concat_pages.py` archives to `_raw/`** — `fetch_p3+.py` skips via `doc_dir/<name>.done`, but after `concat_pages.py` runs it moves `doc_dir` → `data/<Px>_raw/…`, so `.done` is gone and the next fetch re-downloads. Fix: also treat the merged output PDF (`doc_dir.parent/<name>.pdf`) as a completion signal — if it exists and is a valid PDF, skip. One extra `_page_valid`-style check before the network hits.
- [ ] **Track downloads in the DB** — add a `downloads` table (`path`, `bytes`, `sha256`, `status`, `fetched_at`) to give real completeness/idempotency guarantees instead of relying on file-existence checks. Structurally fixes the poison-file and resumability problems at the data layer. (Backlog item "log to db? checksum?" in original `fetch_p3+.py`.)
- [ ] **Archive/compact old years** — `data/` is ~38 GB (not ~100 GB as previously estimated). Archiving or gzip-compressing older year folders is a viable space-saving option. `data/html_cache/` (6,892 prettified HTML files) duplicates the DB JSON and isn't byte-faithful (`prettify()`-transformed) — make writing it optional or gzip-compress.

## Text extraction (roadmap)

- [x] **`convert.py` — PDF → Markdown batch converter** — implemented 2026-06-25. pdftotext, sibling `.md` output, YAML frontmatter, header/pagenum cleanup, ThreadPoolExecutor. Note: PV "PDFs" are actually HTML responses (not real PDFs); pdftotext rejects them — PV conversion will fail until re-downloaded correctly.
- [ ] **SQLite FTS5 indexing** — index `.md` content from `convert.py` into an FTS5 table in `mo.db` for full-text search (zero extra infrastructure).
- [ ] **PV section re-download** — `data/PV/` files are HTML (not PDFs); `pdf_ok()` check was not enforced on download. Re-fetch these 12 files using the correct PDF URL and re-run `convert.py -s PV`.
- [ ] **Consolidate `_raw` dirs into `data/raw/P*/`** — currently per-section raw dirs land as `data/PIII_raw/`, `data/PIV_raw/`, etc. Cleaner to mirror under `data/raw/PIII/`, `data/raw/PIV/`, etc. so the whole raw tree is deletable with `rm -rf data/raw/`. Requires updating `_raw_dest()` in `concat_pages.py` and migrating any existing `data/*_raw/` dirs.
- [ ] **`fetch_p3+.py` should write per-page PDFs into `data/raw/P*/`** — currently `fetch_p3+.py` downloads directly into `data/P*/` (the final output location). It should instead save per-page PDFs into `data/raw/P*/` (a staging area), then `concat_pages.py` merges them into `data/P*/` as today. Mirrors the pattern that `concat_pages.py` already establishes when it archives source pages to `_raw/` after a merge. Makes the distinction between raw downloads and merged outputs explicit in the directory tree and aligns with the `data/raw/` consolidation above.
- [ ] PDF → structured text/HTML — see [pdf2txt.xlsx](https://docs.google.com/spreadsheets/d/1APEmulzWa7PGgDg_mc-7rnY_vbxX2Q6Y)
- [ ] Split into chapters → initial UI
- [ ] NLP, detect entities
- [ ] text extraction should be used for both analysis and rendering of PDFs as HTML - reconstructing layout, pagination and columns (but responsive).


## Phase 2: Analysis & UI

- [ ] **NER on extracted text using LegalNERo** — [LegalNERo](https://relate.racai.ro/repository/legalnero), [CarolLuca/LegalNERo](https://github.com/CarolLuca/LegalNERo) is a manually annotated NER corpus from RACAI (Romanian Academy) covering MO documents. Entities: `PER`, `LOC`, `ORG`, `TIME`, plus fine-grained legal refs (`Law`, `Order`, `EmergencyOrdinance`, `Decree`, `Regulation`, `Directive`, `Code`, etc.). Formats: BRAT `.ann` + CoNLL-U Plus. Pre-trained models on this corpus exist on HuggingFace. Use case: from extracted PDF text, identify cited laws, institutions, locations, dates automatically. Start by running an off-the-shelf model; fine-tune later if needed. License: CC BY-NC-ND 4.0 (non-commercial). See also [senisioi/rolegal](https://github.com/senisioi/rolegal), [dumitrescustefan/ronec](https://github.com/dumitrescustefan/ronec/) / [bert-base-romanian-ner](https://huggingface.co/dumitrescustefan/bert-base-romanian-ner)
- [ ] **Search / browse UI** — after text extraction and NER, expose a simple interface to query documents by entity, date, gazette part (Parte I–VII), or full-text search.


## Misc Analysis/UI Ideas
- MO browser with entity detection. 
- index by entity / views / themed profiles?
- MO ELI5/TL;DR version. MO Daily. Create TOC for each MO.

