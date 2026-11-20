# V0.3 experimental evidence

Python 3.13.5; SQLite 3.46.1; seeds 32191, 43811, 71279. Six synthetic data families, seven policies, one build per seed per policy (126 total). Median across three seeds, no repeated timings within a seed. All builds verified exact ordered data reconstruction, integrity and foreign keys.

| Dataset | V0.2 full visits | V0.3 visits | V0.2 full ms | V0.3 ms | V0.3 gain retained |
|---|---:|---:|---:|---:|---:|
| orders | 40138 | 40062 | 61.02 | 60.75 | 100.00% |
| conflict | 30138 | 30062 | 58.94 | 60.02 | 100.00% |
| high_cardinality | 40705 | 40426 | 85.53 | 90.46 | 100.00% |
| mixed_wide | 41034 | 24336 | 84.65 | 84.96 | 98.64% |
| marginal | 8024 | 92 | 30.52 | 24.28 | N/A |
| no_key | 0 | 0 | 31.08 | 32.76 | N/A |

Mixed-wide: at the same 64,000-visit hard cap as fixed_8N, adaptive used 24,336 versus 41,034 visits, retained 98.64% of V0.2 full-search size savings, and did not show a material timing difference from full search. Adaptive_0 used 41,481 visits and retained 100%. Marginal: 92 versus 8,024 visits, no size saving for either. High-cardinality and conflict do not show a stable speed benefit. Timing and payload results are not proof of general superiority.

Reproduce with `python benchmark_adaptive.py`. Raw full results are also delivered in the V0.3 ZIP; this repository summary is not the raw file.
