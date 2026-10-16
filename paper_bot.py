"""Continuous, strictly simulated No Wick stock scanner. Never submits broker orders."""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, time as clocktime
from zoneinfo import ZoneInfo

from scanner import DEFAULT_TICKERS, get_bars, backtest

NY = ZoneInfo("America/New_York")
DB = os.getenv("PAPER_DB", "paper.db")
SYMBOLS = [s.strip().upper() for s in os.getenv("PAPER_SYMBOLS", ",".join(DEFAULT_TICKERS)).split(",") if s.strip()][:30]
START_CASH = float(os.getenv("PAPER_START_CASH", "500"))
RISK_PCT = min(float(os.getenv("PAPER_RISK_PCT", "1")), 1.0)
RR = float(os.getenv("PAPER_RR", "1.5"))
MIN_RATE = float(os.getenv("PAPER_MIN_WIN_RATE", "55"))
MIN_TRADES = int(os.getenv("PAPER_MIN_TRADES", "30"))
MAX_POSITIONS = 1
MAX_DAILY_TRADES = 3
DAILY_LOSS_PCT = 3.0
POLL_SECONDS = max(60, int(os.getenv("PAPER_POLL_SECONDS", "240")))
_lock = threading.RLock()
logger = logging.getLogger(__name__)


def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL,
        signal_bar TEXT NOT NULL, entry_time TEXT NOT NULL, entry REAL NOT NULL,
        stop REAL NOT NULL, target REAL NOT NULL, shares INTEGER NOT NULL,
        status TEXT NOT NULL, exit_time TEXT, exit_price REAL, pnl REAL DEFAULT 0,
        UNIQUE(symbol, signal_bar, side))""")
    db.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
    db.commit()
    return db


def state(db, key, default):
    row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def put_state(db, key, value):
    db.execute("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, json.dumps(value)))


def market_open(now):
    return now.weekday() < 5 and clocktime(9, 38) <= now.time() < clocktime(15, 55)


def completed_bars(df, now):
    # A 4-minute candle labelled 09:30 closes at 09:34 ET.
    return df[df.index + __import__("pandas").Timedelta(minutes=4) <= now]


def latest_setup(df):
    if len(df) < 32:
        return None
    d = df.copy()
    for span in (5, 9, 30):
        d[f"e{span}"] = d.Close.ewm(span=span, adjust=False).mean()
    p, b = d.iloc[-2], d.iloc[-1]
    if d.index[-2].date() != d.index[-1].date():
        return None
    bull = b.e5 > b.e9 > b.e30 and p.e5 > p.e9 > p.e30
    bear = b.e5 < b.e9 < b.e30 and p.e5 < p.e9 < p.e30
    no_bottom = p.Close > p.Open and abs(p.Open - p.Low) < 0.000001
    no_top = p.Close < p.Open and abs(p.Open - p.High) < 0.000001
    if no_bottom and bull and b.High > p.High and b.Close > b.Open:
        return {"side": "CALL", "stop": float(p.Low), "signal_bar": d.index[-1].isoformat()}
    if no_top and bear and b.Low < p.Low and b.Close < b.Open:
        return {"side": "PUT", "stop": float(p.High), "signal_bar": d.index[-1].isoformat()}
    return None


def snapshot():
    with _lock, connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100")]
        realized = sum(r["pnl"] for r in db.execute("SELECT pnl FROM trades WHERE status='CLOSED'"))
        return {"mode": "PAPER_ONLY", "starting_cash": START_CASH,
                "realized_balance": round(START_CASH + realized, 2),
                "open_positions": [r for r in rows if r["status"] == "OPEN"],
                "trades": rows, "last_scan": state(db, "last_scan", None),
                "candidates": state(db, "candidates", [])}


def scan_once():
    now = datetime.now(NY)
    if not market_open(now):
        return
    with _lock, connect() as db:
        day = now.date().isoformat()
        rows = db.execute("SELECT * FROM trades").fetchall()
        realized = sum(r["pnl"] for r in rows if r["status"] == "CLOSED")
        balance = START_CASH + realized
        day_pnl = sum(r["pnl"] for r in rows if r["status"] == "CLOSED" and r["exit_time"] and r["exit_time"][:10] == day)
        today_count = sum(1 for r in rows if r["entry_time"][:10] == day)
        candidates = []
        for symbol in SYMBOLS:
            try:
                bars = completed_bars(get_bars(symbol, "4m"), now)
                if len(bars) < 35:
                    continue
                # Manage open positions using completed bars AFTER entry, no same-bar hindsight.
                for trade in db.execute("SELECT * FROM trades WHERE status='OPEN' AND symbol=?", (symbol,)).fetchall():
                    subsequent = bars[bars.index > __import__("pandas").Timestamp(trade["entry_time"])]
                    if subsequent.empty:
                        continue
                    candle = subsequent.iloc[0]
                    long = trade["side"] == "CALL"
                    stop_hit = candle.Low <= trade["stop"] if long else candle.High >= trade["stop"]
                    target_hit = candle.High >= trade["target"] if long else candle.Low <= trade["target"]
                    if not (stop_hit or target_hit):
                        continue
                    # Conservative: stop wins if both touched within a bar.
                    exit_price = trade["stop"] if stop_hit else trade["target"]
                    pnl = (exit_price - trade["entry"]) * trade["shares"] * (1 if long else -1)
                    db.execute("UPDATE trades SET status='CLOSED',exit_time=?,exit_price=?,pnl=? WHERE id=?",
                               (now.isoformat(), exit_price, round(pnl, 2), trade["id"]))
                    balance += pnl
                    day_pnl += pnl
                stats = backtest(bars, RR, RISK_PCT, START_CASH, MIN_RATE, MIN_TRADES)
                setup = latest_setup(bars)
                candidates.append({"symbol": symbol, "win_rate": stats["win_rate"],
                                   "trades": stats["trades"], "qualified": stats["qualified"],
                                   "setup": setup})
                if not setup or not stats["qualified"] or today_count >= MAX_DAILY_TRADES:
                    continue
                if day_pnl <= -START_CASH * DAILY_LOSS_PCT / 100 or balance <= 0:
                    continue
                if db.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0] >= MAX_POSITIONS:
                    continue
                # Do not enter using a stale historical signal.
                if (now - bars.index[-1].to_pydatetime()).total_seconds() > 8 * 60:
                    continue
                entry = float(bars.iloc[-1].Close)  # indicative paper fill, not a broker execution
                distance = abs(entry - setup["stop"])
                if distance < 0.01 or (setup["side"] == "CALL" and entry <= setup["stop"]) or (setup["side"] == "PUT" and entry >= setup["stop"]):
                    continue
                risk_budget = max(0, balance * RISK_PCT / 100)
                shares = int(min(risk_budget / distance, max(0, balance) / entry))
                if shares < 1:
                    continue
                target = entry + RR * distance * (1 if setup["side"] == "CALL" else -1)
                cur = db.execute("""INSERT OR IGNORE INTO trades
                    (symbol,side,signal_bar,entry_time,entry,stop,target,shares,status)
                    VALUES(?,?,?,?,?,?,?,?, 'OPEN')""",
                    (symbol, setup["side"], setup["signal_bar"], now.isoformat(), entry,
                     setup["stop"], target, shares))
                if cur.rowcount:
                    today_count += 1
            except Exception:
                logger.exception("Scan failed for %s", symbol)
        put_state(db, "candidates", sorted(candidates, key=lambda c: (not c["qualified"], -c["win_rate"])))
        put_state(db, "last_scan", now.isoformat())
        db.commit()


def run_forever():
    logging.basicConfig(level=logging.INFO)
    with connect():
        pass
    while True:
        try:
            scan_once()
        except Exception:
            logger.exception("Paper scanner cycle failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
