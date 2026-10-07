import csv, json, math, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

TAHITI=timezone(timedelta(hours=-10))

def yahoo(symbol="GC=F", range_="2y", interval="1h"):
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?range={range_}&interval={interval}&events=history"
    req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=45) as r: p=json.loads(r.read().decode())
    z=p["chart"]["result"][0]; q=z["indicators"]["quote"][0]
    out=[]
    for i,t in enumerate(z["timestamp"]):
        if q["close"][i] is None: continue
        out.append({"utc":datetime.fromtimestamp(t,tz=timezone.utc),"local":datetime.fromtimestamp(t,tz=timezone.utc).astimezone(TAHITI),
                    "open":float(q["open"][i]),"high":float(q["high"][i]),"low":float(q["low"][i]),"close":float(q["close"][i])})
    return out

def ema(a,n):
    k=2/(n+1); o=[]; p=None
    for x in a: p=x if p is None else k*x+(1-k)*p; o.append(p)
    return o
def rsi(a,n=14):
    o=[None]*len(a); gains=[]; losses=[]
    for i in range(1,len(a)):
        d=a[i]-a[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
        if i>=n:
            g=sum(gains[-n:])/n; l=sum(losses[-n:])/n
            o[i]=100 if l==0 else 100-100/(1+g/l)
    return o
def atr(rows,n=14):
    tr=[]
    for i,r in enumerate(rows):
        if i==0: tr.append(r["high"]-r["low"])
        else: tr.append(max(r["high"]-r["low"],abs(r["high"]-rows[i-1]["close"]),abs(r["low"]-rows[i-1]["close"])))
    o=[None]*len(rows)
    for i in range(n-1,len(rows)): o[i]=sum(tr[i-n+1:i+1])/n
    return o

def run(rows,name,signal_fn):
    trades=[]
    last_day=None
    for i in range(60,len(rows)-13):
        r=rows[i]; d=r["local"]
        if d.weekday() not in (0,2,4) or d.hour!=14: continue
        if last_day==d.date(): continue
        sig=signal_fn(i)
        if not sig: continue
        entry=r["close"]; a=ATR[i] or 0
        if a<=0: continue
        sl=entry-(1.2*a if sig=="LONG" else -1.2*a)
        tp=entry+(1.8*a if sig=="LONG" else -1.8*a)
        exitp=rows[i+12]["close"]; outcome="TIME"
        for j in range(i+1,i+13):
            b=rows[j]
            hit_sl=b["low"]<=sl if sig=="LONG" else b["high"]>=sl
            hit_tp=b["high"]>=tp if sig=="LONG" else b["low"]<=tp
            if hit_sl and hit_tp: outcome,exitp="SL",sl; break
            if hit_sl: outcome,exitp="SL",sl; break
            if hit_tp: outcome,exitp="TP",tp; break
        pnl=exitp-entry if sig=="LONG" else entry-exitp
        trades.append({"date":str(d.date()),"direction":sig,"entry":round(entry,2),"exit":round(exitp,2),"pnl":round(pnl,2),"outcome":outcome})
        last_day=d.date()
    wins=sum(t["pnl"]>0 for t in trades); losses=sum(t["pnl"]<0 for t in trades)
    gw=sum(t["pnl"] for t in trades if t["pnl"]>0); gl=-sum(t["pnl"] for t in trades if t["pnl"]<0)
    return {"candidate":name,"trades":len(trades),"wins":wins,"losses":losses,
            "win_rate_pct":round(100*wins/len(trades),1) if trades else 0,
            "net":round(sum(t["pnl"] for t in trades),2),
            "profit_factor":round(gw/gl,2) if gl else None,
            "trades_detail":trades}

rows=yahoo(); closes=[r["close"] for r in rows]; E20=ema(closes,20); E50=ema(closes,50); E200=ema(closes,200); R=rsi(closes); ATR=atr(rows)

def macd(i):
    fast=ema(closes,12); slow=ema(closes,26); m=[a-b for a,b in zip(fast,slow)]; s=ema(m,9)
    return "LONG" if m[i]>s[i] and m[i-1]<=s[i-1] else ("SHORT" if m[i]<s[i] and m[i-1]>=s[i-1] else None)
def trend_pullback(i):
    if E50[i]>E200[i] and closes[i]<=E20[i]*1.002 and R[i] is not None and R[i]<55: return "LONG"
    if E50[i]<E200[i] and closes[i]>=E20[i]*0.998 and R[i] is not None and R[i]>45: return "SHORT"
def donchian(i):
    hi=max(x["high"] for x in rows[i-24:i]); lo=min(x["low"] for x in rows[i-24:i])
    if closes[i]>hi and E50[i]>E200[i]: return "LONG"
    if closes[i]<lo and E50[i]<E200[i]: return "SHORT"
def meanrev(i):
    if R[i] is None: return None
    if R[i]<30 and closes[i]<E20[i]: return "LONG"
    if R[i]>70 and closes[i]>E20[i]: return "SHORT"
def breakout(i):
    hi=max(x["high"] for x in rows[i-12:i]); lo=min(x["low"] for x in rows[i-12:i])
    if closes[i]>hi and E20[i]>E50[i]: return "LONG"
    if closes[i]<lo and E20[i]<E50[i]: return "SHORT"

results=[run(rows,"MACD cross (3aLaee core)",macd),run(rows,"EMA20/50/200 trend pullback (omidram-style)",trend_pullback),
         run(rows,"Donchian breakout + EMA trend (classic/open-source family)",donchian),
         run(rows,"RSI mean reversion (gold bot family)",meanrev),run(rows,"12-bar breakout + EMA filter",breakout)]
summary=[{k:v for k,v in x.items() if k!="trades_detail"} for x in results]
summary.sort(key=lambda x: (x["profit_factor"] or -999, x["net"]),reverse=True)
print(json.dumps({"data":"GC=F 2y 1h proxy, not spot XAUUSD","protocol":"14:00 Pacific/Tahiti Mon/Wed/Fri, max 1 trade/day, 12h horizon, ATR 1.2 SL / 1.8 TP","ranking":summary},indent=2))
with open("competition.json","w") as f: json.dump({"summary":summary,"results":results},f,indent=2)
with open("competition.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=summary[0].keys()); w.writeheader(); w.writerows(summary)
