"""Trading papier MANUEL depuis le Flight Deck : l'utilisateur ouvre ses positions (SL, TP1, TP2),
le bot les suit au tick près avec les mêmes règles que le backtest :
TP1 → 50 % fermés + stop au point mort ; TP2 ou SL → fermeture du reste.
Aucun ordre n'est envoyé au broker : tout est simulé, sur les prix réels du flux."""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from src.engine.position import Position
from src.journal import Journal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperError(ValueError):
    pass


class ManualPaperBook:
    def __init__(self, journal: Journal, starting_equity: float = 10_000.0, contract_size: float = 100.0,
                 max_lots: float = 1.0):
        self.j, self.contract_size, self.max_lots = journal, contract_size, max_lots
        self.lock = threading.Lock()
        self.last = {"bid": None, "ask": None, "ts": None}
        if self.j.get("manual_account") is None:
            self.j.set("manual_account", {"equity": starting_equity, "start": starting_equity})
        self.positions: dict[str, Position] = {}
        for pid, d in (self.j.get("manual_positions") or {}).items():
            init_stop, init_risk = d.pop("initial_stop"), d.pop("_initial_risk")
            p = Position(**d); p.initial_stop, p._initial_risk = init_stop, init_risk
            self.positions[pid] = p

    # ---------- persistance ----------
    def _save(self):
        self.j.set("manual_positions", {pid: {**asdict(p), "initial_stop": p.initial_stop, "_initial_risk": p._initial_risk}
                                        for pid, p in self.positions.items()})

    def _book(self, p: Position, delta: float):
        acct = self.j.get("manual_account"); acct["equity"] += delta; self.j.set("manual_account", acct)

    def _finish(self, pid: str):
        ex = self.j.get("manual_exits") or {}
        night = ex.pop(pid, None) is not None
        if night:
            self.j.set("manual_exits", ex)
        p = self.positions.pop(pid)
        self.j.add_trade(p, "PAPIER-NUIT" if night else "PAPIER-MANUEL")

    # ---------- actions ----------
    def open(self, side: str, lots: float, sl: float | None = None, tp1: float | None = None, tp2: float | None = None,
             sl_dist: float | None = None, r1: float = 1.0, r2: float = 2.0, exit_at: str | None = None) -> dict:
        """SL/TP en prix absolus, ou en distance (sl_dist, en $) et multiples de R, calculés sur le prix d'exécution."""
        side = side.upper()
        with self.lock:
            bid, ask = self.last["bid"], self.last["ask"]
            if bid is None:
                raise PaperError("Aucun prix reçu : le flux MT5 doit tourner")
            if side not in ("BUY", "SELL"):
                raise PaperError("Sens invalide")
            if not 0.01 <= lots <= self.max_lots:
                raise PaperError(f"Taille entre 0.01 et {self.max_lots} lot")
            entry = ask if side == "BUY" else bid
            s = 1 if side == "BUY" else -1
            if sl_dist:
                if sl_dist <= 0:
                    raise PaperError("Distance de stop invalide")
                sl, tp1, tp2 = entry - s * sl_dist, entry + s * sl_dist * r1, entry + s * sl_dist * r2
            if sl is None:
                raise PaperError("SL obligatoire")
            if s * (entry - sl) <= 0:
                raise PaperError("Le SL doit être sous le prix pour un achat, au-dessus pour une vente")
            r = abs(entry - sl)
            tp1 = tp1 if tp1 else entry + s * r
            tp2 = tp2 if tp2 else entry + 2 * s * r
            if s * (tp1 - entry) <= 0 or s * (tp2 - tp1) < 0:
                raise PaperError("Il faut TP1 au-delà de l'entrée et TP2 au-delà de TP1")
            pid = uuid.uuid4().hex[:8]
            self.positions[pid] = Position(side, round(entry, 2), round(sl, 2), round(tp1, 2), round(tp2, 2),
                                           round(lots, 2), self.last["ts"] or _now(), self.contract_size, 0.0)
            if exit_at:                       # sortie à heure fixe (fenêtre nuit), en UTC
                ex = self.j.get("manual_exits") or {}; ex[pid] = exit_at; self.j.set("manual_exits", ex)
            self._save()
            return self.view()

    def modify(self, pid: str, sl: float | None = None, tp1: float | None = None, tp2: float | None = None) -> dict:
        with self.lock:
            p = self.positions.get(pid)
            if not p:
                raise PaperError("Position introuvable")
            s = 1 if p.side == "BUY" else -1
            price = self.last["bid"] if p.side == "BUY" else self.last["ask"]
            if sl is not None:
                if price is not None and s * (price - sl) <= 0:
                    raise PaperError("Ce SL serait déjà touché")
                p.stop = round(sl, 2)
            if tp1 is not None and not p.tp1_done:
                p.tp1 = round(tp1, 2)
            if tp2 is not None:
                p.tp2 = round(tp2, 2)
            self._save()
            return self.view()

    def close(self, pid: str, why: str = "MANUEL") -> dict:
        with self.lock:
            p = self.positions.get(pid)
            if not p:
                raise PaperError("Position introuvable")
            price = self.last["bid"] if p.side == "BUY" else self.last["ask"]
            before = p.realized
            p.force_close(price if price is not None else p.entry, self.last["ts"] or _now(), why)
            self._book(p, p.realized - before); self._finish(pid); self._save()
            return self.view()

    def close_all(self, why: str = "STOP") -> None:
        for pid in list(self.positions):
            try:
                self.close(pid, why)
            except PaperError:
                pass

    def due_exits(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        return [pid for pid, at in (self.j.get("manual_exits") or {}).items()
                if pid in self.positions and datetime.fromisoformat(at) <= now]

    def on_tick(self, bid: float, ask: float, ts: str) -> None:
        self.last = {"bid": bid, "ask": ask, "ts": ts}       # prix à jour avant une éventuelle sortie à heure fixe
        for pid in self.due_exits():
            try:
                self.close(pid, "SORTIE HEURE FIXE")
            except PaperError:
                pass
        with self.lock:
            self.last = {"bid": bid, "ask": ask, "ts": ts}
            changed = False
            for pid, p in list(self.positions.items()):
                px = bid if p.side == "BUY" else ask     # on sort au prix réellement disponible
                before = p.realized
                p.update({"ts": ts, "high": px, "low": px, "close": px})
                if p.realized != before:
                    self._book(p, p.realized - before); changed = True
                if not p.is_open:
                    self._finish(pid); changed = True
            if changed:
                self._save()

    # ---------- lecture ----------
    def view(self) -> dict:
        bid, ask = self.last["bid"], self.last["ask"]
        out = []
        for pid, p in self.positions.items():
            s = 1 if p.side == "BUY" else -1
            px = bid if p.side == "BUY" else ask
            open_pnl = s * (px - p.entry) * p.lots * p.remaining * p.contract_size if px is not None else 0.0
            out.append({"id": pid, "side": p.side, "lots": p.lots, "entry": p.entry, "sl": p.stop,
                        "sl_initial": p.initial_stop, "tp1": p.tp1, "tp2": p.tp2, "tp1_done": p.tp1_done,
                        "remaining": p.remaining, "realized": round(p.realized, 2),
                        "pnl": round(p.realized + open_pnl, 2), "opened_at": p.opened_at,
                        "exit_at": (self.j.get("manual_exits") or {}).get(pid)})
        acct = self.j.get("manual_account")
        hist = [r for r in self.j.rows("trades", 30) if r.get("mode") in ("PAPIER-MANUEL", "PAPIER-NUIT")][:10]
        return {"account": {**acct, "equity": round(acct["equity"], 2)}, "positions": out,
                "history": [{k: h[k] for k in ("side", "lots", "entry", "outcome", "pnl", "r", "closed_at")} for h in hist],
                "price": self.last}
