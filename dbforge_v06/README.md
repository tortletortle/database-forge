# DBForge V0.6 — evidence-guided streaming validation

DBForge V0.6 retains the V0.5 disk-staged CSV-to-SQLite synthesis pipeline and changes the default exact functional-dependency validation access path.

## Main change

V0.5 created a temporary index on each determinant column before running the grouped exact check. Controlled one-million-row experiments showed that this determinant-only index was slower than a sequential table scan plus SQLite's temporary GROUP BY B-tree on three different synthetic layouts.

V0.6 therefore defaults to `index_strategy='none'`. It still validates every candidate exactly; no dependency is accepted from sampling. Two optional strategies remain available for controlled comparisons:

- `none` (default): sequential scan and SQLite temporary GROUP BY B-tree.
- `determinant`: reproduce V0.5's determinant-only index.
- `covering`: index the determinant and all candidate RHS columns for that scan.

## Quick start

Python 3.9+; standard library only. From the repository root:

```bash
python dbforge_v06/streaming.py input.csv output.sqlite --batch-size 5000 --cache-mib 8
python -m unittest discover -s dbforge_v06 -v
```

To reproduce the older index behavior or test a covering index:

```bash
python dbforge_v06/streaming.py input.csv output.sqlite --index-strategy determinant
python dbforge_v06/streaming.py input.csv output.sqlite --index-strategy covering
```

All modes retain the same exact validation, synthesis, integrity checks, and no-overwrite publication behavior.

## Evidence

- 16 V0.6 regression tests pass.
- Three 1M-row synthetic layouts (one sorted layout had 999,990 rows) were compared, with two fresh-database runs per strategy.
- Across all three layouts, no index had the lowest combined index-build-plus-query time for the two exact determinant scans.
- Across 20k, 100k, 250k and 1M full-pipeline comparisons, V0.6 was effectively tied at 100k and faster at the other three sizes. At 1M, median time fell from 16.79 s to 15.20 s (about 9.5% faster), analysis time fell about 31.2%, and peak RSS remained approximately 116.6 MiB.
- Every strategy produced identical grouped-check results in the microbenchmarks. Full V0.6 builds passed integrity, foreign-key, and exact ordered reconstruction checks.

See [EXPERIMENT.md](EXPERIMENT.md), [index-strategy summary](benchmark_index_strategy_results.json), [full-pipeline results](benchmark_full_pipeline_results.json), and the three per-workload raw files: [random orders](benchmark_index_strategy_raw_orders_random_1m.json), [high cardinality](benchmark_index_strategy_raw_high_cardinality_1m.json), and [customer-sorted](benchmark_index_strategy_raw_customer_sorted_999990.json).

## Limitations

- Results are from synthetic CSV data on one Linux x86_64 environment using Python 3.13.5 and SQLite 3.46.1. Windows, network filesystems, real business datasets, and other SQLite versions remain untested.
- The no-index default is evidence-guided for the tested workloads, not a universal theorem. Very wide RHS payloads, different storage devices, and different candidate counts may change the trade-off.
- V0.6 still supports unary functional dependencies and identifier-like or explicitly selected determinant columns. Composite keys, incremental updates, parallel ingestion, semantic type inference, and production query-workload optimization are not implemented.
- This is an execution-plan optimization, not a new functional-dependency discovery algorithm.

## Benchmark reproduction

Generate the deterministic random-order, high-cardinality, and customer-sorted input layouts (rows are streamed directly to CSV):

```bash
python dbforge_v06/generate_index_benchmark_data.py --rows 1000000 --output-dir /tmp/dbforge_v06_data
```

The index benchmark accepts an input CSV and explicit determinant-to-RHS scan specifications:

```bash
python dbforge_v06/benchmark_index_strategies.py orders.csv --scan customer_id=customer_name,region --scan product_id=product_name,category --repeats 2 --output benchmark_index_results.json

python dbforge_v06/benchmark_full_pipeline.py orders.csv --repeats 2 --modes v05 none
```

The index benchmark stages the CSV once, copies the staged database for each strategy, runs each strategy in a fresh subprocess, records query plans, index sizes, build/query time and peak RSS, and checks that grouped results match. The full-pipeline benchmark compares V0.5 and V0.6 end-to-end with exact reconstruction verification.
