# XAUUSD Lab

XAUUSD research and Paper Trading laboratory. No AI/ML.

## S.A.T.A. integration

S.A.T.A. is treated as a strategy and execution subsystem, not copied blindly
into the Lab. The Lab maps its 3 horizons and 4 analysis methods into 12
reproducible candidates:

- Scalping: M15 bias, M5 setup, M1 trigger
- Normal: H4 bias, H1 setup, M15 trigger
- Swing: D1 bias, H4 setup, H1 trigger
- Methods: tendance, smc, orderblock, combine

See docs/SATA-LAB-MAP.md.

## Research protocol

Every candidate is evaluated on the same data, cost model and slippage model.
Out-of-sample validation and at least 30 trades are required before a candidate
can be considered for Paper. The Lab never selects a winner from a README claim.

## Decision layer

Signals are normalized and can be combined with deterministic confluence.
Disagreement defaults to NO TRADE. This is rule-based logic, not AI.

## Execution

IBKR is the primary broker/data path. The first execution environment is
IBKR Paper. Live orders remain disabled by default.

IBKR historical market data supports OHLC bars and Bid/Ask/Midpoint sources;
the Lab uses broker contract metadata as the source of truth for trading
specifications.

## Safety

The browser never receives broker credentials. No Live order is enabled by this
branch. Paper validation comes before any future Live decision.

## Current branch

integration/sata-lab-v2
