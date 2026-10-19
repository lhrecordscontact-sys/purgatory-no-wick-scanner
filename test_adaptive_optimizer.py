from adaptive_optimizer import propose, train_rank

def test_generates_bounded_candidates_from_train():
    previous={"results":{"baseline":{"train":{"trades":35,"net_profit":5},
                                    "holdout":{"net_profit":-999}}}}
    variants={"baseline":{"min_rvol":1.2,"min_adx":18}}
    a=propose(previous,variants,limit=5)
    assert len(a)==5
    assert all(name.startswith("adaptive_baseline_") for name in a)
    previous["results"]["baseline"]["holdout"]["net_profit"]=999999
    assert propose(previous,variants,limit=5)==a

def test_train_rank_excludes_unprofitable():
    r={"results":{"a":{"train":{"trades":50,"net_profit":-1,"profit_factor":0.9}},
                  "b":{"train":{"trades":50,"net_profit":10,"profit_factor":1.2}}}}
    assert [x["name"] for x in train_rank(r)]==["b"]
