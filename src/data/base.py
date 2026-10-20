from abc import ABC, abstractmethod


class MarketDataAdapter(ABC):
    """Toutes les sources renvoient une liste de bougies :
    {"ts": ISO-8601 UTC, "open", "high", "low", "close", "volume"} triées par date croissante."""

    name = "adapter"

    @abstractmethod
    def candles(self, symbol, timeframe, start=None, end=None):
        raise NotImplementedError
