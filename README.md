# Test Création Bot — XAUUSD

Bot pédagogique minimaliste pour comprendre l'architecture d'un système de trading automatisé.

> ⚠️ Prototype éducatif. Aucun ordre réel n'est envoyé par ce projet.

## Architecture

TradingView → webhook FastAPI → moteur de stratégie → calcul du risque → signal → journal SQL.

Le dashboard n'est qu'une interface. Le moteur reste côté serveur.

## Stratégie simple

- Actif : XAUUSD
- Signal : croisement EMA 20 / EMA 50
- Entrée : clôture de la bougie confirmant le croisement
- Stop : 0,5 × ATR(14)
- TP1 : 1R sur 50 % de la position
- TP2 : 2R sur 50 % de la position
- Une seule position à la fois
- Risque cible : 0,25 % du capital
- Perte journalière maximale : 0,50 %
- Taille plafonnée à 0,01 lot dans le prototype
- Mode par défaut : signal/paper, jamais exécution réelle

## Important

Trading comporte un risque de perte. Un backtest ou un signal ne garantit aucune performance future.
