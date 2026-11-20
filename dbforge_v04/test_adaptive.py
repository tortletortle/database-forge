import random, tempfile, unittest
from pathlib import Path
from adaptive import discover_adaptive
from dbforge import discover, generate, plan, valid
from benchmark import dataset

class AdaptiveTests(unittest.TestCase):
    def test_budget_and_exactness(self):
        cols,rows=dataset(1200,'rare_conflict')
        for budget in (0,1199,1200,2400,4800,None):
            fds,s=discover_adaptive(rows,len(cols),None,budget)
            self.assertLessEqual(s['visits'],s['budget'])
            self.assertEqual(s['candidates'],s['pruned']+s['checked']+s['unresolved'])
            self.assertEqual(s['checked'],s['accepted']+s['rejected'])
            self.assertTrue(all(valid(rows,*fd) for fd in fds))
            self.assertNotIn((1,2),fds)
    def test_unlimited_zero_threshold_matches_plan(self):
        for seed in range(30):
            rng=random.Random(seed)
            rows=[(str(a:=rng.randrange(6)),str(a)*4,str(b:=rng.randrange(8)),str(b)*3,str(rng.randrange(2))) for _ in range(100)]
            full,_=discover(rows,5); actual,_=discover_adaptive(rows,5,None,10000,0)
            self.assertEqual(plan(rows,full),plan(rows,actual))
    def test_sample_not_acceptance(self):
        rows=[(str(i%4),'value'+str(i%4)) for i in range(2000)]+[('1','rare')]
        for seed in range(15):
            fds,s=discover_adaptive(rows,2,{0},None,0,16,seed)
            self.assertNotIn((0,1),fds)
    def test_low_return_policy(self):
        rows=[(str(i%2),str(i%2)) for i in range(1000)]
        fds,s=discover_adaptive(rows,2,{0},None,2)
        self.assertEqual(fds,[]); self.assertEqual(s['visits'],0)
        self.assertGreater(s['threshold_pruned'],0)
    def test_output_roundtrip(self):
        cols,rows=dataset(1200,'orders')
        with tempfile.TemporaryDirectory() as tmp:
            r=generate(cols,rows,Path(tmp)/'a.db',method='adaptive')
            self.assertTrue(r['verified']); self.assertGreater(len(r['dimensions']),0)
    def test_no_key(self):
        fds,s=discover_adaptive([('a','b')],2,set())
        self.assertEqual(fds,[]); self.assertTrue(s['profiling_skipped'])
    def test_bad_policy(self):
        for bad in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): discover_adaptive([('a',)],1,None,min_return=bad)
if __name__=='__main__': unittest.main()
