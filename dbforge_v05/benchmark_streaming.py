"""End-to-end V0.4 in-memory vs V0.5 disk-staged CSV benchmark.

Each measurement runs in a fresh subprocess so ru_maxrss is comparable.
The source CSV is generated once and excluded from the timed region.
"""
import csv
import json
import platform
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
V04 = HERE.parent / 'dbforge_v04'
CHILD = r'''
import json, resource, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).parent / "dbforge_v04"))
sys.path.insert(0, sys.argv[1])
from dbforge import load_csv, generate
from streaming import generate_csv_streaming
source, output, method = sys.argv[2:5]
t0 = time.perf_counter()
if method == "v04":
    cols, rows = load_csv(source)
    report = generate(cols, rows, output, method="fast")
else:
    report = generate_csv_streaming(source, output, batch_size=5000, cache_mib=8)
elapsed = time.perf_counter() - t0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform == "darwin": rss_mib = rss / (1024*1024)
else: rss_mib = rss / 1024
print(json.dumps({"method":method,"elapsed_s":elapsed,"peak_rss_mib":rss_mib,
                  "output_bytes":report.get("bytes",report.get("output_bytes")),
                  "rows":report["rows"],"verified":report["verified"],
                  "stage_seconds":report.get("stage_seconds"),
                  "analysis_seconds":report.get("analysis_seconds"),
                  "build_seconds":report.get("build_seconds"),
                  "verify_seconds":report.get("verify_seconds"),
                  "validation_rows_scanned":report.get("validation_rows_scanned")}))
'''


def write_orders(path, n, seed=8301):
    rng = random.Random(seed)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['order_id','customer_id','customer_name','region','product_id','product_name','category','quantity','note'])
        for i in range(n):
            c = rng.randrange(max(2, n//30))
            p = rng.randrange(1200)
            w.writerow([f'O{i:08}', f'C{c:07}', f'Customer {c:07} extended name',
                        f'Region {c%17}', f'P{p:07}', f'Product {p:07} extended description',
                        f'Category {p%13}', str(rng.randrange(1,20)), f'Note {rng.randrange(10000)}'])


def run_one(source, output, method):
    output.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, '-c', CHILD, str(HERE), str(source), str(output), method],
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    cases = [(20000,2),(100000,2),(250000,2)]
    result = {'environment': {'python':sys.version.split()[0], 'platform':platform.platform(),
                              'sqlite':__import__('sqlite3').sqlite_version},
              'note':'Source CSV generation excluded; each method measured in a fresh subprocess; peak RSS is process maximum resident set size. 1M is streaming-only.',
              'cases':[]}
    with tempfile.TemporaryDirectory(prefix='dbforge-bench-') as tmp:
        root = Path(tmp)
        for n, repeats in cases:
            source = root / f'orders-{n}.csv'
            write_orders(source, n, 8301+n)
            runs = {'v04':[], 'v05_streaming':[]}
            methods = ['v04','v05_streaming'] if n < 1000000 else ['v05_streaming']
            for rep in range(repeats):
                order = methods[:]
                random.Random(710+rep+n).shuffle(order)
                for method in order:
                    out = root / f'{n}-{rep}-{method}.sqlite'
                    row = run_one(source, out, method)
                    if not row['verified'] or row['rows'] != n:
                        raise RuntimeError(f'validation failed: {n} {method}')
                    runs[method].append(row)
                    out.unlink()
            summary = {}
            for method, rows in runs.items():
                if not rows: continue
                summary[method] = {
                    'elapsed_s_median':round(statistics.median(x['elapsed_s'] for x in rows),3),
                    'peak_rss_mib_median':round(statistics.median(x['peak_rss_mib'] for x in rows),1),
                    'output_bytes':rows[0]['output_bytes'],
                    'verified_runs':sum(x['verified'] for x in rows),
                    'stage_s_median':round(statistics.median(x['stage_seconds'] for x in rows if x['stage_seconds'] is not None),3) if any(x['stage_seconds'] is not None for x in rows) else None,
                    'analysis_s_median':round(statistics.median(x['analysis_seconds'] for x in rows if x['analysis_seconds'] is not None),3) if any(x['analysis_seconds'] is not None for x in rows) else None,
                }
            case = {'rows':n,'csv_bytes':source.stat().st_size,'repeats':repeats,'summary':summary,'raw':runs}
            if 'v04' in summary:
                case['memory_reduction_ratio'] = round(1-summary['v05_streaming']['peak_rss_mib_median']/summary['v04']['peak_rss_mib_median'],4)
                case['speed_ratio_v04_over_v05'] = round(summary['v04']['elapsed_s_median']/summary['v05_streaming']['elapsed_s_median'],4)
            result['cases'].append(case)
            print(json.dumps({'rows':n,'summary':summary}, ensure_ascii=False), flush=True)
    (HERE/'benchmark_streaming_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__ == '__main__':
    main()