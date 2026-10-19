# Hinova XAUUSD Lab — decoupled target architecture

This is the implementation contract for the lab. Evolve the existing repository; do not
replace it with a second monolithic bot.

## Data path

`vendor/source adapters -> WebSocket transport -> Rust event bus -> canonical Tick events
-> strategy consumers (Python and SQL) -> research/persistence -> comparator`

### 1. Source adapters
- MT5 bridge: broker-specific bid/ask ticks and closed candles; distinguish terminal time from receive time.
- TradingView: alert/webhook adapter. Alerts are events, not a tick feed; never fabricate ticks from alerts.
- IBKR: authenticated local Gateway/TWS adapter; respect entitlement, pacing and instrument contract details.
- CSV/historical: reproducible replay with file hash, timezone, source, instrument and coverage metadata.
- Every adapter declares instrument type and provenance. `GC=F` futures must never be relabeled as spot XAUUSD.

### 2. WebSocket boundary
Adapters publish a versioned, normalized schema. Consumer transport must not import vendor SDKs.
Reconnect/backoff, heartbeat, auth, TLS, idempotency and durable recovery are production gates.

### 3. Rust event bus
The initial implementation lives at `services/rust-event-bus`. It validates Tick v1 and fans
out over WebSockets. Current implementation is an in-memory prototype, bound to loopback by
default. It is not durable and must not be publicly exposed. Add a durable log/replay layer and
consumer acknowledgements before treating it as a production bus.

### 4. Strategy agents
- Python agents: deterministic indicators, strategy implementations, backtesting and scoring.
- SQL agents: declarative queries/rules over persisted market events and time windows.
- Both consume the same canonical schema and emit versioned `StrategySignal` events; neither
  may directly execute orders.
- Existing `src/core` remains the authoritative deterministic engine until parity tests prove
  any refactor safe. Do not fork the strategy maths into Rust.

### 5. Storage
- PostgreSQL: configuration, strategy registry metadata, experiment manifests, account/tenant
  metadata and audit relations.
- QuestDB: high-volume timestamped ticks/bars/derived measurements where benchmarks justify it.
- Local JSONL/CSV: portable fixture/replay artifacts and reproducible research outputs.
- Define retention, idempotency keys and schema migrations before connecting storage writers.

### 6. Safety and validation
- Event types are data contracts, not permission to trade.
- Unknown schema, stale ticks, crossed markets, gaps or conflicting instrument metadata fail closed.
- Keep `LIVE_EXECUTION_ENABLED=False` and `execution_allowed=False`. No live order route is part
  of this implementation.
- Validate in stages: Rust contract tests; deterministic Python contract tests; adapter fixtures;
  replay parity; throughput/lag/reconnect tests; persistence integration; only then paper validation.
- CI success proves code checks passed, not that broker data, MQL5 compilation, or profitability
  has been validated.

## Current implementation status

- Existing Python event envelope / in-process bus: present on the parent feature branch.
- Rust WebSocket tick ingress/fan-out prototype: added in `services/rust-event-bus`.
- Vendor-specific WebSocket adapters: not yet implemented.
- Python and SQL agent consumers over the Rust bus: not yet connected.
- PostgreSQL/QuestDB writers: not yet connected.
- Durable event log/replay and authenticated transport: not yet implemented.
