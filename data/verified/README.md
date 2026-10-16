# Verified XAUUSD datasets

Drop **verified** XAUUSD spot/CFD exports here (e.g. a broker MT5 history export).
The daily research workflow (`--mode real`) only reads this folder. Nothing here is
downloaded automatically and no other instrument is ever substituted.

Each dataset = two files:

`xauusd_m15_<broker>.csv` — normalized OHLC schema v1.0 (header required):

```
ts,open,high,low,close,volume,spread
1767225600,2400.10,2401.55,2399.80,2401.20,1532,0.28
```

- `ts`: UTC epoch seconds of the candle **open**, aligned to the timeframe.
- `spread` (optional): bid/ask spread at close, price units.

`xauusd_m15_<broker>.csv.meta.json` — mandatory provenance:

```json
{
  "symbol": "XAUUSD",
  "instrument_type": "cfd",
  "timeframe": "M15",
  "source": "mt5:<broker-name>:<server>",
  "source_timezone": "UTC",
  "retrieved_at": 1767225600,
  "notes": "Exported from MT5 History Center"
}
```

`instrument_type` must be `spot` or `cfd`. A `futures` dataset (e.g. COMEX `GC=F`)
is excluded from XAUUSD reports. Do not commit licensed data you are not allowed to
redistribute: keep it in a private store and fetch it in a separate, clearly marked job.

## Getting data — current status (2026-10-16)

- **Dukascopy via GitHub Actions: blocked.** Their data server answers GitHub-hosted runners with
  HTTP 202 and empty payloads. The fetch step is disabled by default; we do not bypass it.
- **Recommended route — your broker's MT5 export** (the same feed the EA will trade):
  MT5 → *View → Symbols* → XAUUSD → *Bars* → M15 → choose dates → *Request* → *Export Bars*,
  then convert columns to the schema above with `instrument_type: "cfd"` and
  `source: "mt5:<broker>:<server>"`.
- **Dukascopy from your own computer** (residential IP), research use only:
  `npx dukascopy-node@1.50.0 -i xauusd -from 2025-10-01 -to 2026-10-15 -t m15 -p bid -v -f csv -bs 3 -bp 1500 -r 3 -re`
  (same with `-p ask`), then `python research/import_dukascopy.py ... --ask ...`.

Keep licensed data out of git (see `.gitignore`); store it privately and inject it into CI only
through a separate, explicitly approved job.
