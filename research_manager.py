"""Research manager: asks diagnostic questions and assigns the next safe experiment.
Runs after each research batch; no brokerage actions or production rule changes.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def decide(report):
    baseline = report.get("baseline_holdout") or {}
    errors = report.get("errors") or {}
    experiments = report.get("adaptive_experiments") or {}
    qualified = (report.get("improvement_agent") or {}).get("qualified_candidates") or []
    symbols = int(report.get("coverage_completed_in_pass") or 0)
    total = int(report.get("universe_size") or 0)
    tasks = []
    if errors:
        tasks.append({"question":"Which symbols or indicators failed, and why?",
                      "action":"Investigate data and backtest errors; do not count failed symbols as tested.",
                      "evidence":{"error_count":len(errors)}})
    if not experiments:
        tasks.append({"question":"Why were no adaptive variations generated?",
                      "action":"Verify the previous training report and candidate generator."})
    if int(baseline.get("trades") or 0)<100:
        tasks.append({"question":"Is there enough independent out-of-sample evidence?",
                      "action":"Continue sequential stock batches; avoid performance claims from small samples."})
    if float(baseline.get("net_profit") or 0)<=0:
        tasks.append({"question":"What causes the baseline to lose after modeled costs?",
                      "action":"Compare stop exits, chop, volume and trend filters on training data."})
    if qualified:
        tasks.append({"question":"Will any candidate survive untouched future data and options transaction costs?",
                      "action":"Perform prospective validation; do not auto-promote."})
    if not tasks:
        tasks.append({"question":"Do results generalize across dates and symbols?",
                      "action":"Continue independent walk-forward validation."})
    return {"updated_utc":datetime.now(timezone.utc).isoformat(),
            "status":"RESEARCH_ONLY","live_trading_enabled":False,
            "coverage":{"completed":symbols,"total":total},
            "research_status":(report.get("improvement_agent") or {}).get("status","UNKNOWN"),
            "questions_and_next_actions":tasks,
            "next_step":"Run next research batch and reassess; stop only on explicit operator decision.",
            "success_criteria":"At least 100 independent out-of-sample trades, positive net after realistic costs, profit factor >=1.25, drawdown <=10%, stable across multiple unseen periods; manual approval required.",
            "success_verified":False}

def main():
    source=Path("reports/research_latest.json")
    if not source.exists():
        raise SystemExit("Research report missing")
    report=json.loads(source.read_text())
    result=decide(report)
    prompts=[item["question"] for item in result["questions_and_next_actions"]]
    # Optional OpenAI API review. Without a key the manager remains deterministic.
    # Suggestions are advisory: never execute AI-generated code or promote a strategy.
    result["rule_based_review"]={
        "baseline_holdout":report.get("baseline_holdout"),
        "improvement_agent":report.get("improvement_agent"),
        "adaptive_experiments":list((report.get("adaptive_experiments") or {}).keys()),
        "errors_count":len(report.get("errors") or {}),
        "training_candidates":report.get("train_ranked_candidates",[])[:5],
        "constraints":"Research-only; propose falsifiable tests, no live trading or code execution"
    }
    result["rule_based_review"]["questions"]=prompts
    result["ai_review"]="Disabled (free rule-based mode; no OpenAI API requests)"
    result["ai_review_enabled"]=False
    result["review_mode"]="FREE_RULE_BASED"
    dest=Path("reports/manager_latest.json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=="__main__":
    main()
