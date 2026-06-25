import subprocess
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def run_script(script_name, extra_args=None):
    start_time = time.time()
    cmd = [sys.executable, str(_HERE / script_name)]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.call(cmd)
    print(f"{script_name} executed in {time.time() - start_time:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Orchestrates monitoruloficial.ro scrapers')
    parser.add_argument('-start', '--start_date',
                        default=(datetime.today() - timedelta(weeks=2)).strftime('%Y-%m-%d'),
                        help='start date YYYY-MM-DD (default: 2 weeks ago)')
    args = parser.parse_args()

    script_filenames = ["get_index.py", "fetch_p3+.py"]
    for script in script_filenames:
        run_script(script, ['-start', args.start_date])
