from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bot import crossover_signal

app=FastAPI(title="Test Création Bot",version="0.1.0")

class TradingViewAlert(BaseModel):
    symbol:str="XAUUSD"; price:float; ema20:float; ema50:float
    prev_ema20:float; prev_ema50:float; atr14:float

@app.get("/")
def root():
    return {"project":"Test Création Bot","symbol":"XAUUSD","mode":"paper_signal_only"}

@app.post("/webhook/tradingview")
def tradingview_webhook(alert:TradingViewAlert):
    if alert.symbol.upper()!="XAUUSD":
        raise HTTPException(400,"Only XAUUSD is enabled.")
    s=crossover_signal(alert.price,alert.ema20,alert.ema50,alert.prev_ema20,alert.prev_ema50,alert.atr14)
    return {"project":"Test Création Bot","signal":s.__dict__,
            "risk":{"risk_per_trade_pct":0.25,"max_daily_loss_pct":0.50,"mode":"PAPER"}}
