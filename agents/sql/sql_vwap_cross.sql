-- Agent SQL n°2 : croisement du VWAP glissant (48 bougies, ~4 h en M5) dans le sens de la pente.
-- Poids = volume, ou nombre de ticks si le flux ne fournit pas de volume.
-- Stop = moyenne des 14 dernières amplitudes (high - low).
WITH last49 AS (
  SELECT timestamp, high, low, close,
         CASE WHEN volume > 0 THEN volume ELSE CAST(ticks AS DOUBLE) END AS w
  FROM bars WHERE symbol = '{symbol}' AND tf = '{tf}'
  ORDER BY timestamp DESC LIMIT 49
),
cur AS (SELECT timestamp, close FROM last49 ORDER BY timestamp DESC LIMIT 1),
prev AS (SELECT p.close AS prev_close FROM last49 p CROSS JOIN cur c WHERE p.timestamp < c.timestamp ORDER BY p.timestamp DESC LIMIT 1),
vw AS (
  SELECT sum(w.close * w.w) / sum(w.w) AS vwap, count() AS n
  FROM last49 w CROSS JOIN cur c WHERE w.timestamp < c.timestamp
),
rng AS (
  SELECT avg(x.high - x.low) AS ar FROM (SELECT high, low FROM last49 ORDER BY timestamp DESC LIMIT 14) x
)
SELECT
  c.timestamp AS bar_ts,
  CASE WHEN v.n < 48 OR v.vwap IS NULL OR g.ar <= 0 THEN 'NONE'
       WHEN p.prev_close <= v.vwap AND c.close > v.vwap THEN 'BUY'
       WHEN p.prev_close >= v.vwap AND c.close < v.vwap THEN 'SELL'
       ELSE 'NONE' END AS action,
  c.close AS entry,
  g.ar AS r,
  'Croisement du VWAP 48 bougies' AS reason
FROM cur c CROSS JOIN prev p CROSS JOIN vw v CROSS JOIN rng g;
