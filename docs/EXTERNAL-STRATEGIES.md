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
