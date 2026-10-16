# Client EA ↔ Hinova API contract (v1.0) — design, not yet implemented

The client runs a **light MQL5 EA in their own MetaTrader 5 terminal**. Hinova never
receives broker passwords, never holds funds, and never sends orders. The EA:

1. sends authorised, closed-candle market data and non-secret account state;
2. receives a **proposal** (`BUY` / `SELL` / `NO_TRADE`);
3. re-checks everything locally before any (future, separately authorised) action.

## Request — `POST /v1/signals/evaluate`

Header `Authorization: Bearer <tenant API key>` (stored in the EA inputs, never in code).

```json
{
  "schema_version": "1.0",
  "idempotency_key": "<terminal-id>-<bar-ts>",
  "request_ts": 1767225600,
  "provenance": {"symbol": "XAUUSD", "instrument_type": "cfd", "timeframe": "M15",
                 "source": "mt5:<broker>:<server>"},
  "candles": [{"ts": 1767224700, "open": 2400.1, "high": 2401.5, "low": 2399.8,
               "close": 2401.2, "volume": 1532, "spread": 0.28}],
  "account": {"open_positions": 0, "daily_pnl_pct": -0.2, "current_spread": 0.28}
}
```

Rules enforced server-side (`src/api/service.py`): unknown fields rejected; `tenant_id`
in the body rejected; `request_ts` within ±300 s; idempotency key replays the stored
answer; ≤ 2000 candles; data quality, freshness and instrument identity validated.

## Response

`signal` = full `SignalRecord` (`src/core/contracts.py`) plus `signal_id`, `tenant_id`,
`expires_at` (60 s). `execution_allowed` is always `false` in this milestone.

## Mandatory EA-side behaviour (when written)

- Add the API URL to *Tools → Options → Expert Advisors → Allow WebRequest*.
- `WebRequest` is synchronous: call it from `OnTimer`, short timeout (≤ 3 s), never block `OnTick`.
- On timeout, HTTP error, invalid JSON, `expires_at` passed, symbol mismatch or
  `execution_allowed=false` → **do nothing** (fail closed).
- Recompute lot size locally from `SYMBOL_TRADE_TICK_VALUE`, `SYMBOL_TRADE_TICK_SIZE`,
  `SYMBOL_VOLUME_MIN/MAX/STEP`; never trust a server-side lot.
- Licence/trial expiry stops *new proposals only*; it must never close or modify positions.
