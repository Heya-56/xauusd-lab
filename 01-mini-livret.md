# Mini-livret — XAUUSD Lab depuis un téléphone

## 1. Créer le dépôt

Sur GitHub depuis le téléphone:
1. + -> New repository
2. Nom: xauusd-lab
3. Créer le dépôt
4. Importer le contenu de cette archive

## 2. Premier test

GitHub -> Actions -> Lab smoke test -> Run workflow.

Le résultat attendu est un check vert.

## 3. Expérience standard

- XAUUSD
- 14:00 Pacific/Tahiti
- lundi / mercredi / vendredi
- M5
- maximum 1 trade par journée d'expérience
- backtest d'abord

## 4. Candidats open source

Pour chaque repo candidat, conserver:
- URL
- licence
- stars/forks au moment de l'import
- activité récente
- timeframe
- dépendances
- règles
- métriques annoncées
- métriques reproduites
- résultats out-of-sample
- sensibilité aux coûts/slippage

Un README n'est jamais traité comme une preuve de performance.

## 5. Données

yfinance sert au prototypage/recherche. IBKR devient la référence pour la phase Paper Trading.

## 6. Progression

1. smoke test
2. data adapters
3. registre de 5 à 11 candidats
4. normalisation des signaux
5. backtest commun
6. out-of-sample
7. Paper Trading IBKR
8. seulement ensuite étude d'une architecture live

## 7. Sécurité

Aucune clé IBKR dans Git. Aucun ordre live dans v0.1.
