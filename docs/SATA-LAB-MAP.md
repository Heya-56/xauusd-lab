# S.A.T.A. × XAUUSD Lab

## Cartography

| Horizon | Bias | Setup | Trigger | Methods |
|---|---|---|---|---|
| Scalping | M15 | M5 | M1 | tendance, smc, orderblock, combine |
| Normal | H4 | H1 | M15 | tendance, smc, orderblock, combine |
| Swing | D1 | H4 | H1 | tendance, smc, orderblock, combine |

This creates 12 deterministic candidates.

## Division of responsibility

### S.A.T.A.
- Strategy logic
- Indicators
- Sessions
- Economic calendar filter
- Money management
- Position management
- Broker abstraction
- IBKR Gateway adapter

### XAUUSD Lab
- Candidate registry
- Data provenance
- Reproducible experiments
- Cross-strategy comparison
- Out-of-sample validation
- Confluence
- Experiment history
- Research dashboard

## Trading path

Market data -> strategy candidates -> normalized votes -> filters -> risk -> Paper execution -> journal -> Lab

Live execution is intentionally outside the first validation stage.

## Important

The Lab must not copy S.A.T.A.'s simulated XAU/USD contract economics as broker truth.
For real Paper execution, contract size, increments, prices and other trading rules must
come from the connected broker/instrument contract.
