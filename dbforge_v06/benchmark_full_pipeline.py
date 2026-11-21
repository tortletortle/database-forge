"""Compare complete V0.5 and V0.6 CSV-to-SQLite synthesis runs.

Each run uses a fresh subprocess. All modes perform their own exact
reconstruction verification; the report includes elapsed time, phase timing,
peak RSS, discovered dependencies, and verification status.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

CHILD = r'''
import json, resource, sys, time
from pathlib import Path
version_dir, source, output, mode = sys.argv[1:5]
sys.path.insert(0, version_dir)
from streaming import generate_csv_streaming
if mode == 'v05':
    kwargs = {}
else:
    kwargs = {'index_strategy': mode}
t0 = time.perf_counter()
report = generate_csv_streaming(source, output, **kwargs)
print(json.dumps({
    'mode': mode,
    'elapsed_s': time.perf_counter() - t0,
    'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    'rows': report['rows'],
    'verified': report['verified'],
    'stage_seconds': report.get('stage_seconds'),
    'profile_seconds': report.get('profile_seconds'),
    'analysis_seconds': report.get('analysis_seconds'),
    'build_seconds': report.get('build_seconds'),
    'verify_seconds': report.get('verify_seconds'),
    'index_build_seconds': report.get('index_build_seconds'),
    'indexes_built': report.get('indexes_built'),
    'dependencies': report['dependencies'],
    'dimensions': report['dimensions']
}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--seed', type=int, default=5501)
    parser.add_argument('--modes', nargs='+', choices=('v05', 'none', 'determinant', 'covering'),
                        default=('v05', 'none', 'determinant', 'covering'))
    parser.add_argument('--output', type=Path, default=Path('benchmark_full_pipeline_v06.json'))
    args = parser.parse_args()
    if not args.csv.is_file() or args.repeats < 1:
        parser.error('CSV must exist and repeats must be positive')
    repo_root = Path(__file__).resolve().parent.parent
    if 'v05' not in args.modes:
        parser.error('include v05 as the comparison baseline in --modes')
    v06_dir = Path(__file__).resolve().parent
    modes = [(mode, repo_root / 'dbforge_v05' if mode == 'v05' else v06_dir)
             for mode in args.modes]
    raw = {mode: [] for mode, _ in modes}
    with tempfile.TemporaryDirectory(prefix='dbforge-full-bench-') as tmp:
        tmpdir = Path(tmp)
        for repeat in range(args.repeats):
            order = modes[:]
            random.Random(args.seed + repeat).shuffle(order)
            for mode, version_dir in order:
                print(f'run repeat={repeat} mode={mode}', flush=True)
                output = tmpdir / f'{mode}-{repeat}.sqlite'
                proc = subprocess.run(
                    [sys.executable, '-c', CHILD, str(version_dir), str(args.csv), str(output), mode],
                    capture_output=True, text=True, check=True)
                row = json.loads(proc.stdout.strip().splitlines()[-1])
                raw[mode].append(row)
                print(f'finished repeat={repeat} mode={mode} elapsed={row["elapsed_s"]:.3f}s', flush=True)
                if not row['verified']:
                    raise RuntimeError(f'{mode} failed verification on repeat {repeat}')
        expected = raw['v05'][0]['dependencies']
        for mode, rows in raw.items():
            if any(row['dependencies'] != expected for row in rows):
                raise RuntimeError(f'dependency results differ for {mode}')
    summary = {}
    for mode, rows in raw.items():
        summary[mode] = {
            'elapsed_s_median': statistics.median(x['elapsed_s'] for x in rows),
            'peak_rss_mib_median': statistics.median(x['peak_rss_mib'] for x in rows),
            'analysis_seconds_median': statistics.median(x['analysis_seconds'] for x in rows),
            'index_build_seconds_median': statistics.median(x.get('index_build_seconds') or 0 for x in rows),
            'verified_runs': sum(x['verified'] for x in rows),
        }
    report = {'source': str(args.csv), 'repeats': args.repeats,
              'summary': summary, 'raw': raw}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
