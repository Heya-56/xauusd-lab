# Hinova Rust Tick Event Bus — first vertical slice

This service is an isolated, transport-level prototype. It does not place orders and is
not yet wired into the Python strategy engine, SQL agents, or QuestDB.

## Run locally

```bash
cd services/rust-event-bus
cargo test
cargo run
```

Default bind is `127.0.0.1:8787`. Do not bind to a public interface: the current prototype
does not authenticate WebSocket clients. Set `EVENT_BUS_BIND` only on a trusted local network
until authentication and TLS termination are implemented.

- Health: `GET http://127.0.0.1:8787/health`
- Source adapters publish: `ws://127.0.0.1:8787/ws/ingest`
- Strategy/data consumers subscribe: `ws://127.0.0.1:8787/ws/ticks`

## Tick schema v1

```json
{
  "schema_version": 1,
  "event_id": "source-unique-id",
  "source": "mt5|tradingview|ibkr|csv",
  "symbol": "XAUUSD",
  "instrument_type": "spot|cfd|future|unknown",
  "timestamp_ms": 1790000000000,
  "received_at_ms": 0,
  "sequence": 1,
  "bid": 2300.0,
  "ask": 2300.2,
  "venue": null
}
```

The server overwrites `received_at_ms`, validates schema, timestamp, prices and spread
ordering, then broadcasts accepted ticks. Instrument type and source are mandatory to
prevent silently conflating COMEX futures with spot/CFD quotes. Adapters must use the
actual source/instrument labels, not the example labels blindly.

## Known limitations — intentionally explicit

- In-memory broadcast only: no durable replay, delivery guarantee, or cross-process recovery.
- Slow consumers receive a lag warning; they must reconnect/recover from a durable log when added.
- No authentication, authorization, TLS, persistence, deduplication, or rate limiting yet.
- The WebSocket endpoint accepts already-normalized ticks; vendor-specific adapters are separate.
- This is a new crate and is not wired into the existing Python `src/core/event_bus.py`.
- No production deployment or live execution is part of this change.
