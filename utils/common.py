import datetime
import json
import logging
import logging.handlers
import sqlite3
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Canonical constants ──────────────────────────────────────────────────────
# Anchored to repo root via __file__ so cron/VPS invocations work regardless of cwd.
_REPO      = Path(__file__).resolve().parent.parent
DATA_ROOT  = str(_REPO / 'data') + '/'
DB_PATH    = str(_REPO / 'data' / 'mo.db')
HTML_CACHE = str(_REPO / 'data' / 'html_cache') + '/'
LOG_DIR    = _REPO / 'data' / 'logs'
LOG_PATH   = str(LOG_DIR / 'mof.log')

URL_BASE   = 'https://monitoruloficial.ro'
URL_GET_MO = URL_BASE + '/ramo_customs/emonitor/get_mo.php'
URL_GIDF   = URL_BASE + '/ramo_customs/emonitor/gidf.php'
URL_VIEW   = URL_BASE + '/ramo_customs/emonitor/showmo/services/view.php'

PART_FOLDER = {
    "Partea I":          "PI",
    "Partea I Maghiară": "PIM",
    "Partea a II-a":     "PII",
    "Partea a III-a":    "PIII",
    "Partea a IV-a":     "PIV",
    "Partea a V-a":      "PV",
    "Partea a VI-a":     "PVI",
    "Partea a VII-a":    "PVII",
}

# Parts that are ephemeral (~10 days online); fetched by fetch_p3+.py, skipped by fetch_pdfs.py
SHY_PARTS = ["III-a", "IV-a", "VI-a", "VII-a"]

TABLE_NAME = 'dates_lists'

# Pacing: random sleep (min, max) seconds
PACE      = (1.5, 3.0)   # between document requests
PACE_PAGE = (0.6, 1.2)   # between page PDFs of the same document


def section_dir(sectiune: str) -> str:
    """Map a section name to its output folder code (e.g. 'Partea a III-a' → 'PIII').

    Tries exact match first, then substring match, so both full-name keys and
    shy-part substrings are handled by one function.
    """
    if sectiune in PART_FOLDER:
        return PART_FOLDER[sectiune]
    for key, folder in PART_FOLDER.items():
        if key in sectiune:
            return folder
    return "P_unknown"


def parse_date(value, fmt: str = '%Y-%m-%d') -> datetime.datetime:
    """Return value as datetime; parse from string if needed."""
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.strptime(value, fmt)


def make_session() -> requests.Session:
    """Session with a SINGLE retry on connection errors.

    The server IP-bans aggressive clients, so a retry burst keeps the ban hot —
    fail fast and rely on per-request pacing to stay under the rate limit.
    """
    s = requests.Session()
    retry = Retry(
        total=1, connect=1, read=1,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(['GET', 'POST']),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s


def is_pdf(content: bytes) -> bool:
    return content[:5] == b'%PDF-'


def pdf_ok(resp) -> bool:
    """True only when a response carries a real PDF body."""
    return resp.status_code == 200 and bool(resp.content) and is_pdf(resp.content)


def setup_logging(debug: bool = False, logfile: str = None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.StreamHandler()]
    if logfile:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rh = logging.handlers.RotatingFileHandler(
            logfile, maxBytes=5 * 1024 * 1024, backupCount=10, encoding='utf-8'
        )
        handlers.append(rh)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True,
    )


# ── Run tracking (writes to runs table in mo.db) ─────────────────────────────

def init_runs_table(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            script      TEXT    NOT NULL,
            started_at  TEXT    NOT NULL,
            finished_at TEXT,
            duration_s  REAL,
            status      TEXT,
            stats       TEXT
        )
    ''')
    conn.commit()


def log_run_start(conn: sqlite3.Connection, script: str) -> int:
    cur = conn.execute(
        'INSERT INTO runs (script, started_at) VALUES (?, ?)',
        (script, datetime.datetime.now().isoformat(timespec='seconds')),
    )
    conn.commit()
    return cur.lastrowid


def log_run_end(conn: sqlite3.Connection, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        'UPDATE runs SET finished_at=?, duration_s=?, status=?, stats=? WHERE id=?',
        (
            datetime.datetime.now().isoformat(timespec='seconds'),
            _run_duration(conn, run_id),
            status,
            json.dumps(stats, ensure_ascii=False),
            run_id,
        ),
    )
    conn.commit()


def _run_duration(conn: sqlite3.Connection, run_id: int) -> float:
    row = conn.execute('SELECT started_at FROM runs WHERE id=?', (run_id,)).fetchone()
    if not row:
        return 0.0
    try:
        started = datetime.datetime.fromisoformat(row[0])
        return round((datetime.datetime.now() - started).total_seconds(), 2)
    except ValueError:
        return 0.0


def base_headers(which: str = 'headers1') -> dict:
    """Pre-built request headers. PHPSESSID cookies removed (stale/unused)."""
    headers = {
        "headers1": {
            'authority': 'monitoruloficial.ro',
            'accept': '*/*',
            'accept-language': 'en-GB,en;q=0.5',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://monitoruloficial.ro',
            'referer': 'https://monitoruloficial.ro/e-monitor/',
            'sec-ch-ua': '"Chromium";v="112", "Brave";v="112", "Not:A-Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sec-gpc': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        },
        "headers2": {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/111.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'origin': 'https://monitoruloficial.ro',
            'Referer': 'https://monitoruloficial.ro/e-monitor/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'TE': 'trailers',
        },
    }
    return headers.get(which, headers['headers1'])


def generate_dates(start_date, end_date, format: str = '%d.%m.%Y') -> list:
    def is_weekend(date):
        return date.weekday() in [5, 6]

    return [
        (start_date + datetime.timedelta(days=x)).strftime(format)
        for x in range((end_date - start_date).days + 1)
        if not is_weekend(start_date + datetime.timedelta(days=x))
    ]


def readfile(path: str) -> str:
    for encoding in ['utf-8', 'ISO-8859-1', 'cp1252']:
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue


def writefile(path: str, content: str) -> None:
    with open(path, 'w') as f:
        f.write(content)
