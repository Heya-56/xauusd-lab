"""API webhook (FastAPI) : TradingView → bougie clôturée → moteur papier → journal.

Sécurité : chaque requête doit contenir le secret WEBHOOK_SECRET (dans le JSON ou l'en-tête X-Webhook-Secret).
Le navigateur ne reçoit jamais d'identifiants broker et ne contient aucune logique d'exécution.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Header, HTTPException
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

    def qdb():
        from src.agents.questdb import QuestDB
        return QuestDB(ilp="")

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

    @app.get("/api/kill")
    def kill_status():
        return killswitch.status()

    @app.post("/api/kill")
    def kill(req: KillRequest, x_admin_token: str | None = Header(default=None)):
        """Engager le STOP est toujours permis ; le relâcher exige le jeton administrateur."""
        if req.engaged:
            return killswitch.engage(req.reason)
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
