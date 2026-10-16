"""Daily research loop: verify data -> backtest -> compare -> report -> propose.

Two explicit modes:
  --mode real     Uses verified datasets in --data-dir (CSV + .meta.json sidecar).
                  If none are found, writes a DATA_MISSING report and produces
                  NO performance figures. Futures datasets are never reported as spot.
  --mode fixture  Runs the same pipeline on the deterministic SYNTHETIC fixture to
                  detect behavioural regressions against a locked baseline.
                  Results are labelled synthetic and are not market performance.

Outputs (in --out): results.csv, results.json, report.md, proposals.md.
Proposals are written for human review only; nothing is promoted or deployed.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.backtest import run_backtest, split_metrics  # noqa: E402
from src.core.contracts import InstrumentType  # noqa: E402
from src.core.engine import AGGREGATION_RULE  # noqa: E402
from src.core.registry import StrategyRegistry, load_profiles, validate_config  # noqa: E402
from src.data.adapters import CsvFileAdapter, DataUnavailable, SyntheticFixtureAdapter  # noqa: E402
from src.data.ohlc import validate_series  # noqa: E402

TRADABLE = (InstrumentType.SPOT, InstrumentType.CFD)
FIELDS = ["dataset", "instrument_type", "timeframe", "profile", "candidate", "segment", "trades",
          "win_rate_pct", "expectancy", "expectancy_r", "profit_factor", "net_points",
          "max_drawdown_points", "total_costs", "exposure_pct", "sample_warning"]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def load_datasets(mode: str, data_dir: Path) -> tuple[list, list[str]]:
    notes: list[str] = []
    if mode == "fixture":
        return [("synthetic-seed-7", SyntheticFixtureAdapter().load())], notes
    datasets = []
    for csv_path in sorted(data_dir.glob("*.csv")) if data_dir.exists() else []:
        try:
            s = CsvFileAdapter(csv_path).load()
        except DataUnavailable as exc:
            notes.append(f"{csv_path.name}: unavailable ({exc})")
            continue
        if s.provenance.instrument_type not in TRADABLE:
            notes.append(f"{csv_path.name}: instrument_type={s.provenance.instrument_type.value} "
                         "excluded (not XAUUSD spot/CFD)")
            continue
        q = validate_series(s, expected_symbol="XAUUSD", allowed_instrument_types=TRADABLE)
        if not q.ok:
            notes.append(f"{csv_path.name}: quality {q.status.value} {q.issues[:5]}")
            continue
        datasets.append((csv_path.stem, s))
    return datasets, notes


def candidates_for(profile_name: str, profile: dict, registry: StrategyRegistry):
    signal_ids = [s for s in profile["eligible_strategies"]
                  if registry.get(s).available and registry.get(s).role == "signal"]
    filters = [s for s in profile["eligible_strategies"]
               if registry.get(s).available and registry.get(s).role == "filter"]
    out = [(sid, [sid]) for sid in signal_ids]
    if len(signal_ids) > 1:
        out.append(("combined_all_signals", signal_ids))
    if filters and signal_ids:
        out.append(("combined_all_with_filters", signal_ids + filters))
    return out


def run(mode: str, data_dir: Path, out: Path, baseline_path: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    registry, profiles = StrategyRegistry(), load_profiles()
    datasets, notes = load_datasets(mode, data_dir)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": mode, "git_sha": git_sha(),
            "aggregation_rule": AGGREGATION_RULE, "data_notes": notes,
            "strategy_versions": {d["strategy_id"]: d["version"] for d in registry.catalog()}}
    rows: list[dict] = []
    if not datasets:
        meta["status"] = "DATA_MISSING"
    else:
        meta["status"] = "OK"
        meta["datasets"] = []
        for name, series in datasets:
            p = series.provenance
            meta["datasets"].append({"name": name, "symbol": p.symbol, "instrument_type": p.instrument_type.value,
                                     "timeframe": p.timeframe, "source": p.source, "candles": len(series),
                                     "from_ts": series.candles[0].ts, "to_ts": series.last_ts,
                                     "data_hash": series.data_hash()})
            for pname, profile in profiles.items():
                if profile["decision_timeframe"] != p.timeframe:
                    continue
                for cand, ids in candidates_for(pname, profile, registry):
                    config = validate_config({"profile": pname, "strategies": {i: {"enabled": True} for i in ids}},
                                             registry, profiles)
                    trades = run_backtest(series, config, registry,
                                          allow_synthetic=(mode == "fixture"))
                    split = split_metrics(trades, series)
                    for seg in ("all", "in_sample", "out_of_sample"):
                        rows.append({"dataset": name, "instrument_type": p.instrument_type.value,
                                     "timeframe": p.timeframe, "profile": pname, "candidate": cand,
                                     "segment": seg, **{k: split[seg].get(k) for k in FIELDS[6:]}})
    regressions = compare_baseline(rows, baseline_path) if baseline_path else []
    proposals = make_proposals(rows, regressions, meta)
    write_outputs(out, meta, rows, regressions, proposals)
    return {"meta": meta, "rows": rows, "regressions": regressions, "proposals": proposals}


def compare_baseline(rows: list[dict], baseline_path: Path) -> list[str]:
    if not baseline_path.exists():
        return [f"BASELINE_MISSING:{baseline_path.name}"]
    base = {(r["dataset"], r["profile"], r["candidate"], r["segment"]): r
            for r in json.loads(baseline_path.read_text())["rows"]}
    issues = []
    current = {(r["dataset"], r["profile"], r["candidate"], r["segment"]): r for r in rows}
    for key, b in base.items():
        c = current.get(key)
        if c is None:
            issues.append(f"MISSING_CANDIDATE:{'/'.join(key)}")
        elif (c["trades"], c["net_points"]) != (b["trades"], b["net_points"]):
            issues.append(f"CHANGED:{'/'.join(key)} trades {b['trades']}->{c['trades']} "
                          f"net {b['net_points']}->{c['net_points']}")
    return issues


def make_proposals(rows, regressions, meta) -> list[str]:
    """Deterministic, evidence-linked suggestions. An optional LLM summariser may
    rewrite these later, but only citing these rows; nothing is auto-applied."""
    props = []
    if meta["status"] == "DATA_MISSING":
        return ["Provide a verified XAUUSD spot/CFD export (CSV + .meta.json) in data/verified/. "
                "No performance can be measured until then."]
    by = {}
    for r in rows:
        by.setdefault((r["dataset"], r["profile"], r["candidate"]), {})[r["segment"]] = r
    for (ds, prof, cand), seg in sorted(by.items()):
        a, i, o = seg.get("all", {}), seg.get("in_sample", {}), seg.get("out_of_sample", {})
        ref = f"[{ds}/{prof}/{cand}]"
        if (a.get("trades") or 0) < 30:
            props.append(f"{ref} only {a.get('trades')} trades (<30): extend history before any conclusion.")
        ie, oe = i.get("expectancy"), o.get("expectancy")
        if ie is not None and oe is not None and ie > 0 >= oe:
            props.append(f"{ref} in-sample expectancy {ie} vs out-of-sample {oe}: likely unstable, do not promote.")
    props += [f"Regression to review: {r}" for r in regressions]
    return props


def write_outputs(out: Path, meta, rows, regressions, proposals) -> None:
    (out / "results.json").write_text(json.dumps({"meta": meta, "rows": rows, "regressions": regressions,
                                                  "proposals": proposals}, indent=2))
    with (out / "results.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    banner = {
        "fixture": "> **SYNTHETIC FIXTURE — NOT MARKET DATA.** These figures only detect code regressions.",
        "real": "> Backtest on verified historical data. Backtest ≠ paper ≠ live. No result implies future profit.",
    }[meta["mode"]]
    lines = [f"# Hinova Trading Lab — daily research ({meta['mode']})", "", banner, "",
             f"- Status: **{meta['status']}**", f"- Generated: {meta['generated_at']}",
             f"- Commit: `{meta['git_sha']}` — aggregation `{meta['aggregation_rule']}`", ""]
    for n in meta["data_notes"]:
        lines.append(f"- Data note: {n}")
    for d in meta.get("datasets", []):
        lines.append(f"- Dataset `{d['name']}`: {d['symbol']} {d['instrument_type']} {d['timeframe']} "
                     f"from `{d['source']}`, {d['candles']} candles, hash `{d['data_hash']}`")
    if rows:
        lines += ["", "| profile | candidate | segment | trades | expectancy | PF | max DD | warning |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['profile']} | {r['candidate']} | {r['segment']} | {r['trades']} | "
                         f"{r['expectancy']} | {r['profit_factor']} | {r['max_drawdown_points']} | "
                         f"{r['sample_warning'] or ''} |")
    lines += ["", "## Regressions", *([f"- {r}" for r in regressions] or ["- none"]),
              "", "## Limitations",
              "- Results are per unit in price points; position sizing needs broker contract metadata.",
              "- Costs are modelling assumptions from config/profiles.json, not broker-measured.",
              "- No parameter optimisation was performed; the out-of-sample segment is a holdout.",
              "- Multiple candidates are compared: beware multiple-testing bias."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    (out / "proposals.md").write_text("# Research proposals (human review required)\n\n" +
                                      ("\n".join(f"- {p}" for p in proposals) or "- none") + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["real", "fixture"], required=True)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "verified"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "out"))
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--fail-on-regression", action="store_true")
    a = ap.parse_args()
    res = run(a.mode, Path(a.data_dir), Path(a.out), Path(a.baseline) if a.baseline else None)
    print(json.dumps({"status": res["meta"]["status"], "rows": len(res["rows"]),
                      "regressions": res["regressions"]}, indent=2))
    if a.fail_on_regression and res["regressions"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
