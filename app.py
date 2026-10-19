from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from scanner import DEFAULT_TICKERS, get_bars, backtest

app = FastAPI(title="PURGATORY No Wick Scanner")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/api/scan")
def scan(symbols: str=",".join(DEFAULT_TICKERS), timeframe: str=Query("5m", pattern="^(1m|4m|5m)$"),
         min_rate: float=Query(70, ge=0, le=100), min_trades: int=Query(30, ge=1, le=10000),
         rr: float=Query(1.5, gt=0, le=20), risk_pct: float=Query(2, gt=0, le=100)):
    tickers = list(dict.fromkeys(x.strip().upper() for x in symbols.split(",") if x.strip()))[:30]
    def work(symbol):
        try:
            return {"symbol": symbol, **backtest(get_bars(symbol, timeframe), rr, risk_pct, 500, min_rate, min_trades)}
        except Exception as exc:
            return {"symbol": symbol, "error": str(exc)[:180]}
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(work, s) for s in tickers]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda r: (not r.get("qualified", False), -r.get("win_rate", 0), -r.get("trades", 0)))
    return {"scanned_at": datetime.now(timezone.utc).isoformat(), "timeframe": timeframe, "results": results, "count": len(results)}


@app.get("/api/paper/status")
def paper_status():
    """Read the GitHub Actions paper-state snapshot, never the ephemeral Render disk."""
    import base64
    import os
    import sqlite3
    import tempfile
    from pathlib import Path
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    owner_repo = "lhrecordscontact-sys/purgatory-no-wick-scanner"
    url = f"https://api.github.com/repos/{owner_repo}/contents/paper.db?ref=paper-state"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "purgatory-paper-dashboard"}
    token = os.environ.get("GITHUB_READ_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=8) as response:
            import json
            payload = json.load(response)
        data = base64.b64decode(payload["content"], validate=False)
        if len(data) > 10_000_000 or not data.startswith(bytes.fromhex("53514c69746520666f726d6174203300")):
            raise ValueError("Invalid paper state snapshot")
        with tempfile.TemporaryDirectory() as tmp:
            dbfile = Path(tmp) / "paper.db"
            dbfile.write_bytes(data)
            con = sqlite3.connect(f"file:{dbfile}?mode=ro&immutable=1", uri=True)
            con.row_factory = sqlite3.Row
            try:
                trades = [dict(x) for x in con.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100")]
                settings = {x["key"]: x["value"] for x in con.execute("SELECT key,value FROM state")}
                realized = con.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='CLOSED'").fetchone()[0]
                has_options = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='option_trades'").fetchone()
                options_trades = [dict(x) for x in con.execute("SELECT * FROM option_trades ORDER BY id DESC LIMIT 100")] if has_options else []
            finally:
                con.close()
        import json
        return {"available": True, "mode": "PAPER_ONLY", "starting_cash": 500,
                "realized_balance": round(500 + realized, 2),
                "realized_pnl": round(realized, 2),
                "open_positions": [t for t in trades if t["status"] == "OPEN"],
                "trades": trades, "options_trades": options_trades, "options_pnl": round(sum(float(t["pnl"]) for t in options_trades if t["status"] == "CLOSED"), 2), "last_scan": json.loads(settings.get("last_scan", "null")),
                "candidates": json.loads(settings.get("candidates", "[]")),
                "note": "Scheduled paper snapshot; updates may be delayed. Open P/L not included."}
    except (HTTPError, URLError, ValueError, KeyError, sqlite3.Error, TimeoutError) as exc:
        return {"available": False, "mode": "PAPER_ONLY", "reason": "Paper snapshot unavailable. Verify paper-state branch and optional GITHUB_READ_TOKEN.",
                "detail": f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__}


@app.get("/api/research/latest")
def research_latest():
    """Read latest completed research report published by worker to GitHub."""
    import base64
    import json
    import os
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    url = "https://api.github.com/repos/lhrecordscontact-sys/purgatory-no-wick-scanner/contents/reports/research_latest.json?ref=main"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "purgatory-research-dashboard"}
    token = os.getenv("GITHUB_READ_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            record = json.load(response)
        report = json.loads(base64.b64decode(record["content"]))
        return {"available": True, "report": report}
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": "No published research report available yet. Worker needs GITHUB_WRITE_TOKEN and a successful completed run.", "error_type": type(exc).__name__}
