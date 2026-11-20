import json,random,statistics,tempfile,platform,sys,sqlite3
from pathlib import Path
from dbforge import generate
from benchmark import dataset
from benchmark_budget import wide,marginal


def run():
    cases={'orders':lambda s:dataset(40000,'orders',s),'conflict':lambda s:dataset(40000,'rare_conflict',s),'high_cardinality':lambda s:dataset(40000,'high_cardinality',s),'mixed_wide':lambda s:wide(25000,s),'marginal':lambda s:marginal(25000,s),'no_key':lambda s:dataset(20000,'wide_random',s)}
    out={'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),'seeds':[55173,68323,82031],'repeats':2,'cases':[]}
    with tempfile.TemporaryDirectory() as tmp:
        for name,fn in cases.items():
            raw=[]
            for seed in out['seeds']:
                cols,rows=fn(seed)
                for repeat in range(out['repeats']):
                    order=['adaptive','cached','fast']; random.Random(seed+repeat).shuffle(order); reports={}
                    for m in order:
                        p=Path(tmp)/f'{name}-{seed}-{repeat}-{m}.sqlite'; r=generate(cols,rows,p,method=m); assert r['verified']; reports[m]=r; p.unlink()
                    for m in ('cached','fast'):
                        for k in ('dependencies','dimensions','visits','bytes'):
                            assert reports[m][k]==reports['adaptive'][k],(name,k)
                    raw.append({'seed':seed,'repeat':repeat,'n':len(rows),'results':reports})
            summary={}
            for m in ('adaptive','cached','fast'):
                rr=[x['results'][m] for x in raw]
                summary[m]={k.replace('_s','_ms'):round(statistics.median(r[k]*1000 for r in rr),2) for k in ('total_s','analysis_s','build_s','validation_s')}
                summary[m]['paired_speedup']=round(statistics.median(x['results']['adaptive']['total_s']/x['results'][m]['total_s'] for x in raw),3)
                summary[m]['wins']=sum(x['results'][m]['total_s']<x['results']['adaptive']['total_s'] for x in raw)
            out['cases'].append({'name':name,'summary':summary,'raw':raw}); print(name,json.dumps(summary),flush=True)
    Path('benchmark_fast_results.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
if __name__=='__main__': run()
