# Changelog

## V0.5

- Added CSV ingestion in bounded Python batches into a disposable SQLite staging database.
- Added SQLite-side exact column profiling and grouped unary-FD validation.
- One determinant grouped scan checks all eligible dependent columns for that determinant.
- Added logical row-visit budget, configurable batch size and SQLite cache target.
- Added SQL-based dimension/fact generation and exact ordered reconstruction verification.
- Added atomic no-overwrite publication after integrity and foreign-key checks.
- Added 12 streaming tests; total suite: 42 tests.
- Benchmarked 20k, 100k, 250k and 1M synthetic rows against V0.4. At 1M rows, peak RSS fell 87.2%, while runtime was about 1.59x longer.
