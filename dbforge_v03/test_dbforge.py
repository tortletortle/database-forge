import csv, sqlite3, tempfile, unittest, random
from contextlib import closing
from pathlib import Path
from dbforge import generate, discover, load_csv
from benchmark import dataset

class TestDBForge(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_random_fd_equivalence(self):
        for seed in range(30):
            rng=random.Random(seed); rows=[tuple(str(rng.randrange(1+(j+1)*2)) for j in range(7)) for i in range(100)]
            self.assertEqual(discover(rows,7,'baseline')[0],discover(rows,7,'progressive',sample_size=12)[0])
            self.assertEqual(discover(rows,7,'baseline')[0],discover(rows,7,'columnar')[0])
    def test_rare_counterexample(self):
        rows=[(str(i%5),str(i%5)) for i in range(1000)]+[('1','x')]
        from dbforge import valid
        # Explicitly ensure the rare exception is not in this fixed sample.
        self.assertTrue(valid(random.Random(42).sample(rows,10),0,1))
        self.assertNotIn((0,1),discover(rows,2,'progressive',sample_size=10)[0])
    def test_normalization_and_foreign_key(self):
        cols,rows=dataset(1200,'orders'); db=self.path/'orders.sqlite'; r=generate(cols,rows,db)
        self.assertTrue(r['verified']); self.assertGreater(len(r['dimensions']),0)
        with closing(sqlite3.connect(db)) as c:
            c.execute('PRAGMA foreign_keys=ON'); fk=c.execute('PRAGMA foreign_key_list(fact)').fetchall()[0]; col=fk[3]
            with self.assertRaises(sqlite3.IntegrityError): c.execute(f'UPDATE fact SET {col}=? WHERE _seq=1',('absent',))
    def test_duplicate_unicode_and_empty_strings(self):
        cols=['select','a"b','_dbforge_seq','rowid']; rows=[('001','张三','','x'),('001','张三','','x'),('002','李四','z','')]; self.assertTrue(generate(cols,rows,self.path/'special.db')['verified'])
    def test_semantic_guard(self):
        cols,rows=dataset(1200,'rare_conflict'); r=generate(cols,rows,self.path/'guard.db')
        self.assertNotIn('customer_name',[x['key'] for x in r['dimensions']])
        self.assertNotIn('customer_name',[a for x in r['dimensions'] for a in x['attributes']])
    def test_explicit_keys(self):
        cols,rows=dataset(1200,'orders'); r=generate(cols,rows,self.path/'explicit.db',keys=['product_id'])
        self.assertEqual([x['key'] for x in r['dimensions']],['product_id'])
    def test_empty(self): self.assertTrue(generate(['a','b'],[],self.path/'empty.db')['verified'])
    def test_ragged(self):
        p=self.path/'bad.csv'; p.write_text('a,b\n1\n',encoding='utf8')
        with self.assertRaises(ValueError): load_csv(p)
    def test_no_overwrite(self):
        p=self.path/'existing.db'; p.write_bytes(b'unchanged')
        with self.assertRaises(FileExistsError): generate(['a'],[('b',)],p)
        self.assertEqual(p.read_bytes(),b'unchanged')
    def test_csv_lexemes(self):
        p=self.path/'a.csv'; p.write_text('id,v\n001,"a,b"\n002,"line\nbreak"\n',encoding='utf8'); cols,rows=load_csv(p)
        self.assertEqual(rows,[('001','a,b'),('002','line\nbreak')]); self.assertTrue(generate(cols,rows,self.path/'a.db')['verified'])
if __name__=='__main__': unittest.main()
