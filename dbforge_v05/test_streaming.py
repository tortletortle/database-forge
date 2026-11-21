import csv
import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'dbforge_v04'))

from dbforge import generate
from streaming import generate_csv_streaming
from benchmark import dataset


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_csv(self, cols, rows, name='input.csv'):
        path = self.root / name
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(rows)
        return path

    def test_roundtrip_and_same_plan_as_v04(self):
        for kind in ('orders', 'rare_conflict', 'high_cardinality', 'wide_random'):
            cols, rows = dataset(1500, kind, 171)
            src = self.write_csv(cols, rows, kind + '.csv')
            old = generate(cols, rows, self.root / (kind + '-old.db'), method='fast')
            new = generate_csv_streaming(src, self.root / (kind + '-new.db'), batch_size=37,
                                         validation_budget=len(rows) * 20)
            self.assertTrue(new['verified'])
            self.assertEqual(old['dependencies'], new['dependencies'])
            self.assertEqual(old['dimensions'], new['dimensions'])
            self.assertEqual(old['bytes'], new['output_bytes'])

    def test_budget_is_full_determinant_scans(self):
        cols, rows = dataset(1000, 'orders', 19)
        src = self.write_csv(cols, rows)
        report = generate_csv_streaming(src, self.root / 'budget.db', validation_budget=1000)
        self.assertLessEqual(report['validation_rows_scanned'], 1000)
        self.assertLessEqual(report['keys_checked'], 1)
        self.assertTrue(report['verified'])

    def test_zero_budget_generates_flat_snapshot(self):
        cols, rows = dataset(300, 'orders', 29)
        src = self.write_csv(cols, rows)
        report = generate_csv_streaming(src, self.root / 'zero.db', validation_budget=0)
        self.assertEqual(report['dimensions'], [])
        self.assertEqual(report['validation_rows_scanned'], 0)
        self.assertTrue(report['verified'])

    def test_batch_sizes_identical(self):
        cols, rows = dataset(600, 'orders', 31)
        src = self.write_csv(cols, rows)
        a = generate_csv_streaming(src, self.root / 'a.db', batch_size=1, validation_budget=10000)
        b = generate_csv_streaming(src, self.root / 'b.db', batch_size=257, validation_budget=10000)
        self.assertEqual(a['dependencies'], b['dependencies'])
        self.assertEqual(a['dimensions'], b['dimensions'])
        self.assertEqual(a['output_bytes'], b['output_bytes'])

    def test_unicode_nul_empty_and_quoted_newline(self):
        cols = ['customer_id', 'name', 'note', '_dbforge_seq']
        rows = [('1', '张三', 'a\x00b', ''), ('1', '张三', 'line1\nline2', ''),
                ('2', '李四', '', 'z')]
        src = self.write_csv(cols, rows)
        report = generate_csv_streaming(src, self.root / 'special.db', validation_budget=100)
        self.assertTrue(report['verified'])
        with sqlite3.connect(self.root / 'special.db') as cx:
            got = cx.execute('SELECT "customer_id", "name", "note", "_dbforge_seq" FROM original_data ORDER BY "_dbforge_seq"').fetchall()
        self.assertEqual(got, rows)

    def test_empty_file_with_header(self):
        src = self.write_csv(['id', 'value'], [])
        report = generate_csv_streaming(src, self.root / 'empty.db')
        self.assertTrue(report['verified'])
        self.assertEqual(report['rows'], 0)

    def test_ragged_row_rejected_and_no_output(self):
        src = self.root / 'bad.csv'
        src.write_text('a,b\n1\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            generate_csv_streaming(src, self.root / 'bad.db')
        self.assertFalse((self.root / 'bad.db').exists())

    def test_duplicate_headers_rejected(self):
        src = self.root / 'dup.csv'
        src.write_text('A,a\n1,2\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            generate_csv_streaming(src, self.root / 'dup.db')

    def test_unknown_explicit_key(self):
        src = self.write_csv(['id', 'v'], [('1', 'a')])
        with self.assertRaises(ValueError):
            generate_csv_streaming(src, self.root / 'unknown.db', keys=['missing'])

    def test_no_overwrite(self):
        src = self.write_csv(['id'], [('1',)])
        out = self.root / 'existing.db'
        out.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            generate_csv_streaming(src, out)
        self.assertEqual(out.read_bytes(), b'keep')

    def test_invalid_options(self):
        src = self.write_csv(['id'], [('1',)])
        for kwargs in ({'batch_size': 0}, {'batch_size': True}, {'cache_mib': 0},
                       {'validation_budget': -1}, {'min_return': -1},
                       {'min_return': float('nan')}, {'min_return': float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate_csv_streaming(src, self.root / ('bad-' + str(len(kwargs)) + '.db'), **kwargs)

    def test_no_key_fallback(self):
        cols, rows = dataset(300, 'wide_random', 37)
        src = self.write_csv(cols, rows)
        report = generate_csv_streaming(src, self.root / 'no-key.db')
        self.assertEqual(report['candidate_keys'], 0)
        self.assertEqual(report['dimensions'], [])
        self.assertTrue(report['verified'])


if __name__ == '__main__':
    unittest.main()