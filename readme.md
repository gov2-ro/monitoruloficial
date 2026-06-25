# monitoruloficial.ro — Official Gazette scraper

scrape [monitoruloficial.ro/e-monitor](https://monitoruloficial.ro/e-monitor/) → save pdfs → get text → make nice / explorable.

This repo was extracted from a larger monorepo into a standalone repo. Everything is now
repo-root–relative, so **always run scripts from the repo root** (not from a subdirectory):
imports (`sys.path.append("utils/")`) and data paths (`data/...`) depend on it.

## Usage

```bash
python main.py                        # orchestrator: get_index.py then fetch_p3+.py, last 2 weeks
python main.py -start 2024-01-01      # from a given date (forwarded to both scripts)

python get_index.py                   # fetch daily index → SQLite + HTML cache (last 15 days)
python get_index.py -start 2024-01-01 -end 2024-03-01
python get_index.py -m l-7            # last 7 days
python get_index.py -m all            # from 2000-01-04 through today

python fetch_p3+.py                   # download ephemeral Parts III–VII (online only ~10 days)
python fetch_pdfs.py                  # download persistent Parts I/II PDFs
python concat_pages.py                # merge per-page PDFs into single-document PDFs
python concat_pages.py --dry-run      # preview without writing
python mof-convert-txt.py             # experimental PyPDF2 PDF→markdown conversion
```

Dependencies (no requirements file — install manually): `requests`, `beautifulsoup4`, `tqdm`,
`urllib3`, `PyPDF2`, `pypdf` (for `concat_pages.py`). Python 3.

CLI flags are **per-script**:

| script | flags |
|---|---|
| `get_index.py` | `-start` `-end` `--overwrite/--no-overwrite` `-m/--mode` `--debug` |
| `fetch_p3+.py` | `-start` `-end` `-days` `--overwrite/--no-overwrite` `-m/--mode` `--debug` |
| `fetch_pdfs.py` | `--debug` |
| `concat_pages.py` | `[root]` `--dry-run` `--overwrite/--no-overwrite` `--debug` |
| `main.py` | `-start` only |

`--overwrite` re-processes items already on disk; `--no-overwrite` (the default) skips them.
`-m l-<x>` means "last x days" (e.g. `-m l-7`). `-m all` runs from 2000-01-04 to today.

## Architecture

Two tiers: build a per-day index of available parts, then download the PDFs for those parts.

- **`get_index.py`** — POSTs `{today, rand}` to `.../emonitor/get_mo.php` per weekday, parses the
  returned HTML (`div.card-body` → `ol.breadcrumb` section name + `a.btn` links), and upserts one
  row per day into SQLite. Also writes a prettified HTML snapshot per day to
  `data/html_cache/<date>.html`. Skips days already in the DB unless `--overwrite`.
- **`fetch_pdfs.py`** — reads every DB row and downloads the **persistent** parts (Part I/II etc.)
  into `data/pdfs/<year>/`, skipping files that already exist. Always processes all rows
  newest-first; configure via the variables at the top of the file.
- **`fetch_p3+.py`** — downloads only the **ephemeral** parts (`shy_parts` =
  `["III-a","IV-a","VI-a","VII-a"]`, online ~10 days). Multi-step per part: scrape `var fid` from
  the part page → POST `gidf.php` for page count + folder → download each page as a separate PDF
  plus a jsonp into the `data/pdfs/_p3+/tmp/<date>/<filename>/` staging tree. Page PDFs are **not
  yet concatenated** (see roadmap). Anti-ban: paces every request with random sleeps, retries at
  most once (retry bursts keep the server's IP ban hot), and aborts after 2 consecutive network
  failures.
- **`mof-convert-txt.py`** — standalone PyPDF2 experiment that converts sample PDFs to markdown.

`shy_parts` is the contract between the two PDF scrapers: `fetch_pdfs.py` skips those parts,
`fetch_p3+.py` fetches only them.

### Shared utilities (`utils/common.py`)

Imported as `from common import ...` (after `sys.path.append("utils/")`). Provides:

**Helpers**
- `generate_dates(start, end, format)` — weekday-only date list
- `parse_date(value)` — returns `datetime`; accepts either a string or a `datetime` unchanged
- `base_headers(which)` — pre-built request headers (`'headers1'` for AJAX/POST, `'headers2'`
  for document GETs)
- `make_session()` — `requests.Session` with single-retry, ban-aware backoff
- `is_pdf(content)` / `pdf_ok(resp)` — validate a response body before writing to disk
- `section_dir(sectiune)` — maps any section name to its `data/<Px>` folder code (exact then
  substring match)
- `setup_logging(debug, logfile)` — shared logging configuration (INFO or DEBUG)
- `readfile(path)` / `writefile(path, content)` — encoding-tolerant file I/O

**Canonical constants** (single source of truth for all scripts)
- Paths: `DATA_ROOT`, `DB_PATH`, `HTML_CACHE`
- URLs: `URL_BASE`, `URL_GET_MO`, `URL_GIDF`, `URL_VIEW`
- Data model: `PART_FOLDER` (full-name → folder code), `SHY_PARTS`, `TABLE_NAME`
- Pacing: `PACE` (between documents), `PACE_PAGE` (between pages of the same document)

### Data model

SQLite `data/mo.db`, table `dates_lists`: `date TEXT PRIMARY KEY`, `json TEXT`. The JSON maps each
section name (e.g. `"Partea I"`) → `{ part-number: href }`.

PDFs land under `data/<Px>/<year>/` for all parts. For the ephemeral parts (PIII, PIV, PVI,
PVII), `fetch_p3+.py` stages per-page downloads in `data/<Px>/<year>/<date>/<filename>/` before
concatenation (roadmap). `<Px>` is one of `PI`, `PII`, `PIII`, `PIV`, `PV`, `PVI`, `PVII`,
`PIM` (Partea I Maghiară). The whole `data/` dir is gitignored.

### Conventions & gotchas

- Rate limiting everywhere: random sleeps between requests + a longer pause every N items.
  Pacing constants live in `utils/common.py` (`PACE`, `PACE_PAGE`).
- `urllib3.disable_warnings(...)` + `verify=False` throughout — the site has SSL issues.
- `get_index.py` and `fetch_p3+.py` end with `os.system('say -v ioana ...')` — a macOS-only
  spoken "done" announcement, guarded by `sys.platform == 'darwin'`.
- `fetch_p3+.py` writes a `<name>.done` file (containing the page count) only after all pages
  download successfully. This is the resumability marker: a partial download is re-attempted
  on the next run; a complete one is skipped.
- `_obsolete/` and `testbench/` subdirs (gitignored) hold scratch/old versions — ignore them.

## Repo layout

```
main.py            orchestrator (get_index.py + fetch_p3+.py; forwards only -start)
get_index.py       day index → SQLite + HTML cache
fetch_pdfs.py      Part I/II PDFs (persistent)
fetch_p3+.py       Parts III–VII PDFs (ephemeral, ~10 days)
concat_pages.py    merge per-page PDFs into single-document PDFs
mof-convert-txt.py one-off PDF→markdown experiment
utils/common.py    shared helpers, constants, session factory
toolbench/         maintenance one-offs (e.g. cleanup-p3folder.py)
docs/              backlog.md / activity-log.md
data/              gitignored: mo.db, html_cache/, PI/ PII/ PIII/ … PVII/, text/
```

## Roadmap

- [x] local cache
    - [x] fetch daily părți
    - [x] download pdfs
    - [x] fetch P-III - P-VII (online for 10 days)
        - [ ] bypass rate limiting, rotating proxies or VPN
        - [x] fetch individual pages
        - [x] fetch jsonp's
        - [x] concatenate pdfs  (`concat_pages.py`)
            - [ ] OCR needed pages

- [ ] structured text/html from PDF
    - [ ] PDF → HTML see [pdf2txt.xslx](https://docs.google.com/spreadsheets/d/1APEmulzWa7PGgDg_mc-7rnY_vbxX2Q6Y) 
    - [ ] split into chapters → initial UI 
    - [ ] NLP, detect entities
- [ ] UI 
- [ ] updater cron
- [ ] notifications
- [ ] annotations, relative links

## Proiecte similare

[ciocan/monitorul-ii](https://github.com/ciocan/monitorul-ii), [Ansvar-Systems/Romanian-law-mcp](https://github.com/Ansvar-Systems/Romanian-law-mcp), [v-khdumi/MonitorulOficialPDF](https://github.com/v-khdumi/MonitorulOficialPDF)

vezi și:

| proiect | obs | price |
|-----|-----|-----|
| [monitoruljuridic.ro](http://www.monitoruljuridic.ro/) | no formatting | gratis |
| [ro-lex.ro](https://www.ro-lex.ro/) |  | gratis |
| [lege-online.ro](https://www.lege-online.ro/monitoare-oficiale) |  |  |
| [lege5.ro](https://lege5.ro/App/MonitorOficial) | formatted, linked | paid |
| [idrept.ro](https://lege5.ro/App/MonitorOficial) | formatted, linked | paid |

