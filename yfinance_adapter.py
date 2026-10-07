import pandas as pd
import yfinance as yf
from .base import MarketDataAdapter

class YFinanceAdapter(MarketDataAdapter):
    name = "yfinance"

    def candles(self, symbol="XAUUSD", timeframe="5m", start=None, end=None):
        ticker = "GC=F" if symbol == "XAUUSD" else symbol
        df = yf.download(
            ticker, start=start, end=end, interval=timeframe,
            auto_adjust=False, progress=False
        )
        if df.empty:
            return df
        if hasattr(df.columns, "levels"):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns=str.lower)
        required = ["open", "high", "low", "close"]
        df = df[[c for c in required if c in df.columns]].dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        return df
