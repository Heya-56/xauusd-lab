# Brancher TradingView sur le bot (mode papier)

## 1. Lancer le serveur

```bash
pip install -r requirements.txt
export WEBHOOK_SECRET="une-longue-chaine-aleatoire"
python -m src.main serve --port 8000
```

Le serveur doit être joignable en HTTPS depuis Internet (VPS, Cloudflare Tunnel, Render, Fly.io…).
TradingView n'accepte que les ports 80 et 443.

## 2. Créer l'alerte sur TradingView

- Graphique : **XAUUSD**, unité de temps **5 minutes** (identique à `experiment.timeframe`).
- Condition : n'importe quelle condition déclenchée **une fois par clôture de barre** (par exemple « XAUUSD › Croisement » ou un indicateur vide).
- Webhook URL : `https://votre-domaine/webhook/tradingview`
- Message :

```json
{
  "secret": "une-longue-chaine-aleatoire",
  "symbol": "{{ticker}}",
  "time": "{{time}}",
  "open": {{open}},
  "high": {{high}},
  "low": {{low}},
  "close": {{close}},
  "volume": {{volume}}
}
```

TradingView envoie la bougie ; **le calcul des EMA, de l'ATR, du risque et des positions se fait côté serveur**.
Il faut au moins 51 bougies avant le premier signal : rejouer l'historique avec `replay --csv` ou attendre ~4 h en M5.

## 3. Suivre

- `GET /api/status` : capital papier, position ouverte
- `GET /api/signals` : chaque signal et la décision du moteur de risque
- `GET /api/trades` : trades clôturés (TP1, TP2, BE, SL, TIME)
