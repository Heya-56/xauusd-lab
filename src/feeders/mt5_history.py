"""Chargement MANUEL de l'historique MT5 dans QuestDB (optionnel, jamais lancé par DEMARRER.bat).
Usage, MT5 ouvert et connecté :  py -m src.feeders.mt5_history --symbol GOLD"""
from __future__ import annotations

import argparse


def bar_lines(symbol: str, tf_s: int, rates, point: float) -> str:
    """Bougies MT5 (copy_rates) -> lignes ILP de la table `bars`, même format que le bus Rust.
    Les horodatages restent à l'heure du serveur MT5, comme les ticks en direct."""
    out = []
    for r in rates:
        t, o, h, l, c = int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        vol = float(r["tick_volume"]); spread = float(r["spread"]) * point
        out.append(f"bars,symbol={symbol},tf={tf_s}s open={o},high={h},low={l},close={c},volume={vol},"
                   f"ticks={int(vol)}i,spread={spread} {t * 1_000_000_000}\n")
    return "".join(out)


def backfill(mt5, symbol: str, counts=((60, 5000), (300, 20000))) -> None:
    """Charge l'historique M1 / M5 de MT5 dans QuestDB au démarrage : agents et baromètre
    disposent tout de suite de ~2 mois d'historique au lieu de devoir l'accumuler en direct."""
    from src.agents.questdb import QuestDB
    db = QuestDB()
    for sql in ("ALTER TABLE bars DEDUP ENABLE UPSERT KEYS(timestamp, symbol, tf)",):
        try:
            db.query(sql)       # évite les doublons si on recharge plusieurs fois
        except Exception:
            pass                # table pas encore créée : elle le sera par l'écriture ci-dessous
    point = mt5.symbol_info(symbol).point
    tfs = {60: mt5.TIMEFRAME_M1, 300: mt5.TIMEFRAME_M5}
    for tf_s, n in counts:
        rates = mt5.copy_rates_from_pos(symbol, tfs[tf_s], 1, n)   # 1 = on saute la bougie en cours
        if rates is None or len(rates) == 0:
            print(f"Historique {tf_s}s indisponible : {mt5.last_error()}")
            continue
        lines = bar_lines(symbol, tf_s, rates, point)
        for i in range(0, len(lines), 2_000_000):
            db.write(lines[i:i + 2_000_000])
        print(f"Historique chargé dans QuestDB : {len(rates)} bougies {tf_s}s")
    try:
        db.query("ALTER TABLE bars DEDUP ENABLE UPSERT KEYS(timestamp, symbol, tf)")
    except Exception:
        pass



if __name__ == "__main__":
    import MetaTrader5 as mt5
    p = argparse.ArgumentParser(); p.add_argument("--symbol", default="GOLD"); a = p.parse_args()
    if not mt5.initialize():
        raise SystemExit(f"MT5 non initialisé : {mt5.last_error()}")
    mt5.symbol_select(a.symbol, True)
    backfill(mt5, a.symbol)
    print("Terminé.")
