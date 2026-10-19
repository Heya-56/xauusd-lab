use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::{
    env,
    net::SocketAddr,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};
use tokio::sync::broadcast;
use tower_http::trace::TraceLayer;

const CHANNEL_CAPACITY: usize = 16_384;

#[derive(Clone)]
struct AppState {
    ticks: broadcast::Sender<Tick>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Tick {
    schema_version: u16,
    event_id: String,
    source: String,
    symbol: String,
    instrument_type: String,
    timestamp_ms: i64,
    received_at_ms: i64,
    sequence: u64,
    bid: f64,
    ask: f64,
    #[serde(default)]
    venue: Option<String>,
}

#[derive(Serialize)]
struct Health {
    status: &'static str,
    service: &'static str,
    schema_version: u16,
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(i64::MAX as u128) as i64
}

fn validate(t: &Tick) -> Result<(), &'static str> {
    if t.schema_version != 1 {
        return Err("unsupported schema_version");
    }
    if t.event_id.trim().is_empty() || t.event_id.len() > 128 {
        return Err("invalid event_id");
    }
    if t.source.trim().is_empty() || t.source.len() > 64 {
        return Err("invalid source");
    }
    if t.symbol.trim().is_empty() || t.symbol.len() > 64 {
        return Err("invalid symbol");
    }
    if t.instrument_type.trim().is_empty() || t.instrument_type.len() > 32 {
        return Err("invalid instrument_type");
    }
    if t.timestamp_ms <= 0 || t.timestamp_ms > now_ms() + 60_000 {
        return Err("invalid timestamp_ms");
    }
    if !t.bid.is_finite() || !t.ask.is_finite() || t.bid <= 0.0 || t.ask <= 0.0 {
        return Err("invalid prices");
    }
    if t.bid > t.ask {
        return Err("bid exceeds ask");
    }
    Ok(())
}

async fn health() -> Json<Health> {
    Json(Health {
        status: "ok",
        service: "hinova-rust-event-bus",
        schema_version: 1,
    })
}

async fn ingest_ws(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| ingest(socket, state))
}

async fn ticks_ws(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| subscribe(socket, state))
}

async fn ingest(mut socket: WebSocket, state: Arc<AppState>) {
    while let Some(Ok(message)) = socket.recv().await {
        match message {
            Message::Text(text) => {
                let parsed = serde_json::from_str::<Tick>(&text);
                let result = match parsed {
                    Ok(mut tick) => {
                        tick.received_at_ms = now_ms();
                        match validate(&tick) {
                            Ok(()) => match state.ticks.send(tick.clone()) {
                                Ok(_) => {
                                    serde_json::json!({"ok": true, "event_id": tick.event_id})
                                }
                                Err(_) => {
                                    serde_json::json!({"ok": false, "error": "no subscribers"})
                                }
                            },
                            Err(e) => serde_json::json!({"ok": false, "error": e}),
                        }
                    }
                    Err(_) => {
                        serde_json::json!({"ok": false, "error": "invalid tick JSON/schema"})
                    }
                };
                if socket
                    .send(Message::Text(result.to_string()))
                    .await
                    .is_err()
                {
                    break;
                }
            }
            Message::Ping(bytes) => {
                if socket.send(Message::Pong(bytes)).await.is_err() {
                    break;
                }
            }
            Message::Close(_) => break,
            _ => {}
        }
    }
}

async fn subscribe(mut socket: WebSocket, state: Arc<AppState>) {
    let mut rx = state.ticks.subscribe();
    loop {
        tokio::select! {
            incoming = socket.recv() => match incoming {
                Some(Ok(Message::Ping(bytes))) => {
                    if socket.send(Message::Pong(bytes)).await.is_err() {
                        break;
                    }
                }
                Some(Ok(Message::Close(_))) | None | Some(Err(_)) => break,
                _ => {}
            },
            outgoing = rx.recv() => match outgoing {
                Ok(tick) => {
                    let Ok(json) = serde_json::to_string(&tick) else {
                        continue;
                    };
                    if socket.send(Message::Text(json)).await.is_err() {
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Lagged(skipped)) => {
                    let warning = serde_json::json!({
                        "type": "consumer.lagged",
                        "skipped": skipped
                    });
                    if socket.send(Message::Text(warning.to_string())).await.is_err() {
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(env::var("RUST_LOG").unwrap_or_else(|_| "info".into()))
        .init();

    // Local-only by default. Bind externally only after adding transport authentication.
    let bind = env::var("EVENT_BUS_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into());
    let addr: SocketAddr = bind.parse().expect("EVENT_BUS_BIND must be a socket address");
    let (ticks, _) = broadcast::channel(CHANNEL_CAPACITY);
    let state = Arc::new(AppState { ticks });
    let app = Router::new()
        .route("/health", get(health))
        .route("/ws/ingest", get(ingest_ws))
        .route("/ws/ticks", get(ticks_ws))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind event bus");
    tracing::info!(
        %addr,
        "event bus listening; live order execution is not implemented"
    );
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .expect("serve event bus");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tick() -> Tick {
        Tick {
            schema_version: 1,
            event_id: "test-1".into(),
            source: "fixture".into(),
            symbol: "XAUUSD".into(),
            instrument_type: "spot_or_cfd_unverified".into(),
            timestamp_ms: now_ms(),
            received_at_ms: 0,
            sequence: 1,
            bid: 2300.0,
            ask: 2300.2,
            venue: None,
        }
    }

    #[test]
    fn accepts_valid_tick_and_preserves_provenance() {
        let t = tick();
        assert!(validate(&t).is_ok());
        assert_eq!(t.source, "fixture");
        assert_eq!(t.instrument_type, "spot_or_cfd_unverified");
    }

    #[test]
    fn rejects_crossed_market() {
        let mut t = tick();
        t.bid = 2301.0;
        assert_eq!(validate(&t), Err("bid exceeds ask"));
    }

    #[test]
    fn rejects_unknown_schema_version() {
        let mut t = tick();
        t.schema_version = 2;
        assert_eq!(validate(&t), Err("unsupported schema_version"));
    }

    #[test]
    fn rejects_non_finite_prices() {
        let mut t = tick();
        t.ask = f64::NAN;
        assert_eq!(validate(&t), Err("invalid prices"));
    }
}
