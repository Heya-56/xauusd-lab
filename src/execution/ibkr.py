import os
import requests
from dataclasses import dataclass


@dataclass
class OrderResult:
    status: str
    payload: dict


class IBKRExecution:
    """Guarded IBKR execution client.

    PAPER is the default. LIVE requires XAUUSD_LIVE_ORDERS=true explicitly.
    The client always supports a what-if preview before submission.
    """

    def __init__(self):
        self.base_url = os.getenv("IBKR_BASE_URL", "https://localhost:5000/v1/api").rstrip("/")
        self.account_id = os.getenv("IBKR_ACCOUNT_ID")
        self.token = os.getenv("IBKR_TOKEN")
        self.conid = int(os.environ["IBKR_CONID"])
        self.verify_tls = os.getenv("IBKR_VERIFY_TLS", "false").lower() == "true"
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _request(self, method, path, **kwargs):
        r = self.session.request(method, f"{self.base_url}{path}", timeout=30, verify=self.verify_tls, **kwargs)
        r.raise_for_status()
        return r.json()

    def accounts(self):
        return self._request("GET", "/iserver/accounts")

    def contract_rules(self, is_buy=True):
        return self._request("GET", f"/iserver/contract/rules?conid={self.conid}&isBuy={'true' if is_buy else 'false'}")

    def what_if(self, side, quantity, order_type="MKT", price=None):
        if not self.account_id:
            raise ValueError("IBKR_ACCOUNT_ID is required for order preview")
        order = {
            "conid": self.conid,
            "orderType": order_type,
            "side": side.upper(),
            "tif": "DAY",
            "quantity": float(quantity),
        }
        if price is not None:
            order["price"] = float(price)
        return self._request("POST", f"/iserver/account/{self.account_id}/orders/whatif", json={"orders": [order]})

    def place(self, side, quantity, order_type="MKT", price=None, client_order_id=None):
        if os.getenv("XAUUSD_LIVE_ORDERS", "false").lower() != "true":
            return OrderResult("BLOCKED", {"reason": "XAUUSD_LIVE_ORDERS is not true; no live order submitted"})
        if not self.account_id:
            raise ValueError("IBKR_ACCOUNT_ID is required for live orders")

        # Mandatory safety gate: preview immediately before submission.
        preview = self.what_if(side, quantity, order_type, price)
        if isinstance(preview, dict) and preview.get("error"):
            return OrderResult("REJECTED_BY_WHATIF", preview)

        order = {
            "conid": self.conid,
            "orderType": order_type,
            "side": side.upper(),
            "tif": "DAY",
            "quantity": float(quantity),
        }
        if price is not None:
            order["price"] = float(price)
        if client_order_id:
            order["cOID"] = client_order_id[:64]

        payload = self._request("POST", f"/iserver/account/{self.account_id}/orders", json={"orders": [order]})
        return OrderResult("SUBMITTED", {"preview": preview, "order": payload})
