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
