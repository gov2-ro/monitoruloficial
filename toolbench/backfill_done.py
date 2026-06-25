"""
Backfill missing or zero-count .done markers for deep-section doc dirs.

fetch_p3+.py writes <docname>.done only when page_count > 0; if the API
returned p=0 (or the script ran before .done logic existed), the marker is
absent or contains "0" even though all page PDFs are present.

This script walks PIII / PIV / PVI / PVII, finds every doc dir whose .done
is missing or zero, counts the actual numeric PDF files, validates them, and
writes the correct count.  Safe to re-run; only touches dirs that need fixing.

Usage (from repo root):
    python toolbench/backfill_done.py
    python toolbench/backfill_done.py --dry-run
    python toolbench/backfill_done.py --debug
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.append("utils/")
from common import DATA_ROOT, is_pdf, setup_logging

DEEP_PARTS = ["PIII", "PIV", "PVI", "PVII"]


def _page_files(doc_dir: Path) -> list[Path]:
    """Return sorted list of numeric-named PDFs in doc_dir."""
    pages = []
    for f in doc_dir.iterdir():
        if f.suffix == '.pdf' and f.stem.isdigit():
            pages.append(f)
    return sorted(pages, key=lambda p: int(p.stem))


def _all_valid(pages: list[Path]) -> bool:
    for p in pages:
        try:
            with open(p, 'rb') as f:
                if not is_pdf(f.read(5)):
                    return False
        except OSError:
            return False
    return True


def _needs_backfill(doc_dir: Path) -> bool:
    done_path = doc_dir / (doc_dir.name + '.done')
    if not done_path.exists():
        return True
    try:
        return int(done_path.read_text().strip()) == 0
    except (ValueError, OSError):
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Backfill missing/zero .done markers for deep-section doc dirs'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be written without writing')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug)

    root = Path(DATA_ROOT)
    written = skipped = invalid = already_ok = 0

    for section in DEEP_PARTS:
        section_path = root / section
        if not section_path.is_dir():
            logging.debug(f'{section}: not found, skipping')
            continue

        # Walk: <section>/<year>/<date>/<docname>/
        for doc_dir in sorted(section_path.glob('*/*/*')):
            if not doc_dir.is_dir():
                continue

            if not _needs_backfill(doc_dir):
                already_ok += 1
                logging.debug(f'OK: {doc_dir.name}')
                continue

            pages = _page_files(doc_dir)
            if not pages:
                logging.warning(f'No numeric PDFs in {doc_dir} — skipping')
                skipped += 1
                continue

            if not _all_valid(pages):
                logging.warning(f'Invalid PDF in {doc_dir} — skipping')
                invalid += 1
                continue

            done_path = doc_dir / (doc_dir.name + '.done')
            count = len(pages)

            if args.dry_run:
                logging.info(f'[dry-run] Would write {done_path.name} = {count} in {doc_dir}')
                written += 1
            else:
                try:
                    done_path.write_text(str(count))
                    logging.debug(f'Wrote {done_path.name} = {count}')
                    written += 1
                except OSError as e:
                    logging.error(f'Failed writing .done for {doc_dir.name}: {e}')
                    invalid += 1

    label = 'Would write' if args.dry_run else 'Written'
    print(f'{label}: {written}  already_ok: {already_ok}  skipped: {skipped}  invalid: {invalid}')


if __name__ == '__main__':
    main()
