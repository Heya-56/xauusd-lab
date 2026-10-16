# Fiche d'installation et de test — Hinova Trading Lab

> Règle d'or : **aucun ordre réel**. Les deux EA n'exécutent jamais de trade. Tests sur **compte démo** uniquement.

## 0. Ce qu'il faut sur l'ordinateur

| Outil | Version | Pour quoi |
|---|---|---|
| Python | 3.11 ou plus | Moteur de calcul, tests, recherche |
| Node.js | 22 | Worker (comptes, passerelle EA) |
| MetaTrader 5 + MetaEditor | Windows | Les deux EA |
| Git (facultatif) | — | Récupérer les mises à jour |

## 1. Décompresser

Dézipper `xauusd-lab.zip` → un dossier `xauusd-lab/`. Ouvrir un terminal **dans ce dossier**.

## 2. Tester le moteur Python

```bash
python -m pip install pytest
python -m pytest -q
```
Attendu : `136 passed, 2 skipped`. Rien d'autre à installer (bibliothèque standard uniquement).

Lancer la recherche quotidienne sur données de démonstration :
```bash
python -m research.daily_research --help
```
Les résultats synthétiques sont marqués comme tels : ce ne sont **pas** des performances réelles.

## 3. Tester le Worker (comptes + passerelle MT5)

```bash
cd workers/accounts-api
npm ci
npm test
```
Attendu : `16` tests réussis (dont 2 avec le vrai moteur Python).

## 4. Parcours complet en local (facultatif)

Suivre `docs/DEPLOYMENT-CLOUDFLARE.md` → section « Local development ». Résumé :
1. Terminal 1 : `HINOVA_ENGINE_SECRET=<32+ caractères> python -m src.api.engine_http`
2. Terminal 2 : dans `workers/accounts-api`, copier `wrangler.example.toml` en `wrangler.toml` (`DEV_MODE="true"`, `ENGINE_URL=http://127.0.0.1:8090`), créer `.dev.vars` avec `ENGINE_SECRET=<même secret>`, puis
   `npx wrangler d1 migrations apply hinova-trading-lab --local && npx wrangler dev --local`
3. Terminal 3 : `python -m http.server 8765 --directory web` puis ouvrir `http://localhost:8765/account.html`
4. Créer un compte → confirmer → créer une clé de terminal (`htl_...`).

## 5. Installer les EA dans MetaTrader 5

1. MT5 → **Fichier → Ouvrir le dossier des données** → `MQL5/Experts/`.
2. Copier les dossiers `mql5/HinovaBridge/` et `mql5/HinovaGoldScanner/` dedans.
3. Ouvrir MetaEditor (F4), ouvrir `HinovaBridge.mq5` → **F7** (compiler). Idem `HinovaGoldScanner.mq5`.
   Noter toute erreur/avertissement et me l'envoyer tel quel.
4. **Outils → Options → Expert Advisors** → cocher « Autoriser WebRequest pour les URL listées » et ajouter l'URL de l'API
   (en local : `http://127.0.0.1:8787` ; MT5 peut exiger HTTPS hors local).
5. Ouvrir un graphique **XAUUSD M15** sur un compte **démo**, glisser `HinovaBridge` dessus et remplir :

| Paramètre | Valeur |
|---|---|
| `InpApiUrl` | URL de l'API, sans `/` final |
| `InpTerminalKey` | la clé `htl_...` de « Mon compte » |
| `InpTimeframe` | identique au profil choisi (M15 pour intraday) |
| `InpBars` | 400 |
| `InpInstrumentType` | `cfd` (ou `spot`) — jamais futures |

6. Attendu : un panneau BUY / SELL / NO_TRADE à chaque bougie clôturée, et le signal visible sur le dashboard.
   Le bouton « Trading algorithmique » peut rester désactivé : l'EA n'en a pas besoin, il ne trade pas.

`HinovaGoldScanner` : glisser sur XAUUSD ; renseigner le nom du symbole GC de ton broker (il varie : `GC`, `GOLD.f`, `XAUUSD.fut`…). Il compare et journalise, il ne trade pas.

## 6. Prompts prêts à copier

À utiliser dans MetaEditor (assistant IA), Claude ou un autre assistant. Ils imposent les règles du projet.

### Prompt A — corriger une erreur de compilation
```
Tu es expert MQL5. Voici le fichier HinovaBridge.mq5 et les erreurs de compilation de MetaEditor (build XXXX).
Corrige UNIQUEMENT ces erreurs, avec le changement minimal.
Interdits : ajouter OrderSend, CTrade, PositionOpen ou toute exécution d'ordre ; changer le format JSON envoyé ;
envoyer la bougie en cours (seulement les bougies clôturées) ; logguer la clé de terminal.
Rends le diff ligne par ligne puis le fichier complet.
[coller les erreurs]
[coller le fichier]
```

### Prompt B — relire l'EA avant test démo
```
Relis cet EA MQL5 comme un auditeur. Vérifie et liste avec numéros de ligne :
1) aucune fonction d'exécution d'ordre n'existe ; 2) seules les bougies clôturées (shift >= 1) sont envoyées ;
3) WebRequest gère timeout, code HTTP != 200 et JSON invalide sans planter ; 4) la clé n'apparaît jamais dans les logs ;
5) l'encodage UTF-8 du corps est correct. Ne réécris rien : signale seulement.
```

### Prompt C — adapter le Scanner au symbole GC de mon broker
```
Dans HinovaGoldScanner, le symbole futures or chez mon broker s'appelle "<NOM>".
Explique où le renseigner (paramètre d'entrée), sans modifier la logique.
Le scanner ne doit jamais trader et ne doit jamais présenter des données futures comme du spot XAUUSD.
```

### Prompt D — exporter des données XAUUSD réelles depuis MT5
```
Écris un script MQL5 (Script, pas EA) qui exporte en CSV les bougies clôturées de XAUUSD
pour l'unité de temps du graphique : colonnes ts (Unix UTC), open, high, low, close, spread.
Inclure le décalage horaire du serveur broker dans l'en-tête. Aucun ordre, aucune requête réseau.
```

### Prompt E — écrire une nouvelle stratégie (côté Python, pas MQL5)
```
Dans le repo xauusd-lab, ajoute une stratégie déterministe dans src/core/strategies/ en suivant l'interface
des stratégies existantes et le registre. Pas d'IA dans les calculs, pas d'accès au futur (uniquement les
bougies <= i). Ajoute ses tests et une petite grille dans config/wf_grids.json (16 combinaisons max).
Elle sera notée par walk-forward : < 5 rejetée, 5-6 orange, >= 6 retenue.
```

## 7. Ce qu'il me faut ensuite
- Le résultat de F7 pour les deux EA.
- Le nom du symbole GC chez ton broker.
- Un export CSV XAUUSD réel (prompt D).
- Ton feu vert + les secrets pour le déploiement preview.
