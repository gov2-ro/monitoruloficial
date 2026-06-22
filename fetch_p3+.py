import sqlite3, json, requests, sys, os, time, random, re, random, json, argparse
import logging, urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
sys.path.append("../utils/")
from common import base_headers

""" 
read each json
download pdfs
check if exists, mode overwrite, mode update
# TODO: write log to db? checksum?
TODO: split by dates
 """

db_filename     =   '../../data/mo/mo.db'
table_name      =   'dates_lists'
output_folder   =   '../../data/mo/pdfs/_p3+/'
tmp_folder   =   '../../data/mo/pdfs/_p3+/tmp/'
verbose         =   False
overwrite       =   False   # if false check if file exists, don't fetch again
pause_at        =   30      # days
pause           =   10      # seconds
shy_parts       =   ["III-a", "IV-a", "VI-a", "VII-a"] # ascunse după10 zile
url_base        =   'https://monitoruloficial.ro'
transit_url     =   'https://monitoruloficial.ro/ramo_customs/emonitor/gidf.php' # to get number of pages
start_date      =   datetime.today() - timedelta(days=10)
end_date        =   datetime.today()
daysago         =   10
timeout         =   30      # seconds per request
pace            =   (1.5, 3.0)   # random sleep (min, max) seconds before every request
pace_page       =   (0.6, 1.2)   # gentler pace between same-document page PDFs
#  - - - - - - - - - - - - - - - - - - - - -

# Session with a SINGLE retry on connection errors. The server IP-bans / RST-resets
# aggressive clients, so a retry burst keeps the ban hot — fail fast and rely on the
# per-request pacing below to stay under the rate limit.
def make_session():
    s = requests.Session()
    retry = Retry(
        total=1, connect=1, read=1,
        backoff_factor=2,                   # one ~2s pause before the single retry
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(['GET', 'POST']),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s

session = make_session()

def be_polite(bounds=pace):
    """Random delay before a request to stay under the server's rate limit."""
    time.sleep(random.uniform(*bounds))

parser = argparse.ArgumentParser(description='looks for dates and return lists of parti MO')
parser.add_argument('-start', '--start_date', help='start date')
parser.add_argument('-end', '--end_date', help='end date')
parser.add_argument('-days', '--days_ago', help='ho many days back from today')
parser.add_argument('--overwrite', help='True / False - if False, check if date exists, if it does, don\'t overwrite')
parser.add_argument('-m', '--mode', help='mode: l-<x> - last <x> days, all - from the beginning to today ')
args = parser.parse_args()
if args.start_date:
    start_date = args.start_date
if args.end_date:
    end_date = args.end_date
if args.overwrite:
    overwrite = args.overwrite
if args.days_ago:
    daysago = args.days_ago
    start_date = end_date - timedelta(days=int(daysago))
if args.mode:
    mode = args.mode
    if mode == 'all':
        end_date = datetime.today().strftime('%Y-%m-%d')


# end_date = datetime.today().strftime('%Y-%m-%d')

conn = sqlite3.connect(db_filename)
c = conn.cursor()
# c.execute('SELECT * FROM ' + table_name + ' ORDER BY date DESC')
# c.execute("SELECT * from '" + table_name + "' WHERE date BETWEEN '2023-04-10' AND '2023-04-12';")
c.execute("SELECT * from '" + table_name + "' WHERE date BETWEEN '" + str(start_date) + "' AND '" + end_date.strftime('%Y-%m-%d') + "';") 
rows = c.fetchall()
 
nrows = len(rows)
tqdm.write(' > ' + str(nrows) + ' days in the db')
all_files = 0
files_found = new_files_found = 0
prev_year = 1000
consecutive_failures = 0
max_consecutive_failures = 2

for row in tqdm(rows, desc='days'):
# Iterate over the rows and convert the JSON string to a dictionary
    date, json_str = row
    json_dict = json.loads(json_str)
    ii = 0
    for sectiune, parti in tqdm(json_dict.items(), desc='părți', leave=False):
        # check if parte < 3, don't bother, skip.
        if not any(part in sectiune for part in shy_parts):
            continue

        for nr, url in tqdm(parti.items(), desc='pdfs', leave=False):
            jj = 0
            filename = os.path.splitext(url[1:])[0]
            urlparts = filename.split('--')
            year=urlparts[-1]
            if len(year) != 4:
                tqdm.write('err: ' + str(year))
            
            if str(year) != str(prev_year):
                tqdm.write(f" -- current year: " + str(year) + " -", end="\r")
                # check if folder exists, cread if not, print.
                if not os.path.exists(output_folder + str(year) ):
                    os.makedirs(output_folder + str(year))
                    # tqdm.write(f"created " + str(year) + " folder", end="\r")
                    tqdm.write("created " + str(year) + " folder")
            
            # if not os.path.exists(tmp_folder + filename ):
            #         os.makedirs(tmp_folder + filename )
            #         # tqdm.write(f"created " + str(year) + " folder", end="\r")
            #         tqdm.write("created " + tmp_folder + filename  + " folder")

            # FIXME: if file exists don't overwrite?

            prev_year = year

            if verbose:
                tqdm.write('>> ' + url_base + url)

            if overwrite is False and os.path.isfile(output_folder + str(year) + '/' + filename + '.pdf'):
                files_found += 1
                if verbose:
                    tqdm.write('skipping ' + date + '/' + filename + '.pdf');
                continue #if overwrite = False and file exists, continue

               
            be_polite()
            try:
                response = session.get(url_base + url, headers=base_headers('headers2'), verify=False, timeout=timeout)
                consecutive_failures = 0
            except Exception as e:
                logging.error(f'Error processing URL {url_base + url}: {e}')
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    tqdm.write(f'Stopping: {consecutive_failures} consecutive failures.')
                    conn.close()
                    raise SystemExit(1)
                continue

            # get fid value

            soup = BeautifulSoup(response.content, 'html.parser')
            script_tags = soup.find_all('script')
            fid_value = None
            
            for script_tag in script_tags:
                # match = re.search("var fid = '(.*)';", script_tag.string)
                if script_tag.string is None:
                    continue
                try:
                    match = re.search(r"var fid\s*=\s*'(.*)';", script_tag.string)
                except Exception as e:
                    print(e)
                    breakpoint()

                if match:
                    fid_value = match.group(1)
                    break

            # now request gidf.php to find out the number of pages
            data = {'fid': fid_value, 'rand': random.random() }
            
            be_polite()
            try:
                response = session.post(transit_url, headers=base_headers('headers1'), data=data, verify=False, timeout=timeout)
                consecutive_failures = 0
            except Exception as e:
                logging.error('eRrx: '+ str(e))
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    tqdm.write(f'Stopping: {consecutive_failures} consecutive failures.')
                    conn.close()
                    raise SystemExit(1)
                continue

            # Server sometimes returns HTTP 200 with an empty/HTML body under load.
            # Guard the parse so a single bad response skips this item instead of
            # killing the whole run with an unhandled JSONDecodeError/KeyError.
            try:
                gidf_json = json.loads(response.text)
                title = gidf_json['t']
                page_count = gidf_json['p']
                folder = gidf_json['f']
            except (json.JSONDecodeError, KeyError) as e:
                logging.error(f'Bad gidf response for {url_base + url} (fid={fid_value}): {e}; body[:120]={response.text[:120]!r}')
                continue
            ziurl_jsonp = f"https://monitoruloficial.ro/ramo_customs/emonitor/showmo/services/view.php?doc={gidf_json['d']}&format=jsonp&subfolder={gidf_json['f']}&page=10"
            
            if not os.path.isdir(tmp_folder + date ):
                os.makedirs(tmp_folder + date )
            if not os.path.isdir(tmp_folder + date + '/' + filename):
                os.makedirs(tmp_folder + date + '/' + filename)

            if overwrite is False and os.path.isfile(tmp_folder + date + '/' + filename + '/' + filename + '.json'):
                tqdm.write('skipping ' + date + '/' + filename + '.json');
                continue #if overwrite = False and file exists, continue

            be_polite()
            try:
                response = session.get(ziurl_jsonp, headers=base_headers('headers2'), verify=False, timeout=timeout)
            except Exception as e:
                logging.error(f'Error processing URL {ziurl_jsonp}: {e}')
                continue   # don't fall through and write the previous response's body

            try:
                with open(tmp_folder + date + '/' + filename + '/' + filename + '.json', 'wb') as f:
                    f.write(response.content) 
                    tqdm.write(' >> ' + tmp_folder + date + '/' + filename + '/' + filename + '.json')       
            except Exception as e:
                logging.error(f' > E172 > Error saving PDF URL : {e}')

            for i in range(1, gidf_json['p'] + 1):
                ziurl = f"https://monitoruloficial.ro/ramo_customs/emonitor/showmo/services/view.php?doc={gidf_json['d']}&format=pdf&subfolder={gidf_json['f']}&page={i}"
               
                if overwrite is False and os.path.isfile(tmp_folder + date + '/' + filename + '/' + str(i) + '.pdf'):
                        files_found += 1
                        # if verbose:
                        tqdm.write('skipping ' + date + '/' + filename + '.pdf');
                        continue #if overwrite = False and file exists, continue

                be_polite(pace_page)
                try:
                    response = session.get(ziurl, headers=base_headers('headers2'), verify=False, timeout=timeout)
                except Exception as e:
                    logging.error(f'Error processing URL {url}: {e}')
                    continue   # skip this page rather than writing a stale/garbage PDF

                try:
                    # with open(output_folder + date + '.pdf', 'wb') as f:
                    with open(tmp_folder + date + '/'  + filename + '/' + str(i) + '.pdf', 'wb') as f:
                        f.write(response.content)
                        all_files+=1        
                except Exception as e:
                    logging.error(f'Error saving PDF URL : {e}')
            
            jj+=1
            if round(all_files/pause_at) == all_files/pause_at:
                time.sleep(pause)
                # os.system('say -v ioana "piiua " -r 250')
                if (new_files_found != files_found): 
                    tqdm.write("Files found: " + str(files_found))
                    new_files_found = files_found
            # tqdm.write('   - >  ' + str(ii) + '/' + str(nrows) + ' ' + str(ii+jj) + ' ' + str(jj))
    ii+=1
    
    # time.sleep(random.random()*1.75)

conn.close()
tqdm.write(' -- done ' + str(len(rows)) + ' days ' + str(ii) + ' secțiuni ' + str(all_files) + ' saved pdfs')
os.system('say -v ioana "în sfârșit, am gătat ' +  str(all_files) + ' fișiere " -r 250')