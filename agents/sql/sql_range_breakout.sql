-- Agent SQL n°3 : cassure du plus haut / plus bas des 24 bougies précédentes (~2 h en M5).
-- Stop = 1,5 × amplitude moyenne des 14 dernières bougies.
WITH last25 AS (
  SELECT timestamp, high, low, close FROM bars
  WHERE symbol = '{symbol}' AND tf = '{tf}'
  ORDER BY timestamp DESC LIMIT 25
),
cur AS (SELECT timestamp, close FROM last25 ORDER BY timestamp DESC LIMIT 1),
rangebox AS (
  SELECT max(w.high) AS hi, min(w.low) AS lo, avg(w.high - w.low) AS ar, count() AS n
  FROM last25 w CROSS JOIN cur c WHERE w.timestamp < c.timestamp
)
SELECT
  c.timestamp AS bar_ts,
  CASE WHEN g.n < 24 OR g.ar <= 0 THEN 'NONE'
       WHEN c.close > g.hi THEN 'BUY'
       WHEN c.close < g.lo THEN 'SELL'
       ELSE 'NONE' END AS action,
  c.close AS entry,
  1.5 * g.ar AS r,
  'Cassure du range 24 bougies' AS reason
FROM cur c CROSS JOIN rangebox g;
