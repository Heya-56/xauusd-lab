# XAUUSD Lab

Research and Paper-validation laboratory for gold strategies. No AI/ML. No live orders.

## Start here — no local installation required for research

1. Open the [Actions tab](https://github.com/Heya-56/xauusd-lab/actions).
2. Select **Lab smoke test** and choose **Run workflow** to validate the code and safety checks.
3. The research workflow is separate from the broker adapter. When a validated historical XAUUSD spot data source is configured, its run will publish CSV/JSON reports as downloadable artifacts.

> **Data-source status:** Yahoo Finance returned HTTP 404 for XAUUSD=X. The older GC=F ticker is COMEX gold futures, not XAUUSD spot, and must not be reported as spot performance. The IBKR runner currently requires a local authenticated IB Gateway/TWS session, so it is not the no-install GitHub Actions route. Until a valid spot feed is connected, no XAUUSD spot backtest result is claimed.

## Research protocol

All candidates must use the same verified data, explicit cost/slippage assumptions, and comparable periods. Require out-of-sample validation and at least 30 trades before considering a candidate for Paper. Do not select a winner from README claims or in-sample returns alone.

The existing competition runner evaluates five candidate families across five Paris-time entry hours and two holding horizons (50 configurations), but its current Yahoo XAUUSD data fetch is blocked. See [portable lab implementation plan](docs/PORTABLE-LAB-PLAN.md).

## Architecture

- **Research core:** portable deterministic backtests and metrics.
- **Market-data adapters:** normalized OHLC data, with source/instrument metadata.
- **Broker adapters (later):** IBKR Paper, MT5 demo/Paper, or another compatible broker, without coupling the research core to any one provider.
- **Reports:** CSV/JSON downloadable from GitHub Actions.
- **Payments (separate layer):** PayPal/OSB may be evaluated for commercial receipts. They are not broker connectors; trading-profit withdrawals depend on the broker's supported withdrawal methods.

## S.A.T.A. integration

S.A.T.A. is treated as a strategy and execution subsystem, not copied blindly into the Lab. The Lab maps its 3 horizons and 4 analysis methods into 12 reproducible candidates:

- Scalping: M15 bias, M5 setup, M1 trigger
- Normal: H4 bias, H1 setup, M15 trigger
- Swing: D1 bias, H4 setup, M15 trigger
- Methods: tendance, smc, orderblock, combine

See [docs/SATA-LAB-MAP.md](docs/SATA-LAB-MAP.md).

## Safety

- The research runner never submits orders.
- Paper validation is a separate stage.
- Live orders remain disabled by default.
- Broker credentials must never be exposed to the browser or committed to GitHub.
- No broker-specific dependency belongs in the research core.

## Current branch

integration/sata-lab-v2
