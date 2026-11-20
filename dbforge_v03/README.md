# DBForge V0.3 — adaptive marginal-return scheduling (experimental)

Python 3.9+ standard library. Run `python dbforge.py input.csv output.sqlite --strategy adaptive` for the automatic policy. Use `--budget 40000` to override the default 8*N maximum row-pair visits. `--min-return 2` is the minimum upper-bound UTF-8 payload bytes per full validation visit; it is a heuristic policy, not a guaranteed disk-space saving. `--strategy bound` reproduces the V0.2 scheduler. `--flat` skips discovery; `--keys customer_id product_id` sets eligible determinants. Exact CSV string values and input row order are preserved in `original_data` using the sequence column in `dbforge_metadata`.

## Algorithm

Reuse V0.2 exact column profiling and positive-payload bound pruning. Reject additional low-return candidates under the configured policy. Prioritize potential novel dependent value savings, accounting for the estimated amortized key cost. Validate candidates in a deterministic random pilot order followed by every remaining row exactly once; stop at the first contradiction. Never accept an incompletely verified dependency. Do not start a validation if the remaining budget cannot cover all N rows. Fully validated dependencies enter the unchanged greedy disjoint-star planner. The policy can miss valuable alternatives and is not globally optimal.

## Reproduce

- `python -m unittest -v`: 23 tests (16 inherited, 7 new).
- `python benchmark_adaptive.py`: six synthetic data families, three seeds, seven build policies, 126 builds; one measurement per seed and policy with randomized execution order. Every build verifies SQLite integrity, FK constraints and exact ordered reconstruction.
- `benchmark_adaptive_results.json`: locally generated raw per-build reports; regenerate it with the command above.

## Limitations

Default threshold and cap are provisional engineering choices; the validation visit cap excludes profiling, ranking, planning, writes and verification. No stable end-to-end speedup is established. All workloads are synthetic; no multiple hardware platforms, external FD-engine baselines, composite keys, query workload, or future business constraints have been validated. Relative storage gains use V0.2 bound full-search as reference, not a globally optimal design. The adaptive_0 ablation removes the return threshold but retains the cap, pilot order and dynamic ranks.
