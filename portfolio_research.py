"""Conservative single-account stock-signal research; not executable options P/L."""
from datetime import datetime

def portfolio_simulation(results, initial_cash=500.0):
    events=[]
    for symbol, result in results:
        for t in result.get("trade_log", []):
            try:
                entry=datetime.fromisoformat(t["entry_time"])
                exit_at=datetime.fromisoformat(t["exit_time"])
                shares=int(t["shares"])
                if shares <= 0 or exit_at < entry:
                    continue
                events.append((entry, exit_at, symbol, t, shares))
            except (ValueError, KeyError, TypeError):
                continue
    events.sort(key=lambda x: (x[0], x[2]))
    cash=float(initial_cash)
    busy_until=None
    accepted=[]
    skipped=0
    peak=cash
    max_drawdown=0.0
    for entry, exit_at, symbol, t, shares in events:
        if busy_until is not None and entry <= busy_until:
            skipped+=1
            continue
        price=float(t["entry"])
        # Never spend more than available cash on underlying-equivalent shares.
        size=min(shares,int(max(cash,0)/price)) if price>0 else 0
        if size<1:
            skipped+=1
            continue
        pnl=float(t["pnl"])*size/shares
        cash+=pnl
        busy_until=exit_at
        peak=max(peak,cash)
        max_drawdown=max(max_drawdown,100*(peak-cash)/peak)
        accepted.append({"symbol":symbol,"entry_time":t["entry_time"],
                         "exit_time":t["exit_time"],"side":t["side"],
                         "shares":size,"net_pnl":round(pnl,2),
                         "ending_cash":round(cash,2)})
    wins=sum(t["net_pnl"]>0 for t in accepted)
    return {"initial_cash":initial_cash,"ending_cash":round(cash,2),
            "net_profit":round(cash-initial_cash,2),
            "trades":len(accepted),"wins":wins,
            "win_rate":round(100*wins/len(accepted),2) if accepted else 0,
            "skipped_overlapping_or_unaffordable":skipped,
            "max_drawdown_pct":round(max_drawdown,2),
            "target_1000_reached":cash>=1000,
            "trade_log":accepted,
            "caveat":"Single $500 cash-constrained sequential stock-signal proxy, including backtest fees/slippage; shorts are hypothetical, not executable cash-account trades; NOT options pricing or validated live returns. Batch only, not entire universe."}
