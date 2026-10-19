"""Conservative, research-only strategy improvement monitor.

Compare candidates on the SAME stocks and SAME holdout windows. Never promote
a strategy or place orders based on these diagnostics.
"""
def assess(report, min_trades=30, min_profit_factor=1.10):
    results=report.get("results",{})
    baseline=results.get("baseline",{}).get("holdout",{})
    bt=int(baseline.get("trades",0))
    bp=float(baseline.get("net_profit",0))
    assessments=[]
    for name,item in results.items():
        if name=="baseline": continue
        h=item.get("holdout",{})
        n=int(h.get("trades",0))
        net=float(h.get("net_profit",0))
        pf=h.get("profit_factor")
        draw=float(h.get("worst_single_symbol_drawdown_pct",0))
        bdraw=float(baseline.get("worst_single_symbol_drawdown_pct",0))
        eligible=(n>=min_trades and bt>=min_trades and
                  net>max(0,bp) and pf is not None and
                  float(pf)>=min_profit_factor and draw<=bdraw)
        assessments.append({"variant":name,"trades":n,"holdout_net_profit":net,
                            "profit_factor":pf,"drawdown_pct":draw,
                            "beats_baseline":eligible})
    qualified=sorted((a for a in assessments if a["beats_baseline"]),
                     key=lambda a:(a["holdout_net_profit"],a["trades"]),reverse=True)
    return {"status":"CANDIDATE_FOUND_NOT_VALIDATED" if qualified else "NOT_IMPROVING",
            "baseline_trades":bt,"baseline_holdout_profit":bp,
            "qualified_candidates":qualified,
            "candidates_checked":len(assessments),
            "next_action":("Validate candidates on new, untouched future sessions; no live promotion."
                           if qualified else
                           "Inspect loss reasons; test entry filters, exits, risk/reward and market regimes on identical historical windows."),
            "warning":"Repeated use of the same holdout overfits it; this is a diagnostic, not independent validation.",
            "live_execution_allowed":False}
