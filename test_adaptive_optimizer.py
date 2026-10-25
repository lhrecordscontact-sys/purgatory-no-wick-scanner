from adaptive_optimizer import CHAMPION_NAME, CHAMPION_PARAMS, propose, signature, train_rank

def test_generates_bounded_candidates_from_champion_not_holdout():
    previous={"results":{CHAMPION_NAME:{"train":{"trades":35,"net_profit":5},
                                        "holdout":{"net_profit":-999}}}}
    variants={CHAMPION_NAME:CHAMPION_PARAMS}
    a=propose(previous,variants,limit=5)
    assert len(a)==5
    assert all(name.startswith("challenge_") for name in a)
    assert all(p["signal_mode"]=="momentum_break" and
               sum(p.get(k)!=CHAMPION_PARAMS.get(k) for k in p if k!="signal_mode")==1
               for p in a.values())
    previous["results"][CHAMPION_NAME]["holdout"]["net_profit"]=999999
    assert propose(previous,variants,limit=5)==a

def test_skips_previously_tested_signatures():
    variants={CHAMPION_NAME:CHAMPION_PARAMS}
    first=propose({},variants,limit=3)
    previous={"experiment_signatures_seen":[signature(p) for p in first.values()]}
    second=propose(previous,variants,limit=3)
    assert len(second)==3
    assert set(map(signature,first.values())).isdisjoint(map(signature,second.values()))

def test_train_rank_excludes_unprofitable():
    r={"results":{"a":{"train":{"trades":50,"net_profit":-1,"profit_factor":0.9}},
                  "b":{"train":{"trades":50,"net_profit":10,"profit_factor":1.2}}}}
    assert [x["name"] for x in train_rank(r)]==["b"]
