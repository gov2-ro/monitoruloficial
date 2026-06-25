import json, sys, os, time, sqlite3, random, argparse, logging, urllib3
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from tqdm import tqdm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append("utils/")
from common import (
    generate_dates, base_headers, parse_date, make_session,
    setup_logging, DB_PATH, HTML_CACHE, TABLE_NAME, URL_GET_MO,
)


def main():
    parser = argparse.ArgumentParser(description='Fetch daily MO index → SQLite + HTML cache')
    parser.add_argument('-start', '--start_date', help='start date YYYY-MM-DD (default: 15 days ago)')
    parser.add_argument('-end',   '--end_date',   help='end date YYYY-MM-DD (default: today)')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, default=False,
                        help='overwrite existing DB rows (--no-overwrite to skip, default)')
    parser.add_argument('-m', '--mode',
                        help='l-<x>: last x days; all: from 2000-01-04 to today')
    parser.add_argument('--debug', action='store_true', help='verbose debug logging')
    args = parser.parse_args()

    setup_logging(args.debug)

    start_dt = parse_date(args.start_date) if args.start_date else datetime.today() - timedelta(days=15)
    end_dt   = parse_date(args.end_date)   if args.end_date   else datetime.today()

    if args.mode:
        if args.mode == 'all':
            start_dt = datetime(2000, 1, 4)
            end_dt   = datetime.today()
        elif args.mode.startswith('l-'):
            try:
                days     = int(args.mode[2:])
                end_dt   = datetime.today()
                start_dt = end_dt - timedelta(days=days)
            except ValueError:
                logging.error(f'Invalid mode {args.mode!r}. Use l-<number> or all.')
                raise SystemExit(1)
        else:
            logging.error(f'Unknown mode {args.mode!r}. Use l-<number> or all.')
            raise SystemExit(1)

    overwrite     = args.overwrite
    save_to_cache = True
    save_to_db    = True
    pause_at      = 31   # days between longer pauses
    pause         = 7    # seconds

    zidates = generate_dates(start_dt, end_dt, '%Y-%m-%d')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f'CREATE TABLE IF NOT EXISTS {TABLE_NAME} '
              '("date" TEXT, "json" TEXT, PRIMARY KEY("date"))')

    logging.info(f'Range: {start_dt:%Y-%m-%d} → {end_dt:%Y-%m-%d}')
    if overwrite:
        logging.info('Overwriting previously saved dates')
    else:
        c.execute(
            f'SELECT date FROM {TABLE_NAME} WHERE date BETWEEN ? AND ?',
            (start_dt.strftime('%Y-%m-%d'), end_dt.strftime('%Y-%m-%d')),
        )
        sqlite_dates = {row[0] for row in c.fetchall()}
        if sqlite_dates:
            logging.info(f'Skipping {len(sqlite_dates)} days already in DB')
        zidates = [d for d in zidates if d not in sqlite_dates]

    logging.info(f'Processing {len(zidates)} days')
    session = make_session()
    ii = 0

    for oneday in tqdm(zidates):
        data = {'today': oneday, 'rand': random.random()}
        try:
            response = session.post(URL_GET_MO, headers=base_headers('headers1'),
                                    data=data, verify=False, timeout=30)
        except Exception as e:
            logging.error(f'Request failed for {oneday}: {e}')
            continue

        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            json_data = {}
            for div in soup.find_all('div', class_='card-body'):
                ol = div.find('ol', class_='breadcrumb')
                if ol is None:
                    continue
                key = ol.text.strip()
                value = {a.text: a['href'] for a in div.find_all('a', class_='btn')}
                json_data[key] = value
        except Exception as e:
            logging.error(f'Parse error for {oneday}: {e}')
            continue

        if save_to_cache:
            cache_path = HTML_CACHE + oneday + '.html'
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(soup.prettify())
                logging.debug(f'Written cache: {cache_path}')
            except Exception as e:
                logging.warning(f'Cache write failed for {oneday}: {e}')

        if save_to_db:
            json_result = json.dumps(json_data, ensure_ascii=False)
            if overwrite:
                sql = f'INSERT OR REPLACE INTO {TABLE_NAME} (date, json) VALUES (?, ?)'
            else:
                sql = f'INSERT INTO {TABLE_NAME} (date, json) VALUES (?, ?) ON CONFLICT(date) DO NOTHING'
            c.execute(sql, (oneday, json_result))
            conn.commit()

        ii += 1
        time.sleep(random.random() * 2)
        if ii % pause_at == 0:
            time.sleep(pause)

    conn.close()
    tqdm.write(f'{ii} days saved to DB')
    if sys.platform == 'darwin':
        os.system(f'say -v ioana "în sfârșit, am gătat {ii} zile " -r 250')


if __name__ == '__main__':
    main()
