"""Budgeted, exact-on-accept unary FD discovery for snapshot synthesis."""
from collections import Counter, defaultdict


def discover_budget(rows, width, allowed, budget=None, strategy='benefit'):
    if budget is not None and (not isinstance(budget,int) or budget<0):
        raise ValueError('budget must be a nonnegative integer or None')
    if strategy not in ('lexical','benefit','bound'):
        raise ValueError('unknown strategy')
    n=len(rows)
    stats=dict(candidates=0,pruned=0,checked=0,rejected=0,accepted=0,unresolved=0,visits=0,budget=budget,strategy=strategy)
    if not n or allowed == set() or budget == 0:
        stats['profiling_skipped']=True
        return [],stats
    columns=list(zip(*rows)); counts=[]; totals=[]; distinct_bytes=[]; min_bytes=[]
    for c in columns:
        freq=Counter(c); lengths={v:len(v.encode('utf-8')) for v in freq}
        counts.append(len(freq)); totals.append(sum(freq[v]*l for v,l in lengths.items()))
        distinct_bytes.append(sum(lengths.values())); min_bytes.append(min(lengths.values()))
    pairs=[]; bounds=defaultdict(int)
    for i in range(width):
        if allowed is not None and i not in allowed: continue
        if not 1<counts[i]<n: continue
        for j in range(width):
            if j==i or not 1<counts[j]<=counts[i]: continue
            # A valid FD requires one value per distinct determinant; each distinct
            # RHS value occurs at least once among these representatives.
            ub=totals[j]-distinct_bytes[j]-(counts[i]-counts[j])*min_bytes[j]
            score=totals[j]*(1-counts[i]/n)
            pairs.append((i,j,ub,score)); bounds[i]+=max(0,ub)
    stats['candidates']=len(pairs)
    if strategy=='bound':
        # Key duplication is paid once for a dimension, not once per attribute.
        # If even the sum of individual valid upper bounds cannot cover it,
        # no positive-payload star around this key is possible.
        pairs=[p for p in pairs if p[2]>0 and bounds[p[0]]>distinct_bytes[p[0]]]
        stats['pruned']=stats['candidates']-len(pairs)
    if strategy!='lexical': pairs.sort(key=lambda p:(-p[3],-p[2],p[0],p[1]))
    result=[]
    for i,j,_,_ in pairs:
        if budget is not None and stats['visits']>=budget: break
        seen={}; complete=True; valid=True
        for x,y in zip(columns[i],columns[j]):
            if budget is not None and stats['visits']>=budget:
                complete=False; break
            stats['visits']+=1
            if seen.setdefault(x,y)!=y:
                valid=False; break
        if not complete: break
        stats['checked']+=1
        if valid: result.append((i,j)); stats['accepted']+=1
        else: stats['rejected']+=1
    stats['unresolved']=len(pairs)-stats['checked']
    return sorted(result),stats
