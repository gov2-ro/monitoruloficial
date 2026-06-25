import sqlite3, json, sys, os, time, random, re, argparse, logging, urllib3
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from tqdm import tqdm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append("utils/")
from common import (
    base_headers, parse_date, make_session, section_dir,
    is_pdf, pdf_ok, setup_logging,
    DATA_ROOT, DB_PATH, TABLE_NAME, URL_BASE, URL_GIDF, URL_VIEW,
    SHY_PARTS, PACE, PACE_PAGE,
)

"""
Read the day index from SQLite, download ephemeral Parts III–VII PDFs.
Each document is staged as individual page PDFs under data/<Px>/<year>/<date>/<name>/.
A <name>.done file (containing the page count) is written only after all pages succeed;
it is the authoritative completion marker used to skip already-complete documents.
"""


def be_polite(bounds=PACE):
    time.sleep(random.uniform(*bounds))


def main():
    parser = argparse.ArgumentParser(description='Download ephemeral Parts III–VII PDFs')
    parser.add_argument('-start', '--start_date', help='start date YYYY-MM-DD')
    parser.add_argument('-end',   '--end_date',   help='end date YYYY-MM-DD')
    parser.add_argument('-days',  '--days_ago',   help='how many days back from today')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, default=False,
                        help='re-download existing files (--no-overwrite to skip, default)')
    parser.add_argument('-m', '--mode', help='l-<x>: last x days; all: from 2000-01-04')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug)

    start_dt = datetime.today() - timedelta(days=10)
    end_dt   = datetime.today()

    if args.start_date:
        start_dt = parse_date(args.start_date)
    if args.end_date:
        end_dt = parse_date(args.end_date)
    if args.days_ago:
        start_dt = end_dt - timedelta(days=int(args.days_ago))
    if args.mode:
        if args.mode == 'all':
            start_dt = datetime(2000, 1, 4)
            end_dt   = datetime.today()
        elif args.mode.startswith('l-'):
            try:
                start_dt = datetime.today() - timedelta(days=int(args.mode[2:]))
                end_dt   = datetime.today()
            except ValueError:
                logging.error(f'Invalid mode {args.mode!r}. Use l-<number> or all.')
                raise SystemExit(1)

    overwrite            = args.overwrite
    pause_at             = 30    # files between longer pauses
    pause                = 10    # seconds
    timeout              = 30    # seconds per request
    max_consecutive_failures = 2

    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute(
        f'SELECT * FROM {TABLE_NAME} WHERE date BETWEEN ? AND ?',
        (start_dt.strftime('%Y-%m-%d'), end_dt.strftime('%Y-%m-%d')),
    )
    rows = c.fetchall()

    tqdm.write(f' > {len(rows)} days in the DB')
    all_files = 0
    files_found = 0
    consecutive_failures = 0

    session = make_session()

    for row in tqdm(rows, desc='days'):
        date, json_str = row
        try:
            json_dict = json.loads(json_str)
        except json.JSONDecodeError as e:
            logging.error(f'JSON decode error for {date}: {e}')
            continue

        for sectiune, parti in tqdm(json_dict.items(), desc='părți', leave=False):
            if not any(part in sectiune for part in SHY_PARTS):
                continue

            for nr, url in tqdm(parti.items(), desc='pdfs', leave=False):
                filename = os.path.splitext(url[1:])[0]
                urlparts  = filename.split('--')
                year      = urlparts[-1]
                if len(year) != 4:
                    logging.error(f'Unexpected year token {year!r} in URL {url}')
                    continue

                part_out  = os.path.join(DATA_ROOT, section_dir(sectiune), year)
                part_tmp  = os.path.join(DATA_ROOT, section_dir(sectiune), year, date)
                doc_dir   = os.path.join(part_tmp, filename)
                done_path = os.path.join(doc_dir, filename + '.done')

                # ── Ensure year directory exists ─────────────────────────────
                if not os.path.exists(part_out):
                    os.makedirs(part_out)
                    tqdm.write(f'Created {part_out}')

                # ── Early completeness check (no network needed) ─────────────
                # Skip only if .done exists AND every page file is present+valid.
                if not overwrite and os.path.isfile(done_path):
                    try:
                        stored_count = int(open(done_path).read().strip())
                        all_present = all(
                            _page_valid(os.path.join(doc_dir, f'{i}.pdf'))
                            for i in range(1, stored_count + 1)
                        )
                        if all_present:
                            files_found += stored_count
                            logging.debug(f'Complete, skipping: {filename}')
                            continue
                    except (ValueError, OSError):
                        pass  # corrupted .done — fall through and re-download

                logging.debug(f'>> {URL_BASE + url}')

                # ── Request 1: GET part page to extract fid ──────────────────
                be_polite()
                try:
                    response = session.get(URL_BASE + url, headers=base_headers('headers2'),
                                           verify=False, timeout=timeout)
                except Exception as e:
                    logging.error(f'GET {URL_BASE + url}: {e}')
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        tqdm.write(f'Stopping: {consecutive_failures} consecutive failures')
                        conn.close()
                        raise SystemExit(1)
                    continue

                if response.status_code != 200:
                    logging.warning(f'HTTP {response.status_code} for {URL_BASE + url}')
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        tqdm.write(f'Stopping: {consecutive_failures} consecutive failures')
                        conn.close()
                        raise SystemExit(1)
                    continue

                consecutive_failures = 0

                soup     = BeautifulSoup(response.content, 'html.parser')
                fid_value = None
                for script_tag in soup.find_all('script'):
                    if script_tag.string is None:
                        continue
                    try:
                        match = re.search(r"var fid\s*=\s*'(.*)';", script_tag.string)
                    except Exception as e:
                        logging.error(f'Regex error extracting fid: {e}')
                        continue
                    if match:
                        fid_value = match.group(1)
                        break

                if fid_value is None:
                    logging.warning(f'No fid found for {URL_BASE + url} — skipping')
                    continue

                # ── Request 2: POST gidf.php for page count ──────────────────
                data = {'fid': fid_value, 'rand': random.random()}
                be_polite()
                try:
                    response = session.post(URL_GIDF, headers=base_headers('headers1'),
                                            data=data, verify=False, timeout=timeout)
                except Exception as e:
                    logging.error(f'POST gidf (fid={fid_value}): {e}')
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        tqdm.write(f'Stopping: {consecutive_failures} consecutive failures')
                        conn.close()
                        raise SystemExit(1)
                    continue

                if response.status_code != 200:
                    logging.warning(f'gidf HTTP {response.status_code} (fid={fid_value})')
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        tqdm.write(f'Stopping: {consecutive_failures} consecutive failures')
                        conn.close()
                        raise SystemExit(1)
                    continue

                try:
                    gidf_json  = json.loads(response.text)
                    page_count = gidf_json['p']
                except (json.JSONDecodeError, KeyError) as e:
                    logging.error(
                        f'Bad gidf response (fid={fid_value}): {e}; '
                        f'body[:120]={response.text[:120]!r}'
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        tqdm.write(f'Stopping: {consecutive_failures} consecutive failures')
                        conn.close()
                        raise SystemExit(1)
                    continue

                consecutive_failures = 0

                os.makedirs(doc_dir, exist_ok=True)

                # ── Request 3: GET jsonp metadata ────────────────────────────
                ziurl_jsonp = (
                    f"{URL_VIEW}?doc={gidf_json['d']}&format=jsonp"
                    f"&subfolder={gidf_json['f']}&page=10"
                )
                be_polite()
                try:
                    response = session.get(ziurl_jsonp, headers=base_headers('headers2'),
                                           verify=False, timeout=timeout)
                except Exception as e:
                    logging.error(f'GET jsonp {ziurl_jsonp}: {e}')
                    continue

                if response.status_code == 200 and response.content:
                    json_path = os.path.join(doc_dir, filename + '.json')
                    try:
                        with open(json_path, 'wb') as f:
                            f.write(response.content)
                        logging.debug(f'Saved jsonp: {json_path}')
                    except Exception as e:
                        logging.error(f'Error saving jsonp: {e}')
                else:
                    logging.warning(
                        f'Bad jsonp response: HTTP {response.status_code} for {ziurl_jsonp}'
                    )

                # ── Download pages ───────────────────────────────────────────
                pages_saved = 0
                for i in range(1, page_count + 1):
                    ziurl     = (
                        f"{URL_VIEW}?doc={gidf_json['d']}&format=pdf"
                        f"&subfolder={gidf_json['f']}&page={i}"
                    )
                    page_path = os.path.join(doc_dir, f'{i}.pdf')

                    if not overwrite and _page_valid(page_path):
                        pages_saved += 1
                        continue

                    be_polite(PACE_PAGE)
                    try:
                        response = session.get(ziurl, headers=base_headers('headers2'),
                                               verify=False, timeout=timeout)
                    except Exception as e:
                        logging.error(f'GET page {i} of {filename}: {e}')
                        continue

                    if not pdf_ok(response):
                        logging.warning(
                            f'Bad page {i} response: HTTP {response.status_code}, '
                            f'len={len(response.content)}, magic={response.content[:5]!r}'
                        )
                        continue

                    try:
                        with open(page_path, 'wb') as f:
                            f.write(response.content)
                        pages_saved += 1
                        all_files  += 1
                    except Exception as e:
                        logging.error(f'Error saving page {i} of {filename}: {e}')

                # ── Write completion marker only when fully downloaded ────────
                if pages_saved == page_count:
                    try:
                        with open(done_path, 'w') as f:
                            f.write(str(page_count))
                    except Exception as e:
                        logging.error(f'Error writing .done for {filename}: {e}')
                else:
                    logging.warning(
                        f'{filename}: saved {pages_saved}/{page_count} pages — '
                        f'.done not written, will retry next run'
                    )

                if all_files > 0 and all_files % pause_at == 0:
                    time.sleep(pause)
                    if files_found:
                        tqdm.write(f'Files found (skipped): {files_found}')

    conn.close()
    tqdm.write(f'Done: {len(rows)} days, {all_files} pages saved, {files_found} skipped')
    if sys.platform == 'darwin':
        os.system(f'say -v ioana "în sfârșit, am gătat {all_files} fișiere " -r 250')


def _page_valid(path: str) -> bool:
    """True if path exists and starts with the PDF magic bytes."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as f:
            return is_pdf(f.read(5))
    except OSError:
        return False


if __name__ == '__main__':
    main()
