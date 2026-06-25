import sqlite3, json, sys, os, time, random, argparse, logging, urllib3
from tqdm import tqdm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent / 'utils'))
from common import (
    base_headers, section_dir, setup_logging, make_session,
    is_pdf, DB_PATH, TABLE_NAME, SHY_PARTS, URL_BASE, DATA_ROOT,
)

"""
Download persistent Parts I, II, V (and PIM) PDFs from the day index.
Ephemeral parts (III-a, IV-a, VI-a, VII-a) are handled by fetch_p3+.py.
Configure by editing the variables below or passing CLI flags.
"""

logfile = DATA_ROOT + 'fetch_pdfs.log'


def fetch_pdf(session, url_base, url, output_path, headers):
    full_url = url_base + url
    logging.info(f'Downloading: {full_url}')

    try:
        response = session.get(full_url, headers=headers, timeout=30, stream=True)

        if response.status_code != 200:
            logging.error(f'HTTP {response.status_code} for {full_url}')
            return False

        content_type = response.headers.get('content-type', '')
        if 'application/pdf' not in content_type.lower():
            logging.warning(f'Unexpected content-type: {content_type} — checking magic bytes')

        # Buffer the response and validate before writing to disk.
        # This prevents poison files (HTML/empty bodies served as 200 OK under load).
        body = response.content
        if not body:
            logging.error(f'Empty body for {full_url}')
            return False
        if not is_pdf(body):
            logging.error(
                f'Not a PDF (magic={body[:8]!r}) for {full_url} — skipping write'
            )
            return False

        with open(output_path, 'wb') as f:
            f.write(body)
        logging.info(f'Saved: {output_path}')
        return True

    except Exception as e:
        logging.error(f'Request failed for {full_url}: {e}')
        return False


def main():
    parser = argparse.ArgumentParser(description='Download persistent Parts I/II PDFs')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug, logfile=logfile)

    session = make_session()

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f'SELECT * FROM {TABLE_NAME} ORDER BY date DESC')
        rows = c.fetchall()
        logging.info(f'Found {len(rows)} days in DB')

        for row in tqdm(rows, desc='days'):
            date, json_str = row
            try:
                json_dict = json.loads(json_str)

                for sectiune, parti in tqdm(json_dict.items(), desc='părți', leave=False):
                    if any(part in sectiune for part in SHY_PARTS):
                        continue

                    part_key = section_dir(sectiune)

                    for nr, url in tqdm(parti.items(), desc='pdfs', leave=False):
                        filename = os.path.splitext(url[1:])[0]
                        urlparts  = filename.split('--')
                        year      = urlparts[-1]

                        if not year.isdigit() or len(year) != 4:
                            logging.error(f'Invalid year {year!r} in URL: {url}')
                            continue

                        year_dir    = os.path.join(DATA_ROOT, part_key, year)
                        os.makedirs(year_dir, exist_ok=True)
                        output_path = os.path.join(year_dir, f'{filename}.pdf')

                        if os.path.isfile(output_path):
                            logging.debug(f'Exists, skipping: {output_path}')
                            continue

                        if fetch_pdf(session, URL_BASE, url, output_path, base_headers('headers2')):
                            time.sleep(random.uniform(2.0, 4.0))
                        else:
                            time.sleep(random.uniform(5.0, 8.0))

            except json.JSONDecodeError as e:
                logging.error(f'JSON decode error for {date}: {e}')
                continue
            except Exception as e:
                logging.error(f'Error processing {date}: {e}')
                continue

    except sqlite3.Error as e:
        logging.error(f'Database error: {e}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
