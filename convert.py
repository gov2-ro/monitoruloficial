"""
Convert downloaded MO PDFs to Markdown using pdftotext (poppler).

Outputs a sibling .md file next to each source PDF (same dir, same basename).
Flat sections (PI, PII, PIM, PV) — layout: data/<Px>/<year>/<name>.pdf
Deep sections (PIII, PIV, PVI, PVII) — layout: data/<Px>/<year>/<date>/<name>.pdf
  (deep sections require concat_pages.py to have been run first)

Usage (from repo root):
    python convert.py                          # all sections, skip existing
    python convert.py -s PV                    # smoke test (12 PDFs)
    python convert.py -s PI PII PIM PV         # flat sections only
    python convert.py -s PIII PIV PVI PVII     # after concat_pages.py
    python convert.py --overwrite              # force reconvert
    python convert.py --dry-run                # preview counts only
    python convert.py -w 4 --debug
"""

import argparse
import logging
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

sys.path.append("utils/")
from common import DATA_ROOT, setup_logging

FLAT_PARTS = {"PI", "PII", "PIM", "PV"}
DEEP_PARTS = {"PIII", "PIV", "PVI", "PVII"}
ALL_PARTS  = sorted(FLAT_PARTS | DEEP_PARTS)

_FNAME_RE = re.compile(r'Monitorul-Oficial--(\w+)--(\w+)--(\d{4})\.pdf$', re.IGNORECASE)
_DATE_RE  = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# pdftotext strips hyphenation automatically; page separator for LLM chunking
_PAGE_SEP = '\n\n---\n\n'

# Running header pattern (both Â and A variants appear in older issues)
_HEADER_RE = re.compile(r'^MONITORUL OFICIAL AL ROM[ÂA]NIEI[^\n]*\n', re.MULTILINE)
# Leading page number line (1–4 digits on its own line at the start of a page block)
_PAGENUM_RE = re.compile(r'^\d{1,4}\n')
# ISSN/barcode artifact (last page) — "ISSN 1453-4495" or similar trailing line
_ISSN_RE = re.compile(r'\nISSN\s+\d[\d\s\-]+$', re.IGNORECASE)


def parse_filename(pdf_path: Path) -> dict | None:
    m = _FNAME_RE.search(pdf_path.name)
    if not m:
        return None
    part, number, year = m.group(1), m.group(2), int(m.group(3))
    is_bis = number.lower().endswith('bis')
    clean_number = re.sub(r'[Bb]is$', '', number)

    # For deep sections the grandparent dir is the date (YYYY-MM-DD)
    date = None
    grandparent = pdf_path.parent.name
    if _DATE_RE.match(grandparent):
        date = grandparent

    return {
        'part': part,
        'number': clean_number,
        'year': year,
        'is_bis': is_bis,
        'date': date,
    }


def find_pdfs(root: Path, sections: list[str]) -> list[Path]:
    results = []
    for section in sections:
        section_path = root / section
        if not section_path.is_dir():
            logging.warning(f'{section}: directory not found — skipping')
            continue

        if section in FLAT_PARTS:
            # data/<Px>/<year>/<name>.pdf
            pdfs = [
                p for p in section_path.glob('*/*.pdf')
                if p.name.startswith('Monitorul-Oficial--')
            ]
        else:
            # merged docs: data/<Px>/<year>/<date>/<name>.pdf  (3 levels deep)
            # page-level files are one more level down: …/<name>/<N>.pdf — excluded
            pdfs = [
                p for p in section_path.glob('*/*/*.pdf')
                if p.name.startswith('Monitorul-Oficial--')
            ]
            if not pdfs:
                done_count = sum(1 for _ in section_path.glob('*/*/*/*.done'))
                logging.warning(
                    f'{section}: 0 merged PDFs — run concat_pages.py first '
                    f'({done_count} .done markers found)'
                )

        logging.debug(f'{section}: {len(pdfs)} PDFs')
        results.extend(pdfs)
    return results


def clean_text(raw: str) -> str:
    pages = raw.split('\x0c')
    cleaned = []
    for page in pages:
        # strip leading page-number line
        page = _PAGENUM_RE.sub('', page, count=1)
        # strip running header
        page = _HEADER_RE.sub('', page)
        # strip trailing whitespace per line
        lines = [line.rstrip() for line in page.splitlines()]
        page = '\n'.join(lines).strip()
        if page:
            cleaned.append(page)

    text = _PAGE_SEP.join(cleaned)
    # strip ISSN/barcode artifact at the end
    text = _ISSN_RE.sub('', text)
    # collapse 3+ consecutive blank lines → 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def make_frontmatter(meta: dict) -> str:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    date_val = f'"{meta["date"]}"' if meta['date'] else 'null'
    number = meta['number']
    return (
        '---\n'
        f'source: monitoruloficial.ro\n'
        f'part: {meta["part"]}\n'
        f'number: "{number}"\n'
        f'year: {meta["year"]}\n'
        f'date: {date_val}\n'
        f'is_bis: {"true" if meta["is_bis"] else "false"}\n'
        f'converter: pdftotext\n'
        f'converted_at: {now}\n'
        '---\n\n'
    )


def convert_one(pdf_path: Path, overwrite: bool, dry_run: bool) -> tuple[str, bool]:
    """Convert one PDF to Markdown. Returns (status, success)."""
    md_path = pdf_path.with_suffix('.md')

    if not overwrite and md_path.exists():
        return ('exists', True)

    meta = parse_filename(pdf_path)
    if meta is None:
        tqdm.write(f'WARN: Cannot parse filename: {pdf_path.name} — skipping')
        return ('skipped', False)

    if dry_run:
        return ('would_convert', True)

    try:
        result = subprocess.run(
            ['pdftotext', '-enc', 'UTF-8', str(pdf_path), '-'],
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            tqdm.write(f'WARN: pdftotext failed ({result.returncode}): {pdf_path.name}')
            return ('failed', False)

        raw = result.stdout.decode('utf-8', errors='replace')
        text = clean_text(raw)
        frontmatter = make_frontmatter(meta)
        md_path.write_text(frontmatter + text, encoding='utf-8')
        logging.debug(f'Converted: {pdf_path.name}')
        return ('converted', True)

    except subprocess.TimeoutExpired:
        tqdm.write(f'ERROR: Timeout (300s): {pdf_path.name}')
        if md_path.exists():
            md_path.unlink()
        return ('failed', False)
    except Exception as e:
        tqdm.write(f'ERROR: {pdf_path.name}: {e}')
        if md_path.exists():
            md_path.unlink()
        return ('failed', False)


def main():
    parser = argparse.ArgumentParser(description='Convert MO PDFs → Markdown via pdftotext')
    parser.add_argument('-s', '--sections', nargs='+', choices=ALL_PARTS, default=ALL_PARTS,
                        metavar='SECTION',
                        help=f'sections to convert (default: all): {" ".join(ALL_PARTS)}')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, default=False,
                        help='reconvert PDFs that already have a .md sibling')
    parser.add_argument('--dry-run', action='store_true',
                        help='print what would be converted without writing')
    parser.add_argument('-w', '--workers', type=int, default=min(8, os.cpu_count() or 4),
                        help='parallel workers (default: min(8, cpu_count))')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug)

    root = Path(DATA_ROOT)
    if not root.is_dir():
        logging.error(f'Data root not found: {root}')
        raise SystemExit(1)

    pdfs = find_pdfs(root, args.sections)
    if not pdfs:
        print('No PDFs found.')
        return

    logging.info(f'{len(pdfs)} PDFs found across sections: {", ".join(args.sections)}')
    if args.dry_run:
        logging.info('Dry-run mode: no files will be written')

    converted = exists = failed = would = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(convert_one, p, args.overwrite, args.dry_run): p for p in pdfs}
        with tqdm(as_completed(futures), total=len(futures), desc='convert', unit='pdf') as bar:
            for fut in bar:
                status, _ = fut.result()
                if status == 'converted':
                    converted += 1
                elif status == 'exists':
                    exists += 1
                elif status == 'would_convert':
                    would += 1
                else:
                    failed += 1

    if args.dry_run:
        print(f'Dry-run: {would} would convert  {exists} already exist  {failed} would skip/fail')
    else:
        print(f'Done: {converted} converted  {exists} already existed  {failed} failed')

    if sys.platform == 'darwin':
        total = converted or would
        os.system(f'say -v ioana "convert gata, {total} fișiere" -r 250')


if __name__ == '__main__':
    main()
