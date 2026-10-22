from .ema_cross import EmaCross
from .macd_cross import MacdCross
from .rsi_reversion import RsiReversion
from .scalp_momentum import ScalpMomentum


class StrategyRegistry:
    def __init__(self):
        self._strategies = {}

    def register(self, strategy):
        self._strategies[strategy.name] = strategy

    def all(self):
        return list(self._strategies.values())

    def get(self, name):
        if name not in self._strategies:
            raise KeyError(f"Stratégie inconnue : {name}. Disponibles : {', '.join(self._strategies)}")
        return self._strategies[name]


def default_registry() -> StrategyRegistry:
    """Agents Python : 3 agents de fond (M5) + 1 agent de scalping (M1)."""
    reg = StrategyRegistry()
    for s in (EmaCross(), MacdCross(), RsiReversion(), ScalpMomentum()):
        reg.register(s)
    return reg
