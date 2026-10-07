"""Register external reference strategies."""
CATALOG=[
 {"id":"external-ma20-ma50","source":"FahadJawed8/gold-xauusd-backtester","type":"trend_baseline","signal":"20/50 moving-average crossover"},
 {"id":"external-demarker-mean-reversion","source":"dns2jtm/xauusd-mean-reversion","type":"mean_reversion_reference","signal":"DeMarker extreme","grid_enabled":False},
]
if __name__=="__main__":
 import json; print(json.dumps(CATALOG,indent=2))
