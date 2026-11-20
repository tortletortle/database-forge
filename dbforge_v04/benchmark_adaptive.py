import json,random,statistics,tempfile,platform,sys,sqlite3
from pathlib import Path
from dbforge import generate
from benchmark import dataset
from benchmark_budget import wide,marginal


def run():
    cases={'orders':lambda s:dataset(10000,'orders',s),'conflict':lambda s:dataset(10000,'rare_conflict',s),'high_cardinality':lambda s:dataset(10000,'high_cardinality',s),'mixed_wide':lambda s:wide(8000,s),'marginal':lambda s:marginal(8000,s),'no_key':lambda s:dataset(5000,'wide_random',s)}
    out={'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),'seeds':[32191,43811,71279],'cases':[]}
    with tempfile.TemporaryDirectory() as tmp:
        for name,fn in cases.items():
            raw=[]
            for seed in out['seeds']:
                cols,rows=fn(seed); n=len(rows)
                opts={'flat':{'normalize':False},'full':{'method':'budget','strategy':'bound'},'fixed_2N':{'method':'budget','budget':2*n},'fixed_4N':{'method':'budget','budget':4*n},'fixed_8N':{'method':'budget','budget':8*n},'adaptive':{'method':'adaptive'},'adaptive_0':{'method':'adaptive','min_return':0}}
                order=list(opts); random.Random(seed).shuffle(order); reports={}
                for m in order:
                    p=Path(tmp)/f'{name}-{seed}-{m}.sqlite'; r=generate(cols,rows,p,**opts[m]); assert r['verified']; reports[m]=r; p.unlink()
                raw.append({'seed':seed,'n':n,'results':reports})
            summary={}
            for m in opts:
                rr=[x['results'][m] for x in raw]
                gains=[(x['results']['flat']['bytes']-x['results'][m]['bytes'])/(x['results']['flat']['bytes']-x['results']['full']['bytes']) for x in raw if x['results']['flat']['bytes']!=x['results']['full']['bytes']]
                summary[m]={'total_ms':round(statistics.median(r['total_s']*1000 for r in rr),2),'analysis_ms':round(statistics.median(r['analysis_s']*1000 for r in rr),2),'visits':statistics.median(r.get('visits',0) for r in rr),'bytes':statistics.median(r['bytes'] for r in rr),'gain_retained':round(statistics.median(gains),4) if gains else None}
            out['cases'].append({'name':name,'summary':summary,'raw':raw}); print(name,json.dumps(summary),flush=True)
    Path('benchmark_adaptive_results.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
if __name__=='__main__': run()
