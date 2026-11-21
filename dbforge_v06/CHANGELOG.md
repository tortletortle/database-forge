# Changelog

## V0.6

- Changed exact grouped-FD validation default from determinant-only index to sequential scan plus SQLite temporary GROUP BY B-tree, based on three repeated 1M-row synthetic workload experiments.
- Added selectable none, determinant, and covering index strategies for reproducible comparisons.
- Added index-build timing to the execution report.
- Added a reusable isolated-process benchmark harness with query-plan, index-size, timing, RSS, and exact-result comparison output.
- Added a streaming synthetic-data generator for randomized, high-cardinality, and customer-sorted layouts.
- Added 4 regression tests for strategy equivalence, default behavior, invalid strategy handling, and V0.6 metadata; total V0.6 suite: 16 tests.
- On the tested 1M-row order workload, full-pipeline median time improved about 9.5% vs V0.5, with peak RSS effectively unchanged.
