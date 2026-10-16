# Hinova Bridge (MT5) — sends closed candles, shows the proposal, never trades

1. Hinova dashboard → **Mon compte** → *Connecter un MT5* → copy the `htl_…` key (shown once).
2. MT5 → *Tools → Options → Expert Advisors* → tick **Allow WebRequest for listed URL** and add the
   API origin (e.g. `https://api.hinova…`).
3. Copy `HinovaBridge.mq5` to `MQL5/Experts/`, compile (F7), drop it on an **XAUUSD** chart.
4. Inputs: `InpApiUrl`, `InpTerminalKey`, `InpTimeframe` = the decision timeframe of your profile
   (M15 for intraday/custom, H4 for swing, M5 for scalping).

Behaviour: on each new **closed** bar (checked every `InpPollSeconds`), it posts the last `InpBars`
closed candles (UTC timestamps, spread in price units), the open-position count on the symbol and
today's realised P/L % — never the login password. The reply is shown on the chart; anything other
than a valid `BUY`/`SELL` (network error, HTTP error, expired signal, unexpected body) is displayed as
`NO_TRADE`. One request per bar, even after an error. `execution_allowed` is always `false`.

Contract: `payload.example.json` is the exact shape; the Worker tests, the engine tests and a
repository test (`tests/test_safety.py`) all check it. Not compiled in CI (MetaEditor is Windows-only).
