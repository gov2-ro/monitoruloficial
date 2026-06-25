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

- [ ] **`convert.py` — PDF → Markdown batch converter** — plan at `~/.claude/plans/check-the-fetched-pdfs-transient-russell.md`. Use `pdftotext` (poppler, already installed); sibling `.md` output; MO-specific cleanup (strip running headers, page numbers); YAML frontmatter from filename; ThreadPoolExecutor; CLI flags matching existing scripts. Flat sections (PI/PII/PIM/PV, ~20K PDFs) ready immediately; PIII/PIV/PVI/PVII need `concat_pages.py` first. Supersedes `mof-convert-txt.py`.
- [ ] **SQLite FTS5 indexing** — after `convert.py`, index `.md` content into an FTS5 table in `mo.db` for full-text search (zero extra infrastructure).
- [ ] PDF → structured text/HTML — see [pdf2txt.xlsx](https://docs.google.com/spreadsheets/d/1APEmulzWa7PGgDg_mc-7rnY_vbxX2Q6Y)
- [ ] Split into chapters → initial UI
- [ ] NLP, detect entities

## Phase 2: Analysis & UI

- [ ] **NER on extracted text using LegalNERo** — [LegalNERo](https://relate.racai.ro/repository/legalnero), [CarolLuca/LegalNERo](https://github.com/CarolLuca/LegalNERo) is a manually annotated NER corpus from RACAI (Romanian Academy) covering MO documents. Entities: `PER`, `LOC`, `ORG`, `TIME`, plus fine-grained legal refs (`Law`, `Order`, `EmergencyOrdinance`, `Decree`, `Regulation`, `Directive`, `Code`, etc.). Formats: BRAT `.ann` + CoNLL-U Plus. Pre-trained models on this corpus exist on HuggingFace. Use case: from extracted PDF text, identify cited laws, institutions, locations, dates automatically. Start by running an off-the-shelf model; fine-tune later if needed. License: CC BY-NC-ND 4.0 (non-commercial). See also [senisioi/rolegal](https://github.com/senisioi/rolegal), [dumitrescustefan/ronec](https://github.com/dumitrescustefan/ronec/) / [bert-base-romanian-ner](https://huggingface.co/dumitrescustefan/bert-base-romanian-ner)
- [ ] **Search / browse UI** — after text extraction and NER, expose a simple interface to query documents by entity, date, gazette part (Parte I–VII), or full-text search.


## Misc Analysis/UI Ideas
- MO browser with entity detection. 
- index by entity / views / themed profiles?
- MO ELI5/TL;DR version. MO Daily

