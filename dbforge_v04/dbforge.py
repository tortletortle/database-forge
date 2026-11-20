"""DBForge V0.4: lossless snapshot synthesis for rectangular CSV data."""
import argparse, csv, json, random, sqlite3, tempfile, time, os
from pathlib import Path
from collections import defaultdict
from operator import itemgetter
from itertools import zip_longest
from budget import discover_budget


def load_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        cols = next(reader, [])
        if not cols or any(not c or '\x00' in c for c in cols) or len({c.casefold() for c in cols}) != len(cols):
            raise ValueError('CSV header must have nonempty, case-insensitively unique names')
        rows = [tuple(r) for r in reader]
    if any(len(r) != len(cols) for r in rows):
        raise ValueError('Ragged CSV rows')
    return cols, rows


def candidates(rows, width):
    if not rows: return []
    counts = [len(set(r[i] for r in rows)) for i in range(width)]
    # Restrict to nonconstant, nonunique determinants and nonconstant dependents.
    return [(i,j) for i in range(width) for j in range(width)
            if i != j and 1 < counts[i] < len(rows) and 1 < counts[j] <= counts[i]]


def valid(rows, i, j):
    seen = {}
    for r in rows:
        if r[i] in seen:
            if seen[r[i]] != r[j]: return False
        else: seen[r[i]] = r[j]
    return True


def discover(rows, width, method='columnar', sample_size=512):
    if method == 'columnar':
        if not rows: return [], {'candidates':0,'survivors':0}
        # Column projections are shared by cardinality and pair validation.
        columns = list(zip(*rows))
        counts = [len(set(values)) for values in columns]
        pairs = [(i,j) for i in range(width) for j in range(width) if i!=j and 1<counts[i]<len(rows) and 1<counts[j]<=counts[i]]
        result=[]
        for i,j in pairs:
            seen={}; put=seen.setdefault
            for x,y in zip(columns[i],columns[j]):
                if put(x,y)!=y: break
            else: result.append((i,j))
        return result, {'candidates':len(pairs),'survivors':len(pairs)}
    pairs = candidates(rows, width)
    if method == 'baseline':
        return [(i,j) for i,j in pairs if valid(rows,i,j)], {'candidates':len(pairs),'survivors':len(pairs)}
    sample = random.Random(42).sample(rows, min(sample_size,len(rows)))
    survivors = [(i,j) for i,j in pairs if valid(sample,i,j)]
    # Each determinant shares one representative map; full stream eliminates failures.
    grouped = defaultdict(list)
    for i,j in survivors: grouped[i].append(j)
    result = []
    for i, js in grouped.items():
        seen = {}; active = set(js)
        for r in rows:
            if not active: break
            old = seen.get(r[i])
            if old is None: seen[r[i]] = r
            else: active.difference_update(j for j in tuple(active) if old[j] != r[j])
        result.extend((i,j) for j in active)
    return sorted(result), {'candidates':len(pairs),'survivors':len(survivors)}


def plan(rows, fds, allowed_keys=None, evidence=None):
    """Greedy disjoint star decomposition; estimates UTF-8 payload only."""
    if not fds: return []
    by_key = defaultdict(list)
    for i,j in fds:
        if allowed_keys is None or i in allowed_keys: by_key[i].append(j)
    if not by_key: return []
    if evidence is not None:
        proposals=[(i,evidence['key_costs'][i],{j:evidence['gains'][i,j] for j in js}) for i,js in by_key.items()]
    else:
        total = [0]*len(rows[0]) if rows else []
        for r in rows:
            for j,v in enumerate(r): total[j] += len(v.encode('utf-8'))
        proposals=[]
        for i, js in by_key.items():
            representatives = {r[i]:r for r in rows}
            key_cost = sum(len(v.encode('utf-8')) for v in representatives)
            gains = {j: total[j]-sum(len(r[j].encode('utf-8')) for r in representatives.values()) for j in js}
            proposals.append((i,key_cost,gains))
    chosen=[]; reserved=set(); removed=set()
    while True:
        choices=[]
        for i,cost,gains in proposals:
            if i in reserved or i in removed: continue
            js=tuple(sorted(j for j,g in gains.items() if j not in reserved and j not in removed and g>0))
            gain=sum(gains[j] for j in js)-cost
            if js and gain>0: choices.append((gain,i,js))
        if not choices: break
        gain,i,js=max(choices,key=lambda x:(x[0],-x[1],x[2]))
        chosen.append((i,js,gain)); reserved.add(i); removed.update(js)
    return chosen


def q(name): return '"'+name.replace('"','""')+'"'


def generate(cols, rows, destination, method='columnar', normalize=True, keys=None, unrestricted=False, budget=None, strategy='bound', min_return=2.0):
    start=time.perf_counter()
    # Conservative semantic policy: accept named identifier candidates, or explicit keys.
    # No field-name heuristic is a proof of future business semantics.
    if keys is not None and any(k not in cols for k in keys): raise ValueError('Unknown explicit entity key')
    allowed = None if unrestricted else {i for i,c in enumerate(cols) if (c in keys if keys is not None else c.lower()=='id' or c.lower().endswith(('_id','_code')))}
    evidence = {} if method in ('cached','fast') else None
    if normalize and method in ('adaptive','cached','fast'):
        from adaptive import discover_adaptive
        fds,stats=discover_adaptive(rows,len(cols),allowed,budget,min_return,evidence=evidence)
    elif normalize and method=='budget':
        fds,stats=discover_budget(rows,len(cols),allowed,budget,strategy)
    else:
        fds,stats=discover(rows,len(cols),method) if normalize else ([],{})
    groups=plan(rows,fds,allowed,evidence=evidence) if normalize else []
    analysis_s=time.perf_counter()-start
    destination=Path(destination)
    if destination.exists(): raise FileExistsError(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Use an adjacent temporary file and publish only after full validation.
    fd,tmp=tempfile.mkstemp(prefix='.dbforge-',suffix='.sqlite',dir=destination.parent); os.close(fd)
    cx=None
    try:
        cx=sqlite3.connect(tmp)
        cx.execute('PRAGMA foreign_keys=ON')
        cx.execute('BEGIN')
        removed={j for _,js,_ in groups for j in js}
        base=[j for j in range(len(cols)) if j not in removed]
        # Generated physical column names avoid collisions with SQL and SQLite rowid aliases.
        c=lambda j:f'c{j}'
        owner={j:'f' for j in base}
        joins=[]; constraints=[]
        for k,(i,js,gain) in enumerate(groups):
            t=f'dim_{k}'; indices=(i,)+js
            defs=[f'{c(j)} TEXT NOT NULL'+(' PRIMARY KEY' if j==i else '') for j in indices]
            cx.execute(f'CREATE TABLE {t} ({", ".join(defs)})')
            representatives={r[i]:r for r in rows}
            dim_rows = map(itemgetter(*indices), representatives.values()) if method=="fast" else (tuple(r[j] for j in indices) for r in representatives.values())
            cx.executemany(f'INSERT INTO {t} VALUES ({",".join("?" for _ in indices)})', dim_rows)
            constraints.append(f'FOREIGN KEY ({c(i)}) REFERENCES {t}({c(i)})')
            joins.append(f'JOIN {t} ON f.{c(i)}={t}.{c(i)}')
            owner.update({j:t for j in js})
        defs=['_seq INTEGER PRIMARY KEY']+[f'{c(j)} TEXT NOT NULL' for j in base]+constraints
        cx.execute(f'CREATE TABLE fact ({", ".join(defs)})')
        if method=='fast':
            if len(base)==len(cols): projected=iter(rows)
            elif len(base)==1: projected=((r[base[0]],) for r in rows)
            else: projected=map(itemgetter(*base),rows)
            fact_rows=((n,*r) for n,r in enumerate(projected,1))
        else:
            fact_rows=((n,*[r[j] for j in base]) for n,r in enumerate(rows,1))
        cx.executemany(f'INSERT INTO fact VALUES ({",".join("?" for _ in range(len(base)+1))})',fact_rows)
        internal='_dbforge_seq'
        while internal.casefold() in {x.casefold() for x in cols}: internal+='_' 
        cx.execute('CREATE VIEW original_data AS SELECT '+', '.join(f'{owner[j]}.{c(j)} AS {q(name)}' for j,name in enumerate(cols))+f', f._seq AS {q(internal)} FROM fact f '+ ' '.join(joins))
        # Metadata maps source names and explicit text encoding policy.
        cx.execute('CREATE TABLE dbforge_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        cx.executemany('INSERT INTO dbforge_metadata VALUES (?,?)', [('columns',json.dumps(cols,ensure_ascii=False)),('sequence_column',internal),('policy','All CSV cells are exact strings; empty string is not SQL NULL.')])
        cx.commit()
        build_s=time.perf_counter()-start-analysis_s
        vstart=time.perf_counter()
        if cx.execute('PRAGMA integrity_check').fetchone()!=('ok',) or cx.execute('PRAGMA foreign_key_check').fetchone() is not None: raise RuntimeError('Integrity check failed')
        cursor=cx.execute('SELECT '+','.join(q(x) for x in cols)+f' FROM original_data ORDER BY {q(internal)}')
        if method=='fast':
            missing=object()
            for actual,expected in zip_longest(cursor,rows,fillvalue=missing):
                if actual!=expected: raise RuntimeError('Round-trip mismatch or row count mismatch')
        else:
            for expected in rows:
                if cursor.fetchone()!=expected: raise RuntimeError('Round-trip mismatch')
            if cursor.fetchone() is not None: raise RuntimeError('Unexpected extra rows')
        validation_s=time.perf_counter()-vstart
        cx.close(); cx=None
        # Hard link creation is atomic and will not overwrite an existing destination.
        os.link(tmp,destination)
        return {'rows':len(rows),'columns':len(cols),'dependencies':[[cols[i],cols[j]] for i,j in fds],**stats,
                'dimensions':[{'key':cols[i],'attributes':[cols[j] for j in js],'estimated_payload_saved':gain} for i,js,gain in groups],
                'key_policy':'unrestricted snapshot' if unrestricted else ('explicit' if keys is not None else 'identifier-name heuristic'),'analysis_s':analysis_s,'build_s':build_s,'validation_s':validation_s,'total_s':time.perf_counter()-start,'bytes':destination.stat().st_size,'verified':True}
    finally:
        if cx is not None: cx.close()
        Path(tmp).unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('csv'); p.add_argument('database'); p.add_argument('--flat',action='store_true'); p.add_argument('--keys',nargs='+'); p.add_argument('--unrestricted',action='store_true'); p.add_argument('--budget',type=int,help='Maximum row-pair validation visits, excludes profiling/build'); p.add_argument('--strategy',choices=['lexical','benefit','bound','adaptive','fast'],default='bound'); p.add_argument('--min-return',type=float,default=2.0); a=p.parse_args()
    cols,rows=load_csv(a.csv); print(json.dumps(generate(cols,rows,a.database,normalize=not a.flat,keys=a.keys,unrestricted=a.unrestricted,method=a.strategy if a.strategy in ('adaptive','fast') else 'budget',budget=a.budget,strategy=a.strategy,min_return=a.min_return),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
