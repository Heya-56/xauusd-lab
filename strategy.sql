-- TEST CRÉATION BOT — moteur SQL pédagogique
CREATE OR REPLACE FUNCTION generate_xauusd_signal(
  p_price numeric, p_ema20 numeric, p_ema50 numeric,
  p_prev_ema20 numeric, p_prev_ema50 numeric, p_atr14 numeric,
  p_side_allowed text DEFAULT 'BOTH'
)
RETURNS TABLE(action text, entry numeric, stop_loss numeric, tp1 numeric, tp2 numeric, reason text)
LANGUAGE plpgsql AS $$
DECLARE r numeric;
BEGIN
  r := 0.5 * p_atr14;
  IF p_prev_ema20 <= p_prev_ema50 AND p_ema20 > p_ema50 AND p_side_allowed IN ('BOTH','LONG') THEN
    RETURN QUERY SELECT 'BUY', p_price, p_price-r, p_price+r, p_price+2*r, 'EMA20 crossed above EMA50';
    RETURN;
  END IF;
  IF p_prev_ema20 >= p_prev_ema50 AND p_ema20 < p_ema50 AND p_side_allowed IN ('BOTH','SHORT') THEN
    RETURN QUERY SELECT 'SELL', p_price, p_price+r, p_price-r, p_price-2*r, 'EMA20 crossed below EMA50';
    RETURN;
  END IF;
  RETURN QUERY SELECT 'NONE', p_price, NULL::numeric, NULL::numeric, NULL::numeric, 'No confirmed crossover';
END; $$;
