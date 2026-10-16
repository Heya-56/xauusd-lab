# XAUUSD Lab — Hinova Trading Lab foundation

A research and paper-validation laboratory for XAUUSD strategies. The deterministic research core remains authoritative; optional AI agents may explain and review evidence, but must never invent market data, bypass risk controls or automatically promote strategies. **No live orders are enabled.**

## Start here

- **[Claude Code: full Hinova Trading Lab architecture and implementation brief](docs/CLAUDE-HINOVA-TRADING-LAB-SPEC.md)** — system layers, strategy toggles, scalping/intraday/swing profiles, anti-hallucination controls, daily research loop, multi-tenancy, Cloudflare white-label deployment and acceptance criteria.
- [Claude Code: MQL5-first gold engine brief](docs/CLAUDE-GOLD-ENGINE-BRIEF.md) — locate and audit the actual EA source before claiming strategy parity.
- [GitHub Actions](https://github.com/Heya-56/xauusd-lab/actions) — select **Lab smoke test** and choose **Run workflow** to validate the current code and safety checks.
- [Portable lab implementation plan](docs/PORTABLE-LAB-PLAN.md).
- [S.A.T.A. lab mapping](docs/SATA-LAB-MAP.md).

## Hinova Trading Lab — status 2026-10-16

End-to-end chain built and tested: MT5 bridge EA → Cloudflare Worker (accounts, trial, e-mail
verification, terminal keys, configs) → HMAC-signed Python engine → live dashboard. Walk-forward
validation and a 0–10 score rank strategies. **Nothing is deployed; live execution is disabled; no
XAUUSD spot/CFD performance is claimed** (no verified dataset yet). S.A.T.A. is evaluated only as an
external package, pending a written licence from its author.

```bash
pip install pyyaml pytest
pytest -q                                                     # full deterministic suite
python research/daily_research.py --mode real    --out reports/out/real      # DATA_MISSING until data/verified/ is filled
python research/daily_research.py --mode fixture --out reports/out/fixture \
       --baseline reports/baseline/fixture_baseline.json --fail-on-regression
python research/build_dashboard_snapshot.py                   # regenerate web/data/demo-snapshot.json
python -m http.server 8000 --directory web                    # dashboard (demo, synthetic)
```

- [Audit 2026-10-15](docs/AUDIT-2026-10-15.md) — baseline, risks found, new architecture
- [MQL5 audit status](docs/MQL5-STRATEGY-AUDIT.md) — source missing, files requested
- [EA ↔ API contract](docs/EA-BRIDGE-CONTRACT.md) · [Architecture, deployment & rollback](docs/DEPLOYMENT-CLOUDFLARE.md)
- MT5: [Hinova Bridge](mql5/HinovaBridge/README.md) (signals) · [Hinova Gold Scanner](mql5/HinovaGoldScanner/README.md) (spot vs futures)
- [Verified data format](data/verified/README.md) · [Score 0-10 and AI policy](docs/SCORING-AND-AI-POLICY.md)

## Data-source status — read before interpreting results

Yahoo Finance returned HTTP 404 for `XAUUSD=X`. The older `GC=F` ticker represents COMEX gold futures, not XAUUSD spot, and must not be reported as spot performance. The IBKR runner currently requires a local authenticated IB Gateway/TWS session, so it is not the no-install GitHub Actions route. Until a valid and verified spot/CFD feed is configured, **no XAUUSD spot backtest result is claimed**.

## Research protocol

- Candidates use the same verified data, timestamps, cost/slippage assumptions and execution model.
- Require chronological out-of-sample or walk-forward validation; do not select a winner on in-sample returns alone.
- Require at least 30 trades for preliminary consideration and document sample-size limitations.
- Report trade count, expectancy, profit factor, maximum drawdown, costs, exposure and out-of-sample performance.
- Failed, stale or mismatched data must result in an explicit failure/NO_TRADE state, never fabricated results.

The existing competition runner evaluates five candidate families across five Paris-time entry hours and two holding horizons (50 configurations), but its current Yahoo XAUUSD data fetch is blocked.

## Architecture principles

- **Presentation:** CSS, dashboard components and responsive layout only; never authoritative signal logic.
- **API/application:** authentication, tenant isolation, licenses, entitlements, audit events and validated contracts.
- **Deterministic core:** indicator calculations, independent strategy modules, signal schemas, risk gates and backtesting; runs without an LLM.
- **Data layer:** source adapters, normalized OHLC, instrument identity, provenance, quality checks, parameterized/allow-listed queries and migrations.
- **Optional agents:** structured analysis, bull/bear review and research proposals with evidence references; no arbitrary SQL, direct production edits or self-authorized deployment.
- **Daily research:** repeatable reports and proposed experiments; no automatic strategy promotion or deployment.
- **Adapters:** isolated MT5/IBKR data or paper-execution integrations; no broker credentials in browser code, logs or GitHub.
- **White-label:** reproducible versioned deployment into a customer's own Cloudflare account, with narrowly scoped customer-authorized access and separate secrets/configuration.

## Current strategy research

The S.A.T.A. mapping describes 12 candidates from three horizons and four methods:

- Scalping: M15 bias, M5 setup, M1 trigger.
- Normal: H4 bias, H1 setup, M15 trigger.
- Swing: D1 bias, H4 setup, M15 trigger.
- Methods: tendance, SMC, order block and combined.

These are research mappings, not proof of profitability. MACD, RSI, Fibonacci, MA20/MA50, ATR, DeMarker and price-structure candidates must each be independently versioned, testable and switchable. Fibonacci pivots and all pattern detectors must avoid look-ahead/repainting.

## Safety baseline

- Research runner does not submit orders.
- Paper validation is a separate stage.
- Live execution remains disabled by default and is out of scope for the current brief.
- An independent deterministic risk gate can veto every proposed setup.
- Invalid/stale data, malformed agent output, API failure or missing evidence must fail closed.
- No grid, martingale, averaging down or unlimited position stacking.
- Never expose broker credentials to the website, an LLM provider or the repository.
- Never claim tests passed unless they actually ran and passed.

## Current working branch

`feature/gold-engine-mql5-tradingagents` (based on `integration/sata-lab-v2`).

Before strategy-specific implementation, inspect the repository and locate the actual `.mq5`, `.mqh`, `.set` and Strategy Tester files. If the source is missing, do not invent the original strategy's rules or claim parity. Continue only with scaffolding and explicitly specified, independently testable components.
