# MQL5 strategy audit — status: SOURCE MISSING

Date: 2026-10-15. Searched the repository and the build workspace for `*.mq5`, `*.mqh`,
`*.set` and Strategy Tester reports. **No file found.**

Per `docs/CLAUDE-GOLD-ENGINE-BRIEF.md`, no S.A.T.A./EA rule has been reconstructed or
guessed. The registry exposes `sata_mql5_parity` as **unavailable**; the API and the
dashboard refuse to enable it.

## Files needed to start the audit

1. The EA source: `<name>.mq5`
2. All included headers: `*.mqh` (and any library they include)
3. The tester / live input set: `*.set`
4. Optionally: a Strategy Tester report (HTML/XML) and the broker symbol specification
   (contract size, tick size/value, digits, volume min/max/step) used for it.

Do not include account numbers, passwords or server credentials.

## Audit template (to fill once sources are provided)

1. Entry rules — closed vs forming candle
2. Exit rules — SL/TP, trailing, break-even, partials, time exits
3. Indicators, exact parameters, timeframes, filter order
4. Risk & lot sizing — tick value/size, digits, volume constraints
5. Position management — magic numbers, duplicate prevention, retries
6. Sessions/timezone, spread, news, day-of-week filters
7. Look-ahead / repainting / bar-index / sizing bugs found
8. Parity table

| MQL5 behaviour (file:line) | Python implementation | Parity test |
|---|---|---|
| _pending sources_ | — | — |
