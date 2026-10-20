# XAUUSD Lab — bot de trading (mode papier)

Bot de démonstration Hinova Digital : architecture complète d'un système de trading automatisé sur l'or (XAUUSD).

> ⚠️ **Mode papier uniquement.** Aucun ordre réel n'est envoyé (`live_orders_enabled: false`).
> Le trading comporte un risque de perte en capital. Un backtest ne garantit aucune performance future.

## Architecture

```
 Sources de données                 Bus d'événements (Rust)                 Agents de stratégie
 ─────────────────                 ───────────────────────                 ───────────────────
 MT5 (src/feeders/mt5.py) ──┐                                         ┌─▶ Python : ema_cross
 Replay CSV (feeders/replay)├─ WS ─▶  /publish  ── ticks ──▶ bougies ─┤   Python : macd_cross
 API broker                 ┘        (tokio)       │      M5 clôturées│   Python : rsi_reversion
                                                   │                  ├─▶ SQL : sql_bollinger_reversion
                                      /subscribe ◀─┘ ticks + bars ────┤   SQL : sql_vwap_cross
                                                   │                  └─▶ SQL : sql_range_breakout
                                                   ▼                              │
                                         QuestDB (ILP 9009) ◀── signaux ──────────┘
                                         ticks · bars · signals
                                                   │
                                                   ▼
                                  API interface (FastAPI) : /api/agents · /api/consensus
```

- **Bus Rust** (`bus/`) : reçoit les ticks en WebSocket, les diffuse aux agents, agrège les bougies (5 min par défaut) et écrit ticks + bougies dans QuestDB. Tampon et reconnexion si QuestDB tombe.
- **Agents Python** (`src/strategies/`) : calculés en mémoire à chaque bougie clôturée, préchargés depuis QuestDB au démarrage.
- **Agents SQL** (`agents/sql/*.sql`) : requêtes exécutées par QuestDB lui-même sur la table `bars`.
- **QuestDB** : tables `ticks`, `bars`, `signals` (créées automatiquement). Chaque signal porte l'agent, le langage, l'action, entrée, stop, TP1, TP2 et la raison.
- **Interface** : `/api/agents` (dernier signal des 6 agents) et `/api/consensus` (vote pondéré, poids dans `config/experiment.yml`).
- **Moteur papier & backtest** (`src/engine/`) : moteur de risque, positions TP1/TP2/point mort, journal SQLite et webhook TradingView.

### Lancer la pile complète

```bash
docker compose up -d --build                         # QuestDB + bus + agents + API
python -m src.feeders.replay XAUUSD_M5.csv           # rejouer un export MT5
python -m src.feeders.mt5 --url ws://IP:9100/publish # flux temps réel (Windows + MT5)
```

Sans Docker : `cd bus && cargo run --release`, puis `python -m src.agents.runner all` et `uvicorn src.api:app`.
Variables utiles : `BUS_TOKEN` (protège `/publish`), `BAR_SECONDS`, `QUESTDB_ILP`, `QUESTDB_HTTP`.

## Moteur papier — stratégie de référence (`ema_cross`)

- Signal : croisement EMA20 / EMA50 à la clôture
- Stop : 0,5 × ATR(14) · TP1 : 1R sur 50 % · TP2 : 2R sur 50 % · stop au point mort après TP1
- Une position à la fois, 1 trade par jour, lun/mer/ven 14h–18h (Paris)
- Risque 0,25 % par trade, perte journalière max 0,5 %, taille plafonnée à 0,01 lot
- Coûts inclus : spread 0,30 $ + slippage 0,05 $ par once (`config/experiment.yml`)

## Démarrage

```bash
pip install -r requirements.txt
(cd bus && cargo test)                             # bus Rust
pytest -q                                          # 23 tests, dont bout en bout bus → agents
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
| `bus/` | Bus d'événements Rust (WebSocket, agrégation, écriture QuestDB) |
| `src/strategies/` | 3 agents Python (ajouter une classe + l'enregistrer dans `registry.py`) |
| `agents/sql/` | 3 agents SQL exécutés par QuestDB |
| `src/agents/` | Runner des agents, client QuestDB |
| `src/feeders/` | Sources : replay CSV, MT5 |
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
