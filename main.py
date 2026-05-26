import subprocess
import time
import argparse
from datetime import datetime, timedelta

def run_script(script_name, extra_args=None):
    start_time = time.time()
    cmd = ['python', script_name]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.call(cmd)
    end_time = time.time()
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
