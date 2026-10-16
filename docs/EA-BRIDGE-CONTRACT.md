# Client EA ↔ Hinova API contract (v1.0) — implemented

The client runs a **light MQL5 EA in their own MetaTrader 5 terminal**. Hinova never
receives broker passwords, never holds funds, and never sends orders. The EA:

1. sends authorised, closed-candle market data and non-secret account state;
2. receives a **proposal** (`BUY` / `SELL` / `NO_TRADE`);
3. re-checks everything locally before any (future, separately authorised) action.

Implementation: `mql5/HinovaBridge/HinovaBridge.mq5` (EA), `workers/accounts-api/src/signals.js` (gateway),
`src/api/engine_http.py` (engine). The exact payload is `mql5/HinovaBridge/payload.example.json`.

## Request — `POST /v1/ea/signal`

Header `Authorization: Bearer htl_…` (terminal key from « Mon compte », stored in the EA inputs, never in code).

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

Rules enforced server-side (Worker + engine): terminal key valid and not revoked; e-mail verified;
`signals.read` entitlement active; unknown fields and `tenant_id` in the body rejected; `request_ts`
within ±300 s; idempotency key replays the stored answer; ≤ 2000 candles; 30 requests/min per tenant;
the engine re-validates the stored configuration and checks data quality, freshness, timeframe and
instrument identity (futures refused).

## Response

`signal` = full `SignalRecord` (`src/core/contracts.py`) plus `signal_id`, `tenant_id`,
`expires_at` (60 s). `execution_allowed` is always `false` in this milestone.

## EA-side behaviour (implemented)

- Add the API URL to *Tools → Options → Expert Advisors → Allow WebRequest*.
- `WebRequest` is synchronous: called from `OnTimer`, timeout ≤ 10 s, `OnTick` is never blocked.
- On timeout, HTTP error, invalid JSON, `expires_at` passed, symbol mismatch or
  `execution_allowed=false` → **do nothing** (fail closed).
- Recompute lot size locally from `SYMBOL_TRADE_TICK_VALUE`, `SYMBOL_TRADE_TICK_SIZE`,
  `SYMBOL_VOLUME_MIN/MAX/STEP`; never trust a server-side lot.
- Licence/trial expiry stops *new proposals only*; it must never close or modify positions.
