from abc import ABC, abstractmethod

class MarketDataAdapter(ABC):
    name = "adapter"

    @abstractmethod
    def candles(self, symbol, timeframe, start=None, end=None):
        raise NotImplementedError
