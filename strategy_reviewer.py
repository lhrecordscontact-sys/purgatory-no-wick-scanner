"""PURGATORY AI research reviewer. Research only; never places orders or edits live rules.
Input: JSON report from a validated backtester. Optional OPENAI_API_KEY for AI questions.
Usage: python strategy_reviewer.py report.json
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

REQUIRED = ("trade_count", "net_profit", "max_drawdown", "profit_factor", "out_of_sample_trades")
def evaluate(report):
    missing = [k for k in REQUIRED if k not in report]
    if missing:
        return {"approved": False, "reason": "Missing validated metrics: " + ", ".join(missing)}
    n = int(report["out_of_sample_trades"])
    pf = float(report["profit_factor"])
    dd = float(report["max_drawdown"])
    profit = float(report["net_profit"])
    approved = n >= 100 and pf >= 1.25 and profit > 0 and dd <= 0.10 and bool(report.get("costs_included")) and bool(report.get("no_lookahead"))
    return {"approved": approved, "reason": "Research gate passed; human approval still required" if approved else "Insufficient evidence for promotion", "out_of_sample_trades": n, "profit_factor": pf, "net_profit": profit, "max_drawdown": dd}

def questions(report):
    return [
        "Which losing trades were caused by countertrend entries, spread/slippage, or market chop?",
        "Would filtering low relative volume or EMA/VWAP misalignment improve OUT-OF-SAMPLE net expectancy?",
        "What happens to trade frequency and profit after realistic options bid/ask and fees?",
        "Does the candidate outperform the unchanged baseline across multiple dates and symbols?",
        "Are the improvements statistically robust, or just overfit to the recent losers?",
    ]

def ask_ai(report, qs):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return "OPENAI_API_KEY missing: questions generated, AI review not executed."
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "messages": [
            {"role": "system", "content": "You are a skeptical quantitative research reviewer. Ask pointed questions and propose testable experiments. Do not claim guaranteed profits, recommend live execution, or edit code. Output concise experiment proposals with failure criteria."},
            {"role": "user", "content": json.dumps({"report": report, "questions": qs})},
        ],
    }
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            data = json.load(res)
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        return "AI review unavailable: " + str(type(exc).__name__)

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python strategy_reviewer.py validated_report.json")
    with open(sys.argv[1], encoding="utf-8") as f:
        report = json.load(f)
    qs = questions(report)
    output = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "gate": evaluate(report), "questions": qs, "ai_recommendations": ask_ai(report, qs), "execution_mode": "RESEARCH_ONLY", "auto_promote": False}
    os.makedirs("reports", exist_ok=True)
    with open("reports/review_latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
