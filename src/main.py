"""Interface en ligne de commande du XAUUSD Lab.

  python -m src.main check                     # vérifie la configuration
  python -m src.main backtest --csv data.csv   # backtest sur un export MT5/TradingView
  python -m src.main backtest --yahoo          # backtest rapide sur données Yahoo (GC=F, recherche)
  python -m src.main replay --csv data.csv     # rejoue un CSV bougie par bougie dans le moteur papier
  python -m src.main serve                     # lance le webhook TradingView (mode papier)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml

from src.engine.backtest import run_backtest
from src.engine.experiment import Experiment
from src.strategies.registry import default_registry


def load_cfg(path):
    return yaml.safe_load(Path(path).read_text())


def load_candles(args, cfg):
    if args.csv:
        from src.data.csv_adapter import CsvAdapter
        return CsvAdapter(args.csv).candles(start=args.start, end=args.end)
    if args.yahoo:
        from src.data.yahoo_adapter import YahooAdapter
        return YahooAdapter().candles("XAUUSD", cfg["experiment"]["timeframe"])
    if args.ibkr:
        from src.data.ibkr_adapter import IBKRAdapter
        return IBKRAdapter().candles("XAUUSD", cfg["experiment"]["timeframe"])
    sys.exit("Choisir une source : --csv FICHIER, --yahoo ou --ibkr")


def cmd_check(args, cfg):
    print(Experiment(cfg).run().to_json())


TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}


def cmd_backtest(args, cfg):
    candles = load_candles(args, cfg)
    if not candles:
        sys.exit("Aucune bougie chargée.")
    if args.strategy == "all":
        tf = TF_SECONDS.get(args.tf or cfg["experiment"]["timeframe"], 300)
        rows = []
        from src.agents.sql_backtest import sql_strategies
        for strat in default_registry().all() + sql_strategies():
            if strat.timeframe != tf:
                continue
            res = run_backtest(candles, strat, cfg, equity=args.equity)
            a, o = res["all"], res["out_of_sample"]
            rows.append([strat.name, a["trades"], a["win_rate_pct"], a["expectancy_r"], a["profit_factor"],
                         a["max_drawdown_pct"], o["trades"], o["expectancy_r"], o["profit_factor"]])
        head = ["stratégie", "trades", "gagnants %", "espérance R", "PF", "DD max %", "OOS trades", "OOS esp. R", "OOS PF"]
        print(" | ".join(head))
        for r in rows:
            print(" | ".join(str(x) for x in r))
        print("\nOOS = hors échantillon (30 % finaux). Moins de 30 trades = non significatif.")
        return
    strat = default_registry().get(args.strategy or cfg.get("strategy", {}).get("name", "ema_cross"))
    res = run_backtest(candles, strat, cfg, equity=args.equity)
    trades = res.pop("trades")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "backtest.json").write_text(json.dumps({**res, "trades": trades}, indent=2))
    with open(out / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trades[0].keys()) if trades else ["opened_at"])
        w.writeheader()
        w.writerows(trades)
    print(json.dumps(res, indent=2, default=str))
    oos = res["out_of_sample"]
    print(f"\n→ {res['all']['trades']} trades · out-of-sample : {oos['trades']} trades, "
          f"espérance {oos['expectancy_r']} R, PF {oos['profit_factor']}, DD max {oos['max_drawdown_pct']} %")
    if not res["all"]["enough_trades"]:
        print("⚠ Moins de 30 trades : échantillon insuffisant, le résultat ne prouve rien.")
    print(f"Résultats écrits dans {out}/")


def cmd_replay(args, cfg):
    from src.engine.paper import PaperTrader
    from src.journal import Journal
    candles = load_candles(args, cfg)
    db = args.db or "replay.sqlite"
    if Path(db).exists():
        Path(db).unlink()
    strat = default_registry().get(cfg.get("strategy", {}).get("name", "ema_cross"))
    t = PaperTrader(cfg, strat, Journal(db))
    for c in candles:
        r = t.on_candle(c)
        for e in r.get("events", []):
            print(c["ts"], e)
    print(json.dumps(t.status(), indent=2))


def cmd_serve(args, cfg):
    import uvicorn
    os.environ.setdefault("XAUUSD_CONFIG", args.config)
    uvicorn.run("src.api:app", host=args.host, port=args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="xauusd-lab")
    p.add_argument("--config", default="config/experiment.yml")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check")
    for name in ("backtest", "replay"):
        s = sub.add_parser(name)
        s.add_argument("--csv")
        s.add_argument("--yahoo", action="store_true")
        s.add_argument("--ibkr", action="store_true")
        s.add_argument("--start")
        s.add_argument("--end")
        if name == "backtest":
            s.add_argument("--strategy", help="nom de la stratégie, ou all")
            s.add_argument("--tf", help="unité de temps du CSV pour --strategy all (5m, 1m…)")
            s.add_argument("--equity", type=float, default=10_000)
            s.add_argument("--out", default="results")
        else:
            s.add_argument("--db")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    cfg = load_cfg(args.config)
    {"check": cmd_check, "backtest": cmd_backtest, "replay": cmd_replay, "serve": cmd_serve,
     None: cmd_check}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
