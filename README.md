# Phenom Crypto AI v0.2 — Mobile dashboard + API scaffold

Designed for deployment from a phone using a GitHub repository and a cloud Python host. It includes a responsive mobile dashboard, CoinGecko market data, optional X API recent-search integration, optional Alpaca stock snapshots, a stop-loss/take-profit position-size calculator, and a SQLite event log.

## Run locally (or deploy)
Python 3.11 recommended:
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000`. For phone use, deploy the repository to a Python web host.

## Deploy
`render.yaml` is a starting point for Render. Upload the files to GitHub, create a Render Web Service from the repo, and add environment variables in the provider dashboard. Do not commit tokens.
- `X_BEARER_TOKEN`: X API v2 bearer token with recent-search access. X API availability/pricing/access may change.
- `ALPACA_API_KEY` and `ALPACA_API_SECRET`: keys for market data. This code does not place orders.
- SQLite in `/tmp` is ephemeral on many hosts. For durable logs, configure a persistent disk or managed PostgreSQL before relying on 24/7 operation.

## Important status
This is a scaffold/prototype, not a validated trading system:
- The X sentiment value is a simple keyword heuristic, not a trained language model.
- Crypto market data is retrieved live on request; no background 24/7 worker is running yet.
- The stocks feed requires credentials and may be limited to the IEX feed based on the data plan.
- No real order execution exists. Paper trading, audit logs, hard daily loss limits, idempotent orders, monitoring, persistent storage, and independent validation are required before any live trading.
- Stop-loss and take-profit values are planning levels only; actual fills can be worse because of slippage, gaps, or low liquidity.
- Never guarantee profit or use "never lose" claims.

## Next engineering milestones
1. Deploy and verify data connections with timestamps.
2. Add X author/source credibility, duplicate detection, event extraction, and multiple-source corroboration.
3. Add durable storage and a scheduled worker, alerting, health checks, and data freshness limits.
4. Build walk-forward backtests with costs, spread, slippage, and benchmarks.
5. Paper trade for a statistically meaningful period; then evaluate before considering any live integration.
