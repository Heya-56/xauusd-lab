"""External deterministic strategy candidates for the XAUUSD Lab."""
from __future__ import annotations
from typing import Sequence

def ema(values: Sequence[float], n: int) -> list[float]:
    if not values: return []
    k=2/(n+1); out=[]; prev=None
    for x in values:
        prev=float(x) if prev is None else k*float(x)+(1-k)*prev
        out.append(prev)
    return out

def demarker(high, low, n=14):
    out=[None]*len(high); up=[]; down=[]
    for i in range(1,len(high)):
        up.append(max(float(high[i])-float(high[i-1]),0.0))
        down.append(max(float(low[i-1])-float(low[i]),0.0))
        if len(up)>=n:
            u=sum(up[-n:])/n; d=sum(down[-n:])/n
            out[i]=1.0 if u+d==0 else u/(u+d)
    return out

def ma20_ma50_signal(closes):
    if len(closes)<51: return None
    e20,e50=ema(closes,20),ema(closes,50); i=len(closes)-1; p=i-1
    if e20[p] <= e50[p] and e20[i] > e50[i]: return "LONG"
    if e20[p] >= e50[p] and e20[i] < e50[i]: return "SHORT"
    return None

def demarker_mean_reversion_signal(highs,lows,closes,period=14,low_threshold=.30,high_threshold=.70):
    if len(closes)<period+2: return None
    dm=demarker(highs,lows,period); i=len(closes)-1
    if dm[i] is None: return None
    if dm[i]<low_threshold: return "LONG"
    if dm[i]>high_threshold: return "SHORT"
    return None
