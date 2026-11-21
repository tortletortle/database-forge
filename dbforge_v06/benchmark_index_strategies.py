"""Compare exact grouped-FD validation with no index, determinant-only, and covering indexes.

Example:
  python benchmark_index_strategies.py orders.csv \
    --scan customer_id=customer_name,region \
    --scan product_id=product_name,category --repeats 2

Each strategy runs in a fresh subprocess against a copy of one disk-staged SQLite
input. Index construction and grouped-query time are reported separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHILD = r'''
import json, resource, sqlite3, sys, time
from pathlib import Path
path, mode, scans_json, cache_mib = sys.argv[1:5]
scans = json.loads(scans_json)
cx = sqlite3.connect(path)
cx.execute('PRAGMA temp_store=FILE')
cx.execute(f'PRAGMA cache_size={-int(cache_mib) * 1024}')
cx.execute('PRAGMA mmap_size=0')
results = []
for scan in scans:
    key, rhs = scan['key_index'], scan['rhs_indices']
    index_name = 'ix_dbforge_bench'
    build_s = 0.0
    index_bytes = 0
    if mode == 'determinant':
        columns = [f'c{key}']
    elif mode == 'covering':
        columns = [f'c{key}'] + [f'c{x}' for x in rhs]
    else:
        columns = []
    if columns:
        t0 = time.perf_counter()
        cx.execute(f'CREATE INDEX {index_name} ON raw({", ".join(columns)})')
        cx.commit()
        build_s = time.perf_counter() - t0
        try:
            index_bytes = cx.execute(
                'SELECT COALESCE(SUM(pgsize),0) FROM dbstat WHERE name=?',
                (index_name,)).fetchone()[0]
        except sqlite3.OperationalError:
            index_bytes = None
        source = f'raw INDEXED BY {index_name}'
    else:
        source = 'raw'
    bad = ', '.join(
        f'CASE WHEN MIN(c{j}) <> MAX(c{j}) THEN 1 ELSE 0 END AS b{k}'
        for k, j in enumerate(rhs))
    reps = ', '.join(
        f'length(CAST(MIN(c{j}) AS BLOB)) AS r{k}'
        for k, j in enumerate(rhs))
    inner = f'SELECT {bad}, {reps} FROM {source} GROUP BY c{key}'
    outer = 'SELECT ' + ', '.join(
        [f'MAX(b{k})' for k in range(len(rhs))] +
        [f'SUM(r{k})' for k in range(len(rhs))]) + f' FROM ({inner})'
    plan = [row[3] for row in cx.execute('EXPLAIN QUERY PLAN ' + outer)]
    t0 = time.perf_counter()
    result = cx.execute(outer).fetchone()
    query_s = time.perf_counter() - t0
    results.append({'key': scan['key'], 'rhs': scan['rhs'],
                    'build_s': build_s, 'query_s': query_s,
                    'index_bytes': index_bytes, 'result': result, 'plan': plan})
    if columns:
        cx.execute(f'DROP INDEX {index_name}')
        cx.commit()
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform == 'darwin':
    peak_mib = peak / (1024 * 1024)
else:
    peak_mib = peak / 1024
print(json.dumps({'mode': mode, 'results': results,
                  'peak_rss_mib': peak_mib}))
cx.close()
'''


def parse_scan(spec: str, columns: list[str]) -> dict:
    if '=' not in spec:
        raise ValueError(f'Invalid --scan {spec!r}; expected key=rhs1,rhs2')
    key, rhs_text = spec.split('=', 1)
    rhs = [x for x in rhs_text.split(',') if x]
    if key not in columns or not rhs or any(x not in columns for x in rhs):
        raise ValueError(f'Unknown key or RHS column in --scan {spec!r}')
    if key in rhs or len(set(rhs)) != len(rhs):
        raise ValueError(f'Key and RHS columns must be distinct in --scan {spec!r}')
    return {'key': key, 'rhs': rhs,
            'key_index': columns.index(key),
            'rhs_indices': [columns.index(x) for x in rhs]}


def stage_csv(source: Path, stage_path: Path, batch_size: int, cache_mib: int):
    cx = sqlite3.connect(stage_path)
    cx.execute('PRAGMA temp_store=FILE')
    cx.execute(f'PRAGMA cache_size={-cache_mib * 1024}')
    cx.execute('PRAGMA mmap_size=0')
    cx.execute('PRAGMA journal_mode=OFF')
    cx.execute('PRAGMA synchronous=OFF')
    with source.open('r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.reader(handle)
        columns = next(reader, [])
        if not columns or any(not c for c in columns):
            raise ValueError('CSV requires a nonempty header')
        if len({c.casefold() for c in columns}) != len(columns):
            raise ValueError('CSV headers must be unique ignoring case')
        definitions = ['_seq INTEGER PRIMARY KEY'] + [
            f'c{i} TEXT NOT NULL' for i in range(len(columns))]
        cx.execute(f'CREATE TABLE raw ({", ".join(definitions)})')
        insert = 'INSERT INTO raw VALUES (' + ', '.join(
            '?' for _ in range(len(columns) + 1)) + ')'
        batch, rows = [], 0
        for row in reader:
            if len(row) != len(columns):
                raise ValueError(f'Ragged CSV row near logical record {rows + 2}')
            rows += 1
            batch.append((rows, *row))
            if len(batch) >= batch_size:
                cx.executemany(insert, batch)
                batch.clear()
        if batch:
            cx.executemany(insert, batch)
    cx.commit()
    cx.close()
    return columns, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--scan', action='append', required=True,
                        help='Exact determinant scan, e.g. customer_id=customer_name,region')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=5000)
    parser.add_argument('--cache-mib', type=int, default=8)
    parser.add_argument('--seed', type=int, default=8301)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.repeats < 1 or args.batch_size < 1 or args.cache_mib < 1:
        parser.error('repeats, batch-size, and cache-mib must be positive')
    if not args.csv.is_file():
        parser.error(f'CSV does not exist: {args.csv}')

    with tempfile.TemporaryDirectory(prefix='dbforge-index-bench-') as tmp:
        root = Path(tmp)
        stage = root / 'stage.sqlite'
        t0 = time.perf_counter()
        columns, rows = stage_csv(args.csv, stage, args.batch_size, args.cache_mib)
        stage_seconds = time.perf_counter() - t0
        scans = [parse_scan(x, columns) for x in args.scan]
        print(f'staged rows={rows} in {stage_seconds:.3f}s', flush=True)
        modes = ['none', 'determinant', 'covering']
        raw = {mode: [] for mode in modes}
        for repeat in range(args.repeats):
            order = modes[:]
            random.Random(args.seed + repeat).shuffle(order)
            for mode in order:
                print(f'run repeat={repeat} mode={mode}', flush=True)
                db = root / f'{mode}-{repeat}.sqlite'
                shutil.copy2(stage, db)
                proc = subprocess.run(
                    [sys.executable, '-c', CHILD, str(db), mode,
                     json.dumps(scans), str(args.cache_mib)],
                    capture_output=True, text=True, check=True)
                raw[mode].append(json.loads(proc.stdout.strip().splitlines()[-1]))
                print(f'finished repeat={repeat} mode={mode}', flush=True)

        baseline = raw['none']
        comparisons = {}
        for mode in modes[1:]:
            equal = True
            for repeat in range(args.repeats):
                a = [x['result'] for x in baseline[repeat]['results']]
                b = [x['result'] for x in raw[mode][repeat]['results']]
                equal = equal and a == b
            comparisons[mode] = {'exact_group_results_match_no_index': equal}

        summary = {}
        for mode, runs in raw.items():
            totals = [sum(x['build_s'] + x['query_s'] for x in run['results'])
                      for run in runs]
            summary[mode] = {
                'total_scan_s_median': statistics.median(totals),
                'peak_rss_mib_median': statistics.median(
                    x['peak_rss_mib'] for x in runs),
                'per_scan': [{
                    'key': scan['key'],
                    'build_s_median': statistics.median(
                        run['results'][i]['build_s'] for run in runs),
                    'query_s_median': statistics.median(
                        run['results'][i]['query_s'] for run in runs),
                    'index_bytes_median': statistics.median(
                        run['results'][i]['index_bytes'] or 0 for run in runs),
                } for i, scan in enumerate(scans)]
            }
        report = {
            'source': str(args.csv), 'rows': rows, 'columns': columns,
            'repeats': args.repeats, 'stage_seconds': stage_seconds,
            'stage_bytes': stage.stat().st_size,
            'environment': {'python': sys.version.split()[0],
                            'sqlite': sqlite3.sqlite_version,
                            'platform': platform.platform()},
            'summary': summary, 'comparisons': comparisons, 'raw': raw
        }
    output = args.output or Path('benchmark_index_results.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'rows': rows, 'stage_seconds': stage_seconds,
                      'summary': summary, 'comparisons': comparisons}, indent=2))


if __name__ == '__main__':
    main()
