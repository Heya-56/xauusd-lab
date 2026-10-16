# XAUUSD Strategy GIS Worker

A separate Cloudflare Worker that calculates technical-indicator layers for a selected historical or simulated trade. It is an analysis/visualization service, not an execution engine.

## Why it is separate

- Keeps the existing Python/FastAPI bot and its risk controls untouched.
- Exposes normalized per-candle series and events that a dashboard can render as independently toggleable map-like layers.
- Does not connect to IBKR, submit orders, store secrets, or change the active strategy.
- Keeps heavy backtests in the existing Python research engine; this Worker is intended for bounded chart analysis (maximum 2,000 candles per request).

## Endpoints

- `GET /health`
- `POST /api/v1/strategy-gis/analyze`

Example request:

```json
{
  "symbol": "XAUUSD",
  "timeframe": "M5",
  "candles": [
    { "time": 1792000000, "open": 4200, "high": 4203, "low": 4198, "close": 4201 },
    { "time": 1792000300, "open": 4201, "high": 4205, "low": 4200, "close": 4204 },
    { "time": 1792000600, "open": 4204, "high": 4206, "low": 4202, "close": 4203 }
  ],
  "layers": {
    "ema": true,
    "rsi": true,
    "macd": true,
    "fibonacci": true,
    "atr": false
  },
  "trade": {
    "id": "trade-demo-001",
    "side": "long",
    "entryTime": 1792000300,
    "entryPrice": 4204,
    "stopLoss": 4195,
    "takeProfit": 4222
  }
}
```

The sample is illustrative only. Real input must be chronological OHLC data from the chosen source. The response returns each enabled layer's series/events, Fibonacci levels, trade timestamp mapping, and warnings.

## Layers in v1

- EMA fast/slow and crossover events
- RSI with configurable oversold/overbought levels
- MACD, signal line, histogram, and crossover events
- Fibonacci retracement levels from the high/low of a configurable lookback
- ATR series

## Run locally

```bash
npm install
npm run typecheck
npm run dev
```

## Deployment and safety

Deploy independently from the bot. Before exposing it publicly, add authentication/rate limiting and restrict CORS to the dashboard origin. Never put brokerage API keys in this Worker. This version has no broker adapter and cannot place or modify orders.

The Worker computes indicators; it does not assert that a signal is profitable. Fibonacci levels use a simple lookback high/low and do not infer swing direction. Backtesting, transaction-cost modelling, out-of-sample validation, and paper trading remain separate responsibilities.
