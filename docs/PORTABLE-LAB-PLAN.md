# Portable XAUUSD Lab — implementation direction

## Goal
Run research and backtests from GitHub Actions without installing software on the user's PC or requiring a locally running broker gateway.

## Architecture boundaries
- Research core: deterministic strategy evaluation, walk-forward/out-of-sample checks, metrics and report generation.
- Market-data adapters: normalized OHLC bars with explicit source, symbol, timeframe, timezone and coverage metadata.
- Broker adapters (later): IBKR Paper, MT5 Paper/demo, or another supported broker. Each adapter must implement a documented interface; the research core must not import broker-specific libraries.
- Reporting: CSV and JSON artifacts attached to a GitHub Actions run.
- Payments (separate future product layer): PayPal/OSB are for commercial receipts only. They are not broker connectors and must not be treated as a route for withdrawing trading profits unless the broker explicitly supports it.

## Non-negotiable safety rules
- Research and backtests never submit orders.
- Live trading remains disabled by default and is not part of this implementation.
- Paper execution must be a separate, explicit stage after research validation.
- Never describe GC=F (COMEX gold futures) as XAUUSD spot.
- Every report must state its data source, instrument, period, timeframe, timezone, assumptions, and whether spread, commission and slippage were modelled.
- No strategy is declared validated based only on in-sample returns. Require out-of-sample checks and a meaningful trade count.

## Immediate implementation order
1. Make the GitHub Actions entry point easy to find and manually runnable.
2. Fix and test the research pipeline independently from IB Gateway.
3. Resolve a reliable, permitted historical XAUUSD spot data source before publishing spot performance.
4. Generate and upload CSV/JSON reports as workflow artifacts.
5. Add replaceable broker adapters only after the offline research pipeline works.
6. Keep payment integrations separate from trading accounts and broker withdrawals.

## Current known blocker
Yahoo Finance returned HTTP 404 for the XAUUSD=X symbol in the current runner. The IBKR historical-data runner requires an authenticated local IB Gateway/TWS session, so it cannot be used as the no-install GitHub Actions data source. Until a valid XAUUSD spot data source is wired and verified, no result should be labelled an XAUUSD spot backtest.
