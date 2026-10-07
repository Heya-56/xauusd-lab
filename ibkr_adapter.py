class IBKRAdapter:
    name = "ibkr"

    def candles(self, symbol, timeframe, start=None, end=None):
        raise NotImplementedError(
            "IBKR adapter is intentionally disabled in v0.1. "
            "Implement and validate market-data access in Paper Trading first."
        )
