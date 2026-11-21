# DBForge V0.5 — experiment record

## Method

Compared V0.4's in-memory load_csv + generate(method='fast') against V0.5's disk-staged generate_csv_streaming. Each measurement ran in a fresh subprocess. Peak RSS was read from resource.getrusage(RUSAGE_SELF).ru_maxrss; source CSV generation was outside the timed region. Smaller cases used two runs per method with randomized order. The one-million-row comparison used two measurements per method in separate fresh processes on the same deterministic CSV. Every build completed SQLite integrity, foreign-key, and exact ordered round-trip verification.

Environment: Python 3.13.5, SQLite 3.46.1, Linux x86_64, 4 GiB cgroup memory limit. Workload: synthetic nine-column orders with customer and product dependencies. The 1M CSV was 130,056,617 bytes.

## Results

| Rows | V0.4 time (s) | V0.5 time (s) | V0.4 peak RSS (MiB) | V0.5 peak RSS (MiB) | RSS reduction | V0.5 / V0.4 time |
|---:|---:|---:|---:|---:|---:|---:|
| 20,000 | 0.241 | 0.271 | 111.4 | 102.4 | 8.1% | 1.12x |
| 100,000 | 0.998 | 1.542 | 178.8 | 116.7 | 34.7% | 1.54x |
| 250,000 | 2.477 | 4.007 | 299.2 | 116.3 | 61.1% | 1.62x |
| 1,000,000 | 10.583 | 16.786 | 912.5 | 116.7 | 87.2% | 1.59x |

The smaller three cases each represent the median of two runs. The million-row figures are also medians of two runs per method. At one million rows, V0.5 staged 1,000,000 records in 2.6 s, spent about 7.5 s profiling and validating, built the final database in about 2.3 s, and verified it in about 4.5 s. It performed two exact determinant-group scans (2,000,000 logical row visits) under an 8,000,000-visit budget. Temporary staging file size was 158,670,848 bytes; final output was 51,490,816 bytes.

The V0.4 and V0.5 million-row outputs were attached to one SQLite connection and compared both ways with EXCEPT; both differences contained zero rows. Both contained exactly 1,000,000 reconstructed rows. The final database file sizes differed by 20,480 bytes due to physical SQLite layout/order, not logical content.

## Interpretation

**Observed:** V0.5 process peak RSS stayed around 116–117 MiB from 100k through 1M rows in this workload, while V0.4 increased from 178.8 MiB at 100k to 912.5 MiB at 1M. The million-row case therefore demonstrated an 87.2% lower peak RSS. All outputs passed integrity and exact reconstruction checks.

**Observed trade-off:** V0.5 was slower at every measured size, approximately 1.1x to 1.6x longer. The disk staging pass, SQL profiling/grouped validation, and verification add I/O and query overhead. This version addresses memory scaling, not throughput superiority.

**Inference:** The nearly flat V0.5 RSS across tested sizes suggests the bounded batch and SQLite cache strategy is effective for this dataset. It does not establish a strict upper bound for all field widths, very large individual CSV fields, SQLite temporary structures, or other schemas.

**Unknown:** Performance on Windows, SSD vs HDD, network filesystems, high-cardinality million-row data, multi-column dependencies, and real business data remains untested. No multi-threaded path is implemented.

Reproduce smaller cases with python dbforge_v05/benchmark_streaming.py; the one-million-row raw measurements and environment details are in benchmark_streaming_1m.json.
