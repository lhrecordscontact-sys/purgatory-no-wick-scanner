from improvement_agent import assess

def test_rejects_losing_variants():
    report={"results":{"baseline":{"holdout":{"trades":40,"net_profit":-20,"worst_single_symbol_drawdown_pct":10}},
    "bad":{"holdout":{"trades":45,"net_profit":-5,"profit_factor":0.8,"worst_single_symbol_drawdown_pct":8}}}}
    result=assess(report)
    assert result["status"]=="NOT_IMPROVING"
    assert result["qualified_candidates"]==[]
    assert result["live_execution_allowed"] is False

def test_flags_candidate_without_approving_live_trading():
    report={"results":{"baseline":{"holdout":{"trades":40,"net_profit":-20,"worst_single_symbol_drawdown_pct":10}},
    "better":{"holdout":{"trades":45,"net_profit":15,"profit_factor":1.3,"worst_single_symbol_drawdown_pct":8}}}}
    result=assess(report)
    assert result["status"]=="CANDIDATE_FOUND_NOT_VALIDATED"
    assert result["qualified_candidates"][0]["variant"]=="better"
    assert result["live_execution_allowed"] is False
