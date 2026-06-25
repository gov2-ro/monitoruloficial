# Plan: PDF → Markdown conversion (`convert.py`)

## Context

We have 38GB of downloaded PDFs across 8 gazette sections. Before building analysis pipelines we need a reliable PDF→text step. Exploration confirmed:

- **All tested PDFs have real text layers** (no OCR needed) — both PI/2013 and PIV/2025 samples extracted cleanly
- `pdftotext` (poppler) is already installed via Homebrew; no new dependencies required
- `pymupdf4llm`, `pypdf`, `PyPDF2` are all **not installed**
- `mof-convert-txt.py` is a dead experiment (hardcoded to `_obsolete/` samples, PyPDF2-based) — will be superseded

**Data inventory:**

| Section | PDFs | Size | Structure | Ready now? |
|---|---|---|---|---|
| PI | 16,704 | 22 GB | `data/PI/<year>/*.pdf` | ✅ |
| PII | 2,753 | 768 MB | `data/PII/<year>/*.pdf` | ✅ |
| PIM | 723 | 211 MB | `data/PIM/<year>/*.pdf` | ✅ |
| PV | 12 | 96 KB | `data/PV/<year>/*.pdf` | ✅ |
| PIII | 14,496 (pages) | 1.6 GB | per-page, unmerged | needs `concat_pages.py` |
| PIV | 441,290 (pages) | 13 GB | per-page, unmerged | needs `concat_pages.py` |
| PVI | 444 (pages) | 75 MB | per-page, unmerged | needs `concat_pages.py` |
| PVII | 1,688 (pages) | 51 MB | per-page, unmerged | needs `concat_pages.py` |

---

## Approach

Create `convert.py` at repo root. Uses `pdftotext` via subprocess (already installed, proven on these PDFs). Outputs sibling `.md` files next to each source PDF (same directory, same basename). Follows existing script patterns (argparse, tqdm, `utils/common.py`, macOS `say`).

**Why `pdftotext` over `pymupdf4llm`:**
- Already installed, zero new deps
- PDFs have text layers — no OCR or layout detection needed
- Produces clean prose; for LLM/analysis use, clean text ≥ noisy markdown headings
- If richer markdown is needed later, add `--converter pymupdf4llm` as an option

---

## Implementation

### New file: `convert.py`

**Key functions:**

**`parse_filename(pdf_path: Path) -> dict | None`**
- Regex: `r'Monitorul-Oficial--(\w+)--(\w+)--(\d{4})\.pdf$'` → `{part, number, year, is_bis}`
- For deep-path sections (PIII+): extract `date` from grandparent dir name (`YYYY-MM-DD`)
- Returns `None` on parse failure

**`find_pdfs(root: Path, sections: list[str]) -> list[Path]`**
- `FLAT_PARTS = {"PI", "PII", "PIM", "PV"}` → glob `data/<Px>/*/*.pdf`
- Deep sections (PIII, PIV, PVI, PVII) → glob `data/<Px>/*/*/*.pdf` (finds merged docs after concat; page-level `N.pdf` files are one level deeper, excluded)
- Filter to paths whose filename starts with `Monitorul-Oficial--`
- Warn when a deep section has 0 merged PDFs: `"PIII: 0 merged PDFs — run concat_pages.py first (N .done markers found)"`

**`clean_text(raw: str) -> str`**
- Split on form-feed `\x0c` into pages
- Per page: strip leading page-number line (`^\d{1,4}\n`) and running header (`MONITORUL OFICIAL AL ROM[ÂA]NIEI[^\n]*\n`)
- Rejoin pages with `\n\n---\n\n` (lightweight page separator, useful for LLM chunking)
- Strip ISSN/barcode artifact on last page
- Collapse 3+ blank lines → 2; strip trailing whitespace per line
- Note: no hyphen-break repair needed — pdftotext already joins them

**`make_frontmatter(meta: dict) -> str`**
```yaml
---
source: monitoruloficial.ro
part: PI
number: "533"
year: 2013
date: null          # filled for PIII+ where path includes YYYY-MM-DD
is_bis: false
converter: pdftotext
converted_at: 2026-06-25T10:00:00
---
```

**`convert_one(pdf_path: Path, overwrite: bool, dry_run: bool) -> tuple[str, bool]`**
1. Check `.md` sibling exists → skip unless overwrite
2. `dry_run` → return early
3. `subprocess.run(['pdftotext', '-enc', 'UTF-8', str(pdf_path), '-'], timeout=300)` — 300s for large Bis files (844MB)
4. `clean_text()` + `make_frontmatter()` + write with `Path.write_text(..., encoding='utf-8')` (not `writefile()` — that omits encoding, unsafe for Romanian chars)
5. Never write partial output; failed conversions leave no `.md` → re-runnable

**`main()`**
```
argparse:
  -s / --sections: one or more of PI PII PIII PIV PIM PV PVI PVII (default: all)
  --overwrite / --no-overwrite (BooleanOptionalAction, default: False)
  --dry-run
  -w / --workers INT (default: min(8, os.cpu_count()))
  --debug

ThreadPoolExecutor with tqdm(as_completed(...))
Summary: "Done: N converted  M already existed  K failed"
macOS say guard (same pattern as get_index.py)
```

**CLI usage:**
```bash
python convert.py                        # all sections, skip existing
python convert.py -s PV                  # smoke test (12 PDFs)
python convert.py -s PI PII PIM PV       # flat sections only
python convert.py -s PIII PIV PVI PVII   # after concat_pages.py
python convert.py --overwrite            # force reconvert
python convert.py --dry-run              # preview counts only
python convert.py -w 4 --debug
```

### Files to update

- **`readme.md`** — add `convert.py` to usage table and repo layout; add `poppler` to dependency list; check roadmap checkbox for "structured text/html from PDF"
- **`docs/backlog.md`** — add items: FTS5 SQLite indexing, pymupdf4llm as optional converter
- **`docs/activity-log.md`** — add entry after completion

### `mof-convert-txt.py`

Leave in place but superseded. Do not delete yet — it has some useful regex ideas for header detection.

---

## Performance notes

- pdftotext throughput ~5–6 MB/s CPU-bound
- PI (22GB, 8 workers) → ~9 min
- Flat sections total ~23GB → ~12 min
- Markdown output ~20–25% of PDF input size → ~5–6GB total

---

## Verification

1. `python convert.py -s PV --debug` — smoke test, 12 PDFs, inspect one `.md` output
2. `python convert.py -s PI --dry-run` — confirms 16,704 PDFs found, nothing written
3. Run PI once, re-run immediately → second run reports all as "already existed" (idempotency)
4. Spot-check `.md` file: correct YAML frontmatter, no running headers, page separators (`---`) present, Romanian characters intact
