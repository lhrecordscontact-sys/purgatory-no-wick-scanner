"""Autonomous, research-only PURGATORY experiments. No brokerage orders or live-rule edits."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
import pandas as pd
from no_wick_pro import Config, walk_forward
from strategy_reviewer import questions, ask_ai
from us_universe import universe
import os

SYMBOLS = ["SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMD","TSLA","META","AMZN",
           "GOOGL","PLTR","SOFI","COIN","HOOD","BAC","F","INTC","MU","UBER",
           "NFLX","AVGO","JPM","XLF","XLK","MSTR","RIVN","TQQQ","SQQQ","SMCI"]
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

def main():
    cfg=Config(rr=1.5,risk_pct=0.5,daily_loss_pct=2,max_trades_day=8)
    symbols, universe_errors = universe()
    if not symbols:
        raise RuntimeError("US ticker universe unavailable; refusing to claim full-market coverage")
    # Rotate deterministic batches across hourly runs; never claim all symbols were tested.
    batch_size=max(10,min(int(os.getenv("RESEARCH_BATCH_SIZE","60")),100))
    batch_number=int(datetime.now(timezone.utc).timestamp()//3600)
    offset=(batch_number*batch_size)%len(symbols)
    selected_symbols=(symbols+symbols)[offset:offset+batch_size]
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
            "mode":"RESEARCH_ONLY","execution_enabled":False,"auto_promote":False,
            "bar_interval":"5m","universe_size":len(symbols),
            "universe_errors":universe_errors,"batch_offset":offset,
            "symbols_requested":len(selected_symbols),"symbols_in_batch":selected_symbols,
            "caveats":["Yahoo 5-minute data is not a 4-minute strategy or historical options pricing.",
                       "Each symbol is simulated independently with $500; summed profit is NOT portfolio P/L.",
                       "Experiment selection is TRAIN-ONLY; holdout is descriptive and not used for choosing.",
                       "Repeated daily research can overfit the same holdout; independent future validation is required.",
                       "No validated aggregate portfolio drawdown or options transaction costs."],
            "variants":VARIANTS,"errors":{}}
    per={name:{"train":[],"holdout":[],"symbols":0} for name in VARIANTS}
    for symbol in selected_symbols:
        try:
            data=bars(symbol)
            for name,params in VARIANTS.items():
                try:
                    result=walk_forward(data,replace(cfg,**params))
                    per[name]["train"].append(result["train"])
                    per[name]["holdout"].append(result["holdout"])
                    per[name]["symbols"]+=1
                except Exception as exc:
                    report["errors"][symbol+":"+name]=str(exc)[:160]
        except Exception as exc:
            report["errors"][symbol]=str(exc)[:160]
    report["results"]={name:{"train":metrics(v["train"]),"holdout":metrics(v["holdout"]),
                             "symbols_completed":v["symbols"]} for name,v in per.items()}
    # Train-only ranking: prefer positive expectancy with sufficient training examples.
    eligible=[name for name,v in report["results"].items() if v["train"]["trades"]>=30]
    selected=max(eligible,key=lambda n:(report["results"][n]["train"]["net_profit"],
                                        report["results"][n]["train"]["trades"])) if eligible else None
    report["training_selected_variant"]=selected
    report["baseline_holdout"]=report["results"]["baseline"]["holdout"]
    report["selected_holdout"]=report["results"][selected]["holdout"] if selected else None
    report["research_gate"]={"approved":False,
        "reason":"No live promotion: independent validation and actual options costs missing."}
    report["questions"]=questions(report)
    report["ai_recommendations"]=ask_ai(report,report["questions"])
    Path("reports").mkdir(exist_ok=True)
    Path("reports/research_latest.json").write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({"symbols_completed":per["baseline"]["symbols"],
                      "baseline_holdout":report["baseline_holdout"],
                      "training_selected_variant":selected,
                      "selected_holdout":report["selected_holdout"],
                      "ai_review_available":not str(report["ai_recommendations"]).startswith(("AI review unavailable","OPENAI_API_KEY missing")),
                      "research_gate":report["research_gate"]}))
if __name__=="__main__": main()
