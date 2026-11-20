import json,random,statistics,tempfile,platform,sys,sqlite3
from pathlib import Path
from dbforge import generate
from benchmark import dataset

def wide(n,seed=317):
    rng=random.Random(seed); cols=['noise_id','noise_label','tiny_id','tiny_tag','major_id','major_name','major_notes','product_id','product_name','region']+[f'noise_{i}' for i in range(12)]
    rows=[]
    for i in range(n):
        a=rng.randrange(800); b=rng.randrange(2); c=rng.randrange(90); d=rng.randrange(150)
        rows.append((f'N{a}',str(rng.randrange(500)),str(b),str(b),f'C{c}',f'Customer {c:03}'*5,f'Notes {c:03}'*8,f'P{d}',f'Product {d:03}'*4,str(c%8),*(str(rng.randrange(50)) for _ in range(12))))
    return cols,rows

def marginal(n,seed=426):
    rng=random.Random(seed); rows=[]
    for i in range(n):
        a=i//2; b=i//3
        rows.append((f'LongIdentifier-{a:06}'*3,str(a%2),f'AnotherIdentifier-{b:06}'*3,str(b%3),str(rng.randrange(2)),str(rng.randrange(3))))
    return ['first_id','a','second_id','b','noise1','noise2'],rows

def run():
    cases=[('orders_holdout',dataset(20000,'orders',17842)),('conflict_holdout',dataset(20000,'rare_conflict',17843)),('high_cardinality_holdout',dataset(20000,'high_cardinality',17844)),('random_wide_holdout',dataset(10000,'wide_random',17845)),('mixed_wide',wide(16000)),('marginal',marginal(12000))]
    out={'environment':{'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'platform':platform.platform()},'repetitions':3,'budget_formula':'2*N or 4*N validation visits; profiling and build excluded','cases':[]}
    with tempfile.TemporaryDirectory() as tmp:
        for label,(cols,rows) in cases:
            n=len(rows); opts={'flat':{'normalize':False},'v01':{},'full_lex':{'method':'budget','strategy':'lexical'},'full_bound':{'method':'budget','strategy':'bound'}}
            opts.update({f'{s}_{k}N':{'method':'budget','strategy':s,'budget':k*n} for k in (2,4) for s in ('lexical','benefit','bound')})
            raw={m:[] for m in opts}
            for rep in range(3):
                order=list(opts); random.Random(729+rep).shuffle(order)
                for m in order:
                    p=Path(tmp)/f'{label}-{rep}-{m}.db'; r=generate(cols,rows,p,**opts[m]); assert r['verified']; raw[m].append(r); p.unlink()
            base=raw['v01'][0]; assert raw['full_lex'][0]['dimensions']==base['dimensions']==raw['full_bound'][0]['dimensions']
            flat=raw['flat'][0]['bytes']; full=base['bytes']; summary={}
            for m,rs in raw.items():
                r=rs[0]; summary[m]={'analysis_ms':round(statistics.median(x['analysis_s'] for x in rs)*1000,3),'total_ms':round(statistics.median(x['total_s'] for x in rs)*1000,3),'bytes':r['bytes'],'payload_gain':sum(x['estimated_payload_saved'] for x in r['dimensions']),'storage_gain_retained':round((flat-r['bytes'])/(flat-full),4) if flat!=full else None,**{k:r[k] for k in ('candidates','pruned','checked','unresolved','visits','budget') if k in r}}
            case={'name':label,'n':n,'width':len(cols),'summary':summary,'raw':raw}; out['cases'].append(case)
            print(label, json.dumps(summary),flush=True)
    Path('benchmark_budget_results.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
if __name__=='__main__': run()
