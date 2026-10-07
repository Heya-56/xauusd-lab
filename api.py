from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from backtest import load_csv, run_backtest
from bot import crossover_signal, position_size

app = FastAPI(title="Test Création Bot", version="1.0.0")
DATA = Path(__file__).parent / "data" / "sample_xauusd.csv"

class SignalPayload(BaseModel):
    symbol: str = "XAUUSD"
    highs: list[float]
    lows: list[float]
    closes: list[float]

@app.get("/api/health")
def health():
    return {"status":"ok","mode":"paper","execution":False}

@app.get("/api/strategy")
def strategy():
    return {"symbol":"XAUUSD","signal":"EMA20/EMA50 crossover","stop":"0.5 ATR14","tp1":"1R / 50%","tp2":"2R / 50%","risk_per_trade":"0.25%","max_daily_loss":"0.50%","max_lot":0.01}

@app.get("/api/backtest")
def backtest():
    return run_backtest(load_csv(DATA))

@app.post("/api/signal")
def signal(payload: SignalPayload):
    if payload.symbol.upper() != "XAUUSD":
        raise HTTPException(status_code=400, detail="Prototype accepts XAUUSD only")
    result = crossover_signal(payload.closes, payload.highs, payload.lows)
    if result is None:
        return {"signal":None}
    return {"signal":result.__dict__,"educational_lot_size":position_size(10000,result.entry,result.stop),"execution":False}

@app.post("/webhook/tradingview")
def tradingview_webhook(payload: dict):
    return {"received":True,"mode":"paper","execution":False,"message":"Signal received. No broker order is sent."}
