# PURGATORY Research Agents — deployment specification

## Goal
Run a continuously hosted, PAPER-ONLY research and setup-ranking service. No agent can submit real orders, edit production strategy rules automatically, or claim a win probability from an arbitrary score.

## Roles
1. Data agent: ingest and validate OHLCV, session timestamps, splits, missing bars, and data freshness. 4-minute Yahoo data is limited to about 7 days; procure a licensed longer intraday history before meaningful evaluation.
2. Signal agent: apply fixed no-wick rules to closed candles only; emit entry, invalidation, stop, target, timestamp, and data provenance.
3. Backtest agent: next-bar execution, fees, spreads, slippage, conservative intrabar stop priority, no future leakage, chronological train/holdout and walk-forward tests.
4. Optimization agent: compare a small predefined parameter grid on TRAINING folds only, with penalties for turnover and drawdown; never tune on the final holdout.
5. Risk agent: cap 1% per trade, 3% daily loss, 3 trades/day, one open position; reject stale quotes, missing volume, or oversized spread.
6. Review agent: compare candidate versus incumbent across multiple market regimes and independent holdout periods; require explicit human approval before promotion.
7. Reporting agent: rank current setups, show completed trade logs, trade count, expectancy, profit factor, drawdown, confidence intervals and rejection reasons.

## Scheduler
- 04:00–09:30 ET: collect premarket context (do not paper-fill options outside eligible hours).
- 09:30–16:00 ET: run scanning after every completed 4-minute candle; account for data latency and exchange holidays.
- 16:00–20:00 ET: analyze extended-session context; avoid treating it as regular-session liquidity.
- Overnight: data integrity checks, scheduled backtests and daily reports.
- Run as an always-on worker service with a persistent database and a watchdog; a free sleeping web instance is not sufficient. Budget for data/API and hosting.
- Record heartbeat, last completed bar, job failures and dataset version. Alert on stale data or missed scans.

## Minimum acceptance checks before paper deployment
- At least 60 sessions of valid historical 4-minute bars, preferably more.
- At least 30 closed out-of-sample trades for a preliminary result; more are needed for robust inference.
- Net-positive expectancy after conservative transaction costs and drawdown within configured limits.
- Compare with unchanged baseline and random/permutation benchmarks; reject improvements isolated to one ticker or one week.
- Separate stock backtests from options: an options strategy needs historical bid/ask, strike, expiry, Greeks, and contract-specific fills. Stock-price returns are NOT options P/L.
- No live trading by default; no automatic strategy promotion.
- Paper trades must be visible and reconciled before further automation.

## Existing code
- no_wick_pro.py is a research prototype, not wired to the production API or worker.
- scanner.py and paper_bot.py remain the production baseline until a reviewed migration.
- Do not use a simulated score as an actual probability of winning.
