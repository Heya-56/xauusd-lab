"""API webhook (FastAPI) : TradingView → bougie clôturée → moteur papier → journal.

Sécurité : chaque requête doit contenir le secret WEBHOOK_SECRET (dans le JSON ou l'en-tête X-Webhook-Secret).
Le navigateur ne reçoit jamais d'identifiants broker et ne contient aucune logique d'exécution.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src import killswitch

from src.engine.paper import PaperTrader
from src.journal import Journal
from src.strategies.registry import default_registry

CONFIG_PATH = os.getenv("XAUUSD_CONFIG", "config/experiment.yml")
DB_PATH = os.getenv("XAUUSD_DB", "xauusd_lab.sqlite")


class CandleAlert(BaseModel):
    """Message d'alerte TradingView (voir docs/02-tradingview-webhook.md)."""
    secret: str | None = None
    symbol: str = "XAUUSD"
    time: str = Field(..., description="Heure d'ouverture de la bougie, ISO-8601 ou epoch ms ({{time}})")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class MT5Position(BaseModel):
    ticket: int
    symbol: str
    type: int                 # 0 = achat, 1 = vente (convention MT5)
    volume: float
    price_open: float
    sl: float = 0
    tp: float = 0
    price_current: float = 0
    profit: float = 0
    time: int = 0


class PositionsReport(BaseModel):
    positions: list[MT5Position]


class PaperOpen(BaseModel):
    side: str
    lots: float = 0.01
    sl: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    sl_dist: float | None = None
    r1: float = 1.0
    r2: float = 2.0


class PaperModify(BaseModel):
    id: str
    sl: float | None = None
    tp1: float | None = None
    tp2: float | None = None


class PaperClose(BaseModel):
    id: str


class KillRequest(BaseModel):
    engaged: bool
    reason: str = "STOP manuel depuis l'interface"


def create_app(config_path: str = CONFIG_PATH, db_path: str = DB_PATH) -> FastAPI:
    cfg = yaml.safe_load(Path(config_path).read_text())
    strategy = default_registry().get(cfg.get("strategy", {}).get("name", "ema_cross"))
    trader = PaperTrader(cfg, strategy, Journal(db_path))
    secret = os.getenv("WEBHOOK_SECRET", "")
    admin_token = os.getenv("ADMIN_TOKEN", "")
    feed_symbol = cfg.get("instrument", {}).get("feed_symbol", "GOLD")
    app = FastAPI(title="XAUUSD Lab", version="1.1.0")
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-Admin-Token"])

    import time as _time
    _cache: dict = {}

    class _CachedQDB:
        """Évite de solliciter QuestDB à chaque rafraîchissement d'écran : réponses gardées 1,5 s."""
        def __init__(self):
            from src.agents.questdb import QuestDB
            self.q = QuestDB(ilp="")

        def query(self, sql):
            hit = _cache.get(sql)
            if hit and _time.monotonic() - hit[0] < 1.5:
                return hit[1]
            rows = self.q.query(sql)
            _cache[sql] = (_time.monotonic(), rows)
            return rows

        def recent_bars(self, symbol, tf, limit):
            from src.agents.questdb import QuestDB
            return QuestDB.recent_bars(self, symbol, tf, limit)

    def qdb():
        return _CachedQDB()

    # ---------- trading papier manuel, suivi au tick par le bus ----------
    from src.engine.manual_paper import ManualPaperBook, PaperError
    book = ManualPaperBook(Journal(db_path), float(cfg.get("paper", {}).get("starting_equity", 10_000)),
                           float(cfg.get("instrument", {}).get("contract_size", 100)))
    app.state.book = book

    async def follow_bus():
        import asyncio, json
        import websockets
        url = os.getenv("BUS_URL", "ws://127.0.0.1:9100/subscribe")
        while True:
            try:
                async with websockets.connect(url, max_size=2**22) as ws:
                    async for raw in ws:
                        ev = json.loads(raw)
                        if ev.get("type") == "tick" and ev.get("symbol") == feed_symbol:
                            from datetime import datetime, timezone
                            ts = datetime.fromtimestamp(ev["ts_ms"] / 1000, tz=timezone.utc).isoformat()
                            book.on_tick(ev["bid"], ev["ask"], ts)
            except Exception:
                await asyncio.sleep(3)

    @app.on_event("startup")
    async def _start_follow():
        if os.getenv("XAUUSD_NO_BUS") != "1":
            import asyncio
            app.state.follow = asyncio.create_task(follow_bus())

    @app.get("/api/paper")
    def paper_view():
        return book.view()

    @app.post("/api/paper/open")
    def paper_open(req: PaperOpen):
        if killswitch.engaged():
            raise HTTPException(423, "STOP engagé : ouverture refusée")
        try:
            return book.open(req.side, req.lots, req.sl, req.tp1, req.tp2, req.sl_dist, req.r1, req.r2)
        except PaperError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/paper/modify")
    def paper_modify(req: PaperModify):
        try:
            return book.modify(req.id, req.sl, req.tp1, req.tp2)
        except PaperError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/paper/close")
    def paper_close(req: PaperClose):
        try:
            return book.close(req.id)
        except PaperError as e:
            raise HTTPException(400, str(e))

    def require_admin(token):
        if not admin_token:
            raise HTTPException(503, "ADMIN_TOKEN non configuré côté serveur")
        if not hmac.compare_digest(token or "", admin_token):
            raise HTTPException(401, "Jeton administrateur invalide")

    @app.get("/")
    def root():
        return {"project": "XAUUSD Lab", "mode": "PAPER", "live_orders_enabled": False, "stop": killswitch.status()}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/status")
    def status():
        return trader.status()

    @app.get("/api/signals")
    def signals(limit: int = 50):
        return trader.j.rows("signals", limit)

    @app.get("/api/trades")
    def trades(limit: int = 50):
        return trader.j.rows("trades", limit)

    @app.post("/webhook/tradingview")
    def webhook(alert: CandleAlert, x_webhook_secret: str | None = Header(default=None)):
        if not secret:
            raise HTTPException(503, "WEBHOOK_SECRET non configuré côté serveur")
        given = alert.secret or x_webhook_secret or ""
        if not hmac.compare_digest(given, secret):
            raise HTTPException(401, "Secret invalide")
        if alert.symbol.upper().replace(":", "").removeprefix("OANDA").removeprefix("FX") not in {"XAUUSD"}:
            raise HTTPException(400, "Seul XAUUSD est activé")
        from src.data.csv_adapter import _parse_time
        candle = {"ts": _parse_time({"time": alert.time}), "open": alert.open, "high": alert.high,
                  "low": alert.low, "close": alert.close, "volume": alert.volume}
        return trader.on_candle(candle)

    app.state.positions = {"at": None, "items": []}

    @app.post("/api/positions", include_in_schema=False)
    def report_positions(rep: PositionsReport, request: Request):
        """Positions ouvertes lues dans MT5 par le pont (lecture seule). Accepté uniquement depuis la machine locale."""
        if request.client is None or request.client.host not in ("127.0.0.1", "::1", "testclient"):
            raise HTTPException(403, "Réservé au pont MT5 local")
        from datetime import datetime, timezone
        from src.scan import levels
        items = []
        for p in rep.positions:
            side = "BUY" if p.type == 0 else "SELL"
            lv = levels(side, p.price_open, p.sl, p.tp or None) if p.sl else {"entry": p.price_open, "sl": None, "tp1": None, "tp2": p.tp or None}
            items.append({"ticket": p.ticket, "symbol": p.symbol, "side": side, "volume": p.volume,
                          "profit": p.profit, "price": p.price_current, **lv})
        app.state.positions = {"at": datetime.now(timezone.utc).isoformat(), "items": items}
        return {"ok": True, "count": len(items)}

    @app.get("/api/positions")
    def positions():
        return app.state.positions

    @app.get("/api/scan")
    def scan(symbol: str | None = None):
        from src.scan import build_scan
        rows = agents(symbol)
        tf_of = {a.name: a.timeframe for a in default_registry().all()}
        out = build_scan(rows, cfg.get("consensus", {}).get("weights", {}), tf_of)
        return {"setups": out, "validated": False,
                "note": "Configurations calculées, non validées par backtest : information seulement, aucun ordre."}

    @app.get("/api/kill")
    def kill_status():
        return killswitch.status()

    @app.post("/api/kill")
    def kill(req: KillRequest, x_admin_token: str | None = Header(default=None)):
        """Engager le STOP est toujours permis ; le relâcher exige le jeton administrateur."""
        if req.engaged:
            st = killswitch.engage(req.reason)
            book.close_all("STOP")
            return st
        require_admin(x_admin_token)
        return killswitch.release()

    @app.get("/api/market")
    def market(symbol: str | None = None):
        from src.agents.questdb import _tag
        sym = _tag(symbol or feed_symbol)
        try:
            rows = qdb().query(f"SELECT timestamp, bid, ask FROM ticks WHERE symbol = '{sym}' LATEST ON timestamp PARTITION BY symbol")
        except Exception as e:
            raise HTTPException(503, f"QuestDB indisponible : {e}")
        return {"symbol": sym, **(rows[0] if rows else {})}

    @app.get("/api/bars")
    def bars(symbol: str | None = None, tf: int = 300, limit: int = 120):
        try:
            return qdb().recent_bars(symbol or feed_symbol, f"{int(tf)}s", min(int(limit), 1000))
        except Exception as e:
            raise HTTPException(503, f"QuestDB indisponible : {e}")

    @app.get("/api/agents")
    def agents(symbol: str | None = None):
        """Dernier résultat de chacun des 6 agents (lu dans QuestDB)."""
        from src.agents.questdb import QuestDB, _tag
        try:
            return QuestDB(ilp="").query(
                f"SELECT * FROM signals WHERE symbol = '{_tag(symbol or feed_symbol)}' LATEST ON timestamp PARTITION BY agent")
        except Exception as e:
            raise HTTPException(503, f"QuestDB indisponible : {e}")

    @app.get("/api/consensus")
    def consensus(symbol: str | None = None):
        """Vote pondéré des agents sur la dernière bougie évaluée (poids dans config : consensus.weights)."""
        from src.engine.score import weighted_consensus
        rows = agents(symbol)
        if not rows:
            return {"direction": "NO_TRADE", "score": 0, "agents": 0}
        weights = cfg.get("consensus", {}).get("weights", {})
        rows = [r for r in rows if weights.get(r["agent"], 1.0) > 0]
        if not rows:
            return {"direction": "NO_TRADE", "score": 0, "agents": 0}
        last = max(r["timestamp"] for r in rows)
        mapping = {"BUY": "LONG", "SELL": "SHORT"}
        votes = [{"direction": mapping.get(r["action"], "NO_TRADE"), "weight": weights.get(r["agent"], 1.0)}
                 for r in rows if r["timestamp"] == last]
        return {"bar_ts": last, "agents": len(votes), **weighted_consensus(votes)}

    ui = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if ui.is_dir():
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
        app.mount("/ui", StaticFiles(directory=ui, html=True), name="ui")

        @app.get("/dashboard", include_in_schema=False)
        def dashboard():
            return RedirectResponse("/ui/")

    app.state.trader = trader
    return app


app = create_app() if os.getenv("XAUUSD_NO_AUTOAPP") != "1" else None
