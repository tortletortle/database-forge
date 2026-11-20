# DBForge V0.4 — evidence-reuse generation engine

V0.4 preserves V0.3's adaptive dependency scheduler and greedy schema planner, but reuses exact validation evidence rather than rescanning all cells to recompute estimated UTF-8 payload savings. The fast path also uses tuple projections and streaming cursor iteration. SQLite durability settings, foreign key enforcement, integrity checks, exact ordered reconstruction, and no-overwrite publication remain unchanged.

## Usage

Python 3.9+; standard library only. The previous CLI default (`bound`) is preserved for compatibility. Opt in to the new engine:

```bash
python dbforge.py input.csv output.sqlite --strategy fast
python -m unittest -v
python benchmark_fast.py
```

`--strategy adaptive` runs the V0.3 control. The Python API additionally exposes `method='cached'` for the evidence-only ablation and `method='fast'` for the full optimization. The default adaptive cap is 8*N row-pair validation visits, not an elapsed-time limit. All CSV values remain exact strings.

## Evidence reuse

For an exactly verified dependency i -> j, the validation map contains precisely one dependent value for every distinct determinant. Therefore its payload savings equal the old planner's total dependent bytes minus the sum of dependent bytes over representative rows. The duplicated determinant bytes equal the exact distinct determinant payload computed during profiling. Only scalar gains and costs are retained, not the full validation maps. The unchanged greedy selection then consumes these exact same scores. This is an implementation optimization, not a new dependency discovery algorithm.

## Reproducibility and scope

30 local unit tests; 108 verified builds over six synthetic families, three new seeds, two repetitions and three methods; randomized within-pair method order. See EXPERIMENT.md and regenerate the raw JSON using the benchmark command. The ZIP includes full raw results. All three methods must agree on accepted dependencies, dimension definitions, validation visits, and file size for every labeled comparison. The benchmark starts after the input is loaded into memory and does not measure CSV parsing. The same in-memory rows and SQLite writer configuration are used. No claims about external engines, real business datasets, million-row scaling, memory peaks, or other hardware are established.
