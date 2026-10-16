# HinovaScalpIndicator — indicateur de scalping XAUUSD (aucun ordre)

Code original Hinova Digital. Aucun code tiers (Market/CodeBase MQL5) n'est repris.

**Ce que ça fait** : flèches achat/vente sur bougies **clôturées** (M1–M15), avec SL/TP *indicatifs* en commentaire.
- Tendance : EMA 9 vs EMA 50 (deux bougies d'accord).
- Déclencheur : pullback sur l'EMA rapide, puis clôture directionnelle du bon côté.
- Filtres : ATR minimum, spread maximum, session horaire serveur, délai entre deux signaux.

**Ce que ça ne fait pas** : aucun ordre, aucune requête réseau, aucune promesse de performance.
Les flèches ne sont pas une stratégie validée : elles doivent passer le walk-forward du lab (jauge ≥ 6) avant toute confiance.

**Installation** : copier ce dossier dans `MQL5/Indicators/`, ouvrir dans MetaEditor, F7, puis glisser sur un graphique XAUUSD.
**Statut** : non compilé ici (MetaEditor = Windows). Envoie-moi le résultat de F7.

Réglages à ajuster par broker : `InpMinAtr` (en $), `InpMaxSpreadPts` (en points broker), heures de session (heure **serveur**).
