# XAUUSD Lab — bot de trading (mode papier)

Bot de démonstration Hinova Digital : architecture complète d'un système de trading automatisé sur l'or (XAUUSD).

> ⚠️ **Mode papier uniquement.** Aucun ordre réel n'est envoyé (`live_orders_enabled: false`).
> Le trading comporte un risque de perte en capital. Un backtest ne garantit aucune performance future.

## Architecture

```
Données (CSV MT5/TradingView · Yahoo · IBKR) ─┐
TradingView webhook (bougie clôturée) ────────┤
                                              ▼
                Stratégie (src/strategies) → Moteur de risque (src/engine/risk.py)
                                              ▼
              Position papier (TP1 50 % · point mort · TP2 · SL · sortie temps)
                                              ▼
                       Journal SQLite (bougies, signaux, décisions, trades)
```

Le même moteur sert au **backtest** et au **temps réel** : ce qui est testé est ce qui tourne.

## Stratégie de démonstration (`ema_cross`)

- Signal : croisement EMA20 / EMA50 à la clôture
- Stop : 0,5 × ATR(14) · TP1 : 1R sur 50 % · TP2 : 2R sur 50 % · stop au point mort après TP1
- Une position à la fois, 1 trade par jour, lun/mer/ven 14h–18h (Paris)
- Risque 0,25 % par trade, perte journalière max 0,5 %, taille plafonnée à 0,01 lot
- Coûts inclus : spread 0,30 $ + slippage 0,05 $ par once (`config/experiment.yml`)

## Démarrage

```bash
pip install -r requirements.txt
pytest -q                                          # 14 tests
python -m src.main check                           # vérifie la configuration
python -m src.main backtest --csv XAUUSD_M5.csv    # export MT5 ou TradingView
python -m src.main backtest --yahoo                # recherche rapide (GC=F, pas le spot)
python -m src.main replay --csv XAUUSD_M5.csv      # rejoue l'historique dans le moteur papier
WEBHOOK_SECRET=... python -m src.main serve        # webhook TradingView
```

Le backtest affiche les résultats **in-sample (70 %) et out-of-sample (30 %)** séparément et écrit `results/backtest.json` + `results/trades.csv`.
Sous 30 trades, le résultat est signalé comme non significatif.

Export CSV depuis MT5 : *Affichage › Symboles › Barres › XAUUSD M5 › Exporter*.

## Arborescence

| Dossier | Rôle |
|---|---|
| `src/strategies/` | Stratégies (ajouter une classe + l'enregistrer dans `registry.py`) |
| `src/engine/` | Risque, position, backtest, moteur papier |
| `src/data/` | Adaptateurs CSV, Yahoo, IBKR |
| `src/execution/ibkr.py` | Exécution IBKR protégée (bloquée sans `XAUUSD_LIVE_ORDERS=true` + aperçu what-if) |
| `src/api.py` | Webhook FastAPI + endpoints lecture seule pour un dashboard |
| `research/` | Compétition de 50 tests multi-stratégies (GitHub Actions) |
| `docs/` | Mini-livret et guide webhook TradingView |

## Passer en réel (pas avant)

1. ≥ 30 trades out-of-sample positifs **avec coûts**, sur données du broker réel
2. ≥ 4 semaines de papier en conditions réelles, écarts papier/backtest expliqués
3. Brancher l'exécution broker derrière le moteur de risque, avec kill-switch et alertes
