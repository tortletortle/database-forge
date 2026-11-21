"""DBForge V0.6: evidence-guided bounded-memory CSV -> SQLite synthesis.

The raw CSV is staged in a temporary SQLite database in bounded batches.
Exact unary FDs are checked by SQLite grouped scans; accepted FDs are never
inferred from a sample. The published database is created separately and
atomically linked into place only after integrity and round-trip validation.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import tempfile
import time
from math import isfinite
from collections import defaultdict
from pathlib import Path


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _configure_scratch(cx: sqlite3.Connection, cache_mib: int) -> None:
    # Scratch data are reproducible from the input CSV; avoid retaining a large
    # SQLite page cache in RAM. FILE temp storage keeps GROUP BY spill off heap.
    cx.execute('PRAGMA temp_store=FILE')
    cx.execute(f'PRAGMA cache_size={-cache_mib * 1024}')
    cx.execute('PRAGMA mmap_size=0')
    cx.execute('PRAGMA journal_mode=OFF')
    cx.execute('PRAGMA synchronous=OFF')


def _read_header(reader):
    cols = next(reader, [])
    if not cols or any(not c or '\x00' in c for c in cols):
        raise ValueError('CSV header must have nonempty names without NUL')
    if len({c.casefold() for c in cols}) != len(cols):
        raise ValueError('CSV header names must be unique ignoring case')
    return cols


def _allowed_key_indices(cols, keys, unrestricted):
    if keys is not None:
        missing = [k for k in keys if k not in cols]
        if missing:
            raise ValueError(f'Unknown explicit entity keys: {missing}')
        return {cols.index(k) for k in keys}
    if unrestricted:
        return set(range(len(cols)))
    return {i for i, name in enumerate(cols)
            if name.lower() == 'id' or name.lower().endswith(('_id', '_code'))}


def _profile(cx, cols):
    """Exact per-column cardinality and UTF-8 payload profile, using SQLite."""
    result = []
    n = cx.execute('SELECT COUNT(*) FROM raw').fetchone()[0]
    for i in range(len(cols)):
        col = f'c{i}'
        total = cx.execute(
            f'SELECT COALESCE(SUM(length(CAST({col} AS BLOB))),0) FROM raw'
        ).fetchone()[0]
        count, distinct_bytes, min_bytes = cx.execute(
            f'''SELECT COUNT(*),
                       COALESCE(SUM(length(CAST(v AS BLOB))),0),
                       COALESCE(MIN(length(CAST(v AS BLOB))),0)
                FROM (SELECT DISTINCT {col} AS v FROM raw)'''
        ).fetchone()
        result.append({'count': count, 'total_bytes': total,
                       'distinct_bytes': distinct_bytes, 'min_bytes': min_bytes})
    return n, result


def _choose_groups(proposals):
    """Same deterministic greedy disjoint-star planner as V0.4."""
    chosen, reserved, removed = [], set(), set()
    while True:
        choices = []
        for i, key_cost, gains in proposals:
            if i in reserved or i in removed:
                continue
            js = tuple(sorted(j for j, gain in gains.items()
                              if j not in reserved and j not in removed and gain > 0))
            net = sum(gains[j] for j in js) - key_cost
            if js and net > 0:
                choices.append((net, i, js))
        if not choices:
            break
        net, i, js = max(choices, key=lambda x: (x[0], -x[1], x[2]))
        chosen.append((i, js, net))
        reserved.add(i)
        removed.update(js)
    return chosen


def generate_csv_streaming(source, destination, *, normalize=True, keys=None,
                           unrestricted=False, validation_budget=None, min_return=2.0,
                           batch_size=5000, cache_mib=8, index_strategy='none'):
    """Generate a verified SQLite snapshot from CSV with bounded Python memory.

    validation_budget counts logical source rows consumed by exact grouped
    determinant scans. A determinant scan validates all its eligible RHS
    attributes together. It is not a physical-I/O or wall-clock budget.
    None means at most 8 full determinant scans. The CSV staging pass and
    database build/verification are outside this validation budget.

    index_strategy selects 'none' (default), 'determinant', or 'covering'.
    'none' lets SQLite use a sequential scan and temporary GROUP BY B-tree;
    'determinant' reproduces V0.5's determinant-only index; 'covering' indexes
    the determinant and all RHS columns for that scan.
    """
    start = time.perf_counter()
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError('batch_size must be a positive integer')
    if not isinstance(cache_mib, int) or isinstance(cache_mib, bool) or cache_mib < 1:
        raise ValueError('cache_mib must be a positive integer')
    if isinstance(min_return, bool) or not isinstance(min_return, (int, float)) or not isfinite(min_return) or min_return < 0:
        raise ValueError('min_return must be a finite nonnegative number')
    if index_strategy not in ('none', 'determinant', 'covering'):
        raise ValueError('index_strategy must be none, determinant, or covering')
    destination.parent.mkdir(parents=True, exist_ok=True)

    stats = {'rows': 0, 'columns': 0, 'candidate_keys': 0,
             'candidate_dependencies': 0, 'keys_checked': 0,
             'dependencies': [], 'dimensions': [], 'validation_rows_scanned': 0,
             'validation_budget': None, 'indexes_built': 0,
             'index_strategy': index_strategy, 'index_build_seconds': 0.0,
             'verified': False, 'memory_mode': 'bounded Python batches + SQLite disk staging'}

    with tempfile.TemporaryDirectory(prefix='.dbforge-stage-', dir=destination.parent) as workdir:
        stage_path = Path(workdir) / 'stage.sqlite'
        stage = sqlite3.connect(stage_path)
        _configure_scratch(stage, cache_mib)
        try:
            with source.open('r', newline='', encoding='utf-8-sig') as handle:
                reader = csv.reader(handle)
                cols = _read_header(reader)
                stats['columns'] = len(cols)
                key_indices = _allowed_key_indices(cols, keys, unrestricted)
                definitions = ['_seq INTEGER PRIMARY KEY'] + [f'c{i} TEXT NOT NULL' for i in range(len(cols))]
                stage.execute(f'CREATE TABLE raw ({", ".join(definitions)})')
                insert_sql = f'INSERT INTO raw VALUES ({", ".join("?" for _ in range(len(cols)+1))})'
                batch = []
                seq = 0
                for row in reader:
                    if len(row) != len(cols):
                        raise ValueError(f'Ragged CSV row near logical record {seq + 2}: expected {len(cols)} fields, got {len(row)}')
                    seq += 1
                    batch.append((seq, *row))
                    if len(batch) >= batch_size:
                        stage.executemany(insert_sql, batch)
                        batch.clear()
                if batch:
                    stage.executemany(insert_sql, batch)
                stage.commit()
                stats['rows'] = seq
            stats['stage_seconds'] = time.perf_counter() - start

            profile_start = time.perf_counter()
            n = stats['rows']
            if normalize and key_indices and n:
                n, profile = _profile(stage, cols)
            else:
                profile = []
            stats['profile_seconds'] = time.perf_counter() - profile_start
            stats['validation_budget'] = (8 * n if validation_budget is None else validation_budget)
            budget = stats['validation_budget']
            if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
                raise ValueError('validation_budget must be a nonnegative integer or None')

            proposals = []
            if normalize and n:
                for i in sorted(key_indices):
                    ci = profile[i]['count']
                    if not (1 < ci < n):
                        continue
                    possible = []
                    for j, p in enumerate(profile):
                        if i == j or not (1 < p['count'] <= ci):
                            continue
                        ub = (p['total_bytes'] - p['distinct_bytes']
                              - (ci - p['count']) * p['min_bytes'])
                        if ub >= min_return * n and ub > 0:
                            possible.append((j, ub))
                    net_upper = sum(ub for _, ub in possible) - profile[i]['distinct_bytes']
                    if possible and net_upper > 0:
                        proposals.append((i, possible, net_upper))
                stats['candidate_keys'] = len(proposals)
                stats['candidate_dependencies'] = sum(len(p[1]) for p in proposals)
                # Benefit per full scan; ties are deterministic by source column.
                proposals.sort(key=lambda x: (-x[2], x[0]))

                exact_fds = []
                exact_gains = {}
                planner_proposals = []
                for i, possible, _ in proposals:
                    if stats['validation_rows_scanned'] + n > budget:
                        break
                    # All RHS checks share one grouped scan. The default path
                    # deliberately avoids a determinant-only index: it can
                    # cause random table lookups for every RHS value. Optional
                    # index modes remain available for workload-specific tests.
                    idx = f'ix_raw_key_{i}'
                    rhs = [j for j, _ in possible]
                    if index_strategy != 'none':
                        index_columns = [f'c{i}']
                        if index_strategy == 'covering':
                            index_columns.extend(f'c{j}' for j in rhs)
                        index_sql = ', '.join(index_columns)
                        index_start = time.perf_counter()
                        stage.execute(f'CREATE INDEX {idx} ON raw({index_sql})')
                        stage.commit()
                        stats['index_build_seconds'] += time.perf_counter() - index_start
                        stats['indexes_built'] += 1
                        source_sql = f'raw INDEXED BY {idx}'
                    else:
                        source_sql = 'raw'
                    bad_exprs = [f'CASE WHEN MIN(c{j}) <> MAX(c{j}) THEN 1 ELSE 0 END AS b{k}'
                                 for k, j in enumerate(rhs)]
                    inner = f'SELECT {", ".join(bad_exprs + [f"length(CAST(MIN(c{j}) AS BLOB)) AS r{k}" for k,j in enumerate(rhs)])} FROM {source_sql} GROUP BY c{i}'
                    outer = 'SELECT ' + ', '.join([f'MAX(b{k})' for k in range(len(rhs))] + [f'SUM(r{k})' for k in range(len(rhs))]) + f' FROM ({inner})'
                    row = stage.execute(outer).fetchone()
                    bad = row[:len(rhs)]
                    rep_bytes = row[len(rhs):]
                    gains = {}
                    for k, j in enumerate(rhs):
                        if bad[k] == 0:
                            gain = profile[j]['total_bytes'] - rep_bytes[k]
                            exact_fds.append((i, j))
                            exact_gains[i, j] = gain
                            gains[j] = gain
                    if gains:
                        planner_proposals.append((i, profile[i]['distinct_bytes'], gains))
                    stats['keys_checked'] += 1
                    stats['validation_rows_scanned'] += n
                    if index_strategy != 'none':
                        stage.execute(f'DROP INDEX {idx}')
                        stage.commit()
                exact_fds.sort()
                stats['unresolved_keys'] = stats['candidate_keys'] - stats['keys_checked']
                stats['dependencies'] = [[cols[i], cols[j]] for i, j in exact_fds]
                groups = _choose_groups(planner_proposals)
            else:
                groups = []
                stats['candidate_keys'] = 0
                stats['candidate_dependencies'] = 0
                stats['unresolved_keys'] = 0
            stats['analysis_seconds'] = time.perf_counter() - profile_start
        finally:
            stage.close()

        stage_bytes = stage_path.stat().st_size if stage_path.exists() else 0
        stats['stage_bytes'] = stage_bytes

        fd, output_tmp = tempfile.mkstemp(prefix='.dbforge-output-', suffix='.sqlite', dir=destination.parent)
        os.close(fd)
        output = sqlite3.connect(output_tmp)
        try:
            output.execute('PRAGMA foreign_keys=ON')
            output.execute('PRAGMA temp_store=FILE')
            output.execute(f'PRAGMA cache_size={-cache_mib * 1024}')
            output.execute('PRAGMA mmap_size=0')
            output.execute('BEGIN')
            output.execute('ATTACH DATABASE ? AS src', (str(stage_path),))
            removed = {j for _, js, _ in groups for j in js}
            base = [j for j in range(len(cols)) if j not in removed]
            owner = {j: 'f' for j in base}
            joins, constraints = [], []
            for k, (i, js, _) in enumerate(groups):
                table = f'dim_{k}'
                indices = (i, *js)
                defs = [f'c{j} TEXT NOT NULL' + (' PRIMARY KEY' if j == i else '') for j in indices]
                output.execute(f'CREATE TABLE {table} ({", ".join(defs)})')
                select = ', '.join([f'c{i}', *[f'MIN(c{j})' for j in js]])
                output.execute(f'INSERT INTO {table} SELECT {select} FROM src.raw GROUP BY c{i}')
                constraints.append(f'FOREIGN KEY (c{i}) REFERENCES {table}(c{i})')
                joins.append(f'JOIN {table} ON f.c{i}={table}.c{i}')
                owner.update({j: table for j in js})
                stats['dimensions'].append({'key': cols[i], 'attributes': [cols[j] for j in js],
                                             'estimated_payload_saved': sum(
                                                 exact_gains[i, j]
                                                 for j in js) - profile[i]['distinct_bytes']})
            fact_defs = ['_seq INTEGER PRIMARY KEY'] + [f'c{j} TEXT NOT NULL' for j in base] + constraints
            output.execute(f'CREATE TABLE fact ({", ".join(fact_defs)})')
            dest_cols = ['_seq'] + [f'c{j}' for j in base]
            select_cols = ['_seq'] + [f'c{j}' for j in base]
            output.execute(f'INSERT INTO fact ({", ".join(dest_cols)}) SELECT {", ".join(select_cols)} FROM src.raw ORDER BY _seq')

            internal = '_dbforge_seq'
            col_names = {x.casefold() for x in cols}
            while internal.casefold() in col_names:
                internal += '_'
            view_cols = [f'{owner[j]}.c{j} AS {q(name)}' for j, name in enumerate(cols)]
            view_cols.append(f'f._seq AS {q(internal)}')
            output.execute('CREATE VIEW original_data AS SELECT ' + ', '.join(view_cols) +
                           ' FROM fact f ' + ' '.join(joins))
            output.execute('CREATE TABLE dbforge_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            output.executemany('INSERT INTO dbforge_metadata VALUES (?,?)', [
                ('columns', json.dumps(cols, ensure_ascii=False)),
                ('sequence_column', internal),
                ('policy', 'CSV cells are exact strings; empty string is not SQL NULL.'),
                ('engine', 'DBForge V0.6 streaming SQLite staging')])
            output.commit()
            stats['build_seconds'] = time.perf_counter() - start - stats['stage_seconds'] - stats['analysis_seconds']

            verify_start = time.perf_counter()
            if output.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise RuntimeError('SQLite integrity_check failed')
            if output.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise RuntimeError('SQLite foreign_key_check failed')
            mismatch = ' OR '.join(f's.c{j} IS NOT o.{q(cols[j])}' for j in range(len(cols)))
            seq_name = q(internal)
            bad_count = output.execute(
                f'''SELECT COUNT(*) FROM src.raw s JOIN original_data o
                    ON o.{seq_name}=s._seq WHERE {mismatch}''').fetchone()[0]
            src_count = output.execute('SELECT COUNT(*) FROM src.raw').fetchone()[0]
            out_count = output.execute(f'SELECT COUNT(*) FROM original_data').fetchone()[0]
            missing = output.execute(
                f'SELECT COUNT(*) FROM (SELECT _seq FROM src.raw EXCEPT SELECT {seq_name} FROM original_data)'
            ).fetchone()[0]
            extra = output.execute(
                f'SELECT COUNT(*) FROM (SELECT {seq_name} FROM original_data EXCEPT SELECT _seq FROM src.raw)'
            ).fetchone()[0]
            if bad_count or missing or extra or src_count != out_count:
                raise RuntimeError('Exact ordered source reconstruction failed')
            stats['verify_seconds'] = time.perf_counter() - verify_start
            output.execute('DETACH DATABASE src')
            output.close()
            output = None
            # Atomic no-overwrite publication on the destination filesystem.
            os.link(output_tmp, destination)
            stats['output_bytes'] = destination.stat().st_size
            stats['total_seconds'] = time.perf_counter() - start
            stats['verified'] = True
            return stats
        finally:
            if output is not None:
                output.close()
            Path(output_tmp).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv')
    p.add_argument('database')
    p.add_argument('--flat', action='store_true')
    p.add_argument('--keys', nargs='+')
    p.add_argument('--unrestricted', action='store_true')
    p.add_argument('--validation-budget', type=int)
    p.add_argument('--min-return', type=float, default=2.0)
    p.add_argument('--batch-size', type=int, default=5000)
    p.add_argument('--cache-mib', type=int, default=8)
    p.add_argument('--index-strategy', choices=('none', 'determinant', 'covering'), default='none')
    args = p.parse_args()
    report = generate_csv_streaming(args.csv, args.database,
                                    normalize=not args.flat, keys=args.keys,
                                    unrestricted=args.unrestricted,
                                    validation_budget=args.validation_budget, min_return=args.min_return,
                                    batch_size=args.batch_size, cache_mib=args.cache_mib,
                                    index_strategy=args.index_strategy)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
