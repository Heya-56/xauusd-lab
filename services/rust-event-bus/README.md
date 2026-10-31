# Hinova Rust Tick Event Bus — first vertical slice

This isolated transport prototype does not place orders and is not yet wired into Python strategy agents, SQL agents, or QuestDB.

## Start the Rust bus
```powershell
cd services/rust-event-bus
cargo test
cargo run
```
Default bind: `127.0.0.1:8787`. Do not bind publicly; authentication and TLS are not implemented.

- Health: `http://127.0.0.1:8787/health`
- Ingest: `ws://127.0.0.1:8787/ws/ingest`
- Consumers: `ws://127.0.0.1:8787/ws/ticks`

## Connect MT5 in read-only mode
Run this bridge on the Windows computer with the MT5 desktop terminal installed and logged in. It only reads quotes; it contains no order-placement calls.

1. Start the Rust bus on that same computer.
2. Open MT5 and log into the intended demo account. Confirm the broker's gold symbol in Market Watch (it may be `XAUUSD`, `XAUUSD.a`, `GOLD`, etc.).
3. In PowerShell, from this directory:
```powershell
py -m pip install -r requirements-mt5.txt
$env:MT5_SYMBOL = "XAUUSD"
$env:EVENT_BUS_WS_URL = "ws://127.0.0.1:8787/ws/ingest"
py mt5_bridge.py
```
Set `MT5_SYMBOL` to the exact broker symbol. The bridge rejects non-loopback WebSocket URLs. Press Ctrl+C to stop it.

A successful connection prints bid/ask updates and acknowledgements from the Rust bus. If no quotes appear, check MT5 login, Market Watch symbol, market hours, and the bus health endpoint.

### Limits and safety
- A bus acknowledgement proves that the local MT5 API supplied a quote and the bus accepted it; it does not prove production readiness.
- The symbol is deliberately labeled `broker_instrument_unverified`; symbol name alone does not establish spot/CFD/futures classification.
- This polling bridge forwards the latest observed quote; it is not a lossless tick recorder.
- No live orders, authentication, TLS, persistence, deduplication, or rate limiting.
- Python strategy agents, SQL agents, PostgreSQL, and QuestDB remain unconnected.
