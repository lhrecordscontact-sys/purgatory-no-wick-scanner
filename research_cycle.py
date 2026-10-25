"""Autonomous, research-only PURGATORY experiments. No brokerage orders or live-rule edits."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
import pandas as pd
from no_wick_pro import Config, walk_forward, backtest
from strategy_reviewer import questions, ask_ai
from us_universe import universe
from portfolio_research import portfolio_simulation
from improvement_agent import assess
from adaptive_optimizer import propose, train_rank, signature, CHAMPION_NAME, CHAMPION_PARAMS
import os
import base64
from urllib.request import Request, urlopen

SYMBOLS = ["SPY","QQQ","IWM","NVDA","TSLA","AAPL","AMD","META","AMZN","MSFT","PLTR","COIN","MSTR","HOOD"]

VARIANTS = {
    "baseline": {"min_rvol":1.2,"min_adx":18.0,"wick_tolerance":0.02},
    "rvol_1_0": {"min_rvol":1.0,"min_adx":18.0,"wick_tolerance":0.02},
    "rvol_0_8": {"min_rvol":0.8,"min_adx":18.0,"wick_tolerance":0.02},
    "adx_14": {"min_rvol":1.2,"min_adx":14.0,"wick_tolerance":0.02},
    "wick_0_05": {"min_rvol":1.2,"min_adx":18.0,"wick_tolerance":0.05},
    "rvol_1_adx_14": {"min_rvol":1.0,"min_adx":14.0,"wick_tolerance":0.02},
    "wick_0_10": {"min_rvol":1.2,"min_adx":18.0,"wick_tolerance":0.10},
    "rvol_0_8_adx_14": {"min_rvol":0.8,"min_adx":14.0,"wick_tolerance":0.02},
    "adx_22": {"min_rvol":1.2,"min_adx":22.0,"wick_tolerance":0.02},
    "elite_v7_proxy": {"signal_mode":"elite_v7_proxy","stop_atr_buffer":0.25},
    "orb_break": {"signal_mode":"orb_break"},
    "vwap_reclaim": {"signal_mode":"vwap_reclaim"},
    "ema9_pullback": {"signal_mode":"ema9_pullback"},
    "momentum_break": {"signal_mode":"momentum_break"},
    CHAMPION_NAME: CHAMPION_PARAMS,
    "atr_stop_025": {"stop_atr_buffer":0.25},
    "atr_stop_050": {"stop_atr_buffer":0.50},
    "body_60": {"min_confirmation_body":0.60},
    "no_chase_1atr": {"max_entry_extension_atr":1.0},
    "atr_025_no_chase": {"stop_atr_buffer":0.25,"max_entry_extension_atr":1.0},
    "body_70_rvol_15": {"min_confirmation_body":0.70,"min_rvol":1.5},
    "body_60_adx_22": {"min_confirmation_body":0.60,"min_adx":22.0},
    "body_60_no_chase": {"min_confirmation_body":0.60,"max_entry_extension_atr":1.0},
    "strict_trend_quality": {"min_confirmation_body":0.65,"min_rvol":1.5,"min_adx":22.0,"max_entry_extension_atr":0.75},
}
def bars(symbol):
    d=yf.download(symbol,interval="5m",period="60d",auto_adjust=False,progress=False,threads=False)
    if isinstance(d.columns,pd.MultiIndex):
        d.columns=d.columns.get_level_values(0)
    if d.empty or not {"Open","High","Low","Close","Volume"}.issubset(d.columns):
        raise ValueError("missing OHLCV")
    if d.index.tz is None: d.index=d.index.tz_localize("UTC")
    return d[["Open","High","Low","Close","Volume"]].dropna()

def metrics(results):
    logs=[t for r in results for t in r["trade_log"]]
    wins=sum(t["pnl"]>0 for t in logs)
    gain=sum(t["pnl"] for t in logs if t["pnl"]>0)
    loss=-sum(t["pnl"] for t in logs if t["pnl"]<0)
    return {"trades":len(logs),"wins":wins,
            "win_rate":round(100*wins/len(logs),2) if logs else 0,
            "net_profit":round(sum(r["net_profit"] for r in results),2),
            "profit_factor":round(gain/loss,3) if loss else None,
            "worst_single_symbol_drawdown_pct":round(max((r["max_drawdown_pct"] for r in results),default=0),2),
            "loss_reasons":{reason:sum(1 for t in logs if t["pnl"]<0 and t["reason"]==reason)
                            for reason in sorted(set(t["reason"] for t in logs))}}

def previous_report():
    url = "https://api.github.com/repos/lhrecordscontact-sys/purgatory-no-wick-scanner/contents/reports/research_latest.json?ref=main"
    headers = {"Accept":"application/vnd.github+json", "User-Agent":"purgatory-research"}
    token = os.getenv("GITHUB_WRITE_TOKEN") or os.getenv("GITHUB_READ_TOKEN")
    if token: headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            record = json.load(response)
        return json.loads(base64.b64decode(record["content"]))
    except Exception as exc:
        print("No previous learning state:", type(exc).__name__)
        return {}

def next_batch_offset(symbols, previous):
    """Resume by last tested ticker even if the listed universe changes."""
    import bisect
    if not symbols:
        return 0, 1
    previous_batch = previous.get("symbols_in_batch") or []
    pass_number = int(previous.get("coverage_pass", 1))
    if previous_batch:
        offset = bisect.bisect_right(symbols, previous_batch[-1])
        return (offset, pass_number) if offset < len(symbols) else (0, pass_number + 1)
    offset = int(previous.get("batch_offset", 0)) + int(previous.get("symbols_requested", 0))
    if previous.get("universe_size") == len(symbols):
        return offset % len(symbols), pass_number + (offset >= len(symbols))
    return 0, 1

def main():
    cfg=Config(rr=1.5,risk_pct=0.5,daily_loss_pct=2,max_trades_day=8)
    # Focus on liquid, widely traded names instead of sweeping the entire US ticker list.
    # Fixed universe makes same-symbol comparisons easier across research cycles.
    symbols = SYMBOLS
    universe_errors = {}
    if not symbols:
        raise RuntimeError("Focused research universe is empty")
    # Resume contiguous batches from the last successfully published GitHub report.
    batch_size=len(symbols)
    previous = previous_report()
    # Generate next experiments from prior TRAIN data only, before reading this
    # batch's holdout. Never update live strategy or select using holdout.
    experiments=propose(previous,VARIANTS,limit=8)
    variants={**VARIANTS,**experiments}
    prior_signatures = set(previous.get("experiment_signatures_seen", []))
    prior_signatures.update(signature(p) for p in previous.get("adaptive_experiments", {}).values())
    experiment_signatures_seen = sorted(prior_signatures | {signature(p) for p in experiments.values()})
    offset, coverage_pass = 0, int(previous.get("coverage_pass", 0)) + 1
    selected_symbols=symbols[offset:offset+batch_size]
    prior_symbols=previous.get("symbols_in_batch",[])
    comparison_symbols=[]  # Full focused universe already receives identical variant tests.
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
            "universe_mode":"FOCUSED_14",
            "mode":"RESEARCH_ONLY","execution_enabled":False,"auto_promote":False,
            "bar_interval":"5m","universe_size":len(symbols),
            "universe_errors":universe_errors,"batch_offset":offset,
            "coverage_pass":coverage_pass,"coverage_completed_in_pass":offset+len(selected_symbols),
            "coverage_remaining_in_pass":len(symbols)-offset-len(selected_symbols),
            "symbols_requested":len(selected_symbols),"symbols_in_batch":selected_symbols,
            "caveats":["Yahoo 5-minute data is not a 4-minute strategy or historical options pricing.",
                       "Each symbol is simulated independently with $500; summed profit is NOT portfolio P/L.",
                       "Experiment selection is TRAIN-ONLY; holdout is descriptive and not used for choosing.",
                       "Repeated daily research can overfit the same holdout; independent future validation is required.",
                       "No validated aggregate portfolio drawdown or options transaction costs."],
            "variants":variants,"adaptive_experiments":experiments,
            "experiment_signatures_seen":experiment_signatures_seen,
            "provisional_champion":{"name":CHAMPION_NAME,"parameters":CHAMPION_PARAMS,
                "basis":"Best previously observed $500-account proxy (batch 36); not independently validated",
                "promotion_allowed":False},"errors":{}}
    per={name:{"train":[],"holdout":[],"last_week":[],"symbols":0,"holdout_by_symbol":[]} for name in variants}
    for symbol in selected_symbols:
        try:
            data=bars(symbol)
            for name,params in variants.items():
                try:
                    result=walk_forward(data,replace(cfg,**params))
                    per[name]["train"].append(result["train"])
                    per[name]["holdout"].append(result["holdout"])
                    per[name]["holdout_by_symbol"].append((symbol,result["holdout"]))
                    sessions=sorted(set(data.index.tz_convert("America/New_York").date))
                    if len(sessions)>=20:
                        week=data[data.index.tz_convert("America/New_York").date>=sessions[-5]]
                        per[name]["last_week"].append(backtest(week,replace(cfg,**params)))
                    per[name]["symbols"]+=1
                except Exception as exc:
                    report["errors"][symbol+":"+name]=str(exc)[:160]
        except Exception as exc:
            report["errors"][symbol]=str(exc)[:160]
    report["results"]={name:{"train":metrics(v["train"]),"holdout":metrics(v["holdout"]),
                             "last_week":metrics(v["last_week"]),
                             "symbols_completed":v["symbols"]} for name,v in per.items()}
    # Same-symbol comparison is diagnostic only; never use it to tune holdout.
    comparison={}
    for symbol in comparison_symbols:
        try:
            data=bars(symbol)
            for name in ("baseline","atr_stop_025","atr_stop_050","body_60","no_chase_1atr","atr_025_no_chase"):
                result=walk_forward(data,replace(cfg,**variants[name]))
                comparison.setdefault(name,[]).append(result["holdout"])
        except Exception as exc:
            report["errors"]["comparison:"+symbol]=str(exc)[:160]
    report["previous_batch_comparison"]={
        "symbols_requested":comparison_symbols,
        "results":{name:metrics(items) for name,items in comparison.items()},
        "caveat":"Historical same-symbol holdout is a diagnostic comparison, not an independent prospective validation."}
    # Rolling history overlaps across runs: do not add repeated trades.
    # These are per-run training diagnostics, not independent observations.
    totals = {
        name: {"trades": item["train"]["trades"],
               "wins": item["train"]["wins"],
               "net_profit": item["train"]["net_profit"],
               "batches": 1}
        for name, item in report["results"].items()
    }
    eligible = [name for name, v in totals.items()
                if v["trades"] >= 100 and v["net_profit"] > 0]
    selected = max(eligible, key=lambda n: (
        totals[n]["net_profit"] / totals[n]["trades"],
        totals[n]["trades"])) if eligible else None
    # The champion is always evaluated; challengers cannot be promoted from
    # reused holdout data or a single overlapping training snapshot.
    report["champion_train"] = report["results"][CHAMPION_NAME]["train"]
    report["champion_holdout_diagnostic"] = report["results"][CHAMPION_NAME]["holdout"]
    report["champion_challengers_train"] = [
        {"name":n,"train":report["results"][n]["train"]}
        for n in experiments]
    report["training_selected_variant"] = selected
    report["adaptive_learning"] = {
        "method": "Current training snapshot only; overlapping runs not accumulated",
        "training_totals": totals,
        "prior_selected_variant": previous.get("training_selected_variant"),
        "selected_variant": selected,
        "minimum_training_trades": 100,
        "positive_training_profit_required": True,
        "holdout_not_used_for_selection": True,
        "independent_new_trades_verified": False,
        "live_execution_enabled": False,
        "caution": "Current historical snapshot only; prospective validation still required."
    }
    report["last_week_evaluation"]={"description":"Last five available trading sessions per stock; independent $500 per-symbol stock simulations, not a shared $500 portfolio",
                                    "selected_by_training_only":selected,
                                    "baseline":report["results"]["baseline"]["last_week"],
                                    "candidate":report["results"][selected]["last_week"] if selected else None}
    report["single_account_holdout"]={name:portfolio_simulation(v["holdout_by_symbol"]) for name,v in per.items()}
    report["single_account_selected_holdout"]=report["single_account_holdout"].get(selected) if selected else None
    report["single_account_goal_verified"]=False
    report["single_account_goal_reason"]="Research-only batch proxy; no independent full-universe portfolio or executable options validation."
    report["baseline_holdout"]=report["results"]["baseline"]["holdout"]
    report["selected_holdout"]=report["results"][selected]["holdout"] if selected else None
    report["account_goal"]={"starting_cash_usd":500,"target_cash_usd":1000,
                            "required_return_pct":100,
                            "achieved":False,
                            "reason":"Separate per-symbol stock backtests cannot establish a $500-to-$1000 portfolio result; options execution and capital constraints are not simulated."}
    report["research_gate"]={"approved":False,
        "reason":"No live promotion: independent validation and actual options costs missing."}
    report["improvement_agent"]=assess(report)
    report["train_ranked_candidates"]=train_rank(report)
    report["improvement_agent"]["new_experiments"]=list(experiments)
    report["improvement_agent"]["autonomous_research_only"]=True
    report["questions"]=questions(report)
    report["ai_recommendations"]=ask_ai(report,report["questions"])
    Path("reports").mkdir(exist_ok=True)
    Path("reports/research_latest.json").write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({"symbols_completed":per["baseline"]["symbols"],
                      "baseline_holdout":report["baseline_holdout"],
                      "last_week_evaluation":report["last_week_evaluation"],
                      "training_selected_variant":selected,
                      "selected_holdout":report["selected_holdout"],
                      "ai_review_available":not str(report["ai_recommendations"]).startswith(("AI review unavailable","OPENAI_API_KEY missing")),
                      "improvement_agent":report["improvement_agent"],
                      "research_gate":report["research_gate"],
                      "account_goal":report["account_goal"]}))
if __name__=="__main__": main()
