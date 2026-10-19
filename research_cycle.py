"""Scheduled research: genuine 5-minute stock OHLCV holdout, never options P/L."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
import pandas as pd
from no_wick_pro import Config, walk_forward
from strategy_reviewer import evaluate, questions, ask_ai

SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN"]
def bars(symbol):
    d = yf.download(symbol, interval="5m", period="60d", auto_adjust=False, progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    if d.empty or not {"Open","High","Low","Close","Volume"}.issubset(d.columns):
        raise ValueError("missing OHLCV")
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    return d[["Open","High","Low","Close","Volume"]].dropna()

def summarize(stats):
    trades = stats["trade_log"]
    profits = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    losses = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    return {"trades":stats["trades"], "net_profit":stats["net_profit"],
            "max_drawdown_pct":stats["max_drawdown_pct"],
            "profit_factor":round(profits/losses,3) if losses else None,
            "win_rate":stats["win_rate"],
            "loss_reasons":{reason:sum(1 for t in trades if t["pnl"]<0 and t["reason"]==reason)
                            for reason in sorted(set(t["reason"] for t in trades))}}

def main():
    cfg = Config(rr=1.5, risk_pct=0.5, daily_loss_pct=2, max_trades_day=8)
    report = {"generated_utc":datetime.now(timezone.utc).isoformat(),
              "mode":"STOCK_BACKTEST_RESEARCH_ONLY", "bar_interval":"5m",
              "note":"5-minute proxy, NOT 4-minute execution or 0DTE options performance; Yahoo history is limited.",
              "symbols":{}, "errors":{}}
    for symbol in SYMBOLS:
        try:
            result=walk_forward(bars(symbol), cfg)
            report["symbols"][symbol]={"train":summarize(result["train"]),
                                       "holdout":summarize(result["holdout"]),
                                       "train_sessions":result["train_sessions"],
                                       "holdout_sessions":result["holdout_sessions"]}
        except Exception as exc:
            report["errors"][symbol]=str(exc)[:160]
    holdouts=[x["holdout"] for x in report["symbols"].values()]
    n=sum(x["trades"] for x in holdouts)
    gross_profit=sum(x["net_profit"] for x in holdouts)
    # Do not infer portfolio-level drawdown by adding independent per-symbol account results.
    review_input={"trade_count":n, "out_of_sample_trades":n, "net_profit":gross_profit,
                  "max_drawdown":1.0, "profit_factor":0.0,
                  "costs_included":True, "no_lookahead":False,
                  "caveat":"Independent per-symbol stock simulations, no validated portfolio-level risk or options costs."}
    report["research_gate"]=evaluate(review_input)
    report["questions"]=questions(report)
    report["ai_recommendations"]=ask_ai(report,report["questions"])
    report["auto_promote"]=False
    Path("reports").mkdir(exist_ok=True)
    Path("reports/research_latest.json").write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({"symbols_completed":len(holdouts),"holdout_trades":n,"research_gate":report["research_gate"]}))

if __name__=="__main__":
    main()
