"""V0.3 experimental marginal-return FD scheduler for lossless snapshots."""
from collections import Counter, defaultdict
from math import isfinite
import random


def discover_adaptive(rows, width, allowed, budget=None, min_return=2.0, pilot_size=128, seed=41, evidence=None):
    """Return fully validated unary FDs; budget counts row-pair visits only.

    min_return is a heuristic minimum potential UTF-8 bytes saved per
    successful full validation visit, not a guarantee of actual disk savings.
    A default cap of 8*N is a policy limit, not a wall-clock deadline.
    """
    n=len(rows)
    cap=8*n if budget is None else budget
    if not isinstance(cap,int) or isinstance(cap,bool) or cap<0:
        raise ValueError('budget must be a nonnegative integer or None')
    if not isfinite(min_return) or min_return<0:
        raise ValueError('min_return must be finite and nonnegative')
    if not isinstance(pilot_size,int) or pilot_size<0:
        raise ValueError('pilot_size must be a nonnegative integer')
    if evidence is not None: evidence.clear()
    s=dict(candidates=0,pruned=0,checked=0,rejected=0,accepted=0,unresolved=0,
           visits=0,budget=cap,strategy='adaptive',min_return=min_return,
           threshold_pruned=0,early_rejected=0,stop_reason='exhausted')
    if not n or allowed==set() or cap<n:
        s.update(profiling_skipped=True,stop_reason='no_complete_validation_possible' if n and cap<n else 'no_eligible_data')
        return [],s
    columns=list(zip(*rows)); counts=[]; totals=[]; distinct=[]; minima=[]
    for col in columns:
        freq=Counter(col); lengths={v:len(v.encode('utf-8')) for v in freq}
        counts.append(len(freq)); totals.append(sum(freq[v]*l for v,l in lengths.items()))
        distinct.append(sum(lengths.values())); minima.append(min(lengths.values()))
    if evidence is not None: evidence["key_costs"]=distinct; evidence["gains"]={}
    pairs=[]; aggregate=defaultdict(int)
    for i in range(width):
        if allowed is not None and i not in allowed: continue
        if not 1<counts[i]<n: continue
        for j in range(width):
            if i==j or not 1<counts[j]<=counts[i]: continue
            ub=totals[j]-distinct[j]-(counts[i]-counts[j])*minima[j]
            estimate=totals[j]*(1-counts[i]/n)
            pairs.append((i,j,ub,estimate)); aggregate[i]+=max(0,ub)
    s['candidates']=len(pairs)
    pairs=[p for p in pairs if p[2]>0 and aggregate[p[0]]>distinct[p[0]]]
    s['pruned']=s['candidates']-len(pairs)
    # The threshold is a policy, unlike the safe positive-payload pruning above.
    keep=[p for p in pairs if p[2]>=min_return*n]
    s['threshold_pruned']=len(pairs)-len(keep)
    s['pruned']+=s['threshold_pruned']; pairs=keep
    sample=random.Random(seed).sample(range(n),min(pilot_size,n)); sampled=set(sample)
    order=sample+[k for k in range(n) if k not in sampled]
    best={}; opened=set(); result=[]
    while pairs:
        if cap-s['visits']<n:
            s['stop_reason']='budget'; break
        # Alternate determinants can still win after key-cost amortization.
        # Deprioritize, rather than discard, already-covered dependents.
        remaining=Counter(p[0] for p in pairs)
        def rank(p):
            i,j,ub,estimate=p
            novelty=max(0,estimate-best.get(j,0))
            amortized=distinct[i]/remaining[i] if i not in opened else 0
            return (novelty-amortized, estimate, ub, -i, -j)
        i,j,ub,estimate=max(pairs,key=rank); pairs.remove((i,j,ub,estimate))
        seen={}; before=s['visits']
        for k in order:
            x,y=columns[i][k],columns[j][k]; s['visits']+=1
            if seen.setdefault(x,y)!=y:
                s['rejected']+=1
                if s['visits']-before<=len(sample): s['early_rejected']+=1
                break
        else:
            result.append((i,j)); s['accepted']+=1; opened.add(i)
            gain=totals[j]-sum(len(v.encode('utf-8')) for v in seen.values())
            if evidence is not None: evidence["gains"][i,j]=gain
            best[j]=max(best.get(j,0),gain)
        s['checked']+=1
    s['unresolved']=len(pairs)
    if not pairs and s['threshold_pruned']: s['stop_reason']='return_threshold'
    return sorted(result),s
