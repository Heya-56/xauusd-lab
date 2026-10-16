# Hinova Gold Scanner (MT5) — decision support only

Compares XAUUSD (chart symbol) with a reference gold symbol (e.g. COMEX `GC` futures, name varies by
broker). **It never sends orders**: no trade library is included, and a repository test fails if
`OrderSend`, `CTrade` or `Trade.mqh` appear in this folder.

## Files (copy the whole folder to `MQL5/Experts/HinovaGoldScanner/`)

| File | Role | May use |
|---|---|---|
| `HGS_Types.mqh` | Shared contract `SScannerSnapshot`, signal enum | nothing |
| `HGS_Scanner.mqh` | Data engine: quotes, rolling mean/stdev (O(1) ring buffer), Z-score, hysteresis | market data only |
| `HGS_Dashboard.mqh` | UI: native chart objects, redraw only on change | snapshot only |
| `HGS_Journal.mqh` | CSV journal in `MQL5\Files\` (`;` separator, flushed per line) | snapshot only |
| `HinovaGoldScanner.mq5` | Wiring: OnInit / OnTick (engine) / OnTimer (UI) / OnChartEvent / OnDeinit | modules |

## Signal

`diff = mid(XAUUSD) − mid(reference)`. Spot and futures differ by a cost of carry that drifts and jumps
at contract roll, so the raw gap is **not** compared to a fixed threshold. The engine compares the gap
to its own rolling mean: `deviation = diff − mean`, `Z = deviation / stdev`.

- `0 NEUTRE`, `1 BUY` (Z ≤ −entry: spot cheap vs reference), `2 SELL` (Z ≥ +entry).
- Entry gates (counted once per sample): |deviation| ≥ max(`InpMinDevPts`, `InpCostMult` × broker
  spread) **and** the condition holds for `InpConfirmSamples` consecutive samples. Without these, a pure
  Z ≥ 2 threshold fires about 5 % of the time on noise alone (shown by `tests/test_mql5_scanner_logic.py`).
- Hysteresis: back to neutral when |Z| ≤ exit (avoids flicker and journal spam).
- Fail closed: `NO_TICK`, `BAD_QUOTE`, `STALE_REF` (feeds more than `InpMaxQuoteAgeMs` apart, e.g. CME
  daily pause), `WARMUP` (window not full), `FLAT` (zero variance) → always NEUTRE.
- Sampling at a fixed cadence (`InpSampleMs`) so bursts of ticks do not bias the statistics.

## Limits (read before use)

- Not risk-free arbitrage: a retail account cannot lock spot vs futures at one broker; this is a
  statistical relative-value indicator. A high |Z| can persist or widen.
- The reference must exist at your broker. Contract roll creates a jump in `diff`; the window re-learns
  the new level (WARMUP-like period of `InpWindow × InpSampleMs`).
- Timestamps are broker server time (ms from the spot tick).
- Logic tested in CI through a Python mirror (`research/scanner_reference.py`) on simulated streams:
  quiet market, carry drift, shocks, frozen reference, contract roll, tick bursts.
- Not compiled in CI (MetaEditor is Windows-only). Compile in MetaEditor (F7) before use and test in the
  Strategy Tester in "Every tick based on real ticks" with both symbols available.
