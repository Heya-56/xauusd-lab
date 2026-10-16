export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

type LayerId = "ema" | "rsi" | "macd" | "fibonacci" | "atr";

interface TradeContext {
  id?: string;
  entryTime?: number;
  exitTime?: number;
  side?: "long" | "short";
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
}

interface AnalyzeRequest {
  symbol: string;
  timeframe: string;
  candles: Candle[];
  layers?: Partial<Record<LayerId, boolean>>;
  trade?: TradeContext;
  settings?: {
    emaFast?: number;
    emaSlow?: number;
    rsiPeriod?: number;
    rsiOversold?: number;
    rsiOverbought?: number;
    macdFast?: number;
    macdSlow?: number;
    macdSignal?: number;
    atrPeriod?: number;
    fibonacciLookback?: number;
  };
}

interface LayerResult {
  id: LayerId;
  enabled: boolean;
  values?: Record<string, Array<number | null>>;
  levels?: Record<string, number>;
  events: Array<{ time: number; type: string; value?: number; label: string }>;
  status: string;
}

const DEFAULT_LAYERS: Record<LayerId, boolean> = {
  ema: true, rsi: true, macd: true, fibonacci: true, atr: true,
};

const json = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders(), "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function validateCandles(input: unknown): input is Candle[] {
  if (!Array.isArray(input) || input.length < 3 || input.length > 2000) return false;
  let previous = -Infinity;
  for (const c of input) {
    if (!c || !isFiniteNumber(c.time) || c.time <= previous) return false;
    if (![c.open, c.high, c.low, c.close].every(isFiniteNumber)) return false;
    if (c.high < Math.max(c.open, c.close, c.low) || c.low > Math.min(c.open, c.close, c.high)) return false;
    if (c.volume !== undefined && (!isFiniteNumber(c.volume) || c.volume < 0)) return false;
    previous = c.time;
  }
  return true;
}

function ema(input: number[], period: number): Array<number | null> {
  const out: Array<number | null> = Array(input.length).fill(null);
  if (period < 1 || input.length < period) return out;
  const alpha = 2 / (period + 1);
  let value = input.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = value;
  for (let i = period; i < input.length; i++) {
    value = input[i] * alpha + value * (1 - alpha);
    out[i] = value;
  }
  return out;
}

function rsi(input: number[], period: number): Array<number | null> {
  const out: Array<number | null> = Array(input.length).fill(null);
  if (period < 1 || input.length <= period) return out;
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const delta = input[i] - input[i - 1];
    gains += Math.max(delta, 0);
    losses += Math.max(-delta, 0);
  }
  let avgGain = gains / period, avgLoss = losses / period;
  const calc = () => avgLoss === 0 ? (avgGain === 0 ? 50 : 100) : 100 - 100 / (1 + avgGain / avgLoss);
  out[period] = calc();
  for (let i = period + 1; i < input.length; i++) {
    const delta = input[i] - input[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(delta, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-delta, 0)) / period;
    out[i] = calc();
  }
  return out;
}

function atr(candles: Candle[], period: number): Array<number | null> {
  const tr = candles.map((c, i) => i === 0 ? c.high - c.low :
    Math.max(c.high - c.low, Math.abs(c.high - candles[i - 1].close), Math.abs(c.low - candles[i - 1].close)));
  const out: Array<number | null> = Array(candles.length).fill(null);
  if (period < 1 || candles.length < period) return out;
  let value = tr.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = value;
  for (let i = period; i < tr.length; i++) {
    value = (value * (period - 1) + tr[i]) / period;
    out[i] = value;
  }
  return out;
}

function crossEvents(
  times: number[], a: Array<number | null>, b: Array<number | null>, label: string,
): LayerResult["events"] {
  const events: LayerResult["events"] = [];
  for (let i = 1; i < times.length; i++) {
    if (a[i - 1] === null || b[i - 1] === null || a[i] === null || b[i] === null) continue;
    if (a[i - 1]! <= b[i - 1]! && a[i]! > b[i]!) events.push({ time: times[i], type: "bullish-cross", label: label + " bullish cross" });
    if (a[i - 1]! >= b[i - 1]! && a[i]! < b[i]!) events.push({ time: times[i], type: "bearish-cross", label: label + " bearish cross" });
  }
  return events;
}

function analyze(body: AnalyzeRequest) {
  const candles = body.candles;
  const times = candles.map(c => c.time);
  const closes = candles.map(c => c.close);
  const settings = body.settings ?? {};
  const layers = { ...DEFAULT_LAYERS, ...(body.layers ?? {}) };
  const fastPeriod = settings.emaFast ?? 20;
  const slowPeriod = settings.emaSlow ?? 50;
  const rsiPeriod = settings.rsiPeriod ?? 14;
  const rsiOversold = settings.rsiOversold ?? 30;
  const rsiOverbought = settings.rsiOverbought ?? 70;
  const macdFast = settings.macdFast ?? 12;
  const macdSlow = settings.macdSlow ?? 26;
  const macdSignalPeriod = settings.macdSignal ?? 9;
  const atrPeriod = settings.atrPeriod ?? 14;
  const fibLookback = settings.fibonacciLookback ?? 100;

  const results: LayerResult[] = [];
  const fastEma = ema(closes, fastPeriod);
  const slowEma = ema(closes, slowPeriod);
  const rsiValues = rsi(closes, rsiPeriod);
  const macdFastValues = ema(closes, macdFast);
  const macdSlowValues = ema(closes, macdSlow);
  const macdLine = closes.map((_, i) => macdFastValues[i] === null || macdSlowValues[i] === null
    ? null : macdFastValues[i]! - macdSlowValues[i]!);
  const macdValid = macdLine.map((v, i) => v === null ? 0 : v);
  const macdStart = macdLine.findIndex(v => v !== null);
  const signalInput = macdStart < 0 ? [] : macdValid.slice(macdStart);
  const signalPartial = ema(signalInput, macdSignalPeriod);
  const signalLine: Array<number | null> = Array(candles.length).fill(null);
  signalPartial.forEach((v, i) => { signalLine[macdStart + i] = v; });
  const histogram = macdLine.map((v, i) => v === null || signalLine[i] === null ? null : v - signalLine[i]!);
  const atrValues = atr(candles, atrPeriod);

  if (layers.ema) results.push({
    id: "ema", enabled: true, values: { fast: fastEma, slow: slowEma },
    events: crossEvents(times, fastEma, slowEma, "EMA"), status: "calculated",
  });
  if (layers.rsi) {
    const events: LayerResult["events"] = [];
    for (let i = 1; i < rsiValues.length; i++) {
      if (rsiValues[i - 1] === null || rsiValues[i] === null) continue;
      if (rsiValues[i - 1]! >= rsiOversold && rsiValues[i]! < rsiOversold) events.push({ time: times[i], type: "oversold", value: rsiValues[i]!, label: "RSI entered oversold zone" });
      if (rsiValues[i - 1]! <= rsiOverbought && rsiValues[i]! > rsiOverbought) events.push({ time: times[i], type: "overbought", value: rsiValues[i]!, label: "RSI entered overbought zone" });
    }
    results.push({ id: "rsi", enabled: true, values: { rsi: rsiValues }, levels: { oversold: rsiOversold, overbought: rsiOverbought }, events, status: "calculated" });
  }
  if (layers.macd) results.push({
    id: "macd", enabled: true, values: { macd: macdLine, signal: signalLine, histogram },
    events: crossEvents(times, macdLine, signalLine, "MACD"), status: "calculated",
  });
  if (layers.fibonacci) {
    const window = candles.slice(-Math.max(2, Math.min(fibLookback, candles.length)));
    const high = Math.max(...window.map(c => c.high));
    const low = Math.min(...window.map(c => c.low));
    const range = high - low;
    results.push({
      id: "fibonacci", enabled: true,
      levels: { low, "23.6%": low + range * 0.236, "38.2%": low + range * 0.382, "50%": low + range * 0.5, "61.8%": low + range * 0.618, "78.6%": low + range * 0.786, high },
      events: [], status: "calculated",
    });
  }
  if (layers.atr) results.push({ id: "atr", enabled: true, values: { atr: atrValues }, events: [], status: "calculated" });

  let tradeContext: Record<string, unknown> | null = null;
  if (body.trade) {
    const t = body.trade;
    const entryIndex = t.entryTime === undefined ? -1 : times.findIndex(v => v >= t.entryTime!);
    const exitIndex = t.exitTime === undefined ? -1 : times.findIndex(v => v >= t.exitTime!);
    tradeContext = {
      ...t,
      entryIndex: entryIndex < 0 ? null : entryIndex,
      entryCandleTime: entryIndex < 0 ? null : times[entryIndex],
      exitIndex: exitIndex < 0 ? null : exitIndex,
      exitCandleTime: exitIndex < 0 ? null : times[exitIndex],
    };
  }

  return {
    schemaVersion: "1.0.0",
    mode: "analysis-only",
    symbol: body.symbol,
    timeframe: body.timeframe,
    candleCount: candles.length,
    firstCandleTime: times[0],
    lastCandleTime: times[times.length - 1],
    latestClose: closes[closes.length - 1],
    trade: tradeContext,
    layers: results,
    warnings: [
      "Indicator layers are descriptive and do not constitute a validated trading strategy.",
      "Fibonacci levels use the highest high and lowest low in the selected lookback; swing direction is not inferred.",
      "No broker orders are created or modified by this Worker.",
    ],
  };
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }
    if (url.pathname === "/health" && request.method === "GET") {
      return json({ ok: true, service: "strategy-gis-worker", version: "1.0.0", mode: "analysis-only" });
    }
    if (url.pathname !== "/api/v1/strategy-gis/analyze" || request.method !== "POST") {
      return json({ error: "not_found", message: "Use POST /api/v1/strategy-gis/analyze or GET /health." }, 404);
    }
    let body: AnalyzeRequest;
    try {
      body = await request.json() as AnalyzeRequest;
    } catch {
      return json({ error: "invalid_json" }, 400);
    }
    if (!body || typeof body.symbol !== "string" || body.symbol.length > 32 ||
        typeof body.timeframe !== "string" || body.timeframe.length > 16 || !validateCandles(body.candles)) {
      return json({ error: "invalid_request", message: "Provide symbol, timeframe, and 3–2000 valid chronological OHLC candles." }, 400);
    }
    const allowed: LayerId[] = ["ema", "rsi", "macd", "fibonacci", "atr"];
    if (body.layers && Object.keys(body.layers).some(key => !allowed.includes(key as LayerId) || typeof body.layers![key as LayerId] !== "boolean")) {
      return json({ error: "invalid_layers", message: "Layer flags must be boolean and use supported layer IDs." }, 400);
    }
    try {
      return json(analyze(body));
    } catch {
      return json({ error: "analysis_failed", message: "Analysis failed; no trading action was taken." }, 422);
    }
  },
};

function corsHeaders(): HeadersInit {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type, authorization",
    "access-control-max-age": "86400",
  };
}
