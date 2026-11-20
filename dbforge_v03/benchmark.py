import csv, json, random, sqlite3, tempfile, time, statistics, platform, sys
from pathlib import Path
from dbforge import discover, generate, load_csv

COLS=['order_id','customer_id','customer_name','region','product_id','product_name','category','quantity','note']
def dataset(n,kind,seed=8301):
    rng=random.Random(seed); rows=[]
    for i in range(n):
        c=rng.randrange(max(2,n//30)); p=rng.randrange(120)
        if kind=='wide_random':
            rows.append(tuple(str(rng.randrange(max(2,n//30))) for _ in range(24))); continue
        if kind=='high_cardinality': c=rng.randrange(max(2,n//2)); p=rng.randrange(max(2,n//3))
        rows.append((f'O{i:07}',f'C{c:06}',f'Customer {c:06} extended name',f'Region {c%12}',f'P{p:06}',f'Product {p:06} extended description',f'Category {p%11}',str(rng.randrange(1,20)),f'Note {rng.randrange(1000)}'))
    if kind=='rare_conflict' and n: rows[-1]=rows[-1][:2]+('Conflicting Name',)+rows[-1][3:]
    return ([f'field_{i}' for i in range(24)] if kind=='wide_random' else COLS),rows

def run():
    output={'environment':{'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'platform':platform.platform()}, 'repetitions':5,'cases':[]}
    with tempfile.TemporaryDirectory() as tmp:
        for kind,n in [('orders',30000),('rare_conflict',30000),('high_cardinality',30000),('wide_random',15000)]:
            cols,rows=dataset(n,kind); times={m:[] for m in ('baseline','progressive','columnar')}; full={m:[] for m in ('flat','normalized')}
            for rep in range(5):
                res={}
                for m in (('baseline','progressive','columnar') if rep%2==0 else ('columnar','progressive','baseline')):
                    start=time.perf_counter(); res[m]=discover(rows,len(cols),m); times[m].append(time.perf_counter()-start)
                assert res['baseline'][0]==res['progressive'][0]==res['columnar'][0]
                for m in (('flat','normalized') if rep%2==0 else ('normalized','flat')):
                    report=generate(cols,rows,Path(tmp)/f'{kind}-{rep}-{m}.sqlite',normalize=m=='normalized'); full[m].append(report)
            if kind=='rare_conflict': assert (1,2) not in res['columnar'][0]
            case={'case':kind,'n':n,'width':len(cols),'fd_count':len(res['progressive'][0]),**res['progressive'][1],
                  'fd_timings_ms':{m:[round(t*1000,3) for t in ts] for m,ts in times.items()},'fd_median_ms':{m:round(statistics.median(ts)*1000,3) for m,ts in times.items()},
                  'generation_median_ms':{m:round(statistics.median(r['total_s'] for r in rs)*1000,3) for m,rs in full.items()},'bytes':{m:rs[0]['bytes'] for m,rs in full.items()},'dimensions':full['normalized'][0]['dimensions'],'verified':all(r['verified'] for rs in full.values() for r in rs)}
            output['cases'].append(case); print(json.dumps(case,ensure_ascii=False),flush=True)
    Path('benchmark_results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__': run()
