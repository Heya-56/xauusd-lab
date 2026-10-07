"""Simple bar-by-bar backtest for the educational XAUUSD strategy."""
import csv
from dataclasses import dataclass

from bot import atr, ema

@dataclass
class Trade:
    side: str
    entry: float
    exit: float
    pnl: float
    reason: str

def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def run_backtest(rows, starting_capital=10000.0, risk_fraction=0.0025,
                 max_daily_loss_fraction=0.005, max_lot=0.01, contract_size=100.0):
    closes=[float(r["close"]) for r in rows]
    highs=[float(r["high"]) for r in rows]
    lows=[float(r["low"]) for r in rows]
    fast, slow, atr14=ema(closes,20), ema(closes,50), atr(highs,lows,closes,14)
    capital=starting_capital
    trades=[]
    open_trade=None
    day_start=capital
    current_day=None

    for i,row in enumerate(rows):
        day=row["timestamp"][:10]
        if day != current_day:
            current_day=day
            day_start=capital
        if capital <= day_start*(1-max_daily_loss_fraction):
            continue

        if open_trade is None and i>50 and all(x is not None for x in (fast[i],fast[i-1],slow[i],slow[i-1],atr14[i])):
            long_cross=fast[i-1] <= slow[i-1] and fast[i] > slow[i]
            short_cross=fast[i-1] >= slow[i-1] and fast[i] < slow[i]
            if long_cross or short_cross:
                entry=closes[i]
                distance=atr14[i]*0.5
                risk_cash=capital*risk_fraction
                lots=min(max_lot,risk_cash/(distance*contract_size)) if distance else 0
                if lots:
                    side="LONG" if long_cross else "SHORT"
                    open_trade={"side":side,"entry":entry,"stop":entry-distance if side=="LONG" else entry+distance,
                                "tp1":entry+distance if side=="LONG" else entry-distance,
                                "tp2":entry+2*distance if side=="LONG" else entry-2*distance,
                                "lots":lots,"tp1_done":False}

        if open_trade:
            h,l=float(row["high"]),float(row["low"])
            side=open_trade["side"]; lots=open_trade["lots"]; entry=open_trade["entry"]
            stop, tp1, tp2=open_trade["stop"],open_trade["tp1"],open_trade["tp2"]
            stop_hit=l<=stop if side=="LONG" else h>=stop
            tp1_hit=h>=tp1 if side=="LONG" else l<=tp1
            tp2_hit=h>=tp2 if side=="LONG" else l<=tp2
            sign=1 if side=="LONG" else -1
            if stop_hit:
                pnl=(stop-entry)*contract_size*lots*sign
                trades.append(Trade(side,entry,stop,pnl,"STOP")); capital+=pnl; open_trade=None
            elif tp2_hit:
                pnl=(tp2-entry)*contract_size*lots*sign
                if open_trade["tp1_done"]: pnl*=1
                else: pnl*=1
                trades.append(Trade(side,entry,tp2,pnl,"TP2")); capital+=pnl; open_trade=None
            elif tp1_hit and not open_trade["tp1_done"]:
                pnl=(tp1-entry)*contract_size*lots*0.5*sign
                trades.append(Trade(side,entry,tp1,pnl,"TP1")); capital+=pnl; open_trade["tp1_done"]=True

    wins=sum(t.pnl>0 for t in trades); losses=sum(t.pnl<0 for t in trades)
    gp=sum(t.pnl for t in trades if t.pnl>0); gl=abs(sum(t.pnl for t in trades if t.pnl<0))
    return {"starting_capital":starting_capital,"ending_capital":round(capital,2),
            "net_pnl":round(capital-starting_capital,2),"trades":len(trades),
            "wins":wins,"losses":losses,
            "win_rate":round(wins/len(trades)*100,2) if trades else 0,
            "profit_factor":round(gp/gl,3) if gl else None,
            "history":[t.__dict__ for t in trades]}

if __name__=="__main__":
    print(run_backtest(load_csv("data/sample_xauusd.csv")))
