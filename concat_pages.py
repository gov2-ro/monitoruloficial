"""
Merge per-page PDFs produced by fetch_p3+.py into single-document PDFs.

Input layout:  data/<Px>/<year>/<date>/<name>/<N>.pdf   (individual pages)
               data/<Px>/<year>/<date>/<name>/<name>.done  (completion marker with page count)
Output:        data/<Px>/<year>/<date>/<name>.pdf

Only merges documents where the .done marker exists and all pages pass the PDF
magic-byte check. Incomplete or in-progress document directories are skipped with
a warning.

Usage (from repo root):
    python concat_pages.py [--dry-run] [--overwrite] [--debug] [root]

    root        data root to scan (default: data/)
    --dry-run   print what would be merged without writing anything
    --overwrite re-merge even if the output file already exists
    --debug     verbose logging
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.append("utils/")
from common import is_pdf, setup_logging, DATA_ROOT

try:
    from pypdf import PdfWriter, PdfReader
except ImportError:
    print("pypdf not installed. Run: pip install pypdf", file=sys.stderr)
    raise SystemExit(1)


def _read_done(done_path: Path) -> int | None:
    """Return page count from .done file, or None if missing/invalid."""
    try:
        return int(done_path.read_text().strip())
    except (ValueError, OSError):
        return None


def _all_pages_valid(doc_dir: Path, page_count: int) -> list[Path] | None:
    """Return sorted page paths if all pages exist and are valid PDFs, else None."""
    pages = []
    for i in range(1, page_count + 1):
        p = doc_dir / f'{i}.pdf'
        if not p.is_file():
            return None
        try:
            with open(p, 'rb') as f:
                if not is_pdf(f.read(5)):
                    return None
        except OSError:
            return None
        pages.append(p)
    return pages


def concat_doc(page_paths: list[Path], output_path: Path, dry_run: bool) -> bool:
    """Merge page_paths (already sorted) into output_path. Returns True on success."""
    if dry_run:
        logging.info(f'[dry-run] Would merge {len(page_paths)} pages → {output_path}')
        return True
    try:
        writer = PdfWriter()
        for p in page_paths:
            reader = PdfReader(str(p))
            for page in reader.pages:
                writer.add_page(page)
        with open(output_path, 'wb') as f:
            writer.write(f)
        logging.info(f'Merged {len(page_paths)} pages → {output_path}')
        return True
    except Exception as e:
        logging.error(f'Failed to merge {output_path}: {e}')
        return False


def _raw_dest(doc_dir: Path, root: Path) -> Path:
    """Return the _raw mirror path for doc_dir.

    data/PIII/2025/2025-01-03/Monitorul-...  →  data/PIII_raw/2025/2025-01-03/Monitorul-...
    """
    rel = doc_dir.relative_to(root)
    part = rel.parts[0]
    return root / (part + '_raw') / Path(*rel.parts[1:])


def find_doc_dirs(root: Path):
    """Yield all doc directories that contain a .done marker."""
    # Structure: <root>/<Px>/<year>/<date>/<docname>/
    for part_dir in sorted(root.iterdir()):
        if not part_dir.is_dir() or part_dir.name.startswith('.'):
            continue
        if part_dir.name.endswith('_raw'):
            continue
        for year_dir in sorted(part_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for date_dir in sorted(year_dir.iterdir()):
                if not date_dir.is_dir():
                    continue
                for doc_dir in sorted(date_dir.iterdir()):
                    if not doc_dir.is_dir():
                        continue
                    done_path = doc_dir / (doc_dir.name + '.done')
                    if done_path.is_file():
                        yield doc_dir, done_path


def main():
    parser = argparse.ArgumentParser(description='Concatenate per-page PDFs into document PDFs')
    parser.add_argument('root', nargs='?', default=DATA_ROOT,
                        help=f'data root to scan (default: {DATA_ROOT})')
    parser.add_argument('--dry-run',   action='store_true', help='print actions without writing')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, default=False,
                        help='re-merge even if output already exists')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug)

    root = Path(args.root)
    if not root.is_dir():
        logging.error(f'Root directory not found: {root}')
        raise SystemExit(1)

    doc_dirs = list(find_doc_dirs(root))
    logging.info(f'Found {len(doc_dirs)} candidate document directories')

    merged = skipped = failed = 0

    for doc_dir, done_path in tqdm(doc_dirs, desc='docs'):
        page_count = _read_done(done_path)
        if page_count is None:
            logging.warning(f'Unreadable .done in {doc_dir} — skipping')
            continue
        if page_count == 0:
            logging.warning(f'{doc_dir.name}: .done says 0 pages — run toolbench/backfill_done.py first')
            failed += 1
            continue

        # Output is one level up from the doc dir, same name + .pdf
        output_path = doc_dir.parent / (doc_dir.name + '.pdf')

        if not args.overwrite and output_path.is_file():
            # Skip only when output is newer than the most recently touched page file
            newest_page_mtime = max(
                (doc_dir / f'{i}.pdf').stat().st_mtime
                for i in range(1, page_count + 1)
                if (doc_dir / f'{i}.pdf').is_file()
            ) if page_count > 0 else 0
            if output_path.stat().st_mtime >= newest_page_mtime:
                logging.debug(f'Up to date, skipping: {output_path}')
                skipped += 1
                continue

        page_paths = _all_pages_valid(doc_dir, page_count)
        if page_paths is None:
            logging.warning(
                f'{doc_dir.name}: .done says {page_count} pages but some are '
                f'missing or invalid — skipping'
            )
            failed += 1
            continue

        if concat_doc(page_paths, output_path, dry_run=args.dry_run):
            merged += 1
            if not args.dry_run:
                raw_dest = _raw_dest(doc_dir, root)
                try:
                    raw_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(doc_dir), str(raw_dest))
                    logging.debug(f'Moved source → {raw_dest}')
                except Exception as e:
                    logging.warning(f'Move to _raw failed for {doc_dir.name}: {e}')
        else:
            failed += 1

    label = '[dry-run] Would merge' if args.dry_run else 'Merged'
    print(f'{label}: {merged}  skipped: {skipped}  failed: {failed}')


if __name__ == '__main__':
    main()
