# DBForge — database synthesis engine

> Status: Private development repository.

DBForge explores automatic relational database generation from weakly structured CSV data.

## Current version: V0.6

V0.6 retains V0.5's disk-staged CSV-to-SQLite synthesis pipeline and changes the default exact functional-dependency validation access path based on controlled index-strategy experiments.

- [V0.6 source and usage](dbforge_v06/README.md)
- [V0.6 streaming implementation](dbforge_v06/streaming.py)
- [V0.6 regression tests](dbforge_v06/test_streaming.py)
- [V0.6 experiment report](dbforge_v06/EXPERIMENT.md)
- [V0.6 raw index-strategy results](dbforge_v06/benchmark_index_strategy_results.json)
- [V0.6 full-pipeline comparisons](dbforge_v06/benchmark_full_pipeline_results.json)
- [V0.6 synthetic benchmark data generator](dbforge_v06/generate_index_benchmark_data.py)
- [V0.5 disk-staged baseline](dbforge_v05/README.md)
- [V0.4 in-memory optimization baseline](dbforge_v04/README.md)
- [V0.3 adaptive scheduler](dbforge_v03/README.md)
- [V0.2 budget-aware dependency search](dbforge_v02/README.md)

## V0.6 evidence and trade-offs

- 16 V0.6 regression tests pass.
- Three synthetic data layouts were compared at approximately one million rows, with two repetitions per index strategy.
- No index was the fastest total validation strategy in all three tested layouts. The determinant-only index introduced costly dependent-column lookups; covering indexes reduced query time but did not recover their build cost.
- Across 20k, 100k, 250k and 1M full-pipeline comparisons, V0.6 was effectively tied at 100k and faster at the other three sizes. At 1M, median time was 15.20 s vs 16.79 s for V0.5 (about 9.5% faster); analysis time fell about 31.2%, while peak RSS remained about 116.6 MiB.
- These are synthetic Linux results, not proof that no-index is optimal for every schema or storage device.

Run V0.6 tests from the repository root:

    python -m unittest discover -s dbforge_v06 -v

## Engineering conventions

1. One project per repository; keep development repositories private.
2. Preserve local Git history and tags.
3. Every version should include tests, benchmark evidence, and a change record.
4. Do not mark unverified features as complete.
5. Do not force-push a skeleton over existing history.

## Version history

- V0.5 introduced bounded-batch disk staging and exact SQLite-side grouped validation. Its determinant-only index is retained as an explicit V0.6 comparison mode.
- V0.4 reuses exact validation evidence in schema planning and optimizes tuple projections and cursor-based round-trip verification.
- V0.3 introduced adaptive marginal-benefit scheduling.
- V0.2 retained the budget-aware fixed strategy.

## Migration

If a complete local Git history already exists:

    git remote add origin https://github.com/tortletortle/database-forge.git
    git push -u origin --all
    git push origin --tags

Do not force-push over the existing repository history.
