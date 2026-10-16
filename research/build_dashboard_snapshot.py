"""Build web/data/demo-snapshot.json from the deterministic engine.

The dashboard never computes signals: it renders this server-produced snapshot
(later: the /v1 API). The demo snapshot uses the SYNTHETIC fixture and is
labelled as such in the data and in the UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.review import run_review  # noqa: E402
from src.core.backtest import run_backtest, split_metrics  # noqa: E402
from src.core.contracts import Decision  # noqa: E402
from src.core.engine import evaluate  # noqa: E402
from src.core.registry import StrategyRegistry, load_profiles, validate_config  # noqa: E402
from src.core.risk_gate import AccountState  # noqa: E402
from src.core.scoring import score_strategy  # noqa: E402
from src.data.adapters import SyntheticFixtureAdapter  # noqa: E402
from src.data.ohlc import validate_series  # noqa: E402

DEFAULT_ON = ["macd_cross", "rsi_reversion", "ema_trend", "fibonacci_pullback", "sr_breakout", "atr_regime"]


def build() -> dict:
    reg, profiles = StrategyRegistry(), load_profiles()
    series = SyntheticFixtureAdapter().load()
    cfg = validate_config({"profile": "intraday", "strategies": {s: {"enabled": True} for s in DEFAULT_ON}}, reg)
    acct = AccountState(current_spread=0.30)
    recent, last = [], None
    for i in range(100, len(series)):
        rec = evaluate(series.upto(i), cfg, reg, account=acct, allow_synthetic=True)
        last = rec
        if rec.decision is not Decision.NO_TRADE:
            recent.append({"ts": rec.as_of_ts, "decision": rec.decision.value,
                           "price": series.candles[i].close, "reasons": rec.reason_codes[-1:]})
    run_review(last)
    perf = {}
    for sid in DEFAULT_ON:
        if reg.get(sid).role != "signal":
            continue
        one = validate_config({"profile": "intraday", "strategies": {sid: {"enabled": True}}}, reg)
        perf[sid] = split_metrics(run_backtest(series, one, reg, allow_synthetic=True), series)
        perf[sid]["score"] = score_strategy(perf[sid], synthetic=True)
    q = validate_series(series)
    return {
        "snapshot_kind": "DEMO_SYNTHETIC_FIXTURE",
        "disclaimer": "Données synthétiques de démonstration — pas des données de marché. Aucune performance réelle.",
        "provenance": {"symbol": series.provenance.symbol, "instrument_type": series.provenance.instrument_type.value,
                       "timeframe": series.provenance.timeframe, "source": series.provenance.source,
                       "candles": len(series), "data_hash": series.data_hash(), "quality": q.status.value},
        "catalog": reg.catalog(),
        "profiles": profiles,
        "active_config": {"profile": "intraday", "enabled": DEFAULT_ON, "config_hash": cfg.config_hash},
        "candles": [{"ts": c.ts, "o": c.open, "h": c.high, "l": c.low, "c": c.close} for c in series.candles[-160:]],
        "latest_signal": last.to_dict(),
        "recent_signals": recent[-12:],
        "performance": perf,
    }


if __name__ == "__main__":
    out = ROOT / "web" / "data" / "demo-snapshot.json"
    out.write_text(json.dumps(build(), indent=1))
    print(f"wrote {out.relative_to(ROOT)}")
