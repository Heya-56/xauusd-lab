# Claude Code Brief — XAUUSD Gold Engine (MQL5-first)

## Mission

Build a robust, testable, gold-specific research engine in this repository, using the user's existing MQL5 Expert Advisor as the source of truth for current trading logic. Reuse the best architectural ideas from TauricResearch/TradingAgents without blindly copying the whole application or making paid LLM APIs mandatory.

Work on branch: feature/gold-engine-mql5-tradingagents.
Base branch: integration/sata-lab-v2.

## Mandatory first step: locate and analyse the actual MQL5

Before implementing strategy logic, inspect the current workspace for .mq5, .mqh, Strategy Tester reports, set files and relevant notes. Check common MetaTrader paths and any project attachments/files available to the workspace.

- If the user's actual MQL5 source is present, read it completely and map its behavior before changing anything.
- If it is not present, do not invent or reconstruct its rules from memory. Stop strategy implementation and report exactly which file is missing; ask the user to provide the .mq5 source (and .mqh dependencies / .set file if applicable). Continue only with non-strategy scaffolding and tests that do not assume unknown strategy rules.
- Never commit account credentials, broker login details, API keys, personal data or terminal data.
- Do not upload the MQL5 source to a third-party service.

Produce docs/MQL5-STRATEGY-AUDIT.md with:
1. Entry rules and whether they use closed or forming candles.
2. Exit rules, SL/TP, trailing stop, break-even, partial exits and time exits.
3. Indicators and exact parameters, timeframe(s), filters and confirmation order.
4. Risk calculation, lot sizing, tick value/size, symbol digits, volume min/max/step.
5. Position management, magic numbers, duplicate-entry prevention and order retry logic.
6. Sessions/timezone, spread filters, news filters and day-of-week constraints.
7. Potential look-ahead/repainting, bar-index, order-selection, sizing and execution bugs.
8. A rule-by-rule parity table: MQL5 behavior -> Python implementation -> test covering parity.
Clearly separate verified code facts from assumptions.

## Existing project constraints — preserve them

- This repository is the existing Heya-56/xauusd-lab lab. Extend it; do not create a competing bot or rewrite everything.
- Current architecture has a deterministic research core, data adapters, candidate competition, risk checks and reports. Inspect existing files before editing.
- XAUUSD spot must be identified as such. Do not treat COMEX futures (GC=F) as spot gold, and do not claim a spot backtest if the source is unavailable or invalid.
- Current README states no live orders. Preserve this invariant. Default execution is research/signal/paper only.
- Preserve current candidate experiments and S.A.T.A. mapping unless tests demonstrate a safe, documented migration.
- Keep broker-specific dependencies out of the research core. IBKR/MT5 adapters must be isolated.
- Keep the code runnable on free GitHub Actions where practical. No paid LLM API or paid data feed may be required for deterministic tests.
- Do not introduce grid, martingale, averaging-down or unlimited position stacking.
- Do not tune a strategy on the same data used to report its final performance.

## What to reuse from TradingAgents

Study the upstream source and current Apache-2.0 license before copying anything. Record upstream URL, version/commit, files reused or adapted, modifications and attribution in docs/EXTERNAL-STRATEGIES.md and retain required notices.

Reuse the ideas/components, not the whole framework by default:
- Distinct analyst roles with typed, structured outputs.
- Bull/bear debate or adversarial review of a proposed setup.
- A trader/orchestrator that must cite evidence from deterministic strategy outputs.
- An independent risk manager that can veto any setup.
- Reproducible decision logs and configurable research depth.

TradingAgents' LLM-based reasoning is an optional plugin, not the authoritative source of prices, indicators, trade rules or risk calculations. The core must still run without an LLM using deterministic Python logic. Never allow an LLM to fabricate OHLC data, bypass risk controls or submit an order.

## Gold-specific strategy modules

Implement only after the MQL5 audit is complete. Keep each strategy independently switchable and independently testable:
- Exact MQL5 strategy parity candidate (first benchmark; preserve its rules before enhancements).
- EMA trend / MA20-MA50 benchmark already referenced by the lab.
- MACD (default research parameters 12/26/9; configurable).
- RSI (default 14; configurable).
- Fibonacci retracement, with pivots confirmed without future-data leakage.
- Chart structure: support/resistance, trendlines, breakouts and pullbacks; any pattern detector must define objective rules and avoid repainting.
- ATR volatility regime and ATR-based stop research.
- DeMarker mean-reversion candidate only as an isolated research candidate; do not adopt grid/martingale mechanics.

Do not combine every indicator into one opaque score. Record each candidate's raw signal, evidence, timestamp, data provenance, timeframe, stop/target proposal and veto reason. Measure whether combinations add value beyond individual candidates and control for correlated indicators.

## Architecture target

1. data/: normalized OHLC schema and source/instrument metadata.
2. strategies/: strategy interface plus independent implementations.
3. signals/: typed signal/evidence schema and orchestrator.
4. agents/: deterministic technical analyst, structure analyst, bull reviewer, bear reviewer and trader/orchestrator; optional LLM adapter behind a clean interface.
5. risk/: deterministic risk gate independent of agent outputs.
6. backtest/: event-driven simulation with spread, commission, slippage, realistic fills and explicit bar timing.
7. adapters/: isolated data and paper-execution adapters for IBKR/MT5.
8. reports/: CSV/JSON results and decision explanations.
9. tests/: unit, regression, parity, no-look-ahead, risk-veto and smoke tests.

Follow existing repository conventions where possible rather than creating all folders if equivalent modules already exist.

## Risk and validation gates

- No live-order path may be added or enabled.
- Keep the repository's existing default risk configuration; do not silently change it.
- Validate lot size using broker symbol metadata and tick-value calculations; never assume all XAUUSD brokers use the same contract specification.
- Enforce max risk per trade, max open positions, daily loss limit, max spread, data freshness and valid stop distance before a signal is eligible for paper execution.
- Risk gate must veto even if every analyst agrees.
- All strategies use the same verified data window, timezone, spread/slippage/commission assumptions and execution model.
- Use chronological train/validation/test splits or walk-forward validation. Prevent look-ahead, survivorship/data leakage and hyperparameter overfitting.
- Report trade count, expectancy, profit factor, max drawdown, win/loss distribution, exposure, costs and out-of-sample results. Never present a backtest as a guarantee.
- No strategy can be marked a winner solely from in-sample returns. Require at least 30 trades for preliminary consideration, then document limitations and sample size.
- Keep CI tests deterministic and network-independent. Network-dependent data checks must be separate and clearly marked.

## Implementation sequence

1. Inventory repository, current tests and MQL5 availability.
2. Complete MQL5 audit and parity specification; if source is missing, pause strategy-specific work and request it.
3. Run current tests and record baseline before modifications.
4. Propose a short architecture diff and file plan.
5. Implement the smallest vertical slice: one MQL5-parity strategy -> normalized signal -> risk veto -> backtest/report -> tests.
6. Add technical strategy modules one by one, each with unit tests and comparison reports.
7. Add optional TradingAgents-inspired review/orchestration only after deterministic core works.
8. Run all tests, document results and limitations, and summarize changed files.
9. Do not merge to main, enable live execution, or claim profitable performance.

## Acceptance criteria

- Existing tests and current research workflow continue to work.
- MQL5 behavior is documented and parity differences are explicit.
- The same input candles produce reproducible strategy outputs.
- No future candle information is used for a signal.
- Every proposed setup includes evidence, stop/target, estimated risk and a clear reason when vetoed.
- Agent layer can be disabled and all deterministic tests still pass.
- No API key is required for the core.
- Research output identifies instrument/source/timeframe/cost assumptions and never mislabels futures as spot.
- Final report lists tests actually run and their actual outcomes; do not claim unrun tests passed.
