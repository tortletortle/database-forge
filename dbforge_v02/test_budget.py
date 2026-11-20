import random, tempfile, unittest
from pathlib import Path
from budget import discover_budget
from dbforge import discover,plan,valid,generate
from benchmark import dataset

class BudgetTests(unittest.TestCase):
    def test_budget_and_exactness(self):
        cols,rows=dataset(500,'rare_conflict')
        for budget in (0,1,499,500,1000,10000,None):
            for strategy in ('lexical','benefit','bound'):
                fds,s=discover_budget(rows,len(cols),None,budget,strategy)
                if budget is not None: self.assertLessEqual(s['visits'],budget)
                self.assertTrue(all(valid(rows,*fd) for fd in fds))
                self.assertEqual(s['candidates'],s['pruned']+s['checked']+s['unresolved'])
                self.assertEqual(s['checked'],s['accepted']+s['rejected'])
                self.assertNotIn((1,2),fds)
    def test_bound_preserves_plan(self):
        for seed in range(60):
            rng=random.Random(seed); rows=[]
            for n in range(60):
                a=rng.randrange(5); b=rng.randrange(8)
                rows.append((str(a),str(a)*rng.choice([1,1,1,2]),str(b),str(b)*4,str(a%2),str(b%2),str(rng.randrange(3))))
            full,_=discover(rows,7); fds,s=discover_budget(rows,7,None,None,'bound')
            self.assertEqual(plan(rows,full),plan(rows,fds))
    def test_exact_full_lexical(self):
        cols,rows=dataset(1200,'orders'); allowed={1,4}
        full,_=discover(rows,len(cols)); fds,_=discover_budget(rows,len(cols),allowed,None,'lexical')
        self.assertEqual(fds,[p for p in full if p[0] in allowed])
    def test_zero_budget_roundtrip(self):
        cols,rows=dataset(400,'orders')
        with tempfile.TemporaryDirectory() as tmp:
            r=generate(cols,rows,Path(tmp)/'a.db',method='budget',budget=0)
            self.assertTrue(r['verified']); self.assertEqual(r['dimensions'],[])
    def test_partial_budget_roundtrip(self):
        cols,rows=dataset(1200,'rare_conflict')
        with tempfile.TemporaryDirectory() as tmp:
            r=generate(cols,rows,Path(tmp)/'a.db',method='budget',budget=2400)
            self.assertTrue(r['verified']); self.assertLessEqual(r['visits'],2400)
    def test_invalid_budget(self):
        with self.assertRaises(ValueError): discover_budget([('a',)],1,None,-1)
if __name__=='__main__': unittest.main()
