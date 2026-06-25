import logging
import sqlite3
import subprocess
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / 'utils'))
from common import setup_logging, LOG_PATH, DB_PATH, init_runs_table, log_run_start, log_run_end


def run_script(script_name, extra_args=None):
    start_time = time.time()
    cmd = [sys.executable, str(_HERE / script_name)]
    if extra_args:
        cmd.extend(extra_args)
    ret = subprocess.call(cmd)
    elapsed = time.time() - start_time
    logging.info(f"{script_name} finished in {elapsed:.2f}s (exit {ret})")
    return elapsed, ret


if __name__ == "__main__":
    setup_logging(logfile=LOG_PATH)

    parser = argparse.ArgumentParser(description='Orchestrates monitoruloficial.ro scrapers')
    parser.add_argument('-start', '--start_date',
                        default=(datetime.today() - timedelta(weeks=2)).strftime('%Y-%m-%d'),
                        help='start date YYYY-MM-DD (default: 2 weeks ago)')
    args = parser.parse_args()

    db_conn = sqlite3.connect(DB_PATH)
    init_runs_table(db_conn)
    run_id = log_run_start(db_conn, 'main.py')

    script_filenames = ["get_index.py", "fetch_p3+.py"]
    total = 0.0
    for script in script_filenames:
        elapsed, _ = run_script(script, ['-start', args.start_date])
        total += elapsed

    log_run_end(db_conn, run_id, 'ok', {'scripts_run': len(script_filenames), 'total_duration_s': round(total, 2)})
    db_conn.close()
