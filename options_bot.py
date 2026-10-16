"""Strictly simulated 0DTE option trades. No broker connection or order placement."""
import json
import os
import sqlite3
from datetime import datetime, time as clocktime
from zoneinfo import ZoneInfo
import yfinance as yf
from paper_bot import connect, market_open, SYMBOLS, latest_setup
from scanner import get_bars, backtest

NY = ZoneInfo("America/New_York")
MAX_PREMIUM = 100.0
MAX_RISK = 15.0
STOP_PCT = 0.20
TARGET_PCT = 0.30
MAX_TRADES_DAY = 2
MIN_RATE = 70.0
MIN_TRADES = 30

def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS option_trades (
      id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, contract TEXT NOT NULL,
      side TEXT NOT NULL, expiry TEXT NOT NULL, strike REAL NOT NULL,
      entry_time TEXT NOT NULL, entry_ask REAL NOT NULL, quantity INTEGER NOT NULL,
      exit_time TEXT, exit_bid REAL, status TEXT NOT NULL, pnl REAL DEFAULT 0,
      exit_reason TEXT, UNIQUE(contract, entry_time))""")
    db.commit()

def quote(symbol, contract, expiry, side):
    chain = yf.Ticker(symbol).option_chain(expiry)
    frame = chain.calls if side == "CALL" else chain.puts
    matches = frame[frame["contractSymbol"] == contract]
    if matches.empty:
        return None
    return matches.iloc[0]

def valid_price(row, now):
    try:
        bid, ask = float(row["bid"]), float(row["ask"])
        if bid <= 0 or ask <= 0 or ask < bid or (ask - bid) / ask > 0.15:
            return None
        # Yahoo option-chain quotes can be stale. Refuse known stale trades.
        last = row.get("lastTradeDate")
        if last is None or str(last) == "NaT":
            return None
        timestamp = __import__("pandas").Timestamp(last)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        age = (now - timestamp.to_pydatetime().astimezone(NY)).total_seconds()
        if age < -60 or age > 600:
            return None
        return bid, ask
    except (ValueError, TypeError, KeyError):
        return None

def scan_once():
    now = datetime.now(NY)
    if not market_open(now):
        return
    with connect() as db:
        initialize(db)
        day = now.date().isoformat()
        # Close existing paper options first. Mark missing quotes, never invent fills.
        for trade in db.execute("SELECT * FROM option_trades WHERE status='OPEN'").fetchall():
            try:
                row = quote(trade["symbol"], trade["contract"], trade["expiry"], trade["side"])
                prices = valid_price(row, now) if row is not None else None
                if not prices:
                    continue
                bid, ask = prices
                change = (bid - trade["entry_ask"]) / trade["entry_ask"]
                reason = ("stop" if change <= -STOP_PCT else "target" if change >= TARGET_PCT
                          else "end_of_day" if now.time() >= clocktime(15, 40) else None)
                if reason:
                    pnl = round((bid - trade["entry_ask"]) * 100 * trade["quantity"], 2)
                    db.execute("""UPDATE option_trades SET exit_time=?,exit_bid=?,status='CLOSED',
                                  pnl=?,exit_reason=? WHERE id=?""",
                               (now.isoformat(), bid, pnl, reason, trade["id"]))
            except Exception as exc:
                print("Option exit quote unavailable:", trade["symbol"], type(exc).__name__)
        db.commit()
        # Never open late in the day; options expire today.
        if not clocktime(9, 45) <= now.time() < clocktime(11, 30):
            return
        trades_today = db.execute("SELECT COUNT(*) FROM option_trades WHERE substr(entry_time,1,10)=?", (day,)).fetchone()[0]
        day_pnl = db.execute("SELECT COALESCE(SUM(pnl),0) FROM option_trades WHERE substr(exit_time,1,10)=?", (day,)).fetchone()[0]
        if trades_today >= MAX_TRADES_DAY or day_pnl <= -MAX_RISK:
            return
        if db.execute("SELECT COUNT(*) FROM option_trades WHERE status='OPEN'").fetchone()[0]:
            return
        candidates = []
        for symbol in SYMBOLS:
            try:
                ticker = yf.Ticker(symbol)
                if day not in ticker.options:
                    continue
                bars = get_bars(symbol, "4m")
                bars = bars[bars.index + __import__("pandas").Timedelta(minutes=4) <= now]
                if bars.empty or bars.index[-1].date() != now.date():
                    continue
                if (now - bars.index[-1].to_pydatetime()).total_seconds() > 600:
                    continue
                stats = backtest(bars, 1.5, 1, 500, MIN_RATE, MIN_TRADES)
                setup = latest_setup(bars)
                if not setup or not stats["qualified"]:
                    continue
                side = setup["side"]
                chain = ticker.option_chain(day)
                frame = chain.calls if side == "CALL" else chain.puts
                spot = float(bars.iloc[-1].Close)
                for _, row in frame.iterrows():
                    prices = valid_price(row, now)
                    if not prices:
                        continue
                    bid, ask = prices
                    cost = ask * 100
                    if cost > MAX_PREMIUM or cost * STOP_PCT > MAX_RISK:
                        continue
                    strike = float(row["strike"])
                    # Stay near the underlying price; avoid deep OTM lottery contracts.
                    if abs(strike - spot) / spot > 0.015:
                        continue
                    oi = row.get("openInterest", 0)
                    volume = row.get("volume", 0)
                    if (0 if __import__("pandas").isna(oi) else oi) < 100 or (0 if __import__("pandas").isna(volume) else volume) < 20:
                        continue
                    score = stats["win_rate"] - 100 * (ask - bid) / ask
                    candidates.append((score, symbol, str(row["contractSymbol"]), side, strike, ask))
            except Exception as exc:
                print("Option candidate unavailable:", symbol, type(exc).__name__)
        if not candidates:
            return
        _, symbol, contract, side, strike, ask = max(candidates)
        # One contract; simulated ask entry, never claim broker execution.
        db.execute("""INSERT INTO option_trades
            (symbol,contract,side,expiry,strike,entry_time,entry_ask,quantity,status)
            VALUES (?,?,?,?,?,?,?,?, 'OPEN')""",
            (symbol, contract, side, day, strike, now.isoformat(), ask, 1))
        db.commit()

if __name__ == "__main__":
    scan_once()
