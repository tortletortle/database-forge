# V0.4 experiment record

Python 3.13.5; SQLite 3.46.1; Linux-6.18.57-x86_64-with-glibc2.41. Seeds 55173, 68323, 82031; two repeats per seed; randomized method order. 108 verified builds. Median milliseconds over six runs per method and case. Paired speedup is the median of baseline/fast time ratios, not the ratio of independently computed medians.

| Dataset | rows | V0.3 ms | cached only ms | V0.4 fast ms | paired speedup | wins out of 6 |
|---|---:|---:|---:|---:|---:|---:|
| orders | 40000 | 266.29 | 228.85 | 236.58 | 1.102 | 6 |
| conflict | 40000 | 252.99 | 222.15 | 224.83 | 1.157 | 6 |
| high_cardinality | 40000 | 439.03 | 395.77 | 374.76 | 1.167 | 6 |
| mixed_wide | 25000 | 308.29 | 253.25 | 256.94 | 1.201 | 6 |
| marginal | 25000 | 77.18 | 77.03 | 73.54 | 1.046 | 5 |
| no_key | 20000 | 121.17 | 123.79 | 117.43 | 1.020 | 4 |

The dependency list, dimension plan, validation visits and database file size matched for every comparison. All builds passed full ordered round-trip validation and SQLite integrity and FK checks. The cached-only ablation identifies repeated payload accounting as the main avoidable cost. The optimized projection/cursor path does not consistently add speed on top of evidence reuse. No-key and marginal speedups are small and variable. The in-memory synthetic-data benchmark excludes CSV parsing, has no independent real-dataset or external-engine baseline, and does not isolate the cost of filesystem caches or measure peak RAM.
