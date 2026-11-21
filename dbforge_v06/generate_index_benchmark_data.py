"""Generate the three deterministic synthetic CSV layouts used in V0.6 tests.

The generator streams rows directly to CSV and does not build a Python list of
all records. At --rows 1000000, customer_sorted intentionally emits 999,990
rows because it uses 30 records for each of floor(rows / 30) customer IDs.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

HEADER = ['order_id', 'customer_id', 'customer_name', 'region', 'product_id',
          'product_name', 'category', 'quantity', 'note']


def row(seq: int, customer: int, product: int, rng: random.Random,
        region_mod: int = 17, category_mod: int = 13) -> list[str]:
    return [f'O{seq:08}', f'C{customer:07}',
            f'Customer {customer:07} extended name', f'Region {customer % region_mod}',
            f'P{product:07}', f'Product {product:07} extended description',
            f'Category {product % category_mod}', str(rng.randrange(1, 20)),
            f'Note {rng.randrange(10000)}']


def write_random_orders(path: Path, n: int):
    rng = random.Random(8301 + n)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for i in range(n):
            customer = rng.randrange(max(2, n // 30))
            product = rng.randrange(1200)
            writer.writerow(row(i, customer, product, rng))
    return n


def write_high_cardinality(path: Path, n: int):
    rng = random.Random(8301 + n)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for i in range(n):
            customer = rng.randrange(max(2, n // 2))
            product = rng.randrange(max(2, n // 3))
            writer.writerow(row(i, customer, product, rng, region_mod=12, category_mod=11))
    return n


def write_customer_sorted(path: Path, n: int):
    rng = random.Random(92741)
    seq = 0
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for customer in range(n // 30):
            for _ in range(30):
                product = rng.randrange(1200)
                seq += 1
                writer.writerow(row(seq, customer, product, rng))
    return seq


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=1_000_000)
    parser.add_argument('--output-dir', type=Path, default=Path('dbforge_v06_data'))
    args = parser.parse_args()
    if args.rows < 30:
        parser.error('rows must be at least 30')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        ('orders_random', write_random_orders),
        ('high_cardinality', write_high_cardinality),
        ('customer_sorted', write_customer_sorted),
    ]
    for name, writer in cases:
        path = args.output_dir / f'{name}.csv'
        actual_rows = writer(path, args.rows)
        print(f'{name}: rows={actual_rows:,} bytes={path.stat().st_size:,} path={path}')


if __name__ == '__main__':
    main()
