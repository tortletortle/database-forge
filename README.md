# DBForge — database synthesis engine

> Status: Private development repository.

DBForge explores automatic relational database generation from weakly structured CSV data.

## Current version: V0.5

V0.5 adds a disk-staged streaming path that bounds Python-side memory by ingesting CSV in batches into a temporary SQLite database. It performs exact grouped functional-dependency checks inside SQLite, synthesizes dimension/fact tables, and validates exact ordered reconstruction before publishing the output.

- [V0.5 source and usage](dbforge_v05/README.md)
- [V0.5 streaming implementation](dbforge_v05/streaming.py)
- [V0.5 regression tests](dbforge_v05/test_streaming.py)
- [V0.5 experiment report](dbforge_v05/EXPERIMENT.md)
- [V0.5 one-million-row raw measurements](dbforge_v05/benchmark_streaming_1m.json)
- [V0.4 in-memory optimization baseline](dbforge_v04/README.md)
- [V0.3 adaptive scheduler](dbforge_v03/README.md)
- [V0.2 budget-aware dependency search](dbforge_v02/README.md)

## V0.5 evidence and trade-offs

- 12 V0.5 streaming regression tests pass; earlier version test suites remain in their respective version directories.
- On a synthetic 1,000,000-row workload, peak RSS was 116.7 MiB for V0.5 vs 912.5 MiB for V0.4 (87.2% lower).
- Runtime was 16.79 s for V0.5 vs 10.58 s for V0.4 (about 1.59x slower). This is a memory-scaling improvement, not a throughput win.
- Both generated databases reconstructed exactly 1,000,000 rows; bidirectional SQL EXCEPT comparisons returned zero differing rows.
- The experiment used Python 3.13.5, SQLite 3.46.1, Linux x86_64, and synthetic data. Windows, high-cardinality million-row inputs, real business data, and network filesystems remain untested.

Run the V0.5 tests from the repository root:

    python -m unittest discover -s dbforge_v05 -v

## Engineering conventions

1. One project per repository; keep development repositories private.
2. Preserve local Git history and tags.
3. Every version should include tests, benchmark evidence, and a change record.
4. Do not mark unverified features as complete.
5. Do not force-push a skeleton over existing history.

## Version history

- V0.4 reuses exact validation evidence in schema planning and optimizes tuple projections and cursor-based round-trip verification. See its experiment record for the paired benchmark.
- V0.3 introduced adaptive marginal-benefit scheduling.
- V0.2 retained the budget-aware fixed strategy.

## Migration

If a complete local Git history already exists:

    git remote add origin https://github.com/tortletortle/database-forge.git
    git push -u origin --all
    git push origin --tags

Do not force-push over the existing repository history.
