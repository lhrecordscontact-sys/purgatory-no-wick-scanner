"""Research-only candidate generator. Never edits production strategy or trades.

Deterministic experiments based ONLY on previous TRAIN outcomes. No holdout
metrics are read when generating new candidates.
"""
from dataclasses import replace

def propose(previous, base_variants, limit=8):
    prior=previous.get("results",{})
    ranked=[]
    for name, item in prior.items():
        if name not in base_variants:
            continue
        train=item.get("train",{})
        trades=int(train.get("trades",0))
        profit=float(train.get("net_profit",0))
        if trades>=15:
            ranked.append((profit/max(trades,1),trades,name))
    ranked.sort(reverse=True)
    parents=[name for _,_,name in ranked[:2]] or ["baseline"]
    candidates={}
    for parent in parents:
        params=dict(base_variants[parent])
        for field, values in (
            ("rr",(1.0,1.5,2.0,2.5)),
            ("min_rvol",(1.0,1.5,2.0)),
            ("min_adx",(16.0,22.0,28.0)),
            ("max_entry_extension_atr",(0.75,1.25)),
            ("min_confirmation_body",(0.55,0.70)),
        ):
            for value in values:
                if params.get(field)==value:
                    continue
                trial={**params,field:value}
                name="adaptive_"+parent+"_"+field+"_"+str(value).replace(".","p")
                candidates[name]=trial
                if len(candidates)>=limit:
                    return candidates
    return candidates

def train_rank(report, minimum_trades=30):
    ranked=[]
    for name, value in report.get("results",{}).items():
        m=value.get("train",{})
        n=int(m.get("trades",0))
        if n<minimum_trades:
            continue
        net=float(m.get("net_profit",0))
        pf=m.get("profit_factor")
        if net>0 and pf is not None and float(pf)>1:
            ranked.append({"name":name,"train_trades":n,"train_net":net,
                           "train_profit_factor":pf,"net_per_trade":round(net/n,4)})
    return sorted(ranked,key=lambda x:(x["net_per_trade"],x["train_trades"]),reverse=True)
