# External strategy references

## MA20/MA50
Reference: FahadJawed8/gold-xauusd-backtester.
The original project uses yfinance, a 20/50 moving-average crossover, and compares strategy performance with buy-and-hold.
The Lab reimplements only the deterministic signal against normalized Lab OHLC. Published results are not Lab results.

## DeMarker mean reversion
Reference: dns2jtm/xauusd-mean-reversion.
The original project uses multi-timeframe DeMarker and a grid recovery mechanism, and documents transaction-cost analysis and walk-forward analysis.
The Lab imports only the deterministic DeMarker signal. Grid/martingale execution is intentionally disabled.

## Data-source rule
The reference projects use Yahoo Finance. The Lab does not treat Yahoo GC=F as spot XAUUSD. IBKR XAUUSD is the canonical future validation source.

## Common validation
Both candidates must use the same data, costs, slippage, OOS split, minimum-trade rule and ranking protocol as S.A.T.A.

## External components review — 2026-10-15

Rule: the product is sold as SaaS and under a commercial white-label licence, so only
permissive licences (MIT, BSD, Apache-2.0) may be vendored or depended upon. Copyleft
(GPL/AGPL/LGPL) or "Commons Clause" code is excluded from the shipped product.

| Project | Licence (checked) | Decision |
|---|---|---|
| [dukascopy-node](https://github.com/Leo4815162342/dukascopy-node) v1.50.0 | MIT (npm metadata) | **Used** as a pinned CLI in the network data job (`npx dukascopy-node@1.50.0`). Not vendored, not forked. Data is research-only, not committed or redistributed. |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) v0.3.1 | Apache-2.0 | **Ideas only** (analyst / bull-bear / trader / risk roles) re-implemented deterministically in `src/agents/review.py`. No code copied. Fork not needed. |
| HF dataset `ZombitX64/xauusd-gold-price-historical-data-2004-2025` | none stated, unknown origin | **Rejected** as verified data (no licence, no instrument identity). |
| vectorbt | Apache-2.0 + Commons Clause | Rejected for the product (commercial restriction). |
| backtesting.py | AGPL-3.0 | Rejected (network copyleft incompatible with SaaS/white-label). |
| freqtrade / backtrader | GPL-3.0 | Rejected for the product. |

Re-check licences at each version bump; record the version used in report metadata.
