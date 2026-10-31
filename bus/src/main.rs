//! XAUUSD Lab — bus d'événements.
//!
//! ws://HOST:9100/publish   : les sources (MT5, broker, replay) envoient des ticks JSON
//! ws://HOST:9100/subscribe : les agents reçoivent {"type":"tick",...} et {"type":"bar",...}
//! Chaque tick et chaque bougie clôturée sont aussi écrits dans QuestDB (ILP).
mod ilp;
mod model;

use futures_util::{SinkExt, StreamExt};
use model::{BarAggregator, Tick};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{broadcast, mpsc};
use tokio_tungstenite::tungstenite::{handshake::server::{Request, Response}, Message};

struct Bus {
    events: broadcast::Sender<String>,
    aggs: Mutex<Vec<BarAggregator>>,
    questdb: Option<mpsc::Sender<String>>,
    token: Option<String>,
}

impl Bus {
    fn ingest(&self, v: &Value) -> Result<(), String> {
        let t = Tick::from_json(v)?;
        let closed: Vec<_> = self.aggs.lock().unwrap().iter_mut().filter_map(|a| a.push(&t)).collect();
        let _ = self.events.send(json!({"type": "tick", "symbol": t.symbol, "ts_ms": t.ts_ms,
            "bid": t.bid, "ask": t.ask, "mid": t.mid(), "volume": t.volume}).to_string());
        if let Some(q) = &self.questdb {
            let _ = q.try_send(ilp::tick_line(&t));
        }
        for b in closed {
            let mut ev = serde_json::to_value(&b).unwrap();
            ev["type"] = json!("bar");
            let _ = self.events.send(ev.to_string());
            if let Some(q) = &self.questdb {
                let _ = q.try_send(ilp::bar_line(&b));
            }
            tracing::debug!("bougie clôturée {} {}", b.symbol, b.ts_ms);
        }
        Ok(())
    }
}

async fn handle(bus: Arc<Bus>, stream: TcpStream) {
    let mut path = String::new();
    let ws = tokio_tungstenite::accept_hdr_async(stream, |req: &Request, resp: Response| {
        path = req.uri().to_string();
        Ok(resp)
    }).await;
    let Ok(ws) = ws else { return };
    let (mut out, mut inp) = ws.split();
    let (route, query) = path.split_once('?').unwrap_or((path.as_str(), ""));

    match route {
        "/publish" => {
            if let Some(tok) = &bus.token {
                if !query.split('&').any(|kv| kv == format!("token={tok}")) {
                    let _ = out.send(Message::text(r#"{"error":"token invalide"}"#)).await;
                    return;
                }
            }
            while let Some(Ok(msg)) = inp.next().await {
                let Message::Text(txt) = msg else { continue };
                let parsed: Result<Value, _> = serde_json::from_str(&txt);
                let items = match parsed {
                    Ok(Value::Array(a)) => a,
                    Ok(v) => vec![v],
                    Err(e) => { let _ = out.send(Message::text(json!({"error": e.to_string()}).to_string())).await; continue; }
                };
                for v in &items {
                    if let Err(e) = bus.ingest(v) {
                        let _ = out.send(Message::text(json!({"error": e}).to_string())).await;
                    }
                }
            }
        }
        "/subscribe" => {
            let mut rx = bus.events.subscribe();
            loop {
                tokio::select! {
                    ev = rx.recv() => match ev {
                        Ok(s) => if out.send(Message::text(s)).await.is_err() { break },
                        Err(broadcast::error::RecvError::Lagged(n)) => {
                            let _ = out.send(Message::text(json!({"type":"lagged","dropped":n}).to_string())).await;
                        }
                        Err(_) => break,
                    },
                    m = inp.next() => if !matches!(m, Some(Ok(_))) { break },
                }
            }
        }
        _ => { let _ = out.send(Message::text(r#"{"error":"route inconnue : /publish ou /subscribe"}"#)).await; }
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt().with_env_filter(
        tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into())).init();
    let addr = std::env::var("BUS_ADDR").unwrap_or_else(|_| "0.0.0.0:9100".into());
    // Plusieurs unités de temps possibles : BAR_SECONDS=300,60 (M5 pour les agents de fond, M1 pour le scalping)
    let tfs: Vec<i64> = std::env::var("BAR_SECONDS").unwrap_or_else(|_| "300,60".into())
        .split(',').filter_map(|s| s.trim().parse().ok()).filter(|&n| n > 0).collect();
    let tf = tfs.iter().map(|t| t.to_string()).collect::<Vec<_>>().join("s, ");
    let questdb = std::env::var("QUESTDB_ILP").ok().filter(|s| !s.is_empty())
        .map(|a| ilp::spawn_writer(a, 500_000));
    let bus = Arc::new(Bus {
        events: broadcast::channel(16_384).0,
        aggs: Mutex::new(tfs.iter().map(|&t| BarAggregator::new(t)).collect()),
        questdb,
        token: std::env::var("BUS_TOKEN").ok().filter(|s| !s.is_empty()),
    });
    let listener = TcpListener::bind(&addr).await.expect("bind");
    tracing::info!("bus XAUUSD Lab sur ws://{addr} (bougies {tf}s, QuestDB {})",
        if bus.questdb.is_some() { "actif" } else { "désactivé" });
    loop {
        if let Ok((s, _)) = listener.accept().await {
            tokio::spawn(handle(bus.clone(), s));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::model::*;
    use super::ilp::*;
    use serde_json::json;

    fn t(ts: &str, px: f64) -> Tick {
        Tick::from_json(&json!({"symbol": "OANDA:XAUUSD", "ts": ts, "bid": px, "ask": px + 0.2})).unwrap()
    }

    #[test]
    fn parse_formats() {
        let a = Tick::from_json(&json!({"ts": "2026-01-05T10:00:00Z", "price": 2650.0})).unwrap();
        let b = Tick::from_json(&json!({"ts": 1767607200000i64, "price": 2650.0})).unwrap();
        let c = Tick::from_json(&json!({"ts": "2026-01-05T11:00:00+01:00", "price": 2650.0})).unwrap();
        assert_eq!(a.ts_ms, 1_767_607_200_000);
        assert_eq!(a.ts_ms, b.ts_ms);
        assert_eq!(a.ts_ms, c.ts_ms);
        assert_eq!(normalize_symbol("XAUUSDm"), "XAUUSD");
        assert!(Tick::from_json(&json!({"ts": 1, "bid": 2, "ask": 1})).is_err());
    }

    #[test]
    fn aggregates_bars() {
        let mut ag = BarAggregator::new(300);
        assert!(ag.push(&t("2026-01-05T10:00:01Z", 2650.0)).is_none());
        assert!(ag.push(&t("2026-01-05T10:02:00Z", 2655.0)).is_none());
        assert!(ag.push(&t("2026-01-05T10:04:59Z", 2648.0)).is_none());
        let bar = ag.push(&t("2026-01-05T10:05:00Z", 2651.0)).unwrap();
        assert_eq!((bar.open, bar.high, bar.low, bar.close, bar.ticks), (2650.1, 2655.1, 2648.1, 2648.1, 3));
        assert!((bar.spread - 0.2).abs() < 1e-9);
        assert_eq!(bar.symbol, "XAUUSD");
        assert!(ag.push(&t("2026-01-05T09:00:00Z", 1.0)).is_none()); // en retard
    }

    #[test]
    fn ilp_lines() {
        let l = tick_line(&t("2026-01-05T10:00:00Z", 2650.0));
        assert_eq!(l, "ticks,symbol=XAUUSD bid=2650,ask=2650.2,volume=0 1767607200000000000\n");
    }
}
