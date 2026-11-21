# DBForge V0.5 — disk-staged streaming synthesis

DBForge explores automatic relational database generation from weakly structured CSV data.

V0.5 adds a CSV-to-SQLite generation path that does not materialize the complete input dataset as Python tuples. It parses CSV records in bounded batches, writes a disposable SQLite staging database, performs exact column profiling and grouped functional-dependency validation inside SQLite, then creates a separate output database. The final file is published only after integrity, foreign-key, row-count, sequence, and exact-value reconstruction checks pass.

## Quick start

Python 3.9+; standard library only. The V0.5 streaming implementation is streaming.py. It reuses the V0.4 in-memory implementation as a comparison baseline in tests and benchmarks.

From the repository root:

    python dbforge_v05/streaming.py input.csv output.sqlite --batch-size 5000 --cache-mib 8
    python -m unittest discover -s dbforge_v05 -v

Options:

- --keys: explicitly name eligible determinant columns. By default, only columns named id or ending in _id / _code are considered.
- --unrestricted: allow any column as a determinant (use cautiously; this is not a semantic guarantee).
- --validation-budget: maximum logical source-row visits for exact determinant-group validation. One determinant is checked in one grouped pass, so each check consumes N logical visits. This is not a physical-I/O, CPU-time, or wall-clock budget. Default: 8 * row_count.
- --min-return: minimum upper-bound dependent UTF-8 payload saving per row before a candidate is considered; default 2.0. This is a heuristic threshold, not a guarantee of final on-disk savings.
- --batch-size: number of CSV records held in a Python insert batch; default 5,000.
- --cache-mib: SQLite page-cache target in MiB; default 8. This is not a hard process RSS limit.
- --flat: skip dependency discovery and normalization but still use streaming staging and verified output.

## V0.5 algorithm

1. Parse the CSV with csv.reader; validate the header and row width.
2. Insert each bounded batch into a temporary SQLite raw table. Scratch data are reproducible from the source CSV; the source file is never modified.
3. Compute exact cardinality and UTF-8 payload profiles using SQLite queries.
4. For each profitable eligible determinant, create a temporary index and run one grouped query. MIN(dependent) != MAX(dependent) detects a counterexample exactly under SQLite's default BINARY text comparison; all candidate dependent columns for that determinant are checked in the same grouped scan. No dependency is accepted from sampling.
5. Reuse exact representative payload costs in the deterministic greedy disjoint-star planner used by V0.4.
6. Build dimension and fact tables with SQL INSERT ... SELECT, preserving source row sequence. The original_data view reconstructs the original columns.
7. Run PRAGMA integrity_check, PRAGMA foreign_key_check, compare row sequences and every reconstructed field against the staging table. Publish with a no-overwrite hard link only after all checks pass.

## Validation and benchmark evidence

- 42 unit tests pass in the complete V0.5 development snapshot; the committed V0.5-specific regression suite contains 12 tests.
- At 1,000,000 synthetic rows, V0.5 peak RSS was 116.7 MiB vs 912.5 MiB for V0.4 (87.2% lower).
- Runtime was 16.79 s vs 10.58 s (about 1.59x slower); this is a memory-scaling improvement, not a throughput win.
- Both million-row outputs contained exactly 1,000,000 reconstructed rows; bidirectional SQL EXCEPT comparisons returned zero differing rows.
- The experiment report and raw one-million-row measurements are in EXPERIMENT.md and benchmark_streaming_1m.json.

## Important limitations

- V0.5 is a bounded-memory path, not a universal speed improvement. On the tested synthetic order workload it was slower than V0.4.
- The staging database consumes temporary disk space; the million-row run used about 159 MB of staging storage in addition to the 130 MB CSV and 51 MB output database.
- The exact FD model supports unary dependencies and identifier-like or explicitly selected determinant columns. Composite keys, semantic type inference, schema migration, incremental updates, parallel ingestion, and query-workload optimization are not implemented.
- The row-visit budget excludes CSV staging, profiling, index construction, output writing, and verification. It is a deterministic work-accounting metric, not a total compute budget.
- Experiments use synthetic CSV data on one Linux environment. Windows, network filesystems, high-cardinality million-row data, real business data, and external database engines remain untested.

## Novelty boundary

Streaming functional-dependency discovery is already an active research area. COD3 (2025) studies non-blocking continuous FD discovery over data streams. DBForge V0.5 does not claim a new online FD-discovery algorithm: it is a disk-staged, batch/offline synthesis pipeline using SQLite's exact grouped aggregation. The engineering hypothesis tested here is whether this approach can bound Python-side memory while retaining exact output reconstruction.

SQLite's query planner and covering-index behavior are existing database-engine capabilities; V0.5 relies on them rather than presenting them as new algorithms. A future optimization should benchmark a covering index against the current determinant-only index because a wider index may reduce table lookups while increasing temporary disk use and index-build time.

References:
- COD3, Non-blocking functional dependency discovery from data streams, Information Sciences 690 (2025): https://doi.org/10.1016/j.ins.2024.121531
- SQLite PRAGMA documentation: https://www.sqlite.org/pragma.html
- SQLite query planning and covering indexes: https://www.sqlite.org/queryplanner.html
