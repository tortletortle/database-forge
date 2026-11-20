import random, sqlite3, tempfile, unittest
from pathlib import Path
from contextlib import closing
from dbforge import generate, plan
from adaptive import discover_adaptive
from benchmark import dataset
from benchmark_budget import wide, marginal

class FastTests(unittest.TestCase):
    def test_exact_cached_plan(self):
        for seed in range(40):
            rng=random.Random(seed)
            rows=[(str(a:=rng.randrange(9)),str(a)*5,'中'+str(a),str(b:=rng.randrange(5)),str(b)*4,str(rng.randrange(3))) for _ in range(150)]
            if seed%2: rows[-1]=(*rows[-1][:2],'rare',*rows[-1][3:])
            for cap in (0,150,600,1200,None):
                evidence={}; a,s=discover_adaptive(rows,6,None,cap,0,evidence=evidence)
                b,t=discover_adaptive(rows,6,None,cap,0)
                self.assertEqual((a,s),(b,t))
                self.assertEqual(plan(rows,a,evidence=evidence),plan(rows,b))
    def check_pair(self,cols,rows,**opts):
        with tempfile.TemporaryDirectory() as tmp:
            a=generate(cols,rows,Path(tmp)/'old.db',method='adaptive',**opts)
            b=generate(cols,rows,Path(tmp)/'new.db',method='fast',**opts)
            for k in ('dependencies','dimensions','visits','bytes','verified'):
                self.assertEqual(a.get(k),b.get(k),k)
            def read_db(p):
                with closing(sqlite3.connect(p)) as c:
                    return c.execute('SELECT * FROM original_data ORDER BY '+ '"'+c.execute("SELECT value FROM dbforge_metadata WHERE key='sequence_column'").fetchone()[0]+'"').fetchall(),c.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall()
            self.assertEqual(read_db(Path(tmp)/'old.db'),read_db(Path(tmp)/'new.db'))
    def test_synthetic_families(self):
        for seed in (17,39):
            for cols,rows in (dataset(1500,'orders',seed),dataset(1500,'rare_conflict',seed),dataset(1500,'high_cardinality',seed),wide(1500,seed),marginal(1500,seed),dataset(500,'wide_random',seed)):
                self.check_pair(cols,rows)
    def test_one_base_column(self):
        self.check_pair(['a_id','value'],[(str(i%3),'长'*30+str(i%3)) for i in range(500)])
    def test_special_text(self):
        self.check_pair(['a_id','_dbforge_seq','"rowid"'],[(str(i%3),'中\x00'+str(i%3),'') for i in range(500)],min_return=0)
    def test_empty_and_budget(self):
        self.check_pair(['x_id','a'],[])
        self.check_pair(['x_id','a'],[('1','b'),('1','b'),('2','c')],budget=0)
    def test_flat_single_column(self):
        self.check_pair(['v'],[('a',),('a',),('b',)],normalize=False)
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.db'; p.write_bytes(b'original')
            with self.assertRaises(FileExistsError): generate(['a'],[('b',)],p,method='fast')
            self.assertEqual(p.read_bytes(),b'original')
if __name__=='__main__': unittest.main()
