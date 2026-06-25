"""
Quick dashboard for MO cron run history.

Usage:
    python stats.py              # last 20 runs, all scripts
    python stats.py --last 50
    python stats.py --script get_index.py
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'utils'))
from common import DB_PATH

STATUS_ICON = {'ok': '✓', 'partial': '~', 'error': '✗', None: '?'}


def fmt_stats(raw: str | None) -> str:
    if not raw:
        return ''
    try:
        d = json.loads(raw)
        return '  '.join(f'{k}={v}' for k, v in d.items())
    except (json.JSONDecodeError, TypeError):
        return raw


def fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return '—'
    if seconds < 60:
        return f'{seconds:.1f}s'
    return f'{seconds/60:.1f}m'


def main():
    parser = argparse.ArgumentParser(description='Show MO cron run history')
    parser.add_argument('--last', type=int, default=20, metavar='N', help='rows to show (default: 20)')
    parser.add_argument('--script', default=None, help='filter by script name')
    args = parser.parse_args()

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f'Cannot open DB: {e}', file=sys.stderr)
        raise SystemExit(1)

    if args.script:
        rows = conn.execute(
            'SELECT * FROM runs WHERE script=? ORDER BY started_at DESC LIMIT ?',
            (args.script, args.last),
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM runs ORDER BY started_at DESC LIMIT ?',
            (args.last,),
        ).fetchall()
    conn.close()

    if not rows:
        print('No runs recorded yet.')
        return

    col_script  = max(len(r['script']) for r in rows)
    col_started = 19  # "YYYY-MM-DDTHH:MM:SS"

    header = (
        f"{'Script':<{col_script}}  {'Started':<{col_started}}  "
        f"{'Dur':>6}  {'St':2}  Stats"
    )
    print(header)
    print('-' * (len(header) + 20))

    for r in rows:
        icon   = STATUS_ICON.get(r['status'], '?')
        started = (r['started_at'] or '').replace('T', ' ')
        print(
            f"{r['script']:<{col_script}}  {started:<{col_started}}  "
            f"{fmt_dur(r['duration_s']):>6}  {icon:<2}  {fmt_stats(r['stats'])}"
        )


if __name__ == '__main__':
    main()
