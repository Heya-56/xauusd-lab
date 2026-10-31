//! Écriture vers QuestDB via InfluxDB Line Protocol (TCP 9009). Tampon borné, reconnexion automatique.
use crate::model::{Bar, Tick};
use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;
use tokio::sync::mpsc;
use std::time::Duration;

fn esc_tag(s: &str) -> String {
    s.replace(['\\', ',', '=', ' '], "_")
}

pub fn tick_line(t: &Tick) -> String {
    format!("ticks,symbol={} bid={},ask={},volume={} {}\n",
        esc_tag(&t.symbol), t.bid, t.ask, t.volume, t.ts_ms * 1_000_000)
}

pub fn bar_line(b: &Bar) -> String {
    format!("bars,symbol={},tf={}s open={},high={},low={},close={},volume={},ticks={}i,spread={} {}\n",
        esc_tag(&b.symbol), b.tf_s, b.open, b.high, b.low, b.close, b.volume, b.ticks, b.spread, b.ts_ms * 1_000_000)
}

/// Lance la tâche d'écriture ; renvoie l'émetteur. Si QuestDB est indisponible, les lignes
/// sont conservées jusqu'à `max_buffer`, puis les plus anciennes sont abandonnées.
pub fn spawn_writer(addr: String, max_buffer: usize) -> mpsc::Sender<String> {
    let (tx, mut rx) = mpsc::channel::<String>(65_536);
    tokio::spawn(async move {
        let mut pending: std::collections::VecDeque<String> = Default::default();
        let mut conn: Option<TcpStream> = None;
        let mut tick = tokio::time::interval(Duration::from_millis(250));
        loop {
            tokio::select! {
                msg = rx.recv() => match msg {
                    Some(l) => {
                        pending.push_back(l);
                        if pending.len() > max_buffer { pending.pop_front(); }
                        if pending.len() < 1000 { continue; }
                    }
                    None => break,
                },
                _ = tick.tick() => {}
            }
            if pending.is_empty() { continue; }
            if conn.is_none() {
                match TcpStream::connect(&addr).await {
                    Ok(s) => { tracing::info!("QuestDB ILP connecté sur {addr}"); conn = Some(s); }
                    Err(e) => { tracing::warn!("QuestDB ILP indisponible ({e}) ; {} lignes en attente", pending.len()); continue; }
                }
            }
            let payload: String = pending.iter().map(String::as_str).collect();
            if let Err(e) = conn.as_mut().unwrap().write_all(payload.as_bytes()).await {
                tracing::warn!("écriture ILP échouée : {e}");
                conn = None;
            } else {
                pending.clear();
            }
        }
    });
    tx
}
