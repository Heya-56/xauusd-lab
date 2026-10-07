import json
import os
import requests

BASE = os.getenv("IBKR_BASE_URL", "https://localhost:5000/v1/api").rstrip("/")
TOKEN = os.getenv("IBKR_TOKEN")
CONID = os.getenv("IBKR_CONID")
VERIFY = os.getenv("IBKR_VERIFY_TLS", "false").lower() == "true"

s = requests.Session()
if TOKEN:
    s.headers.update({"Authorization": f"Bearer {TOKEN}"})

def get(path, params=None):
    r = s.get(f"{BASE}{path}", params=params, timeout=20, verify=VERIFY)
    r.raise_for_status()
    return r.json()

print("IBKR_BASE_URL:", BASE)
print("IBKR_CONID:", CONID or "MISSING")

status = get("/iserver/auth/status")
print(json.dumps({"auth": status}, indent=2))
if not status.get("authenticated"):
    raise SystemExit("IBKR brokerage session is not authenticated")

accounts = get("/iserver/accounts")
print(json.dumps({"accounts": accounts}, indent=2))

if not CONID:
    raise SystemExit("Set IBKR_CONID to the verified XAUUSD spot contract ConId before trading")

info = get(f"/iserver/contract/{CONID}/info")
rules = get("/iserver/contract/rules", params={"conid": CONID, "isBuy": "true"})
print(json.dumps({"contract": info, "rules": rules}, indent=2))

if info.get("symbol") != "XAUUSD":
    raise SystemExit(f"Refusing to trade: supplied ConId resolves to {info.get('symbol')!r}, not XAUUSD")

print("IBKR XAUUSD contract verification: OK")
