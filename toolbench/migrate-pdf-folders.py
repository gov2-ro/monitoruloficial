"""
Migrate PDFs from old flat/tmp structure to per-part year-organised folders.

Phase 1 (already done):
  data/pdfs/<year>/<file>.pdf        → data/<part>/<year>/<file>.pdf

Phase 2 (this run):
  data/<part>/tmp/<date>/<name>/     → data/<part>/<year>/<date>/<name>/
  where <year> is extracted from <name> (last segment after '--')

Run with --dry-run first to preview, then without to execute.
"""

import os, re, sys, argparse
from pathlib import Path

DATA_ROOT = Path('data')
EPHEMERAL_PARTS = ['PIII', 'PIV', 'PVI', 'PVII']

parser = argparse.ArgumentParser()
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
dry = args.dry_run

def year_from_name(name):
    m = re.search(r'--(\d{4})$', name)
    return m.group(1) if m else None

moved = skipped = warned = 0

for part in EPHEMERAL_PARTS:
    tmp_dir = DATA_ROOT / part / 'tmp'
    if not tmp_dir.exists():
        print(f'{tmp_dir}: not found, skipping')
        continue
    date_dirs = sorted(tmp_dir.iterdir())
    print(f'{tmp_dir}: {len(date_dirs)} date dirs')
    for date_dir in date_dirs:
        if not date_dir.is_dir():
            continue
        for doc_dir in sorted(date_dir.iterdir()):
            if not doc_dir.is_dir():
                continue
            year = year_from_name(doc_dir.name)
            if not year:
                print(f'  WARN no year in: {doc_dir.name}')
                warned += 1
                continue
            dest = DATA_ROOT / part / year / date_dir.name / doc_dir.name
            if dest.exists():
                skipped += 1
                continue
            if not dry:
                dest.parent.mkdir(parents=True, exist_ok=True)
                doc_dir.rename(dest)
            moved += 1

suffix = ' [DRY RUN]' if dry else ''
print(f'\n{"Would move" if dry else "Moved"}: {moved}  Skipped: {skipped}  Warnings: {warned}{suffix}')

if not dry:
    # Remove now-empty tmp/<date>/ dirs and tmp/ itself
    removed = 0
    for part in EPHEMERAL_PARTS:
        tmp_dir = DATA_ROOT / part / 'tmp'
        if not tmp_dir.exists():
            continue
        for d in sorted(tmp_dir.iterdir()):
            try:
                d.rmdir()
                removed += 1
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
            removed += 1
        except OSError:
            remaining = list(tmp_dir.iterdir())
            print(f'  NOTE {tmp_dir} not empty: {len(remaining)} items remain')
    print(f'Removed {removed} now-empty dirs')
