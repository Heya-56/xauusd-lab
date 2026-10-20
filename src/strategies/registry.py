from .ema_cross import EmaCross


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
    reg = StrategyRegistry()
    reg.register(EmaCross())
    return reg
