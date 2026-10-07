"""IBKR Paper Gateway smoke test. No real order is submitted."""
import json
from src.data.ibkr_gateway import IBKRGatewayAdapter

def main():
    a = IBKRGatewayAdapter()
    try:
        print(json.dumps({"connection": a.connect()}, indent=2, default=str))
        print(json.dumps({"quote": a.quote()}, indent=2, default=str))
        bars = a.candles("XAUUSD", "5m")
        print(json.dumps({"bars": len(bars), "first": bars[:1], "last": bars[-1:]}, indent=2, default=str))
        print(json.dumps({"account": a.account_summary()}, indent=2, default=str))
        print(json.dumps({"what_if": a.what_if_market("BUY", 1)}, indent=2, default=str))
        print("IBKR PAPER GATEWAY CHECK: OK")
    finally:
        a.close()

if __name__ == "__main__":
    main()
