class StrategyRegistry:
    def __init__(self):
        self._strategies = {}

    def register(self, strategy):
        self._strategies[strategy.name] = strategy

    def all(self):
        return list(self._strategies.values())

    def get(self, name):
        return self._strategies[name]
