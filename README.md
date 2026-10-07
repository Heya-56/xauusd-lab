# Test Création Bot — XAUUSD Lab

NE ME CROYEZ PAS. REGARDEZ L’ARCHITECTURE.

Laboratoire pédagogique : données → stratégie → risque → backtest → API → interface.

Stratégie minimale:
- XAUUSD
- EMA 20 / EMA 50
- stop = 0,5 × ATR14
- TP1 = 1R sur 50 %
- TP2 = 2R sur 50 %
- risque théorique = 0,25 % par trade
- perte journalière max = 0,50 %
- taille max du prototype = 0,01 lot
- aucune exécution broker réelle

Architecture:
TradingView/Pine → moteur Python → risque → backtest → SQL/journal → FastAPI → dashboard.

GitHub conserve le code. GitHub Actions lance les tests. Vercel publie l’interface/API légère. Aucun secret broker dans le navigateur.

Lancer:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python backtest.py
uvicorn api:app --reload

TradingView est une couche de visualisation/test via tradingview_strategy.pine. Le webhook est optionnel : le laboratoire n’en dépend pas.

Le dossier data/ contient un petit jeu OHLC synthétique reproductible. Pour une étude sérieuse, utiliser des données historiques fiables et documenter spread, commissions, slippage et gaps.

Avertissement:
Le trading comporte un risque réel de perte. L’automatisation ne garantit aucun bénéfice et un backtest ne garantit pas les performances futures. Ce projet est éducatif/technique et ne constitue pas un conseil en investissement.
