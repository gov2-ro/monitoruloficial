# monitoruloficial.ro — Official Gazette scraper

scrape [monitoruloficial.ro/e-monitor](https://monitoruloficial.ro/e-monitor/) → save pdfs → get text → make nice / explorable.

This repo was extracted from a larger monorepo into a standalone repo. Everything is now
repo-root–relative, so **always run scripts from the repo root** (not from a subdirectory):
imports (`sys.path.append("utils/")`) and data paths (`data/...`) depend on it.

## Usage

```bash
python main.py                   # orchestrator: get_index.py then fetch_p3+.py, last 2 weeks
python main.py -start 2024-01-01 # ...from a given date (only -start is forwarded, to both)

python get_index.py              # fetch daily parts index → SQLite + HTML cache (last 15 days)
python get_index.py -start 2024-01-01 -end 2024-03-01
python get_index.py -m all       # from each script's hardcoded start through today

python fetch_p3+.py              # download ephemeral Parts III–VII (online only ~10 days)
python fetch_pdfs.py             # download persistent Part I/II PDFs (no CLI args; see below)
python mof-convert-txt.py        # experimental PyPDF2 PDF→markdown conversion
```

Dependencies (no requirements file — install manually): `requests`, `beautifulsoup4`, `tqdm`,
`urllib3`, `PyPDF2`. Python 3.

CLI flags are **per-script, not uniform**:

| script | flags |
|---|---|
| `get_index.py` | `-start` `-end` `--overwrite` `-m/--mode` |
| `fetch_p3+.py` | `-start` `-end` `-days` `--overwrite` `-m/--mode` |
| `fetch_pdfs.py` | none — edit the config variables at the top of the file |
| `main.py` | `-start` only |

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
- `generate_dates(start, end, format)` — weekday-only date list
- `base_headers(which)` — pre-built headers (`'headers1'` for AJAX/POST, `'headers2'` for document
  GETs); both carry a hardcoded `PHPSESSID` cookie
- `readfile(path)` / `writefile(path, content)` — encoding-tolerant file I/O

### Data model

SQLite `data/mo.db`, table `dates_lists`: `date TEXT PRIMARY KEY`, `json TEXT`. The JSON maps each
section name (e.g. `"Partea I"`) → `{ part-number: href }`.

PDFs land under `data/<Px>/<year>/` for all parts. For the ephemeral parts (PIII, PIV, PVI,
PVII), `fetch_p3+.py` stages per-page downloads in `data/<Px>/<year>/<date>/<filename>/` before
concatenation (roadmap). `<Px>` is one of `PI`, `PII`, `PIII`, `PIV`, `PV`, `PVI`, `PVII`,
`PIM` (Partea I Maghiară). The whole `data/` dir is gitignored.

### Conventions & gotchas

- Rate limiting everywhere: random sleeps between requests + a longer pause every N items.
- `urllib3.disable_warnings(...)` + `verify=False` throughout — the site has SSL issues.
- `get_index.py` and `fetch_p3+.py` end with `os.system('say -v ioana ...')` — a **macOS-only**
  spoken "done" announcement. Harmless but noisy; silently no-ops elsewhere.
- `_obsolete/` and `testbench/` subdirs (gitignored) hold scratch/old versions — ignore them.

## Repo layout

```
main.py            orchestrator (get_index.py + fetch_p3+.py; forwards only -start)
get_index.py       day index → SQLite + HTML cache
fetch_pdfs.py      Part I/II PDFs (persistent)
fetch_p3+.py       Parts III–VII PDFs (ephemeral, ~10 days)
mof-convert-txt.py one-off PDF→markdown experiment
utils/common.py    shared helpers
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
        - [ ] concatenate pdfs
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

[ciocan/monitorul.ai](https://github.com/ciocan/monitorul.ai), [ciocan/monitorul-ii](https://github.com/ciocan/monitorul-ii), [v-khdumi/MonitorulOficialPDF](https://github.com/v-khdumi/MonitorulOficialPDF)

vezi și:

| proiect | obs | price |
|-----|-----|-----|
| [monitoruljuridic.ro](http://www.monitoruljuridic.ro/) | no formatting | gratis |
| [ro-lex.ro](https://www.ro-lex.ro/) |  | gratis |
| [lege-online.ro](https://www.lege-online.ro/monitoare-oficiale) |  |  |
| [lege5.ro](https://lege5.ro/App/MonitorOficial) | formatted, linked | paid |
| [idrept.ro](https://lege5.ro/App/MonitorOficial) | formatted, linked | paid |

