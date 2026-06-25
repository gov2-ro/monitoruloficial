# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this is

A scraper for **monitoruloficial.ro/e-monitor** (Romania's Official Gazette): fetch the
daily index of *părți* (gazette parts) → download the part PDFs → (eventually) convert to
structured text. See `readme.md` for the roadmap and the list of similar projects.

This repo was extracted from a larger monorepo into a standalone repo. The active scripts
were updated for that (`sys.path` and data paths are now repo-root–relative — see below),
but two helper scripts still point at the old layout (see **Known stale paths**).

## Run from the repo root

All scripts use **cwd-relative paths** — `sys.path.append("utils/")` for the shared module
and `data/...` for the DB/cache. So always run them from the repo root; do **not** `cd` into
a subdirectory first. `main.py` shells out with `subprocess`, inheriting that cwd.

```bash
python main.py                   # orchestrator: get_index.py then fetch_p3+.py, last 2 weeks
python main.py -start 2024-01-01 # ...from a given date (only -start is forwarded, to both)

python get_index.py              # fetch daily parts index → SQLite + HTML cache (last 15 days)
python get_index.py -start 2024-01-01 -end 2024-03-01
python get_index.py -m all       # from each script's hardcoded start through today

python fetch_p3+.py              # download ephemeral Parts III–VII (online only ~10 days)
python fetch_pdfs.py             # download persistent Part I/II PDFs (no CLI args — see below)
python mof-convert-txt.py        # experimental PyPDF2 PDF→markdown (stale paths; see below)
```

Dependencies (no requirements file — install manually): `requests`, `beautifulsoup4`,
`tqdm`, `urllib3`, `PyPDF2`. Python 3.

## Layout

```
main.py            orchestrator (get_index.py + fetch_p3+.py; forwards only -start)
get_index.py       day index → SQLite + HTML cache
fetch_pdfs.py      Part I/II PDFs (persistent)
fetch_p3+.py       Parts III–VII PDFs (ephemeral, ~10 days)
mof-convert-txt.py one-off PDF→markdown experiment
utils/common.py    shared helpers (imported as `from common import ...`)
toolbench/         maintenance one-offs (e.g. cleanup-p3folder.py)
docs/              (empty)
data/              gitignored: mo.db, html_cache/, pdfs/, text/
```

`utils/common.py` provides: `generate_dates(start, end, format)` (weekday-only date list),
`base_headers(which)` (`'headers1'` for AJAX/POST, `'headers2'` for document GETs — both carry
a hardcoded `PHPSESSID` cookie), and `readfile`/`writefile` (encoding-tolerant I/O).

## Data model

SQLite `data/mo.db`, table `dates_lists`: `date TEXT PRIMARY KEY`, `json TEXT`. The JSON maps
each section name (e.g. `"Partea I"`) → `{ part-number: href }`. `get_index.py` also writes a
prettified HTML snapshot per day to `data/html_cache/<date>.html`.

PDFs land under `data/pdfs/<year>/` (Part I/II) and `data/pdfs/_p3+/<year>/`, with
`fetch_p3+.py` staging per-page downloads in `data/pdfs/_p3+/tmp/<date>/<filename>/`.

## How the scrapers work

- **get_index.py** — POSTs `{today, rand}` to `.../emonitor/get_mo.php` per weekday, parses the
  returned HTML (`div.card-body` → `ol.breadcrumb` section name + `a.btn` links), upserts one
  row per day. Skips days already in the DB unless `--overwrite`.
- **fetch_pdfs.py** — reads every DB row, downloads parts that are **not** ephemeral (Part I/II
  etc.) into `data/pdfs/<year>/`, skipping files that already exist. **No argparse**: configure
  via the variables at the top of the file; it always processes all rows newest-first.
- **fetch_p3+.py** — only the ephemeral `shy_parts` = `["III-a","IV-a","VI-a","VII-a"]`.
  Multi-step per part: scrape `var fid` from the part page → POST `gidf.php` for page count +
  folder → download each page as a separate PDF plus a jsonp into the `tmp/` staging tree.
  Page PDFs are **not yet concatenated** (roadmap item). Anti-ban: paces every request with
  random sleeps, retries at most once (retry bursts keep the server's IP ban hot), and aborts
  after 2 consecutive network failures.

`shy_parts` is the contract between the two PDF scrapers: `fetch_pdfs.py` skips those parts,
`fetch_p3+.py` fetches only them.

## Argparse is per-script, not uniform

- `get_index.py`: `-start` `-end` `--overwrite` `-m/--mode`
- `fetch_p3+.py`: `-start` `-end` `-days` `--overwrite` `-m/--mode`
- `fetch_pdfs.py`: none (top-of-file config only)
- `main.py`: `-start` only

For scripts/sections without argparse, edit the config variables at the top of the file rather
than adding flags.

## Conventions & gotchas

- Rate limiting everywhere: random sleeps between requests + a longer pause every N items.
- `urllib3.disable_warnings(...)` + `verify=False` throughout — the site has SSL issues.
- `get_index.py` and `fetch_p3+.py` end with `os.system('say -v ioana ...')` — a **macOS-only**
  spoken "done" announcement. Harmless but noisy; silently no-ops elsewhere.
- `_obsolete/` and `testbench/` subdirs (gitignored) hold scratch/old versions — ignore them.

## Known stale paths (post-move leftovers)

These two still hardcode the old monorepo layout `../../data/mo/` and will fail as-is from the
repo root. The active data dir is now `data/`. Fix the paths before running, or when convenient:

- `mof-convert-txt.py:94` — `rootFolder = '../../data/mo/'`
- `toolbench/cleanup-p3folder.py:5-6` — `'../../data/mo/pdfs/_p3+/tmp/'`, `'../../data/mo/mo.db'`

## Persona
- Act as a senior full-stack developer with deep expertise
- Challenge assumptions and suggest optimizations
- Run code to verify functionality. Limit categories or products processed (~10 categories, ~20 products) while testing. While testing, use a timout of 3 minutes for each script or command to prevent indefinite runs.
- Provide relevant output messages and logging.
- Implement debug mode with verbose logging via config flag
- Keep answers concise and to the point.
- Don’t just agree with me — feel free to challenge my assumptions or offer a different perspective.
- If a question or request is ambiguous or would benefit from clarification, ask follow-up questions before proceeding.


## General Coding Principles
1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements. When running unattended, pick the most reasonable interpretation, proceed, and record the assumption rather than blocking.
2. Implement the simplest solution for simple problems, better solutions for harder problems. Do not over-engineer or add flexibility that isn't needed yet. 
3. Don't touch unrelated code but please do surface bad code or design smells you discover with me so we can address them as a separate issue.
4. Flag uncertainty explicitly. If you're unsure about something, see point 1 above. If it makes sense to do so, conduct a small, localised and low-risk experiment and bring the hypothesis and results to me to discuss. Confidence without certainty causes more damage than admitting a gap.
5. I'm always open to ideas on better ways to do things. Please don't hesitate to suggest a better way, or one that has long lasting impact over a tactical change. (as a few examples)

**Always update the `readme.md` file with any changes, especially if they affect usage, configuration, workflow, or architecture.** Read relevant documentation (readme, site specific readme, data astructure, config) each 10 steps to keep your memory fresh.

## Project tracking

- When detecting things that need to be addressed later, add to `docs/backlog.md` under the relevant section (Retail / Gas / General). Use a checkbox `- [ ]` entry with a clear title and enough context to act on it later.
- After completing any meaningful work, add an entry to `docs/activity-log.md` under the relevant section heading with a `### YYYY-MM-DD — Short Title` entry. Include what was done, why, and any non-obvious decisions.