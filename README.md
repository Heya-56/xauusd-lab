# Dashboard API contract

Read-only endpoints for the first dashboard:

GET /api/market/xauusd
GET /api/market/xauusd/candles
GET /api/experiment/current
GET /api/experiment/history
GET /api/strategies
GET /api/strategies/:id/results
GET /api/data/quality
GET /api/signals/current
GET /api/trades
GET /api/performance

The browser must never receive broker credentials or contain order-execution logic.
