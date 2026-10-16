# Hinova Trading Lab — Architecture & Claude Code Implementation Brief

> **Purpose:** evolve the existing `Heya-56/xauusd-lab` into a modular, auditable, multi-strategy trading research platform that can power a hosted Hinova service and separately licensed white-label deployments.
>
> **Non-negotiable:** correctness and risk controls come before AI autonomy. No strategy is assumed profitable. No live order path may be enabled as part of this specification.

## 1. Product vision

Hinova Trading Lab is a strategy research, decision-support and paper-trading platform for XAUUSD first, designed to support additional instruments only through explicit adapters and validation.

The product offers:
- A futuristic, responsive dashboard with strategy toggles and trading-style profiles.
- Independently testable indicator and price-action strategies.
- A deterministic signal and risk engine.
- Optional AI agents that explain, challenge and compare deterministic results without becoming the source of market truth.
- A daily research loop that proposes improvements, runs reproducible tests and publishes a report; it does **not** silently modify production strategies.
- A customer-local MetaTrader 5 Expert Advisor (EA) or connector that can transmit authorized market/account metadata and receive structured signals. The client retains their broker account, credentials, funds and terminal execution environment.
- A deployment model for Hinova's own Cloudflare account and separately licensed deployments into a customer's Cloudflare account.

This is an engineering and research product, not a promise of trading returns or a guarantee of error-free AI.

## 2. First task for Claude Code: inspect before changing

Work on branch `feature/gold-engine-mql5-tradingagents` unless the repository state indicates a safer branch is required.

1. Inspect the entire repository tree, git status, current branch, current tests, workflows and existing architecture before edits.
2. Read `README.md`, `docs/CLAUDE-GOLD-ENGINE-BRIEF.md`, `docs/PORTABLE-LAB-PLAN.md`, `docs/SATA-LAB-MAP.md`, `docs/EXTERNAL-STRATEGIES.md` and related files when present.
3. Establish a baseline by running existing deterministic tests and the current smoke test. Record the commands and actual outcomes.
4. Search the workspace for `.mq5`, `.mqh`, `.set`, Strategy Tester reports, screenshots and source notes.
5. If the actual EA source is absent, do not invent its trading rules or claim parity. Record the missing files and proceed only with architecture/UI scaffolding and strategies whose rules are explicitly specified here. Ask for source before claiming an exact EA reproduction.
6. Present a short implementation plan and file-level change list, then implement in small, testable increments. Preserve existing working behavior and data provenance.
7. Do not deploy, merge into the default branch, enable real trading, or claim tests passed unless they actually ran and passed.

## 3. Strict layer separation

Keep these as separate modules with explicit interfaces. Follow existing project conventions rather than duplicating equivalent folders.

### A. Presentation / design system
Owns layout, components, interactions, CSS, responsive behavior and visual states only.

Suggested structure if consistent with the current stack:
- `web/` or existing frontend directory
- `styles/tokens.css`: colors, typography, spacing, radius, shadows, motion
- `styles/layout.css`: dashboard grid, panels, responsive layout
- `styles/components.css`: buttons, cards, strategy switches, badges, tables, charts
- `components/`: reusable UI components
- `pages/dashboard/`: dashboard-specific composition

Design direction: futuristic, professional trading cockpit; dark navy/graphite base, restrained teal/cyan and gold accents, legible contrast, compact but breathable data panels. No decorative effects that reduce readability. Responsive from mobile to desktop.

**CSS must not contain business logic.** A redesign or CSS replacement must not change strategy calculations, API contracts, risk logic, persistence or execution behavior. Frontend must never calculate authoritative BUY/SELL signals.

### B. API / application services
Owns authentication, tenant/customer identity, licenses, feature entitlements, configuration validation, rate limits, audit events and API contracts.

Suggested conceptual modules:
- `api/auth`
- `api/tenants`
- `api/licenses`
- `api/strategies`
- `api/signals`
- `api/research`
- `api/audit`

The API validates requests and calls domain services. It must not embed strategy mathematics in route handlers.

### C. Deterministic core
Owns indicator calculations, strategy evaluation, signal normalization, risk gates, position sizing proposals and backtest semantics. This layer must run without an LLM or paid API.

Suggested conceptual modules:
- `core/market_data`
- `core/indicators`
- `core/strategies`
- `core/signals`
- `core/risk`
- `core/backtest`
- `core/validation`

Keep broker-specific behavior out of the core. Every strategy implements a common interface and returns typed evidence, not free-form prose.

### D. Data layer
Owns data providers, schema validation, provenance, normalization, caching, storage and migrations.

- Normalize candles to a documented OHLCV schema with timestamp, timezone, symbol, timeframe, bid/ask or spread where available, source, instrument type and quality metadata.
- Distinguish XAUUSD spot/CFD data from COMEX futures. Never label `GC=F` or any futures series as XAUUSD spot.
- Do not silently substitute a failed feed with another instrument.
- Fail closed when data is stale, incomplete, duplicated, out of order or from an unknown instrument.
- Use parameterized SQL and allow-listed query templates only. **Never execute raw SQL generated by an LLM.**
- Record schema and strategy versions for every research result.
- Keep customer data tenant-isolated. Enforce tenant scoping in server-side authorization and database access; never rely on frontend filtering.

### E. AI agents (optional plug-in)
Owns analyst/reviewer roles, structured explanations, experiment proposals and approved tool calls. It is not the authoritative source of market prices, indicator values, risk limits or order permissions.

The core must remain fully testable with the AI layer disabled. Do not make a paid model/API mandatory for deterministic research or CI.

## 4. Strategy modules and dashboard toggles

Implement each strategy as a separately enabled/disabled candidate. Keep the list data-driven so adding a strategy does not require rewriting dashboard markup.

Initial strategy registry:
- EMA trend / MA20-MA50.
- MACD (initial default parameters 12/26/9; configurable and versioned).
- RSI (initial period 14; thresholds configurable and versioned).
- Fibonacci retracement, only using confirmed pivots and no future-candle leakage.
- ATR volatility regime and ATR-based stop/target research.
- DeMarker as an isolated research candidate.
- Objective price structure: support/resistance, breakout, pullback and trend conditions.
- Exact MQL5 parity candidate, only after source and dependencies are provided and audited.

Each strategy must expose:
- Stable `strategy_id`, name, version and description.
- Explicit parameters and validated ranges.
- Required data/timeframes and warm-up period.
- Deterministic `evaluate(context) -> StrategyResult` behavior.
- Raw signal (BUY / SELL / NO_TRADE), timestamp, source candle IDs/timestamps, indicator values, rationale codes, invalidation conditions and data-quality status.
- Proposed stop/target and risk inputs when supported; proposals are not execution authorization.
- Unit tests, no-look-ahead tests, regression fixtures and backtest report.

Dashboard behavior:
- Each strategy can be switched on/off independently before analysis.
- Show selected state, data readiness, last evaluation, version, test status and whether it is eligible for the selected trading profile.
- Changing a toggle changes the candidate set for future evaluations; it must not rewrite strategy code or silently change existing positions.
- If no valid strategy is enabled, display NO_TRADE.
- If enabled strategies conflict, display the conflict and evidence; do not invent a consensus.
- Store each user's configuration as a versioned configuration snapshot with timestamp and audit event.

Do not combine all indicators into one opaque score. Measure individual and combined candidates separately, account for correlation, and document the rule used to combine them.

## 5. Trading profiles / time horizons

The dashboard must allow explicit profile selection. Profiles are configurations, not separate hard-coded engines.

Initial profiles:
- **Scalping:** candidate mapping can start with M15 bias, M5 setup and M1 trigger, subject to feed quality, latency and realistic cost assumptions.
- **Intraday:** configurable intraday timeframes and session window; no assumptions about broker timezone.
- **Swing:** candidate mapping can start with D1 bias, H4 setup and M15 trigger, subject to strategy-specific validation.
- **Custom / research:** user selects permitted timeframes and strategy set.

Every profile must define and display:
- Timeframes and session/timezone.
- Data freshness threshold.
- Maximum spread and modeled transaction costs.
- Holding-period assumptions and exit rules.
- Strategy eligibility and parameters.
- Risk limits and the current mode (research, paper, live-disabled).

A profile selection is not an order. Never promise that scalping is suitable for every broker, feed or account.

## 6. Signal contract and BUY/SELL endpoints

Use a strict, versioned JSON schema. Example only:

```json
{
  "schema_version": "1.0",
  "signal_id": "server-generated-id",
  "tenant_id": "server-derived-tenant",
  "symbol": "XAUUSD",
  "instrument_type": "broker-specific-spot-or-cfd",
  "profile": "intraday",
  "timeframe": "M15",
  "decision": "NO_TRADE",
  "strategy_ids": ["macd_v1", "rsi_v1"],
  "data_status": "valid",
  "as_of": "ISO-8601 timestamp",
  "evidence": [],
  "risk_status": "blocked",
  "execution_allowed": false,
  "veto_codes": ["LIVE_EXECUTION_DISABLED"]
}
```

The schema is illustrative. Do not hard-code a fake tenant ID, fake market data, or fabricated evidence.

Requirements:
- Prefer a single signal endpoint returning `BUY`, `SELL` or `NO_TRADE` rather than separate unaudited endpoints that imply orders.
- The server derives tenant identity from authenticated credentials; never trust a tenant ID supplied in a body as authorization.
- Include unique signal ID, timestamp, data provenance, strategy versions, evidence references, expiry, risk result and veto reasons.
- Reject unknown enum values, stale signals, invalid schema versions and missing required evidence.
- Idempotency keys and replay protection for state-changing requests.
- The endpoint returns a proposal only. The client-side EA checks signal expiry, selected mode, local configuration, broker symbol metadata and risk rules again.
- Default `execution_allowed=false`. Keep live execution disabled until separately reviewed, explicitly authorized and tested.
- Never expose broker passwords or trading credentials to the website, AI provider, GitHub repository or central logs.

MQL5's `WebRequest` requires the destination URL to be allow-listed in the terminal settings and is synchronous; account for timeouts, latency and failure behavior. Never block critical terminal processing indefinitely waiting for an AI response. On API outage, invalid response or stale signal, fail closed and do not place an order.

## 7. Anti-hallucination and reliability controls

AI cannot be made perfectly hallucination-free. The system must make hallucinations non-authoritative and detect unsupported claims.

Mandatory controls:
1. **Deterministic source of truth:** prices, candles, indicator values, risk calculations and performance metrics come from validated code and stored records, never from LLM prose.
2. **Structured outputs:** agents return schema-validated fields and evidence IDs. Reject malformed, unsupported or missing fields.
3. **Evidence binding:** every claim about a market setup must reference actual candle timestamps, computed indicator outputs, strategy result IDs or validated data records.
4. **No evidence, no signal:** missing evidence, stale feed, conflicting symbol metadata or failed calculation leads to NO_TRADE / blocked status.
5. **Independent risk veto:** risk gate is deterministic, separate from agents, and can veto even if every agent agrees.
6. **No model-written raw SQL execution:** AI may choose from allow-listed query IDs and validated parameters. A proposed new query goes through code review, tests and migration review.
7. **No direct production code editing:** an agent may open a proposed patch or pull request in an isolated branch. CI and a human approval are required before release.
8. **No self-granted permissions:** the model cannot change its own limits, license, tool permissions, account mode or deployment secrets.
9. **Tool allow-list:** read-only research tools by default. Separate permissions for data read, backtest run, report generation, code proposal and deployment. Deployment is not available to trading-decision agents.
10. **Timeouts and budgets:** bound retries, tokens, latency, requests and compute. On model/provider failure, deterministic core continues or returns NO_TRADE.
11. **Auditability:** persist input snapshot/hash, data source, strategy/config version, model/provider/version if used, prompt/template version, structured output, validation result, vetoes and timestamps. Redact credentials and personal data.
12. **Adversarial tests:** test fabricated indicators, stale candles, prompt injection in external text, SQL injection, conflicting agents, malformed JSON, repeated signals, API outages and tenant-ID spoofing.
13. **No claim inflation:** reports must distinguish backtest, out-of-sample, paper and live results. Never claim a strategy is profitable from in-sample returns alone.

## 8. Agent roles and tool access

Optional roles:
- Technical analyst: summarizes deterministic indicator outputs only.
- Structure analyst: evaluates objective price-structure outputs.
- Bull reviewer: argues for a candidate using evidence references.
- Bear reviewer: seeks falsifying evidence and risk conditions.
- Orchestrator: compares validated strategy results and emits a structured proposal.
- Risk manager: deterministic code, not an LLM authority.
- Research engineer: proposes experiments or patches; cannot publish directly.

Use MCP only where it provides a useful, auditable tool interface. MCP is not the market-data source, database, trading protocol or authorization substitute. If an MCP server is exposed remotely, require authentication, least-privilege scopes, HTTPS, input validation, audit logging and per-tool authorization. Never expose deployment credentials or trading actions to an unrestricted agent.

## 9. Daily improvement loop — propose, test, review, release

Create a scheduled GitHub Actions workflow (or the repository's existing scheduler) that:
1. Validates the current data feed and reports data gaps.
2. Runs the current baseline and a fixed, reproducible candidate set.
3. Runs walk-forward/out-of-sample evaluation and realistic spread, commission and slippage assumptions.
4. Compares new candidates to a locked baseline on identical data windows.
5. Checks trade count, expectancy, profit factor, maximum drawdown, costs, exposure, stability across periods and risk constraints.
6. Writes timestamped CSV/JSON/Markdown reports and records code/data/config versions.
7. If AI is available, it may summarize report artifacts and propose a bounded experiment. The summary must link to actual report fields.
8. Opens a proposal/issue or branch for review; it never merges, deploys or changes the production strategy automatically.

Keep CI deterministic and network-independent where possible. Feed downloads should be a separate, clearly marked job. A failed feed must not generate fake results. Do not optimize against the final holdout set. Require chronological splits or walk-forward validation and document limitations, sample size and any multiple-testing risk.

Daily improvement means daily measured research and review—not automatic strategy mutation or daily parameter changes in a customer's live environment.

## 10. Data, database and multi-tenancy

Keep the current repository's data adapters and provenance model. Inspect before selecting or migrating a database.

Core entities may include:
- `tenants` / `users`
- `licenses` / `subscriptions` / `entitlements`
- `linked_terminals` (non-secret metadata only)
- `strategy_definitions` / `strategy_versions`
- `strategy_configs` / `profile_configs`
- `market_data_sources` / `candle_refs`
- `signal_runs` / `signal_evidence`
- `backtest_runs` / `metrics`
- `audit_events`
- `release_records`

Every tenant-owned row must be authorized server-side and scoped to the authenticated tenant. Add tests proving tenant A cannot read or mutate tenant B's data. Use migrations; do not let an LLM alter the schema ad hoc.

Use Cloudflare D1 only if the existing architecture and workload justify it. Keep data access behind a repository/service interface so a storage adapter can be changed without touching strategy logic. Never put secrets in the database unless the storage and encryption model is explicitly designed and reviewed.

## 11. Hosting, source control and white-label licensing

Primary infrastructure remains under Hinova's control:
- GitHub: source, version control, issues, CI and release artifacts.
- Cloudflare: Hinova's hosted frontend, API/Workers and chosen storage.
- Secrets: Cloudflare secret bindings or GitHub Actions secrets, scoped to the minimum required service and environment.

White-label target:
- Create a reproducible, versioned deployment template for a customer's own Cloudflare account.
- Keep customer-specific branding, domain, configuration, license metadata and secrets in deployment configuration—not in the core code.
- Use a separate Cloudflare account/project/database per licensed deployment where isolation is required.
- The customer owns their Cloudflare account and billing. Hinova receives only the narrow, time-limited/scoped deployment access the customer authorizes.
- Never store a customer's Cloudflare API token in source control. Prefer a customer-run deployment or short-lived scoped credentials. Do not copy Hinova production secrets into a customer's deployment.
- Publish signed/versioned releases and deployment/rollback instructions.
- Add a license manifest and version checks, but do not create a hidden kill switch that could endanger open positions. License expiry may disable new signal generation according to contract; it must not issue closing trades or interfere with the customer's broker.
- Treat the contemplated **€15,000 white-label license** as a commercial proposal, not a value hard-coded into code. Define scope, included updates, support, term, deployment rights, IP, security responsibilities and acceptance in a separate written contract. No revenue or legal compliance claims are implied.

Do not automatically create or deploy into a customer's Cloudflare account until the customer has explicitly authorized the action and the credential scope has been checked.

## 12. Trial and subscription entitlements

The SaaS may offer a 7-day trial, but billing and entitlement checks must be separate from strategy logic.

- Store trial start/end timestamps server-side; never trust browser clock.
- Make trial creation and webhook processing idempotent.
- Validate payment provider webhook signatures.
- Entitlements determine access to dashboard features, research quotas and signal APIs.
- Expiry blocks new premium API operations according to policy; it does not send trading orders.
- Clearly distinguish research, demo/paper and any future live-enabled mode.
- Do not ask users to provide broker passwords. Do not imply that subscription grants custody, broker access or guaranteed profit.

Payment provider is not selected by this brief. Do not invent credentials or assume an integration exists.

## 13. Test strategy and release gates

Minimum tests:
- Unit tests for each indicator and strategy, including warm-up and edge cases.
- Golden/regression fixtures for deterministic outputs.
- No-look-ahead tests and confirmed-pivot tests for Fibonacci/structure logic.
- Invalid/stale/missing/out-of-order market data tests.
- Risk gate veto tests, lot-size metadata validation and symbol specification differences.
- API schema, authentication, license expiry, replay and rate-limit tests.
- Tenant isolation tests.
- SQL injection / query allow-list tests.
- LLM malformed output, unsupported claim and timeout tests.
- UI tests showing toggles and profile selections cannot bypass backend validation.
- Daily research workflow test using fixed local fixtures.
- Deployment smoke test and rollback instructions.

No live execution in this milestone. A later live-enabled release requires a separate explicit scope, broker-specific testing, security review, paper validation, user confirmation and jurisdictional/legal review.

## 14. Delivery order

1. Repository inventory and baseline tests.
2. Document current architecture and missing MQL5 source/data feed.
3. Add domain contracts and strategy registry without changing existing research results.
4. Add deterministic MACD/RSI/Fibonacci/profile configuration tests where implementation is safe.
5. Add signal schema and risk veto contract.
6. Add dashboard strategy toggles and profiles using mocked/fixed fixtures; keep CSS separate from domain code.
7. Add data provenance and query allow-list enforcement.
8. Add optional agent interfaces with no-op/deterministic fallback.
9. Add daily research report workflow that cannot auto-promote.
10. Add tenant/licensing/deployment scaffolding only after architecture review.
11. Run all tests and document actual outcomes.
12. Report changed files, risks, unimplemented parts and next steps. Do not claim a feature exists until it is implemented and tested.

## 15. Acceptance criteria

- Existing lab behavior and experiments are preserved unless a documented, tested change is approved.
- Core, data, API, agents and CSS are separately testable.
- The UI can enable/disable each strategy and select scalping/intraday/swing/custom profiles.
- Each output is reproducible from recorded data/config/strategy versions.
- Invalid data or unsupported AI claims result in NO_TRADE/blocked, never a fabricated BUY/SELL.
- AI cannot execute arbitrary SQL, change risk limits, publish code or deploy.
- Daily research produces evidence-based reports and proposals but cannot auto-promote strategies.
- No API key or paid AI provider is required to run deterministic tests.
- Spot/futures identity and feed limitations are explicit.
- Customer deployments are isolated and credentials are never committed.
- No live orders are sent or enabled by this brief.
- Final report lists only tests actually run and their observed results.
