# Strategy score (0-10) and AI policy

## Score — `src/core/scoring.py` (`score_v1`)

Deterministic: computed only from recorded backtest metrics. No AI, no network.

| Tier | Score | Colour | Meaning |
|---|---|---|---|
| REJECTED | < 5 | red | Not used |
| WATCH | 5 – 6 | orange | Keep observing; not tradable |
| RETAINED | ≥ 6 | green | Eligible for **paper trading only** |

Live trading is never triggered by a score. It requires weeks of paper results and an
explicit human decision.

| Component | Weight | Full marks when |
|---|---|---|
| Out-of-sample expectancy (R) | 3 | ≥ 0.30 R per trade |
| Out-of-sample profit factor | 2 | ≥ 1.8 |
| IS/OOS stability | 2 | OOS ≥ 50 % of in-sample, same sign |
| Recovery factor (net / max DD) | 2 | ≥ 2 |
| Sample size | 1 | ≥ 100 trades |

Hard gates: < 30 trades → max 4.0 · < 10 OOS trades → max 4.5 · OOS expectancy ≤ 0 → max 4.9 ·
synthetic data → 0. A strategy that only shines in-sample can never reach orange.

## History

Each scheduled run appends one line to `history/scores.jsonl` on the dedicated
`research-history` branch (never `main`), with the run's `scores.csv`,
`retained_strategies.json` and `report.md` under `runs/<run_id>/`. Each line records commit,
data hash, config hash, strategy versions and score version, so any score can be reproduced.

## AI policy — `config/ai_policy.json`

- **Off by default.** Prices, indicators, risk, backtests and scores never use AI.
- If enabled, AI may only *review a signal* or *summarise a report*, citing existing evidence IDs.
- Hard caps checked **before** any call: calls/day, tokens/call, tokens/day, timeout. A refused
  call costs nothing and falls back to deterministic output. Every call or refusal is logged.
- **Proof of no hallucination impact:** `tests/test_agents.py::test_proof_decision_identical_with_and_without_ai`
  checks on every sampled bar that the decision record is byte-identical with AI off, AI failing
  and AI fabricating evidence. Fabricated evidence IDs are rejected.
