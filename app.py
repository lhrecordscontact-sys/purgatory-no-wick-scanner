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
    return templates.TemplateResponse("index.html", {"request": request})

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
