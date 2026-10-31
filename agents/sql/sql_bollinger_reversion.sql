-- Agent SQL n°1 : retour à la moyenne sur bandes de Bollinger (20 bougies, 2 écarts-types).
-- Achat quand la dernière clôture repasse au-dessus de la bande basse ; vente au retour sous la bande haute.
-- Stop = 1 écart-type ; TP1 = 1R ; TP2 = 2R.
WITH last21 AS (
  SELECT timestamp, close FROM bars
  WHERE symbol = '{symbol}' AND tf = '{tf}'
  ORDER BY timestamp DESC LIMIT 21
),
cur AS (SELECT timestamp, close FROM last21 ORDER BY timestamp DESC LIMIT 1),
prev AS (SELECT p.close AS prev_close FROM last21 p CROSS JOIN cur c WHERE p.timestamp < c.timestamp ORDER BY p.timestamp DESC LIMIT 1),
band AS (
  SELECT avg(w.close) AS mid, stddev_samp(w.close) AS sd, count() AS n
  FROM last21 w CROSS JOIN cur c WHERE w.timestamp < c.timestamp
)
SELECT
  c.timestamp AS bar_ts,
  CASE WHEN b.n < 20 OR b.sd <= 0 THEN 'NONE'
       WHEN p.prev_close < b.mid - 2 * b.sd AND c.close >= b.mid - 2 * b.sd THEN 'BUY'
       WHEN p.prev_close > b.mid + 2 * b.sd AND c.close <= b.mid + 2 * b.sd THEN 'SELL'
       ELSE 'NONE' END AS action,
  c.close AS entry,
  b.sd AS r,
  'Bollinger 20/2 : retour dans les bandes' AS reason
FROM cur c CROSS JOIN prev p CROSS JOIN band b;
