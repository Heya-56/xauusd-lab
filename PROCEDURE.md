# Procédure — Test Création Bot

## 0. Principe

Le laboratoire reste en mode paper/signal. Il ne passe aucun ordre réel.

Flux:
1. TradingView affiche/teste la stratégie.
2. Python calcule EMA, ATR, entrée, stop et objectifs.
3. Le moteur de risque limite la taille.
4. Le backtest rejoue les bougies.
5. SQL peut journaliser les événements.
6. FastAPI expose les résultats.
7. Le dashboard affiche les résultats.
8. GitHub Actions vérifie le code.
9. Vercel héberge l’interface/API légère.

## 1. Installer gratuitement

Installer Python 3.12 et Git.

Puis:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Windows PowerShell:
.venv\Scripts\Activate.ps1

## 2. Vérifier le moteur

pytest -q

Puis:

python backtest.py

Le résultat affiche capital initial, capital final, PnL, nombre de trades, taux de réussite et profit factor.

## 3. Comprendre le signal

EMA20 croise EMA50 vers le haut = LONG.
EMA20 croise EMA50 vers le bas = SHORT.

ATR14 mesure une volatilité récente.
Stop = 0,5 ATR.
1R = distance entre entrée et stop.
TP1 = 1R.
TP2 = 2R.

La position est pensée en deux moitiés:
50 % à TP1, 50 % à TP2.

## 4. Comprendre le risque

Risque cible = 0,25 % du capital.
Perte journalière maximale = 0,50 %.
Taille maximale du prototype = 0,01 lot.

Le calcul de lot est volontairement pédagogique. Le contrat XAUUSD exact dépend du broker et doit être vérifié avant toute utilisation réelle.

## 5. TradingView

Ouvrir XAUUSD dans TradingView.
Créer un Pine Script avec le contenu de tradingview_strategy.pine.
Ajouter le script au graphique.
Utiliser le Strategy Tester pour observer les résultats.

Le webhook est une extension facultative. Ne pas construire le laboratoire autour d’une fonctionnalité de plan payant ou non disponible sur le compte.

## 6. API locale

uvicorn api:app --reload

Ouvrir:
http://127.0.0.1:8000/docs

Endpoints principaux:
GET /api/health
GET /api/strategy
GET /api/backtest
POST /api/signal
POST /webhook/tradingview

Le webhook ne transmet aucun ordre à un broker.

## 7. SQL

Créer une base SQLite locale puis exécuter schema.sql.

Les tables sont volontairement simples:
candles
signals
trades
risk_limits

Le but pédagogique est de voir ce qu’une base fait, pas de cacher l’architecture derrière une plateforme.

## 8. GitHub

Chaque push déclenche .github/workflows/test.yml.

Le workflow:
- installe Python
- installe les dépendances
- lance pytest

GitHub Actions automatise la vérification. Il ne constitue pas la stratégie.

## 9. Vercel

Importer le dépôt GitHub dans Vercel.
Le projet utilise vercel.json.
La page web est dans web/.
L’API Python est dans api/index.py.

Ne jamais mettre de clés broker dans le frontend.

## 10. Avant tout argent réel

Remplacer les données synthétiques.
Vérifier le symbole exact et le contrat.
Ajouter spread, commissions et slippage.
Tester plusieurs périodes.
Séparer période de développement et période de validation.
Faire du paper trading.
Mesurer drawdown, pertes consécutives et stabilité.
Ne jamais conclure qu’un backtest garantit un rendement futur.

## 11. Ce que le projet démontre

Un bot n’est pas une boîte noire magique.

Il est composé de couches:
données + logique + calcul + risque + stockage + tests + interface + infrastructure.

C’est précisément cette architecture qu’il faut demander à voir lorsqu’une personne promet des performances extraordinaires avec un « bot IA ».
