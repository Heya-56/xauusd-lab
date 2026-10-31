//! Modèle d'événements du bus : ticks entrants, bougies agrégées.
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Tick {
    pub symbol: String,
    /// Horodatage en millisecondes epoch UTC.
    pub ts_ms: i64,
    pub bid: f64,
    pub ask: f64,
    pub volume: f64,
}

impl Tick {
    pub fn mid(&self) -> f64 {
        (self.bid + self.ask) / 2.0
    }

    /// Accepte {symbol, ts|time (ms epoch, s epoch ou ISO-8601), bid/ask ou price, volume?}.
    pub fn from_json(v: &Value) -> Result<Tick, String> {
        let symbol = v.get("symbol").and_then(Value::as_str).unwrap_or("XAUUSD");
        let symbol = normalize_symbol(symbol);
        let ts = v.get("ts").or_else(|| v.get("time")).ok_or("champ ts manquant")?;
        let ts_ms = parse_ts(ts)?;
        let num = |k: &str| v.get(k).and_then(Value::as_f64);
        let (bid, ask) = match (num("bid"), num("ask"), num("price")) {
            (Some(b), Some(a), _) => (b, a),
            (_, _, Some(p)) => (p, p),
            _ => return Err("bid/ask ou price requis".into()),
        };
        if !(bid.is_finite() && ask.is_finite()) || bid <= 0.0 || ask < bid {
            return Err(format!("prix invalides bid={bid} ask={ask}"));
        }
        Ok(Tick { symbol, ts_ms, bid, ask, volume: num("volume").unwrap_or(0.0) })
    }
}

pub fn normalize_symbol(s: &str) -> String {
    let s = s.rsplit(':').next().unwrap_or(s).to_uppercase().replace(['/', '.'], "");
    s.trim_end_matches("M").to_string() // XAUUSDm (comptes micro) → XAUUSD
}

fn parse_ts(v: &Value) -> Result<i64, String> {
    if let Some(n) = v.as_i64() {
        return Ok(if n > 100_000_000_000 { n } else { n * 1000 });
    }
    if let Some(f) = v.as_f64() {
        return Ok(if f > 1e11 { f as i64 } else { (f * 1000.0) as i64 });
    }
    let s = v.as_str().ok_or("ts illisible")?;
    parse_iso(s).ok_or_else(|| format!("date ISO invalide: {s}"))
}

/// Parseur ISO-8601 minimal : YYYY-MM-DDTHH:MM[:SS[.fff]][Z|±HH:MM]
fn parse_iso(s: &str) -> Option<i64> {
    let b = s.as_bytes();
    if b.len() < 16 {
        return None;
    }
    let n = |r: std::ops::Range<usize>| s.get(r)?.parse::<i64>().ok();
    let (y, mo, d, h, mi) = (n(0..4)?, n(5..7)?, n(8..10)?, n(11..13)?, n(14..16)?);
    let mut idx = 16;
    let mut sec = 0.0;
    if b.get(16) == Some(&b':') {
        let end = s[17..].find(|c: char| !(c.is_ascii_digit() || c == '.')).map(|e| e + 17).unwrap_or(s.len());
        sec = s[17..end].parse::<f64>().ok()?;
        idx = end;
    }
    let tz = &s[idx..];
    let off_min = if tz.is_empty() || tz == "Z" {
        0
    } else {
        let sign = if tz.starts_with('-') { -1 } else { 1 };
        sign * (tz.get(1..3)?.parse::<i64>().ok()? * 60 + tz.get(4..6)?.parse::<i64>().ok()?)
    };
    // jours depuis epoch (algorithme de Howard Hinnant)
    let (y2, m2) = if mo <= 2 { (y - 1, mo + 9) } else { (y, mo - 3) };
    let era = y2.div_euclid(400);
    let yoe = y2 - era * 400;
    let doy = (153 * m2 + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    let secs = days * 86_400 + h * 3600 + mi * 60 - off_min * 60;
    Some(secs * 1000 + (sec * 1000.0).round() as i64)
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Bar {
    pub symbol: String,
    pub tf_s: i64,
    pub ts_ms: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub ticks: u64,
    /// Spread moyen (ask - bid) sur la bougie, utile pour filtrer le scalping.
    pub spread: f64,
}

/// Agrège les ticks en bougies (prix médian) ; renvoie la bougie précédente lorsqu'elle se clôture.
pub struct BarAggregator {
    pub tf_ms: i64,
    current: std::collections::HashMap<String, Bar>,
}

impl BarAggregator {
    pub fn new(tf_s: i64) -> Self {
        Self { tf_ms: tf_s * 1000, current: Default::default() }
    }

    pub fn push(&mut self, t: &Tick) -> Option<Bar> {
        let bucket = t.ts_ms.div_euclid(self.tf_ms) * self.tf_ms;
        let px = t.mid();
        let fresh = || Bar {
            symbol: t.symbol.clone(), tf_s: self.tf_ms / 1000, ts_ms: bucket,
            open: px, high: px, low: px, close: px, volume: t.volume, ticks: 1, spread: t.ask - t.bid,
        };
        match self.current.get_mut(&t.symbol) {
            Some(b) if b.ts_ms == bucket => {
                b.high = b.high.max(px);
                b.low = b.low.min(px);
                b.close = px;
                b.volume += t.volume;
                b.spread += (t.ask - t.bid - b.spread) / (b.ticks as f64 + 1.0);
                b.ticks += 1;
                None
            }
            Some(b) if bucket < b.ts_ms => None, // tick en retard : ignoré
            _ => self.current.insert(t.symbol.clone(), fresh()),
        }
    }
}
