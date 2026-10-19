# AI Strategy Reviewer — setup and limits

The new `strategy_reviewer.py` reads a validated JSON backtest report and produces `reports/review_latest.json`. It asks an OpenAI API model to challenge the strategy when `OPENAI_API_KEY` is configured. Without a key it still generates research questions and a deterministic promotion gate.

Example input `validated_report.json`:
```json
{"trade_count":150,"out_of_sample_trades":105,"net_profit":20.5,"max_drawdown":0.07,"profit_factor":1.3,"costs_included":true,"no_lookahead":true}
```
These example numbers are fictitious and must not be interpreted as actual scanner performance.

Run `python strategy_reviewer.py validated_report.json`.

**Not yet wired:** The existing scanner must export a real validated backtest report (with trade logs and option costs) and a scheduled worker must call this reviewer. The reviewer does not autonomously update files or speak to an existing ChatGPT conversation. An OpenAI API key is separate from a ChatGPT subscription and may incur charges.

**Promotion gate:** At least 100 out-of-sample trades, positive net profit, profit factor >= 1.25, drawdown <= 10%, recorded costs and no lookahead. Passing the gate does not establish safety or profitability; independent verification and explicit approval are still mandatory.

**Desired future pipeline:** collect -> backtest baseline -> diagnose losses -> AI proposes parameter experiments -> backtest candidates on training folds -> compare untouched holdout -> human review -> paper-only release. No real-money trading, no auto-promotion.
