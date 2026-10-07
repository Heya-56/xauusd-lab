CREATE TABLE IF NOT EXISTS candles (
 id bigserial PRIMARY KEY, symbol text NOT NULL DEFAULT 'XAUUSD',
 timeframe text NOT NULL DEFAULT '15m', ts timestamptz NOT NULL,
 open numeric NOT NULL, high numeric NOT NULL, low numeric NOT NULL,
 close numeric NOT NULL, volume numeric DEFAULT 0,
 UNIQUE(symbol,timeframe,ts)
);

CREATE TABLE IF NOT EXISTS signals (
 id bigserial PRIMARY KEY, symbol text NOT NULL DEFAULT 'XAUUSD',
 ts timestamptz NOT NULL DEFAULT now(), action text NOT NULL,
 entry numeric NOT NULL, stop_loss numeric, tp1 numeric, tp2 numeric,
 risk_pct numeric NOT NULL DEFAULT 0.25,
 status text NOT NULL DEFAULT 'PAPER', reason text
);

CREATE TABLE IF NOT EXISTS risk_limits (
 id integer PRIMARY KEY DEFAULT 1,
 risk_per_trade_pct numeric NOT NULL DEFAULT 0.25,
 max_daily_loss_pct numeric NOT NULL DEFAULT 0.50,
 max_position_size numeric NOT NULL DEFAULT 0.01
);

INSERT INTO risk_limits(id) VALUES (1) ON CONFLICT (id) DO NOTHING;
