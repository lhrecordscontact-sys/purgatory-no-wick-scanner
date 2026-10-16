# PURGATORY No Wick Scanner — Automated Paper Mode

This branch adds a continuously polling **paper-only** scanner. It does not connect to any brokerage or place real orders.

Run locally: `pip install -r requirements.txt`, then `python worker.py`. In another terminal run `uvicorn app:app --reload`.

The worker scans up to 30 tickers every 240 seconds during market hours, uses 4-minute candles, filters for 55% historical win rate and 30 closed historical trades, risks at most 1% of simulated balance, and caps entries at three per day with one open position.

The simulated directional CALL/PUT trades are **stock-price scenarios, not options contracts**. Yahoo's delayed and limited intraday feed, assumed fills at completed-bar close, lack of slippage, holiday handling, and incomplete short-selling modelling make results educational only. The historical backtest is not a prediction.

The Render blueprint provides a web service and separate persistent-disk worker; deployment is **not automatic**. The web service cannot access the worker's SQLite disk, so a shared database or worker API is needed for the hosted dashboard to show paper status. Do not use real money without substantial validation.
