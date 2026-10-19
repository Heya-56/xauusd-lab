# Hinova Trading Lab — headless evolution plan

Status: implementation branch feature/headless-event-contract-v1, based on
feature/gold-engine-mql5-tradingagents. Nothing is merged or deployed.

## Operating constraints

- Keep main unchanged; make all work reviewable on a feature branch and pull request.
- Preserve the deterministic Python core, strategy registry, risk gate, reports,
  MT5 bridge and research scripts unless a tested migration is approved.
- Research and paper validation only. Real-order execution remains disabled.
- Do not invent S.A.T.A. parity while its original EA source/dependencies are absent.
- Do not label COMEX futures data as XAUUSD spot or publish spot-performance claims
  until a permitted and verified spot/CFD data source is available.
- Do not require a paid LLM for deterministic operation or CI.
- Never commit broker passwords, terminal keys or API secrets.

## Ordered implementation

### 1. Inventory and baseline
- Compare main, integration/sata-lab-v2, feature/strategy-gis-worker and
  feature/gold-engine-mql5-tradingagents.
- Preserve the current feature branch as the starting point; do not merge or delete
  competing branches during this pass.
- Use the repository smoke workflow as the reproducible test entry point. A remote
  file inspection is not a test run.

### 2. Stabilize the existing core
- Keep src/core/contracts.py, src/core/engine.py, src/core/registry.py and
  src/core/risk_gate.py authoritative.
- Identify stale root-level copies before any deletion. Remove only after import/reference
  searches and CI prove they are unused.
- Add event contracts without introducing a broker, network or database dependency.

### 3. Event contract (first vertical slice)
- Add immutable, versioned EventEnvelope.
- Carry event ID, type, UTC timestamp in milliseconds, source, correlation ID,
  optional causation ID and object payload.
- Reject unknown event types, unknown/missing fields, invalid timestamps and unsupported
  schema versions. No event type may authorize an order.
- Add deterministic unit tests and run the repository smoke workflow.

### 4. Data adapters and event transport
- Define source adapters separately for MT5 closed candles, TradingView alerts and
  verified historical CSV/IBKR data. These sources have different guarantees and must
  never be treated as interchangeable.
- Keep transport replaceable. Start with in-process dispatch and a durable research log;
  benchmark before adding a network bus or Rust service.
- Preserve symbol, instrument type, broker/source, timeframe, timezone, spread, retrieval
  time and quality metadata. Invalid/stale/incomplete data must fail closed.

### 5. Strategy and risk pipeline
- Adapt each strategy result to the shared event envelope without changing its maths.
- Run the independent risk gate after aggregation. Conflicts, missing evidence or stale
  data must yield NO_TRADE.
- Add correlation IDs and content hashes to logs/reports so results can be reproduced.

### 6. Storage and SIG-style strategy layers
- Measure actual volume, retention and query needs before choosing storage.
- Keep current SQLite/JSON/CSV research outputs working.
- Evaluate QuestDB only against measured time-series needs; do not make it a hard dependency.
- Build the strategy-layer map from verified candle/strategy outputs, never fabricated
  or UI-calculated signals. Visualization cannot override backend decisions.

### 7. Optional review agents
- Preserve deterministic review roles and evidence-ID validation.
- Any LLM is advisory, budget-capped and optional. It cannot change signals, risk limits,
  tenant identity, deployment permissions or execution state.
- Add independent agents only with defined contracts, timeouts, tests and an ablation
  comparison proving useful incremental value.

### 8. CI, paper validation and release
- Run Python tests, worker tests, safety tests and static compilation.
- Publish reproducible CSV/JSON artifacts with source, instrument, timeframe, period,
  timezone, spread/commission/slippage assumptions and strategy/config/data hashes.
- Require chronological out-of-sample or walk-forward checks and at least 30 trades for
  preliminary consideration; document sample-size limits.
- Validate with a demo/paper workflow before considering any future execution scope.
- Open a pull request for review. Do not merge or deploy automatically.

## Known blockers from the existing audit
- The repository audit says Yahoo XAUUSD=X returns 404. GC=F is COMEX futures,
  not spot XAUUSD.
- IBKR historical data requires an authenticated local IB Gateway/TWS session;
  GitHub Actions cannot assume that local gateway exists.
- Exact S.A.T.A. EA source/dependencies and parity material are not present.
- MetaEditor is Windows-only; MQL5 sources are not compiled merely because Python CI passes.

## First deliverable
A tested, transport-neutral event envelope and this ordered plan, isolated on a feature
branch. The next changes should build on this contract only after CI passes. All later
infrastructure remains optional until measurements and data-source blockers are resolved.
