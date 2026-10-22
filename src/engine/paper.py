"""Moteur temps réel en mode papier : chaque bougie clôturée passe par
stratégie → risque → position simulée → journal. Aucun ordre réel n'est envoyé ici."""
from __future__ import annotations

from dataclasses import asdict

from src import killswitch
from src.engine.backtest import SessionFilter
from src.engine.position import Position
from src.engine.risk import RiskManager
from src.journal import Journal


class PaperTrader:
    def __init__(self, cfg: dict, strategy, journal: Journal):
        self.cfg, self.strategy, self.j = cfg, strategy, journal
        self.symbol = cfg["instrument"]["symbol"]
        self.tf = cfg["experiment"]["timeframe"]
        self.rm = RiskManager(cfg)
        self.sess = SessionFilter(cfg)
        costs = cfg.get("costs", {})
        self.cost_side = float(costs.get("spread", 0)) / 2 + float(costs.get("slippage", 0))
        self.mode = "PAPER"
        if self.j.get("account") is None:
            eq = float(cfg.get("paper", {}).get("starting_equity", 10_000))
            self.j.set("account", {"equity": eq, "day": None, "day_start_equity": eq, "realized_today": 0.0, "trades_today": 0})

    def _load_pos(self):
        d = self.j.get("position")
        if not d:
            return None
        init_stop, init_risk = d.pop("initial_stop"), d.pop("_initial_risk")
        p = Position(**d)
        p.initial_stop, p._initial_risk = init_stop, init_risk
        return p

    def _save_pos(self, p):
        self.j.set("position", None if p is None else {**asdict(p), "initial_stop": p.initial_stop, "_initial_risk": p._initial_risk})

    def status(self) -> dict:
        return {"mode": self.mode, "symbol": self.symbol, "timeframe": self.tf, "strategy": self.strategy.name,
                "account": self.j.get("account"), "position": self.j.get("position")}

    def on_candle(self, c: dict) -> dict:
        if not self.j.add_candle(self.symbol, self.tf, c):
            return {"status": "duplicate", "ts": c["ts"]}
        acct = self.j.get("account")
        day = self.sess.day(c["ts"])
        if day != acct["day"]:
            acct.update(day=day, day_start_equity=acct["equity"], realized_today=0.0, trades_today=0)

        events = []
        pos = self._load_pos()
        if killswitch.engaged():
            if pos and pos.is_open:
                before = pos.realized
                pos.force_close(c["close"], c["ts"], "STOP")
                acct["equity"] += pos.realized - before
                acct["realized_today"] += pos.realized - before
                self.j.add_trade(pos, self.mode)
                events.append({"type": "closed", "outcome": "STOP", "pnl": round(pos.realized, 2)})
            self._save_pos(None)
            self.j.set("account", acct)
            return {"status": "halted", "ts": c["ts"], "events": events, "account": acct}
        if pos:
            before = pos.realized
            pos.update(c)
            delta = pos.realized - before
            acct["equity"] += delta
            acct["realized_today"] += delta
            if delta:
                events.append({"type": "fill", "pnl": round(delta, 2)})
            if not pos.is_open:
                self.j.add_trade(pos, self.mode)
                events.append({"type": "closed", "outcome": pos.outcome, "pnl": round(pos.realized, 2)})
                pos = None

        signal = None
        if pos is None and self.sess.allows(c["ts"]):
            hist = self.j.candles(self.symbol, self.tf, limit=max(500, self.strategy.warmup + 5))
            sig = self.strategy.evaluate(hist)
            signal = sig.to_dict()
            decision = None
            if sig.action != "NONE":
                decision = self.rm.evaluate(equity=acct["equity"], day_start_equity=acct["day_start_equity"],
                                            realized_today=acct["realized_today"], open_positions=0,
                                            trades_today=acct["trades_today"], entry=sig.entry, stop=sig.stop_loss)
                if decision.allowed:
                    pos = Position(sig.action, sig.entry, sig.stop_loss, sig.tp1, sig.tp2, decision.size_lots,
                                   c["ts"], self.rm.contract_size, self.cost_side)
                    acct["trades_today"] += 1
                    events.append({"type": "opened", "side": sig.action, "lots": decision.size_lots})
                else:
                    events.append({"type": "rejected", "reason": decision.reason})
                self.j.add_signal(c["ts"], self.strategy.name, sig, decision, self.mode)

        self._save_pos(pos)
        self.j.set("account", acct)
        return {"status": "ok", "ts": c["ts"], "signal": signal, "events": events, "account": acct}
