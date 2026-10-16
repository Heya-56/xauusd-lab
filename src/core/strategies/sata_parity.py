"""Placeholder for exact S.A.T.A. / MQL5 EA parity.

Registered so the dashboard can show it, but NOT evaluable: the .mq5/.mqh/.set
sources are absent from the repository (audit 2026-10-15). No rule is guessed.
"""
from src.core.strategies.base import Strategy


class SataParity(Strategy):
    strategy_id = "sata_mql5_parity"
    version = "0.0.0"
    name = "S.A.T.A. EA parity"
    description = "Exact reproduction of the MQL5 EA. Requires the audited .mq5 source."
    available = False
    unavailable_reason = "MQL5_SOURCE_MISSING"

    def evaluate(self, series):
        raise RuntimeError("sata_mql5_parity is unavailable: MQL5 source missing")
